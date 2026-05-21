from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.schemas.brand import BrandSectionUpsertRequest, BrandUpdateRequest
from app.services.brand import BrandSpaceService


class DummySession:
    def __init__(self) -> None:
        self.commits = 0
        self.refreshed: list[object] = []

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, instance: object) -> None:
        self.refreshed.append(instance)


def build_brand(**overrides):
    payload = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "name": "Acme",
        "slug": "acme",
        "description": "Original description",
        "industry_category": "Technology",
        "lifecycle_state": "draft",
        "is_finalized": False,
        "overview_snapshot": {},
        "resolved_brand_context": {},
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


async def test_refresh_context_commits_and_refreshes_brand() -> None:
    session = DummySession()
    service = BrandSpaceService(session)
    brand = build_brand()
    snapshot = SimpleNamespace(id=uuid4(), context_json={"identity": {"brand_name": "Acme"}})
    service.validator.refresh_brand_context = AsyncMock(return_value=(brand, snapshot))

    refreshed = await service.refresh_context(brand.id)

    assert refreshed is brand
    service.validator.refresh_brand_context.assert_awaited_once_with(brand.id)


async def test_update_brand_commits_and_refreshes_brand() -> None:
    session = DummySession()
    service = BrandSpaceService(session)
    brand = build_brand()
    service.brands.get_scoped = AsyncMock(return_value=brand)

    updated = await service.update_brand(
        brand.tenant_id,
        brand.id,
        BrandUpdateRequest(
            description="Updated description",
            overview_snapshot={"foundations": {"brand_mission": "Grow"}},
        ),
    )

    assert updated is brand
    assert brand.description == "Updated description"
    assert brand.overview_snapshot == {"foundations": {"brand_mission": "Grow"}}
    assert session.commits == 1
    assert session.refreshed == [brand]


async def test_upsert_guardrails_filters_section_only_metadata_for_orm_write() -> None:
    session = DummySession()
    service = BrandSpaceService(session)
    brand = build_brand()
    captured_section = None
    captured_guardrail = None

    async def capture_section(section):
        nonlocal captured_section
        captured_section = section
        return section

    async def capture_guardrail(guardrail):
        nonlocal captured_guardrail
        captured_guardrail = guardrail
        return guardrail

    service.brands.get_scoped = AsyncMock(return_value=brand)
    service.sections.list_current_sections = AsyncMock(return_value=[])
    service.sections.add = AsyncMock(side_effect=capture_section)
    service.guardrails.list_by_brand = AsyncMock(return_value=[])
    service.guardrails.add = AsyncMock(side_effect=capture_guardrail)
    service.refresh_context = AsyncMock(return_value=brand)

    payload = BrandSectionUpsertRequest(
        section_code="guardrails",
        payload={
            "positive_word_bank": ["clear", "confident"],
            "replaceable_words": ["cheap"],
            "negative_word_bank": ["spammy"],
            "dos": ["Be direct"],
            "donts": ["Use slang"],
            "restricted_topics": ["Politics"],
            "restricted_claims": ["Guaranteed returns"],
            "blocked_words": ["best ever"],
            "custom_rules": ["Avoid hype claims"],
            "positive_word_bank_asset_ids": [str(uuid4())],
            "word_bank_assets": {"positive": [{"name": "approved-words.pdf"}]},
        },
        completion_percent=100,
    )

    updated = await service.upsert_section(brand.tenant_id, brand.id, payload)

    assert updated is brand
    assert captured_section is not None
    assert captured_section.payload["positive_word_bank_asset_ids"]
    assert captured_section.payload["word_bank_assets"]["positive"][0]["name"] == "approved-words.pdf"
    assert captured_guardrail is not None
    assert captured_guardrail.positive_word_bank == ["clear", "confident"]
    assert captured_guardrail.custom_rules == ["Avoid hype claims"]
    assert not hasattr(captured_guardrail, "positive_word_bank_asset_ids")
    assert not hasattr(captured_guardrail, "word_bank_assets")
    assert session.commits == 1
    service.refresh_context.assert_awaited_once_with(brand.id)


async def test_publish_brand_only_requires_identity_section() -> None:
    session = DummySession()
    service = BrandSpaceService(session)
    brand = build_brand()
    identity_section = SimpleNamespace(section_code="identity", payload={"brand_name": "Acme"}, completion_percent=40)
    service.brands.get_scoped = AsyncMock(return_value=brand)
    service.sections.list_current_sections = AsyncMock(return_value=[identity_section])
    service.refresh_context = AsyncMock(return_value=brand)

    published = await service.publish_brand(brand.tenant_id, brand.id)

    assert published is brand
    assert brand.lifecycle_state == "active"
    assert brand.is_finalized is True
    service.refresh_context.assert_awaited_once_with(brand.id)


async def test_unpublish_brand_returns_to_draft() -> None:
    session = DummySession()
    service = BrandSpaceService(session)
    brand = build_brand(lifecycle_state="active", is_finalized=True)
    service.brands.get_scoped = AsyncMock(return_value=brand)

    unpublished = await service.unpublish_brand(brand.tenant_id, brand.id)

    assert unpublished is brand
    assert brand.lifecycle_state == "draft"
