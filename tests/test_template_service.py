from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from docx import Document
from PIL import Image

from app.models.knowledge import TemplateMetadata
from app.models.knowledge import Template
from app.schemas.template import TemplateRecommendationResponse
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


def test_template_tokenize_excludes_generic_brand_and_connector_words() -> None:
    tokens = TemplateService._tokenize(
        "Write a LinkedIn carousel for Jiraaf on the India New Zealand FTA"
    )

    assert "jiraaf" not in tokens
    assert "for" not in tokens
    assert "the" not in tokens
    assert {"india", "new", "zealand", "fta"}.issubset(tokens)


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


def test_template_score_prefers_multi_page_templates_for_carousel_requests() -> None:
    carousel_template = Template(
        tenant_id="11111111-1111-1111-1111-111111111111",
        brand_space_id="22222222-2222-2222-2222-222222222222",
        name="Retirement Story Carousel",
        description="Multi-slide retirement explainer",
        kind="static",
        storage_path="templates/retirement-story.pdf",
        analysis_json={"page_count": 5, "layout_type": "carousel"},
        tags=["retirement", "carousel"],
    )
    static_template = Template(
        tenant_id="11111111-1111-1111-1111-111111111111",
        brand_space_id="22222222-2222-2222-2222-222222222222",
        name="Retirement Infographic Card",
        description="Single-slide retirement explainer",
        kind="static",
        storage_path="templates/retirement-card.png",
        analysis_json={"page_count": 1, "layout_type": "infographic"},
        tags=["retirement", "infographic"],
    )
    carousel_metadata = TemplateMetadata(
        tenant_id=carousel_template.tenant_id,
        brand_space_id=carousel_template.brand_space_id,
        template_id=carousel_template.id,
        zone_map={"layout_type": "carousel", "zones": [{"role": "headline"}, {"role": "body"}, {"role": "image"}]},
        sizing_rules={"page_count": 5},
        platform_rules={"supported_platforms": ["linkedin"]},
        editable_fields=["headline", "body", "image"],
        export_rules={"supported_formats": ["png", "pdf"]},
    )
    static_metadata = TemplateMetadata(
        tenant_id=static_template.tenant_id,
        brand_space_id=static_template.brand_space_id,
        template_id=static_template.id,
        zone_map={"layout_type": "infographic", "zones": [{"role": "headline"}, {"role": "body"}, {"role": "image"}]},
        sizing_rules={"page_count": 1},
        platform_rules={"supported_platforms": ["linkedin"]},
        editable_fields=["headline", "body", "image"],
        export_rules={"supported_formats": ["png", "pdf"]},
    )

    carousel_score, _, carousel_breakdown, carousel_plan, carousel_misses = TemplateService._score_template(
        prompt="Create a 5-slide LinkedIn carousel on retirement planning mistakes.",
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
        template=carousel_template,
        metadata=carousel_metadata,
        brand_context={},
    )
    static_score, _, static_breakdown, static_plan, static_misses = TemplateService._score_template(
        prompt="Create a 5-slide LinkedIn carousel on retirement planning mistakes.",
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
        template=static_template,
        metadata=static_metadata,
        brand_context={},
    )

    assert carousel_score > static_score
    assert carousel_breakdown["format_fit"] > static_breakdown["format_fit"]
    assert "multi_slide_sequence_synthesis" not in carousel_plan
    assert static_plan["multi_slide_sequence_synthesis"] is True
    assert static_misses > carousel_misses


def test_adaptation_score_balances_carousel_topic_fit_and_page_count() -> None:
    five_slide_topical = TemplateService._adaptation_score_for_recommendation(
        requested_format_family="carousel",
        template_profile={"format_family": "carousel", "page_count": 5},
        base_score=30.0,
        match_type="adapted_template",
        score_breakdown={"keyword_overlap": 6.0, "ocr_text_fit": 3.0},
    )
    seven_slide_generic = TemplateService._adaptation_score_for_recommendation(
        requested_format_family="carousel",
        template_profile={"format_family": "carousel", "page_count": 7},
        base_score=30.0,
        match_type="adapted_template",
        score_breakdown={"keyword_overlap": 0.0, "ocr_text_fit": 0.0},
    )

    assert five_slide_topical > seven_slide_generic


