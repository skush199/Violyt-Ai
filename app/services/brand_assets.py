from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import shutil
from typing import Any
from uuid import UUID

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.brand_asset_analysis import AssetProcessingOutcome, BrandAssetAnalyzer
from app.ai.rag.retrieval import KnowledgeRetrievalService
from app.core.enums import AssetLifecycle, AssetValidationState, JobType, UsageMetricCode
from app.core.exceptions import NotFoundError
from app.db.session import AsyncSessionLocal
from app.integrations.object_storage import LocalObjectStorage
from app.models.brand_assets import (
    AssetCategoryRouting,
    AssetProcessingStatus,
    AudienceInsightAsset,
    AudienceInsightStructuredData,
    BrandCTATemplate,
    BrandLegalAsset,
    BrandLogoAsset,
    BrandLogoMetadata,
    ColorPaletteEntry,
    MoodBoardAsset,
    NegativeWord,
    PositiveWord,
    ReplaceableWord,
    ReusableBrandAsset,
    TypographyGuide,
    VisualReferenceAsset,
    WordBankUpload,
)
from app.models.knowledge import KnowledgeAsset, Template, TemplateMetadata
from app.repositories.brand_assets import (
    AssetCategoryRoutingRepository,
    AssetProcessingStatusRepository,
    AudienceInsightAssetRepository,
    AudienceInsightStructuredDataRepository,
    BrandCTATemplateRepository,
    BrandLegalAssetRepository,
    BrandLogoAssetRepository,
    BrandLogoMetadataRepository,
    ColorPaletteEntryRepository,
    MoodBoardAssetRepository,
    NegativeWordRepository,
    PositiveWordRepository,
    ReplaceableWordRepository,
    ReusableBrandAssetRepository,
    TypographyGuideRepository,
    VisualReferenceAssetRepository,
    WordBankUploadRepository,
)
from app.repositories.knowledge import KnowledgeAssetRepository, TemplateMetadataRepository, TemplateRepository
from app.schemas.brand_assets import BrandAttachmentUploadRequest
from app.services.data_validation import DataValidatorService
from app.services.jobs import JobService
from app.services.upload_preflight import UploadPreflightService
from app.utils.image_assets import open_image_asset
from app.services.usage import UsageLimitService


