from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.ai.contracts import AIOrchestrationRequest
from app.ai.orchestrator import AIOrchestratorService


class _ScenarioTextProvider:
    provider_name = "scenario-stub"

    def __init__(self, *, message_strategy: dict, planning: dict, repair: dict | None = None) -> None:
        self.message_strategy = message_strategy
        self.planning = planning
        self.repair = repair

    def generate_structured_json(self, envelope, fallback):
        system = str(envelope.system or "")
        if "senior brand content strategist" in system:
            return self.message_strategy
        if "scene-graph repair engine" in system:
            return self.repair or fallback
        return self.planning

    def generate_text(self, envelope, fallback):
        return "Brand-safe supporting research summary."


class _ScenarioImageProvider:
    provider_name = "scenario-image-stub"

    def generate(self, tenant_id, brand_space_id, prompt, size=None):
        return {
            "mime_type": "image/png",
            "storage_path": "tenant/brand/generated/hero.png",
            "width": 1080,
            "height": 1080,
            "asset_role": "ai_image",
            "size": size or "1024x1024",
        }

    def edit(self, tenant_id, brand_space_id, prompt, image_paths, size=None, mask_png_bytes=None):
        return {
            "mime_type": "image/png",
            "storage_path": "tenant/brand/generated/final-hero.png",
            "width": 1080,
            "height": 1080,
            "asset_role": "ai_image",
            "size": size or "1024x1024",
        }


def _base_brand_context() -> dict:
    return {
        "brand_name": "Jiraaf",
        "brand_description": "Curated fixed-income investments for modern Indian investors.",
        "guardrails": {},
        "foundations": {"brand_foundation": "Build trust through clarity, confidence, and measured optimism."},
        "voice_tone": {
            "primary_emotion": "confidence",
            "avoided_emotion": "panic",
            "tone_attributes": ["trustworthy", "optimistic", "clear"],
        },
        "identity": {"logo_asset_id": str(uuid4())},
        "audience_insights": {
            "pain_points": ["confusing options", "uncertain returns"],
            "motivations": ["financial growth", "stable planning"],
        },
        "visual_identity": {
            "brand_color_palette": {"primary": "#003975", "secondary": "#FFA400", "accent": "#00CB91"},
            "palette_entries": [
                {"role": "primary", "color_name": "Regal Blue", "hex_code": "#003975"},
                {"role": "secondary", "color_name": "Orange Peel", "hex_code": "#FFA400"},
                {"role": "accent", "color_name": "Caribbean Green", "hex_code": "#00CB91"},
            ],
            "typography": {"font_families": [{"name": "DM Sans"}]},
        },
    }


def _build_request(
    *,
    prompt: str,
    session_memory: dict | None = None,
    template_candidates: list[dict] | None = None,
    template_context: dict | None = None,
    layout_decision: dict | None = None,
    generate_image: bool = True,
) -> AIOrchestrationRequest:
    return AIOrchestrationRequest(
        tenant_id=uuid4(),
        brand_space_id=uuid4(),
        user_id=uuid4(),
        prompt=prompt,
        studio_panel={
            "platform_preset": "instagram",
            "format": "static",
            "file_type": "png",
            "size": {"width": 1080, "height": 1080},
        },
        conversation_context={"message_count": 4},
        session_memory=session_memory or {},
        resolved_brand_context=_base_brand_context(),
        persona_context={"name": "Young professionals", "audience_goals": ["save more", "travel smarter"]},
        objective_context={"name": "Engagement", "description": "Drive interest with premium social storytelling."},
        retrieved_knowledge={"brand": [{"content": "Jiraaf helps investors grow with regulated fixed-income options."}]},
        template_context=template_context,
        template_candidates=template_candidates or [],
        layout_decision=layout_decision or {"mode": "synthesized_layout"},
        reference_assets=[],
        asset_catalog=[],
        resolution_policy={},
        generate_image=generate_image,
    )


