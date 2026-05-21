from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import UUID

from docx import Document
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag.ocr import OCRService
from app.ai.rag.retrieval import KnowledgeRetrievalService
from app.core.enums import AssetLifecycle, JobType, UsageMetricCode
from app.core.exceptions import NotFoundError
from app.integrations.object_storage import LocalObjectStorage
from app.models.knowledge import KnowledgeAsset
from app.repositories.knowledge import KnowledgeAssetRepository
from app.schemas.knowledge import KnowledgeUploadRequest
from app.services.jobs import JobService
from app.services.brand_assets import BrandAssetService
from app.services.upload_preflight import UploadPreflightService
from app.services.usage import UsageLimitService


class KnowledgeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.assets = KnowledgeAssetRepository(session)
        self.storage = LocalObjectStorage()
        self.ocr = OCRService()
        self.retrieval = KnowledgeRetrievalService()
        self.jobs = JobService(session)
        self.usage = UsageLimitService(session)
        self.preflight = UploadPreflightService()

    @staticmethod
    def _extract_docx_text(absolute_path: str, extracted: dict[str, object]) -> str:
        source_format = str(extracted.get("source_format") or "").lower()
        if source_format != "docx" and not absolute_path.lower().endswith(".docx"):
            return ""
        doc = Document(absolute_path)
        return "\n".join(paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip())

    @staticmethod
    def _read_analysis_text(analysis_path: str | None) -> str:
        if not analysis_path:
            return ""
        path = Path(analysis_path)
        if not path.exists():
            return ""

        raw_text = path.read_text(encoding="utf-8", errors="replace").strip()
        if not raw_text:
            return ""
        if path.suffix.lower() != ".json":
            return raw_text
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            return raw_text
        return json.dumps(parsed, ensure_ascii=False, indent=2)

    async def upload(self, tenant_id: UUID, brand_space_id: UUID, payload: KnowledgeUploadRequest) -> KnowledgeAsset:
        preflight = self.preflight.validate_base64_upload(
            filename=payload.filename,
            mime_type=payload.mime_type,
            content_base64=payload.content_base64,
        )
        stored = self.storage.save_bytes(tenant_id, brand_space_id, "uploads", payload.filename, preflight.content)
        asset = KnowledgeAsset(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            name=payload.name,
            original_filename=payload.filename,
            mime_type=preflight.normalized_mime_type,
            storage_path=stored.storage_path,
            lifecycle_state=AssetLifecycle.INDEXED if payload.skip_processing else AssetLifecycle.UPLOADED,
            channel=payload.channel,
            page_count=preflight.page_count or 0,
            metadata_json={
                **payload.metadata,
                "skip_processing": payload.skip_processing,
                "file_size_bytes": preflight.size_bytes,
                "preflight_page_count": preflight.page_count,
                "preflight_hints": preflight.hints or {},
            },
        )
        if payload.skip_processing:
            asset.page_count = preflight.page_count or (1 if preflight.normalized_mime_type.startswith("image/") else 0)
        await self.assets.add(asset)
        await self.session.commit()
        if not payload.skip_processing:
            await self.jobs.create(
                tenant_id=tenant_id,
                brand_space_id=brand_space_id,
                job_type=JobType.KNOWLEDGE_PROCESS,
                payload={"knowledge_asset_id": str(asset.id)},
                knowledge_asset_id=asset.id,
            )
        return asset

    async def process_asset(self, asset_id: UUID) -> KnowledgeAsset:
        asset = await self.assets.get(asset_id)
        if not asset:
            raise NotFoundError("Knowledge asset not found")
        if asset.field_key:
            return await BrandAssetService(self.session).process_asset(asset_id)
        asset.lifecycle_state = AssetLifecycle.PROCESSING
        asset.processing_error = None
        await self.session.commit()

        try:
            absolute_path = self.storage.absolute_path(asset.storage_path)
            extracted = self.ocr.extract(absolute_path)
            text = extracted.get("text", "")
            if not text:
                text = self._extract_docx_text(absolute_path, extracted)
            analysis_path = extracted.get("analysis_path")
            analysis_text = self._read_analysis_text(analysis_path)
            if analysis_text:
                text = "\n\n".join(part for part in [text, analysis_text] if part).strip()
            image_texts: list[str] = []
            for image_path in extracted.get("images", []):
                if image_path == absolute_path:
                    continue
                try:
                    image_text = self.ocr.extract(image_path).get("text", "")
                except Exception:  # noqa: BLE001
                    image_text = ""
                if image_text:
                    image_texts.append(image_text)
            if image_texts:
                text = "\n\n".join(part for part in [text, *image_texts] if part).strip()

            asset.extracted_text = text or None
            asset.extracted_summary = (text[:1000] if text else None)
            asset.page_count = extracted.get("page_count", 0)
            await self.usage.enforce(asset.tenant_id, UsageMetricCode.OCR_PAGES, max(asset.page_count, 1))
            await self.usage.increment(asset.tenant_id, UsageMetricCode.OCR_PAGES, max(asset.page_count, 1))
            self.retrieval.delete_asset(str(asset.tenant_id), str(asset.brand_space_id), asset.channel, str(asset.id))
            if text:
                self.retrieval.index_asset(
                    tenant_id=str(asset.tenant_id),
                    brand_space_id=str(asset.brand_space_id),
                    channel=asset.channel,
                    source_id=str(asset.id),
                    text=text,
                    metadata={"asset_id": str(asset.id), "filename": asset.original_filename},
                )
                asset.last_indexed_at = datetime.now(timezone.utc).isoformat()
                asset.lifecycle_state = AssetLifecycle.INDEXED
            else:
                asset.lifecycle_state = AssetLifecycle.FAILED
                asset.processing_error = "No extractable text or analysis content found"
            await self.session.commit()
            return asset
        except Exception as exc:  # noqa: BLE001
            asset.lifecycle_state = AssetLifecycle.FAILED
            asset.processing_error = str(exc)
            await self.session.commit()
            raise

    async def list(self, tenant_id: UUID, brand_space_id: UUID) -> list[KnowledgeAsset]:
        return await self.assets.list_by_brand(brand_space_id, tenant_id)

    async def delete(self, asset_id: UUID) -> KnowledgeAsset:
        asset = await self.assets.get(asset_id)
        if not asset:
            raise NotFoundError("Knowledge asset not found")
        self.retrieval.delete_asset(str(asset.tenant_id), str(asset.brand_space_id), asset.channel, str(asset.id))
        asset.lifecycle_state = AssetLifecycle.DELETED
        self.storage.delete(asset.storage_path)
        await self.session.commit()
        return asset

    async def reprocess(self, asset_id: UUID) -> KnowledgeAsset:
        return await self.process_asset(asset_id)

    async def get_scoped(self, tenant_id: UUID, brand_space_id: UUID, asset_id: UUID) -> KnowledgeAsset:
        asset = await self.assets.get_scoped(asset_id, tenant_id, brand_space_id)
        if not asset:
            raise NotFoundError("Knowledge asset not found")
        return asset

    async def delete_scoped(self, tenant_id: UUID, brand_space_id: UUID, asset_id: UUID) -> KnowledgeAsset:
        asset = await self.get_scoped(tenant_id, brand_space_id, asset_id)
        self.retrieval.delete_asset(str(asset.tenant_id), str(asset.brand_space_id), asset.channel, str(asset.id))
        asset.lifecycle_state = AssetLifecycle.DELETED
        self.storage.delete(asset.storage_path)
        await self.session.commit()
        return asset

    async def reprocess_scoped(self, tenant_id: UUID, brand_space_id: UUID, asset_id: UUID) -> KnowledgeAsset:
        await self.get_scoped(tenant_id, brand_space_id, asset_id)
        return await self.process_asset(asset_id)
