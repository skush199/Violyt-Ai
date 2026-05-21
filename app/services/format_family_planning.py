from __future__ import annotations

from typing import Any


class FormatFamilyPlanningService:
    FAMILY_CONTRACTS: dict[str, dict[str, Any]] = {
        "long_form": {
            "primary_unit": "section",
            "body_shape": "multi_section_editorial",
            "outline_mode": "sectioned",
            "content_structure": [
                "title_or_heading",
                "introduction",
                "section_progression",
                "evidence_or_examples",
                "closing_takeaway",
            ],
            "required_components": ["headline", "body"],
            "optional_components": ["cta", "seo_keywords", "outline", "sources_used"],
            "copy_density": "developed",
            "visual_density": "not_applicable",
            "metadata_fields": ["outline", "seo_keywords", "sources_used"],
            "planning_rules": [
                "Write in sections with visible progression instead of one collapsed block.",
                "Favor developed analysis, transitions, and evidence over slogan-style brevity.",
                "Use headings or natural section shifts when the deliverable supports them.",
            ],
        },
        "short_form": {
            "primary_unit": "paragraph",
            "body_shape": "compact_native_post",
            "outline_mode": "linear",
            "content_structure": [
                "hook",
                "analysis_or_explanation",
                "closing_takeaway",
            ],
            "required_components": ["body"],
            "optional_components": ["headline", "cta", "hashtags", "key_takeaway", "sources_used"],
            "copy_density": "compact",
            "visual_density": "not_applicable",
            "metadata_fields": ["hook_type", "key_takeaway", "sources_used"],
            "planning_rules": [
                "Keep the thought progression tight, but still distinct.",
                "Do not over-expand into blog structure or under-expand into one generic sentence.",
                "Use platform-native rhythm such as short paragraphs or compact post beats.",
            ],
        },
        "static": {
            "primary_unit": "panel",
            "body_shape": "single_canvas_message",
            "outline_mode": "single_frame",
            "content_structure": [
                "headline",
                "supporting_line_or_body",
                "proof_cues",
                "cta",
            ],
            "required_components": ["headline", "body", "cta"],
            "optional_components": ["proof_points", "stat_highlights", "visual_direction", "image_prompt"],
            "copy_density": "minimal_to_moderate",
            "visual_density": "single_focus",
            "metadata_fields": ["supporting_line", "proof_points", "stat_highlights", "visual_direction", "design_style", "image_prompt"],
            "planning_rules": [
                "Design around one dominant message on one canvas.",
                "Keep text hierarchy sparse and readable instead of distributing the story across many parts.",
                "Push extra explanation into proof cues rather than turning the panel into a paragraph block.",
            ],
        },
        "carousel": {
            "primary_unit": "slide",
            "body_shape": "multi_slide_sequence",
            "outline_mode": "sequenced",
            "content_structure": [
                "cover",
                "progressive_detail_slides",
                "closing_takeaway_or_cta",
            ],
            "required_components": ["headline", "body", "cta", "carousel_slide_specs"],
            "optional_components": ["proof_points", "stat_highlights", "supporting_line", "claim_evidence_pairs"],
            "copy_density": "distributed",
            "visual_density": "multi_panel_story",
            "metadata_fields": ["carousel_slide_specs", "supporting_line", "proof_points", "stat_highlights", "visual_direction", "design_style", "image_prompt"],
            "planning_rules": [
                "Plan a real slide sequence, not one poster split into pages.",
                "Each slide should add a new beat in the story or explanation.",
                "Reserve the cover and closing for distinct jobs rather than repeating the middle slides.",
            ],
        },
        "infographic": {
            "primary_unit": "section",
            "body_shape": "sectioned_visual_explainer",
            "outline_mode": "sectioned_visual",
            "content_structure": [
                "headline",
                "context_block",
                "key_numbers_or_facts",
                "process_or_structure",
                "implications_or_takeaway",
            ],
            "required_components": ["headline", "body", "cta"],
            "optional_components": ["proof_points", "stat_highlights", "claim_evidence_pairs", "visual_direction", "image_prompt"],
            "copy_density": "structured",
            "visual_density": "stacked_sections",
            "metadata_fields": ["supporting_line", "proof_points", "stat_highlights", "claim_evidence_pairs", "visual_direction", "design_style", "image_prompt"],
            "planning_rules": [
                "Break information into stacked explanatory sections rather than a poster headline plus filler.",
                "Use fact groupings, numeric callouts, and implication blocks.",
                "Keep each section visually scannable while preserving analytical completeness.",
            ],
        },
    }

    LONG_FORM_DELIVERABLES = {"blog", "newsletter", "script", "document", "article"}
    SHORT_FORM_DELIVERABLES = {
        "linkedin_post",
        "instagram_caption",
        "x_post",
        "x_thread",
        "youtube_description",
        "email",
        "social_caption",
        "general_copy",
    }

    def build(
        self,
        *,
        studio_panel: dict[str, Any] | None,
        deliverable_type: str | None = None,
        content_format_brief: dict[str, Any] | None = None,
        research_editorial_brief: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        studio_panel = studio_panel if isinstance(studio_panel, dict) else {}
        content_format_brief = content_format_brief if isinstance(content_format_brief, dict) else {}
        research_editorial_brief = research_editorial_brief if isinstance(research_editorial_brief, dict) else {}
        format_name = self._normalize_text(studio_panel.get("format"), limit=32).casefold()
        platform_preset = self._normalize_text(studio_panel.get("platform_preset"), limit=32).casefold()
        normalized_deliverable = self._normalize_text(deliverable_type, limit=32).casefold()
        family = self._family_for(format_name=format_name, deliverable_type=normalized_deliverable)
        contract = dict(self.FAMILY_CONTRACTS.get(family, self.FAMILY_CONTRACTS["short_form"]))
        preferred_slide_count = self._preferred_slide_count(
            family=family,
            studio_panel=studio_panel,
            content_format_brief=content_format_brief,
            research_editorial_brief=research_editorial_brief,
        )
        notes = self._planning_notes(
            family=family,
            deliverable_type=normalized_deliverable,
            platform_preset=platform_preset,
            content_format_brief=content_format_brief,
            research_editorial_brief=research_editorial_brief,
        )
        return {
            "family": family,
            "deliverable_type": normalized_deliverable,
            "format": format_name,
            "platform_preset": platform_preset,
            "primary_unit": contract.get("primary_unit"),
            "body_shape": contract.get("body_shape"),
            "outline_mode": contract.get("outline_mode"),
            "content_structure": list(contract.get("content_structure") or []),
            "required_components": list(contract.get("required_components") or []),
            "optional_components": list(contract.get("optional_components") or []),
            "copy_density": contract.get("copy_density"),
            "visual_density": contract.get("visual_density"),
            "metadata_fields": list(contract.get("metadata_fields") or []),
            "planning_rules": list(contract.get("planning_rules") or []),
            "preferred_slide_count": preferred_slide_count,
            "notes": notes,
        }

    @classmethod
    def _family_for(cls, *, format_name: str, deliverable_type: str) -> str:
        if format_name == "carousel":
            return "carousel"
        if format_name == "infographic":
            return "infographic"
        if format_name in {"static", "story", "poster"}:
            return "static"
        if deliverable_type in cls.LONG_FORM_DELIVERABLES:
            return "long_form"
        return "short_form"

    @staticmethod
    def _normalize_text(value: Any, limit: int | None = None) -> str:
        text = " ".join(str(value or "").split()).strip()
        if not text or limit is None:
            return text
        return text[:limit].rstrip(" ,.;:-")

    @classmethod
    def _preferred_slide_count(
        cls,
        *,
        family: str,
        studio_panel: dict[str, Any],
        content_format_brief: dict[str, Any],
        research_editorial_brief: dict[str, Any],
    ) -> int | None:
        if family not in {"carousel", "infographic"}:
            return None
        for source in (
            research_editorial_brief.get("preferred_slide_count"),
            content_format_brief.get("preferred_slide_count"),
        ):
            try:
                value = int(source or 0)
            except (TypeError, ValueError):
                value = 0
            if value > 0:
                return value
        return 5 if family == "carousel" else 4

    @staticmethod
    def _planning_notes(
        *,
        family: str,
        deliverable_type: str,
        platform_preset: str,
        content_format_brief: dict[str, Any],
        research_editorial_brief: dict[str, Any],
    ) -> list[str]:
        notes: list[str] = []
        if family == "long_form":
            notes.append("Use visible section progression and developed reasoning.")
        elif family == "short_form":
            notes.append("Keep the structure tight and platform-native without collapsing into generic brevity.")
        elif family == "static":
            notes.append("Plan one dominant canvas message with supporting proof cues.")
        elif family == "carousel":
            notes.append("Plan a true slide-by-slide sequence with distinct beats.")
        elif family == "infographic":
            notes.append("Plan stacked explanatory sections with facts, structure, and implications.")
        if platform_preset:
            notes.append(f"Match the copy rhythm and scannability to {platform_preset}.")
        if content_format_brief.get("summary"):
            notes.append(str(content_format_brief.get("summary")))
        if research_editorial_brief.get("active"):
            notes.append("Preserve the research-editorial thesis and outline inside the family structure.")
        if deliverable_type:
            notes.append(f"Optimize specifically for the {deliverable_type} deliverable.")
        return notes[:6]
