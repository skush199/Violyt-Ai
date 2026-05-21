from app.utils.input_access_tracking import InputAccessTracker


def test_input_access_tracker_reports_used_and_unused_nested_paths() -> None:
    tracker = InputAccessTracker()
    wrapped = tracker.wrap_source(
        "brand_context",
        {
            "identity": {
                "brand_name": "The Good Fish Company",
                "brand_description": "Trusted seafood brand",
            },
            "visual_identity": {
                "brand_mood": "fresh, clean, premium",
                "brand_color_palette": {"primary": "#1CA9C9"},
            },
        },
    )

    assert wrapped["identity"]["brand_name"] == "The Good Fish Company"
    assert wrapped.get("visual_identity", {}).get("brand_mood") == "fresh, clean, premium"

    summary = tracker.build_summary()
    brand_summary = summary["brand_context"]

    assert "identity.brand_name" in brand_summary["used_paths"]
    assert "visual_identity.brand_mood" in brand_summary["used_paths"]
    assert "identity.brand_description" in brand_summary["unused_paths"]
    assert "visual_identity.brand_color_palette.primary" in brand_summary["unused_paths"]
    assert brand_summary["read_counts"]["identity.brand_name"] >= 1
    assert brand_summary["read_counts"]["visual_identity.brand_mood"] >= 1
