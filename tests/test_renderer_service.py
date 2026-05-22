from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw
import pytest

from app.ai.contracts import BlueprintPayload, BlueprintZone, GeneratedImageAsset, GenerationSceneGraph, RendererInput, SceneGraphCanvas, SceneGraphElement, SceneGraphGeometry, StructuredTextPayload
from app.services.renderer import RendererService


def _payload(format_name: str, preset: str = "linkedin", size: dict | None = None) -> RendererInput:
    resolved_size = size or {"width": 1200, "height": 627}
    return RendererInput(
        tenant_id="11111111-1111-1111-1111-111111111111",
        brand_space_id="22222222-2222-2222-2222-222222222222",
        content_version_id="33333333-3333-3333-3333-333333333333",
        studio_panel={"format": format_name, "platform_preset": preset, "file_type": "png", "size": resolved_size},
        blueprint=BlueprintPayload(
            layout_type=format_name,
            zones=[
                BlueprintZone(zone_id="headline", role="headline", x=0, y=0, width=100, height=100, max_lines=3),
                BlueprintZone(zone_id="body", role="body", x=0, y=100, width=100, height=100, max_lines=7),
                BlueprintZone(zone_id="cta", role="cta", x=0, y=200, width=100, height=50, max_lines=2),
            ],
            hierarchy=["headline", "body", "cta"],
            text_blocks=[],
            image_zones=[],
            logo_rules={},
            cta_placement={"alignment": "left"},
            platform_preset=preset,
            export_format="png",
            overflow_strategy={"mode": "shrink_then_wrap"},
        ),
        text=StructuredTextPayload(
            headline="A launch headline",
            body="Sentence one. Sentence two. Sentence three. Sentence four. Sentence five. Sentence six. Sentence seven. Sentence eight.",
            cta="Learn more",
            hashtags=["#brand"],
            metadata={
                "section_label": "Brand Insight",
                "supporting_line": "Trusted market guidance for confident decisions.",
                "proof_points": [
                    "Curated opportunities",
                    "Clear investor communication",
                    "Brand-safe messaging",
                ],
                "stat_highlights": ["Trusted", "Curated", "Transparent"],
            },
        ),
    )


def test_renderer_builds_multiple_pages_for_carousel() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    pages = renderer._build_page_payloads(_payload("carousel"))
    assert len(pages) > 1
    assert pages[-1]["cta"] == "Learn more"


def test_renderer_builds_minimum_three_pages_for_short_carousel_copy() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    payload = _payload("carousel", preset="instagram", size={"width": 1080, "height": 1080})
    payload.text.body = "Inflation reduces purchasing power over time. Fixed-income products can help protect savings."

    pages = renderer._build_page_payloads(payload)

    assert len(pages) >= 3
    assert pages[0]["show_image"] is True
    assert pages[-1]["cta"] == "Learn more"


def test_renderer_scene_graph_renders_unlayered_overlay_footer_and_cta() -> None:
    renderer = RendererService.__new__(RendererService)
    payload = _payload("carousel", size={"width": 1080, "height": 1350})
    renderer.payload = payload
    renderer.settings = type("Settings", (), {"renderer_font_path": ""})()
    renderer._active_font_candidates = []
    renderer._used_font_paths = set()
    renderer._used_font_families = set()
    payload.scene_graph = GenerationSceneGraph(
        canvas=SceneGraphCanvas(width=1080, height=1350, platform="linkedin", file_type="png"),
        layout_mode="image_led_social",
        confidence=0.9,
        layers=["background", "headline_overlay", "body_text_overlay", "cta_overlay", "logo_overlay"],
        elements=[
            SceneGraphElement(
                element_id="background",
                element_type="background",
                role="background",
                layer="background",
                geometry=SceneGraphGeometry(x=0, y=0, width=1, height=1, units="normalized"),
                style={"primary_fill": "#F6F3ED"},
            ),
            SceneGraphElement(
                element_id="headline",
                element_type="text",
                role="headline",
                geometry=SceneGraphGeometry(x=0.06, y=0.08, width=0.72, height=0.12, units="normalized"),
                text="Why this matters now",
                style={"font_size": 56, "fill": "#003975"},
            ),
            SceneGraphElement(
                element_id="cta",
                element_type="text",
                role="cta",
                geometry=SceneGraphGeometry(x=0.06, y=0.82, width=0.56, height=0.06, units="normalized"),
                text="Explore bond options",
                style={"font_size": 24, "fill": "#FFFFFF", "background_fill": "#003975"},
            ),
            SceneGraphElement(
                element_id="legal_footer",
                element_type="text",
                role="legal",
                geometry=SceneGraphGeometry(x=0.03, y=0.94, width=0.94, height=0.05, units="normalized"),
                text="Jiraaf Platform Private Limited; SEBI Registration Number: INZ000315538",
                style={"font_size": 12, "fill": "#666666"},
            ),
        ],
    )

    _image, flags = renderer._render_scene_graph(payload, {"width": 1080, "height": 1350})
    rendered_roles = {str(item.get("role") or "") for item in flags.get("text_blocks_used", [])}

    assert "headline" in rendered_roles
    assert "cta" in rendered_roles
    assert "legal" in rendered_roles


def test_renderer_build_page_payloads_prefers_structured_carousel_slide_specs() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    payload = _payload("carousel", preset="instagram", size={"width": 1080, "height": 1080})
    payload.text.metadata["carousel_slide_specs"] = [
        {
            "role": "hook",
            "headline": "Why foreign flows matter",
            "supporting_line": "See the market signal before the crowd does.",
            "body": "Foreign inflows can shift bond-market confidence faster than most retail investors notice.",
            "proof_points": ["Track demand shifts"],
            "cta": "",
        },
        {
            "role": "proof",
            "headline": "A steadier path",
            "supporting_line": "Curated bonds can help diversify thoughtfully.",
            "body_points": ["Retail-friendly access", "Clearer investor context"],
            "proof_points": ["Retail-friendly access", "Clearer investor context"],
            "stat_highlights": ["Diversified", "Curated"],
            "cta": "Discover curated bonds on Jiraaf",
        },
    ]

    pages = renderer._build_page_payloads(payload)

    assert len(pages) == 2
    assert pages[0]["headline"] == "Why foreign flows matter"
    assert pages[0]["body"] == "Foreign inflows can shift bond-market confidence faster than most retail investors notice."
    assert pages[0]["supporting_line"] == "See the market signal before the crowd does."
    assert pages[1]["body"] == "Retail-friendly access. Clearer investor context"
    assert pages[1]["stat_highlights"] == ["Diversified", "Curated"]
    assert pages[1]["cta"] == "Discover curated bonds on Jiraaf"
    assert pages[0]["content_role"] == "hook"


def test_renderer_builds_single_page_for_static() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    pages = renderer._build_page_payloads(_payload("static"))
    assert len(pages) == 1
    assert pages[0]["headline"] == "A launch headline"


def test_renderer_condenses_social_body_copy() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    condensed = renderer._social_body_copy(
        "Sentence one is here. Sentence two is still useful. Sentence three should not survive into the on-canvas copy.",
        "linkedin",
    )
    assert "Sentence one is here." in condensed
    assert "Sentence two is still useful." in condensed
    assert "Sentence three should not survive" in condensed


def test_renderer_fit_text_block_prefers_smaller_font_before_truncating() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    image = Image.new("RGB", (420, 220), "white")
    draw = ImageDraw.Draw(image)

    font, lines, spacing, fit_meta = renderer._fit_text_block(
        draw=draw,
        text="Foreign investment trends can reshape fixed-income decisions with clearer market signals.",
        width=300,
        height=120,
        base_size=46,
        min_size=16,
        max_lines=3,
    )

    assert lines
    assert spacing >= 2
    assert int(fit_meta["font_size"]) < 46
    assert fit_meta["truncated"] is False


