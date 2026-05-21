from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID
from uuid import uuid4

from PIL import Image
from PIL import ImageDraw

from app.ai.contracts import AIOrchestrationRequest
from app.ai.contracts import RendererInput
from app.ai.orchestrator import AIOrchestratorService
from app.core.studio import resolve_studio_panel_defaults
from app.integrations.object_storage import LocalObjectStorage
from app.services.generation_trace import GenerationTraceService
from app.services.renderer import RendererService


@dataclass(slots=True)
class Scenario:
    name: str
    prompt: str
    message_strategy: dict[str, Any]
    planning: dict[str, Any]
    template_candidates: list[dict[str, Any]]
    template_context: dict[str, Any] | None = None
    layout_decision: dict[str, Any] | None = None
    logo_mode: str = "actual"
    generate_image: bool = True
    platform_preset: str = "instagram"
    format_name: str = "static"
    file_type: str = "png"


class StubTextProvider:
    provider_name = "stub-demo-text"

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario

    def generate_structured_json(self, envelope, fallback):  # noqa: ANN001
        system_text = str(envelope.system or "")
        if "senior brand content strategist" in system_text:
            return self.scenario.message_strategy
        if "scene-graph repair engine" in system_text:
            return {
                "creative_decision": self.scenario.planning.get("creative_decision", {}),
                "scene_graph": self.scenario.planning.get("scene_graph", {}),
            }
        return self.scenario.planning

    def generate_text(self, envelope, fallback):  # noqa: ANN001
        return "Stubbed supporting research summary."


class StubImageProvider:
    provider_name = "stub-demo-image"

    def __init__(self, storage: LocalObjectStorage, scenario_name: str) -> None:
        self.storage = storage
        self.scenario_name = scenario_name

    def generate(self, tenant_id: UUID, brand_space_id: UUID, prompt: str) -> dict[str, Any]:
        prompt_lower = prompt.lower()
        image = Image.new("RGB", (1080, 1080), "#F8F7F2")
        draw = ImageDraw.Draw(image)

        if "flight" in prompt_lower or "travel" in prompt_lower or "airport" in prompt_lower:
            self._draw_travel_visual(draw)
        elif "bond" in prompt_lower or "fixed deposit" in prompt_lower or "investor" in prompt_lower:
            self._draw_finance_visual(draw)
        else:
            self._draw_generic_brand_visual(draw)

        buffer = BytesIO()
        image.save(buffer, format="PNG")
        stored = self.storage.save_bytes(
            tenant_id,
            brand_space_id,
            "generated",
            f"{self.scenario_name}-hero.png",
            buffer.getvalue(),
        )
        return {
            "mime_type": "image/png",
            "storage_path": stored.storage_path,
            "width": 1080,
            "height": 1080,
            "asset_role": "ai_image",
        }

    @staticmethod
    def _draw_travel_visual(draw: ImageDraw.ImageDraw) -> None:
        draw.rectangle((0, 0, 1080, 1080), fill="#EAE6DD")
        draw.rounded_rectangle((560, 70, 1020, 1010), radius=36, fill="#DDEAF3")
        draw.ellipse((690, 70, 1035, 350), fill="#00CB91")
        draw.rounded_rectangle((85, 140, 520, 910), radius=38, fill="#FBF8F0")
        draw.rounded_rectangle((600, 300, 955, 870), radius=26, fill="#003975")
        draw.ellipse((660, 395, 890, 640), fill="#FFA400")
        draw.rounded_rectangle((620, 690, 900, 760), radius=22, fill="#FFFFFF")
        draw.rounded_rectangle((620, 785, 905, 855), radius=22, fill="#00CB91")
        draw.polygon([(840, 150), (1010, 210), (940, 270), (905, 365), (855, 340), (860, 270), (780, 245)], fill="#0F6B5B")

    @staticmethod
    def _draw_finance_visual(draw: ImageDraw.ImageDraw) -> None:
        draw.rectangle((0, 0, 1080, 1080), fill="#F4F1EA")
        draw.rounded_rectangle((70, 90, 1010, 1000), radius=42, fill="#F8F5EF")
        draw.rounded_rectangle((620, 145, 990, 945), radius=30, fill="#003975")
        draw.ellipse((650, 190, 940, 470), fill="#00CB91")
        draw.rounded_rectangle((135, 220, 520, 470), radius=24, fill="#FFFFFF")
        draw.rounded_rectangle((135, 535, 520, 835), radius=24, fill="#FFF7E5")
        draw.rectangle((195, 625, 460, 645), fill="#FFA400")
        draw.rectangle((195, 680, 420, 700), fill="#003975")
        draw.rectangle((195, 735, 440, 755), fill="#00CB91")
        draw.rectangle((705, 585, 930, 705), fill="#FFFFFF")
        draw.ellipse((740, 765, 925, 940), fill="#FFA400")

    @staticmethod
    def _draw_generic_brand_visual(draw: ImageDraw.ImageDraw) -> None:
        draw.rectangle((0, 0, 1080, 1080), fill="#EEF6FF")
        draw.rounded_rectangle((80, 120, 1000, 980), radius=42, fill="#FFFFFF")
        draw.ellipse((640, 100, 1030, 430), fill="#00CB91")
        draw.rounded_rectangle((580, 240, 930, 880), radius=28, fill="#003975")
        draw.rounded_rectangle((120, 260, 470, 430), radius=22, fill="#F8F1D7")
        draw.rounded_rectangle((120, 500, 470, 840), radius=22, fill="#F1F6FB")


def _base_brand_context(logo_asset_id: UUID) -> dict[str, Any]:
    return {
        "brand_name": "Jiraaf",
        "brand_description": "Curated fixed-income investments for modern Indian investors.",
        "guardrails": {},
        "foundations": {
            "brand_foundation": "Build trust through clarity, confidence, and measured optimism.",
        },
        "voice_tone": {
            "primary_emotion": "confidence",
            "avoided_emotion": "panic",
            "tone_attributes": ["trustworthy", "optimistic", "clear"],
        },
        "identity": {
            "logo_asset_id": str(logo_asset_id),
            "brand_name": "Jiraaf",
        },
        "audience_insights": {
            "pain_points": ["uncertain returns", "complex planning", "last-minute booking costs"],
            "motivations": ["financial growth", "smarter planning", "travel confidence"],
        },
        "visual_identity": {
            "brand_color_palette": {
                "primary": "#003975",
                "secondary": "#FFA400",
                "accent": "#00CB91",
                "background": "#F5F1E9",
                "surface": "#FFF9F2",
            },
            "palette_entries": [
                {"role": "primary", "color_name": "Regal Blue", "hex_code": "#003975"},
                {"role": "secondary", "color_name": "Orange Peel", "hex_code": "#FFA400"},
                {"role": "accent", "color_name": "Caribbean Green", "hex_code": "#00CB91"},
                {"role": "background", "color_name": "Warm Sand", "hex_code": "#F5F1E9"},
                {"role": "surface", "color_name": "Soft Ivory", "hex_code": "#FFF9F2"},
            ],
            "typography": {
                "font_families": [{"name": "DM Sans"}],
            },
        },
    }


