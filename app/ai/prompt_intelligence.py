from __future__ import annotations

import json
import re
from typing import Any

from app.ai.context_compiler import ContextCompilerService
from app.ai.providers.llm import PromptEnvelope


class PromptIntelligenceService:
    MISTAKE_CAROUSEL_SIGNAL_PATTERN = re.compile(
        r"\b(mistake|mistakes|pitfall|pitfalls|error|errors|wrong|misstep|missteps|avoid|avoiding|costly)\b",
        re.IGNORECASE,
    )
    PLATFORM_GUIDANCE = {
        "linkedin": (
            "Use professional, insight-led copy. Lead with business value, credibility, and investor confidence. "
            "Prefer restrained hashtags and clear benefit statements over hype."
        ),
        "instagram": (
            "Use visually expressive copy with strong emotional clarity. Keep on-canvas text compact, elegant, "
            "and easy to scan. Favor short supporting lines over dense paragraphs."
        ),
        "x": (
            "Keep the copy tight, punchy, and highly concise. Avoid unnecessary hashtags, long paragraphs, and "
            "generic corporate filler."
        ),
        "youtube_thumbnail": (
            "Prioritize a very short, high-impact headline with thumbnail-safe wording. Avoid dense body text and "
            "choose curiosity or outcome-driven phrasing."
        ),
    }
    FORMAT_GUIDANCE = {
        "static": "Design the copy for a single polished social creative with concise on-canvas text.",
        "carousel": "Design the copy so it can break across multiple slides with clear sectioning and compact cards.",
        "infographic": (
            "Design the copy for a tall visual explainer. Provide structured proof points, short stat-like callouts, "
            "and a compact supporting line that can be rendered as sections."
        ),
        "pdf": "Provide structured, readable copy with clean sectioning that can scale beyond a single social post.",
        "doc": "Provide text that reads well in document form, with clarity and completeness over punchiness.",
    }

    @classmethod
    def _format_visual_structure_summary(cls, detailed_context: dict[str, Any]) -> str:
        """🔥 PHASE 4: Format detailed visual context for LLM prompt"""
        if not detailed_context:
            return ""

        parts = []

        # Layout structures
        layout_structures = detailed_context.get("layout_structures", [])
        if layout_structures:
            for struct in layout_structures:
                elements = []
                if struct.get("numbered_elements_count"):
                    elements.append(f"{struct['numbered_elements_count']} numbered sections")
                if struct.get("icon_text_pairs_count"):
                    elements.append(f"{struct['icon_text_pairs_count']} icon-text pairs")
                if struct.get("hierarchy_detected"):
                    elements.append("hierarchical structure")
                if struct.get("spatial_groups_count"):
                    elements.append(f"{struct['spatial_groups_count']} content groups")
                if elements:
                    parts.append(f"Layout: {', '.join(elements)}")

        # Component patterns
        component_patterns = detailed_context.get("component_patterns", [])
        if component_patterns:
            all_patterns = []
            for cp in component_patterns:
                all_patterns.extend(cp.get("patterns", []))
            if all_patterns:
                parts.append(f"Patterns: {', '.join(set(all_patterns))}")

        # Visual hierarchy
        visual_hierarchies = detailed_context.get("visual_hierarchies", [])
        if visual_hierarchies:
            hierarchy = visual_hierarchies[0]  # Use first
            if hierarchy.get("focal_role"):
                parts.append(f"Focus: {hierarchy['focal_role']}")
            if hierarchy.get("reading_order"):
                reading_order = hierarchy["reading_order"]
                if isinstance(reading_order, list) and reading_order:
                    parts.append(f"Order: {' → '.join(str(r) for r in reading_order[:3])}")

        return " | ".join(parts) if parts else ""

    @classmethod
    def _visual_knowledge_prompt_payload(cls, value: Any) -> dict[str, Any]:
        """🔥 PHASE 4: Extract visual knowledge for prompt - PRESERVE DETAIL"""
        brief = ContextCompilerService.coerce_visual_knowledge_brief(value)

        # Extract detailed context
        detailed_context = brief.get("detailed_visual_context", {})
        visual_structure_summary = cls._format_visual_structure_summary(detailed_context)

        return {
            "grounding_mode": brief.get("grounding_mode"),
            "grounding_strength": brief.get("grounding_strength"),
            "channel_priority": brief.get("channel_priority", []),
            "channels_present": brief.get("channels_present", []),
            "primary_channels_present": brief.get("primary_channels_present", []),
            "template_suppressed": brief.get("template_suppressed", False),
            "suppressed_channels": brief.get("suppressed_channels", []),
            "candidate_count": brief.get("candidate_count", 0),
            "excluded_candidate_count": brief.get("excluded_candidate_count", 0),
            "abstention_reason": brief.get("abstention_reason", ""),
            "rejection_reasons": brief.get("rejection_reasons", {}),
            "summary": brief.get("summary", ""),
            "items": [
                {
                    "channel": item.get("channel"),
                    "role": item.get("role"),
                    "document_type": item.get("document_type"),
                    "content": item.get("content"),
                }
                for item in (brief.get("items") or [])[:5]
                if isinstance(item, dict)
            ],
            "visual_structure_summary": visual_structure_summary,  # 🔥 PHASE 4: NEW
            "detailed_context": detailed_context,  # 🔥 PHASE 4: Full preservation
        }

    @staticmethod
    def _prompt_intelligence_prompt_payload(value: Any) -> dict[str, Any]:
        brief = value if isinstance(value, dict) else {}
        starter_patterns = []
        for item in (brief.get("starter_patterns") or [])[:4]:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            record = {"text": text}
            platforms = [str(platform).strip() for platform in (item.get("platforms") or []) if str(platform).strip()][:4]
            notes = str(item.get("notes") or "").strip()
            if platforms:
                record["platforms"] = platforms
            if notes:
                record["notes"] = notes
            starter_patterns.append(record)
        return {
            "platform_preset": str(brief.get("platform_preset") or "").strip(),
            "starter_patterns": starter_patterns,
            "starter_texts": [str(item).strip() for item in (brief.get("starter_texts") or []) if str(item).strip()][:4],
            "current_platform_rules": [str(item).strip() for item in (brief.get("current_platform_rules") or []) if str(item).strip()][:4],
            "global_rules": [str(item).strip() for item in (brief.get("global_rules") or []) if str(item).strip()][:4],
            "summary": str(brief.get("summary") or "").strip(),
        }

    @staticmethod
    def _prompt_intelligence_rule_block(
        *,
        brief_name: str = "prompt_intelligence_brief",
        output_targets: str = "headline, body, CTA, hashtags, and other copy-bearing fields",
    ) -> str:
        return " ".join(
            [
                f"Use {brief_name}.starter_patterns and {brief_name}.starter_texts as preferred framing patterns for {output_targets}.",
                f"Adapt those patterns to the requested topic and brand context; do not copy them verbatim unless the user explicitly supplied that exact wording.",
                f"Apply {brief_name}.current_platform_rules before {brief_name}.global_rules when they conflict.",
                f"If {brief_name}.summary is present, treat it as brand-specific prompt guidance for hook structure, CTA style, keyword emphasis, and overall phrasing.",
                f"{brief_name} refines platform-native messaging, but it must never override brand guardrails, brand foundations, or the user's topical anchor.",
            ]
        )

    @staticmethod
    def _persona_depth_rule_block(
        *,
        copy_brief_name: str = "brand_copy_brief",
        audience_brief_name: str = "audience_brief",
    ) -> str:
        return " ".join(
            [
                f"Use {audience_brief_name}.audience_research_motivations and {audience_brief_name}.desired_outcomes before persona defaults when deciding which benefit to lead with.",
                f"Use {audience_brief_name}.audience_research_pain_points and {audience_brief_name}.audience_research_objections before persona defaults for problem framing, reassurance, proof sequencing, and CTA friction reduction.",
                f"Use {copy_brief_name}.persona_motivations, {copy_brief_name}.persona_pain_points, {copy_brief_name}.persona_objections, {audience_brief_name}.persona_behaviors, and {audience_brief_name}.persona_goals to refine nuance when the audience research is missing, broad, or tied on specificity.",
                f"Use {copy_brief_name}.persona_content_behavior, {audience_brief_name}.audience_research_behaviors, and {audience_brief_name}.persona_behaviors to match structure, scannability, and content rhythm.",
                f"Use {copy_brief_name}.persona_language_preference, {audience_brief_name}.persona_language_preference, and {audience_brief_name}.language_preference to keep phrasing readable and audience-native.",
                f"If {audience_brief_name}.signal_priority_note is present, follow it rather than blending research-backed audience evidence and persona defaults too early.",
                "Do not flatten persona depth into generic audience filler when these signals are present.",
            ]
        )

    @staticmethod
    def _audience_research_rule_block(
        *,
        audience_brief_name: str = "audience_brief",
        research_summary_name: str = "research_summary",
    ) -> str:
        return " ".join(
            [
                f"Use {audience_brief_name}.research_highlights, {audience_brief_name}.audience_research_motivations, {audience_brief_name}.desired_outcomes, {audience_brief_name}.audience_research_pain_points, {audience_brief_name}.audience_research_preferences, {audience_brief_name}.audience_research_objections, {audience_brief_name}.trust_signals, {audience_brief_name}.proof_cues, and {audience_brief_name}.comparison_points as concrete audience evidence.",
                f"Use {research_summary_name} to preserve non-redundant differentiators, proof cues, and research-backed phrasing, not as a reason to genericize the audience.",
                f"Treat {audience_brief_name}.research_summary as research-only and {audience_brief_name}.persona_summary as persona-only; do not merge them unless the task explicitly needs a combined synthesis.",
                "Keep specific frictions, aspirations, objections, trust anchors, comparison cues, and proof-oriented details when they are present instead of collapsing them into vague brand-safe filler.",
            ]
        )

    @staticmethod
    def _content_format_prompt_payload(value: Any) -> dict[str, Any]:
        brief = value if isinstance(value, dict) else {}
        return {
            "platform_preset": str(brief.get("platform_preset") or "").strip(),
            "format": str(brief.get("format") or "").strip(),
            "summary": str(brief.get("summary") or "").strip(),
            "format_definition": str(brief.get("format_definition") or "").strip(),
            "format_rules": [str(item).strip() for item in (brief.get("format_rules") or []) if str(item).strip()][:6],
            "platform_rules": [str(item).strip() for item in (brief.get("platform_rules") or []) if str(item).strip()][:6],
            "structural_expectations": [
                str(item).strip() for item in (brief.get("structural_expectations") or []) if str(item).strip()
            ][:6],
            "quality_priorities": [
                str(item).strip() for item in (brief.get("quality_priorities") or []) if str(item).strip()
            ][:6],
            "export_rules": [str(item).strip() for item in (brief.get("export_rules") or []) if str(item).strip()][:4],
            "preferred_slide_count": brief.get("preferred_slide_count"),
            "source_attribution_required": bool(brief.get("source_attribution_required")),
        }

    @staticmethod
    def _research_editorial_prompt_payload(value: Any) -> dict[str, Any]:
        brief = value if isinstance(value, dict) else {}
        fact_model = brief.get("fact_model") if isinstance(brief.get("fact_model"), dict) else {}
        outline = []
        for item in (brief.get("outline") or [])[:8]:
            if not isinstance(item, dict):
                continue
            outline.append(
                {
                    "index": str(item.get("index") or "").strip(),
                    "role": str(item.get("role") or "").strip(),
                    "purpose": str(item.get("purpose") or "").strip(),
                }
            )
        source_pack = []
        for item in (brief.get("source_pack") or [])[:6]:
            if not isinstance(item, dict):
                continue
            source_pack.append(
                {
                    "type": str(item.get("type") or "").strip(),
                    "label": str(item.get("label") or "").strip(),
                    "detail": str(item.get("detail") or "").strip(),
                    "source": str(item.get("source") or "").strip(),
                }
            )
        ranked_sources = []
        for item in (brief.get("ranked_sources") or [])[:4]:
            if not isinstance(item, dict):
                continue
            ranked_sources.append(
                {
                    "label": str(item.get("label") or "").strip(),
                    "detail": str(item.get("detail") or "").strip(),
                    "source": str(item.get("source") or "").strip(),
                }
            )
        return {
            "active": bool(brief.get("active")),
            "mode": str(brief.get("mode") or "").strip(),
            "deliverable_type": str(brief.get("deliverable_type") or "").strip(),
            "platform_preset": str(brief.get("platform_preset") or "").strip(),
            "format": str(brief.get("format") or "").strip(),
            "format_family": str(brief.get("format_family") or "").strip(),
            "editorial_style": str(brief.get("editorial_style") or "").strip(),
            "topic_focus": str(brief.get("topic_focus") or "").strip(),
            "angle": str(brief.get("angle") or "").strip(),
            "thesis": str(brief.get("thesis") or "").strip(),
            "reader_payoff": str(brief.get("reader_payoff") or "").strip(),
            "hook_strategy": str(brief.get("hook_strategy") or "").strip(),
            "insight_hierarchy": [str(item).strip() for item in (brief.get("insight_hierarchy") or []) if str(item).strip()][:6],
            "ordered_story_beats": [str(item).strip() for item in (brief.get("ordered_story_beats") or []) if str(item).strip()][:8],
            "narrative_contract": str(brief.get("narrative_contract") or "").strip(),
            "outline": outline,
            "sample_editorial_brief": {
                "source": str(((brief.get("sample_editorial_brief") or {}) if isinstance(brief.get("sample_editorial_brief"), dict) else {}).get("source") or "").strip(),
                "family_name": str(((brief.get("sample_editorial_brief") or {}) if isinstance(brief.get("sample_editorial_brief"), dict) else {}).get("family_name") or "").strip(),
                "slide_count": ((brief.get("sample_editorial_brief") or {}) if isinstance(brief.get("sample_editorial_brief"), dict) else {}).get("slide_count"),
                "story_roles": [
                    str(item).strip()
                    for item in (((brief.get("sample_editorial_brief") or {}) if isinstance(brief.get("sample_editorial_brief"), dict) else {}).get("story_roles") or [])
                    if str(item).strip()
                ][:8],
                "headline_patterns": [
                    str(item).strip()
                    for item in (((brief.get("sample_editorial_brief") or {}) if isinstance(brief.get("sample_editorial_brief"), dict) else {}).get("headline_patterns") or [])
                    if str(item).strip()
                ][:6],
                "sample_summaries": [
                    str(item).strip()
                    for item in (((brief.get("sample_editorial_brief") or {}) if isinstance(brief.get("sample_editorial_brief"), dict) else {}).get("sample_summaries") or [])
                    if str(item).strip()
                ][:6],
                "explanation_styles": [
                    str(item).strip()
                    for item in (((brief.get("sample_editorial_brief") or {}) if isinstance(brief.get("sample_editorial_brief"), dict) else {}).get("explanation_styles") or [])
                    if str(item).strip()
                ][:4],
                "copy_densities": [
                    str(item).strip()
                    for item in (((brief.get("sample_editorial_brief") or {}) if isinstance(brief.get("sample_editorial_brief"), dict) else {}).get("copy_densities") or [])
                    if str(item).strip()
                ][:4],
                "closing_styles": [
                    str(item).strip()
                    for item in (((brief.get("sample_editorial_brief") or {}) if isinstance(brief.get("sample_editorial_brief"), dict) else {}).get("closing_styles") or [])
                    if str(item).strip()
                ][:4],
                "proof_module_count": ((brief.get("sample_editorial_brief") or {}) if isinstance(brief.get("sample_editorial_brief"), dict) else {}).get("proof_module_count"),
            },
            "fact_model": {
                "verified_facts": [
                    {
                        "label": str(item.get("label") or "").strip(),
                        "value": str(item.get("value") or "").strip(),
                        "source_title": str(item.get("source_title") or "").strip(),
                        "source_url": str(item.get("source_url") or "").strip(),
                    }
                    for item in (fact_model.get("verified_facts") or [])[:6]
                    if isinstance(item, dict)
                ],
                "inferences": [str(item).strip() for item in (fact_model.get("inferences") or []) if str(item).strip()][:4],
                "uncertainties": [str(item).strip() for item in (fact_model.get("uncertainties") or []) if str(item).strip()][:4],
            },
            "ranked_sources": ranked_sources,
            "citation_rules": {
                "style": str((brief.get("citation_rules") or {}).get("style") or "").strip()
                if isinstance(brief.get("citation_rules"), dict)
                else "",
                "rules": [
                    str(item).strip()
                    for item in ((brief.get("citation_rules") or {}).get("rules") if isinstance(brief.get("citation_rules"), dict) else [])
                    if str(item).strip()
                ][:4],
            },
            "source_backing_rules": [str(item).strip() for item in (brief.get("source_backing_rules") or []) if str(item).strip()][:4],
            "source_pack": source_pack,
            "source_count": int(brief.get("source_count") or 0),
            "preferred_slide_count": brief.get("preferred_slide_count"),
            "summary": str(brief.get("summary") or "").strip(),
            "disclaimer_requested": bool(brief.get("disclaimer_requested")),
            "disclaimer_placement": str(brief.get("disclaimer_placement") or "").strip(),
            "disclaimer_style": str(brief.get("disclaimer_style") or "").strip(),
            "needs_live_research": bool(brief.get("needs_live_research")),
            "research_status": str(brief.get("research_status") or "").strip(),
        }

    @staticmethod
    def _format_family_plan_prompt_payload(value: Any) -> dict[str, Any]:
        plan = value if isinstance(value, dict) else {}
        return {
            "family": str(plan.get("family") or "").strip(),
            "deliverable_type": str(plan.get("deliverable_type") or "").strip(),
            "format": str(plan.get("format") or "").strip(),
            "platform_preset": str(plan.get("platform_preset") or "").strip(),
            "primary_unit": str(plan.get("primary_unit") or "").strip(),
            "body_shape": str(plan.get("body_shape") or "").strip(),
            "outline_mode": str(plan.get("outline_mode") or "").strip(),
            "content_structure": [str(item).strip() for item in (plan.get("content_structure") or []) if str(item).strip()][:8],
            "required_components": [str(item).strip() for item in (plan.get("required_components") or []) if str(item).strip()][:8],
            "optional_components": [str(item).strip() for item in (plan.get("optional_components") or []) if str(item).strip()][:10],
            "copy_density": str(plan.get("copy_density") or "").strip(),
            "visual_density": str(plan.get("visual_density") or "").strip(),
            "metadata_fields": [str(item).strip() for item in (plan.get("metadata_fields") or []) if str(item).strip()][:12],
            "planning_rules": [str(item).strip() for item in (plan.get("planning_rules") or []) if str(item).strip()][:8],
            "preferred_slide_count": plan.get("preferred_slide_count"),
        }

    @staticmethod
    def _content_plan_prompt_payload(value: Any) -> dict[str, Any]:
        plan = value if isinstance(value, dict) else {}
        return {
            "planning_family": str(plan.get("planning_family") or "").strip(),
            "deliverable_type": str(plan.get("deliverable_type") or "").strip(),
            "format_family": str(plan.get("format_family") or "").strip(),
            "primary_unit": str(plan.get("primary_unit") or "").strip(),
            "body_shape": str(plan.get("body_shape") or "").strip(),
            "outline_mode": str(plan.get("outline_mode") or "").strip(),
            "density_target": str(plan.get("density_target") or "").strip(),
            "content_structure": [str(item).strip() for item in (plan.get("content_structure") or []) if str(item).strip()][:8],
            "required_components": [str(item).strip() for item in (plan.get("required_components") or []) if str(item).strip()][:8],
            "optional_components": [str(item).strip() for item in (plan.get("optional_components") or []) if str(item).strip()][:10],
            "metadata_fields": [str(item).strip() for item in (plan.get("metadata_fields") or []) if str(item).strip()][:12],
            "planning_rules": [str(item).strip() for item in (plan.get("planning_rules") or []) if str(item).strip()][:8],
            "preferred_slide_count": plan.get("preferred_slide_count"),
            "sequence_contract": str(plan.get("sequence_contract") or "").strip(),
            "sequence_expectation": str(plan.get("sequence_expectation") or "").strip(),
            "native_metadata_fields": [
                str(item).strip() for item in (plan.get("native_metadata_fields") or []) if str(item).strip()
            ][:6],
            "research_mode": str(plan.get("research_mode") or "").strip(),
            "ordered_story_beats": [str(item).strip() for item in (plan.get("ordered_story_beats") or []) if str(item).strip()][:8],
            "carousel_archetype": str(plan.get("carousel_archetype") or "").strip(),
            "carousel_slide_grammar": [
                {
                    "role": str(item.get("role") or "").strip(),
                    "job": str(item.get("job") or "").strip(),
                }
                for item in (plan.get("carousel_slide_grammar") or [])[:6]
                if isinstance(item, dict) and (str(item.get("role") or "").strip() or str(item.get("job") or "").strip())
            ],
            "carousel_archetype_rules": [
                str(item).strip() for item in (plan.get("carousel_archetype_rules") or []) if str(item).strip()
            ][:6],
            "sample_editorial_source": str(plan.get("sample_editorial_source") or "").strip(),
            "sample_story_roles": [str(item).strip() for item in (plan.get("sample_story_roles") or []) if str(item).strip()][:8],
            "sample_headline_patterns": [str(item).strip() for item in (plan.get("sample_headline_patterns") or []) if str(item).strip()][:6],
            "sample_summaries": [str(item).strip() for item in (plan.get("sample_summaries") or []) if str(item).strip()][:6],
            "sample_explanation_styles": [str(item).strip() for item in (plan.get("sample_explanation_styles") or []) if str(item).strip()][:4],
            "sample_copy_densities": [str(item).strip() for item in (plan.get("sample_copy_densities") or []) if str(item).strip()][:4],
            "sample_closing_styles": [str(item).strip() for item in (plan.get("sample_closing_styles") or []) if str(item).strip()][:4],
            "disclaimer_requested": bool(plan.get("disclaimer_requested")),
            "disclaimer_placement": str(plan.get("disclaimer_placement") or "").strip(),
        }

    @staticmethod
    def _visual_plan_prompt_payload(value: Any) -> dict[str, Any]:
        plan = value if isinstance(value, dict) else {}
        return {
            "planning_family": str(plan.get("planning_family") or "").strip(),
            "format_family": str(plan.get("format_family") or "").strip(),
            "primary_unit": str(plan.get("primary_unit") or "").strip(),
            "body_shape": str(plan.get("body_shape") or "").strip(),
            "density_target": str(plan.get("density_target") or "").strip(),
            "preferred_slide_count": plan.get("preferred_slide_count"),
            "page_strategy": str(plan.get("page_strategy") or "").strip(),
            "render_mode": str(plan.get("render_mode") or "").strip(),
            "execution_mode": str(plan.get("execution_mode") or "").strip(),
            "visual_sequence_expectation": str(plan.get("visual_sequence_expectation") or "").strip(),
            "research_mode": str(plan.get("research_mode") or "").strip(),
        }

    @staticmethod
    def _format_family_rule_block(
        *,
        plan_name: str = "format_family_plan",
    ) -> str:
        return " ".join(
            [
                f"Treat {plan_name} as the authoritative structural contract for this content family.",
                f"Follow {plan_name}.primary_unit, {plan_name}.body_shape, {plan_name}.content_structure, and {plan_name}.metadata_fields instead of defaulting to one generic social-copy schema.",
                f"Respect {plan_name}.copy_density and {plan_name}.visual_density when deciding how much meaning belongs in the headline, body, proof cues, sections, or slides.",
                f"If {plan_name}.family is long_form, preserve section progression; if short_form, preserve compact native rhythm; if static, keep one dominant panel message; if carousel, plan a real slide sequence; if infographic, plan stacked explanatory sections.",
            ]
        )

    @staticmethod
    def _planning_contract_rule_block(
        *,
        content_plan_name: str = "content_plan",
        visual_plan_name: str = "visual_plan",
        format_family_name: str = "format_family_plan",
        research_brief_name: str = "research_editorial_brief",
    ) -> str:
        return " ".join(
            [
                f"Treat {content_plan_name} and {visual_plan_name} as execution contracts, not optional hints.",
                f"Follow {content_plan_name}.sequence_contract, {content_plan_name}.sequence_expectation, {content_plan_name}.content_structure, and {content_plan_name}.planning_rules before defaulting to a flat headline/body summary.",
                f"When {content_plan_name}.format_family is carousel, metadata.carousel_slide_specs is the primary narrative structure and must carry the real slide-by-slide story.",
                "Each metadata.carousel_slide_specs item should be a distinct object with slide_number, slide_role, headline, supporting_line, body, body_points, proof_points, stat_highlights, visual_focus, and transition_note.",
                f"If {content_plan_name}.ordered_story_beats is present, preserve that beat order exactly and map one core beat to one slide before applying any stock carousel archetype habits.",
                f"When {content_plan_name}.carousel_archetype is present, treat it as the required carousel grammar and follow {content_plan_name}.carousel_slide_grammar step by step.",
                f"When {content_plan_name}.carousel_archetype_rules are present, treat them as hard constraints for slide sequencing and role discipline.",
                "For carousel outputs, slide_role must describe the editorial job of the slide such as hook, context, structure, undercovered_angle, strategic_meaning, takeaway, or closing.",
                "For carousel outputs, do not let one archetype drift into another: an editorial reveal should not read like a list carousel, and a comparison carousel should not read like a poster split into pages.",
                "For carousel outputs, use body and/or body_points to carry the real per-slide explanation instead of hiding the whole story in supporting_line alone.",
                "For carousel outputs, only the final slide may contain CTA text; interior slide CTA fields must be empty strings.",
                f"Use {content_plan_name}.preferred_slide_count, {visual_plan_name}.preferred_slide_count, {format_family_name}.preferred_slide_count, and {research_brief_name}.outline to decide how many slide specs the story needs.",
                "Do not repeat the same supporting_line, proof_points, or generic lesson label across slide specs.",
                "Do not let one slide repeat another slide's editorial job; each slide should advance the sequence by one analytical step.",
                "When the carousel archetype is list_teaching, dedicate one concept or item per interior slide using a repeated mini-structure such as concept, explanation, example, and consequence.",
                "When the carousel archetype is comparison_framework, dedicate one option or strategy per interior slide using a repeated comparison structure such as what it is, how it works, and where it fits.",
                "When the carousel archetype is problem_solution_feature, frame the problem before the solution, then move through capability clusters before the value close.",
                "When the carousel archetype is editorial_reveal, keep hook, factual unpacking, what most coverage missed, and strategic implication as separate slide jobs.",
                "The top-level headline, body, and CTA should summarize the overall sequence, not replace the per-slide structure.",
                f"When {content_plan_name}.format_family is static, keep metadata.carousel_slide_specs empty and make metadata.static_panel_spec the primary surface contract.",
                "metadata.static_panel_spec should be a single object with panel_goal, dominant_message, supporting_lines, proof_points, stat_highlights, visual_focus, and cta_mode.",
                f"If {content_plan_name}.sequence_contract is sample_static_panel_hierarchy and {content_plan_name}.sample_story_roles is present, treat those sampled roles as the required single-surface reading order for metadata.static_panel_spec.",
                f"If {content_plan_name}.sample_headline_patterns, {content_plan_name}.sample_explanation_styles, or {content_plan_name}.sample_copy_densities are present for a static output, match that sampled message hierarchy and density instead of defaulting to poster-generic filler.",
                f"When {content_plan_name}.format_family is infographic, keep metadata.carousel_slide_specs empty unless the user explicitly asks for a paginated carousel version; make metadata.infographic_section_specs the primary stacked structure.",
                "Each metadata.infographic_section_specs item should be a distinct object with section_number, section_role, section_label, headline, body, body_points, proof_points, stat_highlights, claim_evidence_pairs, and visual_focus.",
                "For infographic outputs, use infographic_section_specs to separate overview, evidence, comparison, process, or takeaway sections instead of one long proof-point dump.",
                f"If {content_plan_name}.sequence_contract is sample_infographic_section_flow and {content_plan_name}.sample_story_roles is present, preserve that sampled section-role order in metadata.infographic_section_specs before applying any generic infographic structure.",
                f"If {content_plan_name}.sample_headline_patterns, {content_plan_name}.sample_explanation_styles, or {content_plan_name}.sample_copy_densities are present for an infographic output, follow that sampled teaching density and section rhythm instead of flattening the topic into summary blocks.",
                f"Follow {visual_plan_name}.execution_mode and {visual_plan_name}.visual_sequence_expectation so multi-page outputs feel intentionally sequenced rather than cloned.",
            ]
        )

    @staticmethod
    def _research_editorial_rule_block(
        *,
        brief_name: str = "research_editorial_brief",
    ) -> str:
        return " ".join(
            [
                f"When {brief_name}.active is true, treat it as the authoritative analytical plan for research-heavy content.",
                f"Preserve {brief_name}.thesis, {brief_name}.angle, {brief_name}.reader_payoff, and {brief_name}.hook_strategy instead of flattening them into generic social commentary.",
                f"Use {brief_name}.insight_hierarchy and {brief_name}.source_pack to anchor the copy in specific facts, clauses, comparisons, or implications when present.",
                f"If {brief_name}.narrative_contract is preserve_user_order and {brief_name}.ordered_story_beats is present, treat those ordered beats as a hard storytelling contract.",
                f"If {brief_name}.narrative_contract is follow_sample_editorial_rhythm and {brief_name}.sample_editorial_brief.story_roles is present, preserve that sampled slide-role rhythm while adapting all wording to the user's topic.",
                f"If {brief_name}.narrative_contract is follow_sample_infographic_flow and {brief_name}.sample_editorial_brief.story_roles is present, preserve that sampled infographic section rhythm while adapting the facts and wording to the user's topic.",
                f"If {brief_name}.narrative_contract is follow_sample_static_hierarchy and {brief_name}.sample_editorial_brief.story_roles is present, preserve that sampled static reading hierarchy while adapting the message to the user's topic.",
                f"Treat {brief_name}.fact_model.verified_facts as confirmed facts, {brief_name}.fact_model.inferences as interpretation, and {brief_name}.fact_model.uncertainties as caution signals.",
                f"Follow {brief_name}.citation_rules.style and {brief_name}.citation_rules.rules so attribution matches the output format instead of using one generic citation habit.",
                f"Prefer {brief_name}.ranked_sources and {brief_name}.source_backing_rules when deciding which evidence is strong enough to foreground.",
                f"Use {brief_name}.outline to control section or slide progression; each role should add a new analytical step rather than repeating the same summary.",
                f"If {brief_name}.disclaimer_requested is true, reserve space for a small compliant disclaimer in the requested placement instead of spending that space on decorative filler.",
                f"If {brief_name}.needs_live_research is true and {brief_name}.fact_model.verified_facts is empty, do not invent exact numbers, percentages, dates, rankings, or survey claims beyond what the user explicitly supplied.",
                "Distinguish what happened from why it matters and from what is undercovered or strategically important.",
                "Do not state inferences or implications as if they were verified facts.",
                "If uncertainty remains, name it briefly instead of smoothing it away.",
                "Do not replace research-backed structure with generic brand filler, generic motivational hooks, or repetitive proof-point lists.",
                "Use research as raw material for brand strategy, not as the voice. The finished copy must feel like a premium brand creative, not a research paper, policy memo, or source digest.",
                "Translate evidence into sharp audience-facing hooks, contrasts, labels, and takeaways. Avoid academic transitions such as furthermore, moreover, additionally, in conclusion, and this paper/report examines.",
                "On-canvas copy should be quotable and designed: short lines, strong nouns, active verbs, and one clear idea per module. Put source discipline behind the scenes unless attribution is explicitly required.",
                "If the format is carousel or infographic, let each slide or section advance the editorial outline instead of compressing the topic into one poster summary.",
                "If the format is static or short-form text, condense the strongest thesis and one or two supporting insights without losing the analytical angle.",
            ]
        )

    @staticmethod
    def _has_guide_scoped_client_quality_signals(content_format_brief: dict[str, Any]) -> bool:
        return any(
            [
                str(content_format_brief.get("summary") or "").strip(),
                str(content_format_brief.get("format_definition") or "").strip(),
                content_format_brief.get("format_rules") or [],
                content_format_brief.get("platform_rules") or [],
                content_format_brief.get("structural_expectations") or [],
                content_format_brief.get("quality_priorities") or [],
            ]
        )

    @staticmethod
    def _client_quality_rule_block(
        *,
        brief_name: str = "content_format_brief",
    ) -> str:
        return " ".join(
            [
                f"When {brief_name}.summary or {brief_name}.quality_priorities are present, treat them as client-approved quality guidance.",
                "Preserve the core idea instead of diluting it into safe, generic filler.",
                "Keep messaging audience-facing, not internal, descriptive, or process-oriented.",
                "Decide the structure intentionally instead of repeating rigid templates by habit.",
                "Do not over-structure metadata; use it to support the format, not to pad the response.",
                "Match copy density to the requested format and platform instead of applying one universal brevity rule.",
                f"When {brief_name}.format is static, aim for one clear message, one strong headline, and one or two supporting lines that read within two seconds.",
                f"When {brief_name}.format is carousel, open with a hook, let each slide or page earn one idea, preserve narrative progression, and close with a CTA. If {brief_name}.preferred_slide_count is present, treat it as the preferred pacing rather than a hard mandate. If an ordered narrative is supplied elsewhere in context, preserve that order exactly.",
                f"When {brief_name}.format is infographic, lead with a title or question, use educational hierarchy for data, comparison, or process content, and include a source-attribution cue whenever {brief_name}.source_attribution_required is true or factual claims are central.",
                f"When {brief_name}.platform_preset is linkedin and {brief_name}.format is carousel, treat it as paginated PDF storytelling rather than swipe-first Instagram slang.",
                f"When {brief_name}.platform_preset is instagram, favor scan-friendly hierarchy and image-native pacing.",
                f"When {brief_name}.platform_preset is x, keep the messaging tighter and lower-density than longer-form social formats.",
            ]
        )

    @classmethod
    def _has_mistake_carousel_signals(
        cls,
        prompt: str,
        content_format_brief: dict[str, Any],
    ) -> bool:
        if str(content_format_brief.get("format") or "").strip().casefold() != "carousel":
            return False
        return bool(cls.MISTAKE_CAROUSEL_SIGNAL_PATTERN.search(str(prompt or "")))

    @staticmethod
    def _mistake_carousel_rule_block(
        *,
        prompt_name: str,
        brief_name: str = "content_format_brief",
    ) -> str:
        return " ".join(
            [
                f"When {brief_name}.format is carousel and {prompt_name} clearly signals mistakes, pitfalls, errors, or what to avoid, switch into a mistake-teaching story structure.",
                "Slide 1 must open with a strong hook, not a generic category label.",
                "Slides 2 through n-1 must frame each teaching section as a named mistake, not a vague insight bucket.",
                "Each mistake slide must follow the same structure: Mistake, Why, Impact, and Fix.",
                "Each mistake slide must explain the cause or context, the impact of ignoring it, and the corrective action or fix.",
                "When the prompt implies top, common, or most mistakes, include at least three distinct mistakes before the CTA whenever the content supports it.",
                "Reserve the final slide for the CTA instead of adding another educational detail slide.",
                "Never use generic labels like Investment Education, Key Insight, or Key Point for mistake-style carousel slides.",
                "Never present correct advice as the mistake itself; frame the error in negative terms such as not diversifying, chasing yield, or ignoring duration.",
                "Do not collapse top mistakes into one mistake plus generic tips.",
                "Do not repeat CTA copy or generic reassurance across the interior slides.",
                "Avoid vague educational filler without a concrete causal teaching line.",
            ]
        )

    @staticmethod
    def _content_metadata_schema_block() -> str:
        return "\n".join(
            [
                "- section_label: a short optional label or chip only when it adds clarity",
                "- supporting_line: a concise supporting sentence or subheadline sized to the format and story depth",
                "- proof_points: a list of short proof points, benefit lines, or teaching cues; include as many as the format genuinely needs without filler",
                "- stat_highlights: optional compact stat-style highlights, chips, or key ideas; include enough to support the story without forcing an arbitrary count",
                "- carousel_slide_specs: for carousel outputs, a list of slide objects with keys slide_number, slide_role, headline, supporting_line, body, body_points, proof_points, stat_highlights, visual_focus, transition_note, and cta",
                "- carousel_slide_specs rules: slide_role must name the editorial job of the slide, body/body_points must carry the real per-slide explanation, and only the final slide may contain non-empty cta text",
                "- infographic_section_specs: for infographic outputs, a list of section objects with keys section_number, section_role, section_label, headline, body, body_points, proof_points, stat_highlights, claim_evidence_pairs, and visual_focus",
                "- infographic_section_specs rules: use these to create real stacked editorial sections such as overview, evidence, comparison, process, or takeaway instead of one flat bullet dump",
                "- static_panel_spec: for static outputs, a single object with keys panel_goal, dominant_message, supporting_lines, proof_points, stat_highlights, visual_focus, and cta_mode",
                "- static_panel_spec rules: dominant_message should capture the one thing the panel must communicate at a glance, and supporting_lines should stay short enough to preserve one-panel clarity",
                "- visual_focus rules: provide highly specific, literal premium 2D/3D visual scenes or contextual graphics that directly demonstrate the real-world situation of the slide's content. Do NOT use abstract conceptual metaphors (e.g. avoid vague shields, glowing nodes, chess pieces, or floating jigsaw puzzles). For the first and last slides in particular, specify a strong, attention-grabbing literal hook scene.",
                "- visual_focus must be a content-specific natural-language visual direction, never a JSON object, storage_path, reference_image handle, asset id, filename, or instruction to use an uploaded reference as the visual idea",
                "- hook_type: a short persuasion label such as problem-led, benefit-led, proof-led, comparison-led, contrast-led, myth-busting, or question-led",
                "- objection_handling: short lines that answer likely objections or friction points when the format benefits from them",
                "- trust_builders: credibility cues, proof cues, or reassurance anchors; keep only the ones that materially strengthen the story",
                "- claim_evidence_pairs: objects with keys claim and evidence; include as many concrete pairs as the story genuinely needs",
                "- logo_position: a short placement hint such as top-right, top-left, bottom-right, or bottom-left",
                "- logo_background_tone: one of light, dark, or neutral to describe the intended surface behind the exact overlaid logo",
                "- visual_direction: a short sentence describing the ideal visual mood/composition",
                "- design_style: a short phrase such as editorial finance poster, bold minimal social ad, or premium infographic",
                "- image_prompt: a text-free visual concept for the image generation layer",
            ]
        )

    @staticmethod
    def _persuasion_metadata_rule_block() -> str:
        return " ".join(
            [
                "Use hook_type to make the persuasion pattern explicit instead of hiding it inside generic copy.",
                "Use objection_handling to show how the message resolves friction or skepticism, not just that the objection exists.",
                "Use trust_builders to preserve credibility cues, reassurance anchors, and proof-oriented confidence builders.",
                "Use claim_evidence_pairs so persuasive claims stay tied to concrete support instead of floating as unsupported benefits.",
                "Let metadata depth match the requested format, sample pattern, and narrative load instead of forcing the same small list size every time.",
                "These metadata fields can be richer than the on-canvas text, but they must still stay concise, brand-safe, and usable downstream.",
            ]
        )

    @staticmethod
    def _strategic_content_quality_rule_block() -> str:
        return " ".join(
            [
                "Strategic content quality rules: think like a senior LinkedIn/Instagram campaign strategist and finance-education copy lead, not a mechanical summarizer.",
                "Brand intelligence rules: write for the brand's audience, market category, platform, and visual surface. The answer should feel campaign-ready, not like notes from a research analyst.",
                "Evidence is scaffolding, not the voice. Convert facts into creative tension, memorable framing, and crisp implications; do not narrate the research process or list sources as content unless the format asks for attribution.",
                "Prefer concrete creative formulations over academic phrasing: use punchy contrast, curiosity, reversal, stakes, and smart-reader payoff. Avoid essay-like wording such as 'this highlights', 'it is important to note', 'furthermore', 'moreover', 'therefore', and 'in conclusion' unless they are inside verified quoted copy.",
                "Keep on-canvas copy designed and visual: short, rhythmic lines; no paragraph blocks unless the selected sample uses them; no citation-style clutter; no repeated 'verified facts from...' filler.",
                "Every carousel slide must earn its place with a distinct strategic job: hook tension, factual mechanism, hidden/undercovered angle, implication, proof, or closing payoff.",
                "Do not use sample headings as lazy copy. If the sample says 'Why this matters now' or 'What actually changed', adapt that grammar into topic-specific, audience-facing copy with a concrete angle.",
                "Headlines must contain the real topic, tension, consequence, audience implication, or decision payoff; avoid generic labels such as key insight, what changed, why it matters, or investment education unless paired with a concrete topic-specific modifier.",
                "Use verified_facts and user-supplied facts as the only source for exact dates, numbers, percentages, rankings, currency amounts, commitments, tariffs, returns, or regulatory claims.",
                "If a claim is inferential, phrase it as an implication or what-it-could-mean, not as a confirmed fact.",
                "Tie each claim_evidence_pair to either a verified fact, a user-supplied fact, or a clearly marked strategic inference.",
                "Use audience intelligence: choose the lead and payoff based on audience motivations, objections, desired outcomes, trust cues, and platform behavior, not only the topic.",
                "Use campaign intelligence: align hook_type, objection_handling, trust_builders, CTA, and slide order to the objective_brief and platform_preset.",
                "For LinkedIn, prefer expert educational tension, strategic implication, and professional clarity over hype or generic motivational copy.",
                "For Instagram, keep copy more visual, compressed, and emotionally legible while preserving factual accuracy.",
                "Visual_focus must be as strategic as copy: specify whether the slide needs premium 3D, 2.5D/isometric, flat editorial, dashboard/product surface, chart/module, icon system, document/evidence object, or brand-led visual treatment based on sample visual_craft and brand_visual_brief.",
                "Hook slides need a strong entry visual; middle slides need section-specific visual systems; final slides need a decisive closing/product/action visual. Do not repeat the same generic document, magnifier, chart, handshake, flag, or business icon motif across slides.",
                "For visual metadata, avoid generic stock concepts such as professional photo, handshake, generic chart, vague business icon, document pile, magnifying glass, or abstract globe unless the selected sample explicitly uses that motif with premium craft.",
            ]
        )

    @staticmethod
    def _data_visualization_rule_block() -> str:
        return " ".join(
            [
                "Data visualization rules: tables, tabular sections, charts, graphs, dashboards, matrices, comparison grids, timelines, scorecards, and metric modules are content instruments, not decoration.",
                "Only request a table/chart/graph when it is directly supported by user_prompt, verified_facts, claim_evidence_pairs, proof_points, stat_highlights, body_points, or the active section/slide content.",
                "If no approved data/content anchors exist, do not request or render any table, tabular layout, chart, graph, dashboard, scorecard, timeline, metric module, fake UI analytics panel, or matrix.",
                "Every row, column, axis, legend, label, card heading, metric, and comparison bucket must map to the approved content; do not draw generic bars, unlabeled lines, fake axes, random percentages, placeholder dashboards, or abstract finance widgets.",
                "If exact numeric values, time series, percentages, currency amounts, or rankings are unavailable, do not invent them. When approved qualitative anchors exist, use qualitative comparison cards, process modules, labeled evidence blocks, or a non-numeric matrix instead of numeric charts.",
                "Choose the right data visual type mechanically: table/matrix for comparisons, bar chart for ranked categories with real values, line chart for time series with real dates, flow/process chart for sequences, scorecard/dashboard modules for qualitative evidence, and callout cards for single proof points.",
                "For carousel slides, each slide's data visual must serve that slide's story role and match the selected sample's partitioning and density. For static and infographic outputs, the data visual must support the dominant message or section job without becoming unreadable filler.",
            ]
        )

    @staticmethod
    def _logo_overlay_rule_block() -> str:
        return " ".join(
            [
                "Treat the corner logo placement as a reserved overlay zone for the exact stored brand asset, not as generated artwork.",
                "When a logo is needed, include a concrete logo element with corner-based geometry, style.fit=contain, and enough breathing room around it.",
                "Use metadata.logo_position to describe the intended corner placement when it is deliberate.",
                "Use metadata.logo_background_tone and scene_graph logo validation hints to describe whether the reserved logo surface is light, dark, or neutral.",
                "If the reserved logo zone sits on a light surface, request dark_on_light; if it sits on a dark surface, request light_on_dark.",
                "CRITICAL: Never include the words 'logo', 'brandmark', or 'watermark' inside metadata.image_prompt, metadata.visual_direction, or metadata.design_style as this causes the image model to hallucinate fake logos.",
                "Keep the reserved corner visually quiet, low-texture, and free of competing contrast so the exact overlaid logo and its transparent edges will read cleanly.",
            ]
        )

    @staticmethod
    def _visual_grounding_rule_block(
        *,
        brief_name: str = "visual_knowledge_brief",
        fallback_sources: str,
        output_targets: str | None = None,
    ) -> str:
        rules = [
            f"Always follow {brief_name}.grounding_mode and {brief_name}.grounding_strength.",
            f"Treat any {brief_name} item with role=fallback as lower priority than primary or supporting evidence.",
            f"If {brief_name}.template_suppressed is true, do not use template cues from suppressed channels.",
            "Clean-looking OCR, specimen, or promotional template copy is not valid primary visual grounding just because it is readable.",
            (
                f"If {brief_name}.abstention_reason or {brief_name}.rejection_reasons explain why a candidate or channel was rejected, "
                "treat that as an exclusion rule and do not reconstruct that rejected cue in the output."
            ),
            (
                f"If {brief_name}.grounding_mode is brand_knowledge, use {brief_name}.items as the primary source of visual grounding. "
                "Only use model reasoning to synthesize or clarify those retrieved cues without overriding them."
            ),
        ]
        if output_targets:
            rules.extend(
                [
                    (
                        f"When {brief_name}.grounding_mode is brand_knowledge, {output_targets} must be derived from "
                        f"{brief_name}.items plus the approved brand visual brief."
                    ),
                    (
                        f"When {brief_name}.grounding_mode is llm_fallback, {output_targets} must be derived from {fallback_sources}, "
                        "not from suppressed template cues or rejected candidates."
                    ),
                ]
            )
        else:
            rules.append(
                f"When {brief_name}.grounding_mode is llm_fallback, derive the visual direction from {fallback_sources}, "
                "not from suppressed template cues or rejected candidates."
            )
        return " ".join(rules)

    def compose_generation_envelope(
        self,
        user_prompt: str,
        compiled_context: dict[str, Any],
        studio_panel: dict[str, Any],
    ) -> PromptEnvelope:
        brand_copy_brief = compiled_context.get("brand_copy_brief", {}) or {}
        brand_visual_brief = compiled_context.get("brand_visual_brief", {}) or {}
        audience_brief = compiled_context.get("audience_brief", {}) or {}
        knowledge_brief = compiled_context.get("knowledge_brief", []) or []
        visual_knowledge_brief = self._visual_knowledge_prompt_payload(compiled_context.get("visual_knowledge_brief"))
        render_constraints = compiled_context.get("render_constraints", {}) or {}
        session_brief = compiled_context.get("session_brief", {}) or {}
        template_fit_brief = compiled_context.get("template_fit_brief", {}) or {}
        reference_asset_brief = compiled_context.get("reference_asset_brief", []) or []
        prompt_intelligence_brief = self._prompt_intelligence_prompt_payload(compiled_context.get("prompt_intelligence_brief"))
        content_format_brief = self._content_format_prompt_payload(compiled_context.get("content_format_brief"))
        research_editorial_brief = self._research_editorial_prompt_payload(compiled_context.get("research_editorial_brief"))
        format_family_plan = self._format_family_plan_prompt_payload(compiled_context.get("format_family_plan"))
        content_plan = self._content_plan_prompt_payload(compiled_context.get("content_plan"))
        visual_plan = self._visual_plan_prompt_payload(compiled_context.get("visual_plan"))
        prompt_intelligence_rules = self._prompt_intelligence_rule_block()
        persona_depth_rules = self._persona_depth_rule_block()
        audience_research_rules = self._audience_research_rule_block()
        research_editorial_rules = self._research_editorial_rule_block()
        format_family_rules = self._format_family_rule_block()
        planning_contract_rules = self._planning_contract_rule_block()
        client_quality_rules = (
            self._client_quality_rule_block()
            if self._has_guide_scoped_client_quality_signals(content_format_brief)
            else ""
        )
        mistake_carousel_rules = (
            self._mistake_carousel_rule_block(prompt_name="user_prompt")
            if client_quality_rules and self._has_mistake_carousel_signals(user_prompt, content_format_brief)
            else ""
        )
        content_metadata_schema = self._content_metadata_schema_block()
        persuasion_metadata_rules = self._persuasion_metadata_rule_block()
        strategic_content_quality_rules = self._strategic_content_quality_rule_block()
        data_visualization_rules = self._data_visualization_rule_block()
        logo_overlay_rules = self._logo_overlay_rule_block()
        platform_preset = studio_panel.get("platform_preset")
        format_name = studio_panel.get("format")
        follow_up_mode = session_brief.get("follow_up_mode")
        visual_grounding_rules = self._visual_grounding_rule_block(
            fallback_sources="the approved brand visual brief, approved copy direction, the user's topical anchor, and render constraints",
            output_targets="metadata.visual_direction, metadata.design_style, and metadata.image_prompt",
        )

        system = f"""
        You are Violyt's content orchestration engine for brand-safe generation.
        Always obey brand guardrails over user prompts.
        Return JSON only with keys: headline, body, cta, hashtags, metadata.
        Keep the response renderer-ready, but do not flatten multi-panel or educational formats into poster-style shorthand.
        Headline should be compact and punchy for static single-panel surfaces; for carousel covers and infographic titles it can be a fuller hook when the story requires it.
        Body should be platform-appropriate, avoid unnecessary repetition, and match the requested format density instead of defaulting to one universal length rule.
        CTA should be action-oriented; keep it short for static outputs, but allow a fuller closing line when a carousel or infographic needs a proper ending beat.
        Metadata must be a JSON object and should include:
        {content_metadata_schema}
        Use empty strings or empty lists when a metadata field is unknown. Never return null for metadata keys.
        For static social outputs, prefer fewer words on the canvas and push extra meaning into proof_points and stat_highlights.
        For carousels and infographics, distribute meaning through sections instead of cramming the whole story into one line.
        For carousel outputs, metadata.carousel_slide_specs must include the real slide-by-slide explanation in slide-level body and/or body_points fields; do not rely on supporting_line alone.
        For carousel outputs, only the final slide spec may contain CTA text. Keep interior slide CTA fields empty.
        When a selected sample/reference sequence is present with style_reference_only surface policy, its per-slide sample_page_headline, sample_page_supporting, sample_page_copy, sample_page_editorial_role, sample_page_copy_behavior, sample_page_copy_density, sample_page_closing_grammar, headline_hint, and sequence_summary are editorial authority for hook grammar, insight depth, content density, and closing style. Adapt the user's topic into that editorial grammar instead of falling back to generic explanatory headings.
        If the sample page copy overlaps the user's topic or research summary, treat its concrete facts and insight hierarchy as approved content anchors. If it does not overlap, use only the rhetorical pattern and structure, not the literal facts.
        Do not convert an editorial or macro-takeaway closing sample into a product promotion or platform CTA unless the user explicitly requests a promotion or the selected sample page itself uses that CTA/product grammar.
        Brand-intelligent writing requirement: final slide copy must sound like polished brand communication for the intended audience, not a research paper, compliance memo, or analyst brief. Use facts to create sharp creative framing; do not write source-process phrases such as "verified facts from..." as visible module copy unless the sample explicitly uses source labels.
        When the requested format or sample implies a 5-7 slide sequence, provide enough distinct teaching units to fill that story arc instead of collapsing everything into one numbered-list poster summary.
        Persuasion metadata rules: {persuasion_metadata_rules}
        Strategic content quality rules: {strategic_content_quality_rules}
        Data visualization rules: {data_visualization_rules}
        Logo overlay rules: {logo_overlay_rules}
        Brand name: {brand_copy_brief.get("brand_name")}
        Primary tone attributes: {brand_copy_brief.get("tone_attributes", [])}
        Primary emotion: {brand_copy_brief.get("primary_emotion")}
        Avoided emotion: {brand_copy_brief.get("avoided_emotion")}
        Guardrails do: {brand_copy_brief.get("dos", [])}
        Guardrails do not: {brand_copy_brief.get("donts", [])}
        Blocked words: {brand_copy_brief.get("blocked_words", [])}
        Preferred words: {brand_copy_brief.get("positive_words", [])}
        Platform preset: {platform_preset}
        Format: {format_name}
        File type: {studio_panel.get("file_type")}
        Platform guidance: {self.PLATFORM_GUIDANCE.get(platform_preset, "Keep the copy platform-appropriate.")}
        Format guidance: {self.FORMAT_GUIDANCE.get(format_name, "Keep the content structured and renderer-friendly.")}
        Copy brief: {brand_copy_brief}
        Audience brief: {audience_brief}
        Visual brief: {brand_visual_brief}
        Template fit brief: {template_fit_brief}
        Render constraints: {render_constraints}
        Session brief: {session_brief}
        Reference asset brief: {reference_asset_brief}
        Prompt intelligence brief: {prompt_intelligence_brief}
        Content format brief: {content_format_brief}
        Prompt intelligence rules: {prompt_intelligence_rules}
        Persona depth rules: {persona_depth_rules}
        Audience research rules: {audience_research_rules}
        Research-editorial rules: {research_editorial_rules}
        Planning contract rules: {planning_contract_rules}
        Client quality rules: {client_quality_rules or "No client-specific quality overrides are active."}
        Mistake-style carousel rules: {mistake_carousel_rules or "No mistake-specific carousel override is active."}
        Research editorial brief: {research_editorial_brief}
        Format family plan: {format_family_plan}
        Content plan: {content_plan}
        Visual plan: {visual_plan}
        Format family rules: {format_family_rules}
        Visual knowledge brief: {visual_knowledge_brief}
        Visual grounding rules: {visual_grounding_rules}
        Research summary: {compiled_context.get("research_summary", "")}
        Resolution instructions: {compiled_context.get("resolution_instructions", "")}
        If follow-up mode is modify_previous, treat the prior creative as the base and only change what the user requested.
        If follow-up mode is variant_of_previous, preserve the prior strategic direction but create a meaningfully different option.
        If follow-up mode is variant_of_previous and a prior_layout_archetype is provided, do not reuse that same layout_archetype unless the user explicitly asked for the same layout.
        If follow-up mode is new_content, do not over-anchor on earlier outputs.
""".strip()

        user = f"""
        User prompt:
        {user_prompt}

        Brand copy brief:
        {json.dumps(brand_copy_brief, ensure_ascii=True)}

        Brand visual brief:
        {json.dumps(brand_visual_brief, ensure_ascii=True)}

        Audience brief:
        {json.dumps(audience_brief, ensure_ascii=True)}

        Knowledge brief:
        {json.dumps(knowledge_brief, ensure_ascii=True)}

        Visual knowledge brief:
        {json.dumps(visual_knowledge_brief, ensure_ascii=True)}

        Studio panel:
        {json.dumps(studio_panel, ensure_ascii=True)}

        Template fit brief:
        {json.dumps(template_fit_brief, ensure_ascii=True)}

        Render constraints:
        {json.dumps(render_constraints, ensure_ascii=True)}

        Session brief:
        {json.dumps(session_brief, ensure_ascii=True)}

        Reference asset brief:
        {json.dumps(reference_asset_brief, ensure_ascii=True)}

        Prompt intelligence brief:
        {json.dumps(prompt_intelligence_brief, ensure_ascii=True)}

        Content format brief:
        {json.dumps(content_format_brief, ensure_ascii=True)}

        Research editorial brief:
        {json.dumps(research_editorial_brief, ensure_ascii=True)}

        Format family plan:
        {json.dumps(format_family_plan, ensure_ascii=True)}

        Content plan:
        {json.dumps(content_plan, ensure_ascii=True)}

        Visual plan:
        {json.dumps(visual_plan, ensure_ascii=True)}

        Produce concise, brand-aligned copy that is safe for rendering.
        """.strip()
        return PromptEnvelope(system=system, user=user)

    def compose_creative_planning_envelope(
        self,
        *,
        user_prompt: str,
        compiled_context: dict[str, Any],
        studio_panel: dict[str, Any],
        validation_report: dict[str, Any] | None = None,
        replan_note: str | None = None,
    ) -> PromptEnvelope:
        brand_copy_brief = compiled_context.get("brand_copy_brief", {}) or {}
        brand_visual_brief = compiled_context.get("brand_visual_brief", {}) or {}
        audience_brief = compiled_context.get("audience_brief", {}) or {}
        visual_knowledge_brief = self._visual_knowledge_prompt_payload(compiled_context.get("visual_knowledge_brief"))
        visual_grounding_rules = self._visual_grounding_rule_block(
            fallback_sources=(
                "the approved brand visual brief, the user's topical anchor, allowed template/reference structure cues, "
                "and render constraints"
            ),
            output_targets="metadata.visual_direction, metadata.design_style, creative_decision, and scene_graph",
        )
        render_constraints = compiled_context.get("render_constraints", {}) or {}
        session_brief = compiled_context.get("session_brief", {}) or {}
        template_fit_brief = compiled_context.get("template_fit_brief", {}) or {}
        reference_asset_brief = compiled_context.get("reference_asset_brief", []) or []
        objective_brief = compiled_context.get("objective_brief", {}) or {}
        prompt_intelligence_brief = self._prompt_intelligence_prompt_payload(compiled_context.get("prompt_intelligence_brief"))
        content_format_brief = self._content_format_prompt_payload(compiled_context.get("content_format_brief"))
        research_editorial_brief = self._research_editorial_prompt_payload(compiled_context.get("research_editorial_brief"))
        format_family_plan = self._format_family_plan_prompt_payload(compiled_context.get("format_family_plan"))
        content_plan = self._content_plan_prompt_payload(compiled_context.get("content_plan"))
        visual_plan = self._visual_plan_prompt_payload(compiled_context.get("visual_plan"))
        prompt_intelligence_rules = self._prompt_intelligence_rule_block(
            output_targets="headline, body, CTA, supporting copy, proof points, and other text-bearing plan fields"
        )
        persona_depth_rules = self._persona_depth_rule_block()
        audience_research_rules = self._audience_research_rule_block()
        research_editorial_rules = self._research_editorial_rule_block()
        format_family_rules = self._format_family_rule_block()
        planning_contract_rules = self._planning_contract_rule_block()
        client_quality_rules = (
            self._client_quality_rule_block()
            if self._has_guide_scoped_client_quality_signals(content_format_brief)
            else ""
        )
        mistake_carousel_rules = (
            self._mistake_carousel_rule_block(prompt_name="user_prompt")
            if client_quality_rules and self._has_mistake_carousel_signals(user_prompt, content_format_brief)
            else ""
        )
        content_metadata_schema = self._content_metadata_schema_block()
        persuasion_metadata_rules = self._persuasion_metadata_rule_block()
        strategic_content_quality_rules = self._strategic_content_quality_rule_block()
        data_visualization_rules = self._data_visualization_rule_block()
        logo_overlay_rules = self._logo_overlay_rule_block()
        platform_preset = studio_panel.get("platform_preset")
        format_name = studio_panel.get("format")

        system = f"""
        You are Violyt's AI creative planning engine.
        You are the authoritative decision-maker for content structure, template use, layout synthesis, asset selection, and visual composition.
        The backend will validate and render your plan, but it must not invent the creative on your behalf.
        Think like a premium campaign art director, not a generic layout bot.
        Return JSON only with keys:
        - headline
        - body
        - cta
        - hashtags
        - metadata
        - creative_decision
        - scene_graph
        Metadata must be a JSON object and should include:
        {content_metadata_schema}
        Use empty strings or empty lists when a metadata field is unknown. Never return null for metadata keys.
        Persuasion metadata rules: {persuasion_metadata_rules}
        Strategic content quality rules: {strategic_content_quality_rules}
        Data visualization rules: {data_visualization_rules}
        Logo overlay rules: {logo_overlay_rules}
        Creative decision must include:
        - layout_mode
        - selected_template_id
        - confidence
        - reasoning
        - adaptations
        - asset_strategy
        If the brand has multiple logo variants and the composition clearly needs one, asset_strategy should include logo_variant.
        Valid logo_variant examples:
        - dark_on_light
        - light_on_dark
        - horizontal
        - stacked
        - icon_only
        - wordmark
        Scene graph must include:
        - canvas
        - layout_mode
        - confidence
        - layers
        - elements
        - styles
        - assets
        - template_adaptation
        - validation_hints
        Make the scene graph specific enough that a renderer can execute it without making creative choices.
        Use semantic element roles such as headline, supporting_line, body, proof_points, cta, logo, image, icon, decorative_shape, background, footer, legal.
        CRITICAL GEOMETRY REQUIREMENT: Every visible element MUST include complete normalized geometry with x, y, width, and height as floats between 0.0-1.0.
        The renderer cannot place elements without explicit coordinates. Do not rely on implicit positioning or anchor-only layouts.
        Normalized coordinates are relative to canvas dimensions: x=0 is left edge, x=1 is right edge, y=0 is top edge, y=1 is bottom edge.
        Respect brand guardrails over user prompts.
        For carousel planning, if the format or reference context implies a slide sequence, plan a real multi-slide narrative. Do not compress the concept into one poster body or one generic numbered-list summary.
        If you use numbered or labeled teaching units, each item must be a complete idea line that can stand on its own slide rather than a bare numeric fragment.
        For carousel planning, every slide headline must be topic-specific. Do not output generic sample grammar such as "Why this matters now", "What actually changed", "Why it matters beyond the headline", "What to do with this insight", "Key insight", or "The takeaway".
        For carousel planning, every slide visual_focus must be a concise natural-language visual direction tied to the slide's approved content and sample style. Never put a reference_image object, storage_path, filename, uploaded asset id, or unrelated reference title in visual_focus.
        Choose one dominant visual strategy and at most one supporting visual system:
        - image_led
        - template_led
        - asset_led
        - type_led
        Preserve the user's campaign topic. If the user asks about flights, travel, booking, pricing, or another specific subject, keep that subject visible in the final copy and scene graph.
        If brand alignment requires reframing, reinterpret the topic through the brand lens rather than replacing it with generic product messaging.
        Do not combine generated hero image, template background, reference icon system, and heavy decorative assets all at once.
        If you use a generated hero image, give it clean negative space and let supporting assets stay restrained.
        If you use a template, preserve its composition and do not request a competing hero image unless adaptation truly requires it.
        If a selected or recommended template contains baked-in text, reinterpret its style instead of overlaying new text on the flattened image.
        Do not place emoji, checkmark glyphs, symbol bullets, or decorative icon characters directly inside text fields.
        Never repeat the user's imperative instruction sentence verbatim inside the headline, body, supporting line, or CTA.
        Convert request phrasing like "create an engaging Instagram post" into audience-facing campaign copy.
        If the brand has an uploaded brand asset, include a brand_mark element but do not redraw, restyle, or spell out the brand name as a substitute for the actual brand asset.
        If the brand mark needs a specific variant, set creative_decision.asset_strategy.brand_mark_variant and mirror that in the brand_mark element asset.variant when practical.
        Make the brand mark element an overlay reservation with concrete corner geometry, style.fit=contain, metadata.brand_mark_position, and validation_hints.brand_mark_background_tone when that tone is clear.
        Avoid simplistic vertical icon stamp columns. If you use icons, integrate them into proof-point rows, cards, callouts, or a clearly composed visual system.
        If no validated brand fonts are provided, use generic typography roles such as heading_sans, body_sans, and cta_sans instead of inventing named font families.
        If validated brand fonts are available, only use those font families.
        If brand_visual_brief.design_system or its summary fields are present, use them as first-class layout guidance rather than ignoring them.
        Use brand_visual_brief.dominant_layout_family, preferred_zone_roles, and template_layout_dna or design_system.template_layout_dna to choose composition, approximate geometry, and scene_graph role structure.
        Use brand_visual_brief.hierarchy_summary to shape focal path, spacing rhythm, and density/whitespace.
        Use brand_visual_brief.content_structure_summary to decide whether the composition should read like a single-claim, comparison, steps, benefit-stack, or data-story visual.
        Use brand_visual_brief.visual_craft_summary and any structured visual_craft fields to control depth, rendering style, lighting, polish, and material feel rather than defaulting to flat generic stock imagery.
        Use brand_visual_brief.composition_logic_summary and any structured composition_logic fields to control balance, framing, and layering instead of generic centered poster composition.
        Use brand_visual_brief.subject_semantics_summary and any structured subject_semantics fields to choose the right scene type, subject matter, abstraction level, and finance objects.
        Use brand_visual_brief.motif_summary and brand_visual_brief.design_system motif signals only when they reinforce the topic; never force every motif into the composition.
        Use brand_visual_brief.image_treatment_summary to avoid generic portraits when the reference system implies diagrams, icon-led explainers, editorial compositions, or non-photo treatment.
        Use brand_visual_brief.brand_mark_position and background_style_summary to reserve the correct safe region and keep that surface calm.
        If template_fit_brief.template_editorial_dna, template_fit_brief.template_layout_dna, or template_fit_brief.sequence_pack are present, treat them as concrete sample-specific guidance for sequence rhythm, layout structure, and spatial pacing.
        For Instagram, LinkedIn, X, and other social creatives, do not return a sparse poster with only headline/body/cta unless the prompt explicitly asks for extreme minimalism.
        For social outputs, include a visibly structured composition with:
        - background
        - headline
        - supporting_line or body
        - cta
        - logo when the brand has one
        - at least one primary visual or decorative emphasis element such as image, icon, decorative_shape, or proof_points section
        If the concept includes multiple benefits, comparisons, or proof points, represent them as separate proof_points and/or icon elements instead of a single long body line.
        If creative_decision.asset_strategy mentions logo, icons, or a background element, the scene_graph must include matching elements for them.
        Favor premium editorial social compositions: strong hierarchy, purposeful spacing, one coherent hero area, and elegant brand accents.
        Avoid flat poster filler, random icon stamping, weak clip-art grids, or placeholder compositions.
        If follow-up_mode is variant_of_previous and session_brief.prior_layout_archetype is present, choose a materially different layout_archetype and composition rhythm from that prior archetype.
        If multiple approved uploaded images are available, choose only the strongest subset for the requested format and avoid forcing all of them into one cluttered composition.
        Platform preset: {platform_preset}
        Format: {format_name}
        File type: {studio_panel.get("file_type")}
        Platform guidance: {self.PLATFORM_GUIDANCE.get(platform_preset, "Keep the copy platform-appropriate.")}
        Format guidance: {self.FORMAT_GUIDANCE.get(format_name, "Keep the content structured and renderer-friendly.")}
        Copy brief: {brand_copy_brief}
        Audience brief: {audience_brief}
        Objective brief: {objective_brief}
        Visual brief: {brand_visual_brief}
        Template fit brief: {template_fit_brief}
        Render constraints: {render_constraints}
        Session brief: {session_brief}
        Reference asset brief: {reference_asset_brief}
        Prompt intelligence brief: {prompt_intelligence_brief}
        Content format brief: {content_format_brief}
        Prompt intelligence rules: {prompt_intelligence_rules}
        Persona depth rules: {persona_depth_rules}
        Audience research rules: {audience_research_rules}
        Research-editorial rules: {research_editorial_rules}
        Planning contract rules: {planning_contract_rules}
        Client quality rules: {client_quality_rules or "No client-specific quality overrides are active."}
        Mistake-style carousel rules: {mistake_carousel_rules or "No mistake-specific carousel override is active."}
        Research editorial brief: {research_editorial_brief}
        Format family plan: {format_family_plan}
        Content plan: {content_plan}
        Visual plan: {visual_plan}
        Format family rules: {format_family_rules}
        Visual knowledge brief: {visual_knowledge_brief}
        Visual grounding rules: {visual_grounding_rules}
        Validation report to repair against: {validation_report or {}}
        If validation report issues are present, repair the scene graph rather than restating the same plan.
        {replan_note or ""}
        Match copy density to the requested format and platform. Do not flatten carousel or infographic thinking into a static poster.
        Do not return markdown or explanations outside JSON.
        """.strip()

        user = f"""
        User prompt:
        {user_prompt}

        Brand copy brief:
        {json.dumps(brand_copy_brief, ensure_ascii=True)}

        Brand visual brief:
        {json.dumps(brand_visual_brief, ensure_ascii=True)}

        Audience brief:
        {json.dumps(audience_brief, ensure_ascii=True)}

        Objective brief:
        {json.dumps(objective_brief, ensure_ascii=True)}

        Template candidates and fit:
        {json.dumps(template_fit_brief, ensure_ascii=True)}

        Reference assets:
        {json.dumps(reference_asset_brief, ensure_ascii=True)}

        Prompt intelligence brief:
        {json.dumps(prompt_intelligence_brief, ensure_ascii=True)}

        Content format brief:
        {json.dumps(content_format_brief, ensure_ascii=True)}

        Research editorial brief:
        {json.dumps(research_editorial_brief, ensure_ascii=True)}

        Format family plan:
        {json.dumps(format_family_plan, ensure_ascii=True)}

        Content plan:
        {json.dumps(content_plan, ensure_ascii=True)}

        Visual plan:
        {json.dumps(visual_plan, ensure_ascii=True)}

        Visual knowledge brief:
        {json.dumps(visual_knowledge_brief, ensure_ascii=True)}

        Studio panel:
        {json.dumps(studio_panel, ensure_ascii=True)}

        Render constraints:
        {json.dumps(render_constraints, ensure_ascii=True)}

        Session brief:
        {json.dumps(session_brief, ensure_ascii=True)}

        Validation report:
        {json.dumps(validation_report or {}, ensure_ascii=True)}

        Replan instruction:
        {replan_note or ""}
        """.strip()
        return PromptEnvelope(system=system, user=user)

    def compose_message_strategy_envelope(
        self,
        *,
        user_prompt: str,
        compiled_context: dict[str, Any],
        studio_panel: dict[str, Any],
    ) -> PromptEnvelope:
        brand_copy_brief = compiled_context.get("brand_copy_brief", {}) or {}
        audience_brief = compiled_context.get("audience_brief", {}) or {}
        objective_brief = compiled_context.get("objective_brief", {}) or {}
        knowledge_brief = compiled_context.get("knowledge_brief", []) or []
        session_brief = compiled_context.get("session_brief", {}) or {}
        prompt_intelligence_brief = self._prompt_intelligence_prompt_payload(compiled_context.get("prompt_intelligence_brief"))
        content_format_brief = self._content_format_prompt_payload(compiled_context.get("content_format_brief"))
        research_editorial_brief = self._research_editorial_prompt_payload(compiled_context.get("research_editorial_brief"))
        format_family_plan = self._format_family_plan_prompt_payload(compiled_context.get("format_family_plan"))
        prompt_intelligence_rules = self._prompt_intelligence_rule_block(
            output_targets="message framing, hook style, supporting copy direction, CTA intent, and important keywords"
        )
        persona_depth_rules = self._persona_depth_rule_block()
        audience_research_rules = self._audience_research_rule_block()
        research_editorial_rules = self._research_editorial_rule_block()
        format_family_rules = self._format_family_rule_block()
        client_quality_rules = (
            self._client_quality_rule_block()
            if self._has_guide_scoped_client_quality_signals(content_format_brief)
            else ""
        )
        mistake_carousel_rules = (
            self._mistake_carousel_rule_block(prompt_name="user_prompt")
            if client_quality_rules and self._has_mistake_carousel_signals(user_prompt, content_format_brief)
            else ""
        )
        system = f"""
        You are a senior brand content strategist for {brand_copy_brief.get("brand_name") or "the brand"}.
        Your responsibility is to retrieve, interpret, and synthesize the core message and content direction for a branded marketing creative using ONLY the compiled brand, audience, objective, session, and knowledge context provided.
        Follow these non-negotiable rules:
        1. Retrieve and synthesize ONLY message and communication direction aligned to the provided brand context.
        2. Every field must reflect the emotion: {brand_copy_brief.get("primary_emotion")}.
        3. Never include wording, themes, or claims that trigger the avoided emotion: {brand_copy_brief.get("avoided_emotion")}.
        4. All output must serve the objective: {objective_brief.get("name")} and align with the brand foundations: {brand_copy_brief.get("brand_foundations")}.
        5. Apply these behavioral guardrails at all times: {brand_copy_brief.get("dos", [])}.
        6. Apply these hard restrictions with no exceptions: {brand_copy_brief.get("donts", [])}.
        7. Focus only on communication, message, framing, and content direction.
        8. Do not generate visual design guidance.
        9. Do not generate colors, layout, typography, or scene-graph instructions.
        10. Do not invent unsupported claims.
        11. Do not generate the final image prompt.
        12. If a field is unavailable, return exactly "MISSING".
        13. Preserve the user's topical anchor. Do not silently replace the requested subject with a different campaign topic.
        14. If brand alignment requires reframing, reinterpret the user's topic through the brand lens instead of discarding it.
        15. {prompt_intelligence_rules}
        16. {persona_depth_rules}
        17. {audience_research_rules}
        18. Keep messaging audience-facing, not internal, descriptive, or process-oriented.
        19. Preserve the core idea instead of diluting it into generic brand-safe filler.
        20. When a selected sample/reference carousel provides per-slide sample_page_headline, sample_page_supporting, sample_page_copy, headline_hint, or sequence_summary, use that as the editorial authority for hook style, curiosity level, insight depth, and close grammar. Do not let generic brand positioning or CTA intent override a sample that is interpretive, analytical, or macro-takeaway led.
        21. If the sample's wording uses curiosity, urgency, undercovered-angle, or smart-reader framing, do not add those techniques to what_must_be_avoided_in_messaging unless a hard brand guardrail explicitly forbids them.
        22. Keep the message strategy creative and brand-native. It should define audience tension, angle, promise, and payoff, not produce a research-paper thesis or a list of source notes.
        23. For a style_reference_only carousel, the selected sample sequence is the story model. Match its slide count, per-slide editorial jobs, and final-slide grammar. If the selected sample closes with a macro takeaway, strategic signal, or editorial conclusion, cta_intent must not become product/platform/investment promotion unless the user explicitly requested a product CTA.
        24. Convert research into an audience-facing creative angle: curiosity hook, specific mechanics, undercovered insight, and strategic payoff. Do not make the strategy sound like a source memo, literature review, or compliance note.
        Return JSON only with keys:
        - primary_campaign_theme
        - core_audience_message
        - headline_direction
        - supporting_copy_direction
        - cta_intent
        - key_value_proposition
        - important_keywords
        - emotional_messaging_direction
        - what_must_be_avoided_in_messaging
        Platform preset: {studio_panel.get("platform_preset")}
        Format: {studio_panel.get("format")}
        Prompt intelligence brief: {prompt_intelligence_brief}
        Content format brief: {content_format_brief}
        Research editorial brief: {research_editorial_brief}
        Research-editorial rules: {research_editorial_rules}
        Format family plan: {format_family_plan}
        Format family rules: {format_family_rules}
        Client quality rules: {client_quality_rules or "No client-specific quality overrides are active."}
        Mistake-style carousel rules: {mistake_carousel_rules or "No mistake-specific carousel override is active."}
        """.strip()
        user = f"""
        User prompt:
        {user_prompt}

        Brand copy brief:
        {json.dumps(brand_copy_brief, ensure_ascii=True)}

        Audience brief:
        {json.dumps(audience_brief, ensure_ascii=True)}

        Objective brief:
        {json.dumps(objective_brief, ensure_ascii=True)}

        Knowledge brief:
        {json.dumps(knowledge_brief, ensure_ascii=True)}

        Prompt intelligence brief:
        {json.dumps(prompt_intelligence_brief, ensure_ascii=True)}

        Content format brief:
        {json.dumps(content_format_brief, ensure_ascii=True)}

        Research editorial brief:
        {json.dumps(research_editorial_brief, ensure_ascii=True)}

        Format family plan:
        {json.dumps(format_family_plan, ensure_ascii=True)}

        Session brief:
        {json.dumps(session_brief, ensure_ascii=True)}
        """.strip()
        return PromptEnvelope(system=system, user=user)

    def compose_image_led_social_envelope(
        self,
        *,
        user_prompt: str,
        compiled_context: dict[str, Any],
        studio_panel: dict[str, Any],
        message_strategy: dict[str, Any],
        validation_report: dict[str, Any] | None = None,
        replan_note: str | None = None,
    ) -> PromptEnvelope:
        brand_copy_brief = compiled_context.get("brand_copy_brief", {}) or {}
        brand_visual_brief = compiled_context.get("brand_visual_brief", {}) or {}
        audience_brief = compiled_context.get("audience_brief", {}) or {}
        visual_knowledge_brief = self._visual_knowledge_prompt_payload(compiled_context.get("visual_knowledge_brief"))
        visual_grounding_rules = self._visual_grounding_rule_block(
            fallback_sources=(
                "message_strategy, the approved brand visual brief, the user's topical anchor, allowed template/reference "
                "structure cues, and render constraints"
            ),
            output_targets="metadata.visual_direction, metadata.design_style, creative_decision, and scene_graph",
        )
        render_constraints = compiled_context.get("render_constraints", {}) or {}
        session_brief = compiled_context.get("session_brief", {}) or {}
        template_fit_brief = compiled_context.get("template_fit_brief", {}) or {}
        reference_asset_brief = compiled_context.get("reference_asset_brief", []) or []
        objective_brief = compiled_context.get("objective_brief", {}) or {}
        prompt_intelligence_brief = self._prompt_intelligence_prompt_payload(compiled_context.get("prompt_intelligence_brief"))
        content_format_brief = self._content_format_prompt_payload(compiled_context.get("content_format_brief"))
        research_editorial_brief = self._research_editorial_prompt_payload(compiled_context.get("research_editorial_brief"))
        format_family_plan = self._format_family_plan_prompt_payload(compiled_context.get("format_family_plan"))
        content_plan = self._content_plan_prompt_payload(compiled_context.get("content_plan"))
        visual_plan = self._visual_plan_prompt_payload(compiled_context.get("visual_plan"))
        prompt_intelligence_rules = self._prompt_intelligence_rule_block(
            output_targets="headline, body, CTA, supporting copy, proof points, and other overlay text fields"
        )
        persona_depth_rules = self._persona_depth_rule_block()
        audience_research_rules = self._audience_research_rule_block()
        research_editorial_rules = self._research_editorial_rule_block()
        format_family_rules = self._format_family_rule_block()
        planning_contract_rules = self._planning_contract_rule_block()
        client_quality_rules = (
            self._client_quality_rule_block()
            if self._has_guide_scoped_client_quality_signals(content_format_brief)
            else ""
        )
        mistake_carousel_rules = (
            self._mistake_carousel_rule_block(prompt_name="user_prompt")
            if client_quality_rules and self._has_mistake_carousel_signals(user_prompt, content_format_brief)
            else ""
        )
        content_metadata_schema = self._content_metadata_schema_block()
        persuasion_metadata_rules = self._persuasion_metadata_rule_block()
        logo_overlay_rules = self._logo_overlay_rule_block()
        system = f"""
        You are Violyt's premium social creative planning engine.
        You are designing an image-led branded social creative where the image model is responsible for the finished readable slide composition, while the backend only applies non-generative finishing such as the exact stored logo asset and export-safe compositing.
        Return JSON only with keys:
        - headline
        - body
        - cta
        - hashtags
        - metadata
        - creative_decision
        - scene_graph
        Metadata must be a JSON object and should include:
        {content_metadata_schema}
        Use empty strings or empty lists when a metadata field is unknown. Never return null for metadata keys.
        Persuasion metadata rules: {persuasion_metadata_rules}
        Logo overlay rules: {logo_overlay_rules}
        This mode is image-led. Prefer one unified hero visual with calm negative space for overlays.
        Do not ask the backend to invent the composition. Your scene_graph must define the overlay plan precisely.
        Preserve the user's campaign topic. If the user asks about travel, flights, booking, pricing, or another specific theme, keep that theme visible instead of replacing it with generic product copy.
        The scene_graph should normally contain:
        - background
        - one primary image element that acts as the hero visual (must use valid roles like 'image' or 'hero_visual')
        - headline
        - supporting_line and/or body
        - cta
        - corner_safe_zone
        - at most one restrained decorative_shape system if it helps the composition
        CRITICAL ROLE ENFORCEMENT: Even if adapting a complex multi-module sample template, you MUST ONLY use standard allowed schema roles (headline, body, image, icon, background, corner_safe_zone, cta, decorative_shape). DO NOT invent custom role names like 'slide_1_hero_image' or 'card_image'.
        CRITICAL TEXT ENFORCEMENT: Every layout MUST contain at least one 'headline' and 'body' or 'supporting_line' element in the scene_graph elements array, even if the reference template consists mostly of images or cards.
        The backend will overlay the real uploaded brand asset. Do not redraw, restyle, spell out, or fake the brand mark in text.
        If the composition needs a specific brand mark variant, request it explicitly in creative_decision.asset_strategy.brand_mark_variant and optionally mirror it in the element asset.variant.
        The corner_safe_zone element must describe an overlay reservation, not generated artwork: use concrete corner geometry, style.fit=contain, metadata.brand_mark_position, and validation_hints.brand_mark_background_tone when the surface tone is obvious.
        CRITICAL: Never use the word 'logo', 'watermark', or 'brandmark' in metadata.image_prompt, metadata.visual_direction, or metadata.design_style, as it causes severe hallucinations. Use 'empty reserved corner' instead if you must refer to the space.
        Use templates only when they are clean and safely editable. Flattened or text-heavy templates must be treated as style references, not direct text-overlay surfaces.
        If follow-up_mode is variant_of_previous and session_brief.prior_layout_archetype is present, choose a noticeably different layout_archetype from the prior creative.
        If multiple approved uploaded images are available, choose only the strongest subset for the format instead of forcing every image into the same layout.
        For social creatives, do not produce stamped icon columns, clip-art checklists, fake infographic stickers, or crowded poster mosaics.
        If proof points are needed, keep them short and elegant; the scene graph should still feel like one premium campaign visual.
        REFERENCE IMAGE USAGE: If multiple reference images are available in the reference_asset_brief and the format is carousel, bind one reference image per slide by setting element.asset.storage_path to the reference image's storage path. Each carousel slide should leverage one of the available reference images to create a cohesive visual narrative.
        Use brand fonts only if they are validated and available. Otherwise use generic roles such as heading_sans, body_sans, and cta_sans.
        If brand_visual_brief.design_system or its summary fields are present, use them as first-class visual direction rather than generic defaults.
        Use brand_visual_brief.dominant_layout_family, preferred_zone_roles, and template_layout_dna or design_system.template_layout_dna to define the overlay layout and safe visual/text regions.
        Use brand_visual_brief.hierarchy_summary to control focal emphasis, spacing rhythm, and whitespace.
        Use brand_visual_brief.content_structure_summary to decide whether the image-led composition should feel like a single claim, comparison, steps, benefit-stack, or data-story surface.
        Use brand_visual_brief.visual_craft_summary and any structured visual_craft fields to choose depth, rendering style, lighting, polish, and material feel for the hero scene.
        Use brand_visual_brief.composition_logic_summary and any structured composition_logic fields to control balance, framing, and layering instead of generic centered poster framing.
        Use brand_visual_brief.subject_semantics_summary and any structured subject_semantics fields to choose the right scene type, subject matter, abstraction level, and finance objects.
        Use brand_visual_brief.motif_summary only when the motif naturally supports the topic.
        Use brand_visual_brief.image_treatment_summary to avoid generic business-person imagery when the brand references imply diagram-led, icon-led, editorial, or abstract treatment.
        Use brand_visual_brief.brand_mark_position and background_style_summary to reserve the correct corner_safe_zone on a calm surface.
        If template_fit_brief.template_editorial_dna, template_fit_brief.template_layout_dna, or template_fit_brief.sequence_pack are present, treat them as concrete sample-specific guidance for sequence rhythm, layout structure, and spatial pacing.
        {replan_note or ""}
        creative_decision must include:
        - layout_mode
        - selected_template_id
        - confidence
        - reasoning
        - adaptations
        - asset_strategy
        If the brand has multiple brand mark variants and the composition clearly needs one, asset_strategy should include brand_mark_variant such as dark_on_light, light_on_dark, horizontal, stacked, icon_only, or wordmark.
        asset_strategy must keep one dominant visual system. For this mode, prefer generated_image as dominant_visual_system, with type_led as an optional supporting system.
        scene_graph must include:
        - canvas
        - layout_mode
        - confidence
        - layers
        - elements
        - styles
        - assets
        - template_adaptation
        - validation_hints
        Make the image element large and dominant, then place overlay zones for text/logo with clear spacing and brand-safe hierarchy.
        Keep copy concise and premium.
        If template_fit_brief.sequence_pack.surface_policy is style_reference_only and its slides include sample_page_headline, sample_page_supporting, sample_page_copy, sample_page_editorial_role, sample_page_copy_behavior, sample_page_copy_density, sample_page_closing_grammar, headline_hint, or sequence_summary, use the selected sample's editorial grammar as the slide-copy authority. Match the sample's hook strength, undercovered-angle logic, insight density, and closing grammar while replacing only facts that do not belong to the user's topic.
        Do not summarize the topic when the sample interprets it. Generate non-obvious, researched, audience-aware slide beats that answer why the topic matters, what most people missed, and what strategic pattern it signals when the sample uses that structure.
        Do not turn the final slide into brand/platform promotion unless the user asks for promotion or the sample final slide is itself a CTA/product surface.
        Write like a brand strategist making a premium creative: memorable headline, compact insight modules, strategic implication, and visual copy that can sit on a designed slide. Do not write like a research paper writer; avoid essay paragraphs, bibliography-like source mentions, and generic "verified facts" filler.
        Validation report to repair against: {validation_report or {}}
        Brand copy brief: {brand_copy_brief}
        Brand visual brief: {brand_visual_brief}
        Audience brief: {audience_brief}
        Objective brief: {objective_brief}
        Template fit brief: {template_fit_brief}
        Render constraints: {render_constraints}
        Session brief: {session_brief}
        Reference asset brief: {reference_asset_brief}
        Prompt intelligence brief: {prompt_intelligence_brief}
        Content format brief: {content_format_brief}
        Prompt intelligence rules: {prompt_intelligence_rules}
        Persona depth rules: {persona_depth_rules}
        Audience research rules: {audience_research_rules}
        Research-editorial rules: {research_editorial_rules}
        Planning contract rules: {planning_contract_rules}
        Client quality rules: {client_quality_rules or "No client-specific quality overrides are active."}
        Mistake-style carousel rules: {mistake_carousel_rules or "No mistake-specific carousel override is active."}
        Research editorial brief: {research_editorial_brief}
        Format family plan: {format_family_plan}
        Content plan: {content_plan}
        Visual plan: {visual_plan}
        Format family rules: {format_family_rules}
        Visual knowledge brief: {visual_knowledge_brief}
        Visual grounding rules: {visual_grounding_rules}
        """.strip()
        user = f"""
        User prompt:
        {user_prompt}

        Message strategy:
        {json.dumps(message_strategy, ensure_ascii=True)}

        Brand visual brief:
        {json.dumps(brand_visual_brief, ensure_ascii=True)}

        Template fit brief:
        {json.dumps(template_fit_brief, ensure_ascii=True)}

        Reference asset brief:
        {json.dumps(reference_asset_brief, ensure_ascii=True)}
        """

        # Add explicit reference image paths for carousel usage
        format_name = studio_panel.get("format", "").strip().lower()
        if reference_asset_brief and isinstance(reference_asset_brief, list) and len(reference_asset_brief) > 0:
            if format_name in ("carousel", "instagram_carousel", "linkedin_carousel"):
                reference_image_assets = [
                    ref_asset
                    for ref_asset in reference_asset_brief
                    if isinstance(ref_asset, dict)
                    and str(ref_asset.get("role") or "").strip().casefold() not in {"logo", "logo_variant"}
                    and str(
                        ref_asset.get("storage_path")
                        or ref_asset.get("path")
                        or ref_asset.get("asset_url")
                        or ""
                    ).strip()
                ]
                target_slide_count = 0
                if isinstance(template_fit_brief, dict):
                    sequence_pack = template_fit_brief.get("sequence_pack")
                    editorial_dna = template_fit_brief.get("template_editorial_dna")
                    if isinstance(sequence_pack, dict):
                        target_slide_count = int(sequence_pack.get("slide_count") or 0) or target_slide_count
                    if isinstance(editorial_dna, dict):
                        target_slide_count = int(editorial_dna.get("page_count_hint") or 0) or target_slide_count
                target_slide_count = target_slide_count or int(studio_panel.get("slide_count") or 0) or 0
                if target_slide_count <= 0 and isinstance(content_format_brief, dict):
                    target_slide_count = int(content_format_brief.get("preferred_slide_count") or 0) or 0
                target_slide_count = max(target_slide_count, 1)
                user += f"\n\nREFERENCE IMAGES AVAILABLE FOR CAROUSEL: {len(reference_image_assets)} usable images"
                user += "\n\nCRITICAL IMAGE BINDING REQUIREMENT:"
                user += (
                    f"\nFor this carousel, bind at most one dominant reference image per slide and choose the strongest subset for the {target_slide_count} slides."
                )
                user += "\nEach hero_visual that uses a reference MUST have a real storage_path field pointing to one of these usable reference image paths."
                user += "\nDO NOT use storage_path: 'unknown' or null. If a reference is not suitable for a slide, leave that slide generated rather than inventing fake paths."
                user += "\nPrefer slide-role relevance over raw quantity: opening-hook references for slide 1, structural/data references for middle slides, and product or decision-support references for the closing slide when available."
                user += "\n\nAvailable reference image storage paths:"
                for i, ref_asset in enumerate(reference_image_assets[:8], 1):
                    if isinstance(ref_asset, dict):
                        storage_path = (
                            ref_asset.get("storage_path")
                            or ref_asset.get("path")
                            or ref_asset.get("asset_url")
                            or "unknown"
                        )
                        caption = ref_asset.get("caption") or ref_asset.get("name") or ref_asset.get("label") or ""
                        user += f"\n  {i}. storage_path: '{storage_path}'" + (f" — {caption[:60]}" if caption else "")

        user += f"""

        Render constraints:
        {json.dumps(render_constraints, ensure_ascii=True)}

        Prompt intelligence brief:
        {json.dumps(prompt_intelligence_brief, ensure_ascii=True)}

        Content format brief:
        {json.dumps(content_format_brief, ensure_ascii=True)}

        Research editorial brief:
        {json.dumps(research_editorial_brief, ensure_ascii=True)}

        Format family plan:
        {json.dumps(format_family_plan, ensure_ascii=True)}

        Content plan:
        {json.dumps(content_plan, ensure_ascii=True)}

        Visual plan:
        {json.dumps(visual_plan, ensure_ascii=True)}

        Visual knowledge brief:
        {json.dumps(visual_knowledge_brief, ensure_ascii=True)}

        Studio panel:
        {json.dumps(studio_panel, ensure_ascii=True)}

        Validation report:
        {json.dumps(validation_report or {}, ensure_ascii=True)}

        Replan instruction:
        {replan_note or ""}
        """.strip()
        return PromptEnvelope(system=system, user=user)

    def compose_scene_graph_repair_envelope(
        self,
        *,
        user_prompt: str,
        compiled_context: dict[str, Any],
        studio_panel: dict[str, Any],
        current_scene_graph: dict[str, Any],
        creative_decision: dict[str, Any],
        validation_report: dict[str, Any],
        repair_quality_history: list[float] | None = None,
    ) -> PromptEnvelope:
        prompt_intelligence_brief = self._prompt_intelligence_prompt_payload(compiled_context.get("prompt_intelligence_brief"))
        content_format_brief = self._content_format_prompt_payload(compiled_context.get("content_format_brief"))
        research_editorial_brief = self._research_editorial_prompt_payload(compiled_context.get("research_editorial_brief"))
        format_family_plan = self._format_family_plan_prompt_payload(compiled_context.get("format_family_plan"))
        content_plan = self._content_plan_prompt_payload(compiled_context.get("content_plan"))
        visual_plan = self._visual_plan_prompt_payload(compiled_context.get("visual_plan"))
        prompt_intelligence_rules = self._prompt_intelligence_rule_block(
            output_targets="any repaired text-bearing fields, proof points, CTA language, and messaging hierarchy"
        )
        research_editorial_rules = self._research_editorial_rule_block()
        format_family_rules = self._format_family_rule_block()
        planning_contract_rules = self._planning_contract_rule_block()
        client_quality_rules = (
            self._client_quality_rule_block()
            if self._has_guide_scoped_client_quality_signals(content_format_brief)
            else ""
        )
        mistake_carousel_rules = (
            self._mistake_carousel_rule_block(prompt_name="user_prompt")
            if client_quality_rules and self._has_mistake_carousel_signals(user_prompt, content_format_brief)
            else ""
        )
        logo_overlay_rules = self._logo_overlay_rule_block()
        system = f"""
        You are Violyt's scene-graph repair engine.
        Return JSON only with keys: creative_decision, scene_graph.
        Keep the creative intent intact while repairing the reported violations.
        Do not rewrite content unless required by the validation report.
        The backend renderer will follow your scene graph directly, so provide concrete geometry and styling decisions.
        Do not leave the scene graph sparse.
        Preserve the user's topical anchor while repairing. Do not swap the requested subject for a different campaign theme.
        Convert inline bullet or emoji-like text into structured proof_points or icon-supported sections when required by the validation report.
        If the validation report requires a brand mark, include a visible corner_safe_zone element.
        If the validation report suggests a brand mark mismatch, request the right brand mark variant using creative_decision.asset_strategy.brand_mark_variant.
        Repair corner_safe_zone reservations by using concrete corner geometry, style.fit=contain, and a quiet low-texture surface that matches validation_hints.brand_mark_background_tone when present.
        Reduce visual-system overload: choose a clearer dominant visual strategy instead of mixing every possible asset type.
        If brand fonts are unavailable, use generic typography roles instead of inventing specific font families.
        Repair icon stamp columns by converting them into cards, proof rows, or more integrated callout structures.
        Do not repair a carousel or infographic into a sparse static poster. Keep the repaired hierarchy true to the requested format.
        When repairing a style_reference_only carousel with a selected sample/reference sequence, preserve the sample page's editorial grammar and do not introduce unrelated reusable/reference asset names, product surfaces, or promotional CTAs that are absent from the selected sample page.
        For style_reference_only carousel repair, the selected sample/reference sequence is the only allowed reusable visual family. Do not bind, mention, or copy asset names, storage paths, product surfaces, dashboards, or template titles from any other reference asset. If an unrelated asset seems useful, leave the element generated and describe only the sample-matched visual grammar.
        If the selected sample page does not visibly use a dashboard, chart, table, trading screen, laptop, or product UI, do not add those surfaces during repair even when the topic has financial or economic facts.
        If compiled_context.brand_visual_brief.design_system or its summary fields are present, use them to repair toward the brand's actual layout family, hierarchy, content structure, motif usage, image treatment, visual craft, composition logic, subject semantics, and logo placement instead of generic fallback structure.
        Use brand_visual_brief.hierarchy_summary and content_structure_summary to restore focal path and structural pacing when validation says the graph is sparse or underdesigned.
        Use brand_visual_brief.visual_craft_summary, composition_logic_summary, and subject_semantics_summary to restore premium depth, framing, and topic-specific scene selection when the graph feels generic.
        Use brand_visual_brief.brand_mark_position and background_style_summary to repair corner_safe_zone reservations on the correct surface.
        If you must adjust text-bearing elements during repair, {prompt_intelligence_rules}
        {logo_overlay_rules}
        Prompt intelligence brief: {prompt_intelligence_brief}
        Content format brief: {content_format_brief}
        Research editorial brief: {research_editorial_brief}
        Research-editorial rules: {research_editorial_rules}
        Format family plan: {format_family_plan}
        Content plan: {content_plan}
        Visual plan: {visual_plan}
        Format family rules: {format_family_rules}
        Planning contract rules: {planning_contract_rules}
        Client quality rules: {client_quality_rules or "No client-specific quality overrides are active."}
        Mistake-style carousel rules: {mistake_carousel_rules or "No mistake-specific carousel override is active."}
        """.strip()
        user = f"""
        User prompt:
        {user_prompt}

        Current creative decision:
        {json.dumps(creative_decision, ensure_ascii=True)}

        Current scene graph:
        {json.dumps(current_scene_graph, ensure_ascii=True)}

        Studio panel:
        {json.dumps(studio_panel, ensure_ascii=True)}

        Compiled context:
        {json.dumps(compiled_context, ensure_ascii=True)}

        Format family plan:
        {json.dumps(format_family_plan, ensure_ascii=True)}

        Content plan:
        {json.dumps(content_plan, ensure_ascii=True)}

        Visual plan:
        {json.dumps(visual_plan, ensure_ascii=True)}

        Validation report:
        {json.dumps(validation_report, ensure_ascii=True)}
        """

        # Add quality history if available
        if repair_quality_history and len(repair_quality_history) > 0:
            quality_history_str = " → ".join(f"{q:.2f}" for q in repair_quality_history)
            user += f"\n\nQuality score history: {quality_history_str}"
            user += "\n\nIMPORTANT: Previous repair attempt(s) may have degraded quality. Focus on fixing validation errors without breaking working elements. Be conservative and surgical in your repairs."

        user = user.strip()
        return PromptEnvelope(system=system, user=user)

    def compose_rewrite_envelope(
        self,
        *,
        original_prompt: str,
        rewrite_instruction: str,
        current_payload: dict[str, Any],
        compiled_context: dict[str, Any],
        message_strategy: dict[str, Any],
        tone_analysis: dict[str, Any],
        rewrite_field_plan: dict[str, Any],
        studio_panel: dict[str, Any],
        targeted_fields: list[str] | None = None,
        revision_scope: dict[str, Any] | None = None,
    ) -> PromptEnvelope:
        brand_copy_brief = compiled_context.get("brand_copy_brief", {}) or {}
        audience_brief = compiled_context.get("audience_brief", {}) or {}
        objective_brief = compiled_context.get("objective_brief", {}) or {}
        knowledge_brief = compiled_context.get("knowledge_brief", []) or []
        template_fit_brief = compiled_context.get("template_fit_brief", {}) or {}
        render_constraints = compiled_context.get("render_constraints", {}) or {}
        session_brief = compiled_context.get("session_brief", {}) or {}
        prompt_intelligence_brief = self._prompt_intelligence_prompt_payload(compiled_context.get("prompt_intelligence_brief"))
        content_format_brief = self._content_format_prompt_payload(compiled_context.get("content_format_brief"))
        research_editorial_brief = self._research_editorial_prompt_payload(compiled_context.get("research_editorial_brief"))
        format_family_plan = self._format_family_plan_prompt_payload(compiled_context.get("format_family_plan"))
        content_plan = self._content_plan_prompt_payload(compiled_context.get("content_plan"))
        visual_plan = self._visual_plan_prompt_payload(compiled_context.get("visual_plan"))
        prompt_intelligence_rules = self._prompt_intelligence_rule_block(
            output_targets="rewritten headline, body, CTA, supporting line, proof points, objection handling, trust builders, and claim/evidence pairs"
        )
        persona_depth_rules = self._persona_depth_rule_block()
        audience_research_rules = self._audience_research_rule_block()
        research_editorial_rules = self._research_editorial_rule_block()
        format_family_rules = self._format_family_rule_block()
        planning_contract_rules = self._planning_contract_rule_block()
        client_quality_rules = (
            self._client_quality_rule_block()
            if self._has_guide_scoped_client_quality_signals(content_format_brief)
            else ""
        )
        mistake_carousel_rules = (
            self._mistake_carousel_rule_block(prompt_name="original_prompt")
            if client_quality_rules and self._has_mistake_carousel_signals(original_prompt, content_format_brief)
            else ""
        )
        content_metadata_schema = self._content_metadata_schema_block()
        persuasion_metadata_rules = self._persuasion_metadata_rule_block()
        targeted_field_list = ", ".join(targeted_fields or ["headline", "body", "cta"])
        rewrite_context_payload = {
            "brand_copy_brief": brand_copy_brief,
            "audience_brief": audience_brief,
            "objective_brief": objective_brief,
            "template_fit_brief": template_fit_brief,
            "render_constraints": render_constraints,
            "session_brief": session_brief,
            "prompt_intelligence_brief": prompt_intelligence_brief,
            "content_format_brief": content_format_brief,
            "research_editorial_brief": research_editorial_brief,
            "format_family_plan": format_family_plan,
            "content_plan": content_plan,
            "visual_plan": visual_plan,
            "knowledge_brief": knowledge_brief,
        }
        system = f"""
        You are Violyt's structured rewrite engine.
        This is a rewrite of existing structured content, not a fresh campaign brief.
        Return JSON only with keys:
        - headline
        - body
        - cta
        - hashtags
        - metadata
        Metadata must be a JSON object and should include:
        {content_metadata_schema}
        Use empty strings or empty lists when a metadata field is unknown. Never return null for metadata keys.
        Persuasion metadata rules: {persuasion_metadata_rules}
        Rewrite only the targeted fields that actually need changes: {targeted_field_list}.
        Revision scope: {json.dumps(revision_scope or {}, ensure_ascii=True)}
        Preserve the current campaign surface, template-fit assumptions, and brand-safe messaging unless the rewrite instruction explicitly changes them.
        Do not invent a new campaign angle, template, layout system, scene graph, or visual plan.
        Do not echo the rewrite instruction back as audience-facing copy.
        Keep proof, trust, objection handling, and claim/evidence support grounded in the compiled audience and research context.
        Match rewritten density to the requested format instead of enforcing one universal brevity rule.
        Apply these rules while rewriting:
        - {prompt_intelligence_rules}
        - {persona_depth_rules}
        - {audience_research_rules}
        - {research_editorial_rules}
        - {format_family_rules}
        - {planning_contract_rules}
        - {client_quality_rules or "No client-specific quality overrides are active."}
        - {mistake_carousel_rules or "No mistake-specific carousel override is active."}
        Platform preset: {studio_panel.get("platform_preset")}
        Format: {studio_panel.get("format")}
        File type: {studio_panel.get("file_type")}
        Format family plan: {format_family_plan}
        Content plan: {content_plan}
        Visual plan: {visual_plan}
        Format family rules: {format_family_rules}
        Planning contract rules: {planning_contract_rules}
        """.strip()
        user = f"""
        Original user prompt:
        {original_prompt}

        Rewrite instruction:
        {rewrite_instruction}

        Targeted fields:
        {json.dumps(targeted_fields or ["headline", "body", "cta"], ensure_ascii=True)}

        Revision scope:
        {json.dumps(revision_scope or {}, ensure_ascii=True)}

        Current structured content:
        {json.dumps(current_payload, ensure_ascii=True)}

        Current message strategy:
        {json.dumps(message_strategy, ensure_ascii=True)}

        Current tone QA:
        {json.dumps(tone_analysis, ensure_ascii=True)}

        Field rewrite plan:
        {json.dumps(rewrite_field_plan, ensure_ascii=True)}

        Compiled rewrite context:
        {json.dumps(rewrite_context_payload, ensure_ascii=True)}

        Format family plan:
        {json.dumps(format_family_plan, ensure_ascii=True)}

        Content plan:
        {json.dumps(content_plan, ensure_ascii=True)}

        Visual plan:
        {json.dumps(visual_plan, ensure_ascii=True)}

        Studio panel:
        {json.dumps(studio_panel, ensure_ascii=True)}
        """.strip()
        return PromptEnvelope(system=system, user=user)

    @staticmethod
    def _knowledge_to_sections(retrieved_knowledge: dict[str, list[dict[str, Any]]]) -> dict[str, list[str]]:
        sections: dict[str, list[str]] = {}
        for channel, items in retrieved_knowledge.items():
            sections[channel] = [item["content"] for item in items]
        return sections