class BrandAssetService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.assets = KnowledgeAssetRepository(session)
        self.storage = LocalObjectStorage()
        self.jobs = JobService(session)
        self.usage = UsageLimitService(session)
        self.retrieval = KnowledgeRetrievalService()
        self.analyzer = BrandAssetAnalyzer()
        self.logo_assets = BrandLogoAssetRepository(session)
        self.logo_metadata = BrandLogoMetadataRepository(session)
        self.audience_assets = AudienceInsightAssetRepository(session)
        self.audience_structured = AudienceInsightStructuredDataRepository(session)
        self.visual_references = VisualReferenceAssetRepository(session)
        self.mood_boards = MoodBoardAssetRepository(session)
        self.reusable_assets = ReusableBrandAssetRepository(session)
        self.palette_entries = ColorPaletteEntryRepository(session)
        self.typography_guides = TypographyGuideRepository(session)
        self.word_bank_uploads = WordBankUploadRepository(session)
        self.positive_words = PositiveWordRepository(session)
        self.negative_words = NegativeWordRepository(session)
        self.replaceable_words = ReplaceableWordRepository(session)
        self.processing_status = AssetProcessingStatusRepository(session)
        self.routing_repo = AssetCategoryRoutingRepository(session)
        self.templates = TemplateRepository(session)
        self.template_metadata = TemplateMetadataRepository(session)
        self.legal_assets = BrandLegalAssetRepository(session)
        self.cta_templates = BrandCTATemplateRepository(session)
        self.validator = DataValidatorService(session)
        self.preflight = UploadPreflightService()

    async def upload(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        field_key: str,
        payload: BrandAttachmentUploadRequest,
    ) -> KnowledgeAsset:
        preflight = self.preflight.validate_base64_upload(
            filename=payload.filename,
            mime_type=payload.mime_type,
            content_base64=payload.content_base64,
        )
        stored = self.storage.save_bytes(tenant_id, brand_space_id, field_key, payload.filename, preflight.content)
        asset = KnowledgeAsset(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            name=payload.name,
            original_filename=payload.filename,
            mime_type=preflight.normalized_mime_type,
            storage_path=stored.storage_path,
            lifecycle_state=AssetLifecycle.INDEXED if payload.skip_processing else AssetLifecycle.UPLOADED,
            channel=self._default_channel(field_key, payload.desired_category),
            field_key=field_key,
            asset_category=payload.desired_category,
            source_intent=field_key,
            page_count=preflight.page_count or 0,
            metadata_json={
                **payload.metadata,
                "desired_category": payload.desired_category,
                "file_size_bytes": preflight.size_bytes,
                "preflight_page_count": preflight.page_count,
                "preflight_hints": preflight.hints or {},
            },
            structured_data_json={},
            normalized_data_json={},
            validation_state=AssetValidationState.PENDING,
            validation_summary_json={"warnings": []},
            is_active=True,
        )
        await self.assets.add(asset)
        await self._upsert_processing_status(
            asset=asset,
            lifecycle_state=asset.lifecycle_state,
            status_message="File uploaded and awaiting processing." if not payload.skip_processing else "File uploaded.",
            progress_total=asset.page_count,
        )
        await self.session.commit()
        if payload.skip_processing:
            return await self.process_asset(asset.id)
        await self.jobs.create(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            job_type=JobType.KNOWLEDGE_PROCESS,
            payload={"knowledge_asset_id": str(asset.id), "field_key": field_key},
            knowledge_asset_id=asset.id,
        )
        return asset

    async def list(self, tenant_id: UUID, brand_space_id: UUID, field_key: str | None = None) -> list[KnowledgeAsset]:
        if field_key:
            assets = await self.assets.list_by_field(brand_space_id, field_key, tenant_id=tenant_id)
        else:
            assets = await self.assets.list_by_brand(brand_space_id, tenant_id)
        return [
            asset
            for asset in assets
            if str(asset.lifecycle_state or "").lower() != AssetLifecycle.DELETED.value and bool(asset.is_active)
        ]

    async def get_scoped(self, tenant_id: UUID, brand_space_id: UUID, asset_id: UUID) -> KnowledgeAsset:
        asset = await self.assets.get_scoped(asset_id, tenant_id, brand_space_id)
        if not asset:
            raise NotFoundError("Brand attachment not found")
        return asset

    async def unsync(self, tenant_id: UUID, brand_space_id: UUID, asset_id: UUID) -> KnowledgeAsset:
        asset = await self.get_scoped(tenant_id, brand_space_id, asset_id)
        await self._cleanup_attachment_side_effects(asset)
        asset.is_active = False
        asset.validation_state = AssetValidationState.EXCLUDED
        asset.validation_summary_json = {
            **(asset.validation_summary_json or {}),
            "warnings": ["Asset was unsynced and excluded from generation."],
        }
        await self._upsert_processing_status(
            asset=asset,
            lifecycle_state=asset.lifecycle_state,
            status_message="Attachment unsynced and removed from validated brand context.",
        )
        await self.session.commit()
        await self.validator.refresh_brand_context(brand_space_id)
        await self.session.refresh(asset)
        return asset

    async def delete(self, tenant_id: UUID, brand_space_id: UUID, asset_id: UUID) -> KnowledgeAsset:
        asset = await self.get_scoped(tenant_id, brand_space_id, asset_id)
        await self._cleanup_attachment_side_effects(asset)
        asset.lifecycle_state = AssetLifecycle.DELETED
        asset.is_active = False
        await self._upsert_processing_status(
            asset=asset,
            lifecycle_state=AssetLifecycle.DELETED,
            status_message="Attachment deleted.",
        )
        await self.session.commit()
        await self.validator.refresh_brand_context(brand_space_id)
        await self.session.refresh(asset)
        return asset

    async def reprocess(self, tenant_id: UUID, brand_space_id: UUID, asset_id: UUID) -> KnowledgeAsset:
        asset = await self.get_scoped(tenant_id, brand_space_id, asset_id)
        asset.lifecycle_state = AssetLifecycle.UPLOADED
        asset.processing_error = None
        await self._upsert_processing_status(
            asset=asset,
            lifecycle_state=AssetLifecycle.UPLOADED,
            status_message="Attachment re-queued for processing.",
        )
        await self.session.commit()
        await self.jobs.create(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            job_type=JobType.KNOWLEDGE_PROCESS,
            payload={"knowledge_asset_id": str(asset.id), "field_key": asset.field_key},
            knowledge_asset_id=asset.id,
        )
        await self.session.refresh(asset)
        return asset

    async def process_asset(self, asset_id: UUID) -> KnowledgeAsset:
        asset = await self.assets.get(asset_id)
        if not asset:
            raise NotFoundError("Brand attachment not found")
        asset.lifecycle_state = AssetLifecycle.PROCESSING
        asset.processing_error = None
        await self._upsert_processing_status(
            asset=asset,
            lifecycle_state=AssetLifecycle.PROCESSING,
            status_message="Extracting and classifying attachment.",
            processor_name="brand_asset_pipeline",
        )
        await self.session.commit()

        try:
            absolute_path = self.storage.absolute_path(asset.storage_path)
            loop = asyncio.get_running_loop()

            def progress_callback(current: int, total: int, message: str) -> None:
                asyncio.run_coroutine_threadsafe(
                    self._persist_processing_progress(asset.id, current, total, message),
                    loop,
                )

            outcome = await asyncio.to_thread(
                self.analyzer.analyze,
                absolute_path=absolute_path,
                filename=asset.original_filename,
                mime_type=asset.mime_type,
                requested_field_key=asset.field_key or asset.channel,
                desired_category=asset.asset_category,
                metadata=asset.metadata_json,
                progress_callback=progress_callback,
            )

            asset.channel = outcome.channel
            asset.asset_category = outcome.routed_category
            asset.classification_confidence = outcome.confidence
            is_typography_guide = outcome.routed_category == "typography_guide"
            asset.page_count = (
                outcome.page_count
                if is_typography_guide
                else max(outcome.page_count, 1 if asset.mime_type.startswith("image/") else 0)
            )
            asset.extracted_text = outcome.extracted_text or None
            asset.extracted_summary = (outcome.extracted_text[:1000] if outcome.extracted_text else None)
            asset.structured_data_json = outcome.structured_data
            asset.normalized_data_json = outcome.normalized_data
            asset.validation_state = outcome.validation_state
            asset.validation_summary_json = {"warnings": outcome.warnings}
            asset.last_indexed_at = datetime.now(timezone.utc).isoformat()

            await self._upsert_routing(asset, outcome)
            await self._clear_reusable_assets(asset.id)
            await self._persist_category_records(asset, outcome)
            await self._index_asset(asset, outcome)
            billable_ocr_pages = 0 if is_typography_guide else max(asset.page_count, 1)
            if billable_ocr_pages:
                await self.usage.enforce(asset.tenant_id, UsageMetricCode.OCR_PAGES, billable_ocr_pages)
                await self.usage.increment(asset.tenant_id, UsageMetricCode.OCR_PAGES, billable_ocr_pages)

            await self._upsert_processing_status(
                asset=asset,
                lifecycle_state=AssetLifecycle.PROCESSING,
                status_message="Refreshing validated brand context.",
                progress_current=max(asset.page_count, 1),
                progress_total=max(asset.page_count, 1),
                raw_status_json={
                    "ocr_complete": not is_typography_guide,
                    "font_detection_complete": is_typography_guide,
                    "vision_analysis_complete": not any(
                        "visual analysis" in warning.lower()
                        for warning in outcome.warnings
                    ),
                },
            )
            await self.session.commit()
            await self.validator.refresh_brand_context(asset.brand_space_id)

            asset.lifecycle_state = AssetLifecycle.INDEXED
            await self._upsert_processing_status(
                asset=asset,
                lifecycle_state=AssetLifecycle.INDEXED,
                status_message="Attachment processed and synced.",
                progress_current=max(asset.page_count, 1),
                progress_total=max(asset.page_count, 1),
                raw_status_json={
                    "ocr_complete": not is_typography_guide,
                    "font_detection_complete": is_typography_guide,
                    "vision_analysis_complete": not any(
                        "visual analysis" in warning.lower()
                        for warning in outcome.warnings
                    ),
                },
            )
            await self.session.commit()
            await self.session.refresh(asset)
            return asset
        except Exception as exc:  # noqa: BLE001
            asset.lifecycle_state = AssetLifecycle.FAILED
            asset.processing_error = str(exc)
            asset.validation_state = AssetValidationState.WARNING
            asset.validation_summary_json = {"warnings": [str(exc)]}
            await self._upsert_processing_status(
                asset=asset,
                lifecycle_state=AssetLifecycle.FAILED,
                status_message="Attachment processing failed.",
                raw_status_json={"error": str(exc)},
            )
            await self.session.commit()
            raise

    async def _index_asset(self, asset: KnowledgeAsset, outcome: AssetProcessingOutcome) -> None:
        self.retrieval.delete_asset(str(asset.tenant_id), str(asset.brand_space_id), asset.channel, str(asset.id))
        quality_metadata = self._analysis_quality_metadata(
            outcome.structured_data,
            outcome.normalized_data,
            outcome.template_analysis,
        )
        base_metadata = {
            "asset_id": str(asset.id),
            "filename": asset.original_filename,
            "field_key": asset.field_key,
            "asset_category": asset.asset_category,
            "validation_state": outcome.validation_state,
            "classification_confidence": float(outcome.confidence or 0.0),
            "source_format": outcome.source_format,
            "template_tags": list(outcome.template_tags or []),
            **quality_metadata,
        }
        if outcome.extracted_text:
            self.retrieval.index_asset(
                tenant_id=str(asset.tenant_id),
                brand_space_id=str(asset.brand_space_id),
                channel=asset.channel,
                source_id=str(asset.id),
                text=outcome.extracted_text,
                metadata=base_metadata,
            )
        structured_documents = self._structured_retrieval_documents(asset, outcome)
        if structured_documents:
            self.retrieval.index_documents(
                tenant_id=str(asset.tenant_id),
                brand_space_id=str(asset.brand_space_id),
                channel=asset.channel,
                source_id=str(asset.id),
                documents=structured_documents,
            )

    @staticmethod
    def _normalize_retrieval_text(value: Any, limit: int | None = None) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            text = " ".join(value.strip().split())
        elif isinstance(value, dict):
            text = " ".join(
                str(value.get(key, "")).strip()
                for key in ("label", "name", "role", "summary", "text", "value", "hex_code", "color_name", "dominant_mode")
                if value.get(key)
            ).strip()
        elif isinstance(value, (list, tuple, set)):
            text = "; ".join(
                item
                for item in (
                    BrandAssetService._normalize_retrieval_text(entry, limit=limit)
                    for entry in value
                )
                if item
            )
        else:
            text = str(value).strip()
        if not limit or len(text) <= limit:
            return text
        return text[:limit].rstrip(" ,.;:")

    @classmethod
    def _retrieval_list(cls, value: Any, *, limit: int, item_limit: int = 96) -> list[str]:
        if not isinstance(value, list):
            return []
        items: list[str] = []
        seen: set[str] = set()
        for entry in value:
            text = cls._normalize_retrieval_text(entry, limit=item_limit)
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            items.append(text)
            if len(items) >= limit:
                break
        return items

    @classmethod
    def _palette_terms(cls, palette_entries: Any, *, limit: int = 4) -> list[str]:
        if not isinstance(palette_entries, list):
            return []
        items: list[str] = []
        seen: set[str] = set()
        for entry in palette_entries:
            if not isinstance(entry, dict):
                continue
            role = cls._normalize_retrieval_text(entry.get("role"), limit=20)
            hex_code = cls._normalize_retrieval_text(entry.get("hex_code") or entry.get("hex"), limit=16)
            color_name = cls._normalize_retrieval_text(entry.get("color_name") or entry.get("name"), limit=24)
            label = " ".join(part for part in [role, hex_code or color_name] if part).strip()
            if not label:
                continue
            key = label.casefold()
            if key in seen:
                continue
            seen.add(key)
            items.append(label)
            if len(items) >= limit:
                break
        return items

    @staticmethod
    def _analysis_quality_metadata(*payloads: Any) -> dict[str, Any]:
        merged: dict[str, Any] = {
            "analysis_quality_score": 0.0,
            "summary_quality_score": 0.0,
            "ocr_signal_score": 0.0,
            "source_agreement_score": 0.0,
            "ocr_noise_ratio": None,
            "promotional_line_ratio": None,
            "selected_line_count": 0,
            "candidate_line_count": 0,
            "visual_grounding_line_count": 0,
            "template_copy_line_count": 0,
            "evidence_types": [],
            "source_agreement_types": [],
            "observed_signal_types": [],
            "available_signal_types": [],
            "line_classification_counts": {},
        }
        evidence_types: list[str] = []
        source_agreement_types: list[str] = []
        observed_signal_types: list[str] = []
        available_signal_types: list[str] = []
        line_classification_counts: dict[str, int] = {}
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            quality = payload.get("analysis_quality")
            if not isinstance(quality, dict):
                continue
            for key in ("analysis_quality_score", "summary_quality_score", "ocr_signal_score", "source_agreement_score"):
                try:
                    merged[key] = max(float(merged.get(key) or 0.0), float(quality.get(key) or 0.0))
                except (TypeError, ValueError):
                    continue
            for key in ("selected_line_count", "candidate_line_count", "visual_grounding_line_count", "template_copy_line_count"):
                try:
                    merged[key] = max(int(merged.get(key) or 0), int(quality.get(key) or 0))
                except (TypeError, ValueError):
                    continue
            for key in ("ocr_noise_ratio", "promotional_line_ratio"):
                try:
                    value = float(quality.get(key))
                except (TypeError, ValueError):
                    continue
                current = merged.get(key)
                merged[key] = value if current is None else min(float(current), value)
            for entry in quality.get("evidence_types") or []:
                text = str(entry or "").strip()
                if text and text not in evidence_types:
                    evidence_types.append(text)
            for key, target in (
                ("source_agreement_types", source_agreement_types),
                ("observed_signal_types", observed_signal_types),
                ("available_signal_types", available_signal_types),
            ):
                for entry in quality.get(key) or []:
                    text = str(entry or "").strip()
                    if text and text not in target:
                        target.append(text)
            line_counts = quality.get("line_classification_counts")
            if isinstance(line_counts, dict):
                for key, value in line_counts.items():
                    try:
                        line_classification_counts[str(key)] = max(
                            int(line_classification_counts.get(str(key), 0) or 0),
                            int(value or 0),
                        )
                    except (TypeError, ValueError):
                        continue
        merged["evidence_types"] = evidence_types
        merged["source_agreement_types"] = source_agreement_types
        merged["observed_signal_types"] = observed_signal_types
        merged["available_signal_types"] = available_signal_types
        merged["line_classification_counts"] = line_classification_counts
        if merged["ocr_noise_ratio"] is None:
            merged["ocr_noise_ratio"] = 0.0
        if merged["promotional_line_ratio"] is None:
            merged["promotional_line_ratio"] = 0.0
        return merged

    @classmethod
    def _structured_retrieval_documents(
        cls,
        asset: KnowledgeAsset,
        outcome: AssetProcessingOutcome,
    ) -> list[dict[str, Any]]:
        category = str(outcome.routed_category or asset.asset_category or "")
        structured = outcome.structured_data if isinstance(outcome.structured_data, dict) else {}
        normalized = outcome.normalized_data if isinstance(outcome.normalized_data, dict) else {}
        template_analysis = outcome.template_analysis if isinstance(outcome.template_analysis, dict) else {}
        signal_count = 0
        documents: list[dict[str, Any]] = []
        quality_metadata = cls._analysis_quality_metadata(structured, normalized, template_analysis)
        base_metadata = {
            "asset_id": str(asset.id),
            "filename": asset.original_filename,
            "field_key": asset.field_key,
            "asset_category": asset.asset_category,
            "validation_state": outcome.validation_state,
            "classification_confidence": float(outcome.confidence or 0.0),
            "source_format": outcome.source_format,
            "template_tags": list(outcome.template_tags or []),
            **quality_metadata,
        }

        palette_terms = cls._palette_terms(
            normalized.get("palette")
            or structured.get("palette_entries")
            or structured.get("color_usage")
            or template_analysis.get("color_usage"),
            limit=5,
        )
        font_terms = cls._retrieval_list(
            normalized.get("font_families")
            or structured.get("fonts")
            or structured.get("font_families")
            or template_analysis.get("font_families"),
            limit=4,
        )
        reusable_zone_terms = cls._retrieval_list(
            normalized.get("reusable_zones")
            or structured.get("reusable_zones")
            or template_analysis.get("editable_zones"),
            limit=6,
            item_limit=48,
        )
        asset_label_terms = cls._retrieval_list(
            structured.get("asset_labels")
            or normalized.get("asset_labels")
            or structured.get("icon_assets")
            or structured.get("micro_design_elements")
            or structured.get("decorative_assets"),
            limit=8,
        )
        tag_terms = cls._retrieval_list(template_analysis.get("tags"), limit=6, item_limit=40)
        platform_terms = cls._retrieval_list(template_analysis.get("platform_hints"), limit=4, item_limit=32)
        template_copy_terms = cls._retrieval_list(
            template_analysis.get("copy_lines")
            or structured.get("copy_lines")
            or normalized.get("copy_lines"),
            limit=4,
            item_limit=96,
        )
        visual_evidence_units: list[dict[str, str]] = []
        seen_visual_units: set[tuple[str, str]] = set()
        for payload in (
            structured.get("visual_evidence_units"),
            normalized.get("visual_evidence_units"),
            template_analysis.get("visual_evidence_units"),
        ):
            if not isinstance(payload, list):
                continue
            for item in payload:
                if not isinstance(item, dict):
                    continue
                kind = cls._normalize_retrieval_text(item.get("kind"), limit=32)
                summary = cls._normalize_retrieval_text(item.get("summary"), limit=180)
                source = cls._normalize_retrieval_text(item.get("source"), limit=24)
                if not kind or not summary:
                    continue
                key = (kind.casefold(), summary.casefold())
                if key in seen_visual_units:
                    continue
                seen_visual_units.add(key)
                visual_evidence_units.append(
                    {
                        "kind": kind,
                        "summary": summary,
                        "source": source or "derived",
                    }
                )
                if len(visual_evidence_units) >= 6:
                    break
            if len(visual_evidence_units) >= 6:
                break
        summary_candidates = [
            cls._normalize_retrieval_text(structured.get("knowledge_summary"), limit=220),
            cls._normalize_retrieval_text(structured.get("structure_summary"), limit=220),
            cls._normalize_retrieval_text(structured.get("style_summary"), limit=220),
            cls._normalize_retrieval_text(structured.get("summary"), limit=220),
            cls._normalize_retrieval_text(normalized.get("structure_summary"), limit=220),
            cls._normalize_retrieval_text(normalized.get("summary"), limit=220),
            cls._normalize_retrieval_text(normalized.get("style_summary"), limit=220),
            cls._normalize_retrieval_text(template_analysis.get("structure_summary"), limit=220),
            cls._normalize_retrieval_text(template_analysis.get("summary"), limit=220),
            cls._normalize_retrieval_text(template_analysis.get("style_summary"), limit=220),
        ]
        template_brand_score = float(template_analysis.get("brand_score") or normalized.get("brand_score") or 0.0)
        overview_parts = [
            part
            for part in [
                f"Category {category}" if category else "",
                f"Layout {cls._normalize_retrieval_text(template_analysis.get('layout_type') or normalized.get('layout_type'), limit=48)}"
                if template_analysis.get("layout_type") or normalized.get("layout_type")
                else "",
                f"Background style {cls._normalize_retrieval_text((template_analysis.get('background_style') or {}).get('dominant_mode'), limit=40)}"
                if isinstance(template_analysis.get("background_style"), dict)
                else "",
                next((candidate for candidate in summary_candidates if candidate), ""),
                f"Palette cues: {', '.join(palette_terms)}" if palette_terms else "",
                f"Typography cues: {', '.join(font_terms)}" if font_terms else "",
                f"Reusable zones: {', '.join(reusable_zone_terms)}" if reusable_zone_terms else "",
                f"Platform hints: {', '.join(platform_terms)}" if platform_terms else "",
                f"Style tags: {', '.join(tag_terms)}" if tag_terms else "",
            ]
            if part
        ]
        if overview_parts:
            signal_count += sum(
                1
                for part in [
                    palette_terms,
                    font_terms,
                    reusable_zone_terms,
                    asset_label_terms,
                    tag_terms,
                    platform_terms,
                    visual_evidence_units,
                    [candidate for candidate in summary_candidates if candidate],
                ]
                if part
            )
            documents.append(
                {
                    "content": ". ".join(overview_parts),
                    "metadata": {
                        **base_metadata,
                        "document_type": "structured_summary",
                        "structured_signal_score": signal_count,
                        "template_brand_score": template_brand_score,
                        "visual_grounding_allowed": True,
                    },
                }
            )
        for unit in visual_evidence_units:
            documents.append(
                {
                    "content": f"{unit['kind'].replace('_', ' ').title()} evidence: {unit['summary']}.",
                    "metadata": {
                        **base_metadata,
                        "document_type": "structured_visual_unit",
                        "structured_signal_score": max(signal_count, 1),
                        "template_brand_score": template_brand_score,
                        "visual_grounding_allowed": True,
                        "evidence_kind": unit["kind"],
                        "evidence_source": unit["source"],
                    },
                }
            )
        if palette_terms:
            documents.append(
                {
                    "content": f"Palette system: {', '.join(palette_terms)}.",
                    "metadata": {
                        **base_metadata,
                        "document_type": "structured_palette",
                        "structured_signal_score": max(signal_count, len(palette_terms)),
                        "template_brand_score": template_brand_score,
                        "visual_grounding_allowed": True,
                    },
                }
            )
        if font_terms:
            documents.append(
                {
                    "content": f"Typography system: {', '.join(font_terms)}.",
                    "metadata": {
                        **base_metadata,
                        "document_type": "structured_typography",
                        "structured_signal_score": max(signal_count, len(font_terms)),
                        "template_brand_score": template_brand_score,
                        "visual_grounding_allowed": True,
                    },
                }
            )
        if reusable_zone_terms or template_analysis.get("layout_type") or normalized.get("layout_type"):
            layout_label = cls._normalize_retrieval_text(
                template_analysis.get("layout_type") or normalized.get("layout_type"),
                limit=48,
            )
            layout_parts = [
                f"Layout system: {layout_label}" if layout_label else "",
                f"Zones: {', '.join(reusable_zone_terms)}" if reusable_zone_terms else "",
            ]
            content = ". ".join(part for part in layout_parts if part)
            if content:
                documents.append(
                    {
                        "content": content,
                        "metadata": {
                            **base_metadata,
                            "document_type": "structured_layout",
                            "structured_signal_score": max(signal_count, len(reusable_zone_terms)),
                            "template_brand_score": template_brand_score,
                            "visual_grounding_allowed": True,
                        },
                    }
                )
        if asset_label_terms:
            documents.append(
                {
                    "content": f"Reusable visual labels: {', '.join(asset_label_terms)}.",
                    "metadata": {
                        **base_metadata,
                        "document_type": "structured_labels",
                        "structured_signal_score": max(signal_count, len(asset_label_terms)),
                        "template_brand_score": template_brand_score,
                        "visual_grounding_allowed": True,
                    },
                }
            )
        if template_copy_terms:
            documents.append(
                {
                    "content": f"Template copy cues: {', '.join(template_copy_terms)}.",
                    "metadata": {
                        **base_metadata,
                        "document_type": "structured_template_copy",
                        "structured_signal_score": len(template_copy_terms),
                        "template_brand_score": template_brand_score,
                        "visual_grounding_allowed": False,
                    },
                }
            )
        return documents

    async def _persist_category_records(self, asset: KnowledgeAsset, outcome: AssetProcessingOutcome) -> None:
        if outcome.routed_category == "logo":
            await self._persist_logo(asset, outcome)
            await self._persist_reusable_assets(asset, outcome)
            return
        if outcome.routed_category == "audience_insight":
            await self._persist_audience(asset, outcome)
            return
        if outcome.routed_category in {"reference_creative", "template"}:
            await self._persist_template_intelligence(asset, outcome)
            if outcome.routed_category == "reference_creative":
                await self._persist_visual_reference(asset, outcome)
                await self._persist_palette(asset, outcome)
                await self._persist_typography(asset, outcome)
            await self._persist_reusable_assets(asset, outcome)
            await self._persist_legal_disclaimers(asset, outcome)
            await self._persist_cta_templates(asset, outcome)
            return
        if outcome.routed_category == "mood_board":
            await self._persist_mood_board(asset, outcome)
            await self._persist_reusable_assets(asset, outcome)
            return
        if outcome.routed_category == "color_palette":
            await self._persist_palette(asset, outcome)
            return
        if outcome.routed_category == "typography_guide":
            await self._persist_typography(asset, outcome)
            return
        if outcome.routed_category in {"positive_word_bank", "negative_word_bank", "replaceable_word_bank"}:
            await self._persist_word_bank(asset, outcome)
            return
        if outcome.routed_category == "knowledge_other":
            await self._persist_reusable_assets(asset, outcome)

    async def _persist_logo(self, asset: KnowledgeAsset, outcome: AssetProcessingOutcome) -> None:
        logo_asset = await self.logo_assets.get_by_knowledge_asset(asset.id)
        if not logo_asset:
            logo_asset = BrandLogoAsset(
                tenant_id=asset.tenant_id,
                brand_space_id=asset.brand_space_id,
                knowledge_asset_id=asset.id,
                variant_label=asset.metadata_json.get("variant_label"),
                compatibility=outcome.normalized_data.get("usage_metadata", {}).get("compatible_backgrounds", []),
                usage_metadata=outcome.normalized_data.get("usage_metadata", {}),
                source_metadata_json=asset.metadata_json,
            )
            self.session.add(logo_asset)
            await self.session.flush()
        else:
            logo_asset.variant_label = asset.metadata_json.get("variant_label")
            logo_asset.compatibility = outcome.normalized_data.get("usage_metadata", {}).get("compatible_backgrounds", [])
            logo_asset.usage_metadata = outcome.normalized_data.get("usage_metadata", {})
            logo_asset.source_metadata_json = asset.metadata_json
        metadata = await self.logo_metadata.get_by_logo_asset(logo_asset.id)
        if not metadata:
            metadata = BrandLogoMetadata(
                tenant_id=asset.tenant_id,
                brand_space_id=asset.brand_space_id,
                brand_logo_asset_id=logo_asset.id,
                logo_colors=outcome.structured_data.get("logo_colors", []),
                size_rules=outcome.structured_data.get("size_rules", {}),
                font_details=outcome.structured_data.get("font_details", {}),
                tagline=outcome.structured_data.get("tagline"),
                extracted_text=asset.extracted_text,
                inference_metadata={"source_format": outcome.source_format},
            )
            self.session.add(metadata)
        else:
            metadata.logo_colors = outcome.structured_data.get("logo_colors", [])
            metadata.size_rules = outcome.structured_data.get("size_rules", {})
            metadata.font_details = outcome.structured_data.get("font_details", {})
            metadata.tagline = outcome.structured_data.get("tagline")
            metadata.extracted_text = asset.extracted_text
            metadata.inference_metadata = {"source_format": outcome.source_format}

    async def _persist_audience(self, asset: KnowledgeAsset, outcome: AssetProcessingOutcome) -> None:
        analysis_metadata = {
            "source_format": outcome.source_format,
            "audience_evidence": outcome.structured_data.get("research_evidence", {}),
            "research_signal_count": outcome.structured_data.get("research_signal_count", 0),
            "analysis_quality": outcome.structured_data.get("analysis_quality", {}),
        }
        source_metadata = {
            **(asset.metadata_json or {}),
            "analysis_metadata": analysis_metadata,
        }
        audience_asset = await self.audience_assets.get_by_knowledge_asset(asset.id)
        if not audience_asset:
            audience_asset = AudienceInsightAsset(
                tenant_id=asset.tenant_id,
                brand_space_id=asset.brand_space_id,
                knowledge_asset_id=asset.id,
                summary=outcome.normalized_data.get("research_summary"),
                confidence=outcome.confidence,
                source_metadata_json=source_metadata,
            )
            self.session.add(audience_asset)
            await self.session.flush()
        else:
            audience_asset.summary = outcome.normalized_data.get("research_summary")
            audience_asset.confidence = outcome.confidence
            audience_asset.source_metadata_json = source_metadata
        structured = await self.audience_structured.get_by_audience_asset(audience_asset.id)
        analysis_quality = outcome.structured_data.get("analysis_quality", {})
        source_agreement_score = None
        try:
            source_agreement_score = float(analysis_quality.get("source_agreement_score"))
        except (TypeError, ValueError, AttributeError):
            source_agreement_score = None
        if not structured:
            structured = AudienceInsightStructuredData(
                tenant_id=asset.tenant_id,
                brand_space_id=asset.brand_space_id,
                audience_insight_asset_id=audience_asset.id,
                audience_segments=outcome.structured_data.get("audience_segments", []),
                behaviors=outcome.structured_data.get("behaviors", []),
                motivations=outcome.structured_data.get("motivations", []),
                pain_points=outcome.structured_data.get("pain_points", []),
                objections=outcome.structured_data.get("objections", []),
                desired_outcomes=outcome.structured_data.get("desired_outcomes", []),
                preferences=outcome.structured_data.get("preferences", []),
                trust_signals=outcome.structured_data.get("trust_signals", []),
                proof_cues=outcome.structured_data.get("proof_cues", []),
                comparison_points=outcome.structured_data.get("comparison_points", []),
                demographics=outcome.structured_data.get("demographics", {}),
                psychographics=outcome.structured_data.get("psychographics", {}),
                research_summary=outcome.structured_data.get("research_summary"),
                research_evidence=outcome.structured_data.get("research_evidence", {}),
                research_signal_count=int(outcome.structured_data.get("research_signal_count") or 0),
                analysis_quality=analysis_quality if isinstance(analysis_quality, dict) else {},
                evidence_confidence=outcome.confidence,
                source_agreement_score=source_agreement_score,
            )
            self.session.add(structured)
        else:
            structured.audience_segments = outcome.structured_data.get("audience_segments", [])
            structured.behaviors = outcome.structured_data.get("behaviors", [])
            structured.motivations = outcome.structured_data.get("motivations", [])
            structured.pain_points = outcome.structured_data.get("pain_points", [])
            structured.objections = outcome.structured_data.get("objections", [])
            structured.desired_outcomes = outcome.structured_data.get("desired_outcomes", [])
            structured.preferences = outcome.structured_data.get("preferences", [])
            structured.trust_signals = outcome.structured_data.get("trust_signals", [])
            structured.proof_cues = outcome.structured_data.get("proof_cues", [])
            structured.comparison_points = outcome.structured_data.get("comparison_points", [])
            structured.demographics = outcome.structured_data.get("demographics", {})
            structured.psychographics = outcome.structured_data.get("psychographics", {})
            structured.research_summary = outcome.structured_data.get("research_summary")
            structured.research_evidence = outcome.structured_data.get("research_evidence", {})
            structured.research_signal_count = int(outcome.structured_data.get("research_signal_count") or 0)
            structured.analysis_quality = analysis_quality if isinstance(analysis_quality, dict) else {}
            structured.evidence_confidence = outcome.confidence
            structured.source_agreement_score = source_agreement_score

    async def _persist_visual_reference(self, asset: KnowledgeAsset, outcome: AssetProcessingOutcome) -> None:
        template = await self.templates.get_by_source_asset(asset.id)
        reference = await self.visual_references.get_by_knowledge_asset(asset.id)
        if not reference:
            reference = VisualReferenceAsset(
                tenant_id=asset.tenant_id,
                brand_space_id=asset.brand_space_id,
                knowledge_asset_id=asset.id,
                template_id=template.id if template else None,
                layout_structure=outcome.structured_data.get("layout_structure", {}),
                style_characteristics=outcome.structured_data.get("style_characteristics", {}),
                reusable_zones=outcome.structured_data.get("reusable_zones", []),
                brand_score=outcome.structured_data.get("brand_score"),
            )
            self.session.add(reference)
        else:
            reference.template_id = template.id if template else None
            reference.layout_structure = outcome.structured_data.get("layout_structure", {})
            reference.style_characteristics = outcome.structured_data.get("style_characteristics", {})
            reference.reusable_zones = outcome.structured_data.get("reusable_zones", [])
            reference.brand_score = outcome.structured_data.get("brand_score")

    async def _persist_mood_board(self, asset: KnowledgeAsset, outcome: AssetProcessingOutcome) -> None:
        board = await self.mood_boards.get_by_knowledge_asset(asset.id)
        if not board:
            board = MoodBoardAsset(
                tenant_id=asset.tenant_id,
                brand_space_id=asset.brand_space_id,
                knowledge_asset_id=asset.id,
                style_summary=outcome.structured_data.get("style_summary"),
                icon_assets=outcome.structured_data.get("icon_assets", []),
                micro_design_elements=outcome.structured_data.get("micro_design_elements", []),
                decorative_assets=outcome.structured_data.get("decorative_assets", []),
                enhancement_components=outcome.structured_data.get("enhancement_components", []),
            )
            self.session.add(board)
        else:
            board.style_summary = outcome.structured_data.get("style_summary")
            board.icon_assets = outcome.structured_data.get("icon_assets", [])
            board.micro_design_elements = outcome.structured_data.get("micro_design_elements", [])
            board.decorative_assets = outcome.structured_data.get("decorative_assets", [])
            board.enhancement_components = outcome.structured_data.get("enhancement_components", [])

    async def _persist_reusable_assets(self, asset: KnowledgeAsset, outcome: AssetProcessingOutcome) -> None:
        await self._clear_reusable_assets(asset.id)
        for candidate in outcome.derived_assets:
            asset_kind = str(candidate.get("asset_kind") or "reference_fragment")
            normalized_metadata = candidate.get("normalized_metadata", {})
            review_status = str((normalized_metadata or {}).get("review_status") or "reference_only")
            if review_status == "excluded":
                continue
            stored_payload = self._store_reusable_asset_payload(asset, candidate)
            if not stored_payload:
                continue
            self.session.add(
                ReusableBrandAsset(
                    tenant_id=asset.tenant_id,
                    brand_space_id=asset.brand_space_id,
                    knowledge_asset_id=asset.id,
                    asset_kind=asset_kind,
                    label=str(candidate.get("label") or asset.name)[:200],
                    mime_type=stored_payload["mime_type"],
                    storage_path=stored_payload["storage_path"],
                    width=stored_payload["width"],
                    height=stored_payload["height"],
                    confidence=candidate.get("confidence"),
                    is_active=asset.is_active,
                    source_metadata_json=candidate.get("source_metadata", {}),
                    normalized_metadata_json={
                        **normalized_metadata,
                        "crop_box": candidate.get("crop_box"),
                    },
                )
            )

    async def _clear_reusable_assets(self, knowledge_asset_id: UUID) -> None:
        for reusable_asset in await self.reusable_assets.list_by_knowledge_asset(knowledge_asset_id):
            self.storage.delete(reusable_asset.storage_path)
        await self.reusable_assets.delete_by_knowledge_asset(knowledge_asset_id)

    async def _cleanup_attachment_side_effects(self, asset: KnowledgeAsset) -> None:
        self.retrieval.delete_asset(str(asset.tenant_id), str(asset.brand_space_id), asset.channel, str(asset.id))
        await self._clear_reusable_assets(asset.id)
        await self.palette_entries.delete_by_asset(asset.id)
        await self._delete_linked_records(asset.id)
        self._delete_attachment_storage_artifacts(asset.storage_path)
        await self.session.flush()

    async def _delete_linked_records(self, knowledge_asset_id: UUID) -> None:
        logo_asset = await self.logo_assets.get_by_knowledge_asset(knowledge_asset_id)
        if logo_asset:
            await self.session.delete(logo_asset)

        audience_asset = await self.audience_assets.get_by_knowledge_asset(knowledge_asset_id)
        if audience_asset:
            await self.session.delete(audience_asset)

        visual_reference = await self.visual_references.get_by_knowledge_asset(knowledge_asset_id)
        if visual_reference:
            await self.session.delete(visual_reference)

        mood_board = await self.mood_boards.get_by_knowledge_asset(knowledge_asset_id)
        if mood_board:
            await self.session.delete(mood_board)

        typography_guide = await self.typography_guides.get_by_knowledge_asset(knowledge_asset_id)
        if typography_guide:
            await self.session.delete(typography_guide)

        word_bank_upload = await self.word_bank_uploads.get_by_knowledge_asset(knowledge_asset_id)
        if word_bank_upload:
            await self.positive_words.delete_by_upload(word_bank_upload.id)
            await self.negative_words.delete_by_upload(word_bank_upload.id)
            await self.replaceable_words.delete_by_upload(word_bank_upload.id)
            await self.session.delete(word_bank_upload)

        template = await self.templates.get_by_source_asset(knowledge_asset_id)
        if template:
            await self.session.delete(template)

    def _delete_attachment_storage_artifacts(self, storage_path: str | None) -> None:
        normalized_path = str(storage_path or "").strip()
        if not normalized_path:
            return
        try:
            absolute_path = Path(self.storage.absolute_path(normalized_path))
        except ValueError:
            return

        scratch_root = absolute_path.parent / "_ocr"
        page_images_root = scratch_root / "page_images"
        targets = [
            absolute_path,
            absolute_path.with_name(f"{absolute_path.stem}_analysis.json"),
            scratch_root / absolute_path.name,
            scratch_root / f"{absolute_path.stem}_analysis.json",
            scratch_root / f"{absolute_path.stem}_ocr.txt",
            scratch_root / absolute_path.stem,
        ]

        for target in targets:
            self._remove_storage_target(target)

        remaining_source_files = [
            child
            for child in absolute_path.parent.iterdir()
            if child.name != "_ocr"
        ] if absolute_path.parent.exists() else []
        if not remaining_source_files:
            self._remove_storage_target(page_images_root)
            self._remove_storage_target(scratch_root)

        self._prune_empty_storage_dirs(
            [
                page_images_root,
                scratch_root,
                absolute_path.parent,
                absolute_path.parent.parent,
            ]
        )

    @staticmethod
    def _remove_storage_target(target: Path) -> None:
        try:
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.exists():
                target.unlink(missing_ok=True)
        except OSError:
            return

    def _prune_empty_storage_dirs(self, directories: list[Path]) -> None:
        base_path = self.storage.base_path
        for directory in directories:
            current = directory
            while current.exists() and current != base_path:
                try:
                    current.rmdir()
                except OSError:
                    break
                current = current.parent

    def _store_reusable_asset_payload(self, asset: KnowledgeAsset, candidate: dict) -> dict | None:
        source_path = str(candidate.get("source_path") or "").strip()
        if not source_path:
            return None
        try:
            with open_image_asset(source_path) as source:
                crop_box = candidate.get("crop_box")
                image = source.convert("RGBA")
                if crop_box:
                    left, top, right, bottom = [int(value) for value in crop_box]
                    image = image.crop((left, top, right, bottom))
                width, height = image.size
                if width < 16 or height < 16:
                    return None
                buffer = BytesIO()
                image.save(buffer, format="PNG")
        except Exception:  # noqa: BLE001
            return None

        safe_label = str(candidate.get("label") or asset.name or "asset").replace("/", " ").replace("\\", " ")
        stored = self.storage.save_bytes(
            asset.tenant_id,
            asset.brand_space_id,
            f"derived-assets/{asset.id}",
            f"{safe_label}.png",
            buffer.getvalue(),
        )
        return {
            "storage_path": stored.storage_path,
            "mime_type": "image/png",
            "width": width,
            "height": height,
        }

    async def _persist_palette(self, asset: KnowledgeAsset, outcome: AssetProcessingOutcome) -> None:
        await self.palette_entries.delete_by_asset(asset.id)
        entries = outcome.structured_data.get("palette_entries", [])
        if not isinstance(entries, list) or not entries:
            entries = outcome.normalized_data.get("all", [])
        if (not isinstance(entries, list) or not entries) and isinstance(outcome.template_analysis, dict):
            entries = outcome.template_analysis.get("color_usage", [])
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            hex_code = entry.get("hex_code")
            if not hex_code:
                continue
            self.session.add(
                ColorPaletteEntry(
                    tenant_id=asset.tenant_id,
                    brand_space_id=asset.brand_space_id,
                    knowledge_asset_id=asset.id,
                    role=entry.get("role", "primary"),
                    color_name=entry.get("color_name"),
                    hex_code=hex_code,
                    rgb_value=entry.get("rgb_value", {}),
                    confidence=outcome.confidence,
                    source_metadata_json={"source": entry.get("source")},
                )
            )

    async def _persist_typography(self, asset: KnowledgeAsset, outcome: AssetProcessingOutcome) -> None:
        font_families = outcome.structured_data.get("font_families", [])
        if (not isinstance(font_families, list) or not font_families) and isinstance(outcome.template_analysis, dict):
            font_families = outcome.template_analysis.get("font_families", [])

        style_hierarchy = outcome.structured_data.get("style_hierarchy", {})
        if (not isinstance(style_hierarchy, dict) or not style_hierarchy) and isinstance(outcome.template_analysis, dict):
            style_hierarchy = outcome.template_analysis.get("typography_dna", {})

        usage_patterns = outcome.structured_data.get("usage_patterns", {})
        if (not isinstance(usage_patterns, dict) or not usage_patterns) and isinstance(outcome.template_analysis, dict):
            usage_patterns = {
                "heading": outcome.template_analysis.get("heading"),
                "header": outcome.template_analysis.get("header"),
                "footer": outcome.template_analysis.get("footer"),
                "text_style_map": outcome.template_analysis.get("text_style_map", []),
                "font_size_hints": outcome.template_analysis.get("font_size_hints", []),
                "font_colors": outcome.template_analysis.get("font_colors", []),
            }

        if not font_families and not style_hierarchy and not usage_patterns:
            return

        guide = await self.typography_guides.get_by_knowledge_asset(asset.id)
        if not guide:
            guide = TypographyGuide(
                tenant_id=asset.tenant_id,
                brand_space_id=asset.brand_space_id,
                knowledge_asset_id=asset.id,
                font_families=font_families if isinstance(font_families, list) else [],
                style_hierarchy=style_hierarchy if isinstance(style_hierarchy, dict) else {},
                usage_patterns=usage_patterns if isinstance(usage_patterns, dict) else {},
                confidence=outcome.confidence,
            )
            self.session.add(guide)
        else:
            guide.font_families = font_families if isinstance(font_families, list) else []
            guide.style_hierarchy = style_hierarchy if isinstance(style_hierarchy, dict) else {}
            guide.usage_patterns = usage_patterns if isinstance(usage_patterns, dict) else {}
            guide.confidence = outcome.confidence

    async def _persist_word_bank(self, asset: KnowledgeAsset, outcome: AssetProcessingOutcome) -> None:
        upload = await self.word_bank_uploads.get_by_knowledge_asset(asset.id)
        if not upload:
            upload = WordBankUpload(
                tenant_id=asset.tenant_id,
                brand_space_id=asset.brand_space_id,
                knowledge_asset_id=asset.id,
                bank_type=outcome.routed_category,
                normalized_terms=outcome.structured_data.get("normalized_terms", []),
                phrase_map=outcome.structured_data.get("phrase_map", {}),
            )
            self.session.add(upload)
            await self.session.flush()
        else:
            upload.bank_type = outcome.routed_category
            upload.normalized_terms = outcome.structured_data.get("normalized_terms", [])
            upload.phrase_map = outcome.structured_data.get("phrase_map", {})

        await self.positive_words.delete_by_upload(upload.id)
        await self.negative_words.delete_by_upload(upload.id)
        await self.replaceable_words.delete_by_upload(upload.id)

        if outcome.routed_category == "positive_word_bank":
            for term in upload.normalized_terms:
                self.session.add(
                    PositiveWord(
                        tenant_id=asset.tenant_id,
                        brand_space_id=asset.brand_space_id,
                        upload_id=upload.id,
                        term=term,
                    )
                )
        elif outcome.routed_category == "negative_word_bank":
            for term in upload.normalized_terms:
                self.session.add(
                    NegativeWord(
                        tenant_id=asset.tenant_id,
                        brand_space_id=asset.brand_space_id,
                        upload_id=upload.id,
                        term=term,
                    )
                )
        else:
            for term in upload.normalized_terms:
                self.session.add(
                    ReplaceableWord(
                        tenant_id=asset.tenant_id,
                        brand_space_id=asset.brand_space_id,
                        upload_id=upload.id,
                        term=term,
                        replacements=upload.phrase_map.get(term, []),
                    )
                )

    async def _persist_template_intelligence(self, asset: KnowledgeAsset, outcome: AssetProcessingOutcome) -> None:
        template = await self.templates.get_by_source_asset(asset.id)
        kind = (
            "hybrid"
            if asset.mime_type in {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
            else "layout"
        )
        analysis_json = {"status": "indexed", **(outcome.template_analysis or {})}
        matcher_features = {
            "palette": outcome.normalized_data.get("palette", []),
            "font_families": outcome.normalized_data.get("font_families", []),
            "layout_type": outcome.normalized_data.get("layout_type"),
            "brand_score": outcome.normalized_data.get("brand_score"),
        }
        if not template:
            template = Template(
                tenant_id=asset.tenant_id,
                brand_space_id=asset.brand_space_id,
                name=asset.name,
                description=asset.extracted_summary,
                kind=kind,
                storage_path=asset.storage_path,
                source_knowledge_asset_id=asset.id,
                origin_field_key=asset.field_key,
                analysis_json=analysis_json,
                matcher_features_json=matcher_features,
                tags=outcome.template_tags,
            )
            await self.templates.add(template)
        else:
            template.name = asset.name
            template.description = asset.extracted_summary
            template.kind = kind
            template.origin_field_key = asset.field_key
            template.analysis_json = analysis_json
            template.matcher_features_json = matcher_features
            template.tags = outcome.template_tags

        metadata = await self.template_metadata.get_by_template(template.id)
        zone_map = {
            "layout_type": analysis_json.get("layout_type"),
            "zones": analysis_json.get("reusable_zones", analysis_json.get("editable_zones", [])),
            "icons": analysis_json.get("icons", []),
            "background_style": analysis_json.get("background_style", {}),
            "editorial_dna": analysis_json.get("editorial_dna", {}),
            "layout_dna": analysis_json.get("layout_dna", {}),
            "composition_logic": analysis_json.get("composition_logic", {}),
            "visual_craft_dna": analysis_json.get("visual_craft_dna", {}),
            "subject_semantics": analysis_json.get("subject_semantics", {}),
        }
        sizing_rules = {"page_count": asset.page_count, "source_format": outcome.source_format}
        platform_rules = {
            "supported_platforms": analysis_json.get("platform_hints", ["linkedin", "instagram"]),
            "analysis_status": "indexed",
        }
        export_rules = {"supported_formats": ["pdf", "png", "jpg", "doc"]}
        if not metadata:
            metadata = TemplateMetadata(
                tenant_id=asset.tenant_id,
                brand_space_id=asset.brand_space_id,
                template_id=template.id,
                zone_map=zone_map,
                sizing_rules=sizing_rules,
                platform_rules=platform_rules,
                editable_fields=[zone.get("role", "content") for zone in zone_map["zones"] if isinstance(zone, dict)],
                export_rules=export_rules,
            )
            await self.template_metadata.add(metadata)
        else:
            metadata.zone_map = zone_map
            metadata.sizing_rules = sizing_rules
            metadata.platform_rules = platform_rules
            metadata.editable_fields = [zone.get("role", "content") for zone in zone_map["zones"] if isinstance(zone, dict)]
            metadata.export_rules = export_rules

    async def _persist_legal_disclaimers(self, asset: KnowledgeAsset, outcome: AssetProcessingOutcome) -> None:
        """Extract and persist legal disclaimers from template/reference creative footer text"""
        structured = outcome.structured_data or {}
        footer_text = structured.get("footer")
        footer_style = structured.get("footer_style") or {}

        if not footer_text or not isinstance(footer_text, str):
            return

        # Check if footer contains legal language
        footer_lower = footer_text.lower()

        # Generic legal keywords (domain-agnostic)
        generic_legal_keywords = {
            "disclaimer", "regulated by", "subject to", "terms and conditions",
            "copyright", "all rights reserved", "privacy policy", "trademark"
        }

        # TODO: Load domain-specific keywords from brand context
        # (e.g., financial: "sebi", "amfi", "mutual fund", "investments are subject to")
        # domain_keywords = set(brand_context.get("legal_keywords", []))
        # legal_keywords = generic_legal_keywords | domain_keywords

        legal_keywords = generic_legal_keywords

        has_legal_content = any(keyword in footer_lower for keyword in legal_keywords)
        if not has_legal_content:
            return

        # Check if already exists for this source asset
        existing = await self.legal_assets.get_by_source_asset(asset.id)

        # Extract styling information
        font_size = 8
        text_color = "#666666"
        if footer_style:
            if "font_size" in footer_style:
                try:
                    font_size = int(footer_style["font_size"])
                except (ValueError, TypeError):
                    pass
            if "fill" in footer_style:
                text_color = str(footer_style["fill"])
            elif "color" in footer_style:
                text_color = str(footer_style["color"])

        # Determine applicable formats based on source format
        applies_to_formats = ["carousel", "static", "infographic"]

        # Determine asset_type based on content
        asset_type = "disclaimer"
        if "copyright" in footer_lower or "all rights reserved" in footer_lower:
            asset_type = "copyright"
        elif "privacy" in footer_lower:
            asset_type = "privacy"

        if existing:
            # Update existing legal asset
            existing.text_template = footer_text
            existing.asset_type = asset_type
            existing.applies_to_formats = applies_to_formats
            existing.font_size = font_size
            existing.text_color = text_color
            existing.position = "footer"
        else:
            # Create new legal asset
            legal_asset = BrandLegalAsset(
                tenant_id=asset.tenant_id,
                brand_space_id=asset.brand_space_id,
                asset_type=asset_type,
                text_template=footer_text,
                applies_to_formats=applies_to_formats,
                position="footer",
                font_size=font_size,
                text_color=text_color,
                confidence=0.9,
                source_asset_id=asset.id,
            )
            self.session.add(legal_asset)

        await self.session.flush()

    async def _persist_cta_templates(self, asset: KnowledgeAsset, outcome: AssetProcessingOutcome) -> None:
        """Extract and persist CTA templates from reference creative vision analysis"""
        structured = outcome.structured_data or {}
        vision = structured.get("vision_analysis") or {}
        component_motifs = vision.get("component_motifs") or {}
        cta_button_style = component_motifs.get("cta_button_style") or {}

        # Check if CTA button styling was detected
        if not cta_button_style.get("detected"):
            return

        # Extract OCR text to find CTA text
        ocr_text = structured.get("text", "")
        if not ocr_text:
            return

        # Look for common CTA patterns in text
        cta_keywords = [
            "explore now", "get started", "learn more", "shop now",
            "sign up", "book demo", "try free", "contact us",
            "discover", "start", "begin", "join", "subscribe"
        ]

        ocr_lower = ocr_text.lower()
        detected_cta = None
        for keyword in cta_keywords:
            if keyword in ocr_lower:
                # Extract the actual CTA text (with proper capitalization)
                # Find it in original text
                words = ocr_text.split()
                for i, word in enumerate(words):
                    if word.lower() == keyword.split()[0]:
                        # Get the phrase (1-3 words)
                        phrase_words = keyword.split()
                        if i + len(phrase_words) <= len(words):
                            candidate = " ".join(words[i:i+len(phrase_words)])
                            if candidate.lower() == keyword:
                                detected_cta = candidate
                                break
                if detected_cta:
                    break

        if not detected_cta:
            # Default CTA if pattern found but text not extracted
            detected_cta = "Learn More"

        # Extract button styling
        button_color = cta_button_style.get("button_color", "#000000")
        text_color = cta_button_style.get("text_color", "#FFFFFF")
        button_style_type = cta_button_style.get("style", "solid")
        border_radius = cta_button_style.get("border_radius", 8)

        # Map style to our enum
        style_map = {
            "solid": "rounded",
            "outlined": "sharp",
            "ghost": "rounded",
            "gradient": "rounded"
        }
        button_style = style_map.get(button_style_type, "rounded")

        # Check if template already exists for this brand
        existing_templates = await self.cta_templates.get_by_brand_space(asset.brand_space_id)

        # If no templates exist, create this as the default
        is_default = len(existing_templates) == 0

        # Generate template name based on detected characteristics
        template_name = f"auto_detected_{button_style_type}"

        # Check if this specific template already exists
        template_exists = any(t.template_name == template_name for t in existing_templates)

        if not template_exists:
            # Create new CTA template
            cta_template = BrandCTATemplate(
                tenant_id=asset.tenant_id,
                brand_space_id=asset.brand_space_id,
                template_name=template_name,
                headline_template="Discover how {brand} can help you",
                body_template="Take the next step with {brand}",
                button_text=detected_cta,
                button_color=button_color,
                button_text_color=text_color,
                button_style=button_style,
                icon_hint=None,
                visual_theme=vision.get("visual_mood", "professional"),
                is_default=is_default,
            )
            self.session.add(cta_template)
            await self.session.flush()

    async def _upsert_routing(self, asset: KnowledgeAsset, outcome: AssetProcessingOutcome) -> None:
        routing = await self.routing_repo.get_by_asset(asset.id)
        payload = {
            "tenant_id": asset.tenant_id,
            "brand_space_id": asset.brand_space_id,
            "knowledge_asset_id": asset.id,
            "requested_field_key": asset.field_key or asset.channel,
            "requested_category": asset.metadata_json.get("desired_category"),
            "routed_category": outcome.routed_category,
            "classifier": outcome.routing.get("classifier"),
            "confidence": outcome.routing.get("confidence"),
            "routing_reason": outcome.routing.get("routing_reason"),
            "decision_json": outcome.routing.get("decision_json", {}),
        }
        if not routing:
            self.session.add(AssetCategoryRouting(**payload))
            await self.session.flush()
            return
        routing.requested_field_key = payload["requested_field_key"]
        routing.requested_category = payload["requested_category"]
        routing.routed_category = payload["routed_category"]
        routing.classifier = payload["classifier"]
        routing.confidence = payload["confidence"]
        routing.routing_reason = payload["routing_reason"]
        routing.decision_json = payload["decision_json"]

    async def _upsert_processing_status(
        self,
        asset: KnowledgeAsset,
        lifecycle_state: str,
        status_message: str,
        processor_name: str | None = None,
        progress_current: int = 0,
        progress_total: int = 0,
        raw_status_json: dict | None = None,
    ) -> None:
        status = await self.processing_status.get_by_asset(asset.id)
        if not status:
            status = AssetProcessingStatus(
                tenant_id=asset.tenant_id,
                brand_space_id=asset.brand_space_id,
                knowledge_asset_id=asset.id,
                field_key=asset.field_key or asset.channel,
                lifecycle_state=lifecycle_state,
                processor_name=processor_name,
                progress_current=progress_current,
                progress_total=progress_total,
                status_message=status_message,
                raw_status_json=raw_status_json or {},
            )
            self.session.add(status)
            await self.session.flush()
            return
        status.field_key = asset.field_key or asset.channel
        status.lifecycle_state = lifecycle_state
        status.processor_name = processor_name or status.processor_name
        status.progress_current = progress_current
        status.progress_total = progress_total
        status.status_message = status_message
        status.raw_status_json = raw_status_json or status.raw_status_json

    async def _persist_processing_progress(
        self,
        asset_id: UUID,
        current: int,
        total: int,
        message: str,
    ) -> None:
        async with AsyncSessionLocal() as session:
            asset_repo = KnowledgeAssetRepository(session)
            status_repo = AssetProcessingStatusRepository(session)
            asset = await asset_repo.get(asset_id)
            status = await status_repo.get_by_asset(asset_id)
            if not asset or not status:
                return
            status.lifecycle_state = AssetLifecycle.PROCESSING
            status.progress_current = max(current, 0)
            status.progress_total = max(total, status.progress_total, 0)
            status.status_message = message
            status.raw_status_json = {
                **(status.raw_status_json or {}),
                "last_progress_message": message,
            }
            await session.commit()

    @staticmethod
    def _default_channel(field_key: str, desired_category: str | None) -> str:
        category = desired_category or field_key
        mapping = {
            "logo": "metadata",
            "audience_insights": "audience_insights",
            "reference_creatives": "reference_creative",
            "mood_board": "mood_board",
            "color_palette": "visual_identity",
            "font_guide": "visual_identity",
            "positive_word_bank": "guardrail_support",
            "negative_word_bank": "guardrail_support",
            "replaceable_word_bank": "guardrail_support",
            "brand_knowledge_templates": "template",
            "brand_knowledge_other": "brand",
            "template": "template",
        }
        return mapping.get(category, "brand")
