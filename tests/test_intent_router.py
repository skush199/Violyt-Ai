from app.services.intent_router import IntentRouterService


def test_intent_router_routes_greeting_to_small_talk() -> None:
    decision = IntentRouterService().route("Hi")
    assert decision.mode == "small_talk"


def test_intent_router_routes_text_deliverable_to_content_only() -> None:
    decision = IntentRouterService().route("Write a LinkedIn post on bond duration risk.")
    assert decision.mode == "content_only"
    assert decision.deliverable_type == "linkedin_post"


def test_intent_router_routes_visual_request_to_visual_generation() -> None:
    decision = IntentRouterService().route("Generate a LinkedIn carousel on bond mistakes.")
    assert decision.mode == "visual_generation"


def test_intent_router_routes_tone_review_to_evaluation() -> None:
    decision = IntentRouterService().route("Check tone consistency: This copy feels too salesy.")
    assert decision.mode == "evaluation"


def test_intent_router_keeps_visual_follow_up_in_visual_mode() -> None:
    decision = IntentRouterService().route(
        "Make slide 2 sharper and reduce the text.",
        {"last_response_mode": "visual_generation"},
    )
    assert decision.mode == "visual_generation"
    assert decision.uses_previous_output is True


def test_intent_router_treats_fresh_carousel_brief_as_new_generation_even_after_visual_turn() -> None:
    decision = IntentRouterService().route(
        (
            "Write a LinkedIn carousel for Jiraaf on the India-New Zealand Free Trade Agreement. "
            "Length: 4-6 slides. Open with a hook that makes the reader swipe."
        ),
        {"last_response_mode": "visual_generation"},
    )

    assert decision.mode == "visual_generation"
    assert decision.uses_previous_output is False
    assert decision.reason == "fresh_visual_generation_request"


def test_intent_router_treats_standalone_brief_with_plain_language_it_as_new_generation() -> None:
    decision = IntentRouterService().route(
        (
            "Write a LinkedIn carousel for Jiraaf, an Indian alternative investments platform, "
            "on the India-New Zealand Free Trade Agreement signed on 27 April 2026. "
            "Tone: conversational, analytical, intelligent. "
            "Angle: Go beyond the headline numbers. Look at how the deal is structured, "
            "what India negotiated, and why it matters strategically - not just what India gained."
        ),
        {"last_response_mode": "visual_generation"},
    )

    assert decision.mode == "visual_generation"
    assert decision.uses_previous_output is False
    assert decision.reason == "fresh_visual_generation_request"


def test_intent_router_treats_long_census_visual_brief_as_fresh_generation() -> None:
    decision = IntentRouterService().route(
        (
            "Create a LinkedIn carousel post for Jiraaf on the topic: How Census 2027 could impact India's "
            "financial future. Keep it relevant for working professionals who are interested in wealth creation "
            "but may not track policy-level events closely. Structure it like a story: Start with a strong hook, "
            "explain what the census is simply, show why people ignore it, then connect it to money and end with "
            "a strong thought-provoking closing. Keep text short per slide."
        ),
        {"last_response_mode": "visual_generation"},
    )

    assert decision.mode == "visual_generation"
    assert decision.uses_previous_output is False
    assert decision.revision_scope is None
    assert decision.reason == "fresh_visual_generation_request"


def test_intent_router_keeps_text_follow_up_in_content_mode() -> None:
    decision = IntentRouterService().route(
        "Rewrite this to sound more analytical.",
        {"last_response_mode": "content_only", "last_text_deliverable_type": "linkedin_post"},
    )
    assert decision.mode == "content_only"
    assert decision.uses_previous_output is True


def test_intent_router_extracts_text_revision_scope_for_cta_only() -> None:
    decision = IntentRouterService().route(
        "Rewrite only the CTA and make it more analytical.",
        {"last_response_mode": "content_only", "last_text_deliverable_type": "linkedin_post"},
    )
    assert decision.mode == "content_only"
    assert decision.revision_scope is not None
    assert decision.revision_scope["targeted_fields"] == ["cta"]
    assert decision.revision_scope["only_targeted"] is True
    assert decision.revision_scope["change_tone"] is True


def test_intent_router_extracts_visual_revision_scope_for_slide_specific_follow_up() -> None:
    decision = IntentRouterService().route(
        "Make slide 3 sharper but keep the visuals the same.",
        {"last_response_mode": "visual_generation"},
    )
    assert decision.mode == "visual_generation"
    assert decision.revision_scope is not None
    assert decision.revision_scope["slide_indexes"] == [3]
    assert decision.revision_scope["preserve_visuals"] is True


def test_intent_router_preserves_true_visual_follow_up_reuse() -> None:
    decision = IntentRouterService().route(
        "Make slide 2 shorter and keep the same design.",
        {"last_response_mode": "visual_generation"},
    )

    assert decision.mode == "visual_generation"
    assert decision.uses_previous_output is True
    assert decision.revision_scope is not None
    assert decision.revision_scope["slide_indexes"] == [2]


def test_intent_router_routes_copy_to_carousel_as_mixed_workflow() -> None:
    decision = IntentRouterService().route(
        "Turn it into a carousel for LinkedIn.",
        {"last_response_mode": "content_only", "last_text_deliverable_type": "linkedin_post"},
    )

    assert decision.mode == "visual_generation"
    assert decision.workflow_plan is not None
    assert decision.workflow_plan["type"] == "repurpose_text_to_visual"
    assert decision.uses_previous_output is False


def test_intent_router_routes_review_then_generate_as_mixed_workflow() -> None:
    decision = IntentRouterService().route(
        "Review this document, then generate a LinkedIn post from it.",
        {},
    )

    assert decision.mode == "content_only"
    assert decision.workflow_plan is not None
    assert decision.workflow_plan["type"] == "review_then_generate"