def _prepare_service(provider: _ScenarioTextProvider) -> AIOrchestratorService:
    service = AIOrchestratorService()
    service.guardrails = SimpleNamespace(validate_prompt=lambda *args, **kwargs: None, validate_output=lambda *args, **kwargs: None)
    service.resolution = SimpleNamespace(
        build_plan=lambda **kwargs: SimpleNamespace(
            ordered_knowledge={"brand": [{"content": "Jiraaf helps investors grow with regulated fixed-income options."}]},
            instructions="Prefer validated brand context.",
            metadata={"ordered_channels": ["brand"]},
        )
    )
    service.providers = SimpleNamespace(
        get_text_provider=lambda purpose: provider,
        get_image_provider=lambda: _ScenarioImageProvider(),
    )
    service.tone = SimpleNamespace(evaluate=lambda **kwargs: {"score": 0.91, "summary": "on-brand"})
    return service


def test_stub_generation_travel_prompt_uses_image_led_brand_safe_plan() -> None:
    service = _prepare_service(
        _ScenarioTextProvider(
            message_strategy={
                "primary_campaign_theme": "Travel smarter with stable financial planning",
                "core_audience_message": "Book with more confidence when your travel fund is supported by steady growth.",
                "headline_direction": "Practical and optimistic",
                "supporting_copy_direction": "Short, supportive, modern",
                "cta_intent": "Encourage confident exploration",
                "key_value_proposition": "Steady investing can support future travel goals.",
                "important_keywords": ["travel fund", "smarter bookings", "stable growth"],
                "emotional_messaging_direction": "Confident optimism",
                "what_must_be_avoided_in_messaging": ["panic pricing", "financial fear"],
            },
            planning={
                "headline": "Book Flights Smarter",
                "body": "Use flexible dates, fare alerts, and better planning to spend less on every trip.",
                "cta": "Plan with Confidence",
                "hashtags": ["#TravelSmarter", "#Jiraaf"],
                "metadata": {
                    "supporting_line": "Small booking habits can unlock better fares.",
                    "proof_points": ["Compare fares", "Set alerts", "Stay flexible"],
                    "stat_highlights": ["Lower fares", "Better timing"],
                    "visual_direction": "Premium travel lifestyle image with calm overlay space",
                    "design_style": "editorial travel social creative",
                    "image_prompt": "A premium airport travel planning scene with no text",
                },
                "creative_decision": {
                    "layout_mode": "synthesized_layout",
                    "confidence": 0.88,
                    "reasoning": ["No exact editable template needed", "Image-led travel social fits the prompt best"],
                    "adaptations": {},
                    "asset_strategy": {"use_generated_image": True, "dominant_visual_system": "generated_image"},
                },
                "scene_graph": {
                    "canvas": {"width": 1080, "height": 1080, "platform": "instagram", "file_type": "png"},
                    "layout_mode": "synthesized_layout",
                    "confidence": 0.88,
                    "layers": ["background", "primary_visual", "content", "brand"],
                    "styles": {"layout_archetype": "hero_overlay"},
                    "validation_hints": {"template_surface_policy": "style_reference_only"},
                    "elements": [
                        {"element_id": "background", "element_type": "background", "role": "background", "layer": "background", "geometry": {"x": 0, "y": 0, "width": 1, "height": 1, "units": "normalized"}, "style": {"fill_role": "background"}},
                        {"element_id": "hero", "element_type": "image", "role": "image", "layer": "primary_visual", "geometry": {"x": 0, "y": 0, "width": 1, "height": 1, "units": "normalized"}, "asset": {"asset_role": "ai_image"}, "style": {"fit": "cover"}},
                        {"element_id": "headline", "element_type": "text", "role": "headline", "layer": "content", "geometry": {"x": 0.08, "y": 0.12, "width": 0.42, "height": 0.14, "units": "normalized"}, "text": "Book Flights Smarter", "style": {"font_role": "heading_sans", "fill_role": "primary", "font_size": 56}},
                        {"element_id": "supporting_line", "element_type": "text", "role": "supporting_line", "layer": "content", "geometry": {"x": 0.08, "y": 0.28, "width": 0.4, "height": 0.1, "units": "normalized"}, "text": "Small booking habits can unlock better fares.", "style": {"font_role": "body_sans", "fill_role": "secondary_text", "font_size": 24}},
                        {"element_id": "proof_points", "element_type": "text", "role": "proof_points", "layer": "content", "geometry": {"x": 0.08, "y": 0.42, "width": 0.34, "height": 0.18, "units": "normalized"}, "text": ["Compare fares", "Set alerts", "Stay flexible"], "style": {"font_role": "body_sans", "fill_role": "secondary_text", "font_size": 20}},
                        {"element_id": "cta", "element_type": "text", "role": "cta", "layer": "brand", "geometry": {"x": 0.08, "y": 0.78, "width": 0.3, "height": 0.08, "units": "normalized"}, "text": "Plan with Confidence", "style": {"font_role": "cta_sans", "fill_role": "light_text", "background_fill_role": "primary", "font_size": 24}},
                        {"element_id": "logo", "element_type": "logo", "role": "logo", "layer": "brand", "geometry": {"x": 0.74, "y": 0.08, "width": 0.18, "height": 0.08, "units": "normalized"}, "asset": {"asset_role": "logo", "trust_level": "trusted"}, "style": {"fit": "contain"}},
                    ],
                },
            },
        )
    )

    response = service.generate(
        _build_request(prompt="Create an engaging Instagram post that shares tips and strategies to book flights at a lower cost.")
    )

    roles = [element.role for element in response.scene_graph.elements if element.visible]
    assert response.explainability["generation_path"] == "image_led_social"
    assert response.validation_report.status == "clean"
    assert response.repair_attempts == 0
    assert response.render_authority == "ai"
    assert response.final_render_asset is not None
    assert response.final_render_asset.metadata["render_source"] == "ai"
    assert {"headline", "image", "logo", "cta"}.issubset(set(roles))


