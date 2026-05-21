from app.services.content_planning import ContentPlanningService
from app.services.visual_planning import VisualPlanningService


def test_architecture_e2e_text_planning_bundle_is_consistent() -> None:
    bundle = ContentPlanningService().build_text_plan(
        prompt="Write a LinkedIn post explaining why a trade agreement matters strategically, not just numerically.",
        studio_panel={"format": "static", "platform_preset": "linkedin", "file_type": "png"},
        brand_context={"brand_name": "Jiraaf"},
        persona_context={},
        objective_context={},
        knowledge_brief=[],
        live_research={"status": "available", "verified_facts": [{"label": "Signed", "value": "27 April 2026"}]},
        deliverable_type="linkedin_post",
    )

    assert bundle["research_editorial_brief"]["active"] is True
    assert bundle["content_plan"]["planning_family"] == "text"
    assert bundle["content_plan"]["research_mode"] in {"research_editorial", "standard"}
    assert bundle["format_family_plan"]["family"] in {"short_form", "static"}


def test_architecture_e2e_visual_planning_bundle_is_consistent() -> None:
    bundle = VisualPlanningService().build_visual_plan(
        prompt="Create a 5-slide analytical carousel on a new trade agreement.",
        studio_panel={"format": "carousel", "platform_preset": "linkedin", "file_type": "pdf"},
        brand_context={"brand_name": "Jiraaf"},
        persona_context={},
        objective_context={},
        knowledge_brief=[],
        live_research={"status": "available", "verified_facts": [{"label": "Signed", "value": "27 April 2026"}]},
        deliverable_type="visual_generation",
    )

    assert bundle["research_editorial_brief"]["active"] is True
    assert bundle["content_plan"]["format_family"] == "carousel"
    assert bundle["content_plan"]["sequence_contract"] == "native_carousel_metadata"
    assert bundle["content_plan"]["native_metadata_fields"][0] == "carousel_slide_specs"
    assert bundle["content_plan"]["preferred_slide_count"] == 5
    assert bundle["visual_plan"]["planning_family"] == "visual"
    assert bundle["visual_plan"]["execution_mode"] == "multi_page_sequence"
    assert bundle["visual_plan"]["render_mode"] == "ai_final_render"
    assert bundle["format_family_plan"]["family"] in {"carousel", "infographic", "static"}