def _scenario_travel_low_cost() -> Scenario:
    return Scenario(
        name="travel_low_cost_image_led",
        prompt="Create an engaging Instagram post that shares tips and strategies to book flights at a lower cost.",
        message_strategy={
            "primary_campaign_theme": "Travel smarter with lower-cost flight planning",
            "core_audience_message": "Practical booking habits can help travelers spend less and plan with more confidence.",
            "headline_direction": "Confident and benefit-led",
            "supporting_copy_direction": "Short, premium, action-oriented",
            "cta_intent": "Encourage confident exploration",
            "key_value_proposition": "Small planning habits can unlock better fares and better journeys.",
            "important_keywords": ["lower-cost flights", "fare alerts", "flexible dates", "smarter travel"],
            "emotional_messaging_direction": "Confidence and optimism",
            "what_must_be_avoided_in_messaging": ["panic booking", "fear of missing out", "hype"],
        },
        planning={
            "headline": "Book Flights Smarter",
            "body": "Use flexible dates, fare alerts, and better timing to spend less on every trip.",
            "cta": "Plan with Confidence",
            "hashtags": ["#TravelSmarter", "#Jiraaf"],
            "metadata": {
                "supporting_line": "A few better habits can lead to better fares.",
                "proof_points": ["Compare multiple routes", "Track fare drops", "Stay flexible on timing"],
                "stat_highlights": ["Lower fares", "Smarter timing"],
                "visual_direction": "Premium travel lifestyle image with elegant overlay space",
                "design_style": "editorial travel social creative",
                "image_prompt": "A premium airport travel planning scene with no text, no icons, no logos, no stickers",
            },
            "creative_decision": {
                "layout_mode": "synthesized_layout",
                "confidence": 0.9,
                "reasoning": [
                    "Travel social prompt benefits from an image-led hero composition.",
                    "No exact editable template is required.",
                ],
                "adaptations": {},
                "asset_strategy": {
                    "use_generated_image": True,
                    "use_template_background": False,
                    "use_brand_reference_assets": False,
                    "dominant_visual_system": "generated_image",
                    "logo_injection_required": True,
                },
            },
            "scene_graph": {
                "canvas": {"width": 1080, "height": 1080, "platform": "instagram", "file_type": "png"},
                "layout_mode": "synthesized_layout",
                "confidence": 0.9,
                "layers": ["background", "primary_visual", "content", "brand"],
                "styles": {"layout_archetype": "hero_overlay"},
                "validation_hints": {"template_surface_policy": "style_reference_only"},
                "elements": [
                    {"element_id": "background", "element_type": "background", "role": "background", "layer": "background", "geometry": {"x": 0, "y": 0, "width": 1, "height": 1, "units": "normalized"}, "style": {"fill_role": "background"}},
                    {"element_id": "hero", "element_type": "image", "role": "image", "layer": "primary_visual", "geometry": {"x": 0.5, "y": 0.05, "width": 0.43, "height": 0.82, "units": "normalized"}, "asset": {"asset_role": "ai_image"}, "style": {"fit": "cover", "border_radius": 28}},
                    {"element_id": "headline", "element_type": "text", "role": "headline", "layer": "content", "geometry": {"x": 0.08, "y": 0.12, "width": 0.34, "height": 0.16, "units": "normalized"}, "text": "Book Flights Smarter", "style": {"font_role": "heading_sans", "fill_role": "primary", "font_size": 58}},
                    {"element_id": "supporting_line", "element_type": "text", "role": "supporting_line", "layer": "content", "geometry": {"x": 0.08, "y": 0.3, "width": 0.33, "height": 0.1, "units": "normalized"}, "text": "A few better habits can lead to better fares.", "style": {"font_role": "body_sans", "fill_role": "secondary_text", "font_size": 24}},
                    {"element_id": "proof_points", "element_type": "text", "role": "proof_points", "layer": "content", "geometry": {"x": 0.08, "y": 0.45, "width": 0.32, "height": 0.2, "units": "normalized"}, "text": ["Compare multiple routes", "Track fare drops", "Stay flexible on timing"], "style": {"font_role": "body_sans", "fill_role": "secondary_text", "font_size": 20}},
                    {"element_id": "cta", "element_type": "text", "role": "cta", "layer": "brand", "geometry": {"x": 0.08, "y": 0.79, "width": 0.31, "height": 0.08, "units": "normalized"}, "text": "Plan with Confidence", "style": {"font_role": "cta_sans", "fill_role": "light_text", "background_fill_role": "primary", "font_size": 24}},
                    {"element_id": "logo", "element_type": "logo", "role": "logo", "layer": "brand", "geometry": {"x": 0.76, "y": 0.08, "width": 0.16, "height": 0.08, "units": "normalized"}, "asset": {"asset_role": "logo", "trust_level": "trusted"}, "style": {"fit": "contain"}},
                ],
            },
        },
        template_candidates=[],
        layout_decision={"mode": "synthesized_layout"},
        logo_mode="actual",
    )


