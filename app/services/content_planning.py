from __future__ import annotations

from typing import Any

from app.services.format_family_planning import FormatFamilyPlanningService
from app.services.research_editorial_planning import ResearchEditorialPlanningService


class ContentPlanningService:
    def __init__(self) -> None:
        self.research_editorial = ResearchEditorialPlanningService()
        self.format_family_planning = FormatFamilyPlanningService()

    @staticmethod
    def _normalized_text_list(value: Any, *, limit: int = 8) -> list[str]:
        if not isinstance(value, list):
            return []
        items: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if not text or text in items:
                continue
            items.append(text)
            if len(items) >= limit:
                break
        return items

    @classmethod
    def _normalized_outline(cls, value: Any, *, limit: int = 8) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        outline: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                title = str(item.get("title") or item.get("headline") or item.get("label") or "").strip()
                description = str(item.get("description") or item.get("summary") or "").strip()
                if title or description:
                    outline.append(
                        {
                            "title": title,
                            "description": description,
                            "role": str(item.get("role") or item.get("slide_role") or item.get("purpose") or "").strip(),
                        }
                    )
            else:
                text = str(item or "").strip()
                if text:
                    outline.append({"title": text, "description": "", "role": ""})
            if len(outline) >= limit:
                break
        return outline

    @staticmethod
    def _tokenize_text_fragments(*values: Any) -> set[str]:
        tokens: set[str] = set()
        for value in values:
            if isinstance(value, list):
                for item in value:
                    tokens.update(ContentPlanningService._tokenize_text_fragments(item))
                continue
            if isinstance(value, dict):
                for item in value.values():
                    tokens.update(ContentPlanningService._tokenize_text_fragments(item))
                continue
            text = str(value or "").strip().casefold()
            if not text:
                continue
            tokens.update(part for part in text.replace("/", " ").replace("-", " ").split() if part)
        return tokens

    @classmethod
    def _infer_carousel_archetype(
        cls,
        *,
        deliverable_type: str | None,
        format_plan: dict[str, Any],
        research_brief: dict[str, Any],
        outline: list[dict[str, Any]],
        content_structure: list[str],
        required_components: list[str],
        notes: list[str],
    ) -> str:
        ordered_story_beats = cls._normalized_text_list(research_brief.get("ordered_story_beats"), limit=8)
        if ordered_story_beats or str(research_brief.get("narrative_contract") or "").strip().casefold() == "preserve_user_order":
            return "ordered_story"
        outline_roles = {
            str(item.get("role") or "").strip().casefold().replace(" ", "_")
            for item in outline
            if isinstance(item, dict)
        }
        explicit_roles = {role for role in outline_roles if role}
        if explicit_roles & {"undercovered_angle", "missed_angle", "strategic_meaning", "what_happened", "deal_structure"}:
            return "editorial_reveal"
        if explicit_roles & {"problem_frame", "solution_intro", "feature_cluster", "value_close"}:
            return "problem_solution_feature"
        if explicit_roles & {"comparison_item"}:
            return "comparison_framework"
        if explicit_roles & {"list_item"}:
            return "list_teaching"

        tokens = cls._tokenize_text_fragments(
            deliverable_type,
            format_plan,
            research_brief,
            outline,
            content_structure,
            required_components,
            notes,
        )
        text_blob = " ".join(sorted(tokens))

        if any(
            keyword in text_blob
            for keyword in (
                "bias",
                "biases",
                "mistake",
                "mistakes",
                "myth",
                "myths",
                "habit",
                "habits",
                "pitfall",
                "pitfalls",
                "behavioural",
                "behavioral",
            )
        ):
            return "list_teaching"
        if any(
            keyword in text_blob
            for keyword in (
                "versus",
                "compare",
                "comparison",
                "barbell",
                "bullet",
                "ladder",
                "option",
                "options",
                "strategy",
                "strategies",
            )
        ):
            return "comparison_framework"
        if any(
            keyword in text_blob
            for keyword in (
                "analyzer",
                "tool",
                "dashboard",
                "feature",
                "features",
                "workflow",
                "solution",
                "problem",
                "platform",
                "decision",
            )
        ):
            return "problem_solution_feature"
        if any(
            keyword in text_blob
            for keyword in (
                "coverage",
                "headline",
                "undercovered",
                "strategic",
                "deal",
                "implication",
                "trade",
                "missed",
                "overlooked",
            )
        ):
            return "editorial_reveal"
        return "progressive_explainer"

    @staticmethod
    def _carousel_slide_grammar(archetype: str) -> list[dict[str, str]]:
        normalized = str(archetype or "").strip().casefold()
        if normalized == "editorial_reveal":
            return [
                {"role": "hook", "job": "Open with the undercovered or surprising angle only."},
                {"role": "structure", "job": "Explain what actually changed with the concrete factual mechanics."},
                {"role": "undercovered_angle", "job": "Surface the clause, condition, asymmetry, or point most coverage missed."},
                {"role": "strategic_meaning", "job": "Explain why the development matters beyond the surface headline."},
                {"role": "takeaway", "job": "Close with the implication or what to watch next."},
            ]
        if normalized == "ordered_story":
            return [
                {"role": "hook", "job": "Follow the user-requested opening beat exactly."},
                {"role": "detail", "job": "Let each interior slide follow the next requested beat in order without merging beats."},
                {"role": "takeaway", "job": "Close with the user-requested final beat only."},
            ]
        if normalized == "list_teaching":
            return [
                {"role": "hook", "job": "Set up the topic and promise a useful teaching sequence."},
                {"role": "list_item", "job": "Teach one item per slide using concept, explanation, example, and consequence."},
                {"role": "takeaway", "job": "Close with the summary lesson or engagement CTA."},
            ]
        if normalized == "comparison_framework":
            return [
                {"role": "hook", "job": "Frame the comparison and the decision the reader is making."},
                {"role": "comparison_item", "job": "Cover one option per slide using what it is, how it works, and where it fits."},
                {"role": "takeaway", "job": "Close with the comparison takeaway or decision lens."},
            ]
        if normalized == "problem_solution_feature":
            return [
                {"role": "problem_frame", "job": "Define the pain point or problem clearly first."},
                {"role": "solution_intro", "job": "Introduce the solution and how it responds to the problem."},
                {"role": "feature_cluster", "job": "Explain one capability cluster or practical workflow at a time."},
                {"role": "value_close", "job": "Close on the practical value, decision payoff, or next step."},
            ]
        return [
            {"role": "hook", "job": "Open with a strong setup slide."},
            {"role": "detail", "job": "Let each interior slide carry one distinct idea."},
            {"role": "takeaway", "job": "Close the sequence cleanly."},
        ]

    @classmethod
    def _carousel_archetype_rules(cls, archetype: str) -> list[str]:
        normalized = str(archetype or "").strip().casefold()
        if normalized == "editorial_reveal":
            return [
                "Do not mix hook, factual unpacking, missed angle, and implication on the same slide.",
                "Keep the missed-angle slide distinct from the factual breakdown slide.",
                "Close on implication or what to watch next before using a CTA tone.",
            ]
        if normalized == "ordered_story":
            return [
                "Preserve the user-requested beat order exactly instead of substituting a stock carousel grammar.",
                "Dedicate one core story beat per slide and do not merge adjacent beats into one summary slide.",
                "Keep the close slide faithful to the user-requested ending rather than converting it into a generic CTA page.",
            ]
        if normalized == "list_teaching":
            return [
                "Use one concept per interior slide with the same repeated micro-structure.",
                "Do not merge multiple list items into one crowded educational page.",
                "Keep the setup slide separate from the repeated teaching slides.",
            ]
        if normalized == "comparison_framework":
            return [
                "Use one option or strategy per interior slide.",
                "Repeat the same comparison structure across the option slides.",
                "Reserve the final slide for the conclusion or decision lens.",
            ]
        if normalized == "problem_solution_feature":
            return [
                "Explain the problem before introducing the solution.",
                "Keep feature slides focused on one capability cluster at a time.",
                "Close on practical value instead of generic hype.",
            ]
        return []

    @classmethod
    def derive_content_plan(
        cls,
        *,
        deliverable_type: str | None,
        format_family_plan: dict[str, Any] | None,
        research_editorial_brief: dict[str, Any] | None,
        planning_family: str = "text",
    ) -> dict[str, Any]:
        format_plan = format_family_plan if isinstance(format_family_plan, dict) else {}
        research_brief = research_editorial_brief if isinstance(research_editorial_brief, dict) else {}
        format_family = str(format_plan.get("family") or "").strip() or "short_form"
        metadata_fields = cls._normalized_text_list(format_plan.get("metadata_fields"), limit=12)
        content_structure = cls._normalized_text_list(format_plan.get("content_structure"), limit=8)
        required_components = cls._normalized_text_list(format_plan.get("required_components"), limit=10)
        optional_components = cls._normalized_text_list(format_plan.get("optional_components"), limit=12)
        planning_rules = cls._normalized_text_list(format_plan.get("planning_rules"), limit=10)
        notes = cls._normalized_text_list(format_plan.get("notes"), limit=8)
        outline = cls._normalized_outline(research_brief.get("outline"))
        ordered_story_beats = cls._normalized_text_list(research_brief.get("ordered_story_beats"), limit=8)
        sample_editorial_brief = research_brief.get("sample_editorial_brief") if isinstance(research_brief.get("sample_editorial_brief"), dict) else {}
        sample_story_roles = cls._normalized_text_list(sample_editorial_brief.get("story_roles"), limit=8)
        sample_headline_patterns = cls._normalized_text_list(sample_editorial_brief.get("headline_patterns"), limit=6)
        sample_summaries = cls._normalized_text_list(sample_editorial_brief.get("sample_summaries"), limit=6)
        sample_explanation_styles = cls._normalized_text_list(sample_editorial_brief.get("explanation_styles"), limit=4)
        sample_copy_densities = cls._normalized_text_list(sample_editorial_brief.get("copy_densities"), limit=4)
        sample_closing_styles = cls._normalized_text_list(sample_editorial_brief.get("closing_styles"), limit=4)
        preferred_slide_count = int(
            research_brief.get("preferred_slide_count")
            or format_plan.get("preferred_slide_count")
            or 0
        ) or None
        carousel_archetype = ""
        carousel_slide_grammar: list[dict[str, str]] = []
        carousel_archetype_rules: list[str] = []

        if format_family == "carousel":
            sequence_contract = "native_carousel_metadata"
            sequence_expectation = "slide_by_slide_progression"
            native_metadata_fields = [
                "carousel_slide_specs",
                "supporting_line",
                "proof_points",
                "stat_highlights",
            ]
            carousel_archetype = cls._infer_carousel_archetype(
                deliverable_type=deliverable_type,
                format_plan=format_plan,
                research_brief=research_brief,
                outline=outline,
                content_structure=content_structure,
                required_components=required_components,
                notes=notes,
            )
            if ordered_story_beats and carousel_archetype == "ordered_story":
                sequence_contract = "user_ordered_story_beats"
            carousel_slide_grammar = cls._carousel_slide_grammar(carousel_archetype)
            carousel_archetype_rules = cls._carousel_archetype_rules(carousel_archetype)
        elif format_family == "infographic":
            sequence_contract = "native_infographic_sections"
            sequence_expectation = "section_by_section_progression"
            native_metadata_fields = [
                "infographic_section_specs",
                "section_label",
                "supporting_line",
                "proof_points",
                "stat_highlights",
                "claim_evidence_pairs",
            ]
            if sample_story_roles and str(research_brief.get("narrative_contract") or "").strip().casefold() == "follow_sample_infographic_flow":
                sequence_contract = "sample_infographic_section_flow"
                sequence_expectation = "sample_guided_section_progression"
        elif format_family == "static":
            sequence_contract = "native_static_panel_spec"
            sequence_expectation = "single_dominant_idea"
            native_metadata_fields = ["static_panel_spec", "supporting_line", "proof_points", "trust_builders", "stat_highlights"]
            if str(research_brief.get("narrative_contract") or "").strip().casefold() == "follow_sample_static_hierarchy":
                sequence_contract = "sample_static_panel_hierarchy"
                sequence_expectation = "sample_guided_single_surface_hierarchy"
        else:
            sequence_contract = "structured_editorial_progression"
            sequence_expectation = "ordered_message_flow"
            native_metadata_fields = metadata_fields[:6]

        for field in metadata_fields:
            if field not in native_metadata_fields:
                native_metadata_fields.append(field)

        return {
            "planning_family": planning_family,
            "deliverable_type": str(deliverable_type or "").strip() or "general_copy",
            "format_family": format_family,
            "primary_unit": str(format_plan.get("primary_unit") or "").strip() or "draft",
            "body_shape": str(format_plan.get("body_shape") or "").strip() or "freeform",
            "outline_mode": str(format_plan.get("outline_mode") or "").strip() or "flexible",
            "density_target": str(format_plan.get("density_target") or "").strip() or "medium",
            "content_structure": content_structure,
            "required_components": required_components,
            "optional_components": optional_components,
            "metadata_fields": metadata_fields,
            "planning_rules": planning_rules,
            "preferred_slide_count": preferred_slide_count,
            "notes": notes,
            "sequence_contract": sequence_contract,
            "sequence_expectation": sequence_expectation,
            "native_metadata_fields": native_metadata_fields[:8],
            "research_mode": str(research_brief.get("mode") or "").strip() or "standard",
            "slides": outline if format_family == "carousel" else [],
            "story_outline": outline,
            "ordered_story_beats": ordered_story_beats,
            "carousel_archetype": carousel_archetype,
            "carousel_slide_grammar": carousel_slide_grammar,
            "carousel_archetype_rules": carousel_archetype_rules,
            "sample_editorial_source": str(sample_editorial_brief.get("source") or "").strip(),
            "sample_story_roles": sample_story_roles,
            "sample_headline_patterns": sample_headline_patterns,
            "sample_summaries": sample_summaries,
            "sample_explanation_styles": sample_explanation_styles,
            "sample_copy_densities": sample_copy_densities,
            "sample_closing_styles": sample_closing_styles,
            "disclaimer_requested": bool(research_brief.get("disclaimer_requested")),
            "disclaimer_placement": str(research_brief.get("disclaimer_placement") or "").strip(),
        }

    def build_text_plan(
        self,
        *,
        prompt: str,
        studio_panel: dict[str, Any] | None,
        brand_context: dict[str, Any] | None,
        persona_context: dict[str, Any] | None,
        objective_context: dict[str, Any] | None,
        knowledge_brief: list[dict[str, Any]] | None,
        live_research: dict[str, Any] | None,
        content_format_guide: dict[str, Any] | None = None,
        deliverable_type: str | None,
    ) -> dict[str, Any]:
        research_editorial_brief = self.research_editorial.build(
            prompt=prompt,
            studio_panel=studio_panel,
            brand_context=brand_context,
            persona_context=persona_context,
            objective_context=objective_context,
            knowledge_brief=knowledge_brief,
            live_research=live_research,
            content_format_guide=content_format_guide,
            deliverable_type=deliverable_type,
        )
        format_family_plan = self.format_family_planning.build(
            studio_panel=studio_panel,
            deliverable_type=deliverable_type,
            research_editorial_brief=research_editorial_brief,
        )
        return {
            "research_editorial_brief": research_editorial_brief,
            "format_family_plan": format_family_plan,
            "content_plan": self.derive_content_plan(
                deliverable_type=deliverable_type,
                format_family_plan=format_family_plan,
                research_editorial_brief=research_editorial_brief,
                planning_family="text",
            ),
        }
