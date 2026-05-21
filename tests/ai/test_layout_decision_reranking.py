from __future__ import annotations

from app.ai.layout_decision import LayoutDecisionEngine


def _brand_context() -> dict:
    return {
        "identity": {},
        "validation": {"warnings": [], "conflict_count": 0},
        "visual_identity": {"palette_entries": [], "typography": {"font_families": []}},
    }


def _studio_panel() -> dict:
    return {"platform_preset": "instagram", "format": "static", "file_type": "png"}


def test_layout_decision_uses_composite_topic_fit_for_visual_requests() -> None:
    engine = LayoutDecisionEngine()

    decision = engine.decide(
        prompt="Create a social visual that explains how the workflow changed after automation.",
        studio_panel=_studio_panel(),
        brand_context=_brand_context(),
        persona_context={},
        objective_context={},
        template_recommendations=[
            {
                "template_id": "template-1",
                "name": "Transformation Story Carousel",
                "score": 9.6,
                "match_type": "adapted_template",
                "metadata": {"overlay_safe": True},
                "adaptation_plan": {"multi_section_flow": True},
                "editability_score": 0.73,
                "style_only_suitability": 0.18,
                "score_breakdown": {
                    "keyword_overlap": 0.0,
                    "ocr_text_fit": 0.0,
                    "topic_fit": 0.68,
                    "semantic_similarity": 0.82,
                },
            }
        ],
    )

    assert decision.mode == "adapted_template"
    assert decision.template_id == "template-1"


def test_layout_decision_can_promote_runner_up_with_better_fit() -> None:
    engine = LayoutDecisionEngine()

    decision = engine.decide(
        prompt="Create a visual story about workflow transformation after automation.",
        studio_panel=_studio_panel(),
        brand_context=_brand_context(),
        persona_context={},
        objective_context={},
        template_recommendations=[
            {
                "template_id": "template-top",
                "name": "Editorial Grid Template",
                "score": 9.4,
                "match_type": "adapted_template",
                "metadata": {"overlay_safe": True},
                "adaptation_plan": {"compact_cta": True},
                "editability_score": 0.34,
                "style_only_suitability": 0.86,
                "score_breakdown": {"topic_fit": 0.35, "semantic_similarity": 0.44},
            },
            {
                "template_id": "template-runner",
                "name": "Transformation Story Template",
                "score": 8.9,
                "match_type": "adapted_template",
                "metadata": {"overlay_safe": True},
                "adaptation_plan": {"multi_section_flow": True},
                "editability_score": 0.71,
                "style_only_suitability": 0.22,
                "score_breakdown": {"topic_fit": 0.67, "semantic_similarity": 0.78},
            },
        ],
    )

    assert decision.template_id == "template-runner"
    assert decision.mode == "adapted_template"