def test_renderer_font_accepts_weighted_requests() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]

    font = renderer._font(18, weight="bold")

    assert font is not None
    assert any("bold" in path.casefold() for path in renderer._used_font_paths)


def test_renderer_quality_assessment_flags_truncation_overlap_and_small_fonts() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    payload = _payload("static")

    assessment = renderer._assess_render_quality(
        payload=payload,
        render_flags=[
            {
                "template_rendered": False,
                "image_rendered": True,
                "logo_rendered": True,
                "image_assessments": [{"score": 0.7, "fit_mode": "cover"}],
                "text_fit": [{"font_size": 12, "truncated": True}],
                "overlap_checks": [{"role": "image", "passed": False}],
                "pre_shortening": {"body": {"shortened": True}},
                "text_blocks_used": [{"role": "body", "text": "Shortened..."}],
            }
        ],
        size={"width": 1080, "height": 1080},
        decorative_rendered=False,
    )

    assert assessment["text_truncation_count"] == 1
    assert assessment["failed_overlap_count"] == 1
    assert assessment["pre_shortened_block_count"] == 1
    assert "text_truncation_detected" in assessment["issues"]
    assert "text_visual_overlap_detected" in assessment["issues"]


def test_renderer_derives_supporting_badges_from_hashtags() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    badges = renderer._supporting_badges(_payload("static", preset="instagram", size={"width": 1080, "height": 1080}), "instagram")
    assert badges == ["Brand"]


def test_renderer_uses_designed_layout_for_instagram_static() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    payload = _payload("static", preset="instagram", size={"width": 1080, "height": 1080})
    image, flags = renderer._render_page(
        payload,
        {"width": 1080, "height": 1080},
        {"headline": payload.text.headline, "body": payload.text.body, "cta": payload.text.cta, "show_image": False},
    )
    assert image.size == (1080, 1080)
    assert flags["layout_variant"] == "instagram_editorial"
    assert flags["template_rendered"] is False
    assert flags["logo_rendered"] is True


def test_renderer_uses_insight_layout_for_linkedin_static() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    payload = _payload("static", preset="linkedin", size={"width": 1200, "height": 627})
    image, flags = renderer._render_page(
        payload,
        {"width": 1200, "height": 627},
        {"headline": payload.text.headline, "body": payload.text.body, "cta": payload.text.cta, "show_image": False},
    )
    assert image.size == (1200, 627)
    assert flags["layout_variant"] == "linkedin_insight_panel"
    assert flags["render_path"] == "social_page"
    assert flags["text_fit"]
    assert all(check["passed"] for check in flags["overlap_checks"])


def test_renderer_preserves_explicit_palette_roles() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    payload = _payload("static", preset="instagram", size={"width": 1080, "height": 1080})
    payload.brand_visual_rules = {
        "brand_color_palette": {"primary": "#003975", "secondary": "#F4C542", "accent": "#00CB91", "background": "#F8F2E6"},
        "palette_entries": [
            {"role": "secondary", "hex_code": "#00CB91", "color_name": "Caribbean Green"},
            {"role": "secondary", "hex_code": "#3D3DBE", "color_name": "Governor Bay"},
            {"role": "primary", "hex_code": "#003975", "color_name": "Regal Blue"},
            {"role": "accent", "hex_code": "#FFA400", "color_name": "Orange Peel"},
        ],
    }

    resolved = renderer._resolve_palette_roles(payload)

    assert resolved["primary"] == "#003975"
    assert resolved["secondary"] == "#F4C542"
    assert resolved["accent"] == "#00CB91"
    assert resolved["background"] == "#F8F2E6"


def test_renderer_uses_template_palette_as_fallback_evidence() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    payload = _payload("static", preset="instagram", size={"width": 1080, "height": 1080})
    payload.brand_visual_rules = {
        "template_intelligence": [
            {
                "analysis": {
                    "palette": [
                        {"role": "primary", "hex_code": "#F4C542", "color_name": "Golden Sand"},
                        {"role": "secondary", "hex_code": "#003975", "color_name": "Regal Blue"},
                        {"role": "background", "hex_code": "#F8F2E6", "color_name": "Warm Ivory"},
                    ]
                }
            }
        ]
    }

    resolved = renderer._resolve_palette_roles(payload)

    assert resolved["primary"] == "#F4C542"
    assert resolved["secondary"] == "#003975"
    assert resolved["background"] == "#F8F2E6"


def test_renderer_truncates_copy_on_word_boundary() -> None:
    assert RendererService._truncate_copy_at_word_boundary(
        "Ready to expand beyond traditional savings with curated fixed-income options",
        36,
    ) == "Ready to expand beyond..."


def test_renderer_supporting_line_preserves_word_boundaries() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    payload = _payload("static", preset="instagram", size={"width": 1080, "height": 1080})

    supporting = renderer._supporting_line(
        payload,
        "instagram",
        "Explore curated fixed-income opportunities that help investors build long-term confidence.",
    )

    assert not supporting.endswith("confiden")
    assert supporting.endswith("...") or supporting.endswith(".") or supporting == "Trusted market guidance for confident decisions"


def test_renderer_proof_points_preserve_word_boundaries() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    payload = _payload("infographic", preset="instagram", size={"width": 1080, "height": 1350})

    proof_points = renderer._proof_points(
        payload,
        "infographic",
        (
            "Fixed-income options can help stabilize your portfolio. "
            "They can also provide predictable cash flows for long-term planning. "
            "Diversification matters when navigating volatile markets."
        ),
    )

    assert proof_points
    assert all(not point.endswith("plannin") for point in proof_points)


def test_renderer_scene_graph_overlay_cleans_text_zone_on_base_canvas() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    base_canvas = Image.new("RGB", (1080, 1080), color=(24, 41, 89))
    renderer.storage = type("Storage", (), {"exists": lambda _self, path: path == "tenant/brand/generated/base.png"})()
    renderer._build_background_canvas = lambda width, height, background, gradient_spec, base_canvas_asset_path=None: base_canvas.copy()  # type: ignore[method-assign]
    payload = _payload("static", preset="instagram", size={"width": 1080, "height": 1080})
    renderer.payload = payload
    payload.base_canvas_asset_path = "tenant/brand/generated/base.png"
    payload.scene_graph = GenerationSceneGraph(
        canvas=SceneGraphCanvas(width=1080, height=1080, platform="instagram", file_type="png"),
        layout_mode="synthesized_layout",
        confidence=0.85,
        layers=["content"],
        elements=[
            SceneGraphElement(
                element_id="headline",
                element_type="text",
                role="headline",
                geometry=SceneGraphGeometry(x=0.1, y=0.1, width=0.42, height=0.2),
                text="Overlay headline",
                style={"font_size": 64, "background_fill": "#FFFFFF"},
            )
        ],
        assets=[],
        styles={},
        template_adaptation={},
        validation_hints={},
    )

    image, _flags = renderer._render_scene_graph(payload, {"width": 1080, "height": 1080})

    assert image.getpixel((520, 300)) != (24, 41, 89)
    assert image.getpixel((980, 980)) == (24, 41, 89)


