from app.ai.context_compiler import ContextCompilerService
from app.core.config import get_settings


def test_context_compiler_preserves_legacy_brand_foundation_field() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a premium investing post.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {
                "brand_foundation": "Build trust through clarity, confidence, and measured optimism.",
            },
            "audience_insights": {},
            "visual_identity": {},
        },
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 2},
        session_memory={},
    )

    assert compiled["brand_copy_brief"]["brand_foundations"] == "Build trust through clarity, confidence, and measured optimism."


def test_context_compiler_visual_brief_includes_design_system_summaries() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a premium investing explainer.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {},
            "audience_insights": {},
            "visual_identity": {
                "brand_color_palette": {
                    "primary": "#003975",
                    "accent": "#FFA400",
                },
                "design_system": {
                    "sample_count": 4,
                    "layout_preferences": {
                        "dominant": "editorial explainer",
                        "preferred_zone_roles": ["headline", "proof module", "cta"],
                    },
                    "background_style": {
                        "type": "gradient",
                        "description": "calm editorial gradient",
                        "primary_hex": "#003975",
                    },
                    "component_motifs": {
                        "numbered_badges": {"page_support": 3, "page_support_ratio": 0.75},
                        "text_background_boxes": {"page_support": 2, "page_support_ratio": 0.5},
                    },
                    "typography_preferences": {
                        "heading_styles": ["bold editorial headline"],
                        "text_alignments": ["left"],
                        "dominant_cases": ["sentence case"],
                    },
                    "visual_hierarchy": {
                        "focal_roles": ["headline"],
                        "density_preferences": ["airy"],
                        "whitespace_preferences": ["generous"],
                    },
                    "content_structure": {
                        "storytelling_modes": ["data story", "benefit stack"],
                        "cta_prominence": "measured",
                    },
                    "image_treatment": {"styles": ["diagram led", "editorial illustration"]},
                    "brand_cues": {
                        "tone_keywords": ["trustworthy", "measured"],
                        "trust_markers": ["data cues"],
                    },
                    "logo_anchor": "top-right",
                    "gradient_preferences": [
                        {
                            "type": "linear",
                            "direction": "diagonal",
                            "start_color": "#003975",
                            "end_color": "#0A5FB4",
                        }
                    ],
                },
            },
        },
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 1},
        session_memory={},
    )

    brief = compiled["brand_visual_brief"]

    assert brief["sample_count"] == 4
    assert brief["dominant_layout_family"] == "editorial explainer"
    assert brief["preferred_zone_roles"] == ["headline", "proof module", "cta"]
    assert "gradient" in brief["background_style_summary"]
    assert "numbered badges" in brief["motif_summary"]
    assert "headline" in brief["hierarchy_summary"]
    assert "data story" in brief["content_structure_summary"]
    assert "diagram led" in brief["image_treatment_summary"]
    assert brief["logo_position"] == "top-right"
    assert brief["gradient_preferences"][0]["direction"] == "diagonal"


def test_context_compiler_preserves_sequence_pack_zone_maps_in_template_fit_brief() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a premium LinkedIn carousel.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {},
            "audience_insights": {},
            "visual_identity": {},
        },
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png", "size": {"width": 1080, "height": 1350}},
        conversation_context={},
        session_memory={},
        layout_decision={"mode": "adapted_template"},
        template_context={
            "sequence_pack": {
                "family_name": "FLOATING-RATE-BONDS",
                "surface_policy": "style_reference_only",
                "slides": [
                    {
                        "slide_index": 1,
                        "template_name": "FLOATING-RATE-BONDS-1",
                        "reference_asset_path": "tenant/reference/slide-1.jpg",
                        "story_role": "context",
                        "headline_hint": "Beyond the headline",
                        "structural_cues": ["context setup"],
                        "zone_map": {
                            "layout_type": "infographic",
                            "zones": [
                                {"role": "logo", "x": 0.88, "y": 0.02, "w": 0.1, "h": 0.08},
                                {"role": "headline", "x": 0.05, "y": 0.1, "w": 0.65, "h": 0.12},
                                {"role": "image", "x": 0.55, "y": 0.75, "w": 0.4, "h": 0.2},
                            ],
                        },
                    }
                ],
            }
        },
        template_candidates=[],
        reference_assets=[],
    )

    template_fit = compiled["template_fit_brief"]
    assert template_fit["template_layout_dna"]["layout_type"] == "infographic"
    assert template_fit["template_layout_dna"]["zones"][0]["role"] == "logo"
    assert template_fit["sequence_pack"]["slides"][0]["reference_asset_path"] == "tenant/reference/slide-1.jpg"
    assert template_fit["sequence_pack"]["slides"][0]["zone_map"]["layout_type"] == "infographic"
    assert template_fit["sequence_pack"]["slides"][0]["zone_map"]["zones"][1]["role"] == "headline"


def test_context_compiler_reference_asset_brief_preserves_storage_paths() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a premium LinkedIn carousel.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {},
            "audience_insights": {},
            "visual_identity": {},
        },
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png", "size": {"width": 1080, "height": 1350}},
        conversation_context={},
        session_memory={},
        reference_assets=[
            {
                "asset_id": "ref-1",
                "asset_role": "reference_creative",
                "storage_path": "tenant/reference/fta-slide-1.pdf",
                "trust_level": "trusted",
                "metadata": {
                    "name": "FTA slide 1",
                    "summary": "Strong opening hook sample.",
                    "page_count": 5,
                },
            }
        ],
    )

    brief = compiled["reference_asset_brief"][0]
    assert brief["asset_id"] == "ref-1"
    assert brief["storage_path"] == "tenant/reference/fta-slide-1.pdf"
    assert brief["name"] == "FTA slide 1"


def test_context_compiler_drops_zero_area_zones_and_weak_sequence_hints() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a premium LinkedIn carousel.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {},
            "audience_insights": {},
            "visual_identity": {},
        },
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png", "size": {"width": 1080, "height": 1350}},
        conversation_context={},
        session_memory={},
        layout_decision={"mode": "adapted_template"},
        template_context={
            "sequence_pack": {
                "family_name": "06-01",
                "surface_policy": "style_reference_only",
                "slides": [
                    {
                        "slide_index": 1,
                        "template_name": "06.01.2026",
                        "story_role": "hook",
                        "headline_hint": "06.01",
                        "structural_cues": ["cover hook"],
                        "zone_map": {
                            "layout_type": "infographic",
                            "zones": [
                                {"role": "headline", "x": 0.05, "y": 0.1, "w": 0.65, "h": 0.12},
                                {"role": "cta", "x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0},
                            ],
                        },
                    }
                ],
            }
        },
        template_candidates=[],
        reference_assets=[],
    )

    slide = compiled["template_fit_brief"]["sequence_pack"]["slides"][0]
    assert slide["headline_hint"] == ""
    assert slide["sequence_summary"] == "cover hook"
    assert [zone["role"] for zone in slide["zone_map"]["zones"]] == ["headline"]


