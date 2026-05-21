from app.ai.composition_planner import CompositionPlannerService
from app.ai.contracts import BlueprintPayload, BlueprintZone, StructuredTextPayload


def _blueprint(source_mode: str = "synthesized_layout") -> BlueprintPayload:
    return BlueprintPayload(
        layout_type="static",
        zones=[
            BlueprintZone(zone_id="headline", role="headline", x=0, y=0, width=100, height=100, max_lines=3),
            BlueprintZone(zone_id="body", role="body", x=0, y=100, width=100, height=100, max_lines=5),
            BlueprintZone(zone_id="cta", role="cta", x=0, y=200, width=100, height=60, max_lines=2),
        ],
        hierarchy=["headline", "body", "cta"],
        text_blocks=[],
        image_zones=[],
        logo_rules={},
        cta_placement={"alignment": "left"},
        platform_preset="instagram",
        export_format="png",
        overflow_strategy={"mode": "shrink_then_wrap"},
        source_mode=source_mode,
    )


def test_composition_planner_picks_checklist_for_instagram_tips_prompt() -> None:
    planner = CompositionPlannerService()

    plan = planner.build(
        prompt="Create an engaging Instagram post with tips and strategies to book flights at a lower cost",
        blueprint=_blueprint(),
        text_payload=StructuredTextPayload(
            headline="Book Flights Smarter",
            body="Compare sites. Use flexible dates. Set alerts.",
            cta="Travel smarter",
            hashtags=["#Travel"],
            metadata={"proof_points": ["Compare sites", "Use flexible dates", "Set alerts"]},
        ),
        studio_panel={"platform_preset": "instagram", "format": "static", "size": {"width": 1080, "height": 1080}},
        compiled_context={
            "render_constraints": {"text_density": "medium", "canvas_size": {"width": 1080, "height": 1080}},
            "audience_brief": {},
            "brand_visual_brief": {"palette_roles": {"primary": "#0B4D9A", "secondary": "#F5A623"}},
            "template_fit_brief": {},
        },
    )

    assert plan["layout_plan"]["layout_archetype"] == "checklist_card"


def test_composition_planner_allows_brand_gradient_without_explicit_background_role() -> None:
    planner = CompositionPlannerService()

    plan = planner.build(
        prompt="Create a LinkedIn explainer post about investment confidence",
        blueprint=_blueprint(),
        text_payload=StructuredTextPayload(
            headline="Invest with clarity",
            body="Trusted signals for confident decisions.",
            cta="Learn more",
            hashtags=["#Investing"],
            metadata={},
        ),
        studio_panel={"platform_preset": "linkedin", "format": "static", "size": {"width": 1200, "height": 627}},
        compiled_context={
            "render_constraints": {"text_density": "medium", "canvas_size": {"width": 1200, "height": 627}},
            "audience_brief": {},
            "brand_visual_brief": {"palette_roles": {"primary": "#0B4D9A", "secondary": "#F5A623"}},
            "template_fit_brief": {},
        },
    )

    assert plan["background_plan"]["policy"] == "brand_gradient"