def _scenario_bonds_support_fallback() -> Scenario:
    return Scenario(
        name="bonds_support_fallback",
        prompt="Create an engaging Instagram post about why investors are shifting from fixed deposits to bonds in 2026.",
        message_strategy={
            "primary_campaign_theme": "A smarter shift from FDs to bonds",
            "core_audience_message": "Investors want more flexibility, better outcomes, and more confident long-term growth.",
            "headline_direction": "Premium finance, clear and calm",
            "supporting_copy_direction": "Short and educational",
            "cta_intent": "Prompt confident exploration",
            "key_value_proposition": "Bonds can offer stronger growth potential with more flexibility than traditional FDs.",
            "important_keywords": ["bonds", "fixed deposits", "2026 investing", "flexibility"],
            "emotional_messaging_direction": "Confidence and clarity",
            "what_must_be_avoided_in_messaging": ["panic", "fear-driven claims", "guaranteed riches"],
        },
        planning={
            "headline": "Move Beyond Traditional FDs",
            "body": "Explore secure, regulated bond options built for steadier long-term growth.",
            "cta": "Start Investing with Confidence",
            "hashtags": ["#Bonds", "#Jiraaf"],
            "metadata": {
                "supporting_line": "A steadier way to think about growth in 2026.",
                "proof_points": ["Potential for higher returns", "Flexibility across goals"],
                "stat_highlights": ["2026 shift", "Flexible growth"],
                "visual_direction": "Premium finance lifestyle image with a calm editorial treatment",
                "design_style": "finance social image-led creative",
                "image_prompt": "A premium finance editorial scene with no text, no logos, no stickers",
            },
            "creative_decision": {
                "layout_mode": "synthesized_layout",
                "confidence": 0.61,
                "reasoning": ["Image-led finance creative fits the objective."],
                "adaptations": {},
                "asset_strategy": {
                    "use_generated_image": True,
                    "dominant_visual_system": "generated_image",
                    "logo_injection_required": True,
                },
            },
            "scene_graph": {
                "canvas": {"width": 1080, "height": 1080, "platform": "instagram", "file_type": "png"},
                "layout_mode": "synthesized_layout",
                "confidence": 0.61,
                "layers": ["background", "primary_visual"],
                "styles": {"layout_archetype": "hero_overlay"},
                "elements": [
                    {"role": "image", "layer": "primary_visual", "geometry": {"x": 0.52, "y": 0.08, "width": 0.38, "height": 0.74, "units": "normalized"}, "asset_role": "ai_image", "style": {"fit": "cover"}},
                ],
            },
        },
        template_candidates=[],
        layout_decision={"mode": "synthesized_layout"},
        logo_mode="stale_recover",
    )


def _scenario_flattened_template_reference() -> Scenario:
    return Scenario(
        name="flattened_template_style_reference",
        prompt="Create an engaging Instagram post that shares tips and strategies to book flights at a lower cost.",
        message_strategy={
            "primary_campaign_theme": "Affordable travel through smarter planning",
            "core_audience_message": "A cleaner booking plan helps reduce travel costs without stress.",
            "headline_direction": "Helpful and polished",
            "supporting_copy_direction": "Simple social copy",
            "cta_intent": "Invite smart next action",
            "key_value_proposition": "Travel planning habits can lead to lower fares and more confident bookings.",
            "important_keywords": ["flight tips", "fare drops", "flexible dates"],
            "emotional_messaging_direction": "Confident calm",
            "what_must_be_avoided_in_messaging": ["chaos", "panic", "cheap-looking gimmicks"],
        },
        planning={
            "headline": "Lower Fares, Better Timing",
            "body": "Book early, compare routes, and stay flexible to unlock lower-cost trips.",
            "cta": "Travel Smarter",
            "hashtags": ["#FlightTips", "#Jiraaf"],
            "metadata": {
                "supporting_line": "Smarter timing can mean a smarter ticket.",
                "proof_points": ["Compare routes", "Book before peak demand", "Track fare drops"],
                "stat_highlights": ["Cheaper fares", "Better timing"],
                "visual_direction": "Premium reinterpretation of a flat travel poster",
                "design_style": "travel editorial reinterpretation",
                "image_prompt": "A premium travel planning scene with no text, no icons, no logos",
            },
            "creative_decision": {
                "layout_mode": "adapted_template",
                "selected_template_id": "tpl_pdf_001",
                "confidence": 0.84,
                "reasoning": [
                    "Template style is useful for inspiration.",
                    "Flattened text surface should be reinterpreted, not directly overlaid.",
                ],
                "adaptations": {"reinterpret_flattened_template": True, "remove_footer": True},
                "asset_strategy": {
                    "use_generated_image": True,
                    "use_template_background": False,
                    "dominant_visual_system": "generated_image",
                    "template_surface_policy": "style_reference_only",
                    "logo_injection_required": True,
                },
            },
            "scene_graph": {
                "canvas": {"width": 1080, "height": 1080, "platform": "instagram", "file_type": "png"},
                "layout_mode": "adapted_template",
                "confidence": 0.84,
                "layers": ["background", "primary_visual", "content", "brand"],
                "styles": {"layout_archetype": "hero_overlay"},
                "validation_hints": {"template_surface_policy": "style_reference_only"},
                "template_adaptation": {"selected_template_id": "tpl_pdf_001", "reinterpret_flattened_template": True},
                "elements": [
                    {"element_id": "background", "element_type": "background", "role": "background", "layer": "background", "geometry": {"x": 0, "y": 0, "width": 1, "height": 1, "units": "normalized"}, "style": {"fill_role": "background"}},
                    {"element_id": "hero", "element_type": "image", "role": "image", "layer": "primary_visual", "geometry": {"x": 0.48, "y": 0.08, "width": 0.4, "height": 0.76, "units": "normalized"}, "asset": {"asset_role": "ai_image"}, "style": {"fit": "cover", "border_radius": 26}},
                    {"element_id": "headline", "element_type": "text", "role": "headline", "layer": "content", "geometry": {"x": 0.08, "y": 0.12, "width": 0.3, "height": 0.14, "units": "normalized"}, "text": "Lower Fares, Better Timing", "style": {"font_role": "heading_sans", "fill_role": "primary", "font_size": 52}},
                    {"element_id": "supporting_line", "element_type": "text", "role": "supporting_line", "layer": "content", "geometry": {"x": 0.08, "y": 0.29, "width": 0.28, "height": 0.1, "units": "normalized"}, "text": "Smarter timing can mean a smarter ticket.", "style": {"font_role": "body_sans", "fill_role": "secondary_text", "font_size": 22}},
                    {"element_id": "proof_points", "element_type": "text", "role": "proof_points", "layer": "content", "geometry": {"x": 0.08, "y": 0.43, "width": 0.3, "height": 0.18, "units": "normalized"}, "text": ["Compare routes", "Book before peak demand", "Track fare drops"], "style": {"font_role": "body_sans", "fill_role": "secondary_text", "font_size": 20}},
                    {"element_id": "cta", "element_type": "text", "role": "cta", "layer": "brand", "geometry": {"x": 0.08, "y": 0.78, "width": 0.26, "height": 0.08, "units": "normalized"}, "text": "Travel Smarter", "style": {"font_role": "cta_sans", "fill_role": "light_text", "background_fill_role": "primary", "font_size": 24}},
                    {"element_id": "logo", "element_type": "logo", "role": "logo", "layer": "brand", "geometry": {"x": 0.76, "y": 0.08, "width": 0.16, "height": 0.08, "units": "normalized"}, "asset": {"asset_role": "logo", "trust_level": "trusted"}, "style": {"fit": "contain"}},
                ],
            },
        },
        template_candidates=[
            {
                "template_id": "tpl_pdf_001",
                "name": "Travel Poster PDF",
                "score": 0.79,
                "match_type": "reference_only_flattened_text",
                "reinterpretation_suitability": 0.95,
                "style_only_suitability": 0.96,
                "editability_score": 0.24,
            }
        ],
        template_context={
            "template_id": "tpl_pdf_001",
            "overlay_safe": False,
            "text_overlay_risk": 0.92,
        },
        layout_decision={"mode": "adapted_template", "template_id": "tpl_pdf_001"},
        logo_mode="actual",
    )


