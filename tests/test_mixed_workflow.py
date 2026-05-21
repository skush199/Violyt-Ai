from app.services.mixed_workflow import MixedWorkflowService


def test_mixed_workflow_service_builds_state_for_review_then_generate() -> None:
    state = MixedWorkflowService().build_state(
        workflow_plan={"type": "review_then_generate", "target_mode": "content_only"},
        session_context={},
        review_result={"summary": "Use more evidence."},
        reviewed_asset_ids=["asset-1"],
        source_mode="evaluation",
    )

    assert state is not None
    assert state.workflow_type == "review_then_generate"
    assert state.current_step == "apply_review_findings"
    assert len(state.steps) == 3
    assert state.reviewed_asset_ids == ["asset-1"]


def test_mixed_workflow_service_prepare_generation_context_carries_state() -> None:
    context = MixedWorkflowService().prepare_generation_context(
        message="Turn it into a carousel.",
        workflow_plan={"type": "repurpose_text_to_visual", "target_mode": "visual_generation"},
        session_context={
            "last_response_mode": "content_only",
            "last_text_output": "Source copy",
            "last_text_deliverable_type": "linkedin_post",
        },
        review_result=None,
        reference_asset_ids=[],
    )

    assert context.workflow_state is not None
    assert context.workflow_state["workflow_type"] == "repurpose_text_to_visual"
    assert context.workflow_state["steps"][0]["key"] == "reuse_source_text"
    assert "Source text to repurpose" in context.prompt