def test_renderer_scene_graph_overlay_renders_without_preseeded_payload_state() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    base_canvas = Image.new("RGB", (1080, 1350), color=(24, 41, 89))
    renderer.storage = type("Storage", (), {"exists": lambda _self, path: path == "tenant/brand/generated/base.png"})()
    renderer._build_background_canvas = lambda width, height, background, gradient_spec, base_canvas_asset_path=None: base_canvas.copy()  # type: ignore[method-assign]
    payload = _payload("carousel", preset="linkedin", size={"width": 1080, "height": 1350})
    payload.base_canvas_asset_path = "tenant/brand/generated/base.png"
    payload.scene_graph = GenerationSceneGraph(
        canvas=SceneGraphCanvas(width=1080, height=1350, platform="linkedin", file_type="png"),
        layout_mode="synthesized_layout",
        confidence=0.85,
        layers=["content"],
        elements=[
            SceneGraphElement(
                element_id="headline",
                element_type="text",
                role="headline",
                geometry=SceneGraphGeometry(x=0.08, y=0.1, width=0.44, height=0.16),
                text="Overlay headline",
                style={"font_size": 56, "background_fill": "#FFFFFF"},
            )
        ],
        assets=[],
        styles={},
        template_adaptation={},
        validation_hints={},
    )

    image, flags = renderer._render_scene_graph(payload, {"width": 1080, "height": 1350})

    assert image.size == (1080, 1350)
    assert flags["text_fit"]
    assert renderer.payload is None


def test_renderer_ignores_off_palette_background_color_when_palette_is_available() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    payload = _payload("static", preset="instagram", size={"width": 1080, "height": 1080})
    payload.brand_visual_rules = {
        "background_color": "#6C63FF",
        "brand_color_palette": {"primary": "#003975", "secondary": "#FFA400", "accent": "#00CB91"},
    }

    palette = renderer._resolve_palette_roles(payload)
    primary = renderer._resolve_primary_color(palette)
    accent = renderer._resolve_accent_color(palette, primary)
    background = renderer._resolve_background_color(payload, palette, primary, accent)

    assert background != renderer._parse_color("#6C63FF", (0, 0, 0))


def test_renderer_scene_graph_color_supports_light_text_role() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    payload = _payload("static", preset="instagram", size={"width": 1080, "height": 1080})

    resolved = renderer._scene_graph_color(
        payload,
        {"fill_role": "light_text"},
        "fill",
        (12, 34, 56),
        {"primary": "#003975"},
    )

    assert resolved == (255, 255, 255)


def test_renderer_resolves_missing_scene_asset_path_from_payload_image_assets() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    renderer.storage = type(
        "Storage",
        (),
        {
            "exists": lambda _self, path: path == "tenant/brand/generated/fallback-hero.png",
        },
    )()
    payload = _payload("static", preset="instagram", size={"width": 1080, "height": 1080})
    payload.scene_graph = GenerationSceneGraph(
        canvas=SceneGraphCanvas(width=1080, height=1080, platform="instagram", file_type="png"),
        layout_mode="synthesized_layout",
        confidence=0.8,
        layers=["content"],
        elements=[
            SceneGraphElement(
                element_id="hero_image",
                element_type="image",
                role="image",
                geometry=SceneGraphGeometry(x=0.5, y=0.1, width=0.3, height=0.4),
                asset={"asset_role": "ai_image", "storage_path": "tenant/brand/reference/stale.png"},
            )
        ],
        assets=[],
        styles={},
        template_adaptation={},
        validation_hints={},
    )
    payload.image_assets = [
        GeneratedImageAsset(
            asset_id=uuid4(),
            mime_type="image/png",
            storage_path="tenant/brand/generated/fallback-hero.png",
            width=1080,
            height=1080,
            asset_role="ai_image",
        )
    ]

    resolved = renderer._resolve_scene_asset_path(payload, payload.scene_graph.elements[0])

    assert resolved == "tenant/brand/generated/fallback-hero.png"


def test_renderer_uses_base_canvas_for_scene_graph_overlay_without_repasting_visual_assets() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    base_canvas = Image.new("RGB", (1080, 1080), color=(12, 34, 56))
    renderer.storage = type("Storage", (), {})()
    renderer._build_background_canvas = lambda width, height, background, gradient_spec, base_canvas_asset_path=None: base_canvas.copy()  # type: ignore[method-assign]
    payload = _payload("static", preset="instagram", size={"width": 1080, "height": 1080})
    renderer.payload = payload
    payload.base_canvas_asset_path = "tenant/brand/generated/base.png"
    payload.scene_graph = GenerationSceneGraph(
        canvas=SceneGraphCanvas(width=1080, height=1080, platform="instagram", file_type="png"),
        layout_mode="synthesized_layout",
        confidence=0.85,
        layers=["background", "primary_visual", "content"],
        elements=[
            SceneGraphElement(
                element_id="hero_image",
                element_type="image",
                role="image",
                geometry=SceneGraphGeometry(x=0.55, y=0.12, width=0.3, height=0.4),
                asset={"storage_path": "tenant/brand/generated/visual.png", "asset_role": "ai_image"},
            ),
            SceneGraphElement(
                element_id="headline",
                element_type="text",
                role="headline",
                geometry=SceneGraphGeometry(x=0.08, y=0.1, width=0.4, height=0.16),
                text="Overlay headline",
                style={"font_size": 64, "fill_role": "light_text"},
            ),
        ],
        assets=[],
        styles={},
        template_adaptation={},
        validation_hints={},
    )

    image, flags = renderer._render_scene_graph(payload, {"width": 1080, "height": 1080})
    assert image.size == (1080, 1080)
    assert image.convert("RGB").getpixel((980, 980)) == (12, 34, 56)
    assert flags["image_rendered"] is True
    assert flags["image_assessments"] == []


def test_renderer_visual_fit_uses_contain_for_extreme_aspect_mismatch() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]

    assessment = renderer._assess_visual_fit(
        source_width=1600,
        source_height=600,
        target_width=420,
        target_height=920,
    )

    assert assessment["fit_mode"] == "contain"
    assert float(assessment["score"]) < 0.56


def test_renderer_quality_assessment_flags_low_fit_image_risk() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    payload = _payload("static", preset="instagram", size={"width": 1080, "height": 1080})

    assessment = renderer._assess_render_quality(
        payload=payload,
        render_flags=[
            {
                "template_rendered": False,
                "image_rendered": True,
                "logo_rendered": True,
                "decorative_rendered": False,
                "layout_variant": "scene_graph_checklist_corner_card",
                "image_assessments": [{"fit_mode": "contain", "score": 0.41}],
            }
        ],
        size={"width": 1080, "height": 1080},
        decorative_rendered=False,
    )

    assert assessment["image_fit_score"] == 0.41
    assert "image_crop_risk" in assessment["issues"]


def test_renderer_does_not_flag_style_reference_template_as_missing_template_application() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    payload = _payload("static", preset="instagram", size={"width": 1080, "height": 1080})
    payload.blueprint.source_mode = "adapted_template"
    payload.blueprint.source_template_id = "tpl_pdf_001"
    payload.scene_graph = GenerationSceneGraph(
        canvas=SceneGraphCanvas(width=1080, height=1080, platform="instagram", file_type="png"),
        layout_mode="adapted_template",
        confidence=0.82,
        layers=["background", "primary_visual", "content", "brand"],
        validation_hints={"template_surface_policy": "style_reference_only"},
        elements=[],
    )
    payload.creative_decision = {
        "layout_mode": "adapted_template",
        "asset_strategy": {"template_surface_policy": "style_reference_only"},
    }

    assessment = renderer._assess_render_quality(
        payload=payload,
        render_flags=[
            {
                "template_rendered": False,
                "image_rendered": True,
                "logo_rendered": True,
                "layout_variant": "scene_graph_hero_overlay",
            }
        ],
        size={"width": 1080, "height": 1080},
        decorative_rendered=False,
    )

    assert "template_adaptation_missing" not in assessment["issues"]
    assert "review_recommended" not in assessment["issues"]


def test_renderer_does_not_draw_synthetic_lockup_when_real_logo_is_expected_but_missing() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    payload = _payload("static", preset="instagram", size={"width": 1080, "height": 1080})
    payload.brand_visual_rules = {"identity": {"logo_asset_id": str(uuid4())}}

    image, flags = renderer._render_page(
        payload,
        {"width": 1080, "height": 1080},
        {"headline": payload.text.headline, "body": payload.text.body, "cta": payload.text.cta, "show_image": False},
    )

    assert image.size == (1080, 1080)
    assert flags["logo_rendered"] is False


