from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.models.knowledge import KnowledgeAsset
from app.services.knowledge import KnowledgeService


class DummySession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_process_asset_tolerates_non_utf8_analysis_sidecar() -> None:
    session = DummySession()
    service = KnowledgeService(session)
    source_path = Path("tests") / f"floating-rate-bonds-{uuid4()}.jpg"
    source_path.write_bytes(b"fake-image")
    analysis_path = Path("tests") / f"floating-rate-bonds-analysis-{uuid4()}.json"
    analysis_path.write_bytes(b"\xffGenerated visual analysis")

    asset = KnowledgeAsset(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        name="Floating Rate Bonds",
        original_filename="Floating-Rate-Bonds.jpg",
        mime_type="image/jpeg",
        storage_path=str(source_path),
        lifecycle_state="uploaded",
        channel="brand",
        metadata_json={},
    )

    service.assets.get = AsyncMock(return_value=asset)
    service.storage = SimpleNamespace(absolute_path=lambda _path: str(source_path))
    service.ocr = SimpleNamespace(
        extract=lambda path: {
            "text": "Extracted OCR text" if str(path) == str(source_path) else "",
            "images": [str(source_path)],
            "page_count": 2,
            "analysis_path": str(analysis_path),
            "source_format": "jpg",
        }
    )
    service.usage = SimpleNamespace(enforce=AsyncMock(), increment=AsyncMock())
    service.retrieval = SimpleNamespace(delete_asset=Mock(), index_asset=Mock())

    try:
        processed = await service.process_asset(asset.id)

        assert processed is asset
        assert asset.lifecycle_state == "indexed"
        assert "Extracted OCR text" in (asset.extracted_text or "")
        assert "Generated visual analysis" in (asset.extracted_text or "")
        service.usage.enforce.assert_awaited_once()
        service.usage.increment.assert_awaited_once()
        service.retrieval.index_asset.assert_called_once()
        assert session.commits >= 2
    finally:
        source_path.unlink(missing_ok=True)
        analysis_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_process_asset_delegates_fielded_brand_attachments(monkeypatch) -> None:
    session = DummySession()
    service = KnowledgeService(session)
    asset = KnowledgeAsset(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        name="Logo Pack",
        original_filename="logo-pack.pdf",
        mime_type="application/pdf",
        storage_path="uploads/logo-pack.pdf",
        lifecycle_state="uploaded",
        channel="brand",
        field_key="logo",
        metadata_json={},
    )
    service.assets.get = AsyncMock(return_value=asset)

    called = {}

    class DummyBrandAssetService:
        def __init__(self, _session):
            pass

        async def process_asset(self, delegated_asset_id):
            called["asset_id"] = delegated_asset_id
            return asset

    monkeypatch.setattr("app.services.knowledge.BrandAssetService", DummyBrandAssetService)

    processed = await service.process_asset(asset.id)

    assert processed is asset
    assert called["asset_id"] == asset.id