def test_context_compiler_uses_sequence_pack_slide_editorial_and_composition_fallbacks() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a premium LinkedIn carousel.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {},
            "audience_insights": {},
            "visual_identity": {},
        },
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png", "size": {"width": 1080, "height": 1350}},
        conversation_context={},
        session_memory={},
        layout_decision={"mode": "adapted_template"},
        template_context={
            "sequence_pack": {
                "family_name": "FLOATING-RATE-BONDS",
                "surface_policy": "style_reference_only",
                "slides": [
                    {
                        "slide_index": 1,
                        "template_name": "FLOATING-RATE-BONDS-1",
                        "zone_map": {
                            "layout_type": "infographic",
                            "zones": [
                                {"role": "logo", "x": 0.88, "y": 0.02, "w": 0.1, "h": 0.08},
                                {"role": "headline", "x": 0.05, "y": 0.1, "w": 0.65, "h": 0.12},
                                {"role": "image", "x": 0.55, "y": 0.75, "w": 0.4, "h": 0.2},
                            ],
                            "composition_logic": {"balance": "centered", "framing": "stacked_sections"},
                            "editorial_dna": {
                                "story_arc_roles": ["hook", "structure", "takeaway"],
                                "headline_patterns": ["Fixed or Floating Bonds?"],
                                "explanation_style": "stepwise_educational",
                                "closing_style": "cta_close",
                            },
                        },
                    }
                ],
            }
        },
        template_candidates=[],
        reference_assets=[],
    )

    template_fit = compiled["template_fit_brief"]
    assert template_fit["template_zone_roles"] == ["logo", "headline", "image"]
    assert template_fit["template_composition_logic"]["framing"] == "stacked_sections"
    assert template_fit["template_editorial_dna"]["story_arc_roles"] == ["hook", "structure", "takeaway"]
    assert template_fit["template_editorial_dna"]["explanation_styles"] == ["stepwise_educational"]
    compact_pack = ContextCompilerService._compact_sequence_pack(
        {
            "slides": [
                {
                    "slide_index": 1,
                    "story_role": "hook",
                    "zone_map": {
                        "composition_logic": {"balance": "centered", "framing": "stacked_sections"},
                        "editorial_dna": {
                            "story_arc_roles": ["hook", "structure", "takeaway"],
                            "explanation_style": "stepwise_educational",
                        },
                    },
                }
            ]
        }
    )
    assert compact_pack["story_roles"] == ["hook"]
    assert compact_pack["slides"][0]["composition_logic"]["framing"] == "stacked_sections"
    assert compact_pack["slides"][0]["editorial_dna"]["story_arc_roles"] == [
        "hook",
        "structure",
        "takeaway",
    ]


def test_context_compiler_builds_reference_family_profile_from_sample_and_brand_context() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a premium LinkedIn carousel.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {},
            "audience_insights": {},
            "visual_identity": {
                "design_system": {
                    "layout_preferences": {"preferred_zone_roles": ["headline", "hero_visual", "proof_points", "cta"]},
                    "visual_hierarchy": {"whitespace_preferences": ["generous spacing"]},
                    "content_structure": {"preferred_structures": ["editorial explainer"]},
                    "component_motifs": {"numbered_badges": True},
                }
            },
        },
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png", "size": {"width": 1080, "height": 1350}},
        conversation_context={},
        session_memory={},
        layout_decision={"mode": "adapted_template", "template_name": "Planning your retirement"},
        template_context={
            "sequence_pack": {
                "family_name": "RETIREMENT-ARC",
                "sequence_kind": "reference_pdf_blueprint",
                "surface_policy": "style_reference_only",
                "slides": [
                    {
                        "slide_index": 1,
                        "story_role": "hook",
                        "headline_hint": "Planning your retirement",
                        "zone_map": {
                            "layout_type": "editorial split",
                            "zones": [
                                {"role": "headline", "x": 0.05, "y": 0.08, "w": 0.4, "h": 0.12},
                                {"role": "hero_visual", "x": 0.52, "y": 0.1, "w": 0.32, "h": 0.34},
                                {"role": "proof_points", "x": 0.05, "y": 0.56, "w": 0.42, "h": 0.18},
                                {"role": "cta", "x": 0.05, "y": 0.82, "w": 0.24, "h": 0.08},
                            ],
                        },
                    }
                ],
            }
        },
        template_candidates=[],
        reference_assets=[],
        content_format_guide={
            "current_expectations": {
                "linkedin": {
                    "carousel": {
                        "preferred_slide_count": 5,
                        "format_definition": "premium carousel",
                    }
                }
            }
        },
    )

    profile = compiled["reference_family_profile"]
    assert profile["family_name"] == "RETIREMENT-ARC"
    assert profile["layout_lock_strength"] == "strong"
    assert profile["preferred_zone_roles"] == ["headline", "hero_visual", "proof_points", "cta"]
    assert "cover_hero_split" in profile["module_patterns"]
    assert profile["approved_image_zone_roles"] == ["hero_visual"]
    assert profile["slide_profiles"][0]["zone_roles"] == ["headline", "hero_visual", "proof_points", "cta"]
    assert profile["slide_profiles"][0]["zone_boxes"][0] == {
        "role": "headline",
        "x": 0.05,
        "y": 0.08,
        "w": 0.4,
        "h": 0.12,
        "alignment": "",
        "text_capacity": "",
    }


def test_context_compiler_builds_brand_foundations_from_current_schema_fields() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a premium investing post.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {
                "brand_promise": "Make fixed-income investing easier to trust and understand.",
                "human_insight": "Retail investors want steady returns without opaque jargon.",
                "brand_advantage": "Curated bond access with transparent framing.",
                "brand_mission": "Help everyday investors make calmer fixed-income decisions.",
                "brand_vision": "Become the most trusted retail fixed-income platform.",
            },
            "audience_insights": {},
            "visual_identity": {},
        },
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 2},
        session_memory={},
    )

    summary = compiled["brand_copy_brief"]["brand_foundations"]

    assert "Make fixed-income investing easier to trust and understand." in summary
    assert "Retail investors want steady returns without opaque jargon." in summary
    assert "Curated bond access with transparent framing." in summary


def test_context_compiler_prefers_current_schema_foundations_over_legacy_field() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a premium investing post.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {
                "brand_foundation": "Legacy foundation that should not override current schema data.",
                "brand_promise": "Make fixed-income investing easier to trust and understand.",
                "human_insight": "Retail investors want steady returns without opaque jargon.",
            },
            "audience_insights": {},
            "visual_identity": {},
        },
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 2},
        session_memory={},
    )

    summary = compiled["brand_copy_brief"]["brand_foundations"]

    assert "Make fixed-income investing easier to trust and understand." in summary
    assert "Retail investors want steady returns without opaque jargon." in summary
    assert "Legacy foundation that should not override" not in summary


def test_context_compiler_brand_foundations_summary_cleans_punctuation() -> None:
    summary = ContextCompilerService._brand_foundations_summary(
        {
            "brand_promise": "Make fixed-income investing easier to trust and understand.",
            "human_insight": "Retail investors want steady returns without opaque jargon...",
            "brand_advantage": "Curated bond access with transparent framing. ",
        }
    )

    assert ".." not in summary
    assert summary.endswith(".")


