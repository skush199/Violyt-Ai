from __future__ import annotations

import re
from typing import Any

from app.ai.structured_prompt_parser import StructuredPromptParser


class ResearchEditorialPlanningService:
    RESEARCH_SIGNAL_PATTERN = re.compile(
        r"\b("
        r"analysis|analytical|analyze|explainer|explain|why it matters|go beyond|beyond the headline|"
        r"strategy|strategic|implication|implications|policy|regulation|agreement|fta|treaty|budget|"
        r"inflation|rates?|repo|macro|economy|economic|trade|tariff|exports?|imports?|market|"
        r"current|latest|today|recent|signed on|announced|outlook|forecast"
        r")\b",
        re.IGNORECASE,
    )
    CONVERSATIONAL_ANALYTICAL_PATTERN = re.compile(
        r"\b(conversational|analytical|intelligent|informed friend|explain(?:ing)? finance well|not a brand)\b",
        re.IGNORECASE,
    )
    TIMELY_RESEARCH_SIGNAL_PATTERN = re.compile(
        r"\b("
        r"latest|today|recent|current|signed on|announced|policy|regulation|agreement|fta|treaty|budget|"
        r"forecast|outlook|repo|rate cut|tariff|trade deal|exports?|imports?"
        r")\b",
        re.IGNORECASE,
    )
    EXACT_RESEARCH_REQUEST_PATTERN = re.compile(
        r"\b("
        r"exact|specific|latest data|current data|current numbers?|latest numbers?|statistics?|stats?|"
        r"percentage|percentages|benchmark|benchmarks|rankings?|market data|source-backed|verified facts?"
        r")\b",
        re.IGNORECASE,
    )
    PRACTICAL_FINANCE_JOURNEY_PATTERN = re.compile(
        r"\b("
        r"retirement|retire|40s|corpus|net worth|monthly surplus|annual expense|inflation adjusted|"
        r"step by step|step-by-step|journey|planning journey|wealth creation|diversification|"
        r"investment scaling|savings rate|smart retirement plan"
        r")\b",
        re.IGNORECASE,
    )
    VISUAL_OR_TEMPLATE_CHANNEL_PATTERN = re.compile(
        r"(visual|template|layout|render|logo|palette|reference|mood|style|creative|asset|brand_visual)",
        re.IGNORECASE,
    )
    VISUAL_OR_TEMPLATE_CONTENT_PATTERN = re.compile(
        r"\b("
        r"logo|palette|hex|color palette|layout|composition|hero image|safe zone|typography|font|"
        r"curve|circle|brand system|reference creative|visual language|mood board|template|overlay"
        r")\b",
        re.IGNORECASE,
    )
    EXACT_CLAIM_PATTERN = re.compile(
        r"("
        r"\b\d+(?:\.\d+)?\s*%|"
        r"\b\d[\d,]*(?:\.\d+)?\s*(?:crore|lakh|million|billion|trillion|mn|bn|bps|bp)\b|"
        r"\b\d{2,}\b|"
        r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+20\d{2}\b|"
        r"\b20\d{2}\b"
        r")",
        re.IGNORECASE,
    )
    STOPWORDS = {
        "a",
        "an",
        "and",
        "blog",
        "brand",
        "caption",
        "carousel",
        "content",
        "create",
        "description",
        "for",
        "generate",
        "give",
        "image",
        "instagram",
        "linkedin",
        "of",
        "on",
        "or",
        "post",
        "the",
        "thread",
        "write",
        "x",
        "youtube",
    }
    ROLE_TEMPLATES = {
        "carousel": [
            ("hook", "Open with a swipe-worthy thesis or tension point."),
            ("context", "Frame what happened in one clean analytical setup."),
            ("structure", "Explain how the topic, deal, policy, or trend is actually structured."),
            ("undercovered_angle", "Surface the undercovered clause, trade-off, or second-order detail."),
            ("strategic_meaning", "Explain why it matters strategically, not just numerically."),
            ("takeaway", "Close with the smartest reader takeaway or CTA."),
        ],
        "infographic": [
            ("headline", "Lead with the strongest explanatory frame."),
            ("context", "Set up the background quickly."),
            ("key_numbers", "Show the most decision-relevant facts or comparisons."),
            ("structure", "Explain the process, structure, or moving parts."),
            ("implications", "Translate the facts into implications."),
            ("takeaway", "Land the practical takeaway."),
        ],
        "static": [
            ("single_frame_story", "Condense the strongest thesis into one high-clarity insight."),
            ("proof", "Support it with one or two concrete proof cues."),
            ("takeaway", "Leave the reader with a sharp takeaway or CTA."),
        ],
        "long_form": [
            ("intro", "Open with the central tension or framing question."),
            ("what_happened", "Explain what happened with exact context."),
            ("what_matters", "Show what is structurally or economically important."),
            ("undercovered_angle", "Surface what most summaries miss."),
            ("implications", "Translate it into implications for the reader."),
            ("close", "Conclude with a practical takeaway."),
        ],
        "short_form": [
            ("hook", "Open with a strong non-obvious insight."),
            ("analysis", "Explain the key analytical point clearly."),
            ("takeaway", "Close with the practical takeaway."),
        ],
    }

    def build(
        self,
        *,
        prompt: str,
        studio_panel: dict[str, Any] | None,
        brand_context: dict[str, Any] | None,
        persona_context: dict[str, Any] | None,
        objective_context: dict[str, Any] | None,
        knowledge_brief: list[dict[str, Any]] | None = None,
        live_research: dict[str, Any] | None = None,
        content_format_guide: dict[str, Any] | None = None,
        deliverable_type: str | None = None,
        template_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        prompt_text = self._normalize_text(prompt, limit=520)
        parsed_prompt = StructuredPromptParser.parse_prompt(prompt)
        live_research = live_research if isinstance(live_research, dict) else {}
        knowledge_brief = [item for item in (knowledge_brief or []) if isinstance(item, dict)]
        studio_panel = studio_panel if isinstance(studio_panel, dict) else {}
        format_name = self._normalize_text(studio_panel.get("format"), limit=32).casefold()
        platform_preset = self._normalize_text(studio_panel.get("platform_preset"), limit=32).casefold()
        research_sources = [item for item in (live_research.get("sources") or []) if isinstance(item, dict)]
        ranked_sources = [item for item in (live_research.get("ranked_sources") or []) if isinstance(item, dict)]
        verified_facts = [item for item in (live_research.get("verified_facts") or []) if isinstance(item, dict)]
        inferences = self._inferences(live_research=live_research, knowledge_brief=knowledge_brief)
        uncertainties = self._uncertainties(live_research=live_research)
        format_family = self._format_family(format_name=format_name, deliverable_type=deliverable_type)
        explicit_story_beats = self._ordered_story_beats(parsed_prompt)
        sample_editorial_brief = self._sample_editorial_brief(
            template_context=template_context,
            brand_context=brand_context or {},
            format_family=format_family,
        )
        ordered_story_beats = explicit_story_beats or self._sample_story_beats(
            sample_editorial_brief,
            format_family=format_family,
        )
        active = self._should_activate(
            prompt_text=prompt_text,
            live_research=live_research,
            deliverable_type=deliverable_type,
            format_family=format_family,
            ordered_story_beats=ordered_story_beats,
        )
        topic_focus = self._topic_focus(prompt_text)
        angle = self._angle(prompt_text, live_research=live_research)
        thesis = self._thesis(topic_focus=topic_focus, angle=angle, brand_context=brand_context or {})
        insight_hierarchy = self._insight_hierarchy(
            live_research=live_research,
            knowledge_brief=knowledge_brief,
            objective_context=objective_context or {},
        )
        preferred_slide_count = self._preferred_slide_count(
            content_format_guide=content_format_guide or {},
            studio_panel=studio_panel,
        )
        sample_slide_count = self._sample_sequence_slide_count(
            template_context=template_context,
            sample_editorial_brief=sample_editorial_brief,
            format_family=format_family,
        )
        explicit_slide_count = self._explicit_slide_count(prompt_text)
        if sample_slide_count and not explicit_slide_count and not explicit_story_beats:
            preferred_slide_count = sample_slide_count
        elif explicit_slide_count:
            preferred_slide_count = explicit_slide_count
        elif ordered_story_beats:
            preferred_slide_count = max(preferred_slide_count or 0, len(ordered_story_beats))
        outline = self._outline(
            format_family=format_family,
            prompt_text=prompt_text,
            thesis=thesis,
            preferred_slide_count=preferred_slide_count,
            ordered_story_beats=ordered_story_beats,
        )
        ranked_source_pack = self._ranked_source_pack(
            ranked_sources=ranked_sources,
            fallback_sources=research_sources,
        )
        source_pack = self._source_pack(research_sources, verified_facts, knowledge_brief, ranked_source_pack)
        citation_rules = self._citation_rules(
            format_family=format_family,
            deliverable_type=deliverable_type,
            needs_live_research=bool(live_research.get("status") not in (None, "", "not_required")),
            ranked_source_pack=ranked_source_pack,
        )
        source_backing_rules = self._source_backing_rules()
        editorial_style = self._editorial_style(prompt_text, platform_preset)
        reader_payoff = self._reader_payoff(prompt_text, angle)
        hook_strategy = self._hook_strategy(format_family, prompt_text, angle)
        disclaimer_request = parsed_prompt.get("disclaimer_request") if isinstance(parsed_prompt.get("disclaimer_request"), dict) else {}
        sample_guided = bool(
            sample_editorial_brief
            and not explicit_story_beats
            and (
                bool(ordered_story_beats)
                or format_family in {"static", "infographic"}
            )
        )
        mode = (
            "sample_guided_explainer"
            if sample_guided and not active
            else (
            "guided_explainer"
            if explicit_story_beats and not active
            else ("research_editorial" if active else "standard")
            )
        )
        summary = self._summary(
            thesis=thesis,
            reader_payoff=reader_payoff,
            insight_hierarchy=insight_hierarchy,
        )

        return {
            "active": active,
            "mode": mode,
            "deliverable_type": self._normalize_text(deliverable_type, limit=32),
            "platform_preset": platform_preset,
            "format": format_name,
            "format_family": format_family,
            "editorial_style": editorial_style,
            "topic_focus": topic_focus,
            "angle": angle,
            "thesis": thesis,
            "reader_payoff": reader_payoff,
            "hook_strategy": hook_strategy,
            "insight_hierarchy": insight_hierarchy,
            "ordered_story_beats": ordered_story_beats,
            "narrative_contract": (
                "preserve_user_order"
                if explicit_story_beats
                else (
                    "follow_sample_editorial_rhythm"
                    if sample_guided and format_family == "carousel"
                    else (
                        "follow_sample_infographic_flow"
                        if sample_guided and format_family == "infographic"
                        else ("follow_sample_static_hierarchy" if sample_guided and format_family == "static" else "")
                    )
                )
            ),
            "outline": outline,
            "sample_editorial_brief": sample_editorial_brief,
            "fact_model": {
                "verified_facts": verified_facts[:6],
                "inferences": inferences[:4],
                "uncertainties": uncertainties[:4],
            },
            "ranked_sources": ranked_source_pack,
            "citation_rules": citation_rules,
            "source_backing_rules": source_backing_rules,
            "research_guard": self._research_guard(
                active=active,
                prompt_text=prompt_text,
                verified_facts=verified_facts,
                ranked_source_pack=ranked_source_pack,
                research_status=self._normalize_text(live_research.get("status"), limit=32),
            ),
            "source_pack": source_pack,
            "source_count": len(source_pack),
            "preferred_slide_count": preferred_slide_count,
            "summary": summary,
            "disclaimer_requested": bool(disclaimer_request.get("requested")),
            "disclaimer_placement": self._normalize_text(disclaimer_request.get("placement"), limit=24),
            "disclaimer_style": self._normalize_text(disclaimer_request.get("style"), limit=24),
            "needs_live_research": bool(live_research.get("status") not in (None, "", "not_required")),
            "research_status": self._normalize_text(live_research.get("status"), limit=32),
        }

    def _research_guard(
        self,
        *,
        active: bool,
        prompt_text: str,
        verified_facts: list[dict[str, Any]],
        ranked_source_pack: list[dict[str, Any]],
        research_status: str,
    ) -> dict[str, Any]:
        requires_fresh_research = bool(self.RESEARCH_SIGNAL_PATTERN.search(prompt_text))
        requires_blocking_research = bool(
            self.TIMELY_RESEARCH_SIGNAL_PATTERN.search(prompt_text)
            or self.EXACT_CLAIM_PATTERN.search(prompt_text)
            or self.EXACT_RESEARCH_REQUEST_PATTERN.search(prompt_text)
        )
        strict = bool(active and requires_fresh_research)
        # "unavailable" means a search backend IS configured but the runtime fetch failed.
        # "not_configured" means no backend is set up at all — that is not a failure, so
        # it must not trigger hard_fail.  Any other status (not_required, empty) also
        # does not block generation.
        hard_fail = bool(
            strict
            and requires_blocking_research
            and research_status == "unavailable"
            and not verified_facts
            and not ranked_source_pack
        )
        reason = ""
        if hard_fail:
            reason = (
                "This prompt needs externally verified research, but live research was unavailable and no ranked sources were confirmed."
            )
        return {
            "strict_mode": strict,
            "requires_fresh_research": requires_fresh_research,
            "requires_blocking_research": requires_blocking_research,
            "hard_fail": hard_fail,
            "reason": reason,
        }

    @staticmethod
    def knowledge_brief_from_retrieved(retrieved_knowledge: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        brief: list[dict[str, Any]] = []
        for channel, items in (retrieved_knowledge or {}).items():
            for item in (items or [])[:2]:
                if not isinstance(item, dict):
                    continue
                content = ResearchEditorialPlanningService._normalize_text(item.get("content"), limit=420)
                if not content:
                    continue
                brief.append(
                    {
                        "channel": ResearchEditorialPlanningService._normalize_text(channel, limit=32),
                        "content": content,
                        "source_url": ResearchEditorialPlanningService._normalize_text(item.get("source_url"), limit=260) or None,
                    }
                )
        return brief[:8]

    @staticmethod
    def _normalize_text(value: Any, limit: int | None = None) -> str:
        text = " ".join(str(value or "").split()).strip()
        if not text or limit is None:
            return text
        return text[:limit].rstrip(" ,.;:-")

    def _should_activate(
        self,
        *,
        prompt_text: str,
        live_research: dict[str, Any],
        deliverable_type: str | None,
        format_family: str,
        ordered_story_beats: list[str],
    ) -> bool:
        if any(live_research.get(key) for key in ("summary", "sources", "verified_facts")):
            return True
        if self.TIMELY_RESEARCH_SIGNAL_PATTERN.search(prompt_text):
            return True
        if (
            format_family in {"carousel", "infographic"}
            and ordered_story_beats
            and self.PRACTICAL_FINANCE_JOURNEY_PATTERN.search(prompt_text)
            and not self.TIMELY_RESEARCH_SIGNAL_PATTERN.search(prompt_text)
        ):
            return False
        if self.RESEARCH_SIGNAL_PATTERN.search(prompt_text):
            if (
                format_family in {"carousel", "infographic"}
                and self.PRACTICAL_FINANCE_JOURNEY_PATTERN.search(prompt_text)
                and not self.TIMELY_RESEARCH_SIGNAL_PATTERN.search(prompt_text)
            ):
                return False
            return True
        deliverable = self._normalize_text(deliverable_type, limit=32).casefold()
        return deliverable in {"blog", "newsletter"} and bool(self.CONVERSATIONAL_ANALYTICAL_PATTERN.search(prompt_text))

    @staticmethod
    def _ordered_story_beats(parsed_prompt: dict[str, Any]) -> list[str]:
        return [
            str(item).strip()
            for item in (parsed_prompt.get("ordered_story_beats") or [])
            if str(item).strip()
        ][:8]

    @staticmethod
    def _sample_editorial_brief(
        *,
        template_context: dict[str, Any] | None,
        brand_context: dict[str, Any],
        format_family: str,
    ) -> dict[str, Any]:
        if format_family != "carousel":
            return {}

        sequence_pack = (
            template_context.get("sequence_pack")
            if isinstance(template_context, dict) and isinstance(template_context.get("sequence_pack"), dict)
            else {}
        )
        sequence_slides = [
            dict(item)
            for item in (sequence_pack.get("slides") or [])
            if isinstance(item, dict)
        ]
        if len(sequence_slides) >= 3:
            story_roles = [
                str(item.get("story_role") or "").strip()
                for item in sequence_slides
                if str(item.get("story_role") or "").strip()
            ]
            structural_cues = [
                [
                    str(cue).strip()
                    for cue in (item.get("structural_cues") or [])
                    if str(cue).strip()
                ][:4]
                for item in sequence_slides
            ]
            headline_patterns = [
                str(item.get("headline_hint") or "").strip()
                for item in sequence_slides
                if str(item.get("headline_hint") or "").strip()
            ][:6]
            sample_summaries = [
                str(item.get("sequence_summary") or "").strip()
                for item in sequence_slides
                if str(item.get("sequence_summary") or "").strip()
            ][:6]
            return {
                "source": "sequence_pack",
                "family_name": str(sequence_pack.get("family_name") or "").strip(),
                "slide_count": len(sequence_slides),
                "story_roles": story_roles,
                "structural_cues": structural_cues,
                "headline_patterns": headline_patterns,
                "sample_summaries": sample_summaries,
            }

        zone_map = (
            template_context.get("zone_map")
            if isinstance(template_context, dict) and isinstance(template_context.get("zone_map"), dict)
            else {}
        )
        if not zone_map and isinstance(template_context, dict):
            zone_map = template_context if isinstance(template_context.get("editorial_dna"), dict) else {}
        template_editorial_dna = (
            zone_map.get("editorial_dna")
            if isinstance(zone_map, dict) and isinstance(zone_map.get("editorial_dna"), dict)
            else {}
        )
        if template_editorial_dna and str(template_editorial_dna.get("format_family") or "").strip().casefold() == format_family:
            return {
                "source": "template_editorial_dna",
                "family_name": str(zone_map.get("layout_type") or "").strip(),
                "slide_count": int(template_editorial_dna.get("page_count_hint") or 0) or None,
                "story_roles": [
                    str(item).strip()
                    for item in (template_editorial_dna.get("story_arc_roles") or [])
                    if str(item).strip()
                ][:8],
                "headline_patterns": [
                    str(item).strip()
                    for item in (template_editorial_dna.get("headline_patterns") or [])
                    if str(item).strip()
                ][:6],
                "sample_summaries": [
                    str(item).strip()
                    for item in (template_editorial_dna.get("supporting_patterns") or [])
                    if str(item).strip()
                ][:6],
                "explanation_styles": [
                    str(template_editorial_dna.get("explanation_style") or "").strip()
                ]
                if str(template_editorial_dna.get("explanation_style") or "").strip()
                else [],
                "copy_densities": [
                    str(template_editorial_dna.get("copy_density") or "").strip()
                ]
                if str(template_editorial_dna.get("copy_density") or "").strip()
                else [],
                "closing_styles": [
                    str(template_editorial_dna.get("closing_style") or "").strip()
                ]
                if str(template_editorial_dna.get("closing_style") or "").strip()
                else [],
                "proof_module_count": int(template_editorial_dna.get("proof_module_count") or 0) or None,
            }

        visual_identity = brand_context.get("visual_identity", {}) if isinstance(brand_context, dict) else {}
        design_system = visual_identity.get("design_system", {}) if isinstance(visual_identity.get("design_system"), dict) else {}
        editorial_patterns_root = design_system.get("editorial_patterns", {}) if isinstance(design_system.get("editorial_patterns"), dict) else {}
        editorial_patterns = (
            editorial_patterns_root.get(format_family)
            if isinstance(editorial_patterns_root.get(format_family), dict)
            else editorial_patterns_root
        )
        story_arc = [
            str(item).strip()
            for item in (editorial_patterns.get("dominant_story_arc") or [])
            if str(item).strip()
        ][:8]
        if story_arc or format_family == "static":
            return {
                "source": "design_system",
                "family_name": str(editorial_patterns.get("family_name") or "").strip(),
                "slide_count": int(editorial_patterns.get("preferred_slide_count") or len(story_arc) or 0) or len(story_arc),
                "story_roles": story_arc,
                "structural_cues": [],
                "headline_patterns": [
                    str(item).strip()
                    for item in (editorial_patterns.get("headline_patterns") or [])
                    if str(item).strip()
                ][:6],
                "sample_summaries": [
                    str(item).strip()
                    for item in (editorial_patterns.get("sample_summaries") or [])
                    if str(item).strip()
                ][:6],
                "explanation_styles": [
                    str(item).strip()
                    for item in (editorial_patterns.get("explanation_styles") or [])
                    if str(item).strip()
                ][:4],
                "copy_densities": [
                    str(item).strip()
                    for item in (editorial_patterns.get("copy_densities") or [])
                    if str(item).strip()
                ][:4],
                "closing_styles": [
                    str(item).strip()
                    for item in (editorial_patterns.get("closing_styles") or [])
                    if str(item).strip()
                ][:4],
                "proof_module_count": int(editorial_patterns.get("proof_module_count") or 0) or None,
            }
        return {}

    @classmethod
    def _sample_story_beats(
        cls,
        sample_editorial_brief: dict[str, Any],
        *,
        format_family: str,
    ) -> list[str]:
        if format_family not in {"carousel", "infographic"} or not isinstance(sample_editorial_brief, dict):
            return []
        story_roles = [
            str(item).strip()
            for item in (sample_editorial_brief.get("story_roles") or [])
            if str(item).strip()
        ][:8]
        structural_cues = sample_editorial_brief.get("structural_cues") or []
        beats: list[str] = []
        for index, story_role in enumerate(story_roles, start=1):
            cue_list = structural_cues[index - 1] if index - 1 < len(structural_cues) and isinstance(structural_cues[index - 1], list) else []
            cue = next((str(item).strip() for item in cue_list if str(item).strip()), "")
            beat = cls._sample_story_beat_for_role(story_role=story_role, cue=cue, index=index, slide_count=len(story_roles))
            if beat:
                beats.append(beat)
        return beats[:8]

    @staticmethod
    def _sample_story_beat_for_role(
        *,
        story_role: str,
        cue: str,
        index: int,
        slide_count: int,
    ) -> str:
        normalized_role = str(story_role or "").strip().casefold()
        cue_text = str(cue or "").strip()
        if normalized_role in {"hook", "cover", "opening", "title"}:
            return f"Open with a strong hook or tension point{f' inspired by the sample cue: {cue_text}' if cue_text else ''}."
        if normalized_role in {"context", "setup"}:
            return f"Set up the context clearly and simply{f' using the sample rhythm: {cue_text}' if cue_text else ''}."
        if normalized_role in {"structure", "analysis", "what_happened", "detail"}:
            return f"Explain the next core idea step by step{f' with the sample cue: {cue_text}' if cue_text else ''}."
        if normalized_role in {"undercovered_angle", "missed_angle"}:
            return f"Surface the overlooked angle or hidden implication{f' following the sample cue: {cue_text}' if cue_text else ''}."
        if normalized_role in {"strategic_meaning", "what_matters", "implications"}:
            return f"Translate the point into practical or strategic meaning{f' using the sample cue: {cue_text}' if cue_text else ''}."
        if normalized_role in {"takeaway", "close", "closing", "cta", "final"} or index == slide_count:
            return f"Close with the final takeaway or forward-looking conclusion{f' in the sample’s style: {cue_text}' if cue_text else ''}."
        return f"Advance the story with the next distinct teaching beat{f' using the sample cue: {cue_text}' if cue_text else ''}."

    def _topic_focus(self, prompt_text: str) -> str:
        cleaned = re.sub(r"^[\"']+|[\"']+$", "", prompt_text).strip()
        cleaned = re.sub(
            r"^(?:write|create|generate|give me|draft|make)\s+(?:an?|the)?\s*(?:linkedin|instagram|x|youtube)?\s*(?:post|carousel|caption|thread|description|blog)?\s*(?:for [^,]+,)?\s*(?:on|about)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        parts = [part.strip(" ,.-") for part in re.split(r"[.?!]", cleaned) if part.strip()]
        candidate = parts[0] if parts else cleaned
        tokens = [
            token
            for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9&'/-]*", candidate)
            if token.casefold() not in self.STOPWORDS
        ]
        if tokens:
            candidate = " ".join(tokens[:14])
        return candidate[:180].strip() or "the topic"

    def _angle(self, prompt_text: str, *, live_research: dict[str, Any]) -> str:
        lowered = prompt_text.casefold()
        if self.PRACTICAL_FINANCE_JOURNEY_PATTERN.search(prompt_text) and not self.TIMELY_RESEARCH_SIGNAL_PATTERN.search(prompt_text):
            return "Turn the topic into a practical step-by-step financial planning journey with simple examples and clear progression."
        if "go beyond" in lowered or "beyond the headline" in lowered:
            return "Go beyond the headline framing and explain the structure, trade-offs, and strategic meaning."
        if "why it matters" in lowered and "strategic" in lowered:
            return "Explain why it matters strategically, not just what happened."
        if "signed on" in lowered or re.search(r"\b20\d{2}\b", prompt_text):
            return "Anchor the event in exact context, then explain the structure and implications."
        if live_research.get("verified_facts"):
            return "Use verified facts to separate the visible headline from the deeper implications."
        return "Lead with the most decision-useful insight, then explain what is structurally important and undercovered."

    def _thesis(self, *, topic_focus: str, angle: str, brand_context: dict[str, Any]) -> str:
        brand_name = self._normalize_text(brand_context.get("brand_name"), limit=80)
        if brand_name:
            return f"{topic_focus}: {angle} Keep the explanation intelligent, grounded, and native to {brand_name}'s brand voice."
        return f"{topic_focus}: {angle}"

    def _insight_hierarchy(
        self,
        *,
        live_research: dict[str, Any],
        knowledge_brief: list[dict[str, Any]],
        objective_context: dict[str, Any],
    ) -> list[str]:
        insights: list[str] = []
        filtered_knowledge = self._filtered_analytical_knowledge(knowledge_brief)
        for fact in (live_research.get("verified_facts") or [])[:4]:
            if not isinstance(fact, dict):
                continue
            label = self._normalize_text(fact.get("label"), limit=120)
            value = self._normalize_text(fact.get("value"), limit=220)
            if label and value:
                insights.append(f"{label}: {value}")
            elif value:
                insights.append(value)
        for item in filtered_knowledge[:3]:
            content = self._normalize_text(item.get("content"), limit=220)
            if content:
                insights.append(content)
        objective_description = self._normalize_text(
            objective_context.get("description") or objective_context.get("name"),
            limit=180,
        )
        if objective_description:
            insights.append(f"Objective lens: {objective_description}")
        deduped: list[str] = []
        seen: set[str] = set()
        for insight in insights:
            key = insight.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(insight)
        return deduped[:6]

    def _outline(
        self,
        *,
        format_family: str,
        prompt_text: str,
        thesis: str,
        preferred_slide_count: int | None,
        ordered_story_beats: list[str] | None = None,
    ) -> list[dict[str, str]]:
        ordered_story_beats = [str(item).strip() for item in (ordered_story_beats or []) if str(item).strip()]
        if ordered_story_beats and format_family == "carousel":
            return self._outline_from_story_beats(ordered_story_beats)
        templates = list(self.ROLE_TEMPLATES.get(format_family, self.ROLE_TEMPLATES["short_form"]))
        if format_family == "carousel" and preferred_slide_count and preferred_slide_count > 0:
            templates = templates[: max(3, min(preferred_slide_count, len(templates)))]
        outline: list[dict[str, str]] = []
        for index, (role, purpose) in enumerate(templates, start=1):
            outline.append(
                {
                    "index": str(index),
                    "role": role,
                    "purpose": purpose,
                    "notes": self._outline_note(role=role, prompt_text=prompt_text, thesis=thesis),
                }
            )
        return outline

    def _outline_from_story_beats(self, ordered_story_beats: list[str]) -> list[dict[str, str]]:
        outline: list[dict[str, str]] = []
        slide_count = len(ordered_story_beats)
        for index, beat in enumerate(ordered_story_beats, start=1):
            outline.append(
                {
                    "index": str(index),
                    "role": self._ordered_story_role(beat=beat, index=index, slide_count=slide_count),
                    "purpose": beat,
                    "notes": "",
                }
            )
        return outline

    @staticmethod
    def _ordered_story_role(*, beat: str, index: int, slide_count: int) -> str:
        lowered = str(beat or "").casefold()
        if index == 1 or any(token in lowered for token in ("start with", "begin with", "open with", "lead with", "hook")):
            return "hook"
        if index == slide_count or any(token in lowered for token in ("end with", "close with", "finish with", "closing")):
            return "takeaway"
        if any(token in lowered for token in ("what is", "explain", "define", "break down", "simple terms", "step 1", "step 2", "step 3", "step 4")):
            return "structure"
        if any(token in lowered for token in ("why people ignore", "usually ignore", "overlook", "miss", "undercovered")):
            return "undercovered_angle"
        if any(token in lowered for token in ("connect", "impact", "money", "opportunities", "infrastructure", "credit access", "why it matters", "bigger")):
            return "strategic_meaning"
        return "detail"

    def _outline_note(self, *, role: str, prompt_text: str, thesis: str) -> str:
        lowered = prompt_text.casefold()
        if role == "hook":
            if "swipe" in lowered:
                return "Open with a hook strong enough to make the reader continue."
            return "Lead with the strongest non-obvious insight or tension point."
        if role in {"structure", "deal_structure", "what_happened"}:
            return "Explain the mechanics or negotiated structure, not just the surface summary."
        if role in {"undercovered_angle", "implications"}:
            return "Surface what the first-pass summary usually misses."
        if role in {"strategic_meaning", "takeaway", "close"}:
            return "Translate the analysis into strategic or practical meaning for the reader."
        return thesis[:180]

    def _source_pack(
        self,
        sources: list[dict[str, Any]],
        verified_facts: list[dict[str, Any]],
        knowledge_brief: list[dict[str, Any]],
        ranked_source_pack: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        packed: list[dict[str, str]] = []
        filtered_knowledge = self._filtered_analytical_knowledge(knowledge_brief)
        for source in ranked_source_pack[:3]:
            if source.get("label") or source.get("detail"):
                packed.append(
                    {
                        "type": "ranked_source",
                        "label": self._normalize_text(source.get("label"), limit=140),
                        "detail": self._normalize_text(source.get("detail"), limit=220),
                        "source": self._normalize_text(source.get("source"), limit=180),
                    }
                )
        for fact in verified_facts[:4]:
            label = self._normalize_text(fact.get("label"), limit=120)
            value = self._normalize_text(fact.get("value"), limit=200)
            source_title = self._normalize_text(fact.get("source_title"), limit=120)
            source_url = self._normalize_text(fact.get("source_url"), limit=240)
            if label or value:
                packed.append(
                    {
                        "type": "verified_fact",
                        "label": label or value,
                        "detail": value,
                        "source": source_title or source_url,
                    }
                )
        for source in sources[:3]:
            title = self._normalize_text(source.get("title"), limit=140)
            url = self._normalize_text(source.get("url"), limit=240)
            if title or url:
                packed.append({"type": "source", "label": title or url, "detail": url, "source": url})
        for item in filtered_knowledge[:2]:
            content = self._normalize_text(item.get("content"), limit=200)
            channel = self._normalize_text(item.get("channel"), limit=32)
            if content:
                packed.append({"type": "knowledge", "label": channel or "knowledge", "detail": content, "source": channel})
        return packed[:8]

    def _ranked_source_pack(
        self,
        *,
        ranked_sources: list[dict[str, Any]],
        fallback_sources: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        packed: list[dict[str, str]] = []
        for item in ranked_sources[:4]:
            title = self._normalize_text(item.get("title"), limit=140)
            url = self._normalize_text(item.get("url"), limit=240)
            support_count = int(item.get("support_count") or 0)
            rank = int(item.get("rank") or 0)
            if title or url:
                packed.append(
                    {
                        "label": title or url,
                        "detail": f"Rank {rank}; supports {support_count} verified fact(s)." if rank or support_count else url,
                        "source": url or title,
                    }
                )
        if packed:
            return packed[:4]
        for item in fallback_sources[:3]:
            title = self._normalize_text(item.get("title"), limit=140)
            url = self._normalize_text(item.get("url"), limit=240)
            if title or url:
                packed.append({"label": title or url, "detail": url, "source": url or title})
        return packed[:3]

    def _inferences(
        self,
        *,
        live_research: dict[str, Any],
        knowledge_brief: list[dict[str, Any]],
    ) -> list[str]:
        inferred: list[str] = []
        filtered_knowledge = self._filtered_analytical_knowledge(knowledge_brief)
        for item in (live_research.get("inferences") or [])[:4]:
            text = self._normalize_text(item, limit=220)
            if text:
                inferred.append(text)
        if not inferred:
            summary = self._normalize_text(live_research.get("summary"), limit=520)
            for sentence in re.split(r"(?<=[.!?])\s+", summary):
                text = self._normalize_text(sentence, limit=220)
                if not text:
                    continue
                lowered = text.casefold()
                if any(marker in lowered for marker in ("implies", "suggests", "signals", "could", "may", "matters", "strategic")):
                    inferred.append(text)
        for item in filtered_knowledge[:2]:
            content = self._normalize_text(item.get("content"), limit=220)
            if content:
                inferred.append(content)
        deduped: list[str] = []
        seen: set[str] = set()
        for item in inferred:
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped[:4]

    def _uncertainties(self, *, live_research: dict[str, Any]) -> list[str]:
        items: list[str] = []
        for item in (live_research.get("uncertainties") or [])[:4]:
            text = self._normalize_text(item, limit=220)
            if text:
                items.append(text)
        if not items and live_research.get("status") == "unavailable":
            items.append("External verification was unavailable, so any current or exact claim should be treated cautiously.")
        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped[:4]

    def _citation_rules(
        self,
        *,
        format_family: str,
        deliverable_type: str | None,
        needs_live_research: bool,
        ranked_source_pack: list[dict[str, str]],
    ) -> dict[str, Any]:
        deliverable = self._normalize_text(deliverable_type, limit=32).casefold()
        if format_family == "long_form" or deliverable in {"blog", "newsletter"}:
            style = "inline_source_cues"
            rules = [
                "Attribute exact facts, dates, and numbers to the strongest supporting source in the body.",
                "Keep interpretation separate from sourced fact statements.",
                "End with a compact sources-used list in metadata when practical.",
            ]
        elif format_family in {"carousel", "infographic"}:
            style = "light_on_canvas_citations"
            rules = [
                "Keep on-canvas attribution minimal, but attach source cues for exact facts in metadata or supporting copy.",
                "Use concise source mentions for highly specific claims or numbers.",
                "Do not overload slides with citations when the format is swipe-based.",
            ]
        else:
            style = "light_source_cues"
            rules = [
                "Use lightweight source cues for exact facts or claims that could be disputed.",
                "Keep the main copy readable while preserving factual attribution.",
            ]
        if not needs_live_research:
            rules.append("If the content is evergreen and not current-affairs driven, cite only when a specific fact or external claim appears.")
        if not ranked_source_pack:
            rules.append("If reliable source ranking is weak, avoid over-precise claims and state uncertainty instead of implying certainty.")
        return {"style": style, "rules": rules[:4]}

    def _source_backing_rules(self) -> list[str]:
        return [
            "Treat verified_facts as the only claims that can be stated as confirmed facts.",
            "Treat inferences as interpretation or implication, not as confirmed fact.",
            "Surface uncertainties when source coverage is thin, conflicting, conditional, or incomplete.",
            "Prefer higher-ranked sources when selecting which evidence to foreground.",
        ]

    def _preferred_slide_count(self, *, content_format_guide: dict[str, Any], studio_panel: dict[str, Any]) -> int | None:
        if not isinstance(content_format_guide, dict):
            return None
        format_name = self._normalize_text(studio_panel.get("format"), limit=32).casefold()
        expectations = content_format_guide.get("format_expectations")
        if isinstance(expectations, dict):
            current = expectations.get(format_name)
            if isinstance(current, dict):
                try:
                    value = int(current.get("preferred_slide_count") or 0)
                except (TypeError, ValueError):
                    value = 0
                if value > 0:
                    return value
        return None

    def _sample_sequence_slide_count(
        self,
        *,
        template_context: dict[str, Any] | None,
        sample_editorial_brief: dict[str, Any],
        format_family: str,
    ) -> int | None:
        if format_family != "carousel":
            return None
        sequence_pack = (
            template_context.get("sequence_pack")
            if isinstance(template_context, dict) and isinstance(template_context.get("sequence_pack"), dict)
            else {}
        )
        surface_policy = self._normalize_text(sequence_pack.get("surface_policy"), limit=40).casefold()
        if surface_policy not in {"style_reference_only", "lock_template_surface", "sequence_pack_locked"}:
            return None
        sequence_slides = [item for item in (sequence_pack.get("slides") or []) if isinstance(item, dict)]
        try:
            pack_count = int(sequence_pack.get("slide_count") or 0)
        except (TypeError, ValueError):
            pack_count = 0
        sample_count = int(sample_editorial_brief.get("slide_count") or 0) if isinstance(sample_editorial_brief, dict) else 0
        count = pack_count or len(sequence_slides) or sample_count
        return count if count > 0 else None

    def _explicit_slide_count(self, prompt_text: str) -> int | None:
        text = self._normalize_text(prompt_text, limit=520).casefold()
        patterns = (
            r"\b(?:make|create|generate|write|use|with|in)\s+(\d{1,2})\s+(?:slides?|pages?|frames?|carousel\s+slides?)\b",
            r"\b(?:make|create|generate|write|use|with|in)\s+a\s+(\d{1,2})[-\s]*(?:slide|page|frame)\b",
            r"\b(\d{1,2})[-\s]*(?:slide|page|frame)\s+(?:carousel|deck|sequence)\b",
            r"\bcarousel\s+(?:of|with|in)\s+(\d{1,2})\s+(?:slides?|pages?|frames?)\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            try:
                count = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if 1 <= count <= 20:
                return count
        return None

    def _reader_payoff(self, prompt_text: str, angle: str) -> str:
        lowered = prompt_text.casefold()
        if self.PRACTICAL_FINANCE_JOURNEY_PATTERN.search(prompt_text) and not self.TIMELY_RESEARCH_SIGNAL_PATTERN.search(prompt_text):
            return "Reader should leave with a clear step-by-step planning takeaway they can mentally apply to their own finances."
        if "why it matters" in lowered:
            return "Reader should understand why the topic matters beyond the obvious headline."
        if "how" in lowered and "work" in lowered:
            return "Reader should walk away understanding how the mechanism works and why it matters."
        return f"Reader should leave with a clearer analytical understanding: {angle}"

    def _hook_strategy(self, format_family: str, prompt_text: str, angle: str) -> str:
        lowered = prompt_text.casefold()
        if format_family == "carousel" and self.PRACTICAL_FINANCE_JOURNEY_PATTERN.search(prompt_text) and not self.TIMELY_RESEARCH_SIGNAL_PATTERN.search(prompt_text):
            return "Open with a practical tension point or high-stakes planning question, then move through the journey one clear step at a time."
        if format_family == "carousel":
            return "Open with a swipe-worthy hook that names the hidden angle, not just the topic."
        if "question" in lowered:
            return "Open with a sharp question that frames the analysis."
        return f"Open with the strongest non-obvious takeaway implied by the angle: {angle}"

    def _editorial_style(self, prompt_text: str, platform_preset: str) -> str:
        if self.PRACTICAL_FINANCE_JOURNEY_PATTERN.search(prompt_text) and not self.TIMELY_RESEARCH_SIGNAL_PATTERN.search(prompt_text):
            return "practical_finance_explainer"
        if self.CONVERSATIONAL_ANALYTICAL_PATTERN.search(prompt_text):
            return "conversational_analytical"
        if platform_preset == "linkedin":
            return "editorial_professional"
        return "research_led"

    def _summary(self, *, thesis: str, reader_payoff: str, insight_hierarchy: list[str]) -> str:
        pieces = [thesis, reader_payoff, *insight_hierarchy[:2]]
        return " ".join(piece for piece in pieces if piece).strip()[:640]

    def _filtered_analytical_knowledge(self, knowledge_brief: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            item
            for item in (knowledge_brief or [])
            if isinstance(item, dict) and not self._is_visual_or_template_knowledge(item)
        ]

    def _is_visual_or_template_knowledge(self, item: dict[str, Any]) -> bool:
        channel = self._normalize_text(item.get("channel"), limit=64)
        content = self._normalize_text(item.get("content"), limit=260)
        if self.VISUAL_OR_TEMPLATE_CHANNEL_PATTERN.search(channel):
            return True
        return bool(self.VISUAL_OR_TEMPLATE_CONTENT_PATTERN.search(content))

    @classmethod
    def enforce_source_backing(
        cls,
        payload: dict[str, Any],
        *,
        prompt_text: str,
        brief: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict) or not isinstance(brief, dict) or not brief.get("active"):
            return payload

        fact_model = brief.get("fact_model") if isinstance(brief.get("fact_model"), dict) else {}
        verified_facts = [item for item in (fact_model.get("verified_facts") or []) if isinstance(item, dict)]
        needs_live_research = bool(brief.get("needs_live_research"))
        if verified_facts:
            return cls._enforce_verified_fact_grounding(
                payload,
                prompt_text=prompt_text,
                brief=brief,
                verified_facts=verified_facts,
            )
        if not needs_live_research:
            return cls._inject_sources_used(payload, brief)

        allowed_snippets = cls._allowed_exact_snippets(prompt_text=prompt_text, verified_facts=verified_facts)
        sanitized = dict(payload)
        metadata = dict(sanitized.get("metadata") or {}) if isinstance(sanitized.get("metadata"), dict) else {}

        if cls._contains_unsupported_exact_claim(str(sanitized.get("headline") or ""), allowed_snippets):
            sanitized["headline"] = cls._safe_headline(brief=brief, prompt_text=prompt_text)
        if cls._contains_unsupported_exact_claim(str(sanitized.get("body") or ""), allowed_snippets):
            sanitized["body"] = cls._safe_body(brief=brief)
        if cls._contains_unsupported_exact_claim(str(metadata.get("supporting_line") or ""), allowed_snippets):
            metadata["supporting_line"] = cls._safe_supporting_line(brief=brief)

        stat_highlights = metadata.get("stat_highlights") if isinstance(metadata.get("stat_highlights"), list) else []
        metadata["stat_highlights"] = [
            str(item).strip()
            for item in stat_highlights
            if str(item).strip() and not cls._contains_unsupported_exact_claim(str(item), allowed_snippets)
        ]

        proof_points = metadata.get("proof_points") if isinstance(metadata.get("proof_points"), list) else []
        filtered_proof_points = [
            str(item).strip()
            for item in proof_points
            if str(item).strip() and not cls._contains_unsupported_exact_claim(str(item), allowed_snippets)
        ]
        if not filtered_proof_points:
            filtered_proof_points = cls._safe_proof_points(brief=brief)
        metadata["proof_points"] = filtered_proof_points[:4]
        metadata["claim_evidence_pairs"] = []
        metadata["sources_used"] = []
        metadata["research_status"] = cls._normalize_text(brief.get("research_status"), limit=32)
        sanitized["metadata"] = metadata
        return sanitized

    @classmethod
    def _enforce_verified_fact_grounding(
        cls,
        payload: dict[str, Any],
        *,
        prompt_text: str,
        brief: dict[str, Any],
        verified_facts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        sanitized = dict(payload)
        metadata = dict(sanitized.get("metadata") or {}) if isinstance(sanitized.get("metadata"), dict) else {}
        allowed_snippets = cls._allowed_exact_snippets(prompt_text=prompt_text, verified_facts=verified_facts)
        verified_pairs = cls._verified_fact_pairs(verified_facts)
        verified_lines = cls._verified_fact_lines(verified_pairs)

        if cls._contains_unsupported_exact_claim(str(sanitized.get("headline") or ""), allowed_snippets):
            sanitized["headline"] = cls._safe_headline(brief=brief, prompt_text=prompt_text)
        if cls._contains_unsupported_exact_claim(str(sanitized.get("body") or ""), allowed_snippets):
            sanitized["body"] = cls._safe_body_from_verified_facts(
                brief=brief,
                verified_pairs=verified_pairs,
            )

        supporting_line = str(metadata.get("supporting_line") or "").strip()
        if not supporting_line or cls._contains_unsupported_exact_claim(supporting_line, allowed_snippets):
            metadata["supporting_line"] = cls._safe_supporting_line_from_verified_facts(
                brief=brief,
                verified_pairs=verified_pairs,
            )

        stat_highlights = metadata.get("stat_highlights") if isinstance(metadata.get("stat_highlights"), list) else []
        metadata["stat_highlights"] = [
            str(item).strip()
            for item in stat_highlights
            if str(item).strip() and not cls._contains_unsupported_exact_claim(str(item), allowed_snippets)
        ]

        proof_points = metadata.get("proof_points") if isinstance(metadata.get("proof_points"), list) else []
        filtered_proof_points = [
            str(item).strip()
            for item in proof_points
            if str(item).strip() and not cls._contains_unsupported_exact_claim(str(item), allowed_snippets)
        ]
        if not filtered_proof_points:
            filtered_proof_points = verified_lines or cls._safe_proof_points(brief=brief)
        metadata["proof_points"] = filtered_proof_points[:4]

        metadata["claim_evidence_pairs"] = verified_pairs[:4]
        metadata["research_status"] = cls._normalize_text(brief.get("research_status"), limit=32)
        sanitized["metadata"] = metadata
        return cls._inject_sources_used(sanitized, brief)

    @classmethod
    def _inject_sources_used(cls, payload: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), dict) else {}
        if not metadata.get("sources_used"):
            metadata["sources_used"] = [
                label
                for label in (
                    cls._normalize_text(item.get("label"), limit=120)
                    for item in (brief.get("ranked_sources") or [])[:3]
                    if isinstance(item, dict)
                )
                if label
            ]
        payload["metadata"] = metadata
        return payload

    @classmethod
    def _verified_fact_pairs(cls, verified_facts: list[dict[str, Any]]) -> list[dict[str, str]]:
        pairs: list[dict[str, str]] = []
        seen: set[str] = set()
        for fact in verified_facts:
            if not isinstance(fact, dict):
                continue
            claim = cls._normalize_text(
                fact.get("label") or fact.get("claim") or fact.get("headline") or fact.get("title"),
                limit=120,
            )
            evidence = cls._normalize_text(
                fact.get("value") or fact.get("detail") or fact.get("source_title") or fact.get("source"),
                limit=180,
            )
            if not claim and not evidence:
                continue
            key = f"{claim.casefold()}|{evidence.casefold()}"
            if key in seen:
                continue
            seen.add(key)
            pairs.append({"claim": claim, "evidence": evidence})
        return pairs

    @classmethod
    def _verified_fact_lines(cls, pairs: list[dict[str, str]]) -> list[str]:
        lines: list[str] = []
        for pair in pairs:
            claim = cls._normalize_text((pair or {}).get("claim"), limit=140)
            evidence = cls._normalize_text((pair or {}).get("evidence"), limit=180)
            if claim and evidence:
                lines.append(f"{claim}: {evidence}")
            elif claim:
                lines.append(claim)
            elif evidence:
                lines.append(evidence)
            if len(lines) >= 4:
                break
        return lines

    @classmethod
    def _allowed_exact_snippets(cls, *, prompt_text: str, verified_facts: list[dict[str, Any]]) -> set[str]:
        allowed: set[str] = set()
        for match in cls.EXACT_CLAIM_PATTERN.findall(prompt_text or ""):
            text = cls._normalize_text(match, limit=80).casefold()
            if text:
                allowed.add(text)
        for fact in verified_facts:
            for field in ("label", "value", "source_title"):
                text = cls._normalize_text(fact.get(field), limit=120).casefold()
                if text:
                    allowed.add(text)
        return allowed

    @classmethod
    def _contains_unsupported_exact_claim(cls, text: str, allowed_snippets: set[str]) -> bool:
        normalized = cls._normalize_text(text, limit=260)
        if not normalized:
            return False
        lowered = normalized.casefold()
        if any(snippet and snippet in lowered for snippet in allowed_snippets):
            return False
        return bool(cls.EXACT_CLAIM_PATTERN.search(normalized)) or "%" in normalized

    @classmethod
    def _safe_headline(cls, *, brief: dict[str, Any], prompt_text: str) -> str:
        topic_focus = cls._normalize_text(brief.get("topic_focus"), limit=120)
        if topic_focus:
            return topic_focus
        cleaned = cls._normalize_text(prompt_text, limit=120)
        return cleaned or "Research-backed insight"

    @classmethod
    def _safe_body(cls, *, brief: dict[str, Any]) -> str:
        for candidate in (
            brief.get("thesis"),
            brief.get("reader_payoff"),
            cls._first_list_item((brief.get("fact_model") or {}).get("inferences")),
            cls._first_list_item((brief.get("fact_model") or {}).get("uncertainties")),
            brief.get("summary"),
        ):
            text = cls._normalize_text(candidate, limit=320)
            if text:
                return text
        return "Use the strongest source-backed angle and keep current claims qualitative until they are externally verified."

    @classmethod
    def _safe_body_from_verified_facts(cls, *, brief: dict[str, Any], verified_pairs: list[dict[str, str]]) -> str:
        lines = cls._verified_fact_lines(verified_pairs)
        if lines:
            return " ".join(lines[:2])[:320]
        return cls._safe_body(brief=brief)

    @classmethod
    def _safe_supporting_line(cls, *, brief: dict[str, Any]) -> str:
        for candidate in (
            cls._first_list_item((brief.get("fact_model") or {}).get("inferences")),
            brief.get("angle"),
            brief.get("reader_payoff"),
        ):
            text = cls._normalize_text(candidate, limit=180)
            if text:
                return text
        return "Keep the explanation source-aware and avoid unsupported specifics."

    @classmethod
    def _safe_supporting_line_from_verified_facts(cls, *, brief: dict[str, Any], verified_pairs: list[dict[str, str]]) -> str:
        for pair in verified_pairs:
            for candidate in ((pair or {}).get("claim"), (pair or {}).get("evidence")):
                text = cls._normalize_text(candidate, limit=180)
                if text:
                    return text
        return cls._safe_supporting_line(brief=brief)

    @classmethod
    def _safe_proof_points(cls, *, brief: dict[str, Any]) -> list[str]:
        proof_points: list[str] = []
        for candidate in (
            (brief.get("fact_model") or {}).get("inferences"),
            (brief.get("fact_model") or {}).get("uncertainties"),
            brief.get("insight_hierarchy"),
        ):
            for item in candidate if isinstance(candidate, list) else []:
                text = cls._normalize_text(item, limit=180)
                if text:
                    proof_points.append(text)
                if len(proof_points) >= 4:
                    return proof_points
        return proof_points

    @classmethod
    def _first_list_item(cls, values: Any) -> str:
        for item in values if isinstance(values, list) else []:
            text = cls._normalize_text(item, limit=220)
            if text:
                return text
        return ""

    @staticmethod
    def _format_family(*, format_name: str, deliverable_type: str | None) -> str:
        normalized_deliverable = ResearchEditorialPlanningService._normalize_text(deliverable_type, limit=32).casefold()
        if format_name == "carousel":
            return "carousel"
        if format_name == "infographic":
            return "infographic"
        if format_name == "static":
            return "static"
        if normalized_deliverable in {"blog", "newsletter"}:
            return "long_form"
        return "short_form"
