from app.ai.session_memory import SessionMemoryPlanner


def test_session_memory_detects_modify_previous_output() -> None:
    planner = SessionMemoryPlanner()

    intent = planner.detect_follow_up_intent(
        current_prompt="Make the previous one shorter and keep the same layout.",
        recent_messages=[
            {"role": "user", "message_text": "Create a LinkedIn post about bond safety."},
            {"role": "assistant", "message_text": "Here is the first draft."},
        ],
        latest_content={
            "id": "11111111-1111-1111-1111-111111111111",
            "template_id": "22222222-2222-2222-2222-222222222222",
        },
    )

    assert intent["mode"] == "modify_previous"
    assert intent["uses_previous_output"] is True


def test_session_memory_detects_variant_of_previous_output() -> None:
    planner = SessionMemoryPlanner()

    intent = planner.detect_follow_up_intent(
        current_prompt="Give me another version with a different angle.",
        recent_messages=[{"role": "assistant", "message_text": "Draft one"}],
        latest_content={
            "id": "11111111-1111-1111-1111-111111111111",
        },
    )

    assert intent["mode"] == "variant_of_previous"
    assert intent["uses_previous_output"] is True


def test_session_memory_treats_regenerate_as_variant_request() -> None:
    planner = SessionMemoryPlanner()

    intent = planner.detect_follow_up_intent(
        current_prompt="Regenerate this with a different layout.",
        recent_messages=[{"role": "assistant", "message_text": "Draft one"}],
        latest_content={
            "id": "11111111-1111-1111-1111-111111111111",
        },
    )

    assert intent["mode"] == "variant_of_previous"
    assert intent["uses_previous_output"] is True


def test_session_memory_detects_new_content_when_prompt_is_explicit() -> None:
    planner = SessionMemoryPlanner()

    intent = planner.detect_follow_up_intent(
        current_prompt="Create a completely new post about portfolio diversification from scratch.",
        recent_messages=[{"role": "assistant", "message_text": "Earlier draft"}],
        latest_content={
            "id": "11111111-1111-1111-1111-111111111111",
        },
    )

    assert intent["mode"] == "new_content"
    assert intent["new_content_request"] is True


def test_session_memory_build_inherits_previous_selection_for_follow_up() -> None:
    planner = SessionMemoryPlanner()

    memory = planner.build(
        current_prompt="Change the CTA and keep the same template.",
        recent_messages=[{"role": "assistant", "message_text": "Previous output"}],
        recent_content_versions=[
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "persona_id": "33333333-3333-3333-3333-333333333333",
                "objective_id": "44444444-4444-4444-4444-444444444444",
                "template_id": "22222222-2222-2222-2222-222222222222",
            }
        ],
        session_context={"message_count": 2},
    )

    assert memory["follow_up_intent"]["mode"] == "modify_previous"
    assert memory["inherited_persona_id"] == "33333333-3333-3333-3333-333333333333"
    assert memory["inherited_objective_id"] == "44444444-4444-4444-4444-444444444444"
    assert memory["inherited_template_id"] == "22222222-2222-2222-2222-222222222222"


def test_session_memory_treats_long_standalone_brief_as_new_content() -> None:
    planner = SessionMemoryPlanner()

    intent = planner.detect_follow_up_intent(
        current_prompt=(
            "Create a LinkedIn carousel post for Jiraaf on the topic: How Census 2027 could impact India's "
            "financial future. Keep it insightful, simple, and relevant for working professionals interested "
            "in wealth creation."
        ),
        recent_messages=[{"role": "assistant", "message_text": "Earlier FTA draft"}],
        latest_content={
            "id": "11111111-1111-1111-1111-111111111111",
            "prompt": "Write a LinkedIn carousel for Jiraaf on the India-New Zealand Free Trade Agreement.",
            "headline": "What's really inside the India-New Zealand Free Trade Deal?",
        },
    )

    assert intent["mode"] == "new_content"
    assert intent["uses_previous_output"] is False