def test_context_compiler_brand_foundations_summary_stops_on_sentence_boundary() -> None:
    summary = ContextCompilerService._brand_foundations_summary(
        {
            "brand_promise": "Make fixed-income investing easier to trust and understand.",
            "human_insight": "Retail investors want steady returns without opaque jargon.",
            "brand_advantage": "Curated bond access with transparent framing and calm guidance.",
            "market_positioning": "Legacy mismatch should never silently override clearer schema-driven messaging.",
        }
    )

    assert len(summary) <= 220
    assert summary.endswith(".")
    assert "Legacy mismatch should never silently override" not in summary


def test_context_compiler_builds_prompt_intelligence_brief_for_current_platform() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create an Instagram post about fixed-income confidence.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {},
            "prompt_intelligence": {
                "prompt_starters": [
                    {
                        "prompt": "Lead with the investor outcome.",
                        "platforms": ["Instagram Post"],
                        "notes": "Hook first and keep the first line compact.",
                    },
                    {
                        "prompt": "Open with category credibility.",
                        "platforms": ["LinkedIn"],
                    },
                ],
                "platform_rules": {
                    "Instagram Post": {"rules": ["Keep on-canvas text compact.", "Use a short CTA."]},
                    "global": {"dos": ["Anchor the first line in one clear benefit."]},
                },
            },
            "audience_insights": {},
            "visual_identity": {},
        },
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 2},
        session_memory={},
    )

    brief = compiled["prompt_intelligence_brief"]

    assert brief["platform_preset"] == "instagram"
    assert brief["starter_texts"] == ["Lead with the investor outcome."]
    assert "Keep on-canvas text compact" in brief["current_platform_rules"][0]
    assert any("Anchor the first line in one clear benefit" in item for item in brief["global_rules"])


def test_context_compiler_normalizes_prompt_intelligence_legacy_shapes() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create an Instagram post about fixed-income confidence.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {},
            "prompt_intelligence": {
                "prompt_starters": {
                    "Instagram Post": [{"prompt": "Start with the outcome."}],
                    "LinkedIn": [{"prompt": "Lead with category credibility."}],
                },
                "platform_rules": {
                    "by_platform": {"Instagram Post": ["Keep the text compact."]},
                    "General": {"notes": "Prefer one clean benefit before proof."},
                },
            },
            "audience_insights": {},
            "visual_identity": {},
        },
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 2},
        session_memory={},
    )

    brief = compiled["prompt_intelligence_brief"]

    assert brief["starter_texts"] == ["Start with the outcome."]
    assert brief["current_platform_rules"] == ["Keep the text compact"]
    assert any("Prefer one clean benefit before proof" in item for item in brief["global_rules"])


def test_context_compiler_builds_content_format_brief_for_current_platform_and_format() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create an Instagram carousel about fixed-income confidence.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {},
            "audience_insights": {},
            "visual_identity": {},
        },
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "instagram", "format": "carousel", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 2},
        session_memory={},
        content_format_guide={
            "source_path": "docs/guide.docx",
            "summary": "Use format-aware storytelling for social outputs.",
            "definitions": {
                "carousel": "A carousel is a multi-slide, swipeable post for storytelling.",
            },
            "format_expectations": {
                "carousel": {
                    "structure": ["Slide 1: Hook", "Slides 2-4: One idea per slide", "Final slide: CTA"],
                    "quality_priorities": ["Strong narrative flow.", "One idea per slide."],
                    "preferred_slide_count": 5,
                }
            },
            "platform_guidance": {
                "instagram": {
                    "summary": "Instagram carousels should feel scan-friendly and image-native.",
                    "notes": ["Carousel: Up to 10 slides, 1:1 or 4:5", "Prefer scan-friendly hierarchy."],
                }
            },
            "export_guidance": {
                "lines": ["Instagram Carousel: Multiple PNGs or ZIP"],
                "by_platform_format": {"instagram": {"carousel": "Multiple PNGs or ZIP"}},
            },
            "key_insights": ["Each format serves a different purpose and should fit audience behavior."],
        },
    )

    brief = compiled["content_format_brief"]

    assert brief["platform_preset"] == "instagram"
    assert brief["format"] == "carousel"
    assert "multi-slide, swipeable post" in brief["format_definition"]
    assert "Slide 1: Hook" in brief["format_rules"][0]


def test_context_compiler_preserves_format_family_plan() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a LinkedIn carousel.",
        brand_context={},
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={},
        session_memory={},
        format_family_plan={
            "family": "carousel",
            "deliverable_type": "linkedin_post",
            "format": "carousel",
            "platform_preset": "linkedin",
            "primary_unit": "slide",
            "body_shape": "multi_slide_sequence",
            "outline_mode": "sequenced",
            "content_structure": ["cover", "progressive_detail_slides", "closing_takeaway_or_cta"],
            "required_components": ["headline", "body", "cta", "carousel_slide_specs"],
            "optional_components": ["proof_points", "stat_highlights"],
            "copy_density": "distributed",
            "visual_density": "multi_panel_story",
            "metadata_fields": ["carousel_slide_specs", "proof_points"],
            "planning_rules": ["Plan a real slide sequence."],
            "preferred_slide_count": 6,
            "notes": ["Plan a true slide-by-slide sequence with distinct beats."],
        },
    )

    plan = compiled["format_family_plan"]

    assert plan["family"] == "carousel"
    assert plan["primary_unit"] == "slide"
    assert plan["outline_mode"] == "sequenced"
    assert plan["preferred_slide_count"] == 6
    assert "carousel_slide_specs" in plan["required_components"]
    assert "proof_points" in plan["metadata_fields"]
    assert any("slide sequence" in item.casefold() for item in plan["planning_rules"])


def test_context_compiler_omits_content_format_brief_when_guide_missing() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create an Instagram static post about fixed-income confidence.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {},
            "audience_insights": {},
            "visual_identity": {},
        },
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 2},
        session_memory={},
    )

    assert compiled["content_format_brief"] == {}


def test_context_compiler_preserves_research_editorial_brief() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Explain why the latest policy change matters.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {},
            "audience_insights": {},
            "visual_identity": {},
        },
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "pdf", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 1},
        session_memory={},
        research_editorial_brief={
            "active": True,
            "mode": "research_editorial",
            "topic_focus": "latest policy change",
            "angle": "Go beyond the headline and explain the structure.",
            "thesis": "Policy change: explain the structure and implications.",
            "reader_payoff": "Reader should understand why it matters.",
            "hook_strategy": "Open with the undercovered angle.",
            "insight_hierarchy": ["What changed", "Why it matters"],
            "outline": [
                {"index": "1", "role": "hook", "purpose": "Open strong", "notes": "Use the tension point."},
            ],
            "source_pack": [
                {"type": "verified_fact", "label": "Date", "detail": "6 May 2026", "source": "Official source"},
            ],
            "source_count": 1,
            "summary": "Go beyond the headline and explain the implications.",
        },
    )

    brief = compiled["research_editorial_brief"]

    assert brief["active"] is True
    assert brief["mode"] == "research_editorial"
    assert brief["topic_focus"] == "latest policy change"
    assert brief["outline"][0]["role"] == "hook"
    assert brief["source_pack"][0]["label"] == "Date"


