from __future__ import annotations

from typing import Any

from app.ai.contracts import BlueprintPayload, StructuredTextPayload


class CompositionPlannerService:
    def _choose_layout_archetype(
        self,
        *,
        prompt: str,
        studio_panel: dict[str, Any],
        blueprint: BlueprintPayload,
        text_payload: StructuredTextPayload,
        compiled_context: dict[str, Any],
    ) -> str:
        mode = blueprint.source_mode
        if mode == "exact_template":
            return "template_lock"
        if mode == "adapted_template":
            return "template_adapt"

        lowered_prompt = prompt.lower()
        render_constraints = compiled_context.get("render_constraints", {}) or {}
        audience_brief = compiled_context.get("audience_brief", {}) or {}
        visual_brief = compiled_context.get("brand_visual_brief", {}) or {}
        proof_points = text_payload.metadata.get("proof_points", []) or []
        stat_highlights = text_payload.metadata.get("stat_highlights", []) or []
        format_name = studio_panel.get("format", "")
        platform = studio_panel.get("platform_preset", "")
        text_density = render_constraints.get("text_density", "medium")

        if format_name == "infographic":
            return "infographic_stack"
        if any(token in lowered_prompt for token in ["compare", "comparison", "versus", "vs "]):
            return "comparison_board"
        if any(token in lowered_prompt for token in ["tip", "tips", "strategy", "strategies", "how to", "guide", "steps", "checklist"]):
            return "checklist_card" if platform == "instagram" else "insight_split"
        if len(proof_points) >= 3 or len(stat_highlights) >= 3:
            return "stat_board" if platform != "instagram" else "checklist_card"
        if audience_brief.get("segments") and text_density == "high":
            return "insight_split"
        if visual_brief.get("decorative_assets"):
            return "editorial_hero"
        return "insight_split" if platform in {"linkedin", "x"} else "editorial_hero"

    @staticmethod
    def _background_plan(
        *,
        blueprint: BlueprintPayload,
        brand_visual_brief: dict[str, Any],
    ) -> dict[str, Any]:
        if blueprint.source_mode == "exact_template":
            return {
                "policy": "template_background",
                "template_background_required": True,
                "gradient_allowed": False,
                "palette_override_allowed": False,
            }
        if blueprint.source_mode == "adapted_template":
            return {
                "policy": "template_background_with_brand_accents",
                "template_background_required": True,
                "gradient_allowed": False,
                "palette_override_allowed": True,
            }
        palette_roles = brand_visual_brief.get("palette_roles", {}) or {}
        if palette_roles.get("secondary") and (palette_roles.get("background") or palette_roles.get("primary")):
            return {
                "policy": "brand_gradient",
                "template_background_required": False,
                "gradient_allowed": True,
                "palette_override_allowed": True,
            }
        return {
            "policy": "brand_solid_background",
            "template_background_required": False,
            "gradient_allowed": False,
            "palette_override_allowed": True,
        }

    @staticmethod
    def _brand_element_plan(blueprint: BlueprintPayload) -> dict[str, Any]:
        if blueprint.source_mode == "exact_template":
            return {
                "logo_policy": "preserve_existing",
                "header_policy": "preserve_existing",
                "footer_policy": "preserve_existing",
            }
        if blueprint.source_mode == "adapted_template":
            return {
                "logo_policy": "inject_if_missing",
                "header_policy": "preserve_if_present",
                "footer_policy": "preserve_if_present",
            }
        return {
            "logo_policy": "required",
            "header_policy": "optional",
            "footer_policy": "optional",
        }

    @staticmethod
    def _decorative_plan(
        *,
        blueprint: BlueprintPayload,
        brand_visual_brief: dict[str, Any],
    ) -> dict[str, Any]:
        if blueprint.source_mode == "exact_template":
            return {"policy": "template_only", "max_assets": 0}
        if blueprint.source_mode == "adapted_template":
            return {"policy": "light_brand_accents", "max_assets": 1}
        decorative_assets = brand_visual_brief.get("decorative_assets", []) or []
        return {
            "policy": "brand_library" if decorative_assets else "none",
            "max_assets": min(max(len(decorative_assets), 0), 3),
        }

    @staticmethod
    def _primary_visual_plan(
        *,
        blueprint: BlueprintPayload,
        adaptation_plan: dict[str, Any],
    ) -> dict[str, Any]:
        if blueprint.source_mode == "exact_template":
            return {
                "policy": "preserve_template_visual",
                "show_primary_visual_on_first_page_only": True,
            }
        if blueprint.source_mode == "adapted_template":
            return {
                "policy": "replace_with_generated" if adaptation_plan.get("replace_primary_visual") else "preserve_template_visual",
                "show_primary_visual_on_first_page_only": True,
            }
        return {
            "policy": "optional_generated",
            "show_primary_visual_on_first_page_only": True,
        }

    @staticmethod
    def _text_style_plan(
        *,
        blueprint: BlueprintPayload,
        brand_visual_brief: dict[str, Any],
    ) -> dict[str, Any]:
        precedence = "template_first" if blueprint.source_mode in {"exact_template", "adapted_template"} else "brand_first"
        return {
            "precedence": precedence,
            "font_families": brand_visual_brief.get("font_families", []) or [],
            "palette_roles": brand_visual_brief.get("palette_roles", {}) or {},
            "cta_style": "template_native" if precedence == "template_first" else "brand_button",
        }

    @staticmethod
    def _text_content_plan(
        *,
        blueprint: BlueprintPayload,
        text_payload: StructuredTextPayload,
        render_constraints: dict[str, Any],
    ) -> dict[str, Any]:
        proof_points = text_payload.metadata.get("proof_points", []) or []
        stat_highlights = text_payload.metadata.get("stat_highlights", []) or []
        return {
            "headline_word_count": len(text_payload.headline.split()),
            "body_character_count": len(text_payload.body),
            "proof_point_count": len(proof_points),
            "stat_highlight_count": len(stat_highlights),
            "prefer_compact_cta": bool(render_constraints.get("prefer_compact_cta")),
            "text_density": render_constraints.get("text_density", "medium"),
            "show_primary_visual": blueprint.source_mode != "exact_template",
        }

    def build(
        self,
        *,
        prompt: str,
        blueprint: BlueprintPayload,
        text_payload: StructuredTextPayload,
        studio_panel: dict[str, Any],
        compiled_context: dict[str, Any],
    ) -> dict[str, Any]:
        brand_visual_brief = compiled_context.get("brand_visual_brief", {}) or {}
        render_constraints = compiled_context.get("render_constraints", {}) or {}
        template_fit_brief = compiled_context.get("template_fit_brief", {}) or {}
        adaptation_plan = blueprint.adaptation_plan or template_fit_brief.get("adaptation_plan", {}) or {}
        layout_archetype = self._choose_layout_archetype(
            prompt=prompt,
            studio_panel=studio_panel,
            blueprint=blueprint,
            text_payload=text_payload,
            compiled_context=compiled_context,
        )
        return {
            "canvas_plan": {
                "platform_preset": blueprint.platform_preset,
                "export_format": blueprint.export_format,
                "size": render_constraints.get("canvas_size", studio_panel.get("size", {})),
            },
            "layout_plan": {
                "mode": blueprint.source_mode,
                "layout_type": blueprint.layout_type,
                "layout_archetype": layout_archetype,
                "zone_roles": [zone.role for zone in blueprint.zones],
                "template_preservation_level": "strict" if blueprint.source_mode == "exact_template" else ("guided" if blueprint.source_mode == "adapted_template" else "brand_native"),
            },
            "background_plan": self._background_plan(
                blueprint=blueprint,
                brand_visual_brief=brand_visual_brief,
            ),
            "brand_element_plan": self._brand_element_plan(blueprint),
            "decorative_plan": self._decorative_plan(
                blueprint=blueprint,
                brand_visual_brief=brand_visual_brief,
            ),
            "primary_visual_plan": self._primary_visual_plan(
                blueprint=blueprint,
                adaptation_plan=adaptation_plan,
            ),
            "text_style_plan": self._text_style_plan(
                blueprint=blueprint,
                brand_visual_brief=brand_visual_brief,
            ),
            "text_content_plan": self._text_content_plan(
                blueprint=blueprint,
                text_payload=text_payload,
                render_constraints=render_constraints,
            ),
            "qa_plan": {
                "checks": [
                    "overflow",
                    "contrast",
                    "logo_visibility",
                    "cta_visibility",
                    "brand_fidelity",
                    "template_fidelity" if blueprint.source_mode != "synthesized_layout" else "layout_balance",
                ],
                "retry_on_failure": blueprint.source_mode != "exact_template",
            },
        }
