from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from docx import Document
from PIL import Image

from app.models.knowledge import TemplateMetadata
from app.models.knowledge import Template
from app.services.template import TemplateService


def test_template_score_rewards_platform_support_and_keywords() -> None:
    template = Template(
        tenant_id="11111111-1111-1111-1111-111111111111",
        brand_space_id="22222222-2222-2222-2222-222222222222",
        name="LinkedIn Product Launch",
        description="Professional launch layout for B2B announcements",
        kind="static",
        storage_path="templates/sample.png",
        analysis_json={},
        tags=["linkedin", "launch", "b2b"],
    )
    metadata = SimpleNamespace(
        platform_rules={"supported_platforms": ["linkedin", "x"]},
        export_rules={"supported_formats": ["png", "pdf"]},
        editable_fields=["headline", "body", "cta"],
        zone_map={"background_style": {"dominant_mode": "graphic"}},
    )
    score, reasons, breakdown, adaptation_plan, critical_misses = TemplateService._score_template(
        prompt="Create a LinkedIn launch post for a new B2B product",
        studio_panel={"platform_preset": "linkedin", "format": "static", "file_type": "png"},
        template=template,
        metadata=metadata,
        brand_context={},
    )
    assert score > 0
    assert any("platform" in reason for reason in reasons)
    assert breakdown["platform_fit"] > 0
    assert "compact_cta" not in adaptation_plan
    assert critical_misses == 0


def test_template_score_flags_structural_and_brand_mismatches() -> None:
    template = Template(
        tenant_id="11111111-1111-1111-1111-111111111111",
        brand_space_id="22222222-2222-2222-2222-222222222222",
        name="Minimal Announcement",
        description="Simple text-first announcement card",
        kind="static",
        storage_path="templates/announcement.png",
        analysis_json={"brand_score": 4.6},
        matcher_features_json={
            "palette": [{"hex_code": "#0A2540", "role": "primary"}],
            "font_families": [{"name": "Inter"}],
            "content_patterns": ["announcement"],
        },
        tags=["announcement"],
    )
    metadata = TemplateMetadata(
        tenant_id=template.tenant_id,
        brand_space_id=template.brand_space_id,
        template_id=template.id,
        zone_map={
            "layout_type": "static",
            "zones": [{"role": "headline"}],
            "background_style": {"dominant_mode": "graphic"},
        },
        sizing_rules={},
        platform_rules={"supported_platforms": ["instagram"]},
        editable_fields=["headline"],
        export_rules={"supported_formats": ["png"]},
    )

    score, reasons, breakdown, adaptation_plan, critical_misses = TemplateService._score_template(
        prompt="Create a detailed LinkedIn explainer comparing three benefits and include a strong CTA to register",
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
        template=template,
        metadata=metadata,
        brand_context={
            "identity": {"logo_asset_ids": ["logo-1"]},
            "visual_identity": {
                "palette_entries": [{"hex_code": "#A020F0", "role": "primary"}],
                "typography": {"font_families": [{"name": "Manrope"}]},
            },
        },
    )

    assert score > 0
    assert breakdown["content_structure"] >= 0
    assert "cta_reposition" in adaptation_plan
    assert "logo_injection_required" in adaptation_plan
    assert "palette_override_to_brand_system" in adaptation_plan
    assert "typography_override_to_brand_system" in adaptation_plan
    assert critical_misses >= 2


def test_template_score_rewards_extracted_template_text_overlap() -> None:
    template = Template(
        tenant_id="11111111-1111-1111-1111-111111111111",
        brand_space_id="22222222-2222-2222-2222-222222222222",
        name="Domestic Flyers Update",
        description="Travel fare update card",
        kind="static",
        storage_path="templates/flights.png",
        analysis_json={
            "extracted_text_preview": "Good News for Domestic Flyers. Govt caps ticket fares. Route distance and max fare economy.",
            "heading": "Good News for Domestic Flyers",
        },
        tags=["travel", "airfare"],
    )
    metadata = SimpleNamespace(
        platform_rules={"supported_platforms": ["instagram"]},
        export_rules={"supported_formats": ["png"]},
        editable_fields=["headline", "body", "cta"],
        zone_map={
            "background_style": {"dominant_mode": "graphic"},
            "zones": [
                {"role": "headline"},
                {"role": "body"},
                {"role": "cta"},
                {"role": "image"},
            ],
        },
    )

    score, reasons, breakdown, adaptation_plan, critical_misses = TemplateService._score_template(
        prompt="Create an engaging Instagram post with tips for cheaper flight fares and smarter domestic travel booking",
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png"},
        template=template,
        metadata=metadata,
        brand_context={},
    )

    assert score > 0
    assert breakdown["ocr_text_fit"] > 0
    assert any("template text fit" in reason for reason in reasons)
    assert critical_misses == 0
    assert "compact_cta" in adaptation_plan