def test_renderer_paste_logo_strips_light_background_before_compositing() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    root = Path("tests") / f"logo-strip-{uuid4()}"
    root.mkdir(parents=True, exist_ok=True)
    logo_path = root / "logo.png"
    logo = Image.new("RGBA", (240, 120), (255, 255, 255, 255))
    logo_draw = ImageDraw.Draw(logo)
    logo_draw.rounded_rectangle((60, 24, 180, 96), radius=18, fill=(0, 57, 117, 255))
    logo.save(logo_path)

    class Storage:
        def absolute_path(self, path: str) -> str:
            return str(logo_path)

    renderer.storage = Storage()
    canvas = Image.new("RGBA", (240, 140), (18, 28, 38, 255))
    zone = type("Zone", (), {"x": 20, "y": 30, "width": 120, "height": 60})()

    try:
        pasted = renderer._paste_logo(canvas, "tenant/brand/logo/logo.png", zone)
        assert pasted is True
        assert canvas.getpixel((32, 60))[:3] == (0, 57, 117)
    finally:
        logo_path.unlink(missing_ok=True)
        root.rmdir()


def test_renderer_builds_single_page_for_infographic() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    payload = _payload("infographic", preset="instagram", size={"width": 1080, "height": 1920})
    payload.text.metadata["infographic_section_specs"] = [
        {"section_number": 1, "section_role": "overview", "headline": "Why this matters", "proof_points": ["Purchasing power slips"]},
        {"section_number": 2, "section_role": "evidence", "headline": "Key numbers", "stat_highlights": ["26% market share"]},
    ]
    pages = renderer._build_page_payloads(payload)
    assert len(pages) == 1
    assert pages[0]["show_image"] is True
    assert len(pages[0]["infographic_section_specs"]) == 2


def test_renderer_uses_infographic_layout() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    payload = _payload("infographic", preset="instagram", size={"width": 1080, "height": 1920})
    image, flags = renderer._render_page(
        payload,
        {"width": 1080, "height": 1920},
        {"headline": payload.text.headline, "body": payload.text.body, "cta": payload.text.cta, "show_image": False},
    )
    assert image.size == (1080, 1920)
    assert flags["layout_variant"] == "infographic_storyboard"


def test_renderer_includes_static_panel_spec_in_page_payload() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    payload = _payload("static", preset="linkedin", size={"width": 1200, "height": 627})
    payload.text.metadata["static_panel_spec"] = {
        "panel_goal": "single_dominant_message",
        "dominant_message": "Clarity beats generic fixed-income messaging.",
        "supporting_lines": ["Use one core idea and two support lines."],
    }
    pages = renderer._build_page_payloads(payload)
    assert pages[0]["static_panel_spec"]["panel_goal"] == "single_dominant_message"
    assert pages[0]["static_panel_spec"]["dominant_message"] == "Clarity beats generic fixed-income messaging."


def test_renderer_resolves_pdf_template_background_from_ocr_page_images() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    root = Path("tests") / f"template-bg-{uuid4()}"
    page_images = root / "_ocr" / "page_images"
    page_images.mkdir(parents=True, exist_ok=True)
    pdf_path = root / "template.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    image_path = page_images / "page_1.png"
    Image.new("RGB", (400, 400), color=(240, 245, 255)).save(image_path)

    renderer.storage = type("Storage", (), {"absolute_path": lambda _self, path: str(pdf_path)})()
    try:
        resolved = renderer._resolve_template_background_source("tenant/brand/templates/template.pdf")
        assert resolved == image_path
    finally:
        image_path.unlink(missing_ok=True)
        pdf_path.unlink(missing_ok=True)
        page_images.rmdir()
        (root / "_ocr").rmdir()
        root.rmdir()