def test_context_compiler_preserves_persona_depth_in_copy_and_audience_briefs() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create an Instagram post about fixed-income confidence.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {},
            "audience_insights": {},
            "visual_identity": {},
        },
        persona_context={
            "name": "Mass Affluent Investor",
            "role": "investor",
            "audience_goals": ["Earn steadier returns than deposits."],
            "motivations": ["Grow idle money without feeling reckless."],
            "fears_and_pain_points": ["Worries fixed-income products will feel opaque."],
            "objections": ["Needs proof that returns and risk are explained clearly."],
            "content_behavior": {
                "preferred_platforms": ["Instagram", "LinkedIn"],
                "preferred_formats": ["Explainers", "Carousels"],
            },
            "language_preference": "plain English",
        },
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 2},
        session_memory={},
    )

    copy_brief = compiled["brand_copy_brief"]
    audience_brief = compiled["audience_brief"]

    assert copy_brief["persona_name"] == "Mass Affluent Investor"
    assert copy_brief["persona_role"] == "investor"
    assert copy_brief["persona_motivations"] == ["Grow idle money without feeling reckless."]
    assert copy_brief["persona_pain_points"] == ["Worries fixed-income products will feel opaque."]
    assert copy_brief["persona_objections"] == ["Needs proof that returns and risk are explained clearly."]
    assert copy_brief["persona_language_preference"] == "plain English"
    assert any("preferred platforms: Instagram, LinkedIn" in item for item in copy_brief["persona_content_behavior"])
    assert "Grow idle money without feeling reckless." in copy_brief["persona_messaging_summary"]

    assert audience_brief["motivations"] == []
    assert audience_brief["pain_points"] == []
    assert audience_brief["objections"] == []
    assert audience_brief["persona_motivations"] == ["Grow idle money without feeling reckless."]
    assert audience_brief["persona_pain_points"] == ["Worries fixed-income products will feel opaque."]
    assert audience_brief["persona_objections"] == ["Needs proof that returns and risk are explained clearly."]
    assert audience_brief["language_preference"] == "plain English"
    assert audience_brief["persona_language_preference"] == "plain English"
    assert audience_brief["behaviors"] == []
    assert any("preferred platforms: Instagram, LinkedIn" in item for item in audience_brief["persona_behaviors"])
    assert audience_brief["research_summary"] == ""
    assert audience_brief["persona_summary"]
    assert audience_brief["signal_weights"] == {"audience_research": 1.0, "persona_defaults": 0.7}


def test_context_compiler_keeps_audience_research_and_persona_signal_lanes_separate() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create an Instagram post about fixed-income confidence.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {},
            "audience_insights": {
                "segments": [{"label": "Mass Affluent Investor"}],
                "behaviors": ["Compares options before committing."],
                "motivations": ["Needs steady income without unnecessary complexity."],
                "desired_outcomes": ["Earn predictable income without feeling reckless."],
                "pain_points": ["Finds category language opaque."],
                "objections": ["Needs proof that risk is explained clearly."],
                "preferences": ["Credible comparisons over hype."],
                "trust_signals": ["Transparent downside framing builds confidence."],
                "proof_cues": ["Concrete proof beats abstract trust language when comparing deposits with fixed-income options."],
                "comparison_points": ["Trade-off clarity beats vague category confidence."],
                "research_summary": (
                    "Investors respond better when risk is explained in plain English with downside clarity."
                ),
            },
            "visual_identity": {},
        },
        persona_context={
            "name": "Mass Affluent Investor",
            "role": "investor",
            "audience_goals": ["Grow wealth without sleepless volatility."],
            "motivations": ["Grow idle money without feeling reckless."],
            "fears_and_pain_points": ["Worries fixed-income products will feel opaque."],
            "objections": ["Does not want hidden downside surprises."],
            "content_behavior": {
                "preferred_platforms": ["Instagram", "LinkedIn"],
                "preferred_formats": ["Explainers", "Carousels"],
            },
            "language_preference": "plain English",
        },
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 2},
        session_memory={},
    )

    audience_brief = compiled["audience_brief"]

    assert audience_brief["motivations"] == ["Needs steady income without unnecessary complexity."]
    assert audience_brief["pain_points"] == ["Finds category language opaque."]
    assert audience_brief["objections"] == ["Needs proof that risk is explained clearly."]
    assert audience_brief["behaviors"] == ["Compares options before committing."]
    assert audience_brief["persona_motivations"] == ["Grow idle money without feeling reckless."]
    assert audience_brief["persona_pain_points"] == ["Worries fixed-income products will feel opaque."]
    assert audience_brief["persona_objections"] == ["Does not want hidden downside surprises."]
    assert any("preferred platforms: Instagram, LinkedIn" in item for item in audience_brief["persona_behaviors"])
    assert "Grow idle money without feeling reckless." not in audience_brief["research_summary"]
    assert "downside clarity" in audience_brief["research_summary"]
    assert audience_brief["signal_priority_note"].startswith("Prefer research-backed audience lanes")


def test_context_compiler_preserves_audience_research_highlights_without_collapsing_them() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create an Instagram post about fixed-income confidence.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {},
            "audience_insights": {
                "segments": [{"label": "Mass Affluent Investor"}],
                "motivations": ["Needs steady income without unnecessary complexity."],
                "desired_outcomes": ["Earn predictable income without feeling reckless."],
                "pain_points": ["Finds category language opaque."],
                "objections": ["Needs proof that risk is explained clearly."],
                "preferences": ["Credible comparisons over hype."],
                "trust_signals": ["Transparent downside framing builds confidence."],
                "proof_cues": ["Concrete proof beats abstract trust language when comparing deposits with fixed-income options."],
                "comparison_points": ["Trade-off clarity beats vague category confidence."],
                "research_summary": (
                    "Investors respond better when risk is explained in plain English with downside clarity. "
                    "Concrete proof beats abstract trust language."
                ),
                "research_summaries": [
                    "Investors respond better when risk is explained in plain English with downside clarity.",
                    "Concrete proof beats abstract trust language when comparing deposits with fixed-income options.",
                    "Category credibility improves when the message names the trade-off instead of hiding it.",
                ],
                "research_signal_count": 3,
            },
            "visual_identity": {},
        },
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 2},
        session_memory={},
    )

    audience_brief = compiled["audience_brief"]

    assert audience_brief["research_signal_count"] == 3
    assert audience_brief["research_highlights"] == [
        "Concrete proof beats abstract trust language when comparing deposits with fixed-income options.",
        "Transparent downside framing builds confidence.",
        "Trade-off clarity beats vague category confidence.",
        "Needs proof that risk is explained clearly.",
        "Earn predictable income without feeling reckless.",
        "Investors respond better when risk is explained in plain English with downside clarity.",
    ]
    assert audience_brief["desired_outcomes"] == ["Earn predictable income without feeling reckless."]
    assert audience_brief["objections"] == ["Needs proof that risk is explained clearly."]
    assert audience_brief["trust_signals"] == ["Transparent downside framing builds confidence."]
    assert audience_brief["proof_cues"] == ["Concrete proof beats abstract trust language when comparing deposits with fixed-income options."]
    assert audience_brief["comparison_points"] == ["Trade-off clarity beats vague category confidence."]
    assert "Concrete proof beats abstract trust language" in audience_brief["research_summary"]
    assert "Trade-off clarity beats vague category confidence." in audience_brief["research_summary"]


