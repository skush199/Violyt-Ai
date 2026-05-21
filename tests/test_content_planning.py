from app.services.content_planning import ContentPlanningService


def test_content_planning_derives_editorial_reveal_archetype_from_outline() -> None:
    plan = ContentPlanningService.derive_content_plan(
        deliverable_type="linkedin_carousel",
        format_family_plan={
            "family": "carousel",
            "primary_unit": "slide",
            "body_shape": "multi_slide_sequence",
        },
        research_editorial_brief={
            "outline": [
                {"title": "The overlooked headline", "role": "hook"},
                {"title": "What actually changed", "role": "structure"},
                {"title": "What most coverage missed", "role": "undercovered_angle"},
                {"title": "Why it matters strategically", "role": "strategic_meaning"},
            ]
        },
    )

    assert plan["carousel_archetype"] == "editorial_reveal"
    assert plan["carousel_slide_grammar"][0]["role"] == "hook"


def test_content_planning_derives_list_teaching_archetype_from_bias_topic() -> None:
    plan = ContentPlanningService.derive_content_plan(
        deliverable_type="behavioural_biases_carousel",
        format_family_plan={
            "family": "carousel",
            "content_structure": ["setup_slide", "one_bias_per_slide", "closing_cta"],
            "notes": ["Teach one bias per slide with a repeated learning pattern."],
        },
        research_editorial_brief={"outline": []},
    )

    assert plan["carousel_archetype"] == "list_teaching"
    assert any(step["role"] == "list_item" for step in plan["carousel_slide_grammar"])


def test_content_planning_derives_problem_solution_feature_archetype_from_analyzer_topic() -> None:
    plan = ContentPlanningService.derive_content_plan(
        deliverable_type="bond_analyzer_carousel",
        format_family_plan={
            "family": "carousel",
            "notes": ["Frame the product problem first, then show the solution and capability flow."],
        },
        research_editorial_brief={"outline": []},
    )

    assert plan["carousel_archetype"] == "problem_solution_feature"
    assert plan["carousel_slide_grammar"][0]["role"] == "problem_frame"
