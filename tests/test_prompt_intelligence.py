from app.ai.prompt_intelligence import PromptIntelligenceService


def test_generation_envelope_grounds_visual_metadata_from_visual_knowledge_brief() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_generation_envelope(
        user_prompt="Create a premium investing visual.",
        compiled_context={
            "brand_copy_brief": {
                "brand_name": "Jiraaf",
                "persona_motivations": ["Grow idle money without feeling reckless."],
                "persona_pain_points": ["Worries fixed-income products will feel opaque."],
                "persona_objections": ["Needs proof that returns and risk are explained clearly."],
                "persona_content_behavior": ["preferred platforms: Instagram, LinkedIn"],
                "persona_language_preference": "plain English",
            },
            "brand_visual_brief": {"palette_roles": {"primary": "#003975"}},
            "audience_brief": {
                "motivations": ["Grow idle money without feeling reckless."],
                "pain_points": ["Worries fixed-income products will feel opaque."],
                "objections": ["Needs proof that returns and risk are explained clearly."],
                "behaviors": ["preferred platforms: Instagram, LinkedIn"],
                "language_preference": "plain English",
                "research_highlights": [
                    "Concrete proof beats abstract trust language when comparing deposits with fixed-income options.",
                    "Plain-English downside framing outperforms category jargon.",
                ],
            },
            "knowledge_brief": [{"channel": "strategy", "content": "Lead with trust and clarity."}],
            "prompt_intelligence_brief": {
                "platform_preset": "instagram",
                "starter_patterns": [{"text": "Lead with the investor outcome.", "platforms": ["instagram"]}],
                "starter_texts": ["Lead with the investor outcome."],
                "current_platform_rules": ["Keep on-canvas text compact."],
                "global_rules": ["Anchor the first line in one clear benefit."],
                "summary": "Lead with outcome-first phrasing and concise CTA language.",
            },
            "visual_knowledge_brief": {
                "grounding_mode": "brand_knowledge",
                "grounding_strength": "strong",
                "channel_priority": ["visual_identity", "mood_board", "reference_creative", "template", "metadata"],
                "channels_present": ["visual_identity", "template"],
                "primary_channels_present": ["visual_identity"],
                "template_suppressed": True,
                "suppressed_channels": ["template"],
                "items": [
                    {
                        "channel": "visual_identity",
                        "role": "primary",
                        "document_type": "structured_summary",
                        "content": "Use deep blue and warm yellow with calm editorial spacing.",
                    }
                ],
                "rejection_reasons": {"template": "suppressed_by_higher_priority_visual_evidence"},
            },
            "render_constraints": {},
            "session_brief": {},
            "template_fit_brief": {},
            "reference_asset_brief": [],
        },
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png"},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "Visual knowledge brief" in combined
    assert "Use deep blue and warm yellow with calm editorial spacing" in combined
    assert "Prompt intelligence brief" in combined
    assert "Persona depth rules" in combined
    assert "Audience research rules" in combined
    assert "Concrete proof beats abstract trust language when comparing deposits with fixed-income options." in combined
    assert "Needs proof that returns and risk are explained clearly." in combined
    assert "Lead with the investor outcome." in combined
    assert "metadata.visual_direction, metadata.design_style, and metadata.image_prompt" in combined
    assert "hook_type" in combined
    assert "objection_handling" in combined
    assert "trust_builders" in combined
    assert "claim_evidence_pairs" in combined
    assert "avoid generic stock concepts such as professional photo, handshake, generic chart" in combined
    assert "Strategic content quality rules" in combined
    assert "Do not use sample headings as lazy copy" in combined
    assert "Use verified_facts and user-supplied facts as the only source" in combined
    assert "Evidence is scaffolding, not the voice" in combined
    assert "not like notes from a research analyst" in combined
    assert "premium 3D, 2.5D/isometric" in combined
    assert "Use hook_type to make the persuasion pattern explicit" in combined
    assert "Clean-looking OCR, specimen, or promotional template copy is not valid primary visual grounding" in combined
    assert "When visual_knowledge_brief.grounding_mode is brand_knowledge" in combined


def test_image_led_social_envelope_requires_brand_intelligent_creative_copy() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_image_led_social_envelope(
        user_prompt="Create a LinkedIn carousel on a new trade deal.",
        compiled_context={
            "brand_copy_brief": {"brand_name": "Example Brand"},
            "brand_visual_brief": {},
            "audience_brief": {},
            "render_constraints": {},
            "session_brief": {},
            "template_fit_brief": {
                "sequence_pack": {
                    "surface_policy": "style_reference_only",
                    "slides": [
                        {
                            "slide_index": 1,
                            "sample_page_headline": "A small deal with a bigger signal.",
                            "sample_page_copy": "Here is what most coverage missed.",
                        }
                    ],
                }
            },
            "reference_asset_brief": [],
            "objective_brief": {},
            "prompt_intelligence_brief": {},
            "content_format_brief": {"format": "carousel", "platform_preset": "linkedin"},
            "research_editorial_brief": {"active": True},
            "format_family_plan": {},
            "content_plan": {},
            "visual_plan": {},
            "visual_knowledge_brief": {},
        },
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
        message_strategy={},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "Write like a brand strategist making a premium creative" in combined
    assert "Do not write like a research paper writer" in combined
    assert "bibliography-like source mentions" in combined
    assert "sample_page_headline" in combined


def test_message_strategy_envelope_locks_style_reference_sample_story_and_non_promotional_close() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_message_strategy_envelope(
        user_prompt="Create a LinkedIn carousel on the India-New Zealand FTA.",
        compiled_context={
            "brand_copy_brief": {"brand_name": "Jiraaf"},
            "template_fit_brief": {
                "sequence_pack": {
                    "surface_policy": "style_reference_only",
                    "slide_count": 4,
                    "slides": [
                        {"slide_index": 4, "sample_page_closing_grammar": "macro_takeaway"},
                    ],
                }
            },
            "content_format_brief": {"format": "carousel", "platform_preset": "linkedin"},
        },
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "Match its slide count" in combined
    assert "final-slide grammar" in combined
    assert "cta_intent must not become product/platform/investment promotion" in combined
    assert "curiosity hook, specific mechanics, undercovered insight, and strategic payoff" in combined


def test_generation_and_planning_envelopes_include_data_visualization_rules() -> None:
    service = PromptIntelligenceService()

    generation_envelope = service.compose_generation_envelope(
        user_prompt="Create a LinkedIn infographic with a comparison table about bond yields.",
        compiled_context={"brand_copy_brief": {"brand_name": "Jiraaf"}},
        studio_panel={"platform_preset": "linkedin", "format": "infographic", "file_type": "png"},
    )
    planning_envelope = service.compose_creative_planning_envelope(
        user_prompt="Create a LinkedIn carousel with charts about an FTA.",
        compiled_context={"brand_copy_brief": {"brand_name": "Jiraaf"}},
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
    )

    combined = f"{generation_envelope.system}\n{planning_envelope.system}"

    assert "Data visualization rules" in combined
    assert "tables, tabular sections, charts, graphs, dashboards" in combined
    assert "If no approved data/content anchors exist, do not request or render any table" in combined
    assert "do not draw generic bars, unlabeled lines, fake axes" in combined
    assert "If exact numeric values, time series, percentages, currency amounts, or rankings are unavailable" in combined
    assert "When visual_knowledge_brief.grounding_mode is llm_fallback" in combined


def test_creative_planning_envelope_rejects_generic_carousel_headings_and_reference_visual_focus_objects() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_creative_planning_envelope(
        user_prompt="Write a LinkedIn carousel for Jiraaf on the India-New Zealand FTA signed on 27 April 2026.",
        compiled_context={
            "brand_copy_brief": {"brand_name": "Jiraaf"},
            "brand_visual_brief": {},
            "audience_brief": {},
            "objective_brief": {},
            "knowledge_brief": [],
            "prompt_intelligence_brief": {},
            "visual_knowledge_brief": {},
            "render_constraints": {},
            "session_brief": {},
            "template_fit_brief": {"template_name": "FTA (3)"},
            "reference_asset_brief": [],
        },
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "every slide headline must be topic-specific" in combined
    assert "Why this matters now" in combined
    assert "every slide visual_focus must be a concise natural-language visual direction" in combined
    assert "Never put a reference_image object, storage_path" in combined


def test_creative_planning_envelope_uses_visual_knowledge_brief() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_creative_planning_envelope(
        user_prompt="Create a premium investing visual.",
        compiled_context={
            "brand_copy_brief": {
                "brand_name": "Jiraaf",
                "persona_motivations": ["Grow idle money without feeling reckless."],
                "persona_pain_points": ["Worries fixed-income products will feel opaque."],
                "persona_objections": ["Needs proof that returns and risk are explained clearly."],
                "persona_content_behavior": ["preferred platforms: Instagram, LinkedIn"],
                "persona_language_preference": "plain English",
            },
            "brand_visual_brief": {"palette_roles": {"primary": "#003975"}},
            "audience_brief": {
                "motivations": ["Grow idle money without feeling reckless."],
                "pain_points": ["Worries fixed-income products will feel opaque."],
                "objections": ["Needs proof that returns and risk are explained clearly."],
                "behaviors": ["preferred platforms: Instagram, LinkedIn"],
                "language_preference": "plain English",
                "research_highlights": [
                    "Concrete proof beats abstract trust language when comparing deposits with fixed-income options.",
                    "Plain-English downside framing outperforms category jargon.",
                ],
            },
            "objective_brief": {},
            "knowledge_brief": [{"channel": "strategy", "content": "This general strategy note should not appear in visual planning."}],
            "prompt_intelligence_brief": {
                "platform_preset": "instagram",
                "starter_patterns": [{"text": "Lead with the investor outcome.", "platforms": ["instagram"]}],
                "starter_texts": ["Lead with the investor outcome."],
                "current_platform_rules": ["Keep on-canvas text compact."],
                "global_rules": ["Anchor the first line in one clear benefit."],
                "summary": "Lead with outcome-first phrasing and concise CTA language.",
            },
            "visual_knowledge_brief": {
                "grounding_mode": "brand_knowledge",
                "grounding_strength": "strong",
                "channel_priority": ["visual_identity", "mood_board", "reference_creative", "template", "metadata"],
                "channels_present": ["visual_identity"],
                "primary_channels_present": ["visual_identity"],
                "template_suppressed": False,
                "items": [
                    {
                        "channel": "visual_identity",
                        "role": "primary",
                        "document_type": "structured_summary",
                        "content": "Use deep blue and warm yellow with calm editorial spacing.",
                    }
                ],
            },
            "render_constraints": {},
            "session_brief": {},
            "template_fit_brief": {},
            "reference_asset_brief": [],
        },
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png"},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "Visual knowledge brief" in combined
    assert "Use deep blue and warm yellow with calm editorial spacing" in combined
    assert "Prompt intelligence brief" in combined
    assert "Persona depth rules" in combined
    assert "Audience research rules" in combined
    assert "Worries fixed-income products will feel opaque." in combined
    assert "Keep on-canvas text compact." in combined
    assert "hook_type" in combined
    assert "objection_handling" in combined
    assert "trust_builders" in combined
    assert "claim_evidence_pairs" in combined
    assert "grounding_mode" in combined
    assert "This general strategy note should not appear in visual planning." not in combined


def test_creative_planning_envelope_includes_brand_design_system_guidance() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_creative_planning_envelope(
        user_prompt="Create a carousel about bond ladders.",
        compiled_context={
            "brand_copy_brief": {"brand_name": "Jiraaf"},
            "brand_visual_brief": {
                "background_style_summary": "gradient, calm editorial surface",
                "motif_summary": "numbered badges, text background boxes",
                "hierarchy_summary": "headline, airy, generous whitespace",
                "content_structure_summary": "data story, measured CTA",
                "image_treatment_summary": "diagram led, editorial illustration",
                "logo_position": "top-right",
                "preferred_zone_roles": ["headline", "proof module", "cta"],
                "dominant_layout_family": "editorial explainer",
            },
            "audience_brief": {},
            "objective_brief": {},
            "knowledge_brief": [],
            "prompt_intelligence_brief": {},
            "visual_knowledge_brief": {},
            "render_constraints": {},
            "session_brief": {},
            "template_fit_brief": {},
            "reference_asset_brief": [],
        },
        studio_panel={"platform_preset": "instagram", "format": "carousel", "file_type": "png"},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "Use brand_visual_brief.dominant_layout_family, preferred_zone_roles" in combined
    assert "Use brand_visual_brief.hierarchy_summary to shape focal path, spacing rhythm, and density/whitespace." in combined
    assert "Use brand_visual_brief.content_structure_summary to decide whether the composition should read like a single-claim, comparison, steps, benefit-stack, or data-story visual." in combined
    assert "Use brand_visual_brief.logo_position and background_style_summary" in combined
    assert "Use brand_visual_brief.image_treatment_summary to avoid generic portraits" in combined


def test_message_strategy_envelope_keeps_general_knowledge_brief() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_message_strategy_envelope(
        user_prompt="Create a premium investing visual.",
        compiled_context={
            "brand_copy_brief": {
                "brand_name": "Jiraaf",
                "primary_emotion": "trust",
                "avoided_emotion": "hype",
                "brand_foundations": "clarity",
                "dos": [],
                "donts": [],
                "persona_motivations": ["Grow idle money without feeling reckless."],
                "persona_pain_points": ["Worries fixed-income products will feel opaque."],
                "persona_objections": ["Needs proof that returns and risk are explained clearly."],
                "persona_content_behavior": ["preferred platforms: Instagram, LinkedIn"],
                "persona_language_preference": "plain English",
            },
            "audience_brief": {
                "motivations": ["Grow idle money without feeling reckless."],
                "pain_points": ["Worries fixed-income products will feel opaque."],
                "objections": ["Needs proof that returns and risk are explained clearly."],
                "behaviors": ["preferred platforms: Instagram, LinkedIn"],
                "language_preference": "plain English",
                "research_highlights": [
                    "Concrete proof beats abstract trust language when comparing deposits with fixed-income options.",
                    "Plain-English downside framing outperforms category jargon.",
                ],
            },
            "objective_brief": {"name": "Awareness"},
            "knowledge_brief": [{"channel": "strategy", "content": "Lead with trust and explain the product clearly."}],
            "prompt_intelligence_brief": {
                "platform_preset": "instagram",
                "starter_patterns": [{"text": "Lead with the investor outcome.", "platforms": ["instagram"]}],
                "starter_texts": ["Lead with the investor outcome."],
                "current_platform_rules": ["Keep on-canvas text compact."],
                "global_rules": ["Anchor the first line in one clear benefit."],
                "summary": "Lead with outcome-first phrasing and concise CTA language.",
            },
            "visual_knowledge_brief": [{"channel": "visual_identity", "content": "This visual-only note should not replace message strategy context."}],
            "session_brief": {},
        },
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png"},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "Lead with trust and explain the product clearly." in combined
    assert "Prompt intelligence brief" in combined
    assert "Lead with the investor outcome." in combined
    assert "brand_copy_brief.persona_pain_points" in combined
    assert "Use audience_brief.research_highlights" in combined
    assert "plain English" in combined
    assert "Use prompt_intelligence_brief.starter_patterns and prompt_intelligence_brief.starter_texts" in combined
    assert "This visual-only note should not replace message strategy context." not in combined


def test_message_strategy_envelope_includes_research_discipline_rules() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_message_strategy_envelope(
        user_prompt="Write an analytical LinkedIn post on the India-New Zealand FTA and go beyond the headline numbers.",
        compiled_context={
            "brand_copy_brief": {"brand_name": "Jiraaf"},
            "audience_brief": {},
            "objective_brief": {},
            "knowledge_brief": [],
            "research_editorial_brief": {
                "active": True,
                "mode": "research_editorial",
                "format_family": "short_form",
                "thesis": "The structure matters more than the headline gains.",
                "angle": "Explain the negotiated structure and strategic trade-offs.",
                "reader_payoff": "Reader should understand the undercovered strategic angle.",
                "hook_strategy": "Lead with the hidden trade-off.",
                "fact_model": {
                    "verified_facts": [
                        {
                            "label": "Signing date",
                            "value": "27 April 2026",
                            "source_title": "Official release",
                            "source_url": "https://example.com/release",
                        }
                    ],
                    "inferences": ["The phased structure suggests India negotiated defensively."],
                    "uncertainties": ["Implementation timing is still conditional."],
                },
                "ranked_sources": [
                    {"label": "Official release", "detail": "Rank 1; supports 1 verified fact.", "source": "https://example.com/release"}
                ],
                "citation_rules": {
                    "style": "light_source_cues",
                    "rules": ["Use lightweight source cues for exact facts."],
                },
                "source_backing_rules": ["Treat verified facts separately from inferences."],
                "source_pack": [],
            },
            "format_family_plan": {"family": "short_form"},
            "session_brief": {},
        },
        studio_panel={"platform_preset": "linkedin", "format": "static", "file_type": "png"},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "Treat research_editorial_brief.fact_model.verified_facts as confirmed facts" in combined
    assert "Do not state inferences or implications as if they were verified facts." in combined
    assert "If uncertainty remains, name it briefly instead of smoothing it away." in combined
    assert "Use lightweight source cues for exact facts." in combined


def test_image_led_social_envelope_uses_prompt_intelligence_brief() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_image_led_social_envelope(
        user_prompt="Create a premium investing visual.",
        compiled_context={
            "brand_copy_brief": {
                "brand_name": "Jiraaf",
                "persona_motivations": ["Grow idle money without feeling reckless."],
                "persona_pain_points": ["Worries fixed-income products will feel opaque."],
                "persona_objections": ["Needs proof that returns and risk are explained clearly."],
                "persona_content_behavior": ["preferred platforms: Instagram, LinkedIn"],
                "persona_language_preference": "plain English",
            },
            "brand_visual_brief": {"palette_roles": {"primary": "#003975"}},
            "audience_brief": {
                "motivations": ["Grow idle money without feeling reckless."],
                "pain_points": ["Worries fixed-income products will feel opaque."],
                "objections": ["Needs proof that returns and risk are explained clearly."],
                "behaviors": ["preferred platforms: Instagram, LinkedIn"],
                "language_preference": "plain English",
                "research_highlights": [
                    "Concrete proof beats abstract trust language when comparing deposits with fixed-income options.",
                    "Plain-English downside framing outperforms category jargon.",
                ],
            },
            "objective_brief": {},
            "prompt_intelligence_brief": {
                "platform_preset": "instagram",
                "starter_patterns": [{"text": "Lead with the investor outcome.", "platforms": ["instagram"]}],
                "starter_texts": ["Lead with the investor outcome."],
                "current_platform_rules": ["Keep on-canvas text compact."],
                "global_rules": ["Anchor the first line in one clear benefit."],
                "summary": "Lead with outcome-first phrasing and concise CTA language.",
            },
            "visual_knowledge_brief": {
                "grounding_mode": "brand_knowledge",
                "grounding_strength": "strong",
                "items": [
                    {
                        "channel": "visual_identity",
                        "role": "primary",
                        "document_type": "structured_summary",
                        "content": "Use deep blue and warm yellow with calm editorial spacing.",
                    }
                ],
            },
            "render_constraints": {},
            "session_brief": {},
            "template_fit_brief": {},
            "reference_asset_brief": [],
        },
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png"},
        message_strategy={"headline_direction": "Outcome-led"},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "Prompt intelligence brief" in combined
    assert "Persona depth rules" in combined
    assert "Audience research rules" in combined
    assert "Lead with the investor outcome." in combined
    assert "Keep on-canvas text compact." in combined
    assert "hook_type" in combined
    assert "objection_handling" in combined
    assert "trust_builders" in combined
    assert "claim_evidence_pairs" in combined


def test_image_led_social_envelope_interpolates_reference_paths_and_render_blocks() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_image_led_social_envelope(
        user_prompt="Create a premium LinkedIn carousel about trade and investment implications.",
        compiled_context={
            "brand_copy_brief": {"brand_name": "Jiraaf"},
            "brand_visual_brief": {"palette_roles": {"primary": "#003975"}},
            "audience_brief": {},
            "objective_brief": {},
            "prompt_intelligence_brief": {},
            "visual_knowledge_brief": {},
            "render_constraints": {"allow_footer": True},
            "session_brief": {},
            "content_format_brief": {"preferred_slide_count": 5},
            "template_fit_brief": {
                "sequence_pack": {"slide_count": 5},
                "template_editorial_dna": {"page_count_hint": 5},
            },
            "reference_asset_brief": [
                {"role": "logo_variant", "storage_path": "tenant/logo.png", "label": "logo"},
                {"role": "reference_creative", "storage_path": "tenant/ref-slide-1.pdf", "name": "FTA sample"},
                {"role": "reference_creative", "storage_path": "tenant/ref-slide-5.pdf", "name": "Closing sample"},
            ],
        },
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
        message_strategy={"headline_direction": "Outcome-led"},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "finished readable slide composition" in envelope.system
    assert "REFERENCE IMAGES AVAILABLE FOR CAROUSEL: 2 usable images" in envelope.user
    assert "bind at most one dominant reference image per slide" in envelope.user
    assert "tenant/ref-slide-1.pdf" in envelope.user
    assert "tenant/ref-slide-5.pdf" in envelope.user
    assert "{json.dumps(render_constraints, ensure_ascii=True)}" not in envelope.user
    assert '"allow_footer": true' in envelope.user.casefold()


def test_message_strategy_envelope_includes_content_format_brief_and_client_quality_rules() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_message_strategy_envelope(
        user_prompt="Create a LinkedIn carousel about fixed-income confidence.",
        compiled_context={
            "brand_copy_brief": {
                "brand_name": "Jiraaf",
                "primary_emotion": "trust",
                "avoided_emotion": "hype",
                "brand_foundations": "clarity",
                "dos": [],
                "donts": [],
            },
            "audience_brief": {
                "research_highlights": ["Proof-led education outperforms generic credibility claims."],
                "language_preference": "plain English",
            },
            "objective_brief": {"name": "Awareness"},
            "knowledge_brief": [{"channel": "strategy", "content": "Lead with trust and explain the product clearly."}],
            "prompt_intelligence_brief": {},
            "content_format_brief": {
                "platform_preset": "linkedin",
                "format": "carousel",
                "summary": "Use narrative progression with one idea per page.",
                "format_definition": "A carousel is a multi-slide, swipeable post for storytelling.",
                "format_rules": ["Slide 1: Hook", "Slides 2-4: One idea per slide", "Final slide: CTA"],
                "platform_rules": ["Carousel: Multi-page PDF (each page = one slide)"],
                "structural_expectations": ["Open with a hook", "One idea per slide"],
                "quality_priorities": ["Strong narrative flow.", "Keep messaging audience-facing."],
                "export_rules": ["LinkedIn carousel: Multi-page PDF"],
                "preferred_slide_count": 5,
            },
            "session_brief": {},
        },
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "pdf"},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "Content format brief" in combined
    assert "Client quality rules" in combined
    assert "paginated PDF storytelling" in combined
    assert "one idea per slide" in combined.casefold()


def test_message_strategy_envelope_adds_mistake_carousel_rules_for_mistake_prompts() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_message_strategy_envelope(
        user_prompt="Create a LinkedIn carousel on top bond mistakes retail investors should avoid.",
        compiled_context={
            "brand_copy_brief": {"brand_name": "Jiraaf"},
            "audience_brief": {},
            "objective_brief": {"name": "Education"},
            "knowledge_brief": [],
            "prompt_intelligence_brief": {},
            "content_format_brief": {
                "platform_preset": "linkedin",
                "format": "carousel",
                "summary": "Use narrative progression with one idea per page.",
                "quality_priorities": ["Keep messaging audience-facing."],
            },
            "session_brief": {},
        },
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "pdf"},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "Mistake-style carousel rules" in combined
    assert "Slide 1 must open with a strong hook" in combined
    assert "Mistake, Why, Impact, and Fix" in combined
    assert "at least three distinct mistakes" in combined
    assert "Never use generic labels like Investment Education, Key Insight, or Key Point" in combined


def test_message_strategy_envelope_skips_mistake_carousel_rules_for_non_mistake_carousels() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_message_strategy_envelope(
        user_prompt="Create a LinkedIn carousel explaining how bond ladders work.",
        compiled_context={
            "brand_copy_brief": {"brand_name": "Jiraaf"},
            "audience_brief": {},
            "objective_brief": {"name": "Education"},
            "knowledge_brief": [],
            "prompt_intelligence_brief": {},
            "content_format_brief": {
                "platform_preset": "linkedin",
                "format": "carousel",
                "summary": "Use narrative progression with one idea per page.",
                "quality_priorities": ["Keep messaging audience-facing."],
            },
            "session_brief": {},
        },
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "pdf"},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "Mistake-style carousel rules: No mistake-specific carousel override is active." in combined
    assert "Never use generic labels like Investment Education, Key Insight, or Key Point" not in combined


def test_message_strategy_envelope_skips_client_quality_rules_when_only_prompt_intelligence_exists() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_message_strategy_envelope(
        user_prompt="Create a LinkedIn post about fixed-income confidence.",
        compiled_context={
            "brand_copy_brief": {"brand_name": "Jiraaf"},
            "audience_brief": {},
            "objective_brief": {"name": "Awareness"},
            "knowledge_brief": [],
            "prompt_intelligence_brief": {
                "summary": "Lead with the investor outcome.",
                "starter_texts": ["Open with one concrete benefit."],
                "current_platform_rules": ["Keep the message scan-friendly."],
                "global_rules": ["Avoid generic credibility filler."],
            },
            "content_format_brief": {},
            "session_brief": {},
        },
        studio_panel={"platform_preset": "linkedin", "format": "static", "file_type": "png"},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "Prompt intelligence brief" in combined
    assert "No client-specific quality overrides are active." in combined
    assert "When content_format_brief.format is carousel" not in combined


def test_generation_envelope_skips_client_quality_rules_without_scoped_context() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_generation_envelope(
        user_prompt="Create a premium investing visual.",
        compiled_context={
            "brand_copy_brief": {"brand_name": "Jiraaf"},
            "brand_visual_brief": {},
            "audience_brief": {},
            "knowledge_brief": [],
            "prompt_intelligence_brief": {},
            "visual_knowledge_brief": {},
            "render_constraints": {},
            "session_brief": {},
            "template_fit_brief": {},
            "reference_asset_brief": [],
        },
        studio_panel={"platform_preset": "instagram", "format": "static", "file_type": "png"},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "No client-specific quality overrides are active." in combined
    assert "When content_format_brief.format is carousel" not in combined


def test_message_strategy_envelope_includes_research_editorial_brief_when_active() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_message_strategy_envelope(
        user_prompt="Explain why the latest trade agreement matters beyond the headline numbers.",
        compiled_context={
            "brand_copy_brief": {"brand_name": "Jiraaf"},
            "audience_brief": {},
            "objective_brief": {"name": "Thought Leadership"},
            "knowledge_brief": [],
            "prompt_intelligence_brief": {},
            "content_format_brief": {"platform_preset": "linkedin", "format": "carousel"},
            "research_editorial_brief": {
                "active": True,
                "mode": "research_editorial",
                "topic_focus": "India-New Zealand trade agreement",
                "angle": "Go beyond the headline numbers and explain the structure and strategic meaning.",
                "thesis": "Use the deal structure and strategic implications as the real story.",
                "reader_payoff": "Reader should understand what was negotiated and why it matters strategically.",
                "hook_strategy": "Open with the undercovered angle.",
                "insight_hierarchy": ["What was negotiated", "Why it matters strategically"],
                "outline": [{"index": "1", "role": "hook", "purpose": "Lead with tension", "notes": "Use the undercovered angle."}],
                "source_pack": [{"type": "verified_fact", "label": "Signing date", "detail": "27 April 2026", "source": "Official release"}],
                "summary": "Explain the structure, trade-offs, and strategic meaning.",
            },
            "session_brief": {},
        },
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "pdf"},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "Research editorial brief" in combined
    assert "Research-editorial rules" in combined
    assert "authoritative analytical plan for research-heavy content" in combined
    assert "India-New Zealand trade agreement" in combined
    assert "do not invent exact numbers, percentages, dates, rankings, or survey claims" in combined


def test_generation_envelope_includes_format_family_plan() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_generation_envelope(
        user_prompt="Write a blog about bond ladders.",
        compiled_context={
            "brand_copy_brief": {"brand_name": "Jiraaf"},
            "audience_brief": {},
            "objective_brief": {},
            "knowledge_brief": [],
            "session_brief": {},
            "prompt_intelligence_brief": {},
            "content_format_brief": {},
            "research_editorial_brief": {},
            "format_family_plan": {
                "family": "long_form",
                "primary_unit": "section",
                "body_shape": "multi_section_editorial",
                "outline_mode": "sectioned",
                "content_structure": ["title_or_heading", "introduction", "section_progression"],
                "required_components": ["headline", "body"],
                "planning_rules": ["Write in sections with visible progression instead of one collapsed block."],
            },
        },
        studio_panel={"platform_preset": "linkedin", "format": "text", "file_type": "md"},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "Format family plan" in combined
    assert "multi_section_editorial" in combined
    assert "Format family rules" in combined


def test_generation_envelope_includes_content_and_visual_plan_for_carousel_metadata_contract() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_generation_envelope(
        user_prompt="Explain why the India-New Zealand trade agreement matters as a LinkedIn carousel.",
        compiled_context={
            "brand_copy_brief": {"brand_name": "Jiraaf"},
            "brand_visual_brief": {},
            "audience_brief": {},
            "objective_brief": {},
            "knowledge_brief": [],
            "session_brief": {},
            "prompt_intelligence_brief": {},
            "content_format_brief": {"platform_preset": "linkedin", "format": "carousel"},
            "research_editorial_brief": {
                "active": True,
                "outline": [
                    {"index": "1", "role": "hook", "purpose": "Lead with the undercovered angle.", "notes": ""},
                    {"index": "2", "role": "context", "purpose": "Set up what happened.", "notes": ""},
                ],
            },
            "format_family_plan": {
                "family": "carousel",
                "primary_unit": "slide",
                "body_shape": "multi_slide_sequence",
                "outline_mode": "sequenced",
                "content_structure": ["cover", "progressive_detail_slides", "closing_takeaway_or_cta"],
                "required_components": ["headline", "body", "cta", "carousel_slide_specs"],
                "planning_rules": ["Plan a real slide sequence, not one poster split into pages."],
                "preferred_slide_count": 5,
            },
            "content_plan": {
                "planning_family": "text",
                "format_family": "carousel",
                "primary_unit": "slide",
                "body_shape": "multi_slide_sequence",
                "outline_mode": "sequenced",
                "content_structure": ["cover", "progressive_detail_slides", "closing_takeaway_or_cta"],
                "required_components": ["headline", "body", "cta", "carousel_slide_specs"],
                "metadata_fields": ["carousel_slide_specs", "supporting_line", "proof_points"],
                "planning_rules": ["Plan a real slide sequence, not one poster split into pages."],
                "preferred_slide_count": 5,
                "sequence_contract": "native_carousel_metadata",
                "sequence_expectation": "slide_by_slide_progression",
                "native_metadata_fields": ["carousel_slide_specs", "supporting_line", "proof_points"],
                "carousel_archetype": "editorial_reveal",
                "carousel_slide_grammar": [
                    {"role": "hook", "job": "Open with the undercovered angle."},
                    {"role": "structure", "job": "Explain what actually changed."},
                ],
                "carousel_archetype_rules": ["Keep factual unpacking and implication on separate slides."],
            },
            "visual_plan": {
                "planning_family": "visual",
                "format_family": "carousel",
                "primary_unit": "slide",
                "body_shape": "multi_slide_sequence",
                "preferred_slide_count": 5,
                "page_strategy": "multi_page",
                "render_mode": "ai_final_render",
                "execution_mode": "multi_page_sequence",
                "visual_sequence_expectation": "distinct_page_compositions",
            },
            "visual_knowledge_brief": {},
            "render_constraints": {},
            "template_fit_brief": {},
            "reference_asset_brief": [],
        },
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "pdf"},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "Planning contract rules" in combined
    assert "metadata.carousel_slide_specs is the primary narrative structure" in combined
    assert "slide_number, slide_role, headline, supporting_line, body, body_points, proof_points, stat_highlights, visual_focus, and transition_note" in combined
    assert "only the final slide may contain CTA text" in combined
    assert "body and/or body_points to carry the real per-slide explanation" in combined
    assert "\"carousel_archetype\": \"editorial_reveal\"" in combined
    assert "carousel_slide_grammar" in combined
    assert "\"sequence_contract\": \"native_carousel_metadata\"" in combined
    assert "\"execution_mode\": \"multi_page_sequence\"" in combined
    assert "\"preferred_slide_count\": 5" in combined


def test_rewrite_envelope_includes_format_family_plan() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_rewrite_envelope(
        original_prompt="Create a LinkedIn carousel on bond basics.",
        rewrite_instruction="Make slide 2 more analytical.",
        current_payload={"headline": "Bond Basics", "body": "Slide content", "cta": "Learn more", "hashtags": [], "metadata": {}},
        compiled_context={
            "brand_copy_brief": {"brand_name": "Jiraaf"},
            "audience_brief": {},
            "objective_brief": {},
            "knowledge_brief": [],
            "template_fit_brief": {},
            "render_constraints": {},
            "session_brief": {},
            "prompt_intelligence_brief": {},
            "content_format_brief": {"format": "carousel"},
            "research_editorial_brief": {},
            "format_family_plan": {
                "family": "carousel",
                "primary_unit": "slide",
                "body_shape": "multi_slide_sequence",
                "outline_mode": "sequenced",
                "content_structure": ["cover", "progressive_detail_slides", "closing_takeaway_or_cta"],
                "required_components": ["headline", "body", "cta", "carousel_slide_specs"],
                "planning_rules": ["Plan a real slide sequence, not one poster split into pages."],
            },
            "content_plan": {
                "planning_family": "text",
                "format_family": "carousel",
                "primary_unit": "slide",
                "body_shape": "multi_slide_sequence",
                "content_structure": ["cover", "progressive_detail_slides", "closing_takeaway_or_cta"],
                "metadata_fields": ["carousel_slide_specs", "supporting_line"],
                "planning_rules": ["Plan a real slide sequence, not one poster split into pages."],
                "sequence_contract": "native_carousel_metadata",
                "sequence_expectation": "slide_by_slide_progression",
                "carousel_archetype": "comparison_framework",
                "carousel_slide_grammar": [
                    {"role": "hook", "job": "Frame the decision."},
                    {"role": "comparison_item", "job": "Cover one option per slide."},
                ],
            },
            "visual_plan": {
                "planning_family": "visual",
                "format_family": "carousel",
                "primary_unit": "slide",
                "body_shape": "multi_slide_sequence",
                "preferred_slide_count": 5,
                "page_strategy": "multi_page",
                "execution_mode": "multi_page_sequence",
                "visual_sequence_expectation": "distinct_page_compositions",
            },
        },
        message_strategy={},
        tone_analysis={},
        rewrite_field_plan={},
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
        targeted_fields=["body"],
        revision_scope={"targeted_slides": [2], "only_targeted": True},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "Format family plan" in combined
    assert "multi_slide_sequence" in combined
    assert "Format family rules" in combined
    assert "Planning contract rules" in combined
    assert "\"sequence_contract\": \"native_carousel_metadata\"" in combined
    assert "\"carousel_archetype\": \"comparison_framework\"" in combined
    assert "only the final slide may contain CTA text" in combined


def test_scene_graph_repair_envelope_includes_format_family_plan() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_scene_graph_repair_envelope(
        user_prompt="Create a LinkedIn infographic on bond yields.",
        compiled_context={
            "prompt_intelligence_brief": {},
            "content_format_brief": {"format": "infographic"},
            "research_editorial_brief": {},
            "format_family_plan": {
                "family": "infographic",
                "primary_unit": "section",
                "body_shape": "sectioned_visual_explainer",
                "outline_mode": "sectioned_visual",
                "content_structure": ["headline", "context_block", "key_numbers_or_facts"],
                "required_components": ["headline", "body", "cta"],
                "planning_rules": ["Break information into stacked explanatory sections rather than a poster headline plus filler."],
            },
            "content_plan": {
                "planning_family": "text",
                "format_family": "infographic",
                "primary_unit": "section",
                "body_shape": "sectioned_visual_explainer",
                "content_structure": ["headline", "context_block", "key_numbers_or_facts"],
                "planning_rules": ["Break information into stacked explanatory sections rather than a poster headline plus filler."],
                "sequence_contract": "native_infographic_sections",
                "sequence_expectation": "section_by_section_progression",
            },
            "visual_plan": {
                "planning_family": "visual",
                "format_family": "infographic",
                "primary_unit": "section",
                "body_shape": "sectioned_visual_explainer",
                "preferred_slide_count": 4,
                "page_strategy": "multi_page",
                "execution_mode": "multi_page_sequence",
                "visual_sequence_expectation": "stacked_section_hierarchy",
            },
        },
        studio_panel={"platform_preset": "linkedin", "format": "infographic", "file_type": "png"},
        current_scene_graph={"elements": []},
        creative_decision={"layout_mode": "infographic"},
        validation_report={"violations": ["too_sparse"]},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "Format family plan" in combined
    assert "sectioned_visual_explainer" in combined
    assert "Format family rules" in combined
    assert "Planning contract rules" in combined
    assert "\"sequence_expectation\": \"section_by_section_progression\"" in combined


def test_scene_graph_repair_envelope_blocks_unrelated_assets_for_style_reference_carousel() -> None:
    service = PromptIntelligenceService()

    envelope = service.compose_scene_graph_repair_envelope(
        user_prompt="Create a LinkedIn carousel on the India-New Zealand FTA.",
        compiled_context={
            "template_fit_brief": {
                "sequence_pack": {
                    "surface_policy": "style_reference_only",
                    "slides": [{"slide_index": 1, "sample_page_headline": "A sharper opening hook"}],
                }
            },
            "content_format_brief": {"format": "carousel"},
            "prompt_intelligence_brief": {},
        },
        studio_panel={"platform_preset": "linkedin", "format": "carousel", "file_type": "png"},
        current_scene_graph={"elements": []},
        creative_decision={"asset_strategy": {"template_surface_policy": "style_reference_only"}},
        validation_report={"violations": ["missing_headline"]},
    )

    combined = f"{envelope.system}\n{envelope.user}"

    assert "the selected sample/reference sequence is the only allowed reusable visual family" in combined
    assert "Do not bind, mention, or copy asset names" in combined
    assert "If the selected sample page does not visibly use a dashboard" in combined


def test_generation_envelope_includes_native_infographic_and_static_contracts() -> None:
    service = PromptIntelligenceService()

    infographic_envelope = service.compose_generation_envelope(
        user_prompt="Create an infographic about inflation and savings.",
        compiled_context={
            "brand_copy_brief": {"brand_name": "Jiraaf"},
            "audience_brief": {},
            "knowledge_brief": [],
            "prompt_intelligence_brief": {},
            "visual_knowledge_brief": {},
            "render_constraints": {},
            "session_brief": {},
            "template_fit_brief": {},
            "reference_asset_brief": [],
            "content_format_brief": {"format": "infographic"},
            "research_editorial_brief": {},
            "format_family_plan": {"family": "infographic"},
            "content_plan": {
                "planning_family": "text",
                "format_family": "infographic",
                "sequence_contract": "native_infographic_sections",
                "sequence_expectation": "section_by_section_progression",
                "metadata_fields": ["infographic_section_specs", "section_label", "proof_points", "stat_highlights"],
                "native_metadata_fields": ["infographic_section_specs", "section_label", "proof_points", "stat_highlights"],
            },
            "visual_plan": {"planning_family": "visual", "format_family": "infographic"},
        },
        studio_panel={"platform_preset": "instagram", "format": "infographic", "file_type": "png"},
    )
    static_envelope = service.compose_generation_envelope(
        user_prompt="Create a static social post about bond clarity.",
        compiled_context={
            "brand_copy_brief": {"brand_name": "Jiraaf"},
            "audience_brief": {},
            "knowledge_brief": [],
            "prompt_intelligence_brief": {},
            "visual_knowledge_brief": {},
            "render_constraints": {},
            "session_brief": {},
            "template_fit_brief": {},
            "reference_asset_brief": [],
            "content_format_brief": {"format": "static"},
            "research_editorial_brief": {},
            "format_family_plan": {"family": "static"},
            "content_plan": {
                "planning_family": "text",
                "format_family": "static",
                "sequence_contract": "native_static_panel_spec",
                "sequence_expectation": "single_dominant_idea",
                "metadata_fields": ["static_panel_spec", "supporting_line", "proof_points"],
                "native_metadata_fields": ["static_panel_spec", "supporting_line", "proof_points"],
            },
            "visual_plan": {"planning_family": "visual", "format_family": "static"},
        },
        studio_panel={"platform_preset": "linkedin", "format": "static", "file_type": "png"},
    )

    infographic_combined = f"{infographic_envelope.system}\n{infographic_envelope.user}"
    static_combined = f"{static_envelope.system}\n{static_envelope.user}"

    assert "metadata.infographic_section_specs" in infographic_combined
    assert "section_number, section_role, section_label, headline, body, body_points, proof_points, stat_highlights, claim_evidence_pairs, and visual_focus" in infographic_combined
    assert "\"sequence_contract\": \"native_infographic_sections\"" in infographic_combined
    assert "metadata.static_panel_spec" in static_combined
    assert "panel_goal, dominant_message, supporting_lines, proof_points, stat_highlights, visual_focus, and cta_mode" in static_combined
    assert "\"sequence_contract\": \"native_static_panel_spec\"" in static_combined
