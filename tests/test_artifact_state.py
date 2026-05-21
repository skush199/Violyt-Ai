from app.services.artifact_state import ArtifactStateService


def test_artifact_state_service_builds_content_state() -> None:
    service = ArtifactStateService()

    state = service.build_content_state(
        mode="content_only",
        prompt="Write a LinkedIn post about bond ladders.",
        studio_panel={"platform_preset": "linkedin", "format": "text"},
        research_objects={"live_research": {"active": True}, "retrieval_channels": ["knowledge"]},
        planning_objects={"format_family_plan": {"family": "short_form"}},
        revision_lineage={"parent_version_id": "123"},
        source_linked_artifacts={"reviewed_asset_ids": ["a1"]},
    )

    assert state["mode"] == "content_only"
    assert state["research_objects"]["retrieval_channels"] == ["knowledge"]
    assert state["planning_objects"]["format_family_plan"]["family"] == "short_form"
    assert state["revision_lineage"]["parent_version_id"] == "123"
    assert state["source_linked_artifacts"]["reviewed_asset_ids"] == ["a1"]


def test_artifact_state_service_merges_session_state_with_evaluation_history() -> None:
    service = ArtifactStateService()

    session_state = service.build_session_state(
        {"artifact_state": {"evaluation_history": [{"overall_score": 75}], "schema_version": 1}},
        content_artifact_state={"planning_objects": {"format_family_plan": {"family": "carousel"}}},
        evaluation_entry={"overall_score": 82, "review_type": "tone_brand_consistency"},
    )

    assert session_state["planning_objects"]["format_family_plan"]["family"] == "carousel"
    assert len(session_state["evaluation_history"]) == 2
    assert session_state["evaluation_history"][-1]["overall_score"] == 82
