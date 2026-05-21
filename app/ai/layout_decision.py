from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LayoutDecision:
    mode: str
    template_id: str | None
    template_name: str | None
    rationale: list[str]
    score_breakdown: dict[str, float]
    adaptation_plan: dict[str, Any]
    brand_rule_hints: dict[str, Any]
    asset_strategy: dict[str, Any]
    review_flags: list[str]

    def to_payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "template_id": self.template_id,
            "template_name": self.template_name,
            "rationale": self.rationale,
            "score_breakdown": self.score_breakdown,
            "adaptation_plan": self.adaptation_plan,
            "brand_rule_hints": self.brand_rule_hints,
            "asset_strategy": self.asset_strategy,
            "review_flags": self.review_flags,
        }


class LayoutDecisionEngine:
    @staticmethod
    def _identity_has_logo(brand_context: dict[str, Any]) -> bool:
        identity = brand_context.get("identity", {}) or {}
        logo_assets = identity.get("logo_assets") or []
        return bool(
            identity.get("logo_asset_id")
            or identity.get("logo_asset_ids")
            or identity.get("logo_asset_path")
            or logo_assets
        )

    @staticmethod
    def _is_visual_social_request(studio_panel: dict[str, Any]) -> bool:
        format_name = str(studio_panel.get("format") or "").strip().lower()
        file_type = str(studio_panel.get("file_type") or "").strip().lower()
        return file_type in {"png", "jpg", "jpeg", "webp"} and format_name not in {"doc", "pdf"}

    @staticmethod
    def _template_topic_fit_is_weak(chosen_template: dict[str, Any] | None) -> bool:
        if not chosen_template:
            return False
        breakdown = chosen_template.get("score_breakdown") or {}
        if "keyword_overlap" not in breakdown and "ocr_text_fit" not in breakdown:
            return False
        keyword_overlap = float(breakdown.get("keyword_overlap", 0.0) or 0.0)
        ocr_text_fit = float(breakdown.get("ocr_text_fit", 0.0) or 0.0)
        return (keyword_overlap + ocr_text_fit) < 2.5

    @staticmethod
    def _template_format_compatible(recommendation: dict[str, Any], format_name: str) -> bool:
        """Check if template supports requested format."""
        template_metadata = recommendation.get("metadata", {})
        template_format = str(template_metadata.get("format", "")).strip().lower()
        template_tags = template_metadata.get("tags", [])
        if not isinstance(template_tags, list):
            template_tags = []

        if format_name in ("carousel", "instagram_carousel", "linkedin_carousel"):
            match_type = str(recommendation.get("match_type") or "").strip().lower()
            adaptation_plan = recommendation.get("adaptation_plan", {})
            if not isinstance(adaptation_plan, dict):
                adaptation_plan = {}
            sequence_pack = template_metadata.get("sequence_pack")
            reference_zone_map = template_metadata.get("reference_zone_map")
            zone_roles = template_metadata.get("zone_roles", [])
            if not isinstance(zone_roles, list):
                zone_roles = []
            # Carousel needs multi-frame or slide-capable templates
            return (
                "carousel" in template_format
                or "multi-frame" in template_format
                or "multi_frame" in template_format
                or "carousel" in template_tags
                or "slides" in template_tags
                or recommendation.get("sequence_length", 1) > 1
                or (
                    match_type == "adapted_template"
                    and bool(
                        adaptation_plan.get("multi_section_flow")
                        or adaptation_plan.get("prefer_distinct_sections")
                    )
                )
                or (
                    isinstance(sequence_pack, dict)
                    and len(sequence_pack.get("slides") or []) > 1
                )
                or (
                    isinstance(reference_zone_map, dict)
                    and len(reference_zone_map.get("zones") or []) >= 3
                )
                or len(zone_roles) >= 3
            )

        # Single-frame formats accept any template
        return True

    def decide(
        self,
        *,
        prompt: str,
        studio_panel: dict[str, Any],
        brand_context: dict[str, Any],
        persona_context: dict[str, Any],
        objective_context: dict[str, Any],
        template_recommendations: list[dict[str, Any]],
        selected_template_id: str | None = None,
        selected_template_name: str | None = None,
        reference_assets: list[dict[str, Any]] | None = None,
    ) -> LayoutDecision:
        recommendations = template_recommendations or []

        # Filter templates by format compatibility for carousel requests
        format_name = studio_panel.get("format", "").strip().lower()
        if format_name in ("carousel", "instagram_carousel", "linkedin_carousel"):
            filtered_recs = [
                rec for rec in recommendations
                if self._template_format_compatible(rec, format_name)
            ]
            if filtered_recs:
                logger.info(f"Filtered {len(recommendations) - len(filtered_recs)} carousel-incompatible templates")
                recommendations = filtered_recs
            else:
                logger.warning(f"No carousel-compatible templates found in {len(recommendations)} recommendations, proceeding with all templates")

        top = recommendations[0] if recommendations else None
        chosen_template = None
        if selected_template_id:
            chosen_template = next(
                (
                    item
                    for item in recommendations
                    if str(item.get("template_id")) == str(selected_template_id)
                ),
                {
                    "template_id": selected_template_id,
                    "name": selected_template_name or "Selected template",
                    "score": 10.0,
                    "metadata": {},
                    "score_breakdown": {},
                    "adaptation_plan": {},
                },
            )
        elif top:
            chosen_template = top

        decision = self._mode_for_template(
            prompt=prompt,
            studio_panel=studio_panel,
            brand_context=brand_context,
            persona_context=persona_context,
            objective_context=objective_context,
            chosen_template=chosen_template,
            reference_assets=reference_assets or [],
            explicit_template=bool(selected_template_id),
        )
        return decision

    def _mode_for_template(
        self,
        *,
        prompt: str,
        studio_panel: dict[str, Any],
        brand_context: dict[str, Any],
        persona_context: dict[str, Any],
        objective_context: dict[str, Any],
        chosen_template: dict[str, Any] | None,
        reference_assets: list[dict[str, Any]],
        explicit_template: bool,
    ) -> LayoutDecision:
        prompt_length = len(prompt.strip())
        platform = studio_panel.get("platform_preset", "")
        format_name = studio_panel.get("format", "")
        visual_identity = brand_context.get("visual_identity", {}) or {}
        validation = brand_context.get("validation", {}) or {}
        palette_entries = visual_identity.get("palette_entries", []) or []
        typography = visual_identity.get("typography", {}) or {}
        template_score = float(chosen_template.get("score", 0.0)) if chosen_template else 0.0
        chosen_template_review_flags = {
            str(flag).strip().lower()
            for flag in (chosen_template.get("review_flags") or [])
            if str(flag).strip()
        } if isinstance(chosen_template, dict) else set()
        chosen_template_metadata = (
            chosen_template.get("metadata")
            if isinstance(chosen_template, dict) and isinstance(chosen_template.get("metadata"), dict)
            else {}
        )
        chosen_template_review_flags.update(
            str(flag).strip().lower()
            for flag in (chosen_template_metadata.get("review_flags") or [])
            if str(flag).strip()
        )
        relevant_validation_warning_count = (
            float(len(validation.get("warnings", [])))
            if (not chosen_template or "brand_validation_conflicts_present" in chosen_template_review_flags)
            else 0.0
        )
        score_breakdown = {
            "template_score": template_score,
            "reference_asset_count": float(len(reference_assets)),
            "validation_warning_count": relevant_validation_warning_count,
            "palette_depth": float(len(palette_entries)),
            "typography_depth": float(len(typography.get("font_families", []))),
        }

        adaptation_plan = dict((chosen_template or {}).get("adaptation_plan") or {})
        if prompt_length > 120:
            adaptation_plan["expand_headline_or_body"] = True
        if format_name in {"carousel", "infographic", "pdf", "doc"}:
            adaptation_plan["multi_section_flow"] = True
            adaptation_plan["prefer_distinct_sections"] = True
        if platform in {"instagram", "x"}:
            adaptation_plan["compact_cta"] = True
        if reference_assets:
            adaptation_plan["use_reference_assets"] = True
        adaptation_plan["fit_validation_required"] = True

        review_flags = []
        if validation.get("conflict_count", 0) and (
            not chosen_template or "brand_validation_conflicts_present" in chosen_template_review_flags
        ):
            review_flags.append("brand_validation_conflicts_present")
        if len(validation.get("warnings", [])) >= 3:
            review_flags.append("high_warning_volume")

        visual_social_request = self._is_visual_social_request(studio_panel)
        weak_topic_fit = self._template_topic_fit_is_weak(chosen_template)

        mode = "synthesized_layout"
        rationale = [
            "No sufficiently strong template match was found, so the renderer will compose a fresh layout from brand rules."
        ]
        if chosen_template:
            recommended_match_type = str(chosen_template.get("match_type") or "").strip().lower()
            breakdown = chosen_template.get("score_breakdown") or {}
            metadata = chosen_template.get("metadata") or {}
            keyword_overlap = float(breakdown.get("keyword_overlap", 0.0) or 0.0)
            platform_fit = float(breakdown.get("platform_fit", 0.0) or 0.0)
            brand_alignment = float(breakdown.get("brand_alignment", 0.0) or 0.0)
            export_fit = float(breakdown.get("export_fit", 0.0) or 0.0)
            overlay_safe = bool(metadata.get("overlay_safe", True))
            if not overlay_safe:
                mode = "synthesized_layout"
                review_flags.append("template_text_overlay_risk")
                adaptation_plan["reference_style_only"] = True
                rationale = [
                    f"Template '{chosen_template.get('name', 'Template')}' contains baked-in text and will be used as a style reference instead of a render surface."
                ]
            elif visual_social_request and weak_topic_fit and not explicit_template:
                mode = "synthesized_layout"
                review_flags.append("template_topic_mismatch")
                adaptation_plan["reference_style_only"] = True
                adaptation_plan["topic_fit_too_weak"] = True
                rationale = [
                    f"Template '{chosen_template.get('name', 'Template')}' is visually usable, but its topic fit is too weak for this social post, so the renderer will synthesize a new brand-led layout."
                ]
            elif explicit_template:
                if adaptation_plan:
                    mode = "adapted_template"
                    rationale = [
                        f"User-selected template '{chosen_template.get('name', 'Template')}' will be adapted to fit prompt and platform needs."
                    ]
                else:
                    mode = "exact_template"
                    rationale = [
                        f"User-selected template '{chosen_template.get('name', 'Template')}' will be reused directly."
                    ]
            elif recommended_match_type == "reference_only":
                if (
                    template_score >= 7.5
                    and keyword_overlap >= 3.0
                    and platform_fit >= 3.0
                    and (brand_alignment >= 1.0 or export_fit >= 1.0)
                ):
                    mode = "adapted_template"
                    rationale = [
                        f"Template '{chosen_template.get('name', 'Template')}' is visually relevant and will be adapted instead of discarded."
                    ]
                else:
                    mode = "synthesized_layout"
                    rationale = [
                        f"Template '{chosen_template.get('name', 'Template')}' is useful as inspiration, but the renderer will synthesize a new layout for a stronger fit."
                    ]
            elif recommended_match_type == "exact_template":
                mode = "exact_template"
                rationale = [
                    f"Template '{chosen_template.get('name', 'Template')}' is a strong direct match for the prompt, platform, and brand context."
                ]
            elif recommended_match_type == "adapted_template":
                mode = "adapted_template"
                rationale = [
                    f"Template '{chosen_template.get('name', 'Template')}' is relevant, but it needs layout adaptation for this request."
                ]
            elif template_score >= 11.0 and not adaptation_plan:
                mode = "exact_template"
                rationale = [
                    f"Template '{chosen_template.get('name', 'Template')}' is a strong direct match for the prompt, platform, and brand context."
                ]
            elif template_score >= 6.0:
                mode = "adapted_template"
                rationale = [
                    f"Template '{chosen_template.get('name', 'Template')}' is relevant, but it needs layout adaptation for this request."
                ]

        brand_rule_hints = {
            "palette_roles": visual_identity.get("brand_color_palette", {}) or {},
            "font_families": [family.get("name") for family in typography.get("font_families", []) if family.get("name")],
            "logo_required": self._identity_has_logo(brand_context),
            "word_bank_strength": len((brand_context.get("guardrails", {}) or {}).get("positive_word_bank", []))
            + len((brand_context.get("guardrails", {}) or {}).get("negative_word_bank", [])),
        }
        asset_strategy = {
            "use_template_background": mode in {"exact_template", "adapted_template"} and "template_text_overlay_risk" not in review_flags,
            "use_generated_image": studio_panel.get("file_type") != "doc",
            "use_brand_reference_assets": bool(reference_assets),
            "prefer_brand_logo": brand_rule_hints["logo_required"],
            "audience_alignment_available": bool(brand_context.get("audience_insights")),
            "persona_alignment_available": bool(persona_context),
            "objective_alignment_available": bool(objective_context),
        }
        return LayoutDecision(
            mode=mode,
            template_id=(
                None
                if "template_text_overlay_risk" in review_flags or "template_topic_mismatch" in review_flags
                else (str(chosen_template.get("template_id")) if chosen_template and chosen_template.get("template_id") else None)
            ),
            template_name=chosen_template.get("name") if chosen_template else None,
            rationale=rationale,
            score_breakdown=score_breakdown,
            adaptation_plan=adaptation_plan,
            brand_rule_hints=brand_rule_hints,
            asset_strategy=asset_strategy,
            review_flags=review_flags,
        )