def test_stub_generation_reinterprets_flattened_pdf_template_as_style_reference() -> None:
    service = _prepare_service(
        _ScenarioTextProvider(
            message_strategy={
                "primary_campaign_theme": "Affordable travel planning",
                "core_audience_message": "Save more on flights with early, flexible planning.",
                "headline_direction": "Helpful and energetic",
                "supporting_copy_direction": "Short social copy",
                "cta_intent": "Invite confident action",
                "key_value_proposition": "Smarter booking habits lower total travel costs.",
                "important_keywords": ["flight booking", "fare alerts", "flexible dates"],
                "emotional_messaging_direction": "Confidence",
                "what_must_be_avoided_in_messaging": ["chaos", "panic"],
            },
            planning={
                "headline": "Lower Fares, Better Timing",
                "body": "Book early, compare routes, and keep your dates flexible to unlock lower-cost trips.",
                "cta": "Travel Smarter",
                "hashtags": ["#FlightTips", "#Jiraaf"],
                "metadata": {
                    "supporting_line": "A cleaner plan usually means a cheaper ticket.",
                    "proof_points": ["Compare multiple routes", "Book before peak demand", "Track fare drops"],
                    "stat_highlights": ["Cheaper fares", "Smarter timing"],
                    "visual_direction": "Premium reinterpretation of a flat travel poster",
                    "design_style": "image-led travel editorial",
                    "image_prompt": "A premium travel planning visual with no text",
                },
                "creative_decision": {
                    "layout_mode": "adapted_template",
                    "selected_template_id": "tpl_pdf_001",
                    "confidence": 0.83,
                    "reasoning": ["Template style is useful", "Flattened text surface should be reinterpreted, not overlaid"],
                    "adaptations": {"remove_footer": True, "reinterpret_flattened_template": True},
                    "asset_strategy": {"use_generated_image": True, "use_template_background": False, "dominant_visual_system": "generated_image"},
                },
                "scene_graph": {
                    "canvas": {"width": 1080, "height": 1080, "platform": "instagram", "file_type": "png"},
                    "layout_mode": "adapted_template",
                    "confidence": 0.83,
                    "layers": ["background", "primary_visual", "content", "brand"],
                    "styles": {"layout_archetype": "hero_overlay"},
                    "validation_hints": {"template_surface_policy": "style_reference_only"},
                    "template_adaptation": {"selected_template_id": "tpl_pdf_001", "reinterpret_flattened_template": True},
                    "elements": [
                        {"element_id": "background", "element_type": "background", "role": "background", "layer": "background", "geometry": {"x": 0, "y": 0, "width": 1, "height": 1, "units": "normalized"}, "style": {"fill_role": "background"}},
                        {"element_id": "hero", "element_type": "image", "role": "image", "layer": "primary_visual", "geometry": {"x": 0.42, "y": 0.08, "width": 0.48, "height": 0.78, "units": "normalized"}, "asset": {"asset_role": "ai_image"}, "style": {"fit": "cover", "border_radius": 28}},
                        {"element_id": "headline", "element_type": "text", "role": "headline", "layer": "content", "geometry": {"x": 0.08, "y": 0.14, "width": 0.28, "height": 0.14, "units": "normalized"}, "text": "Lower Fares, Better Timing", "style": {"font_role": "heading_sans", "fill_role": "primary", "font_size": 52}},
                        {"element_id": "supporting_line", "element_type": "text", "role": "supporting_line", "layer": "content", "geometry": {"x": 0.08, "y": 0.3, "width": 0.28, "height": 0.1, "units": "normalized"}, "text": "A cleaner plan usually means a cheaper ticket.", "style": {"font_role": "body_sans", "fill_role": "secondary_text", "font_size": 22}},
                        {"element_id": "cta", "element_type": "text", "role": "cta", "layer": "brand", "geometry": {"x": 0.08, "y": 0.77, "width": 0.26, "height": 0.08, "units": "normalized"}, "text": "Travel Smarter", "style": {"font_role": "cta_sans", "fill_role": "light_text", "background_fill_role": "primary", "font_size": 24}},
                        {"element_id": "logo", "element_type": "logo", "role": "logo", "layer": "brand", "geometry": {"x": 0.08, "y": 0.07, "width": 0.18, "height": 0.08, "units": "normalized"}, "asset": {"asset_role": "logo", "trust_level": "trusted"}},
                    ],
                },
            },
        )
    )

    response = service.generate(
        _build_request(
            prompt="Create an engaging Instagram post that shares tips and strategies to book flights at a lower cost.",
            template_candidates=[
                {
                    "template_id": "tpl_pdf_001",
                    "name": "Travel Poster PDF",
                    "score": 0.79,
                    "match_type": "reference_only_flattened_text",
                    "reinterpretation_suitability": 0.93,
                    "style_only_suitability": 0.95,
                }
            ],
            template_context={"analysis": {"text_overlay_risk": "high", "overlay_safe": False}},
            layout_decision={"mode": "adapted_template", "template_name": "Travel Poster PDF"},
        )
    )

    assert response.creative_decision.selected_template_id == "tpl_pdf_001"
    assert response.scene_graph.validation_hints["template_surface_policy"] == "style_reference_only"
    assert response.explainability["generation_path"] == "image_led_social"


