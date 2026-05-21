from app.ai.layout_decision import LayoutDecisionEngine


def test_layout_decision_prefers_exact_template_for_strong_direct_match() -> None:
    engine = LayoutDecisionEngine()

    decision = engine.decide(
        prompt="Create a concise LinkedIn product launch creative",
        studio_panel={"platform_preset": "linkedin", "format": "static", "file_type": "png"},
        brand_context={"validation": {"warnings": []}, "visual_identity": {"brand_color_palette": {"primary": "#123456"}}},
        persona_context={"name": "Founder"},
        objective_context={"name": "Launch"},
        template_recommendations=[
            {
                "template_id": "11111111-1111-1111-1111-111111111111",
                "name": "LinkedIn Launch",
                "score": 12.4,
                "adaptation_plan": {},
            }
        ],
        reference_assets=[],
    )

    assert decision.mode == "exact_template"
    assert decision.template_id == "11111111-1111-1111-1111-111111111111"


def test_layout_decision_chooses_adaptation_when_template_needs_reflow() -> None:
    engine = LayoutDecisionEngine()

    decision = engine.decide(
        prompt="Create a detailed Instagram carousel explaining five product benefits and include a stronger call to action for signups",
        studio_panel={"platform_preset": "instagram", "format": "carousel", "file_type": "png"},
        brand_context={"validation": {"warnings": []}, "visual_identity": {}},
        persona_context={},
        objective_context={},
        template_recommendations=[
            {
                "template_id": "22222222-2222-2222-2222-222222222222",
                "name": "Instagram Explainer",
                "score": 8.2,
                "adaptation_plan": {"multi_section_flow": True},
            }
        ],
        reference_assets=[],
    )

    assert decision.mode == "adapted_template"
    assert decision.adaptation_plan["multi_section_flow"] is True


def test_layout_decision_synthesizes_when_no_template_is_good_enough() -> None:
    engine = LayoutDecisionEngine()

    decision = engine.decide(
        prompt="Design a fresh editorial infographic for a brand new investor education concept with no matching existing layout",
        studio_panel={"platform_preset": "linkedin", "format": "infographic", "file_type": "pdf"},
        brand_context={"validation": {"warnings": ["palette conflict"]}, "visual_identity": {}},
        persona_context={},
        objective_context={},
        template_recommendations=[],
        reference_assets=[{"asset_id": "ref-1"}],
    )

    assert decision.mode == "synthesized_layout"
    assert decision.asset_strategy["use_brand_reference_assets"] is True


def test_layout_decision_respects_reference_only_recommendations() -> None:
    engine = LayoutDecisionEngine()

    decision = engine.decide(
        prompt="Create a long-form LinkedIn explainer with multiple sections and a CTA",
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
        brand_context={"validation": {"warnings": []}, "visual_identity": {}},
        persona_context={},
        objective_context={},
        template_recommendations=[
            {
                "template_id": "33333333-3333-3333-3333-333333333333",
                "name": "Announcement Card",
                "score": 8.8,
                "match_type": "reference_only",
                "adaptation_plan": {"multi_section_flow": True, "cta_reposition": True},
            }
        ],
        reference_assets=[{"asset_id": "ref-1"}],
    )

    assert decision.mode == "synthesized_layout"
    assert "synthesize" in decision.rationale[0].lower()


def test_layout_decision_can_upgrade_reference_only_when_fit_is_visually_strong() -> None:
    engine = LayoutDecisionEngine()

    decision = engine.decide(
        prompt="Create an engaging Instagram post with flight booking tips and lower airfare strategies",
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png"},
        brand_context={"validation": {"warnings": []}, "visual_identity": {"brand_color_palette": {"primary": "#0B4D9A"}}},
        persona_context={},
        objective_context={},
        template_recommendations=[
            {
                "template_id": "44444444-4444-4444-4444-444444444444",
                "name": "Flight Fare Card",
                "score": 8.1,
                "match_type": "reference_only",
                "score_breakdown": {
                    "keyword_overlap": 4.5,
                    "platform_fit": 4.0,
                    "brand_alignment": 1.3,
                    "export_fit": 2.0,
                },
                "adaptation_plan": {"compact_cta": True},
            }
        ],
        reference_assets=[],
    )

    assert decision.mode == "adapted_template"
    assert "adapted" in decision.rationale[0].lower()