def test_template_score_downgrades_flattened_text_heavy_templates_to_reference_style_only() -> None:
    template = Template(
        tenant_id="11111111-1111-1111-1111-111111111111",
        brand_space_id="22222222-2222-2222-2222-222222222222",
        name="FD Returns Poster",
        description="Flattened finance poster",
        kind="static",
        storage_path="templates/fd-returns.png",
        analysis_json={
            "extracted_text_preview": "FD returns fail to beat inflation. Fixed Deposit returns equal 6.5 percent. Inflation equals 5 percent. After tax many investors face negative returns.",
            "surface_kind": "reference_only_flattened_text",
            "text_overlay_risk": "high",
            "overlay_safe": False,
        },
        matcher_features_json={
            "surface_kind": "reference_only_flattened_text",
            "text_overlay_risk": "high",
            "overlay_safe": False,
        },
        tags=["bonds", "fd", "finance"],
    )
    metadata = TemplateMetadata(
        tenant_id=template.tenant_id,
        brand_space_id=template.brand_space_id,
        template_id=template.id,
        zone_map={
            "layout_type": "static",
            "zones": [
                {"role": "headline"},
                {"role": "body"},
                {"role": "cta"},
                {"role": "image"},
            ],
            "background_style": {"dominant_mode": "graphic"},
        },
        sizing_rules={},
        platform_rules={"supported_platforms": ["instagram"]},
        editable_fields=["headline", "body", "cta", "image"],
        export_rules={"supported_formats": ["png"]},
    )

    score, reasons, breakdown, adaptation_plan, critical_misses = TemplateService._score_template(
        prompt="Create an engaging Instagram post about why investors are shifting from fixed deposits to bonds in 2026",
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png"},
        template=template,
        metadata=metadata,
        brand_context={},
    )

    assert score > 0
    assert breakdown["surface_safety"] < 0
    assert adaptation_plan["reference_style_only"] is True
    assert critical_misses >= 3
    assert any("style reference" in reason for reason in reasons)


def test_normalize_editable_zones_supports_normalized_coordinates() -> None:
    zones = TemplateService._normalize_editable_zones(
        [
            {"zone_id": "headline", "role": "headline", "x": 0.1, "y": 0.12, "width": 0.7, "height": 0.18},
            {"zone_id": "cta", "role": "cta"},
        ],
        width=1200,
        height=627,
    )

    headline = next(zone for zone in zones if zone["role"] == "headline")
    cta = next(zone for zone in zones if zone["role"] == "cta")

    assert headline["x"] == 120
    assert headline["width"] == 840
    assert headline["height"] > 0
    assert cta["width"] > 0


class DummySession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_recommend_includes_template_asset_url() -> None:
    session = DummySession()
    service = TemplateService(session)
    tenant_id = uuid4()
    brand_space_id = uuid4()
    template = Template(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        name="Golden Explainer",
        description="Warm branded explainer",
        kind="static",
        storage_path="templates/golden-explainer.png",
        analysis_json={},
        tags=["finance"],
    )
    metadata = TemplateMetadata(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        template_id=template.id,
        zone_map={},
        sizing_rules={},
        platform_rules={"supported_platforms": ["instagram"]},
        editable_fields=["headline"],
        export_rules={"supported_formats": ["png"]},
    )

    service.templates.list_by_brand = AsyncMock(return_value=[template])
    service.metadata.get_by_template = AsyncMock(return_value=metadata)
    service.asset_delivery = SimpleNamespace(
        build_signed_url=lambda storage_path, filename: f"https://assets.test/{filename}"
    )
    service._score_template = lambda *args, **kwargs: (9.5, ["good fit"], {"platform_fit": 3.0}, {}, 0)  # type: ignore[method-assign]

    recommendations = await service.recommend(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        prompt="Create an Instagram explainer post",
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png"},
        brand_context={},
        limit=5,
    )

    assert len(recommendations) == 1
    assert recommendations[0].asset_url == "https://assets.test/golden-explainer.png"