def test_stub_generation_repairs_off_palette_and_icon_stamp_plan_before_rendering() -> None:
    service = _prepare_service(
        _ScenarioTextProvider(
            message_strategy={
                "primary_campaign_theme": "Modern fixed-income confidence",
                "core_audience_message": "Move beyond ordinary returns with steady, regulated options.",
                "headline_direction": "Clear and premium",
                "supporting_copy_direction": "Short and investor-friendly",
                "cta_intent": "Invite confident exploration",
                "key_value_proposition": "Bonds can offer stronger flexibility and smarter growth.",
                "important_keywords": ["bonds", "stable growth", "investor confidence"],
                "emotional_messaging_direction": "Confidence",
                "what_must_be_avoided_in_messaging": ["fear", "panic"],
            },
            planning={
                "headline": "Move Beyond FDs",
                "body": "Discover steadier paths to financial growth.",
                "cta": "Explore Bonds",
                "hashtags": ["#Jiraaf"],
                "metadata": {
                    "supporting_line": "Clearer options for measured growth.",
                    "proof_points": ["Higher flexibility", "Better yield potential", "Regulated access"],
                    "stat_highlights": ["Stable", "Confident"],
                    "visual_direction": "Premium financial hero with restrained overlays",
                    "design_style": "editorial finance social creative",
                    "image_prompt": "A premium financial visual with no text",
                },
                "creative_decision": {
                    "layout_mode": "synthesized_layout",
                    "confidence": 0.79,
                    "reasoning": ["Image-led social creative fits the objective"],
                    "adaptations": {},
                    "asset_strategy": {
                        "use_generated_image": True,
                        "icon_sequence": ["icon-1", "icon-2", "icon-3"],
                        "dominant_visual_system": "generated_image",
                    },
                },
                "scene_graph": {
                    "canvas": {"width": 1080, "height": 1080, "platform": "instagram", "file_type": "png"},
                    "layout_mode": "synthesized_layout",
                    "confidence": 0.79,
                    "layers": ["background", "primary_visual", "content", "brand"],
                    "styles": {"layout_archetype": "hero_overlay"},
                    "elements": [
                        {"element_id": "background", "element_type": "background", "role": "background", "layer": "background", "geometry": {"x": 0, "y": 0, "width": 1, "height": 1, "units": "normalized"}, "style": {"fill": "#6C63FF"}},
                        {"element_id": "hero", "element_type": "image", "role": "image", "layer": "primary_visual", "geometry": {"x": 0.42, "y": 0.08, "width": 0.5, "height": 0.82, "units": "normalized"}, "asset": {"asset_role": "ai_image"}, "style": {"fit": "cover"}},
                        {"element_id": "headline", "element_type": "text", "role": "headline", "layer": "content", "geometry": {"x": 0.08, "y": 0.12, "width": 0.26, "height": 0.12, "units": "normalized"}, "text": "Move Beyond FDs", "style": {"fill": "#6C63FF", "font_size": 52}},
                        {"element_id": "icon_1", "element_type": "icon", "role": "icon", "layer": "content", "geometry": {"x": 0.1, "y": 0.42, "width": 0.08, "height": 0.08, "units": "normalized"}, "asset": {"asset_id": "icon-1", "asset_role": "icon", "trust_level": "trusted"}},
                        {"element_id": "icon_2", "element_type": "icon", "role": "icon", "layer": "content", "geometry": {"x": 0.1, "y": 0.54, "width": 0.08, "height": 0.08, "units": "normalized"}, "asset": {"asset_id": "icon-2", "asset_role": "icon", "trust_level": "trusted"}},
                        {"element_id": "icon_3", "element_type": "icon", "role": "icon", "layer": "content", "geometry": {"x": 0.1, "y": 0.66, "width": 0.08, "height": 0.08, "units": "normalized"}, "asset": {"asset_id": "icon-3", "asset_role": "icon", "trust_level": "trusted"}},
                        {"element_id": "logo", "element_type": "logo", "role": "logo", "layer": "brand", "geometry": {"x": 0.08, "y": 0.07, "width": 0.18, "height": 0.08, "units": "normalized"}, "asset": {"asset_role": "logo", "trust_level": "trusted"}},
                        {"element_id": "cta", "element_type": "text", "role": "cta", "layer": "brand", "geometry": {"x": 0.08, "y": 0.8, "width": 0.26, "height": 0.08, "units": "normalized"}, "text": "Explore Bonds", "style": {"fill_role": "light_text", "background_fill_role": "primary"}},
                    ],
                },
            },
            repair={
                "creative_decision": {
                    "layout_mode": "synthesized_layout",
                    "confidence": 0.84,
                    "reasoning": ["Repair to one dominant image-led system", "Remove off-brand icon stamp treatment"],
                    "adaptations": {},
                    "asset_strategy": {"use_generated_image": True, "dominant_visual_system": "generated_image"},
                },
                "scene_graph": {
                    "canvas": {"width": 1080, "height": 1080, "platform": "instagram", "file_type": "png"},
                    "layout_mode": "synthesized_layout",
                    "confidence": 0.84,
                    "layers": ["background", "primary_visual", "decorative", "content", "brand"],
                    "styles": {"layout_archetype": "hero_overlay"},
                    "elements": [
                        {"element_id": "background", "element_type": "background", "role": "background", "layer": "background", "geometry": {"x": 0, "y": 0, "width": 1, "height": 1, "units": "normalized"}, "style": {"fill_role": "background"}},
                        {"element_id": "hero", "element_type": "image", "role": "image", "layer": "primary_visual", "geometry": {"x": 0.36, "y": 0.06, "width": 0.56, "height": 0.84, "units": "normalized"}, "asset": {"asset_role": "ai_image"}, "style": {"fit": "cover"}},
                        {"element_id": "headline", "element_type": "text", "role": "headline", "layer": "content", "geometry": {"x": 0.08, "y": 0.14, "width": 0.22, "height": 0.14, "units": "normalized"}, "text": "Move Beyond FDs", "style": {"fill_role": "primary", "font_role": "heading_sans", "font_size": 52}},
                        {"element_id": "proof_points", "element_type": "text", "role": "proof_points", "layer": "content", "geometry": {"x": 0.08, "y": 0.34, "width": 0.22, "height": 0.2, "units": "normalized"}, "text": ["Higher flexibility", "Better yield potential", "Regulated access"], "style": {"fill_role": "secondary_text", "font_role": "body_sans", "font_size": 20}},
                        {"element_id": "cta", "element_type": "text", "role": "cta", "layer": "brand", "geometry": {"x": 0.08, "y": 0.78, "width": 0.26, "height": 0.08, "units": "normalized"}, "text": "Explore Bonds", "style": {"fill_role": "light_text", "background_fill_role": "primary", "font_role": "cta_sans"}},
                        {"element_id": "logo", "element_type": "logo", "role": "logo", "layer": "brand", "geometry": {"x": 0.08, "y": 0.07, "width": 0.18, "height": 0.08, "units": "normalized"}, "asset": {"asset_role": "logo", "trust_level": "trusted"}},
                    ],
                },
            },
        )
    )

    request = _build_request(
        prompt="Create an engaging Instagram post about why investors are shifting from fixed deposits to bonds in 2026.",
        generate_image=False,
    )
    request.asset_catalog = [
        {"asset_id": "icon-1", "asset_role": "icon", "storage_path": "icons/1.png", "trust_level": "trusted"},
        {"asset_id": "icon-2", "asset_role": "icon", "storage_path": "icons/2.png", "trust_level": "trusted"},
        {"asset_id": "icon-3", "asset_role": "icon", "storage_path": "icons/3.png", "trust_level": "trusted"},
    ]

    response = service.generate(request)

    issue_ids = {issue.rule_id for issue in response.validation_report.issues}
    assert response.repair_attempts == 1
    assert response.validation_report.status == "clean"
    assert "color_palette_violation" not in issue_ids
    assert "icon_stamp_column" not in issue_ids
    assert all(element.role != "icon" for element in response.scene_graph.elements if element.visible)