def _long_body(sentences: list[str]) -> str:
    return " ".join(sentence.strip().rstrip(".") + "." for sentence in sentences if sentence.strip())


def _generic_scene_graph(
    *,
    platform_preset: str,
    format_name: str,
    file_type: str = "png",
    headline: str,
    supporting_line: str,
    proof_points: list[str],
    cta: str,
    layout_mode: str,
    confidence: float,
    include_image: bool = True,
    template_surface_policy: str | None = None,
    selected_template_id: str | None = None,
) -> dict[str, Any]:
    studio_panel = resolve_studio_panel_defaults(
        {"platform_preset": platform_preset, "format": format_name, "file_type": file_type}
    )
    width = studio_panel["size"]["width"]
    height = studio_panel["size"]["height"]
    is_wide = width > height
    is_tall = height > width
    hero_geometry = (
        {"x": 0.52, "y": 0.08, "width": 0.4, "height": 0.76, "units": "normalized"}
        if not is_wide
        else {"x": 0.58, "y": 0.12, "width": 0.32, "height": 0.64, "units": "normalized"}
    )
    headline_geometry = (
        {"x": 0.07, "y": 0.12, "width": 0.38, "height": 0.16, "units": "normalized"}
        if not is_wide
        else {"x": 0.07, "y": 0.12, "width": 0.42, "height": 0.16, "units": "normalized"}
    )
    supporting_geometry = (
        {"x": 0.07, "y": 0.3, "width": 0.36, "height": 0.1, "units": "normalized"}
        if not is_wide
        else {"x": 0.07, "y": 0.32, "width": 0.42, "height": 0.1, "units": "normalized"}
    )
    proof_geometry = (
        {"x": 0.07, "y": 0.45, "width": 0.36, "height": 0.18, "units": "normalized"}
        if not is_wide
        else {"x": 0.07, "y": 0.48, "width": 0.42, "height": 0.16, "units": "normalized"}
    )
    cta_geometry = (
        {"x": 0.07, "y": 0.81, "width": 0.3, "height": 0.08, "units": "normalized"}
        if not is_tall
        else {"x": 0.07, "y": 0.89, "width": 0.34, "height": 0.06, "units": "normalized"}
    )
    logo_geometry = (
        {"x": 0.76, "y": 0.08, "width": 0.16, "height": 0.08, "units": "normalized"}
        if not is_wide
        else {"x": 0.76, "y": 0.08, "width": 0.14, "height": 0.08, "units": "normalized"}
    )
    elements: list[dict[str, Any]] = [
        {"element_id": "background", "element_type": "background", "role": "background", "layer": "background", "geometry": {"x": 0, "y": 0, "width": 1, "height": 1, "units": "normalized"}, "style": {"fill_role": "background"}},
        {"element_id": "headline", "element_type": "text", "role": "headline", "layer": "content", "geometry": headline_geometry, "text": headline, "style": {"font_role": "heading_sans", "fill_role": "primary", "font_size": 56 if not is_tall else 62}},
        {"element_id": "supporting_line", "element_type": "text", "role": "supporting_line", "layer": "content", "geometry": supporting_geometry, "text": supporting_line, "style": {"font_role": "body_sans", "fill_role": "secondary_text", "font_size": 22 if not is_tall else 24}},
        {"element_id": "proof_points", "element_type": "text", "role": "proof_points", "layer": "content", "geometry": proof_geometry, "text": proof_points, "style": {"font_role": "body_sans", "fill_role": "secondary_text", "font_size": 20}},
        {"element_id": "cta", "element_type": "text", "role": "cta", "layer": "brand", "geometry": cta_geometry, "text": cta, "style": {"font_role": "cta_sans", "fill_role": "light_text", "background_fill_role": "primary", "font_size": 24}},
        {"element_id": "logo", "element_type": "logo", "role": "logo", "layer": "brand", "geometry": logo_geometry, "asset": {"asset_role": "logo", "trust_level": "trusted"}, "style": {"fit": "contain"}},
    ]
    if include_image:
        elements.insert(
            1,
            {"element_id": "hero", "element_type": "image", "role": "image", "layer": "primary_visual", "geometry": hero_geometry, "asset": {"asset_role": "ai_image"}, "style": {"fit": "cover", "border_radius": 28}},
        )
    validation_hints = {}
    if template_surface_policy:
        validation_hints["template_surface_policy"] = template_surface_policy
    template_adaptation = {"selected_template_id": selected_template_id} if selected_template_id else {}
    if template_surface_policy == "style_reference_only" and selected_template_id:
        template_adaptation["reinterpret_flattened_template"] = True
    return {
        "canvas": {"width": width, "height": height, "platform": platform_preset, "file_type": file_type},
        "layout_mode": layout_mode,
        "confidence": confidence,
        "layers": ["background", "primary_visual", "content", "brand"] if include_image else ["background", "content", "brand"],
        "styles": {"layout_archetype": "hero_overlay", "layout_type": format_name},
        "validation_hints": validation_hints,
        "template_adaptation": template_adaptation,
        "elements": elements,
    }