@pytest.mark.asyncio
async def test_analyze_sets_processing_status_and_tracks_ocr_usage() -> None:
    session = DummySession()
    service = TemplateService(session)
    image_path = Path("tests") / f"template-analysis-{uuid4()}.png"
    Image.new("RGB", (1280, 720), color=(240, 245, 255)).save(image_path)

    try:
        template = Template(
            tenant_id=uuid4(),
            brand_space_id=uuid4(),
            name="Quarterly Update",
            description="Presentation-ready layout",
            kind="hybrid",
            storage_path=str(image_path),
            analysis_json={"status": "queued"},
            tags=["report"],
        )
        metadata = TemplateMetadata(
            tenant_id=template.tenant_id,
            brand_space_id=template.brand_space_id,
            template_id=template.id,
            zone_map={},
            sizing_rules={},
            platform_rules={},
            editable_fields=[],
            export_rules={},
        )

        service.templates.get = AsyncMock(return_value=template)
        service.metadata.get_by_template = AsyncMock(return_value=metadata)
        service.storage = SimpleNamespace(absolute_path=lambda _path: str(image_path))
        service.ocr = SimpleNamespace(
            extract=lambda _path: {
                "text": "Quarterly growth highlights",
                "images": [str(image_path)],
                "page_count": 3,
                "source_format": "png",
            }
        )
        service.vision = SimpleNamespace(
            analyze=lambda _path, fallback: {
                **fallback,
                "layout_type": "infographic",
                "platform_hints": ["linkedin", "instagram"],
            }
        )
        service.usage = SimpleNamespace(enforce=AsyncMock(), increment=AsyncMock())

        analyzed = await service.analyze(template.id)

        assert analyzed is template
        assert template.analysis_json["status"] == "indexed"
        assert template.analysis_json["page_count"] == 3
        assert metadata.platform_rules["analysis_status"] == "indexed"
        assert metadata.sizing_rules["page_count"] == 3
        service.usage.enforce.assert_awaited_once()
        service.usage.increment.assert_awaited_once()
        assert session.commits >= 2
    finally:
        image_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_analyze_uses_source_format_for_mislabeled_docx_files() -> None:
    session = DummySession()
    service = TemplateService(session)
    doc_path = Path("tests") / f"brand-strategy-{uuid4()}.doc"
    document = Document()
    document.add_paragraph("Brand strategy playbook")
    document.save(doc_path)

    template = Template(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        name="Brand Strategy",
        description="Long-form strategy document",
        kind="hybrid",
        storage_path=str(doc_path),
        analysis_json={"status": "queued"},
        tags=["strategy"],
    )
    metadata = TemplateMetadata(
        tenant_id=template.tenant_id,
        brand_space_id=template.brand_space_id,
        template_id=template.id,
        zone_map={},
        sizing_rules={},
        platform_rules={},
        editable_fields=[],
        export_rules={},
    )

    service.templates.get = AsyncMock(return_value=template)
    service.metadata.get_by_template = AsyncMock(return_value=metadata)
    service.storage = SimpleNamespace(absolute_path=lambda _path: str(doc_path))
    service.ocr = SimpleNamespace(
        extract=lambda _path: {
            "text": "",
            "images": [],
            "page_count": 1,
            "source_format": "docx",
        }
    )
    service.vision = SimpleNamespace(analyze=lambda _path, fallback: fallback)
    service.usage = SimpleNamespace(enforce=AsyncMock(), increment=AsyncMock())

    try:
        analyzed = await service.analyze(template.id)

        assert analyzed is template
        assert template.analysis_json["status"] == "indexed"
        assert template.analysis_json["extracted_text_preview"].startswith("Brand strategy playbook")
        service.usage.enforce.assert_awaited_once()
        service.usage.increment.assert_awaited_once()
    finally:
        doc_path.unlink(missing_ok=True)
