from app.ai.blueprint import BlueprintService
from app.ai.contracts import GenerationSceneGraph


def test_blueprint_service_marks_template_mode_and_applies_brand_rules() -> None:
    service = BlueprintService()

    blueprint = service.build(
        text_payload={"headline": "Launch faster", "body": "Clear explanation", "cta": "Get started"},
        studio_panel={"platform_preset": "linkedin", "format": "static", "file_type": "png", "size": {"width": 1200, "height": 627}},
        template_metadata={
            "zone_map": {
                "layout_type": "template-layout",
                "zones": [
                    {"zone_id": "headline", "role": "headline", "x": 10, "y": 10, "width": 400, "height": 80},
                    {"zone_id": "body", "role": "body", "x": 10, "y": 100, "width": 400, "height": 140},
                    {"zone_id": "cta", "role": "cta", "x": 10, "y": 260, "width": 280, "height": 64},
                ],
            }
        },
        layout_decision={
            "mode": "exact_template",
            "template_id": "abc-template",
            "adaptation_plan": {},
        },
        brand_context={
            "identity": {"logo_asset_id": "logo-1"},
            "visual_identity": {
                "brand_color_palette": {"primary": "#111111", "secondary": "#eeeeee"},
                "typography": {"font_families": [{"name": "Manrope"}]},
            },
            "guardrails": {"blocked_words": ["banned"]},
        },
    )

    assert blueprint.source_mode == "exact_template"
    assert blueprint.source_template_id == "abc-template"
    assert blueprint.brand_rules_applied["logo_required"] is True
    assert "Manrope" in blueprint.brand_rules_applied["font_families"]


def test_blueprint_service_adapts_template_zones_for_long_copy() -> None:
    service = BlueprintService()

    blueprint = service.build(
        text_payload={
            "headline": "A very long headline that should cause the system to expand the headline zone for an adapted template layout",
            "body": "Body copy " * 80,
            "cta": "Start now",
        },
        studio_panel={"platform_preset": "instagram", "format": "carousel", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        template_metadata={
            "zone_map": {
                "layout_type": "template-layout",
                "zones": [
                    {"zone_id": "headline", "role": "headline", "x": 0, "y": 0, "width": 600, "height": 100},
                    {"zone_id": "body", "role": "body", "x": 0, "y": 120, "width": 600, "height": 280},
                    {"zone_id": "image", "role": "image", "x": 620, "y": 120, "width": 420, "height": 420},
                    {"zone_id": "cta", "role": "cta", "x": 0, "y": 950, "width": 360, "height": 90},
                ],
            }
        },
        layout_decision={
            "mode": "adapted_template",
            "template_id": "def-template",
            "adaptation_plan": {"expand_headline_or_body": True, "multi_section_flow": True, "compact_cta": True},
        },
        brand_context={},
    )

    headline_zone = next(zone for zone in blueprint.zones if zone.role == "headline")
    body_zone = next(zone for zone in blueprint.zones if zone.role == "body")
    cta_zone = next(zone for zone in blueprint.zones if zone.role == "cta")

    assert blueprint.source_mode == "adapted_template"
    assert headline_zone.height > 100
    assert body_zone.max_lines >= 9
    assert cta_zone.width <= 360


def test_blueprint_service_completes_symbolic_template_zones() -> None:
    service = BlueprintService()

    blueprint = service.build(
        text_payload={"headline": "Launch faster", "body": "Clear explanation", "cta": "Get started"},
        studio_panel={"platform_preset": "linkedin", "format": "static", "file_type": "png", "size": {"width": 1200, "height": 627}},
        template_metadata={
            "zone_map": {
                "layout_type": "template-layout",
                "zones": [
                    {"zone_id": "headline", "role": "headline"},
                    {"zone_id": "body", "role": "body"},
                    {"zone_id": "image", "role": "image"},
                    {"zone_id": "cta", "role": "cta"},
                ],
            }
        },
        layout_decision={
            "mode": "exact_template",
            "template_id": "abc-template",
            "adaptation_plan": {},
        },
        brand_context={},
    )

    assert all(zone.width > 0 and zone.height > 0 for zone in blueprint.zones)
    assert next(zone for zone in blueprint.zones if zone.role == "headline").x >= 0


def test_blueprint_service_from_scene_graph_clears_template_identity_for_synthesized_style_only_layout() -> None:
    service = BlueprintService()

    scene_graph = GenerationSceneGraph.model_validate({
        "canvas": {"width": 1080, "height": 1080, "platform": "instagram", "file_type": "png"},
        "layout_mode": "synthesized_layout",
        "elements": [
            {"element_id": "headline", "element_type": "text", "role": "headline", "geometry": {"x": 80, "y": 80, "width": 600, "height": 120}, "text": "Inflation changes what money buys"},
            {"element_id": "body", "element_type": "text", "role": "body", "geometry": {"x": 80, "y": 240, "width": 520, "height": 180}, "text": "Savings lose purchasing power over time."},
            {"element_id": "image", "element_type": "image", "role": "image", "geometry": {"x": 620, "y": 180, "width": 300, "height": 360}},
        ],
        "template_adaptation": {
            "selected_template_id": "fd-early-template",
            "reference_style_only": True,
            "topic_fit_too_weak": True,
        },
        "styles": {"layout_type": "infographic"},
    })

    blueprint = service.from_scene_graph(
        scene_graph,
        studio_panel={"platform_preset": "instagram", "format": "infographic", "file_type": "png"},
        text_payload={"headline": "Inflation changes what money buys", "body": "Savings lose purchasing power over time.", "cta": ""},
    )

    assert blueprint.source_mode == "synthesized_layout"
    assert blueprint.source_template_id is None


def test_blueprint_service_from_scene_graph_keeps_image_zone_ids_aligned_with_resolved_zones() -> None:
    service = BlueprintService()

    scene_graph = GenerationSceneGraph.model_validate({
        "canvas": {"width": 1080, "height": 1350, "platform": "linkedin", "file_type": "png"},
        "layout_mode": "adapted_template",
        "elements": [
            {"element_id": "primary_image", "element_type": "image", "role": "image", "geometry": {"x": 540, "y": 500, "width": 900, "height": 700, "units": "px"}},
            {"element_id": "headline", "element_type": "text", "role": "headline", "geometry": {"x": 80, "y": 120, "width": 561, "height": 270, "units": "px"}, "text": "Avoid These Common Bond Investing Mistakes"},
        ],
        "styles": {"layout_type": "image_led_social"},
    })

    blueprint = service.from_scene_graph(
        scene_graph,
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
        text_payload={"headline": "Avoid These Common Bond Investing Mistakes", "body": "", "cta": ""},
    )

    image_zone = next(zone for zone in blueprint.zones if zone.role == "image")
    assert blueprint.image_zones[0]["zone_id"] == image_zone.zone_id