def test_context_compiler_merges_structured_research_evidence_with_summary_highlights() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create an Instagram post about fixed-income confidence.",
        brand_context={
            "brand_name": "Jiraaf",
            "voice_tone": {},
            "guardrails": {},
            "foundations": {},
            "audience_insights": {
                "research_highlights": [
                    "Investors engage more when the copy explains trade-offs in plain English.",
                    "Messages feel safer when they sound measured rather than promotional.",
                ],
                "research_evidence": [
                    {
                        "field": "proof_cues",
                        "value": "Specific return-versus-deposit comparisons increase credibility.",
                        "source_snippet": "Specific return-versus-deposit comparisons increase credibility.",
                        "confidence": 0.94,
                    },
                    {
                        "field": "trust_signals",
                        "value": "Named downside scenarios reduce perceived hype.",
                        "source_snippet": "Named downside scenarios reduce perceived hype.",
                        "confidence": 0.89,
                    },
                ],
                "objections": ["Rejects messaging that sounds too optimistic."],
            },
            "visual_identity": {},
        },
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 2},
        session_memory={},
    )

    audience_brief = compiled["audience_brief"]

    assert audience_brief["research_highlights"] == [
        "Specific return-versus-deposit comparisons increase credibility.",
        "Investors engage more when the copy explains trade-offs in plain English.",
        "Named downside scenarios reduce perceived hype.",
        "Messages feel safer when they sound measured rather than promotional.",
        "Rejects messaging that sounds too optimistic.",
    ]


def test_context_compiler_omits_prior_headline_for_new_content_prompts() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a new Instagram post about lower flight fares.",
        brand_context={"brand_name": "Jiraaf", "voice_tone": {}, "guardrails": {}, "foundations": {}, "audience_insights": {}, "visual_identity": {}},
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 6},
        session_memory={
            "follow_up_intent": {"mode": "new_content", "uses_previous_output": False},
            "latest_content_version": {"headline": "Why Investors Are Moving Beyond FDs in 2026"},
        },
    )

    assert compiled["session_brief"]["follow_up_mode"] == "new_content"
    assert compiled["session_brief"]["prior_headline"] == ""
    assert compiled["brand_copy_brief"]["prior_headline"] == ""


def test_context_compiler_preserves_prior_headline_for_true_follow_ups() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Make the previous one shorter.",
        brand_context={"brand_name": "Jiraaf", "voice_tone": {}, "guardrails": {}, "foundations": {}, "audience_insights": {}, "visual_identity": {}},
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 6},
        session_memory={
            "follow_up_intent": {"mode": "modify_previous", "uses_previous_output": True},
            "latest_content_version": {"headline": "Why Investors Are Moving Beyond FDs in 2026"},
        },
    )

    assert compiled["session_brief"]["follow_up_mode"] == "modify_previous"
    assert compiled["session_brief"]["prior_headline"] == "Why Investors Are Moving Beyond FDs in 2026"
    assert compiled["brand_copy_brief"]["prior_headline"] == "Why Investors Are Moving Beyond FDs in 2026"


def test_context_compiler_includes_prior_layout_archetype_for_variants() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Regenerate this with a different layout.",
        brand_context={"brand_name": "Jiraaf", "voice_tone": {}, "guardrails": {}, "foundations": {}, "audience_insights": {}, "visual_identity": {}},
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 8},
        session_memory={
            "follow_up_intent": {"mode": "variant_of_previous", "uses_previous_output": True},
            "latest_content_version": {
                "headline": "Why Investors Are Moving Beyond FDs in 2026",
                "scene_graph": {"styles": {"layout_archetype": "wide_editorial_split"}},
            },
        },
    )

    assert compiled["session_brief"]["follow_up_mode"] == "variant_of_previous"
    assert compiled["session_brief"]["prior_layout_archetype"] == "wide_editorial_split"
    assert "distinctly different layout archetype" in compiled["session_brief"]["regeneration_policy"]


def test_context_compiler_respects_explicit_request_lineage_over_follow_up_memory() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a new carousel about Census 2027.",
        brand_context={"brand_name": "Jiraaf", "voice_tone": {}, "guardrails": {}, "foundations": {}, "audience_insights": {}, "visual_identity": {}},
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 8},
        session_memory={
            "follow_up_intent": {"mode": "variant_of_previous", "uses_previous_output": True},
            "request_lineage": {
                "request_mode": "new_content",
                "inheritance_policy": {
                    "inherit_copy_context": False,
                    "inherit_layout_context": False,
                },
            },
            "latest_content_version": {
                "headline": "What's really inside the India-New Zealand Free Trade Deal?",
                "scene_graph": {"styles": {"layout_archetype": "wide_editorial_split"}},
            },
        },
    )

    assert compiled["session_brief"]["follow_up_mode"] == "variant_of_previous"
    assert compiled["session_brief"]["prior_headline"] == ""
    assert compiled["session_brief"]["prior_layout_archetype"] == ""
    assert compiled["brand_copy_brief"]["prior_headline"] == ""


def test_context_compiler_filters_noisy_knowledge_and_prefers_clean_entries() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a new Instagram post about digital gold.",
        brand_context={"brand_name": "Jiraaf", "voice_tone": {}, "guardrails": {}, "foundations": {}, "audience_insights": {}, "visual_identity": {}},
        persona_context={},
        objective_context={},
        ordered_knowledge={
            "visual_identity": [
                {"content": "PRIMARY FONT A B C D E F G H I J K L M N O P Q R S T U V W X Y Z Bold CONDENSED 01 02 03 04 05 06 07 08 09 H1 H2 H3"},
                {"content": "Iconography uses blue and yellow fill-and-stroke forms with a restrained premium finance aesthetic."},
                {"content": "The visual system favors clean spacing, calm geometry, and a trustworthy editorial balance."},
            ],
            "mood_board": [
                {"content": "Visual language uses curves, arrows, and circles derived from the logo to extend the brand system."},
            ],
        },
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 4},
        session_memory={},
    )

    brief = compiled["knowledge_brief"]
    visual_brief = compiled["visual_knowledge_brief"]
    visual_items = visual_brief["items"]

    assert len(brief) == 3
    assert visual_brief["grounding_mode"] == "brand_knowledge"
    assert len(visual_items) == 3
    assert all("PRIMARY FONT A B C D" not in item["content"] for item in brief)
    assert all("PRIMARY FONT A B C D" not in item["content"] for item in visual_items)
    assert any("Iconography uses blue and yellow fill-and-stroke forms" in item["content"] for item in brief)
    assert any("Visual language uses curves, arrows, and circles derived from the logo" in item["content"] for item in brief)
    assert any(item["channel"] == "visual_identity" for item in visual_items)
    assert any(item["channel"] == "mood_board" for item in visual_items)