def _generic_scenario(
    *,
    name: str,
    prompt: str,
    headline: str,
    supporting_line: str,
    body_sentences: list[str],
    proof_points: list[str],
    cta: str,
    platform_preset: str,
    format_name: str,
    file_type: str | None = None,
    layout_mode: str = "synthesized_layout",
    confidence: float = 0.86,
    template_candidates: list[dict[str, Any]] | None = None,
    template_context: dict[str, Any] | None = None,
    layout_decision: dict[str, Any] | None = None,
    template_surface_policy: str | None = None,
    selected_template_id: str | None = None,
    logo_mode: str = "actual",
) -> Scenario:
    body = _long_body(body_sentences)
    metadata = {
        "supporting_line": supporting_line,
        "proof_points": proof_points,
        "stat_highlights": proof_points[:2],
        "visual_direction": "Premium brand-safe social creative with clean composition",
        "design_style": "premium editorial branded creative",
        "image_prompt": "A premium branded marketing visual with no text, no fake logos, no stickers, no clip-art",
    }
    if "travel" in prompt.lower() or "flight" in prompt.lower():
        metadata["visual_direction"] = "Premium travel image-led composition with elegant negative space"
        metadata["design_style"] = "travel editorial campaign creative"
        metadata["image_prompt"] = "A premium travel planning visual with no text, no logos, no icons"
    elif "bond" in prompt.lower() or "invest" in prompt.lower() or "fixed deposit" in prompt.lower():
        metadata["visual_direction"] = "Premium finance image-led composition with clean confidence"
        metadata["design_style"] = "finance editorial campaign creative"
        metadata["image_prompt"] = "A premium finance editorial visual with no text, no logos, no icons"
    return Scenario(
        name=name,
        prompt=prompt,
        message_strategy={
            "primary_campaign_theme": headline,
            "core_audience_message": supporting_line,
            "headline_direction": "Confident and premium",
            "supporting_copy_direction": "Clear, compact, on-brand",
            "cta_intent": "Prompt a confident next step",
            "key_value_proposition": body_sentences[0],
            "important_keywords": [word for word in ["growth", "clarity", "confidence", "planning"] if word in " ".join(body_sentences).lower()] or ["confidence"],
            "emotional_messaging_direction": "Confidence and clarity",
            "what_must_be_avoided_in_messaging": ["panic", "hype", "cheap-looking phrasing"],
        },
        planning={
            "headline": headline,
            "body": body,
            "cta": cta,
            "hashtags": ["#Jiraaf", f"#{platform_preset.title().replace('_', '')}"],
            "metadata": metadata,
            "creative_decision": {
                "layout_mode": layout_mode,
                "selected_template_id": selected_template_id,
                "confidence": confidence,
                "reasoning": [f"Scenario tuned for {platform_preset} {format_name}."] if not selected_template_id else [f"Scenario tuned for {platform_preset} {format_name}.", "Template inspiration is available."],
                "adaptations": {"reinterpret_flattened_template": True} if template_surface_policy == "style_reference_only" and selected_template_id else {},
                "asset_strategy": {
                    "use_generated_image": True,
                    "use_template_background": False,
                    "dominant_visual_system": "generated_image",
                    "logo_injection_required": True,
                    **({"template_surface_policy": template_surface_policy} if template_surface_policy else {}),
                },
            },
            "scene_graph": _generic_scene_graph(
                platform_preset=platform_preset,
                format_name=format_name,
                file_type=file_type or ("pdf" if format_name == "pdf" else "png"),
                headline=headline,
                supporting_line=supporting_line,
                proof_points=proof_points,
                cta=cta,
                layout_mode=layout_mode,
                confidence=confidence,
                include_image=True,
                template_surface_policy=template_surface_policy,
                selected_template_id=selected_template_id,
            ),
        },
        template_candidates=template_candidates or [],
        template_context=template_context,
        layout_decision=layout_decision or {"mode": layout_mode, **({"template_id": selected_template_id} if selected_template_id else {})},
        logo_mode=logo_mode,
        platform_preset=platform_preset,
        format_name=format_name,
        file_type=file_type or ("pdf" if format_name == "pdf" else "png"),
    )


