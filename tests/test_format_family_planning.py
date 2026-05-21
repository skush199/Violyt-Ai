from app.services.format_family_planning import FormatFamilyPlanningService


def test_format_family_planning_builds_carousel_contract_from_visual_format() -> None:
    service = FormatFamilyPlanningService()

    plan = service.build(
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
        content_format_brief={"preferred_slide_count": 6, "summary": "Build for swipe-by-swipe reading."},
        research_editorial_brief={"active": True, "preferred_slide_count": 7},
    )

    assert plan["family"] == "carousel"
    assert plan["primary_unit"] == "slide"
    assert plan["body_shape"] == "multi_slide_sequence"
    assert plan["outline_mode"] == "sequenced"
    assert "carousel_slide_specs" in plan["required_components"]
    assert plan["preferred_slide_count"] == 7
    assert any("slide-by-slide sequence" in note for note in plan["notes"])


def test_format_family_planning_builds_long_form_contract_from_deliverable() -> None:
    service = FormatFamilyPlanningService()

    plan = service.build(
        studio_panel={"platform_preset": "linkedin", "format": "text", "file_type": "md"},
        deliverable_type="blog",
        research_editorial_brief={"active": False},
    )

    assert plan["family"] == "long_form"
    assert plan["primary_unit"] == "section"
    assert plan["body_shape"] == "multi_section_editorial"
    assert plan["outline_mode"] == "sectioned"
    assert "outline" in plan["metadata_fields"]
    assert plan["preferred_slide_count"] is None
    assert any("sections" in rule.casefold() for rule in plan["planning_rules"])
