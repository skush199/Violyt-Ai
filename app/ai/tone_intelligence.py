from __future__ import annotations

from collections import Counter
import re
from typing import Any

from app.ai.providers.base import PromptEnvelope
from app.ai.providers.router import ProviderRouter


class ToneIntelligenceService:
    CTA_PATTERN = re.compile(
        r"\b(call|book|claim|compare|contact|discover|download|explore|get|join|learn|shop|start|try|see|schedule)\b",
        flags=re.IGNORECASE,
    )
    CLAIM_VERB_PATTERN = re.compile(
        r"\b(accelerate|boost|cut|eliminate|grow|help|improve|increase|lower|protect|reduce|save|shrink|simplify|speed|streamline)\b",
        flags=re.IGNORECASE,
    )
    TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z'-]{2,}")
    SENTENCE_SPLIT_PATTERN = re.compile(r"[.!?]+")
    PROOF_NUMBER_PATTERN = re.compile(
        r"\b(?:soc\s*2|iso\s*27001|\d+(?:\.\d+)?(?:%|x)|\d+(?:\.\d+)?\s*(?:day|days|week|weeks|month|months|year|years|hour|hours|min|mins|minute|minutes|team|teams|customer|customers|client|clients|audit|audits|step|steps|users|leaders|countries|markets))\b",
        flags=re.IGNORECASE,
    )
    STOPWORDS = {
        "about",
        "again",
        "also",
        "and",
        "are",
        "been",
        "best",
        "brand",
        "build",
        "can",
        "copy",
        "for",
        "from",
        "have",
        "into",
        "just",
        "more",
        "much",
        "only",
        "our",
        "that",
        "the",
        "their",
        "them",
        "this",
        "with",
        "your",
    }
    GENERIC_PROMO_WORDS = {
        "amazing",
        "best-in-class",
        "cutting edge",
        "effortless",
        "game changing",
        "innovative",
        "leading",
        "next level",
        "powerful",
        "premium",
        "revolutionary",
        "seamless",
        "smart",
        "smarter",
        "transformative",
        "trusted",
        "ultimate",
        "world class",
    }
    PROOF_MARKERS = {
        "backed",
        "benchmark",
        "because",
        "case study",
        "compliant",
        "customers",
        "data",
        "evidence",
        "measured",
        "proof",
        "proven",
        "results",
        "review",
        "stat",
        "study",
        "tested",
        "verified",
    }
    TRUST_MARKERS = {
        "enterprise",
        "gdpr",
        "implementation",
        "onboarding",
        "security",
        "soc 2",
        "support",
        "trusted by",
        "used by",
    }
    OBJECTION_MARKERS = {
        "avoid",
        "compare",
        "even if",
        "how",
        "instead of",
        "no need",
        "not sure",
        "risk",
        "without",
        "why",
    }
    RESPONSE_MARKERS = {
        "backed",
        "clearly explained",
        "guided",
        "explained clearly",
        "low risk",
        "lower risk",
        "no need",
        "plain english",
        "plain-english",
        "secure",
        "simple",
        "step-by-step",
        "supported",
        "transparent",
        "without",
    }
    LOW_SIGNAL_GROUNDING_PREFIXES = (
        "back",
        "buyer",
        "clear",
        "compar",
        "context",
        "data",
        "evid",
        "feel",
        "guid",
        "option",
        "proof",
        "prov",
        "result",
        "review",
        "risk",
        "secur",
        "simple",
        "support",
        "syste",
        "team",
        "test",
        "trust",
        "verif",
        "without",
    )
    OBJECTION_RESPONSE_INSTRUCTION_PREFIXES = {
        "address ",
        "answer ",
        "handle ",
        "respond to ",
        "reassure ",
    }
    GENERIC_CTA_PHRASES = {
        "discover more",
        "explore more",
        "learn more",
        "read more",
        "see more",
    }
    DIMENSION_KEYS = (
        "brand_alignment",
        "proof_strength",
        "objection_handling",
        "distinctiveness",
        "clarity",
        "cta_strength",
    )
    FIELD_GUIDANCE_KEYS = ("headline", "body", "cta", "metadata")

    def __init__(self) -> None:
        self.providers = ProviderRouter()

    @staticmethod
    def _clamp_score(value: float | int) -> int:
        return max(0, min(100, int(round(float(value)))))

    @classmethod
    def _dedupe_messages(cls, messages: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for message in messages:
            normalized = str(message or "").strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            output.append(normalized)
        return output

    @classmethod
    def _flatten_text(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, dict):
            items: list[str] = []
            for nested in value.values():
                items.extend(cls._flatten_text(nested))
            return items
        if isinstance(value, (list, tuple, set)):
            items: list[str] = []
            for nested in value:
                items.extend(cls._flatten_text(nested))
            return items
        return [str(value)]

    @classmethod
    def _extract_terms(cls, value: object) -> set[str]:
        terms: set[str] = set()
        for text in cls._flatten_text(value):
            for token in cls.TOKEN_PATTERN.findall(text.lower()):
                if token in cls.STOPWORDS:
                    continue
                terms.add(token)
        return terms

    @classmethod
    def _content_tokens(cls, content: str) -> list[str]:
        return [token for token in cls.TOKEN_PATTERN.findall(content.lower()) if token not in cls.STOPWORDS]

    @classmethod
    def _match_phrases(cls, content: str, phrases: set[str]) -> list[str]:
        lowered = content.lower()
        hits: list[str] = []
        for phrase in phrases:
            if " " in phrase or "-" in phrase:
                if phrase in lowered:
                    hits.append(phrase)
            elif re.search(rf"\b{re.escape(phrase)}\b", lowered):
                    hits.append(phrase)
        return hits

    @classmethod
    def _phrase_occurrences(cls, content: str, phrase: str) -> int:
        lowered = content.lower()
        target = str(phrase or "").strip().lower()
        if not target:
            return 0
        if " " in target or "-" in target:
            return lowered.count(target)
        return len(re.findall(rf"\b{re.escape(target)}\b", lowered))

    @classmethod
    def _normalize_grounding_text(cls, value: object) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

    @classmethod
    def _grounding_token_root(cls, token: str) -> str:
        root = str(token or "").lower().strip("'")
        if not root:
            return ""
        if len(root) > 5 and root.endswith("ies"):
            root = f"{root[:-3]}y"
        elif len(root) > 6 and root.endswith("ing"):
            root = root[:-3]
        elif len(root) > 5 and root.endswith("ied"):
            root = f"{root[:-3]}y"
        elif len(root) > 5 and root.endswith("ed"):
            root = root[:-2]
        elif len(root) > 5 and root.endswith("ly"):
            root = root[:-2]
        elif len(root) > 6 and root.endswith("ment"):
            root = root[:-4]
        elif len(root) > 6 and root.endswith("tion"):
            root = root[:-4]
        elif len(root) > 5 and root.endswith("ity"):
            root = root[:-3]
        elif len(root) > 5 and root.endswith("y"):
            root = root[:-1]
        elif len(root) > 5 and root.endswith("s"):
            root = root[:-1]
        return root.strip("'")

    @classmethod
    def _grounding_token_variants(cls, token: str) -> set[str]:
        root = cls._grounding_token_root(token)
        if len(root) < 4 or root in cls.STOPWORDS:
            return set()
        variants = {root}
        if len(root) >= 6:
            variants.add(root[:5])
        if len(root) >= 7:
            variants.add(root[:6])
        return {variant for variant in variants if len(variant) >= 4}

    @classmethod
    def _is_low_signal_grounding_term(cls, term: str) -> bool:
        lowered = str(term or "").lower()
        return any(lowered.startswith(prefix) for prefix in cls.LOW_SIGNAL_GROUNDING_PREFIXES)

    @classmethod
    def _grounding_term_weight(cls, term: str) -> float:
        lowered = str(term or "").lower()
        if not lowered:
            return 0.0
        base = 0.35 if cls._is_low_signal_grounding_term(lowered) else 1.0
        if len(lowered) >= 6:
            base += 0.2
        if len(lowered) >= 8:
            base += 0.15
        return base

    @classmethod
    def _grounding_phrase_records(cls, value: object) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for text in cls._flatten_text(value):
            normalized_text = cls._normalize_grounding_text(text)
            if not normalized_text:
                continue

            variant_map: dict[str, set[str]] = {}
            for token in cls.TOKEN_PATTERN.findall(normalized_text):
                if token in cls.STOPWORDS:
                    continue
                variants = cls._grounding_token_variants(token)
                if not variants:
                    continue
                canonical = cls._grounding_token_root(token)
                if not canonical or canonical in cls.STOPWORDS:
                    continue
                variant_map.setdefault(canonical, set()).update(variants)

            if not variant_map and not cls.PROOF_NUMBER_PATTERN.search(text):
                continue

            specific_terms = {
                term
                for term in variant_map
                if len(term) >= 4 and not cls._is_low_signal_grounding_term(term)
            }
            low_signal_terms = set(variant_map) - specific_terms
            has_quantifier = bool(cls.PROOF_NUMBER_PATTERN.search(text))
            if not specific_terms and not has_quantifier and len(normalized_text.split()) < 3:
                continue

            specificity = sum(cls._grounding_term_weight(term) for term in specific_terms)
            if len(specific_terms) >= 2:
                specificity += 0.35
            if has_quantifier:
                specificity += 0.8

            records.append(
                {
                    "text": str(text).strip(),
                    "normalized_text": normalized_text,
                    "variant_map": variant_map,
                    "specific_terms": specific_terms,
                    "low_signal_terms": low_signal_terms,
                    "has_quantifier": has_quantifier,
                    "specificity": max(specificity, 1.0 if has_quantifier else 0.0),
                }
            )
        return records

    @classmethod
    def _grounding_candidate_profile(cls, value: object) -> list[dict[str, Any]]:
        profiles: list[dict[str, Any]] = []
        for text in cls._flatten_text(value):
            normalized_text = cls._normalize_grounding_text(text)
            if not normalized_text:
                continue
            variants: set[str] = set()
            for token in cls.TOKEN_PATTERN.findall(normalized_text):
                if token in cls.STOPWORDS:
                    continue
                variants.update(cls._grounding_token_variants(token))
            profiles.append(
                {
                    "text": str(text).strip(),
                    "normalized_text": normalized_text,
                    "variants": variants,
                    "has_quantifier": bool(cls.PROOF_NUMBER_PATTERN.search(text)),
                }
            )
        return profiles

    @classmethod
    def _grounding_profile_matches(
        cls,
        candidate: dict[str, Any],
        evidence: dict[str, Any],
        *,
        mode: str = "default",
    ) -> bool:
        normalized_candidate = str(candidate.get("normalized_text") or "")
        candidate_variants = candidate.get("variants", set())
        if not normalized_candidate:
            return False

        normalized_evidence = str(evidence.get("normalized_text") or "")
        if normalized_evidence and len(normalized_evidence.split()) >= 3 and normalized_evidence in normalized_candidate:
            return True

        matched_specific_terms = {
            term
            for term in evidence.get("specific_terms", set())
            if candidate_variants & evidence.get("variant_map", {}).get(term, set())
        }
        matched_low_signal_terms = {
            term
            for term in evidence.get("low_signal_terms", set())
            if candidate_variants & evidence.get("variant_map", {}).get(term, set())
        }
        if not matched_specific_terms and not matched_low_signal_terms:
            return False

        weighted_overlap = sum(cls._grounding_term_weight(term) for term in matched_specific_terms)
        weighted_overlap += sum(cls._grounding_term_weight(term) for term in matched_low_signal_terms) * 0.2
        if candidate.get("has_quantifier") and evidence.get("has_quantifier"):
            weighted_overlap += 0.4

        specificity = max(float(evidence.get("specificity") or 0.0), 1.0 if evidence.get("has_quantifier") else 0.0)
        if specificity <= 0:
            return False
        coverage = weighted_overlap / specificity

        if evidence.get("has_quantifier") and coverage >= 0.55 and (matched_specific_terms or matched_low_signal_terms):
            return True
        if len(matched_specific_terms) >= 2 and coverage >= 0.4:
            return True
        if len(matched_specific_terms) >= 1 and matched_low_signal_terms and coverage >= 0.45:
            return True
        if mode == "objection" and len(matched_specific_terms) >= 1 and matched_low_signal_terms and coverage >= 0.32:
            return True
        if len(matched_specific_terms) >= 1 and coverage >= 0.68:
            return True
        return False

    @classmethod
    def _grounding_match_count(cls, candidates: object, evidence_items: object, *, mode: str = "default") -> int:
        evidence_records = cls._grounding_phrase_records(evidence_items)
        candidate_profiles = cls._grounding_candidate_profile(candidates)
        if not evidence_records or not candidate_profiles:
            return 0
        matches = 0
        matched_evidence: set[str] = set()
        for evidence in evidence_records:
            evidence_key = str(evidence.get("text") or evidence.get("normalized_text") or "").lower()
            if not evidence_key or evidence_key in matched_evidence:
                continue
            if any(cls._grounding_profile_matches(candidate, evidence, mode=mode) for candidate in candidate_profiles):
                matched_evidence.add(evidence_key)
                matches += 1
        return matches

    @classmethod
    def _sentence_list(cls, content: str) -> list[str]:
        return [sentence.strip() for sentence in cls.SENTENCE_SPLIT_PATTERN.split(content) if sentence.strip()]

    @classmethod
    def _normalize_content_payload(cls, content_payload: dict[str, Any] | None) -> dict[str, Any]:
        payload = content_payload if isinstance(content_payload, dict) else {}
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        return {
            "headline": str(payload.get("headline") or "").strip(),
            "body": str(payload.get("body") or "").strip(),
            "cta": str(payload.get("cta") or "").strip(),
            "hashtags": [item for item in cls._flatten_text(payload.get("hashtags", [])) if item],
            "metadata": metadata,
        }

    @classmethod
    def _metadata_list(cls, metadata: dict[str, Any], key: str) -> list[str]:
        return [item for item in cls._flatten_text(metadata.get(key, [])) if item]

    @classmethod
    def _metadata_pairs(cls, metadata: dict[str, Any], key: str) -> list[dict[str, str]]:
        raw_pairs = metadata.get(key, [])
        if not isinstance(raw_pairs, list):
            return []
        pairs: list[dict[str, str]] = []
        for item in raw_pairs:
            if not isinstance(item, dict):
                continue
            claim = str(item.get("claim") or "").strip()
            evidence = str(item.get("evidence") or "").strip()
            if not claim and not evidence:
                continue
            pairs.append({"claim": claim, "evidence": evidence})
        return pairs

    @classmethod
    def _structured_assets(cls, content_payload: dict[str, Any]) -> dict[str, Any]:
        metadata = content_payload.get("metadata", {}) if isinstance(content_payload.get("metadata"), dict) else {}
        claim_evidence_pairs = cls._metadata_pairs(metadata, "claim_evidence_pairs")
        evidence_fragments = (
            cls._metadata_list(metadata, "proof_points")
            + cls._metadata_list(metadata, "stat_highlights")
            + cls._metadata_list(metadata, "trust_builders")
            + [pair["evidence"] for pair in claim_evidence_pairs if pair.get("evidence")]
        )
        return {
            "hook_type": str(metadata.get("hook_type") or "").strip(),
            "supporting_line": str(metadata.get("supporting_line") or "").strip(),
            "proof_points": cls._metadata_list(metadata, "proof_points"),
            "stat_highlights": cls._metadata_list(metadata, "stat_highlights"),
            "objection_handling": cls._metadata_list(metadata, "objection_handling"),
            "trust_builders": cls._metadata_list(metadata, "trust_builders"),
            "claim_evidence_pairs": claim_evidence_pairs,
            "evidence_fragments": evidence_fragments,
        }

    @classmethod
    def _is_response_style_objection_line(cls, value: str) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        lowered = text.lower()
        if any(lowered.startswith(prefix) for prefix in cls.OBJECTION_RESPONSE_INSTRUCTION_PREFIXES):
            return False
        return bool(cls._match_phrases(lowered, cls.RESPONSE_MARKERS))

    @classmethod
    def _response_style_objection_lines(cls, values: list[str]) -> list[str]:
        lines: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if not text or not cls._is_response_style_objection_line(text):
                continue
            lines.append(text)
        return cls._dedupe_messages(lines)

    @classmethod
    def _audience_evidence_context(
        cls,
        brand_context: dict[str, Any] | None,
        persona_context: dict[str, Any] | None,
    ) -> dict[str, list[str]]:
        audience_context = (
            brand_context.get("audience_insights", {})
            if isinstance(brand_context, dict) and isinstance(brand_context.get("audience_insights"), dict)
            else {}
        )
        persona_context = persona_context or {}
        return {
            "objections": cls._dedupe_messages(
                cls._flatten_text([audience_context.get("objections", []), persona_context.get("objections", [])])
            )[:6],
            "pain_points": cls._dedupe_messages(
                cls._flatten_text([audience_context.get("pain_points", []), persona_context.get("fears_and_pain_points", [])])
            )[:6],
            "trust_signals": cls._dedupe_messages(cls._flatten_text(audience_context.get("trust_signals", [])))[:6],
            "proof_cues": cls._dedupe_messages(cls._flatten_text(audience_context.get("proof_cues", [])))[:6],
            "comparison_points": cls._dedupe_messages(cls._flatten_text(audience_context.get("comparison_points", [])))[:6],
            "desired_outcomes": cls._dedupe_messages(
                cls._flatten_text(
                    [
                        audience_context.get("desired_outcomes", []),
                        audience_context.get("motivations", []),
                        persona_context.get("audience_goals", []),
                        persona_context.get("motivations", []),
                    ]
                )
            )[:6],
            "research_highlights": cls._dedupe_messages(
                cls._flatten_text(
                    [
                        audience_context.get("research_highlights", []),
                        audience_context.get("research_summaries", []),
                        audience_context.get("research_summary", ""),
                    ]
                )
            )[:6],
        }

    @classmethod
    def _important_terms(
        cls,
        persona_context: dict[str, Any] | None,
        objective_context: dict[str, Any] | None,
        message_strategy: dict[str, Any] | None,
        audience_evidence: dict[str, list[str]] | None = None,
    ) -> set[str]:
        persona_context = persona_context or {}
        objective_context = objective_context or {}
        message_strategy = message_strategy or {}
        audience_evidence = audience_evidence or {}
        return cls._extract_terms(
            [
                persona_context.get("audience_goals", []),
                persona_context.get("motivations", []),
                persona_context.get("content_behavior", {}),
                objective_context.get("name"),
                objective_context.get("description"),
                objective_context.get("content_type"),
                objective_context.get("platform_scope", []),
                message_strategy.get("primary_campaign_theme"),
                message_strategy.get("core_audience_message"),
                message_strategy.get("headline_direction"),
                message_strategy.get("supporting_copy_direction"),
                message_strategy.get("cta_intent"),
                message_strategy.get("key_value_proposition"),
                message_strategy.get("important_keywords", []),
                audience_evidence.get("desired_outcomes", []),
                audience_evidence.get("comparison_points", []),
                audience_evidence.get("proof_cues", []),
                audience_evidence.get("trust_signals", []),
            ]
        )

    @classmethod
    def _claim_fragments(cls, content: str, content_payload: dict[str, Any], message_strategy: dict[str, Any] | None) -> list[str]:
        structured_assets = cls._structured_assets(content_payload)
        candidates = [
            content_payload.get("headline"),
            content_payload.get("body"),
            structured_assets.get("supporting_line"),
            (message_strategy or {}).get("headline_direction"),
            (message_strategy or {}).get("supporting_copy_direction"),
            (message_strategy or {}).get("key_value_proposition"),
        ] + [pair["claim"] for pair in structured_assets["claim_evidence_pairs"]] + cls._sentence_list(content)
        claims: list[str] = []
        for fragment in cls._flatten_text(candidates):
            if cls.CLAIM_VERB_PATTERN.search(fragment) or len(fragment.split()) >= 5:
                claims.append(fragment)
        return cls._dedupe_messages(claims)

    @classmethod
    def _concrete_evidence_fragments(cls, evidence_fragments: list[str]) -> list[str]:
        concrete: list[str] = []
        for fragment in evidence_fragments:
            lowered = fragment.lower()
            if cls.PROOF_NUMBER_PATTERN.search(fragment):
                concrete.append(fragment)
                continue
            if cls._match_phrases(lowered, cls.PROOF_MARKERS | cls.TRUST_MARKERS):
                concrete.append(fragment)
        return cls._dedupe_messages(concrete)

    @classmethod
    def _weighted_score_from_dimensions(cls, dimensions: dict[str, int]) -> int:
        weights = {
            "brand_alignment": 0.20,
            "proof_strength": 0.24,
            "objection_handling": 0.18,
            "distinctiveness": 0.16,
            "clarity": 0.10,
            "cta_strength": 0.12,
        }
        weighted_score = sum(dimensions.get(key, 0) * weight for key, weight in weights.items())
        return cls._clamp_score(weighted_score)

    @classmethod
    def _coerce_dimension_score(cls, value: object, fallback: int) -> int:
        try:
            return cls._clamp_score(float(value))
        except (TypeError, ValueError):
            return fallback

    @classmethod
    def _quality_summary(cls, dimensions: dict[str, int], deviations: list[str], matched_signals: list[str]) -> list[str]:
        dimension_messages = {
            "proof_strength": "Proof is too thin relative to the claims being made.",
            "objection_handling": "Copy does not do enough to resolve likely skepticism or friction.",
            "distinctiveness": "Message still feels too generic or samey to stand out.",
            "cta_strength": "CTA is present but not persuasive enough.",
            "clarity": "Message clarity is being hurt by density or weak structure.",
            "brand_alignment": "Brand voice alignment is inconsistent.",
        }
        ordered = sorted(dimensions.items(), key=lambda item: item[1])
        summary: list[str] = []
        for key, value in ordered:
            if value >= 70:
                continue
            summary.append(dimension_messages.get(key, f"{key} needs improvement."))
            if len(summary) >= 3:
                break
        if not summary and matched_signals:
            summary.append("Copy is reasonably aligned, differentiated, and specific for the current brand constraints.")
        if deviations and not summary:
            summary.extend(deviations[:2])
        return cls._dedupe_messages(summary)[:4]

    @classmethod
    def _field_guidance(
        cls,
        *,
        content_payload: dict[str, Any],
        dimensions: dict[str, int],
        generic_hits: list[str],
        structured_assets: dict[str, Any],
        weak_cta: bool,
    ) -> dict[str, list[str]]:
        guidance: dict[str, list[str]] = {key: [] for key in cls.FIELD_GUIDANCE_KEYS}

        if not structured_assets.get("hook_type") or dimensions["distinctiveness"] < 70 or generic_hits:
            guidance["headline"].append(
                "Make the headline carry a clear persuasion angle such as problem-led, proof-led, or contrast-led instead of generic polish."
            )
        if dimensions["proof_strength"] < 72:
            guidance["body"].append(
                "Tie the body's main claim to concrete proof, trust builders, or measurable support instead of leaving the benefit unsupported."
            )
            guidance["metadata"].append(
                "Strengthen claim_evidence_pairs and proof_points so each major promise has a specific supporting reason."
            )
        if dimensions["objection_handling"] < 72:
            guidance["body"].append(
                "Use the body to answer the audience's likely skepticism or effort concern, not just restate the promise."
            )
            guidance["metadata"].append(
                "Add objection_handling lines that reduce risk, switching effort, or uncertainty in plain language."
            )
        if dimensions["clarity"] < 68:
            guidance["body"].append("Shorten the body so each sentence delivers one concrete idea and lands faster.")
        if weak_cta or dimensions["cta_strength"] < 72:
            guidance["cta"].append(
                "Replace generic CTA language with a concrete next step tied to the audience outcome or value exchange."
            )
        if not structured_assets.get("trust_builders"):
            guidance["metadata"].append(
                "Add trust_builders with credibility cues such as compliance, customer proof, implementation reassurance, or operational confidence."
            )
        if not structured_assets.get("proof_points"):
            guidance["metadata"].append(
                "Populate proof_points with concise specifics or differentiated benefits instead of generic adjectives."
            )
        if structured_assets.get("hook_type") and not guidance["headline"]:
            guidance["headline"].append(
                f"Keep the existing {structured_assets['hook_type']} hook explicit, but tighten it around the strongest audience outcome."
            )
        return {
            key: cls._dedupe_messages(value)[:4]
            for key, value in guidance.items()
        }

    def _heuristic_evaluate(
        self,
        content: str,
        brand_context: dict,
        persona_context: dict | None = None,
        *,
        content_payload: dict[str, Any] | None = None,
        message_strategy: dict[str, Any] | None = None,
        objective_context: dict[str, Any] | None = None,
    ) -> dict:
        persona_context = persona_context or {}
        objective_context = objective_context or {}
        message_strategy = message_strategy or {}
        normalized_payload = self._normalize_content_payload(content_payload)
        content = str(content or "").strip() or " ".join(
            part for part in [normalized_payload["headline"], normalized_payload["body"], normalized_payload["cta"]] if part
        )
        content_lower = content.lower()
        voice = brand_context.get("voice_tone", {})
        guardrails = brand_context.get("guardrails", {})
        matched_signals: list[str] = []
        deviations: list[str] = []
        rewrite_suggestions: list[str] = []

        structured_assets = self._structured_assets(normalized_payload)
        audience_evidence = self._audience_evidence_context(brand_context, persona_context)
        evidence_fragments = structured_assets["evidence_fragments"]
        concrete_evidence = self._concrete_evidence_fragments(evidence_fragments)
        claim_fragments = self._claim_fragments(content, normalized_payload, message_strategy)
        generic_hits = self._match_phrases(content_lower, self.GENERIC_PROMO_WORDS)
        repeated_generic_hits = [
            phrase
            for phrase in self.GENERIC_PROMO_WORDS
            if self._phrase_occurrences(content_lower, phrase) >= 2
        ]
        proof_marker_hits = self._match_phrases(" ".join([content_lower] + [item.lower() for item in evidence_fragments]), self.PROOF_MARKERS)
        trust_marker_hits = self._match_phrases(" ".join([content_lower] + [item.lower() for item in evidence_fragments]), self.TRUST_MARKERS)
        sentences = self._sentence_list(content)
        sentence_lengths = [len(sentence.split()) for sentence in sentences]
        average_length = sum(sentence_lengths) / max(len(sentence_lengths), 1)
        important_terms = self._important_terms(
            persona_context,
            objective_context,
            message_strategy,
            audience_evidence=audience_evidence,
        )
        important_hits = [
            term
            for term in important_terms
            if len(term) >= 4 and re.search(rf"\b{re.escape(term)}\b", content_lower)
        ]
        tokens = self._content_tokens(content)
        token_counts = Counter(token for token in tokens if len(token) >= 5)
        repeated_tokens = [token for token, count in token_counts.items() if count >= 3]
        opener_counts: Counter[str] = Counter()
        for sentence in sentences:
            sentence_tokens = self._content_tokens(sentence)
            if len(sentence_tokens) >= 2:
                opener_counts[" ".join(sentence_tokens[:2])] += 1
        repeated_openers = [opener for opener, count in opener_counts.items() if opener and count >= 2]
        samey_copy = bool(
            len(sentences) >= 3 and (len(repeated_tokens) >= 2 or repeated_openers or any(count >= 4 for count in token_counts.values()))
        )

        brand_alignment = 60
        tone_attributes = [str(attr).lower() for attr in voice.get("tone_attributes", []) if str(attr).strip()]
        for attr in tone_attributes:
            if attr in content_lower:
                matched_signals.append(f"Explicit tone marker present: {attr}")
                brand_alignment += 4

        positive_hits = [word for word in guardrails.get("positive_word_bank", []) if str(word).lower() in content_lower]
        matched_signals.extend([f"Positive bank word used: {word}" for word in positive_hits[:5]])
        brand_alignment += min(len(positive_hits), 3) * 2

        negative_hits = [word for word in guardrails.get("negative_word_bank", []) if str(word).lower() in content_lower]
        deviations.extend([f"Negative bank word used: {word}" for word in negative_hits[:5]])
        brand_alignment -= len(negative_hits[:5]) * 8

        blocked_hits = [word for word in guardrails.get("blocked_words", []) if str(word).lower() in content_lower]
        deviations.extend([f"Blocked word used: {word}" for word in blocked_hits])
        brand_alignment -= len(blocked_hits) * 12

        proof_strength = 45
        proof_grounding_targets = (
            audience_evidence["proof_cues"]
            + audience_evidence["trust_signals"]
            + audience_evidence["comparison_points"]
            + audience_evidence["research_highlights"]
        )
        proof_grounding_matches = self._grounding_match_count(
            evidence_fragments + [pair["claim"] for pair in structured_assets["claim_evidence_pairs"]],
            proof_grounding_targets,
        )
        trust_grounding_matches = self._grounding_match_count(
            structured_assets["trust_builders"],
            audience_evidence["trust_signals"] + audience_evidence["proof_cues"] + audience_evidence["research_highlights"],
        )
        if structured_assets["claim_evidence_pairs"]:
            matched_signals.append("Claim/evidence pairs are present in structured metadata")
            proof_strength += 14 if proof_grounding_targets else 24
            if proof_grounding_targets and proof_grounding_matches:
                matched_signals.append("Claim/evidence pairs align with known audience evidence")
                proof_strength += 10
            elif proof_grounding_targets:
                deviations.append("Claim/evidence pairs are present but weakly grounded in known audience evidence")
                rewrite_suggestions.append("Ground claim/evidence pairs in the audience's known proof cues, trust signals, or comparison points.")
                proof_strength -= 6
        if structured_assets["proof_points"]:
            matched_signals.append("Structured proof points are present")
            proof_strength += 10
        if structured_assets["stat_highlights"]:
            matched_signals.append("Structured stat highlights are present")
            proof_strength += 10
        if structured_assets["trust_builders"]:
            matched_signals.append("Structured trust builders are present")
            proof_strength += 4 if proof_grounding_targets else 8
            if trust_grounding_matches:
                matched_signals.append("Trust builders align with known audience trust or proof cues")
                proof_strength += 4
            elif proof_grounding_targets:
                deviations.append("Trust builders are present but not clearly tied to known audience trust or proof cues")
        if concrete_evidence:
            matched_signals.append("Copy includes concrete evidence or credibility signals")
            proof_strength += min(18, len(concrete_evidence) * 6)
        elif proof_marker_hits or trust_marker_hits:
            matched_signals.append("Copy includes proof-oriented or credibility language")
            proof_strength += 6
        if claim_fragments and not (
            structured_assets["claim_evidence_pairs"]
            or concrete_evidence
            or structured_assets["proof_points"]
            or structured_assets["stat_highlights"]
            or structured_assets["trust_builders"]
        ):
            deviations.append("Claims are broad but under-supported by proof, specifics, or evidence")
            rewrite_suggestions.append("Add claim-and-evidence support with concrete proof points, specifics, or measurable outcomes.")
            proof_strength -= 14
        if (len(generic_hits) >= 2 or repeated_generic_hits) and proof_strength < 70:
            deviations.append("Copy leans on generic marketing language instead of differentiated specifics")
            rewrite_suggestions.append("Replace generic marketing language with differentiated specifics, mechanism, or audience-relevant detail.")
            proof_strength -= 8

        objection_targets = audience_evidence["pain_points"] + audience_evidence["objections"]
        objection_handling = 60 if not objection_targets else 45
        response_style_objection_lines = self._response_style_objection_lines(structured_assets["objection_handling"])
        response_text = " ".join(response_style_objection_lines + [normalized_payload["body"], normalized_payload["headline"]]).lower()
        objection_context_text = " ".join(
            structured_assets["objection_handling"] + [normalized_payload["body"], normalized_payload["headline"]]
        ).lower()
        objection_grounding_matches = self._grounding_match_count(
            response_style_objection_lines + [normalized_payload["body"], normalized_payload["headline"]],
            objection_targets,
            mode="objection",
        )
        response_marker_hits = self._match_phrases(response_text or content_lower, self.RESPONSE_MARKERS)
        objection_marker_hits = self._match_phrases(objection_context_text or content_lower, self.OBJECTION_MARKERS)
        if structured_assets["objection_handling"] and response_style_objection_lines:
            matched_signals.append("Structured objection handling includes a visible response")
            objection_handling += 18 if objection_targets else 32
            if objection_targets and objection_grounding_matches:
                matched_signals.append("Objection handling aligns with known audience friction")
                objection_handling += 14
            elif objection_targets:
                deviations.append("Objection handling is present but not clearly tied to known audience friction")
                rewrite_suggestions.append("Anchor objection handling in the audience's actual objections or pain points, not generic reassurance.")
                objection_handling -= 6
        elif objection_targets and objection_grounding_matches and response_marker_hits:
            if structured_assets["objection_handling"]:
                deviations.append("Objection-handling metadata repeats friction without answering it")
                rewrite_suggestions.append("Rewrite objection_handling as a response line that reassures, explains the trade-off, or lowers perceived risk.")
            matched_signals.append("Copy addresses audience friction with a visible response")
            objection_handling += 22
        elif structured_assets["objection_handling"]:
            deviations.append("Objection-handling metadata repeats friction without answering it")
            rewrite_suggestions.append("Rewrite objection_handling as a response line that reassures, explains the trade-off, or lowers perceived risk.")
            objection_handling -= 8
        elif objection_targets and (objection_grounding_matches or response_marker_hits or objection_marker_hits):
            deviations.append("Copy acknowledges friction but does not resolve the objection strongly enough")
            rewrite_suggestions.append("Answer the audience objection with a direct reassurance, trade-off explanation, or reduced-risk next step.")
            objection_handling += 6
        elif objection_targets:
            deviations.append("Copy does not clearly answer the audience's likely objections or pain points")
            rewrite_suggestions.append("Address the biggest audience objection directly with reassurance, trade-off clarity, or risk reduction.")
            objection_handling -= 12

        distinctiveness = 55
        hook_type = structured_assets["hook_type"]
        if hook_type:
            matched_signals.append(f"Hook type is explicit in metadata: {hook_type}")
            distinctiveness += 10
        if important_hits:
            matched_signals.append("Copy reflects audience or objective-specific language")
            distinctiveness += min(12, len(important_hits) * 3)
        if len(generic_hits) >= 2 or repeated_generic_hits:
            distinctiveness -= min(16, max(len(generic_hits), len(repeated_generic_hits)) * 5)
        if samey_copy:
            deviations.append("Copy feels repetitive or samey instead of building momentum")
            rewrite_suggestions.append("Vary sentence openings and compress repeated ideas so each line adds a new reason to care.")
            distinctiveness -= 12

        clarity = 60
        if 7 <= average_length <= 20:
            clarity += 8
        if structured_assets["supporting_line"]:
            clarity += 4
        tone_intensity = voice.get("tone_intensity", {})
        if tone_intensity and average_length < 5:
            deviations.append("Copy is too sparse to express the configured tone well")
            rewrite_suggestions.append("Add a little more substance so the tone can show up without relying on adjectives alone.")
            clarity -= 8
        if average_length > 26:
            deviations.append("Sentence length drifts long for social-ready content")
            rewrite_suggestions.append("Shorten long sentences so the value proposition lands faster.")
            clarity -= 12

        cta_text = normalized_payload["cta"] or content
        cta_strength = 45
        weak_cta = False
        if self.CTA_PATTERN.search(cta_text):
            matched_signals.append("CTA is explicit and action-oriented")
            cta_strength += 24
        else:
            deviations.append("CTA language is weak or missing")
            rewrite_suggestions.append("End with one clear, benefit-linked CTA instead of a passive close.")
            cta_strength -= 10
            weak_cta = True
        if cta_text.strip().lower() in self.GENERIC_CTA_PHRASES:
            deviations.append("CTA is generic and not clearly tied to the audience outcome")
            rewrite_suggestions.append("Replace generic CTA language with a next step that reinforces the value proposition.")
            cta_strength -= 8
            weak_cta = True
        if important_hits and any(re.search(rf"\b{re.escape(term)}\b", cta_text.lower()) for term in important_hits):
            cta_strength += 8
        if len(cta_text.split()) >= 3 and cta_text.strip().lower() not in self.GENERIC_CTA_PHRASES:
            cta_strength += 4

        dimensions = {
            "brand_alignment": self._clamp_score(brand_alignment),
            "proof_strength": self._clamp_score(proof_strength),
            "objection_handling": self._clamp_score(objection_handling),
            "distinctiveness": self._clamp_score(distinctiveness),
            "clarity": self._clamp_score(clarity),
            "cta_strength": self._clamp_score(cta_strength),
        }
        score = self._weighted_score_from_dimensions(dimensions)

        if blocked_hits or negative_hits:
            rewrite_suggestions.insert(0, "Remove blocked or off-brand wording before refining tone or persuasion.")
        if not matched_signals:
            rewrite_suggestions.append("Increase distinctive brand voice markers, not just polished adjectives.")

        field_guidance = self._field_guidance(
            content_payload=normalized_payload,
            dimensions=dimensions,
            generic_hits=generic_hits,
            structured_assets=structured_assets,
            weak_cta=weak_cta,
        )
        quality_summary = self._quality_summary(dimensions, deviations, matched_signals)

        return {
            "score": score,
            "matched_signals": self._dedupe_messages(matched_signals)[:8],
            "deviations": self._dedupe_messages(deviations)[:8],
            "rewrite_suggestions": self._dedupe_messages(rewrite_suggestions)[:8],
            "quality_summary": quality_summary,
            "persuasion_dimensions": dimensions,
            "field_guidance": field_guidance,
        }

    def evaluate(
        self,
        content: str,
        brand_context: dict,
        persona_context: dict | None = None,
        *,
        content_payload: dict[str, Any] | None = None,
        message_strategy: dict[str, Any] | None = None,
        objective_context: dict[str, Any] | None = None,
    ) -> dict:
        fallback = self._heuristic_evaluate(
            content,
            brand_context,
            persona_context,
            content_payload=content_payload,
            message_strategy=message_strategy,
            objective_context=objective_context,
        )
        provider = self.providers.get_text_provider("generation")
        try:
            result = provider.generate_structured_json(
                PromptEnvelope(
                    system=(
                        "Evaluate the content for brand-tone alignment and persuasive quality. "
                        "Return JSON only with keys: score, matched_signals, deviations, rewrite_suggestions, "
                        "quality_summary, persuasion_dimensions, field_guidance. persuasion_dimensions must contain "
                        "integer scores for brand_alignment, proof_strength, objection_handling, distinctiveness, "
                        "clarity, and cta_strength. field_guidance must map headline, body, cta, and metadata to "
                        "lists of short actionable fixes."
                    ),
                    user=(
                        f"Brand context: {brand_context}\n"
                        f"Persona context: {persona_context or {}}\n"
                        f"Objective context: {objective_context or {}}\n"
                        f"Message strategy: {message_strategy or {}}\n"
                        f"Structured content payload: {content_payload or {}}\n"
                        f"Content: {content}\n"
                        "Score 0-100. Be strict about brand safety, tone mismatch, weak CTA, vague persuasion, "
                        "generic marketing filler, unsupported claims, weak proof, repetition or sameness, and "
                        "missing objection handling for the audience. High scores require differentiated, "
                        "evidence-backed copy, not just on-brand vocabulary."
                    ),
                ),
                fallback=fallback,
            )
            provider_dimensions = result.get("persuasion_dimensions") if isinstance(result.get("persuasion_dimensions"), dict) else {}
            merged_dimensions = {
                key: self._clamp_score(
                    (
                        fallback["persuasion_dimensions"][key]
                        + self._coerce_dimension_score(
                            provider_dimensions.get(key, fallback["persuasion_dimensions"][key]),
                            fallback["persuasion_dimensions"][key],
                        )
                    )
                    / 2
                )
                for key in self.DIMENSION_KEYS
            }

            merged_field_guidance: dict[str, list[str]] = {}
            provider_field_guidance = result.get("field_guidance") if isinstance(result.get("field_guidance"), dict) else {}
            for key in self.FIELD_GUIDANCE_KEYS:
                merged_field_guidance[key] = self._dedupe_messages(
                    fallback["field_guidance"].get(key, []) + self._flatten_text(provider_field_guidance.get(key, []))
                )[:4]

            merged_quality_summary = self._dedupe_messages(
                fallback.get("quality_summary", []) + self._flatten_text(result.get("quality_summary", []))
            )[:4]
            provider_score = self._coerce_dimension_score(result.get("score", fallback["score"]), fallback["score"])
            grounded_score = self._weighted_score_from_dimensions(merged_dimensions)

            return {
                "score": self._clamp_score((provider_score + fallback["score"] + grounded_score) / 3),
                "matched_signals": self._dedupe_messages(
                    fallback["matched_signals"] + self._flatten_text(result.get("matched_signals", []))
                )[:8],
                "deviations": self._dedupe_messages(
                    fallback["deviations"] + self._flatten_text(result.get("deviations", []))
                )[:8],
                "rewrite_suggestions": self._dedupe_messages(
                    fallback["rewrite_suggestions"] + self._flatten_text(result.get("rewrite_suggestions", []))
                )[:8],
                "quality_summary": merged_quality_summary,
                "persuasion_dimensions": merged_dimensions,
                "field_guidance": merged_field_guidance,
            }
        except Exception:  # noqa: BLE001
            return fallback