def test_context_compiler_visual_knowledge_brief_suppresses_template_when_primary_visual_evidence_exists() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a premium investing visual.",
        brand_context={"brand_name": "Jiraaf", "voice_tone": {}, "guardrails": {}, "foundations": {}, "audience_insights": {}, "visual_identity": {}},
        persona_context={},
        objective_context={},
        ordered_knowledge={
            "template": [
                {"content": "A polished poster template with a headline about moving from FDs to bonds."},
            ],
            "visual_identity": [
                {"content": "The brand uses deep blue and warm yellow iconography with clean spacing and premium restraint."},
            ],
            "mood_board": [
                {"content": "Compositions favor editorial balance, calm negative space, and curved motion cues."},
            ],
        },
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 4},
        session_memory={},
    )

    visual_brief = compiled["visual_knowledge_brief"]
    visual_items = visual_brief["items"]

    assert visual_brief["template_suppressed"] is True
    assert any(item["channel"] == "visual_identity" for item in visual_items)
    assert any(item["channel"] == "mood_board" for item in visual_items)
    assert all(item["channel"] != "template" for item in visual_items)


def test_context_compiler_visual_knowledge_brief_uses_template_only_as_fallback() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a premium investing visual.",
        brand_context={"brand_name": "Jiraaf", "voice_tone": {}, "guardrails": {}, "foundations": {}, "audience_insights": {}, "visual_identity": {}},
        persona_context={},
        objective_context={},
        ordered_knowledge={
            "reference_creative": [
                {"content": "Reference creatives favor structured editorial compositions and trusted financial cues."},
            ],
            "template": [
                {"content": "A polished poster template with a headline about moving from FDs to bonds."},
            ],
        },
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 4},
        session_memory={},
    )

    visual_brief = compiled["visual_knowledge_brief"]
    visual_items = visual_brief["items"]

    assert visual_brief["template_suppressed"] is False
    assert visual_brief["grounding_mode"] == "brand_knowledge"
    assert any(item["channel"] == "reference_creative" for item in visual_items)
    assert any(item["channel"] == "template" for item in visual_items)


def test_context_compiler_prefers_structured_visual_hits_and_dedupes_same_source() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a premium investing visual about barbell strategy.",
        brand_context={"brand_name": "Jiraaf", "voice_tone": {}, "guardrails": {}, "foundations": {}, "audience_insights": {}, "visual_identity": {}},
        persona_context={},
        objective_context={},
        ordered_knowledge={
            "visual_identity": [
                {
                    "content": "Why Investors Are Moving From FDs To Bonds In 2025 with premium poster layout and headline body CTA.",
                    "score": 0.22,
                    "metadata": {
                        "source_id": "asset-1",
                        "document_type": "raw_ocr",
                        "validation_state": "clean",
                        "classification_confidence": 0.96,
                    },
                },
                {
                    "content": "Category color_palette. Palette cues: primary #003975, secondary #FFA400. Typography cues: Inter, Roboto. Reusable zones: headline, image, cta.",
                    "score": 0.35,
                    "metadata": {
                        "source_id": "asset-1",
                        "document_type": "structured_summary",
                        "validation_state": "clean",
                        "classification_confidence": 0.96,
                        "structured_signal_score": 6,
                    },
                },
                {
                    "content": "The brand uses deep blue and warm yellow iconography with calm spacing and premium editorial balance.",
                    "score": 0.28,
                    "metadata": {
                        "source_id": "asset-2",
                        "document_type": "structured_summary",
                        "validation_state": "clean",
                        "classification_confidence": 0.92,
                        "structured_signal_score": 5,
                    },
                },
            ],
        },
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 4},
        session_memory={},
    )

    visual_brief = compiled["visual_knowledge_brief"]
    contents = [item["content"] for item in visual_brief["items"]]

    assert any("Palette cues: primary #003975" in content for content in contents)
    assert any("deep blue and warm yellow iconography" in content for content in contents)
    assert not any("Why Investors Are Moving From FDs To Bonds In 2025" in content for content in contents)


def test_context_compiler_penalizes_low_quality_promotional_ocr_against_structured_visual_summary() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a premium investing visual about bond ladders.",
        brand_context={"brand_name": "Jiraaf", "voice_tone": {}, "guardrails": {}, "foundations": {}, "audience_insights": {}, "visual_identity": {}},
        persona_context={},
        objective_context={},
        ordered_knowledge={
            "visual_identity": [
                {
                    "content": "Apply now to discover high yield bond ladders for 2026. Learn more today.",
                    "score": 0.14,
                    "metadata": {
                        "source_id": "asset-ocr",
                        "document_type": "raw_ocr",
                        "validation_state": "clean",
                        "classification_confidence": 0.94,
                        "analysis_quality_score": 3.1,
                        "summary_quality_score": 2.4,
                        "ocr_signal_score": 2.8,
                        "ocr_noise_ratio": 0.72,
                        "promotional_line_ratio": 0.9,
                        "evidence_types": ["visual_system"],
                    },
                },
                {
                    "content": "Palette system: primary #003975, secondary #FFA400. Typography system: Inter, Manrope. Layout system: editorial split with headline, illustration, cta.",
                    "score": 0.33,
                    "metadata": {
                        "source_id": "asset-structured",
                        "document_type": "structured_layout",
                        "validation_state": "clean",
                        "classification_confidence": 0.91,
                        "structured_signal_score": 6,
                        "analysis_quality_score": 8.8,
                        "summary_quality_score": 8.1,
                        "ocr_signal_score": 7.3,
                        "ocr_noise_ratio": 0.08,
                        "promotional_line_ratio": 0.0,
                        "evidence_types": ["layout", "palette", "typography"],
                    },
                },
            ],
        },
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 4},
        session_memory={},
    )

    visual_brief = compiled["visual_knowledge_brief"]

    assert visual_brief["items"][0]["content"].startswith("Palette system: primary #003975")
    assert not any("Apply now" in item["content"] for item in visual_brief["items"])


def test_context_compiler_excludes_template_copy_documents_from_visual_grounding() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a premium investing visual about bond ladders.",
        brand_context={"brand_name": "Jiraaf", "voice_tone": {}, "guardrails": {}, "foundations": {}, "audience_insights": {}, "visual_identity": {}},
        persona_context={},
        objective_context={},
        ordered_knowledge={
            "template": [
                {
                    "content": "Template copy cues: Why Investors Are Moving From FDs To Bonds In 2026, Apply now.",
                    "score": 0.11,
                    "metadata": {
                        "source_id": "asset-template-copy",
                        "document_type": "structured_template_copy",
                        "validation_state": "clean",
                        "classification_confidence": 0.97,
                        "visual_grounding_allowed": False,
                    },
                },
                {
                    "content": "Layout system: editorial split. Zones: headline, illustration, cta.",
                    "score": 0.29,
                    "metadata": {
                        "source_id": "asset-template-structure",
                        "document_type": "structured_layout",
                        "validation_state": "clean",
                        "classification_confidence": 0.9,
                        "structured_signal_score": 4,
                    },
                },
            ],
        },
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 4},
        session_memory={},
    )

    visual_brief = compiled["visual_knowledge_brief"]
    knowledge_brief = compiled["knowledge_brief"]

    assert visual_brief["grounding_strength"] == "fallback_only"
    assert any(item["content"].startswith("Layout system: editorial split") for item in visual_brief["items"])
    assert not any("Why Investors Are Moving From FDs To Bonds In 2026" in item["content"] for item in visual_brief["items"])
    assert any("Why Investors Are Moving From FDs To Bonds In 2026" in item["content"] for item in knowledge_brief)