def test_layout_decision_rejects_explicit_text_heavy_flattened_templates_as_render_surfaces() -> None:
    engine = LayoutDecisionEngine()

    decision = engine.decide(
        prompt="Create an engaging Instagram post about why investors are shifting from fixed deposits to bonds in 2026",
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png"},
        brand_context={"validation": {"warnings": []}, "visual_identity": {"brand_color_palette": {"primary": "#0B4D9A"}}},
        persona_context={},
        objective_context={},
        template_recommendations=[
            {
                "template_id": "55555555-5555-5555-5555-555555555555",
                "name": "FD Returns Poster",
                "score": 9.2,
                "match_type": "adapted_template",
                "adaptation_plan": {},
                "metadata": {
                    "surface_kind": "reference_only_flattened_text",
                    "text_overlay_risk": "high",
                    "overlay_safe": False,
                },
            }
        ],
        selected_template_id="55555555-5555-5555-5555-555555555555",
        selected_template_name="FD Returns Poster",
        reference_assets=[],
    )

    assert decision.mode == "synthesized_layout"
    assert decision.template_id is None
    assert "template_text_overlay_risk" in decision.review_flags
    assert decision.adaptation_plan["reference_style_only"] is True


def test_layout_decision_prefers_brand_logo_when_storage_path_exists() -> None:
    engine = LayoutDecisionEngine()

    decision = engine.decide(
        prompt="Create an Instagram post about steady bond investing",
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png"},
        brand_context={
            "validation": {"warnings": []},
            "visual_identity": {},
            "identity": {"logo_asset_path": "tenant/brand/uploads/logo.png"},
        },
        persona_context={},
        objective_context={},
        template_recommendations=[],
        reference_assets=[],
    )

    assert decision.brand_rule_hints["logo_required"] is True
    assert decision.asset_strategy["prefer_brand_logo"] is True


def test_layout_decision_ignores_unrelated_brand_validation_conflicts_for_clean_selected_template() -> None:
    engine = LayoutDecisionEngine()

    decision = engine.decide(
        prompt="Create a LinkedIn carousel about trade agreements.",
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
        brand_context={
            "validation": {
                "warnings": [
                    "Template 'Floating-Rate-Bonds-6' uses colors outside the validated palette.",
                    "Template 'Another Sample' uses colors outside the validated palette.",
                ],
                "conflict_count": 2,
            },
            "visual_identity": {},
        },
        persona_context={},
        objective_context={},
        template_recommendations=[
            {
                "template_id": "77777777-7777-7777-7777-777777777777",
                "name": "FTA Sample",
                "score": 8.9,
                "adaptation_plan": {"multi_section_flow": True},
                "review_flags": [],
            }
        ],
        reference_assets=[],
    )

    assert "brand_validation_conflicts_present" not in decision.review_flags
    assert decision.score_breakdown["validation_warning_count"] == 0.0


def test_layout_decision_downgrades_weak_topic_template_for_social_visuals() -> None:
    engine = LayoutDecisionEngine()

    decision = engine.decide(
        prompt="Create an Instagram post showing how inflation erodes savings over time",
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png"},
        brand_context={"validation": {"warnings": []}, "visual_identity": {}},
        persona_context={},
        objective_context={},
        template_recommendations=[
            {
                "template_id": "66666666-6666-6666-6666-666666666666",
                "name": "Breaking Your FD Early",
                "score": 8.4,
                "match_type": "adapted_template",
                "adaptation_plan": {"compact_cta": True},
                "score_breakdown": {
                    "keyword_overlap": 0.0,
                    "ocr_text_fit": 0.0,
                    "platform_fit": 4.0,
                    "brand_alignment": 1.0,
                    "export_fit": 1.0,
                },
                "metadata": {"overlay_safe": True},
            }
        ],
        reference_assets=[],
    )

    assert decision.mode == "synthesized_layout"
    assert decision.template_id is None
    assert "template_topic_mismatch" in decision.review_flags
    assert decision.adaptation_plan["reference_style_only"] is True
    assert decision.adaptation_plan["topic_fit_too_weak"] is True


def test_template_format_compatible_accepts_adapted_multi_section_carousel_templates() -> None:
    recommendation = {
        "match_type": "adapted_template",
        "adaptation_plan": {
            "multi_section_flow": True,
            "prefer_distinct_sections": True,
        },
        "metadata": {"format": "static", "tags": []},
    }

    assert LayoutDecisionEngine._template_format_compatible(recommendation, "carousel") is True


def test_template_format_compatible_rejects_true_single_frame_templates_for_carousel() -> None:
    recommendation = {
        "match_type": "exact_template",
        "adaptation_plan": {},
        "metadata": {"format": "static", "tags": ["poster"], "zone_roles": ["headline", "logo"]},
        "sequence_length": 1,
    }

    assert LayoutDecisionEngine._template_format_compatible(recommendation, "carousel") is False