def _all_scenarios() -> list[Scenario]:
    return [
        _scenario_travel_low_cost(),
        _scenario_bonds_support_fallback(),
        _scenario_flattened_template_reference(),
        _generic_scenario(
            name="instagram_story_travel_countdown",
            prompt="Create an Instagram story with quick flight-booking tips for smarter travel planning.",
            headline="Catch Better Fares Faster",
            supporting_line="Short travel habits can make every booking decision sharper.",
            body_sentences=["Track fare alerts before peak demand", "Compare multiple date ranges before you book", "Let timing work for you, not against you"],
            proof_points=["Track alerts", "Compare dates", "Book before peaks"],
            cta="See Smarter Travel",
            platform_preset="instagram",
            format_name="story",
        ),
        _generic_scenario(
            name="instagram_poster_brand_campaign",
            prompt="Create a bold Instagram poster for Jiraaf about building travel funds with more confidence.",
            headline="Your Travel Fund, Made Smarter",
            supporting_line="A steadier financial plan can unlock more confident journeys.",
            body_sentences=["Build toward trips with calm, long-term planning", "Stay focused on progress, not panic"],
            proof_points=["Steady growth", "Calm planning", "Confident travel"],
            cta="Plan the Journey",
            platform_preset="instagram",
            format_name="poster",
        ),
        _generic_scenario(
            name="linkedin_static_bonds_education",
            prompt="Create a LinkedIn post about why investors are moving from fixed deposits to bonds in 2026.",
            headline="Why Investors Are Looking Beyond FDs",
            supporting_line="In 2026, flexibility and clearer growth potential matter more than ever.",
            body_sentences=["More investors want choices that support real long-term goals", "Clarity and flexibility now shape modern fixed-income decisions"],
            proof_points=["Growth potential", "Goal flexibility", "Clearer planning"],
            cta="Explore the Shift",
            platform_preset="linkedin",
            format_name="static",
        ),
        _generic_scenario(
            name="x_static_travel_hook",
            prompt="Create an X post visual with sharp tips to book cheaper flights.",
            headline="Lower-Cost Flights Start With Better Timing",
            supporting_line="Simple travel habits can lead to smarter fares.",
            body_sentences=["Track price drops before demand surges", "Use flexibility as an advantage when comparing options"],
            proof_points=["Watch timing", "Stay flexible", "Compare smartly"],
            cta="Travel Better",
            platform_preset="x",
            format_name="static",
        ),
        _generic_scenario(
            name="youtube_thumbnail_finance_hook",
            prompt="Create a YouTube thumbnail about smarter travel funds and regulated bond investing.",
            headline="Turn Plans Into Travel Funds",
            supporting_line="A smarter financial move can power the next journey.",
            body_sentences=["Use confidence-led investing to support future plans", "Keep the message bold and compact for video discovery"],
            proof_points=["Travel goals", "Smarter funding"],
            cta="Watch the Guide",
            platform_preset="youtube_thumbnail",
            format_name="static",
        ),
        _generic_scenario(
            name="instagram_carousel_travel_tips",
            prompt="Create an Instagram carousel with practical strategies to book cheaper flights.",
            headline="Flight Booking Habits That Save More",
            supporting_line="Break the advice into compact carousel-ready sections.",
            body_sentences=[
                "Start with flexible date windows to see the price range clearly",
                "Compare nearby airports before locking the route",
                "Use alerts to track drops instead of refreshing endlessly",
                "Book before rush periods when prices tighten quickly",
                "Review baggage rules so hidden costs do not surprise you",
                "Stay calm and consistent rather than booking in a hurry",
            ],
            proof_points=["Flexible dates", "Nearby airports", "Fare alerts"],
            cta="Swipe for Smarter Trips",
            platform_preset="instagram",
            format_name="carousel",
        ),
        _generic_scenario(
            name="linkedin_carousel_market_education",
            prompt="Create a LinkedIn carousel explaining why bonds are gaining attention in 2026.",
            headline="Why Bonds Are Getting More Attention",
            supporting_line="A carousel should build the argument across multiple pages.",
            body_sentences=[
                "Investors want choices that support both stability and future flexibility",
                "Clearer yield expectations can make planning easier",
                "Diversification matters more when cash decisions feel uncertain",
                "Goal-based investing works better with more tailored fixed-income options",
                "Transparency and trust still sit at the center of the decision",
                "The strongest communication stays calm, practical, and evidence-led",
            ],
            proof_points=["Flexibility", "Transparency", "Goal alignment"],
            cta="See the Breakdown",
            platform_preset="linkedin",
            format_name="carousel",
        ),
        _generic_scenario(
            name="instagram_infographic_flight_checklist",
            prompt="Create an Instagram infographic with a checklist to reduce flight booking costs.",
            headline="A Smarter Flight Cost Checklist",
            supporting_line="A tall format should feel structured and easy to scan.",
            body_sentences=[
                "Start with route and date flexibility",
                "Use alerts to catch shifts in pricing",
                "Compare total costs, not just headline fares",
                "Check baggage and timing before confirming",
                "Book with clarity instead of pressure",
            ],
            proof_points=["Flexible routing", "Fare alerts", "Total cost checks"],
            cta="Use the Checklist",
            platform_preset="instagram",
            format_name="infographic",
        ),
        _generic_scenario(
            name="linkedin_infographic_bond_overview",
            prompt="Create a LinkedIn infographic that explains key reasons investors are considering bonds in 2026.",
            headline="Bonds in 2026, Explained Clearly",
            supporting_line="A structured infographic should organize the message cleanly.",
            body_sentences=[
                "Investors want clearer routes to long-term financial planning",
                "Flexibility across goals helps modern portfolios stay useful",
                "Growth potential matters when inflation changes expectations",
                "Confidence grows when communication stays transparent and calm",
                "Strong fixed-income products balance trust with opportunity",
            ],
            proof_points=["Planning clarity", "Goal flexibility", "Transparent communication"],
            cta="Read the Snapshot",
            platform_preset="linkedin",
            format_name="infographic",
        ),
        _generic_scenario(
            name="pdf_brand_story_overview",
            prompt="Create a PDF-style brand story page about smarter travel funds and fixed-income confidence.",
            headline="A Clearer Path to Travel Goals",
            supporting_line="The PDF path should paginate longer body copy cleanly.",
            body_sentences=[
                "Smarter travel starts with calmer financial decisions",
                "Long-term planning creates room for better future experiences",
                "Clear messaging helps audiences understand how stability supports aspiration",
                "A premium PDF-style layout should still stay readable and brand-safe",
                "Use calm hierarchy and simple structure over dense visual clutter",
                "Each page should feel intentional, not like a stretched social post",
                "Pagination should preserve narrative flow instead of clipping the message abruptly",
                "Readable sections and consistent hierarchy matter more than decorative overload",
                "The reader should understand the offer, the tone, and the next step at a glance",
                "Brand trust grows when long-form communication stays clear and measured from start to finish",
            ],
            proof_points=["Travel goals", "Calm planning", "Premium clarity"],
            cta="Open the Overview",
            platform_preset="linkedin",
            format_name="pdf",
        ),
        _generic_scenario(
            name="x_poster_thought_leadership",
            prompt="Create a poster-style X visual about calm, confidence-led investing.",
            headline="Confidence Compounds Better Than Noise",
            supporting_line="Thought leadership should feel sharp, calm, and premium.",
            body_sentences=["Clear decisions support stronger long-term outcomes", "Trust grows when the message stays focused and measured"],
            proof_points=["Measured tone", "Clear value", "Long-term trust"],
            cta="Follow the Signal",
            platform_preset="x",
            format_name="poster",
        ),
        _generic_scenario(
            name="linkedin_story_launch_snippet",
            prompt="Create a LinkedIn story-style visual announcing a smarter fixed-income explainer.",
            headline="A Clearer Way to Explain Fixed Income",
            supporting_line="Story-like layouts should still preserve hierarchy and polish.",
            body_sentences=["Use a concise hero line and a supporting takeaway", "Let the image-led system do most of the heavy lifting"],
            proof_points=["Concise", "Professional", "Brand-safe"],
            cta="See the Update",
            platform_preset="linkedin",
            format_name="story",
        ),
        _generic_scenario(
            name="youtube_thumbnail_travel_hack",
            prompt="Create a YouTube thumbnail for a video about lower-cost flight booking strategies.",
            headline="Cheaper Flights, Smarter Moves",
            supporting_line="Thumbnail copy must stay compact and bold.",
            body_sentences=["Use very compact messaging for video discovery", "Keep the visual dominant and the CTA implied"],
            proof_points=["Cheaper flights", "Smarter timing"],
            cta="Watch Now",
            platform_preset="youtube_thumbnail",
            format_name="poster",
        ),
        _generic_scenario(
            name="instagram_static_flattened_reference_variant",
            prompt="Create an Instagram post inspired by an old travel poster but reimagined cleanly for Jiraaf.",
            headline="A Cleaner Way to Travel Smarter",
            supporting_line="Poster inspiration can guide tone without becoming a text-overlay surface.",
            body_sentences=["Use the old poster only as style inspiration", "The final composition should be image-led and brand-safe"],
            proof_points=["Style reference only", "No direct overlay", "Premium reinterpretation"],
            cta="See the Reframe",
            platform_preset="instagram",
            format_name="static",
            layout_mode="adapted_template",
            confidence=0.81,
            template_candidates=[
                {
                    "template_id": "tpl_reference_002",
                    "name": "Legacy Travel Poster",
                    "score": 0.72,
                    "match_type": "reference_only_flattened_text",
                    "reinterpretation_suitability": 0.93,
                    "style_only_suitability": 0.94,
                    "editability_score": 0.18,
                }
            ],
            template_context={"template_id": "tpl_reference_002", "overlay_safe": False, "text_overlay_risk": 0.95},
            template_surface_policy="style_reference_only",
            selected_template_id="tpl_reference_002",
        ),
    ]