def test_template_score_prefers_topic_relevant_retirement_carousel_over_generic_finance_samples() -> None:
    tenant_id = uuid4()
    brand_space_id = uuid4()
    prompt = (
        "Create a LinkedIn carousel on how your 40s can power a smarter retirement plan. "
        "Break down retirement planning into practical steps including retirement corpus calculation, "
        "inflation impact, investment scaling, and diversification. Focus on creating a structured "
        "financial roadmap for working professionals in their 40s."
    )
    studio_panel = {"platform_preset": "linkedin", "format": "carousel", "file_type": "png"}

    def _template(name: str, text: str, page_count: int) -> tuple[Template, TemplateMetadata]:
        template = Template(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            name=name,
            kind="carousel",
            storage_path=f"templates/{name}.pdf",
            analysis_json={
                "layout_type": "carousel",
                "page_count": page_count,
                "extracted_text_preview": text[:300],
                "page_text": [{"text": text}],
            },
            matcher_features_json={"layout_type": "carousel", "content_patterns": ["explainer"]},
            tags=["carousel"],
        )
        metadata = TemplateMetadata(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            template_id=template.id,
            zone_map={"layout_type": "carousel", "zones": [{"role": "headline"}, {"role": "body"}, {"role": "image"}]},
            sizing_rules={"page_count": page_count},
            platform_rules={"supported_platforms": ["linkedin"]},
            editable_fields=["headline", "body", "image"],
            export_rules={"supported_formats": ["png"]},
        )
        return template, metadata

    retirement_template, retirement_metadata = _template(
        "(Jiraaf) Planning your retirement",
        "How Your 40s Can Power a Smarter Retirement Plan. Retirement corpus calculation. Inflation impact. Investment scaling. Diversification. Financial roadmap.",
        6,
    )
    bond_template, bond_metadata = _template(
        "Bond Analyzer",
        "Bond investing is no longer just about looking at yields. Compare issuers, spreads, maturities, ratings, and debt market trends.",
        5,
    )
    fta_template, fta_metadata = _template(
        "FTA",
        "India New Zealand trade deal. Tariffs, exports, imports, mobility, services, and investment clauses.",
        4,
    )

    retirement_score, _, retirement_breakdown, retirement_plan, retirement_misses = TemplateService._score_template(
        prompt, studio_panel, retirement_template, retirement_metadata, {}
    )
    bond_score, _, bond_breakdown, bond_plan, bond_misses = TemplateService._score_template(
        prompt, studio_panel, bond_template, bond_metadata, {}
    )
    fta_score, _, fta_breakdown, fta_plan, fta_misses = TemplateService._score_template(
        prompt, studio_panel, fta_template, fta_metadata, {}
    )

    retirement_adaptation = TemplateService._adaptation_score_for_recommendation(
        requested_format_family="carousel",
        template_profile=TemplateService._template_profile(retirement_template, retirement_metadata),
        base_score=retirement_score,
        match_type=TemplateService._match_type_for_score(retirement_score, retirement_plan, retirement_misses),
        score_breakdown=retirement_breakdown,
    )
    bond_adaptation = TemplateService._adaptation_score_for_recommendation(
        requested_format_family="carousel",
        template_profile=TemplateService._template_profile(bond_template, bond_metadata),
        base_score=bond_score,
        match_type=TemplateService._match_type_for_score(bond_score, bond_plan, bond_misses),
        score_breakdown=bond_breakdown,
    )
    fta_adaptation = TemplateService._adaptation_score_for_recommendation(
        requested_format_family="carousel",
        template_profile=TemplateService._template_profile(fta_template, fta_metadata),
        base_score=fta_score,
        match_type=TemplateService._match_type_for_score(fta_score, fta_plan, fta_misses),
        score_breakdown=fta_breakdown,
    )

    assert retirement_breakdown["topic_semantic_fit"] > bond_breakdown["topic_semantic_fit"]
    assert retirement_breakdown["topic_semantic_fit"] > fta_breakdown["topic_semantic_fit"]
    assert retirement_adaptation > bond_adaptation
    assert retirement_adaptation > fta_adaptation