def test_context_compiler_visual_knowledge_brief_abstains_when_only_weak_visual_candidates_exist() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a premium investing visual.",
        brand_context={"brand_name": "Jiraaf", "voice_tone": {}, "guardrails": {}, "foundations": {}, "audience_insights": {}, "visual_identity": {}},
        persona_context={},
        objective_context={},
        ordered_knowledge={
            "visual_identity": [
                {
                    "content": "Apply now to unlock premium returns today.",
                    "score": 0.12,
                    "metadata": {
                        "source_id": "asset-weak-ocr",
                        "document_type": "raw_ocr",
                        "validation_state": "clean",
                        "classification_confidence": 0.93,
                        "analysis_quality_score": 3.2,
                        "summary_quality_score": 2.8,
                        "source_agreement_score": 0.0,
                        "structured_signal_score": 0.0,
                        "visual_grounding_line_count": 0,
                        "ocr_noise_ratio": 0.62,
                        "promotional_line_ratio": 0.95,
                        "evidence_types": ["visual_system"],
                    },
                },
            ],
        },
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 4},
        session_memory={},
    )

    visual_brief = compiled["visual_knowledge_brief"]

    assert visual_brief["grounding_mode"] == "llm_fallback"
    assert visual_brief["items"] == []
    assert visual_brief["candidate_count"] == 1
    assert visual_brief["abstention_reason"] == "quality_below_channel_floor"
    assert visual_brief["excluded_candidate_count"] >= 1
    assert visual_brief["rejection_reasons"]["quality_below_channel_floor"] >= 1


def test_context_compiler_visual_knowledge_brief_accepts_structured_visual_unit_with_strong_structure() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a premium investing visual.",
        brand_context={"brand_name": "Jiraaf", "voice_tone": {}, "guardrails": {}, "foundations": {}, "audience_insights": {}, "visual_identity": {}},
        persona_context={},
        objective_context={},
        ordered_knowledge={
            "visual_identity": [
                {
                    "content": "Palette system: primary #003975, secondary #FFA400. Typography system: Manrope with editorial headline hierarchy.",
                    "score": 0.24,
                    "metadata": {
                        "source_id": "asset-visual-unit",
                        "document_type": "structured_visual_unit",
                        "validation_state": "clean",
                        "classification_confidence": 0.95,
                        "analysis_quality_score": 6.7,
                        "summary_quality_score": 6.3,
                        "source_agreement_score": 0.0,
                        "structured_signal_score": 4.0,
                        "visual_grounding_line_count": 0,
                        "ocr_noise_ratio": 0.0,
                        "promotional_line_ratio": 0.0,
                        "evidence_types": ["palette", "typography"],
                    },
                },
            ],
        },
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 4},
        session_memory={},
    )

    visual_brief = compiled["visual_knowledge_brief"]

    assert visual_brief["grounding_mode"] == "brand_knowledge"
    assert visual_brief["abstention_reason"] == ""
    assert visual_brief["items"][0]["document_type"] == "structured_visual_unit"
    assert visual_brief["items"][0]["content"].startswith("Palette system: primary #003975")


def test_context_compiler_visual_grounding_thresholds_are_runtime_configurable() -> None:
    compiler = ContextCompilerService()
    settings = get_settings()
    original_overrides = settings.visual_grounding_threshold_overrides_json
    settings.visual_grounding_threshold_overrides_json = (
        '{"visual_identity":{"min_structured_signal_score":5.0}}'
    )
    try:
        compiled = compiler.compile(
            prompt="Create a premium investing visual.",
            brand_context={"brand_name": "Jiraaf", "voice_tone": {}, "guardrails": {}, "foundations": {}, "audience_insights": {}, "visual_identity": {}},
            persona_context={},
            objective_context={},
            ordered_knowledge={
                "visual_identity": [
                    {
                        "content": "Palette system: primary #003975, secondary #FFA400. Typography system: Manrope with editorial headline hierarchy.",
                        "score": 0.24,
                        "metadata": {
                            "source_id": "asset-visual-unit",
                            "document_type": "structured_visual_unit",
                            "validation_state": "clean",
                            "classification_confidence": 0.95,
                            "analysis_quality_score": 6.7,
                            "summary_quality_score": 6.3,
                            "source_agreement_score": 0.0,
                            "structured_signal_score": 4.0,
                            "visual_grounding_line_count": 0,
                            "ocr_noise_ratio": 0.0,
                            "promotional_line_ratio": 0.0,
                            "evidence_types": ["palette", "typography"],
                        },
                    },
                ],
            },
            studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
            conversation_context={"message_count": 4},
            session_memory={},
        )
    finally:
        settings.visual_grounding_threshold_overrides_json = original_overrides

    visual_brief = compiled["visual_knowledge_brief"]

    assert visual_brief["grounding_mode"] == "llm_fallback"
    assert visual_brief["abstention_reason"] == "weak_cross_source_evidence"
    assert visual_brief["thresholds_used"]["visual_identity"]["min_structured_signal_score"] == 5.0
    assert visual_brief["rejection_reasons"]["weak_cross_source_evidence"] >= 1


def test_context_compiler_can_require_quality_metadata_dynamically() -> None:
    settings = get_settings()
    original_requirement = settings.visual_grounding_require_quality_metadata
    settings.visual_grounding_require_quality_metadata = True
    try:
        brief = ContextCompilerService.coerce_visual_knowledge_brief(
            [
                {
                    "channel": "visual_identity",
                    "content": "Use deep blue and warm yellow with calm editorial spacing.",
                    "document_type": "structured_summary",
                }
            ]
        )
    finally:
        settings.visual_grounding_require_quality_metadata = original_requirement

    assert brief["grounding_mode"] == "llm_fallback"
    assert brief["quality_metadata_policy"] == "required"
    assert brief["missing_quality_metadata_count"] == 1
    assert brief["rejection_reasons"]["missing_quality_metadata"] == 1


def test_context_compiler_preserves_existing_visual_brief_under_required_metadata_mode() -> None:
    settings = get_settings()
    original_requirement = settings.visual_grounding_require_quality_metadata
    settings.visual_grounding_require_quality_metadata = True
    try:
        brief = ContextCompilerService.coerce_visual_knowledge_brief(
            {
                "gate_version": "v3",
                "quality_metadata_policy": "compatibility_mode",
                "candidate_count": 1,
                "items": [
                    {
                        "channel": "visual_identity",
                        "role": "primary",
                        "document_type": "structured_summary",
                        "content": "Use deep blue and warm yellow with calm editorial spacing.",
                    }
                ],
            }
        )
    finally:
        settings.visual_grounding_require_quality_metadata = original_requirement

    assert brief["grounding_mode"] == "brand_knowledge"
    assert brief["items"][0]["content"].startswith("Use deep blue and warm yellow")