def test_renderer_preserves_template_background_without_overlaying_generated_visuals_or_logo() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    root = Path("tests") / f"template-render-{uuid4()}"
    root.mkdir(parents=True, exist_ok=True)
    template_path = root / "template.png"
    generated_path = root / "generated.png"
    logo_path = root / "logo.png"
    Image.new("RGB", (1080, 1080), color=(210, 235, 255)).save(template_path)
    Image.new("RGB", (300, 300), color=(255, 180, 50)).save(generated_path)
    Image.new("RGBA", (220, 80), color=(0, 75, 155, 255)).save(logo_path)

    class Storage:
        def absolute_path(self, path: str) -> str:
            mapping = {
                "tenant/brand/templates/template.png": str(template_path),
                "tenant/brand/generated/generated.png": str(generated_path),
                "tenant/brand/logo/logo.png": str(logo_path),
            }
            return mapping[path]

    renderer.storage = Storage()
    payload = RendererInput(
        tenant_id="11111111-1111-1111-1111-111111111111",
        brand_space_id="22222222-2222-2222-2222-222222222222",
        content_version_id="33333333-3333-3333-3333-333333333333",
        studio_panel={"format": "static", "platform_preset": "instagram", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        blueprint=BlueprintPayload(
            layout_type="static",
            zones=[
                BlueprintZone(zone_id="logo", role="logo", x=820, y=42, width=200, height=72, max_lines=1),
                BlueprintZone(zone_id="headline", role="headline", x=64, y=74, width=640, height=156, max_lines=3),
                BlueprintZone(zone_id="body", role="body", x=64, y=250, width=640, height=180, max_lines=5),
                BlueprintZone(zone_id="image", role="image", x=64, y=452, width=952, height=420, max_lines=None),
                BlueprintZone(zone_id="cta", role="cta", x=64, y=910, width=320, height=96, max_lines=2),
            ],
            hierarchy=["headline", "body", "cta", "logo"],
            text_blocks=[],
            image_zones=[{"role": "primary_visual", "zone_id": "image", "required": False}],
            logo_rules={"zone_id": "logo", "required": True},
            cta_placement={"alignment": "left"},
            platform_preset="instagram",
            export_format="png",
            overflow_strategy={"mode": "shrink_then_wrap"},
            source_mode="exact_template",
            source_template_id="template-1",
            adaptation_plan={},
            brand_rules_applied={},
        ),
        text=StructuredTextPayload(
            headline="Flight Bookings on a Budget",
            body="Compare prices, book early, use flexible dates, and watch fare alerts.",
            cta="Travel Smarter",
            hashtags=["#Travel"],
            metadata={},
        ),
        template_asset_path="tenant/brand/templates/template.png",
        logo_asset_path="tenant/brand/logo/logo.png",
        image_assets=[
            {
                "asset_id": uuid4(),
                "mime_type": "image/png",
                "storage_path": "tenant/brand/generated/generated.png",
                "width": 300,
                "height": 300,
                "asset_role": "ai_image",
            }
        ],
        brand_visual_rules={"brand_color_palette": {"primary": "#0B4D9A", "secondary": "#F5A623"}},
        layout_decision={"adaptation_plan": {}},
    )

    try:
        image, flags = renderer._render_page(
            payload,
            {"width": 1080, "height": 1080},
            {"headline": payload.text.headline, "body": payload.text.body, "cta": payload.text.cta, "show_image": True},
        )
        assert image.size == (1080, 1080)
        assert flags["template_rendered"] is True
        assert flags["image_rendered"] is False
        assert flags["logo_rendered"] is False
        cta_background_sample = image.convert("RGB").getpixel((340, 980))
        assert cta_background_sample != (11, 77, 154)
    finally:
        template_path.unlink(missing_ok=True)
        generated_path.unlink(missing_ok=True)
        logo_path.unlink(missing_ok=True)
        root.rmdir()


def test_renderer_does_not_paste_template_background_for_style_reference_only_adapted_templates() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    root = Path("tests") / f"template-style-only-{uuid4()}"
    root.mkdir(parents=True, exist_ok=True)
    template_path = root / "template.png"
    Image.new("RGB", (1080, 1080), color=(240, 120, 40)).save(template_path)

    class Storage:
        def absolute_path(self, path: str) -> str:
            return {"tenant/brand/templates/template.png": str(template_path)}[path]

    renderer.storage = Storage()
    payload = _payload("static", preset="instagram", size={"width": 1080, "height": 1080})
    payload.blueprint.source_mode = "adapted_template"
    payload.blueprint.source_template_id = "template-1"
    payload.template_asset_path = "tenant/brand/templates/template.png"
    payload.scene_graph = GenerationSceneGraph(
        canvas=SceneGraphCanvas(width=1080, height=1080, platform="instagram", file_type="png"),
        layout_mode="adapted_template",
        confidence=0.82,
        layers=["background", "content"],
        validation_hints={"template_surface_policy": "style_reference_only"},
        elements=[],
    )
    payload.creative_decision = {
        "layout_mode": "adapted_template",
        "asset_strategy": {"template_surface_policy": "style_reference_only"},
    }

    try:
        image, flags = renderer._render_page(
            payload,
            {"width": 1080, "height": 1080},
            {"headline": payload.text.headline, "body": payload.text.body, "cta": payload.text.cta, "show_image": False},
        )
        assert image.size == (1080, 1080)
        assert flags["template_rendered"] is False
        assert image.convert("RGB").getpixel((20, 20)) != (240, 120, 40)
    finally:
        template_path.unlink(missing_ok=True)
        root.rmdir()


@pytest.mark.asyncio
async def test_renderer_render_records_quality_and_uses_brand_tinted_background_for_synthesized_layout() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    root = Path("tests") / f"render-quality-{uuid4()}"
    generated_dir = root / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    class Storage:
        def save_bytes(self, tenant_id, brand_space_id, category, filename, content):
            target_dir = root / category
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / filename
            target.write_bytes(content)
            return type("Stored", (), {"storage_path": str(target.relative_to(root)).replace("\\", "/")})()

        def absolute_path(self, path: str) -> str:
            return str(root / Path(path))

    renderer.storage = Storage()
    payload = RendererInput(
        tenant_id="11111111-1111-1111-1111-111111111111",
        brand_space_id="22222222-2222-2222-2222-222222222222",
        content_version_id="33333333-3333-3333-3333-333333333333",
        studio_panel={"format": "static", "platform_preset": "instagram", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        blueprint=BlueprintPayload(
            layout_type="static",
            zones=[
                BlueprintZone(zone_id="headline", role="headline", x=0, y=0, width=100, height=100, max_lines=3),
                BlueprintZone(zone_id="body", role="body", x=0, y=100, width=100, height=100, max_lines=5),
                BlueprintZone(zone_id="cta", role="cta", x=0, y=200, width=100, height=50, max_lines=2),
            ],
            hierarchy=["headline", "body", "cta"],
            text_blocks=[],
            image_zones=[],
            logo_rules={},
            cta_placement={"alignment": "left"},
            platform_preset="instagram",
            export_format="png",
            overflow_strategy={"mode": "shrink_then_wrap"},
            source_mode="synthesized_layout",
            layout_archetype="checklist_card",
            composition_plan={
                "background_plan": {"policy": "brand_gradient"},
                "decorative_plan": {"policy": "none", "max_assets": 0},
                "primary_visual_plan": {"policy": "optional_generated", "show_primary_visual_on_first_page_only": True},
                "text_content_plan": {"show_primary_visual": True},
                "layout_plan": {"layout_archetype": "checklist_card"},
            },
        ),
        text=StructuredTextPayload(
            headline="Book Flights Smarter",
            body="Compare fares, travel midweek, set alerts, and stay flexible.",
            cta="Travel smarter",
            hashtags=["#Travel"],
            metadata={
                "section_label": "Travel Tips",
                "supporting_line": "Simple strategies for lower fares.",
                "proof_points": ["Compare multiple sites", "Set fare alerts", "Use flexible dates"],
                "stat_highlights": ["Budget-friendly", "Smart timing"],
            },
        ),
        brand_visual_rules={"brand_color_palette": {"primary": "#0B4D9A", "secondary": "#F5A623"}},
    )

    response = await renderer.render(payload)

    preview_path = root / Path(response.preview_asset["storage_path"])
    assert preview_path.exists()
    with Image.open(preview_path) as preview:
        top_left = preview.convert("RGB").getpixel((12, 12))
    assert top_left != (247, 244, 236)
    assert response.renderer_metadata["quality_assessment"]["overall_score"] > 0
    assert response.renderer_metadata["latency_ms"]["render_total_ms"] >= 0

    for file in root.rglob("*"):
        if file.is_file():
            file.unlink()
    for directory in sorted([path for path in root.rglob("*") if path.is_dir()], reverse=True):
        directory.rmdir()
    root.rmdir()


@pytest.mark.asyncio
async def test_renderer_prefers_scene_graph_when_present() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    root = Path("tests") / f"scene-graph-render-{uuid4()}"
    root.mkdir(parents=True, exist_ok=True)

    class Storage:
        def save_bytes(self, tenant_id, brand_space_id, category, filename, content):
            target_dir = root / category
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / filename
            target.write_bytes(content)
            return type("Stored", (), {"storage_path": str(target.relative_to(root)).replace("\\", "/")})()

        def absolute_path(self, path: str) -> str:
            return str(root / Path(path))

    renderer.storage = Storage()
    payload = RendererInput(
        tenant_id="11111111-1111-1111-1111-111111111111",
        brand_space_id="22222222-2222-2222-2222-222222222222",
        content_version_id="33333333-3333-3333-3333-333333333333",
        studio_panel={"format": "static", "platform_preset": "instagram", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        blueprint=BlueprintPayload(
            layout_type="static",
            zones=[BlueprintZone(zone_id="headline", role="headline", x=0, y=0, width=100, height=100, max_lines=3)],
            hierarchy=["headline"],
            text_blocks=[],
            image_zones=[],
            logo_rules={},
            cta_placement={"alignment": "left"},
            platform_preset="instagram",
            export_format="png",
            overflow_strategy={"mode": "shrink_then_wrap"},
            source_mode="synthesized_layout",
        ),
        scene_graph=GenerationSceneGraph(
            canvas=SceneGraphCanvas(width=1080, height=1080, platform="instagram", file_type="png"),
            layout_mode="synthesized_layout",
            confidence=0.82,
            layers=["background", "content", "brand"],
            elements=[
                SceneGraphElement(
                    element_id="background",
                    element_type="background",
                    role="background",
                    layer="background",
                    geometry=SceneGraphGeometry(x=0, y=0, width=1, height=1, units="normalized"),
                    style={"primary_fill": "#EEF6FF", "gradient_to": "#0B4D9A"},
                ),
                SceneGraphElement(
                    element_id="headline",
                    element_type="text",
                    role="headline",
                    layer="content",
                    geometry=SceneGraphGeometry(x=0.08, y=0.12, width=0.72, height=0.16, units="normalized"),
                    text="Scene graph headline",
                    style={"font_size": 52, "fill_role": "primary", "max_lines": 3},
                ),
                SceneGraphElement(
                    element_id="cta",
                    element_type="text",
                    role="cta",
                    layer="brand",
                    geometry=SceneGraphGeometry(x=0.08, y=0.8, width=0.32, height=0.09, units="normalized"),
                    text="Act now",
                    style={"font_size": 22, "fill_role": "light_text", "background_fill_role": "primary", "max_lines": 2},
                ),
            ],
            styles={"layout_archetype": "editorial_hero"},
        ),
        text=StructuredTextPayload(
            headline="Blueprint headline should not win",
            body="Body copy",
            cta="Learn more",
            hashtags=["#brand"],
            metadata={},
        ),
        brand_visual_rules={"brand_color_palette": {"primary": "#0B4D9A", "secondary": "#F5A623", "background": "#EEF6FF"}},
        creative_decision={"layout_mode": "synthesized_layout"},
    )

    response = await renderer.render(payload)

    assert response.renderer_metadata["layout_variant"].startswith("scene_graph_")
    preview_path = root / Path(response.preview_asset["storage_path"])
    assert preview_path.exists()

    for file in root.rglob("*"):
        if file.is_file():
            file.unlink()
    for directory in sorted([path for path in root.rglob("*") if path.is_dir()], reverse=True):
        directory.rmdir()
    root.rmdir()


@pytest.mark.asyncio
async def test_renderer_scene_graph_repositions_logo_away_from_text_bounds() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    root = Path("tests") / f"scene-graph-logo-clearance-{uuid4()}"
    root.mkdir(parents=True, exist_ok=True)

    logo = Image.new("RGBA", (360, 120), (0, 0, 0, 0))
    logo_draw = ImageDraw.Draw(logo)
    logo_draw.rounded_rectangle((0, 0, 359, 119), radius=18, fill="#003975")
    logo_draw.text((36, 34), "Jiraaf", fill="white")
    logo_buffer = BytesIO()
    logo.save(logo_buffer, format="PNG")

    class Storage:
        def save_bytes(self, tenant_id, brand_space_id, category, filename, content):
            target_dir = root / category
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / filename
            target.write_bytes(content)
            return type("Stored", (), {"storage_path": str(target.relative_to(root)).replace("\\", "/")})()

        def absolute_path(self, path: str) -> str:
            return str(root / Path(path))

        def exists(self, path: str) -> bool:
            return (root / Path(path)).exists()

    renderer.storage = Storage()
    logo_path = renderer.storage.save_bytes("tenant", "brand", "logo", "logo.png", logo_buffer.getvalue()).storage_path
    payload = _payload("static", preset="instagram", size={"width": 1080, "height": 1080})
    payload.logo_asset_path = logo_path
    payload.scene_graph = GenerationSceneGraph(
        canvas=SceneGraphCanvas(width=1080, height=1080, platform="instagram", file_type="png"),
        layout_mode="synthesized_layout",
        confidence=0.9,
        layers=["background", "content", "brand"],
        elements=[
            SceneGraphElement(
                element_id="background",
                element_type="background",
                role="background",
                layer="background",
                geometry=SceneGraphGeometry(x=0, y=0, width=1, height=1, units="normalized"),
                style={"primary_fill": "#EEF6FF"},
            ),
            SceneGraphElement(
                element_id="headline",
                element_type="text",
                role="headline",
                layer="content",
                geometry=SceneGraphGeometry(x=0.08, y=0.08, width=0.7, height=0.24, units="normalized"),
                text="Foreign investment trends can drive better fixed-income choices for retail investors.",
                style={"font_size": 58, "fill_role": "primary", "max_lines": 4},
            ),
            SceneGraphElement(
                element_id="logo",
                element_type="logo",
                role="logo",
                layer="brand",
                geometry=SceneGraphGeometry(x=0.62, y=0.08, width=0.26, height=0.1, units="normalized"),
            ),
        ],
        styles={"layout_archetype": "editorial_hero"},
    )

    response = await renderer.render(payload)

    assert response.renderer_metadata["render_path"] == "scene_graph_direct"
    overlap_checks = response.renderer_metadata["render_manifest"]["overlap_checks"]
    assert any(check["role"] == "logo" and check["passed"] for check in overlap_checks)
    logo_boxes = [
        item["box"]
        for item in response.renderer_metadata["render_manifest"]["asset_boxes"]
        if item["role"] == "logo"
    ]
    assert logo_boxes

    for file in root.rglob("*"):
        if file.is_file():
            file.unlink()
    for directory in sorted([path for path in root.rglob("*") if path.is_dir()], reverse=True):
        directory.rmdir()
    root.rmdir()


def test_renderer_scene_graph_anchor_places_logo_zone_near_frame_edge() -> None:
    element = SceneGraphElement(
        element_id="logo",
        element_type="logo",
        role="logo",
        layer="brand",
        geometry=SceneGraphGeometry(
            width=0.2,
            height=0.08,
            units="normalized",
            anchor="top-right",
        ),
    )

    box = RendererService._scene_graph_box(element, 1080, 1080)

    assert box == (877, 20, 1060, 101)


def test_renderer_scene_graph_explicit_logo_box_snaps_to_20px_edge() -> None:
    element = SceneGraphElement(
        element_id="logo",
        element_type="logo",
        role="logo",
        layer="brand",
        geometry=SceneGraphGeometry(
            x=0.08,
            y=0.09,
            width=0.2,
            height=0.08,
            units="normalized",
            anchor="top-left",
        ),
    )

    box = RendererService._scene_graph_box(element, 1024, 1536)

    assert box == (20, 20, 194, 135)


def test_renderer_logo_offset_in_zone_aligns_to_bottom_edge() -> None:
    offset = RendererService._logo_offset_in_zone(
        canvas_width=1080,
        canvas_height=1080,
        zone_x=800,
        zone_y=900,
        zone_width=200,
        zone_height=100,
        logo_width=120,
        logo_height=40,
    )

    assert offset == (880, 960)


def test_renderer_trim_logo_margins_crops_opaque_logo_canvas_to_visible_mark() -> None:
    logo = Image.new("RGBA", (1536, 1024), (250, 250, 250, 255))
    draw = ImageDraw.Draw(logo)
    draw.rectangle((292, 324, 420, 615), fill=(247, 153, 0, 255))
    draw.rectangle((460, 324, 1292, 615), fill=(0, 57, 117, 255))

    trimmed = RendererService._trim_transparent_logo_margins(logo)

    assert trimmed.size == (1001, 292)
    assert trimmed.getchannel("A").getbbox() == (0, 0, 1001, 292)


@pytest.mark.asyncio
async def test_renderer_scene_graph_carousel_uses_paginated_render_path() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    root = Path("tests") / f"scene-graph-carousel-{uuid4()}"
    root.mkdir(parents=True, exist_ok=True)

    class Storage:
        def save_bytes(self, tenant_id, brand_space_id, category, filename, content):
            target_dir = root / category
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / filename
            target.write_bytes(content)
            return type("Stored", (), {"storage_path": str(target.relative_to(root)).replace("\\", "/")})()

        def absolute_path(self, path: str) -> str:
            return str(root / Path(path))

    renderer.storage = Storage()
    payload = _payload("carousel", preset="instagram", size={"width": 1080, "height": 1350})
    payload.scene_graph = GenerationSceneGraph(
        canvas=SceneGraphCanvas(width=1080, height=1350, platform="instagram", file_type="png"),
        layout_mode="synthesized_layout",
        confidence=0.84,
        layers=["background", "content", "brand"],
        elements=[
            SceneGraphElement(
                element_id="background",
                element_type="background",
                role="background",
                layer="background",
                geometry=SceneGraphGeometry(x=0, y=0, width=1, height=1, units="normalized"),
                style={"primary_fill": "#EEF6FF"},
            ),
            SceneGraphElement(
                element_id="headline",
                element_type="text",
                role="headline",
                layer="content",
                geometry=SceneGraphGeometry(x=0.08, y=0.12, width=0.7, height=0.16, units="normalized"),
                text="Scene graph carousel headline",
                style={"font_size": 52, "fill_role": "primary", "max_lines": 3},
            ),
        ],
        styles={"layout_archetype": "hero_overlay", "layout_type": "carousel"},
    )

    response = await renderer.render(payload)

    assert response.renderer_metadata["page_count"] > 1
    assert response.renderer_metadata["layout_variant"] == "instagram_editorial"
    assert not response.renderer_metadata["layout_variant"].startswith("scene_graph_")
    assert len(response.export_assets) > 1

    for file in root.rglob("*"):
        if file.is_file():
            file.unlink()
    for directory in sorted([path for path in root.rglob("*") if path.is_dir()], reverse=True):
        directory.rmdir()
    root.rmdir()


@pytest.mark.asyncio
async def test_renderer_single_page_structured_export_uses_export_filename() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    root = Path("tests") / f"structured-export-{uuid4()}"
    root.mkdir(parents=True, exist_ok=True)

    class Storage:
        def save_bytes(self, tenant_id, brand_space_id, category, filename, content):
            target_dir = root / category
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / filename
            target.write_bytes(content)
            return type("Stored", (), {"storage_path": str(target.relative_to(root)).replace("\\", "/")})()

        def absolute_path(self, path: str) -> str:
            return str(root / Path(path))

    renderer.storage = Storage()
    payload = _payload("infographic", preset="instagram", size={"width": 1080, "height": 1080})

    response = await renderer.render(payload)

    assert response.preview_asset["storage_path"].endswith(".png")
    assert "preview-" in response.preview_asset["storage_path"]
    assert len(response.export_assets) == 1
    assert response.export_assets[0]["asset_role"] == "render_export"
    assert "export-" in response.export_assets[0]["storage_path"]
    assert response.export_assets[0]["storage_path"] != response.preview_asset["storage_path"]

    for file in root.rglob("*"):
        if file.is_file():
            file.unlink()
    for directory in sorted([path for path in root.rglob("*") if path.is_dir()], reverse=True):
        directory.rmdir()
    root.rmdir()


@pytest.mark.asyncio
async def test_renderer_scene_graph_infographic_uses_infographic_render_path() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    root = Path("tests") / f"scene-graph-infographic-{uuid4()}"
    root.mkdir(parents=True, exist_ok=True)

    class Storage:
        def save_bytes(self, tenant_id, brand_space_id, category, filename, content):
            target_dir = root / category
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / filename
            target.write_bytes(content)
            return type("Stored", (), {"storage_path": str(target.relative_to(root)).replace("\\", "/")})()

        def absolute_path(self, path: str) -> str:
            return str(root / Path(path))

    renderer.storage = Storage()
    payload = _payload("infographic", preset="instagram", size={"width": 1080, "height": 1920})
    payload.scene_graph = GenerationSceneGraph(
        canvas=SceneGraphCanvas(width=1080, height=1920, platform="instagram", file_type="png"),
        layout_mode="synthesized_layout",
        confidence=0.84,
        layers=["background", "content", "brand"],
        elements=[
            SceneGraphElement(
                element_id="background",
                element_type="background",
                role="background",
                layer="background",
                geometry=SceneGraphGeometry(x=0, y=0, width=1, height=1, units="normalized"),
                style={"primary_fill": "#EEF6FF"},
            ),
            SceneGraphElement(
                element_id="headline",
                element_type="text",
                role="headline",
                layer="content",
                geometry=SceneGraphGeometry(x=0.08, y=0.08, width=0.7, height=0.12, units="normalized"),
                text="Scene graph infographic headline",
                style={"font_size": 54, "fill_role": "primary", "max_lines": 3},
            ),
        ],
        styles={"layout_archetype": "hero_overlay", "layout_type": "infographic"},
    )

    response = await renderer.render(payload)

    assert response.renderer_metadata["page_count"] == 1
    assert response.renderer_metadata["layout_variant"] == "infographic_storyboard"
    assert not response.renderer_metadata["layout_variant"].startswith("scene_graph_")

    for file in root.rglob("*"):
        if file.is_file():
            file.unlink()
    for directory in sorted([path for path in root.rglob("*") if path.is_dir()], reverse=True):
        directory.rmdir()
    root.rmdir()


@pytest.mark.asyncio
async def test_renderer_scene_graph_pdf_uses_paginated_pdf_render_path() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    root = Path("tests") / f"scene-graph-pdf-{uuid4()}"
    root.mkdir(parents=True, exist_ok=True)

    class Storage:
        def save_bytes(self, tenant_id, brand_space_id, category, filename, content):
            target_dir = root / category
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / filename
            target.write_bytes(content)
            return type("Stored", (), {"storage_path": str(target.relative_to(root)).replace("\\", "/")})()

        def absolute_path(self, path: str) -> str:
            return str(root / Path(path))

    renderer.storage = Storage()
    payload = _payload("pdf", preset="linkedin", size={"width": 1240, "height": 1754})
    payload.studio_panel["file_type"] = "pdf"
    payload.blueprint.export_format = "pdf"
    payload.text.body = " ".join(
        [
            "A document-style render should paginate deliberately and keep each page readable."
            for _ in range(20)
        ]
    )
    payload.scene_graph = GenerationSceneGraph(
        canvas=SceneGraphCanvas(width=1240, height=1754, platform="linkedin", file_type="pdf"),
        layout_mode="synthesized_layout",
        confidence=0.84,
        layers=["background", "content", "brand"],
        elements=[
            SceneGraphElement(
                element_id="background",
                element_type="background",
                role="background",
                layer="background",
                geometry=SceneGraphGeometry(x=0, y=0, width=1, height=1, units="normalized"),
                style={"primary_fill": "#EEF6FF"},
            ),
            SceneGraphElement(
                element_id="headline",
                element_type="text",
                role="headline",
                layer="content",
                geometry=SceneGraphGeometry(x=0.08, y=0.08, width=0.7, height=0.12, units="normalized"),
                text="Scene graph PDF headline",
                style={"font_size": 54, "fill_role": "primary", "max_lines": 3},
            ),
        ],
        styles={"layout_archetype": "hero_overlay", "layout_type": "pdf"},
    )

    response = await renderer.render(payload)

    assert response.renderer_metadata["page_count"] > 1
    assert response.renderer_metadata["layout_variant"] == "linkedin_insight_panel"
    assert not response.renderer_metadata["layout_variant"].startswith("scene_graph_")
    assert response.export_assets[0]["mime_type"] == "application/pdf"

    for file in root.rglob("*"):
        if file.is_file():
            file.unlink()
    for directory in sorted([path for path in root.rglob("*") if path.is_dir()], reverse=True):
        directory.rmdir()
    root.rmdir()


@pytest.mark.asyncio
async def test_renderer_scene_graph_image_led_layout_paints_primary_visual_into_preview() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    root = Path("tests") / f"scene-graph-image-led-{uuid4()}"
    root.mkdir(parents=True, exist_ok=True)

    hero = Image.new("RGB", (1080, 1080), "#3355AA")
    hero_draw = ImageDraw.Draw(hero)
    hero_draw.rectangle((520, 0, 1080, 1080), fill="#F4B126")
    hero_draw.ellipse((600, 140, 980, 520), fill="#00CB91")
    hero_buffer = BytesIO()
    hero.save(hero_buffer, format="PNG")

    logo = Image.new("RGBA", (360, 110), (0, 0, 0, 0))
    logo_draw = ImageDraw.Draw(logo)
    logo_draw.rounded_rectangle((0, 0, 359, 109), radius=18, fill="#003975")
    logo_draw.text((38, 30), "Jiraaf", fill="white")
    logo_buffer = BytesIO()
    logo.save(logo_buffer, format="PNG")

    class Storage:
        def save_bytes(self, tenant_id, brand_space_id, category, filename, content):
            target_dir = root / category
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / filename
            target.write_bytes(content)
            return type("Stored", (), {"storage_path": str(target.relative_to(root)).replace("\\", "/")})()

        def absolute_path(self, path: str) -> str:
            return str(root / Path(path))

    renderer.storage = Storage()
    hero_path = renderer.storage.save_bytes("tenant", "brand", "generated", "hero.png", hero_buffer.getvalue()).storage_path
    logo_path = renderer.storage.save_bytes("tenant", "brand", "logo", "jiraaf-logo.png", logo_buffer.getvalue()).storage_path

    payload = RendererInput(
        tenant_id="11111111-1111-1111-1111-111111111111",
        brand_space_id="22222222-2222-2222-2222-222222222222",
        content_version_id="33333333-3333-3333-3333-333333333333",
        studio_panel={"format": "static", "platform_preset": "instagram", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        blueprint=BlueprintPayload(
            layout_type="image_led_social",
            zones=[BlueprintZone(zone_id="headline", role="headline", x=0, y=0, width=100, height=100, max_lines=3)],
            hierarchy=["headline"],
            text_blocks=[],
            image_zones=[],
            logo_rules={},
            cta_placement={"alignment": "left"},
            platform_preset="instagram",
            export_format="png",
            overflow_strategy={"mode": "scene_graph_validate_then_wrap", "deterministic": True},
            source_mode="synthesized_layout",
        ),
        scene_graph=GenerationSceneGraph(
            canvas=SceneGraphCanvas(width=1080, height=1080, platform="instagram", file_type="png"),
            layout_mode="synthesized_layout",
            confidence=0.9,
            layers=["background", "primary_visual", "content", "brand"],
            elements=[
                SceneGraphElement(
                    element_id="background",
                    element_type="background",
                    role="background",
                    layer="background",
                    geometry=SceneGraphGeometry(x=0, y=0, width=1, height=1, units="normalized"),
                    style={"fill_role": "background"},
                ),
                SceneGraphElement(
                    element_id="hero",
                    element_type="image",
                    role="image",
                    layer="primary_visual",
                    geometry=SceneGraphGeometry(x=0.34, y=0.0, width=0.66, height=1.0, units="normalized"),
                    asset={"asset_role": "ai_image", "storage_path": hero_path},
                    style={"fit": "cover"},
                ),
                SceneGraphElement(
                    element_id="headline",
                    element_type="text",
                    role="headline",
                    layer="content",
                    geometry=SceneGraphGeometry(x=0.07, y=0.12, width=0.26, height=0.18, units="normalized"),
                    text="Book Flights Smarter",
                    style={"font_size": 56, "fill_role": "primary"},
                ),
                SceneGraphElement(
                    element_id="logo",
                    element_type="logo",
                    role="logo",
                    layer="brand",
                    geometry=SceneGraphGeometry(x=0.07, y=0.05, width=0.18, height=0.08, units="normalized"),
                    asset={"asset_role": "logo", "storage_path": logo_path},
                    style={"fit": "contain"},
                ),
            ],
            styles={"layout_archetype": "hero_overlay"},
        ),
        text=StructuredTextPayload(
            headline="Book Flights Smarter",
            body="Use flexible dates and alerts to save more.",
            cta="Plan with Confidence",
            hashtags=["#TravelSmarter"],
            metadata={"supporting_line": "Simple planning habits can unlock better fares."},
        ),
        logo_asset_path=logo_path,
        image_assets=[
            {
                "asset_id": uuid4(),
                "mime_type": "image/png",
                "storage_path": hero_path,
                "width": 1080,
                "height": 1080,
                "asset_role": "ai_image",
            }
        ],
        brand_visual_rules={"brand_color_palette": {"primary": "#003975", "secondary": "#FFA400", "accent": "#00CB91"}},
        creative_decision={"layout_mode": "synthesized_layout"},
    )

    response = await renderer.render(payload)

    preview_path = root / Path(response.preview_asset["storage_path"])
    with Image.open(preview_path) as preview:
        preview_rgb = preview.convert("RGB")
        left_sample = preview_rgb.getpixel((120, 160))
        right_sample = preview_rgb.getpixel((900, 260))

    assert response.renderer_metadata["image_rendered"] is True
    assert response.renderer_metadata["logo_rendered"] is True
    assert right_sample != left_sample

    for file in root.rglob("*"):
        if file.is_file():
            file.unlink()
    for directory in sorted([path for path in root.rglob("*") if path.is_dir()], reverse=True):
        directory.rmdir()
    root.rmdir()


@pytest.mark.asyncio
async def test_renderer_does_not_draw_wordmark_substitute_when_logo_asset_is_missing() -> None:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    root = Path("tests") / f"scene-graph-missing-logo-{uuid4()}"
    root.mkdir(parents=True, exist_ok=True)

    class Storage:
        def save_bytes(self, tenant_id, brand_space_id, category, filename, content):
            target_dir = root / category
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / filename
            target.write_bytes(content)
            return type("Stored", (), {"storage_path": str(target.relative_to(root)).replace("\\", "/")})()

        def absolute_path(self, path: str) -> str:
            return str(root / Path(path))

    renderer.storage = Storage()
    payload = RendererInput(
        tenant_id="11111111-1111-1111-1111-111111111111",
        brand_space_id="22222222-2222-2222-2222-222222222222",
        content_version_id="33333333-3333-3333-3333-333333333333",
        studio_panel={"format": "static", "platform_preset": "instagram", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        blueprint=BlueprintPayload(
            layout_type="static",
            zones=[BlueprintZone(zone_id="headline", role="headline", x=0, y=0, width=100, height=100, max_lines=3)],
            hierarchy=["headline"],
            text_blocks=[],
            image_zones=[],
            logo_rules={},
            cta_placement={"alignment": "left"},
            platform_preset="instagram",
            export_format="png",
            overflow_strategy={"mode": "shrink_then_wrap"},
            source_mode="synthesized_layout",
        ),
        scene_graph=GenerationSceneGraph(
            canvas=SceneGraphCanvas(width=1080, height=1080, platform="instagram", file_type="png"),
            layout_mode="synthesized_layout",
            confidence=0.82,
            layers=["background", "content", "brand"],
            elements=[
                SceneGraphElement(
                    element_id="background",
                    element_type="background",
                    role="background",
                    layer="background",
                    geometry=SceneGraphGeometry(x=0, y=0, width=1, height=1, units="normalized"),
                    style={"primary_fill": "#EEF6FF"},
                ),
                SceneGraphElement(
                    element_id="headline",
                    element_type="text",
                    role="headline",
                    layer="content",
                    geometry=SceneGraphGeometry(x=0.08, y=0.12, width=0.72, height=0.16, units="normalized"),
                    text="Scene graph headline",
                    style={"font_size": 52, "fill_role": "primary", "max_lines": 3},
                ),
                SceneGraphElement(
                    element_id="logo",
                    element_type="logo",
                    role="logo",
                    layer="brand",
                    geometry=SceneGraphGeometry(x=0.78, y=0.06, width=0.16, height=0.08, units="normalized"),
                    style={"fit": "contain"},
                ),
            ],
            styles={"layout_archetype": "editorial_hero"},
        ),
        text=StructuredTextPayload(
            headline="Scene graph headline",
            body="Body copy",
            cta="Learn more",
            hashtags=["#brand"],
            metadata={},
        ),
        logo_asset_path="generated/missing-logo.png",
        brand_visual_rules={"brand_name": "Jiraaf", "brand_color_palette": {"primary": "#003975", "secondary": "#FFA400"}},
        creative_decision={"layout_mode": "synthesized_layout"},
    )

    response = await renderer.render(payload)

    assert response.renderer_metadata["logo_rendered"] is False

    for file in root.rglob("*"):
        if file.is_file():
            file.unlink()
    for directory in sorted([path for path in root.rglob("*") if path.is_dir()], reverse=True):
        directory.rmdir()
    root.rmdir()