def test_calibrate_recommendation_confidence_keeps_ranked_carousel_matches_distinct() -> None:
    recommendations = [
        TemplateRecommendationResponse(
            template_id=uuid4(),
            name="FTA-3",
            score=24.0,
            match_type="adapted_template",
            decision_confidence=1.0,
            format_family="carousel",
            is_primary_adaptation=True,
            metadata={"adaptation_score": 35.0},
        ),
        TemplateRecommendationResponse(
            template_id=uuid4(),
            name="Behavioural-Biases",
            score=22.0,
            match_type="adapted_template",
            decision_confidence=1.0,
            format_family="carousel",
            metadata={"adaptation_score": 25.0},
        ),
        TemplateRecommendationResponse(
            template_id=uuid4(),
            name="Bond-Analyzer",
            score=21.0,
            match_type="adapted_template",
            decision_confidence=1.0,
            format_family="carousel",
            metadata={"adaptation_score": 20.0},
        ),
    ]

    calibrated = TemplateService._calibrate_recommendation_confidence(recommendations)

    confidences = [item.decision_confidence for item in calibrated]
    assert confidences == sorted(confidences, reverse=True)
    assert len(set(confidences)) == 3
    assert all(confidence is not None and confidence < 1.0 for confidence in confidences)


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
    template.id = uuid4()
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
async def test_recommend_prefers_same_format_family_and_exposes_adaptation_metadata() -> None:
    session = DummySession()
    service = TemplateService(session)
    tenant_id = uuid4()
    brand_space_id = uuid4()
    carousel_template = Template(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        name="Retirement Story Carousel",
        description="Five-slide retirement explainer",
        kind="static",
        storage_path="templates/retirement-story.pdf",
        analysis_json={"page_count": 5, "layout_type": "carousel"},
        tags=["retirement", "carousel"],
    )
    carousel_template.id = uuid4()
    static_template = Template(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        name="Retirement Poster",
        description="Single-post retirement summary",
        kind="static",
        storage_path="templates/retirement-poster.png",
        analysis_json={"page_count": 1, "layout_type": "static"},
        tags=["retirement", "poster"],
    )
    static_template.id = uuid4()
    carousel_metadata = TemplateMetadata(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        template_id=carousel_template.id,
        zone_map={"layout_type": "carousel", "zones": [{"role": "headline"}, {"role": "body"}, {"role": "image"}]},
        sizing_rules={"page_count": 5},
        platform_rules={"supported_platforms": ["linkedin"]},
        editable_fields=["headline", "body", "image"],
        export_rules={"supported_formats": ["png", "pdf"]},
    )
    static_metadata = TemplateMetadata(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        template_id=static_template.id,
        zone_map={"layout_type": "static", "zones": [{"role": "headline"}, {"role": "body"}, {"role": "image"}]},
        sizing_rules={"page_count": 1},
        platform_rules={"supported_platforms": ["linkedin"]},
        editable_fields=["headline", "body", "image"],
        export_rules={"supported_formats": ["png", "pdf"]},
    )

    service.templates.list_by_brand = AsyncMock(return_value=[static_template, carousel_template])
    service.metadata.get_by_template = AsyncMock(side_effect=[static_metadata, carousel_metadata])
    service.asset_delivery = SimpleNamespace(
        build_signed_url=lambda storage_path, filename: f"https://assets.test/{filename}"
    )

    def _mock_score(_prompt, _panel, template, _metadata, _brand_context):
        if template.id == static_template.id:
            return (9.8, ["strong topical match"], {"format_fit": 1.0}, {}, 0)
        return (8.4, ["carousel structure fit"], {"format_fit": 5.0}, {}, 0)

    service._score_template = _mock_score  # type: ignore[method-assign]

    recommendations = await service.recommend(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        prompt="Create a 5-slide LinkedIn carousel on retirement planning mistakes.",
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
        brand_context={},
        limit=5,
    )

    assert [item.name for item in recommendations] == ["Retirement Story Carousel", "Retirement Poster"]
    assert recommendations[0].metadata["format_family"] == "carousel"
    assert recommendations[1].metadata["format_family"] == "static"
    assert recommendations[0].metadata["adaptation_score"] > recommendations[1].metadata["adaptation_score"]


@pytest.mark.asyncio
async def test_recommend_collapses_carousel_slides_into_family_cards() -> None:
    session = DummySession()
    service = TemplateService(session)
    tenant_id = uuid4()
    brand_space_id = uuid4()

    slide_one = Template(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        name="Retirement-Planning-1",
        description="Slide 1",
        kind="static",
        storage_path="templates/retirement-planning-1.png",
        analysis_json={"page_count": 1, "layout_type": "carousel"},
        tags=["retirement", "carousel"],
    )
    slide_one.id = uuid4()
    slide_two = Template(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        name="Retirement-Planning-2",
        description="Slide 2",
        kind="static",
        storage_path="templates/retirement-planning-2.png",
        analysis_json={"page_count": 1, "layout_type": "carousel"},
        tags=["retirement", "carousel"],
    )
    slide_two.id = uuid4()
    other_family = Template(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        name="Bond-Mistakes-1",
        description="Other family",
        kind="static",
        storage_path="templates/bond-mistakes-1.png",
        analysis_json={"page_count": 1, "layout_type": "carousel"},
        tags=["bonds", "carousel"],
    )
    other_family.id = uuid4()
    metadata = TemplateMetadata(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        template_id=slide_one.id,
        zone_map={"layout_type": "carousel", "zones": [{"role": "headline"}, {"role": "body"}, {"role": "image"}]},
        sizing_rules={"page_count": 1},
        platform_rules={"supported_platforms": ["linkedin"]},
        editable_fields=["headline", "body", "image"],
        export_rules={"supported_formats": ["png"]},
    )

    service.templates.list_by_brand = AsyncMock(return_value=[slide_two, other_family, slide_one])
    service.metadata.get_by_template = AsyncMock(side_effect=[metadata, metadata, metadata])
    service.asset_delivery = SimpleNamespace(
        build_signed_url=lambda storage_path, filename: f"https://assets.test/{filename}"
    )

    def _mock_score(_prompt, _panel, template, _metadata, _brand_context):
        scores = {
            slide_one.id: 9.1,
            slide_two.id: 8.8,
            other_family.id: 8.2,
        }
        return (scores[template.id], ["fit"], {"format_fit": 5.0}, {}, 0)

    service._score_template = _mock_score  # type: ignore[method-assign]

    recommendations = await service.recommend(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        prompt="Create a 5-slide LinkedIn carousel on retirement planning mistakes.",
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
        brand_context={},
        limit=5,
    )

    assert [item.display_name for item in recommendations] == ["Retirement Planning", "Bond Mistakes"]
    assert [item.recommendation_group_key for item in recommendations] == ["RETIREMENT-PLANNING", "BOND-MISTAKES"]
    assert recommendations[0].is_primary_adaptation is True
    assert recommendations[0].selection_reason == "Best Adaptation"
    assert recommendations[0].metadata["family_member_count"] == 2


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