def test_context_compiler_emits_visual_grounding_diagnostics_in_compiled_context() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a premium investing visual.",
        brand_context={"brand_name": "Jiraaf", "voice_tone": {}, "guardrails": {}, "foundations": {}, "audience_insights": {}, "visual_identity": {}},
        persona_context={},
        objective_context={},
        ordered_knowledge={
            "visual_identity": [
                {
                    "content": "Palette system: primary #003975, secondary #FFA400. Typography system: Manrope with editorial headline hierarchy.",
                    "score": 0.24,
                    "metadata": {
                        "source_id": "asset-visual-unit",
                        "document_type": "structured_visual_unit",
                        "validation_state": "clean",
                        "classification_confidence": 0.95,
                        "analysis_quality_score": 6.7,
                        "summary_quality_score": 6.3,
                        "source_agreement_score": 0.0,
                        "structured_signal_score": 4.0,
                        "visual_grounding_line_count": 0,
                        "ocr_noise_ratio": 0.0,
                        "promotional_line_ratio": 0.0,
                        "evidence_types": ["palette", "typography"],
                    },
                },
            ],
        },
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png", "size": {"width": 1080, "height": 1080}},
        conversation_context={"message_count": 4},
        session_memory={},
    )

    diagnostics = compiled["visual_grounding_diagnostics"]

    assert diagnostics["grounding_mode"] == "brand_knowledge"
    assert diagnostics["gate_version"]
    assert diagnostics["quality_metadata_policy"] == "compatibility_mode"
    assert diagnostics["candidate_count"] == 1


def test_context_compiler_preserves_research_editorial_fact_model() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Analyze the trade agreement implications.",
        brand_context={"brand_name": "Jiraaf"},
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "pdf"},
        conversation_context={},
        session_memory={},
        research_editorial_brief={
            "active": True,
            "mode": "research_editorial",
            "format_family": "carousel",
            "topic_focus": "India-New Zealand FTA",
            "fact_model": {
                "verified_facts": [
                    {
                        "label": "Signing date",
                        "value": "27 April 2026",
                        "source_title": "Official release",
                        "source_url": "https://example.com/release",
                    }
                ],
                "inferences": ["The structure suggests a phased opening."],
                "uncertainties": ["Implementation timing may still shift."],
            },
            "ranked_sources": [
                {
                    "label": "Official release",
                    "detail": "Rank 1; supports 2 verified fact(s).",
                    "source": "https://example.com/release",
                }
            ],
            "citation_rules": {
                "style": "light_on_canvas_citations",
                "rules": ["Keep on-canvas citations minimal for exact facts."],
            },
            "source_backing_rules": ["Treat verified facts separately from inferences."],
            "source_pack": [],
        },
    )

    brief = compiled["research_editorial_brief"]

    assert brief["fact_model"]["verified_facts"][0]["value"] == "27 April 2026"
    assert "phased opening" in brief["fact_model"]["inferences"][0]
    assert "Implementation timing" in brief["fact_model"]["uncertainties"][0]
    assert brief["citation_rules"]["style"] == "light_on_canvas_citations"
    assert brief["ranked_sources"][0]["label"] == "Official release"


def test_context_compiler_expands_content_and_visual_plan_for_carousel_execution() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Analyze the trade agreement implications as a carousel.",
        brand_context={"brand_name": "Jiraaf"},
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "pdf"},
        conversation_context={},
        session_memory={},
        content_plan={
            "planning_family": "text",
            "deliverable_type": "social_post",
            "format_family": "carousel",
            "primary_unit": "slide",
            "body_shape": "multi_slide_sequence",
            "outline_mode": "sequenced",
            "density_target": "distributed",
            "content_structure": ["cover", "progressive_detail_slides", "closing_takeaway_or_cta"],
            "required_components": ["headline", "body", "cta", "carousel_slide_specs"],
            "optional_components": ["proof_points", "stat_highlights"],
            "metadata_fields": ["carousel_slide_specs", "supporting_line", "proof_points", "stat_highlights"],
            "planning_rules": ["Plan a real slide sequence, not one poster split into pages."],
            "preferred_slide_count": 5,
            "notes": ["Plan a true slide-by-slide sequence with distinct beats."],
            "research_mode": "research_editorial",
        },
        visual_plan={
            "planning_family": "visual",
            "format_family": "carousel",
            "primary_unit": "slide",
            "body_shape": "multi_slide_sequence",
            "density_target": "distributed",
            "preferred_slide_count": 5,
            "page_strategy": "multi_page",
            "render_mode": "ai_final_render",
            "research_mode": "research_editorial",
        },
    )

    assert compiled["content_plan"]["sequence_contract"] == "native_carousel_metadata"
    assert compiled["content_plan"]["sequence_expectation"] == "slide_by_slide_progression"
    assert compiled["content_plan"]["preferred_slide_count"] == 5
    assert compiled["content_plan"]["native_metadata_fields"][0] == "carousel_slide_specs"
    assert "Plan a real slide sequence" in compiled["content_plan"]["planning_rules"][0]
    assert compiled["visual_plan"]["execution_mode"] == "multi_page_sequence"
    assert compiled["visual_plan"]["visual_sequence_expectation"] == "distinct_page_compositions"


def test_context_compiler_reference_asset_brief_keeps_sequence_cues() -> None:
    compiler = ContextCompilerService()

    compiled = compiler.compile(
        prompt="Create a carousel using the uploaded sample as a quality reference.",
        brand_context={"brand_name": "Jiraaf"},
        persona_context={},
        objective_context={},
        ordered_knowledge={},
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "pdf"},
        conversation_context={},
        session_memory={},
        reference_assets=[
            {
                "asset_role": "reference_creative",
                "trust_level": "approved",
                "metadata": {
                    "label": "FTA sample",
                    "format": "carousel",
                    "page_count": 4,
                    "narrative_pattern": "hook_to_implication_sequence",
                    "structural_cues": [
                        "cover hook",
                        "what happened",
                        "undercovered angle",
                        "implication close",
                    ],
                    "summary": "A four-slide analytical carousel that moves from headline tension into the undercovered implication.",
                },
            }
        ],
    )

    brief = compiled["reference_asset_brief"][0]

    assert brief["format"] == "carousel"
    assert brief["page_count"] == 4
    assert brief["sequence_kind"] == "hook_to_implication_sequence"
    assert brief["structural_cues"][0] == "cover hook"
    assert "undercovered implication" in brief["summary"].casefold()


def test_context_compiler_compact_sequence_pack_preserves_full_reference_asset_path() -> None:
    signed_url = (
        "http://localhost:8000/api/v1/storage/download?token="
        "eyJkb3dubG9hZCI6ZmFsc2UsImV4cCI6MTc3OTExMTExNiwiZmlsZW5hbWUiOiIwNi4wMS4yMDI2LTIzY2Iz"
        "NWI5MjVkZTRhNzZhYTEyMTllNzg4OTFiMTI1LnBuZyIsInN0b3JhZ2VfcGF0aCI6ImV4YW1wbGUifQ.signature"
    )

    compact = ContextCompilerService._compact_sequence_pack(
        {
            "slides": [
                {
                    "slide_index": 1,
                    "story_role": "hook",
                    "headline_hint": "Why this matters now",
                    "reference_asset_path": signed_url,
                    "zone_map": {"zones": [{"role": "headline", "x": 0.1, "y": 0.1, "w": 0.5, "h": 0.2}]},
                }
            ]
        }
    )

    assert compact["slides"][0]["reference_asset_path"] == signed_url
