from scripts.run_generation_stub_demo import _all_scenarios


def test_stub_demo_matrix_covers_at_least_fifteen_scenarios() -> None:
    scenarios = _all_scenarios()

    assert len(scenarios) >= 15
    assert {"static", "story", "poster", "carousel", "infographic", "pdf"}.issubset(
        {scenario.format_name for scenario in scenarios}
    )
    assert {"instagram", "linkedin", "x", "youtube_thumbnail"}.issubset(
        {scenario.platform_preset for scenario in scenarios}
    )
    pdf_scenarios = [scenario for scenario in scenarios if scenario.format_name == "pdf"]
    assert pdf_scenarios
    assert all(scenario.file_type == "pdf" for scenario in pdf_scenarios)