def _studio_panel_for_scenario(scenario: Scenario) -> dict[str, Any]:
    return resolve_studio_panel_defaults(
        {
            "platform_preset": scenario.platform_preset,
            "format": scenario.format_name,
            "file_type": scenario.file_type,
        }
    )


def _build_request(
    *,
    scenario: Scenario,
    tenant_id: UUID,
    brand_space_id: UUID,
    user_id: UUID,
    logo_asset_id: UUID,
    trace_id: str,
) -> AIOrchestrationRequest:
    studio_panel = _studio_panel_for_scenario(scenario)
    return AIOrchestrationRequest(
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        user_id=user_id,
        prompt=scenario.prompt,
        studio_panel=studio_panel,
        conversation_context={"message_count": 3},
        session_memory={},
        resolved_brand_context=_base_brand_context(logo_asset_id),
        persona_context={
            "name": "Young professionals",
            "audience_goals": ["grow money", "plan smarter", "travel better"],
        },
        objective_context={
            "name": "Engagement",
            "description": "Drive premium social engagement with strong but trustworthy messaging.",
        },
        retrieved_knowledge={
            "brand": [{"content": "Jiraaf helps investors grow with curated, regulated fixed-income options."}],
            "reference_creative": [{"content": "Prefer premium, minimal, trustworthy social creatives."}],
        },
        template_context=scenario.template_context,
        template_candidates=scenario.template_candidates,
        layout_decision=scenario.layout_decision or {"mode": "synthesized_layout"},
        reference_assets=[],
        asset_catalog=[],
        platform_constraints={
            "platform_preset": studio_panel["platform_preset"],
            "format": studio_panel["format"],
            "file_type": studio_panel["file_type"],
            "size": studio_panel["size"],
        },
        resolution_policy={},
        generation_trace_id=trace_id,
        generate_image=scenario.generate_image,
    )


def _prepare_orchestrator(
    *,
    scenario: Scenario,
    storage: LocalObjectStorage,
    tracer: GenerationTraceService,
) -> AIOrchestratorService:
    service = AIOrchestratorService()
    service.trace = tracer
    service.guardrails = SimpleNamespace(
        validate_prompt=lambda *args, **kwargs: None,
        validate_output=lambda *args, **kwargs: None,
    )
    service.resolution = SimpleNamespace(
        build_plan=lambda **kwargs: SimpleNamespace(
            ordered_knowledge=kwargs.get("retrieved_knowledge", {}),
            instructions="Prefer validated brand context and concise reference knowledge.",
            metadata={"ordered_channels": sorted((kwargs.get("retrieved_knowledge") or {}).keys())},
        )
    )
    service.providers = SimpleNamespace(
        get_text_provider=lambda purpose: StubTextProvider(scenario),
        get_image_provider=lambda: StubImageProvider(storage=storage, scenario_name=scenario.name),
    )
    service.tone = SimpleNamespace(
        evaluate=lambda **kwargs: {"score": 0.92, "summary": "on-brand", "notes": ["stubbed tone evaluation"]},
    )
    return service


def _create_logo_asset(
    *,
    storage: LocalObjectStorage,
    tenant_id: UUID,
    brand_space_id: UUID,
) -> str:
    image = Image.new("RGBA", (360, 116), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, 359, 115), radius=18, fill="#003975")
    draw.rounded_rectangle((18, 20, 64, 94), radius=10, fill="#00CB91")
    draw.ellipse((28, 30, 54, 56), fill="#FFA400")
    draw.text((86, 34), "Jiraaf", fill="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    stored = storage.save_bytes(
        tenant_id,
        brand_space_id,
        "logo",
        "Jiraaf_logo.png",
        buffer.getvalue(),
    )
    return stored.storage_path


def _brand_visual_rules(brand_context: dict[str, Any]) -> dict[str, Any]:
    visual_identity = dict(brand_context.get("visual_identity", {}) or {})
    return {
        "brand_name": brand_context.get("brand_name"),
        "identity": brand_context.get("identity", {}),
        "brand_color_palette": visual_identity.get("brand_color_palette", {}),
        "palette_entries": visual_identity.get("palette_entries", []),
        "typography": visual_identity.get("typography", {}),
    }


async def _render_output(
    *,
    storage: LocalObjectStorage,
    tracer: GenerationTraceService,
    trace_id: str,
    request: AIOrchestrationRequest,
    response,
    actual_logo_path: str,
    requested_logo_path: str | None,
) -> dict[str, Any]:
    renderer = RendererService(session=None)  # type: ignore[arg-type]
    renderer.storage = storage

    render_input = RendererInput(
        tenant_id=request.tenant_id,
        brand_space_id=request.brand_space_id,
        content_version_id=uuid4(),
        studio_panel=request.studio_panel,
        blueprint=response.blueprint,
        scene_graph=response.scene_graph,
        text=response.text,
        template_metadata=request.template_context or {},
        template_asset_path=None,
        logo_asset_path=requested_logo_path,
        image_assets=response.image_assets,
        decorative_assets=[],
        font_asset_paths=[],
        brand_visual_rules=_brand_visual_rules(request.resolved_brand_context),
        layout_decision=request.layout_decision,
        creative_decision=response.creative_decision.model_dump(mode="json"),
        validation_report=response.validation_report.model_dump(mode="json"),
    )

    tracer.write_payload(
        trace_id,
        "render_input",
        {
            "requested_logo_path": requested_logo_path,
            "actual_logo_path": actual_logo_path,
            "payload": render_input.model_dump(mode="json"),
        },
    )
    render_response = await renderer.render(render_input)
    tracer.write_payload(trace_id, "render_output", render_response.model_dump(mode="json"))
    return {
        "preview_storage_path": render_response.preview_asset["storage_path"] if render_response.preview_asset else None,
        "preview_absolute_path": storage.absolute_path(render_response.preview_asset["storage_path"]) if render_response.preview_asset else None,
        "renderer_metadata": render_response.renderer_metadata,
    }


def _scenario_input_payload(scenario: Scenario, request: AIOrchestrationRequest) -> dict[str, Any]:
    return {
        "scenario": scenario.name,
        "prompt": scenario.prompt,
        "template_candidates": scenario.template_candidates,
        "template_context": scenario.template_context,
        "layout_decision": scenario.layout_decision,
        "request": request.model_dump(mode="json"),
    }


def _run_scenario(
    *,
    scenario: Scenario,
    run_root: Path,
) -> dict[str, Any]:
    tenant_id = uuid4()
    brand_space_id = uuid4()
    user_id = uuid4()
    logo_asset_id = uuid4()

    storage = LocalObjectStorage()
    storage.base_path = (run_root / "objects").resolve()
    storage.base_path.mkdir(parents=True, exist_ok=True)

    tracer = GenerationTraceService(base_dir=run_root / "traces", enabled=True)
    trace = tracer.start_trace(
        prompt=scenario.prompt,
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        metadata={"scenario": scenario.name},
    )
    if not trace:
        raise RuntimeError("Failed to start generation trace")
    trace_id = trace["trace_id"]
    trace_dir = Path(trace["trace_dir"])

    actual_logo_path = _create_logo_asset(storage=storage, tenant_id=tenant_id, brand_space_id=brand_space_id)
    request = _build_request(
        scenario=scenario,
        tenant_id=tenant_id,
        brand_space_id=brand_space_id,
        user_id=user_id,
        logo_asset_id=logo_asset_id,
        trace_id=trace_id,
    )
    tracer.write_payload(trace_id, "scenario_input", _scenario_input_payload(scenario, request))

    orchestrator = _prepare_orchestrator(scenario=scenario, storage=storage, tracer=tracer)
    response = orchestrator.generate(request)
    tracer.write_payload(
        trace_id,
        "orchestration_output",
        {
            "message_strategy": response.message_strategy.model_dump(mode="json"),
            "text": response.text.model_dump(mode="json"),
            "creative_decision": response.creative_decision.model_dump(mode="json"),
            "scene_graph": response.scene_graph.model_dump(mode="json"),
            "validation_report": response.validation_report.model_dump(mode="json"),
            "repair_attempts": response.repair_attempts,
            "explainability": response.explainability,
        },
    )

    requested_logo_path = (
        "missing/logo/Jiraaf_logo.png"
        if scenario.logo_mode == "stale_recover"
        else actual_logo_path
    )
    render_summary = asyncio.run(
        _render_output(
            storage=storage,
            tracer=tracer,
            trace_id=trace_id,
            request=request,
            response=response,
            actual_logo_path=actual_logo_path,
            requested_logo_path=requested_logo_path,
        )
    )

    summary = {
        "scenario": scenario.name,
        "prompt": scenario.prompt,
        "trace_id": trace_id,
        "trace_dir": str(trace_dir.resolve()),
        "preview_absolute_path": render_summary["preview_absolute_path"],
        "generation_path": response.explainability.get("generation_path"),
        "layout_mode": response.creative_decision.layout_mode,
        "validation_status": response.validation_report.status,
        "repair_attempts": response.repair_attempts,
        "renderer_metadata": render_summary["renderer_metadata"],
        "actual_logo_path": actual_logo_path,
        "requested_logo_path": requested_logo_path,
        "image_assets": [asset.model_dump(mode="json") for asset in response.image_assets],
    }
    tracer.write_payload(trace_id, "scenario_summary", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a stubbed end-to-end Violyt generation demo.")
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        help="Run only specific scenarios by name. Can be provided multiple times.",
    )
    args = parser.parse_args()

    selected = set(args.scenarios or [])
    scenarios = [scenario for scenario in _all_scenarios() if not selected or scenario.name in selected]
    if not scenarios:
        available = ", ".join(scenario.name for scenario in _all_scenarios())
        raise SystemExit(f"No scenarios matched. Available: {available}")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_root = (Path("storage") / "stub_demo_runs" / timestamp).resolve()
    run_root.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, Any]] = []
    for scenario in scenarios:
        try:
            summaries.append(_run_scenario(scenario=scenario, run_root=run_root))
        except Exception as exc:  # noqa: BLE001
            error_summary = {
                "scenario": scenario.name,
                "prompt": scenario.prompt,
                "error": str(exc),
            }
            summaries.append(error_summary)
            (run_root / f"{scenario.name}-error.json").write_text(
                json.dumps(error_summary, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            raise

    summary_path = run_root / "run_summary.json"
    summary_path.write_text(json.dumps(summaries, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"Stub demo run root: {run_root}")
    print(f"Run summary: {summary_path}")
    for summary in summaries:
        print(
            json.dumps(
                {
                    "scenario": summary.get("scenario"),
                    "generation_path": summary.get("generation_path"),
                    "layout_mode": summary.get("layout_mode"),
                    "validation_status": summary.get("validation_status"),
                    "repair_attempts": summary.get("repair_attempts"),
                    "preview_absolute_path": summary.get("preview_absolute_path"),
                    "trace_dir": summary.get("trace_dir"),
                    "logo_rendered": (summary.get("renderer_metadata") or {}).get("logo_rendered"),
                    "image_rendered": (summary.get("renderer_metadata") or {}).get("image_rendered"),
                    "layout_variant": (summary.get("renderer_metadata") or {}).get("layout_variant"),
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
