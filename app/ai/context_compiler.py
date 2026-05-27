from __future__ import annotations

import json
import re
from typing import Any

from app.core.config import get_settings
from app.utils.palette_roles import derive_palette_roles

class ContextCompilerService:
    AUDIENCE_RESEARCH_PRIORITY_FIELDS = (
        "proof_cues",
        "trust_signals",
        "comparison_points",
        "objections",
        "desired_outcomes",
    )
    AUDIENCE_SIGNAL_WEIGHTS = {
        "audience_research": 1.0,
        "persona_defaults": 0.7,
    }

    MAX_KNOWLEDGE_ITEMS = 6
    MAX_VISUAL_KNOWLEDGE_ITEMS = 5
    MAX_KNOWLEDGE_CHARS = 220
    MIN_KNOWLEDGE_SIGNAL_SCORE = 6
    VISUAL_KNOWLEDGE_PRIORITY = (
        "visual_identity",
        "mood_board",
        "reference_creative",
        "template",
        "metadata",
    )
    VISUAL_PRIMARY_CHANNELS = {"visual_identity", "mood_board"}
    VISUAL_SUPPORTING_CHANNELS = {"reference_creative"}
    VISUAL_CHANNEL_ITEM_LIMITS = {
        "visual_identity": 2,
        "mood_board": 2,
        "reference_creative": 1,
        "template": 1,
        "metadata": 1,
    }
    VISUAL_BLOCKED_DOCUMENT_TYPES = {"structured_template_copy"}
    VISUAL_GROUNDING_GATE_VERSION = "v3"
    VISUAL_GROUNDING_THRESHOLD_KEYS = (
        "min_analysis_quality_score",
        "min_summary_quality_score",
        "min_source_agreement_score",
        "min_structured_signal_score",
        "min_visual_grounding_line_count",
    )
    VISUAL_CHANNEL_THRESHOLDS = {
        "visual_identity": {
            "min_analysis_quality_score": 5.0,
            "min_summary_quality_score": 4.8,
            "min_source_agreement_score": 0.16,
            "min_structured_signal_score": 2.0,
            "min_visual_grounding_line_count": 1,
        },
        "mood_board": {
            "min_analysis_quality_score": 4.8,
            "min_summary_quality_score": 4.5,
            "min_source_agreement_score": 0.1,
            "min_structured_signal_score": 2.0,
            "min_visual_grounding_line_count": 1,
        },
        "reference_creative": {
            "min_analysis_quality_score": 4.7,
            "min_summary_quality_score": 4.4,
            "min_source_agreement_score": 0.08,
            "min_structured_signal_score": 2.0,
            "min_visual_grounding_line_count": 1,
        },
        "template": {
            "min_analysis_quality_score": 4.9,
            "min_summary_quality_score": 4.6,
            "min_source_agreement_score": 0.1,
            "min_structured_signal_score": 2.0,
            "min_visual_grounding_line_count": 0,
        },
        "metadata": {
            "min_analysis_quality_score": 4.5,
            "min_summary_quality_score": 4.2,
            "min_source_agreement_score": 0.0,
            "min_structured_signal_score": 1.0,
            "min_visual_grounding_line_count": 0,
        },
    }
    SINGLE_LETTER_RUN_PATTERN = re.compile(r"\b(?:[A-Za-z]\s+){6,}[A-Za-z]\b")
    NUMBER_RUN_PATTERN = re.compile(r"\b(?:\d{1,3}\s+){5,}\d{1,3}\b")
    PX_TOKEN_PATTERN = re.compile(r"\b\d{1,3}px\b", re.IGNORECASE)
    REPEATED_SYMBOL_RUN_PATTERN = re.compile(r"[~!@#$%^&*()_+={}\[\]<>|\\/]{3,}")
    FONT_SPECIMEN_PHRASE_PATTERN = re.compile(r"\b(?:primary|secondary)\s+font\b", re.IGNORECASE)
    FONT_SPECIMEN_MARKERS = {
        "font",
        "fonts",
        "typography",
        "regular",
        "medium",
        "semibold",
        "bold",
        "italic",
        "condensed",
        "uppercase",
        "lowercase",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "px",
    }

    @staticmethod
    def _repair_encoding_noise(text: str) -> str:
        if "Ã" not in text and "â" not in text:
            return text
        try:
            repaired = text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text
        return repaired or text

    @staticmethod
    def _normalize_text(value: Any, limit: int | None = None) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            text = " ".join(value.strip().split())
            text = ContextCompilerService._repair_encoding_noise(text)
        elif isinstance(value, dict):
            text = " ".join(
                str(value.get(key, "")).strip()
                for key in ("label", "name", "summary", "text", "value")
                if value.get(key)
            ).strip()
        elif isinstance(value, (list, tuple, set)):
            text = " ".join(ContextCompilerService._normalize_text(item) for item in value if item)
        else:
            text = str(value).strip()
        if not limit:
            return text
        return text[:limit].rstrip(" ,.;:")

    @staticmethod
    def _looks_like_weak_sequence_hint(text: str) -> bool:
        value = ContextCompilerService._normalize_text(text)
        if not value:
            return True
        lowered = value.casefold()
        if lowered.startswith("layout "):
            return True
        tokens = [token for token in re.split(r"[\s._/-]+", value) if token]
        if tokens and all(token.isdigit() for token in tokens):
            return True
        if re.fullmatch(r"(?:\d{1,4}[.\-_/]?){2,6}", value):
            return True
        return len(re.sub(r"[^a-z0-9]+", "", lowered)) <= 4

    @staticmethod
    def _dedupe_items(items: list[str], limit: int) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in items:
            text = ContextCompilerService._normalize_text(item)
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(text)
            if len(cleaned) >= limit:
                break
        return cleaned

    @staticmethod
    def _truncate_text_on_word_boundary(value: Any, limit: int) -> str:
        text = ContextCompilerService._normalize_text(value)
        if not text or len(text) <= limit:
            return text
        window = text[:limit + 1]
        boundary = window.rfind(" ")
        if boundary >= max(int(limit * 0.6), 1):
            return window[:boundary].rstrip(" ,.;:-")
        return text[:limit].rstrip(" ,.;:-")

    @staticmethod
    def _summary_fragment_key(text: str) -> str:
        return re.sub(r"[.!?]+$", "", text.strip()).casefold()

    @classmethod
    def _compose_summary(cls, values: list[Any], *, item_limit: int, summary_limit: int, max_items: int) -> str:
        sentences: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = cls._truncate_text_on_word_boundary(value, item_limit).strip(" ,.;:-")
            if not text:
                continue
            key = cls._summary_fragment_key(text)
            if not key or key in seen:
                continue
            seen.add(key)
            sentence = text if text[-1] in ".!?" else f"{text}."
            candidate = " ".join([*sentences, sentence]).strip()
            if sentences and len(candidate) > summary_limit:
                break
            if not sentences and len(candidate) > summary_limit:
                return cls._truncate_text_on_word_boundary(text, summary_limit).rstrip(" ,.;:-")
            sentences.append(sentence)
            if len(sentences) >= max_items:
                break
        return " ".join(sentences).strip()

    @classmethod
    def _normalized_text_list(cls, value: Any, *, item_limit: int, limit: int) -> list[str]:
        raw_items = value if isinstance(value, (list, tuple, set)) else [value]
        normalized: list[str] = []
        for item in raw_items:
            text = cls._truncate_text_on_word_boundary(item, item_limit).strip()
            if text:
                normalized.append(text)
        return cls._dedupe_items(normalized, limit=limit)

    @classmethod
    def _sentence_text_list(cls, value: Any, *, item_limit: int, limit: int) -> list[str]:
        raw_items = value if isinstance(value, (list, tuple, set)) else [value]
        sentences: list[str] = []
        for item in raw_items:
            text = cls._normalize_text(item)
            if not text:
                continue
            parts = re.split(r"(?<=[.!?])\s+", text)
            if len(parts) <= 1:
                parts = [text]
            for part in parts:
                normalized = cls._truncate_text_on_word_boundary(part, item_limit).strip(" ,.;:-")
                if not normalized:
                    continue
                sentences.append(normalized if normalized[-1] in ".!?" else f"{normalized}.")
        return cls._dedupe_items(sentences, limit=limit)

    @classmethod
    def _persona_content_behavior_items(cls, value: Any, *, limit: int = 4) -> list[str]:
        items: list[str] = []
        seen: set[str] = set()

        def _append(text: str) -> None:
            normalized = cls._normalize_text(text, limit=96).strip(" ,.;:-")
            if not normalized:
                return
            key = cls._summary_fragment_key(normalized)
            if not key or key in seen:
                return
            seen.add(key)
            items.append(normalized)

        def _value_text(candidate: Any) -> str:
            if candidate in (None, "", [], (), {}):
                return ""
            if isinstance(candidate, bool):
                return "yes" if candidate else "no"
            if isinstance(candidate, (list, tuple, set)):
                parts = [cls._normalize_text(item, limit=36) for item in candidate]
                cleaned = [item for item in parts if item]
                return ", ".join(cleaned[:3])
            if isinstance(candidate, dict):
                preferred_keys = (
                    "summary",
                    "notes",
                    "selected_audiences",
                    "preferred_platforms",
                    "platforms",
                    "channels",
                    "preferred_formats",
                    "content_types",
                    "engagement_triggers",
                    "decision_style",
                    "purchase_stage",
                    "frequency",
                    "cadence",
                    "tone",
                    "cta_preferences",
                    "preferred_length",
                )
                pairs: list[str] = []
                for key in preferred_keys:
                    if key not in candidate:
                        continue
                    rendered = _value_text(candidate.get(key))
                    label = cls._normalize_text(str(key).replace("_", " "), limit=28)
                    if not rendered:
                        continue
                    pairs.append(f"{label}: {rendered}" if label else rendered)
                    if len(pairs) >= 2:
                        break
                if not pairs:
                    for key, item in candidate.items():
                        rendered = _value_text(item)
                        label = cls._normalize_text(str(key).replace("_", " "), limit=28)
                        if not rendered:
                            continue
                        pairs.append(f"{label}: {rendered}" if label else rendered)
                        if len(pairs) >= 2:
                            break
                return "; ".join(pairs)
            return cls._normalize_text(candidate, limit=72)

        if isinstance(value, dict):
            preferred_keys = (
                "summary",
                "notes",
                "selected_audiences",
                "preferred_platforms",
                "platforms",
                "channels",
                "preferred_formats",
                "content_types",
                "engagement_triggers",
                "decision_style",
                "purchase_stage",
                "frequency",
                "cadence",
                "tone",
                "cta_preferences",
                "preferred_length",
            )
            for key in preferred_keys:
                if key not in value:
                    continue
                rendered = _value_text(value.get(key))
                label = cls._normalize_text(str(key).replace("_", " "), limit=28)
                if rendered:
                    _append(f"{label}: {rendered}" if label and rendered.casefold() != label.casefold() else rendered)
                if len(items) >= limit:
                    return items[:limit]
            if not items:
                for key, candidate in value.items():
                    rendered = _value_text(candidate)
                    label = cls._normalize_text(str(key).replace("_", " "), limit=28)
                    if rendered:
                        _append(f"{label}: {rendered}" if label and rendered.casefold() != label.casefold() else rendered)
                    if len(items) >= limit:
                        break
            return items[:limit]

        if isinstance(value, (list, tuple, set)):
            for candidate in value:
                rendered = _value_text(candidate)
                if rendered:
                    _append(rendered)
                if len(items) >= limit:
                    break
            return items[:limit]

        rendered = _value_text(value)
        if rendered:
            _append(rendered)
        return items[:limit]

    @classmethod
    def _persona_summary(cls, persona_context: dict[str, Any]) -> str:
        if not isinstance(persona_context, dict):
            return ""
        goals = cls._normalized_text_list(persona_context.get("audience_goals"), item_limit=88, limit=2)
        motivations = cls._normalized_text_list(persona_context.get("motivations"), item_limit=88, limit=2)
        pain_points = cls._normalized_text_list(persona_context.get("fears_and_pain_points"), item_limit=88, limit=2)
        objections = cls._normalized_text_list(persona_context.get("objections"), item_limit=88, limit=2)
        behaviors = cls._persona_content_behavior_items(persona_context.get("content_behavior"), limit=2)
        language_preference = cls._normalize_text(persona_context.get("language_preference"), limit=40)
        return cls._compose_summary(
            [
                *goals[:1],
                *motivations[:2],
                *pain_points[:2],
                *objections[:1],
                *behaviors[:2],
                f"Language preference: {language_preference}" if language_preference else "",
            ],
            item_limit=96,
            summary_limit=260,
            max_items=4,
        )

    @classmethod
    def _audience_research_items(cls, audience: dict[str, Any]) -> list[str]:
        if not isinstance(audience, dict):
            return []
        lanes: dict[str, list[str]] = {
            "proof_cues": [],
            "trust_signals": [],
            "comparison_points": [],
            "objections": [],
            "desired_outcomes": [],
            "highlights": cls._sentence_text_list(audience.get("research_highlights"), item_limit=148, limit=6),
            "summaries": cls._sentence_text_list(audience.get("research_summaries"), item_limit=148, limit=6),
            "summary": cls._sentence_text_list(audience.get("research_summary"), item_limit=148, limit=3),
            "general": [],
        }

        raw_evidence = audience.get("research_evidence")
        evidence_items: list[dict[str, Any]] = raw_evidence if isinstance(raw_evidence, list) else []
        for item in sorted(
            [entry for entry in evidence_items if isinstance(entry, dict)],
            key=lambda entry: (
                cls._audience_research_priority(entry.get("field")),
                -float(entry.get("ranking_score") or 0.0),
                -float(entry.get("confidence") or 0.0),
                -float(entry.get("source_agreement_score") or 0.0),
                -float(entry.get("analysis_quality_score") or 0.0),
                -float(entry.get("evidence_confidence") or 0.0),
                -float(entry.get("research_signal_count") or 0.0),
                str(entry.get("value") or ""),
            ),
        ):
            field = str(item.get("field") or "").strip().casefold()
            value = item.get("value")
            lane_name = field if field in lanes else "general"
            lanes[lane_name].extend(cls._sentence_text_list(value, item_limit=148, limit=2))

        for field in cls.AUDIENCE_RESEARCH_PRIORITY_FIELDS:
            lanes[field].extend(cls._sentence_text_list(audience.get(field), item_limit=148, limit=4))
            lanes[field] = cls._dedupe_items(lanes[field], limit=6)
        lanes["general"] = cls._dedupe_items(lanes["general"], limit=6)

        merged: list[str] = []
        seen: set[str] = set()
        positions = {lane_name: 0 for lane_name in lanes}

        def _append_from_lane(lane_name: str) -> bool:
            lane = lanes.get(lane_name, [])
            index = positions[lane_name]
            while index < len(lane):
                candidate = lane[index]
                index += 1
                key = cls._summary_fragment_key(candidate)
                if not key or key in seen:
                    continue
                positions[lane_name] = index
                seen.add(key)
                merged.append(candidate)
                return True
            positions[lane_name] = index
            return False

        first_pass_order = (
            "proof_cues",
            "highlights",
            "trust_signals",
            "highlights",
            "comparison_points",
            "objections",
            "desired_outcomes",
            "summaries",
            "summary",
            "general",
        )
        fill_order = (
            "proof_cues",
            "trust_signals",
            "comparison_points",
            "objections",
            "desired_outcomes",
            "highlights",
            "summaries",
            "summary",
            "general",
        )
        for lane_name in first_pass_order:
            if len(merged) >= 6:
                break
            _append_from_lane(lane_name)

        while len(merged) < 6:
            progressed = False
            for lane_name in fill_order:
                if len(merged) >= 6:
                    break
                progressed = _append_from_lane(lane_name) or progressed
            if not progressed:
                break
        return merged[:6]

    @classmethod
    def _audience_research_priority(cls, field: Any) -> int:
        normalized = str(field or "").strip().casefold()
        try:
            return cls.AUDIENCE_RESEARCH_PRIORITY_FIELDS.index(normalized)
        except ValueError:
            return len(cls.AUDIENCE_RESEARCH_PRIORITY_FIELDS)

    @staticmethod
    def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
        text = str(value or "").strip()
        if not re.fullmatch(r"#?[0-9a-fA-F]{6}", text):
            return None
        normalized = text[1:] if text.startswith("#") else text
        return tuple(int(normalized[index:index + 2], 16) for index in range(0, 6, 2))

    @classmethod
    def _derived_palette_roles(cls, visual_identity: dict[str, Any]) -> dict[str, str]:
        return derive_palette_roles(visual_identity)

    @classmethod
    def _clean_knowledge_content(cls, value: Any, limit: int | None = None) -> str:
        text = cls._normalize_text(value)
        if not text:
            return ""
        text = cls.SINGLE_LETTER_RUN_PATTERN.sub(" ", text)
        text = cls.NUMBER_RUN_PATTERN.sub(" ", text)
        text = cls.PX_TOKEN_PATTERN.sub(" ", text)
        text = re.sub(r"\bH[1-6]\b", " ", text, flags=re.IGNORECASE)
        text = cls.REPEATED_SYMBOL_RUN_PATTERN.sub(" ", text)
        text = re.sub(r"\s{2,}", " ", text).strip(" ,.;:-")
        if not text:
            return ""
        tokens = re.findall(r"[A-Za-z0-9#'+/-]+", text)
        specimen_markers = [token for token in tokens if token.lower() in cls.FONT_SPECIMEN_MARKERS]
        if cls.FONT_SPECIMEN_PHRASE_PATTERN.search(text) and len(specimen_markers) >= 3:
            return ""
        return cls._normalize_text(text, limit=limit)

    @classmethod
    def _knowledge_signal_score(cls, value: Any) -> int:
        text = cls._normalize_text(value)
        if not text:
            return -999
        tokens = re.findall(r"[A-Za-z0-9#'+/-]+", text)
        if not tokens:
            return -999
        alpha_tokens = [token for token in tokens if re.search(r"[A-Za-z]", token)]
        long_alpha_tokens = [token for token in alpha_tokens if len(re.sub(r"[^A-Za-z]", "", token)) >= 4]
        single_alpha_tokens = [token for token in alpha_tokens if len(re.sub(r"[^A-Za-z]", "", token)) == 1]
        digit_tokens = [token for token in tokens if any(character.isdigit() for character in token)]
        specimen_markers = [token for token in alpha_tokens if token.lower() in cls.FONT_SPECIMEN_MARKERS]
        score = (len(long_alpha_tokens) * 3) + len(alpha_tokens)
        score -= len(single_alpha_tokens) * 4
        score -= len(digit_tokens) * 2
        score -= len(specimen_markers) * 2
        if cls.SINGLE_LETTER_RUN_PATTERN.search(text):
            score -= 24
        if cls.NUMBER_RUN_PATTERN.search(text):
            score -= 12
        if cls.FONT_SPECIMEN_PHRASE_PATTERN.search(text) and len(specimen_markers) >= 3:
            score -= 24
        if len(alpha_tokens) < 4:
            score -= 10
        if len("".join(character for character in text if character.isalpha())) < 20:
            score -= 8
        return score

    @staticmethod
    def _entry_metadata(entry: dict[str, Any]) -> dict[str, Any]:
        metadata = entry.get("metadata")
        return metadata if isinstance(metadata, dict) else {}

    @staticmethod
    def _metadata_float(metadata: dict[str, Any], key: str) -> float:
        try:
            return float(metadata.get(key) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _metadata_int(metadata: dict[str, Any], key: str) -> int:
        try:
            return int(metadata.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _coerce_non_negative_int(value: Any) -> int:
        try:
            return max(int(value or 0), 0)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _visual_grounding_runtime_config(cls) -> dict[str, Any]:
        settings = get_settings()
        thresholds = {
            channel: dict(values)
            for channel, values in cls.VISUAL_CHANNEL_THRESHOLDS.items()
        }
        raw_overrides = getattr(settings, "visual_grounding_threshold_overrides_json", None)
        if isinstance(raw_overrides, str) and raw_overrides.strip():
            try:
                payload = json.loads(raw_overrides)
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                for channel, overrides in payload.items():
                    normalized_channel = cls._normalize_text(channel, limit=32).casefold()
                    if not normalized_channel or not isinstance(overrides, dict):
                        continue
                    merged = dict(
                        thresholds.get(normalized_channel)
                        or thresholds.get("metadata")
                        or {}
                    )
                    for key in cls.VISUAL_GROUNDING_THRESHOLD_KEYS:
                        if key not in overrides:
                            continue
                        try:
                            if key == "min_visual_grounding_line_count":
                                merged[key] = max(0, int(overrides.get(key) or 0))
                            else:
                                merged[key] = max(0.0, float(overrides.get(key) or 0.0))
                        except (TypeError, ValueError):
                            continue
                    thresholds[normalized_channel] = merged
        require_quality_metadata = bool(
            getattr(settings, "visual_grounding_require_quality_metadata", False)
        )
        return {
            "gate_version": cls.VISUAL_GROUNDING_GATE_VERSION,
            "thresholds": thresholds,
            "quality_metadata_policy": "required" if require_quality_metadata else "compatibility_mode",
            "require_quality_metadata": require_quality_metadata,
        }

    @staticmethod
    def _has_visual_quality_metadata(metadata: dict[str, Any]) -> bool:
        return any(
            key in metadata
            for key in (
                "analysis_quality_score",
                "summary_quality_score",
                "source_agreement_score",
                "structured_signal_score",
                "visual_grounding_line_count",
            )
        )

    @classmethod
    def _low_quality_exclusion_reason(cls, metadata: dict[str, Any]) -> str:
        document_type = str(metadata.get("document_type") or "").strip().lower()
        if document_type != "raw_ocr":
            return ""
        analysis_quality_score = cls._metadata_float(metadata, "analysis_quality_score")
        summary_quality_score = cls._metadata_float(metadata, "summary_quality_score")
        ocr_noise_ratio = cls._metadata_float(metadata, "ocr_noise_ratio")
        promotional_line_ratio = cls._metadata_float(metadata, "promotional_line_ratio")
        if promotional_line_ratio >= 0.35 and analysis_quality_score < 5.5:
            return "quality_below_channel_floor"
        if ocr_noise_ratio >= 0.75 and summary_quality_score < 4.5:
            return "quality_below_channel_floor"
        return ""

    @classmethod
    def _should_exclude_low_quality_entry(cls, metadata: dict[str, Any]) -> bool:
        return bool(cls._low_quality_exclusion_reason(metadata))

    @classmethod
    def _visual_channel_gate(cls, channel: str, metadata: dict[str, Any]) -> tuple[bool, str]:
        normalized_channel = cls._normalize_text(channel, limit=32).casefold()
        if not cls._visual_grounding_allowed(normalized_channel, metadata):
            return False, "visual_grounding_blocked"
        thresholds = cls._visual_grounding_runtime_config()["thresholds"].get(
            normalized_channel,
            {
                "min_analysis_quality_score": 4.5,
                "min_summary_quality_score": 4.2,
                "min_source_agreement_score": 0.0,
                "min_structured_signal_score": 1.0,
                "min_visual_grounding_line_count": 0,
            },
        )
        document_type = cls._normalize_text(metadata.get("document_type"), limit=48).casefold()
        analysis_quality_score = cls._metadata_float(metadata, "analysis_quality_score")
        summary_quality_score = cls._metadata_float(metadata, "summary_quality_score")
        source_agreement_score = cls._metadata_float(metadata, "source_agreement_score")
        structured_signal_score = cls._metadata_float(metadata, "structured_signal_score")
        visual_grounding_line_count = cls._metadata_int(metadata, "visual_grounding_line_count")
        promotional_line_ratio = cls._metadata_float(metadata, "promotional_line_ratio")

        quality_floor_met = (
            analysis_quality_score >= float(thresholds["min_analysis_quality_score"])
            or summary_quality_score >= float(thresholds["min_summary_quality_score"])
        )
        structured_floor_met = structured_signal_score >= float(thresholds["min_structured_signal_score"])
        agreement_floor_met = source_agreement_score >= float(thresholds["min_source_agreement_score"])
        line_floor_met = visual_grounding_line_count >= int(thresholds["min_visual_grounding_line_count"])

        if not quality_floor_met and not structured_floor_met:
            return False, "quality_below_channel_floor"
        if (
            normalized_channel != "metadata"
            and not agreement_floor_met
            and not structured_floor_met
            and not line_floor_met
        ):
            return False, "weak_cross_source_evidence"
        if promotional_line_ratio >= 0.45 and not agreement_floor_met and structured_signal_score < float(thresholds["min_structured_signal_score"]) + 1.0:
            return False, "promotional_bias_without_corroboration"
        if document_type == "raw_ocr" and not agreement_floor_met and analysis_quality_score < 6.0:
            return False, "raw_ocr_without_corroboration"
        return True, ""

    @classmethod
    def _knowledge_entry_rank(cls, entry: dict[str, Any], content: str, text_signal_score: int | None = None) -> float:
        metadata = cls._entry_metadata(entry)
        text_signal = float(text_signal_score if text_signal_score is not None else cls._knowledge_signal_score(content))
        raw_distance = entry.get("score")
        try:
            distance = max(float(raw_distance), 0.0) if raw_distance is not None else None
        except (TypeError, ValueError):
            distance = None
        retrieval_bonus = (18.0 / (1.0 + distance)) if distance is not None else 0.0
        validation_state = str(metadata.get("validation_state") or "").strip().lower()
        validation_bonus = {
            "clean": 8.0,
            "warning": 2.0,
            "excluded": -20.0,
        }.get(validation_state, 0.0)
        try:
            confidence = max(0.0, min(float(metadata.get("classification_confidence") or 0.0), 1.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence_bonus = confidence * 8.0
        document_type = str(metadata.get("document_type") or "").strip().lower()
        document_type_bonus = {
            "structured_layout": 10.0,
            "structured_palette": 11.0,
            "structured_summary": 12.0,
            "structured_labels": 8.0,
            "structured_typography": 10.0,
            "structured_visual_unit": 10.5,
            "structured_template_copy": -6.0,
            "raw_ocr": 0.0,
        }.get(document_type, 0.0)
        try:
            structured_signal = max(float(metadata.get("structured_signal_score") or 0.0), 0.0)
        except (TypeError, ValueError):
            structured_signal = 0.0
        structured_bonus = min(structured_signal, 10.0)
        try:
            template_brand_score = max(float(metadata.get("template_brand_score") or 0.0), 0.0)
        except (TypeError, ValueError):
            template_brand_score = 0.0
        try:
            analysis_quality_score = max(float(metadata.get("analysis_quality_score") or 0.0), 0.0)
        except (TypeError, ValueError):
            analysis_quality_score = 0.0
        try:
            summary_quality_score = max(float(metadata.get("summary_quality_score") or 0.0), 0.0)
        except (TypeError, ValueError):
            summary_quality_score = 0.0
        try:
            source_agreement_score = max(float(metadata.get("source_agreement_score") or 0.0), 0.0)
        except (TypeError, ValueError):
            source_agreement_score = 0.0
        try:
            ocr_signal_score = max(float(metadata.get("ocr_signal_score") or 0.0), 0.0)
        except (TypeError, ValueError):
            ocr_signal_score = 0.0
        try:
            visual_grounding_line_count = max(float(metadata.get("visual_grounding_line_count") or 0.0), 0.0)
        except (TypeError, ValueError):
            visual_grounding_line_count = 0.0
        try:
            template_copy_line_count = max(float(metadata.get("template_copy_line_count") or 0.0), 0.0)
        except (TypeError, ValueError):
            template_copy_line_count = 0.0
        try:
            ocr_noise_ratio = max(float(metadata.get("ocr_noise_ratio") or 0.0), 0.0)
        except (TypeError, ValueError):
            ocr_noise_ratio = 0.0
        try:
            promotional_line_ratio = max(float(metadata.get("promotional_line_ratio") or 0.0), 0.0)
        except (TypeError, ValueError):
            promotional_line_ratio = 0.0
        evidence_types = metadata.get("evidence_types") if isinstance(metadata.get("evidence_types"), list) else []
        visual_grounding_penalty = 3.0 if metadata.get("visual_grounding_allowed") is False else 0.0
        evidence_bonus = min(len([item for item in evidence_types if str(item).strip()]), 5) * 0.8
        analysis_bonus = min(analysis_quality_score, 10.0) * 1.1
        summary_bonus = min(summary_quality_score, 10.0) * 0.85
        source_agreement_bonus = min(source_agreement_score, 1.0) * 10.0
        ocr_signal_bonus = min(ocr_signal_score, 10.0) * 0.45
        visual_line_bonus = min(visual_grounding_line_count, 4.0) * 0.45
        noise_penalty = min(ocr_noise_ratio, 1.0) * 12.0
        promotional_penalty = min(promotional_line_ratio, 1.0) * 10.0
        template_copy_penalty = min(template_copy_line_count, 4.0) * 0.35
        raw_ocr_penalty = 3.5 if document_type == "raw_ocr" and analysis_quality_score < 6.0 else 0.0
        return (
            text_signal
            + retrieval_bonus
            + validation_bonus
            + confidence_bonus
            + document_type_bonus
            + structured_bonus
            + template_brand_score
            + analysis_bonus
            + summary_bonus
            + source_agreement_bonus
            + ocr_signal_bonus
            + visual_line_bonus
            + evidence_bonus
            - noise_penalty
            - promotional_penalty
            - template_copy_penalty
            - raw_ocr_penalty
            - visual_grounding_penalty
        )

    @classmethod
    def _ranked_knowledge_records(
        cls,
        entries: list[dict[str, Any]],
        *,
        per_channel_limit: int,
    ) -> list[dict[str, Any]]:
        ranked_entries: list[dict[str, Any]] = []
        seen_content: set[str] = set()
        seen_sources: set[str] = set()
        cleaned_entries: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            content = cls._clean_knowledge_content(entry.get("content"), limit=cls.MAX_KNOWLEDGE_CHARS)
            if not content:
                continue
            score = cls._knowledge_signal_score(content)
            if score < cls.MIN_KNOWLEDGE_SIGNAL_SCORE:
                continue
            metadata = cls._entry_metadata(entry)
            if cls._should_exclude_low_quality_entry(metadata):
                continue
            source_key = cls._normalize_text(
                metadata.get("source_id") or metadata.get("asset_id") or metadata.get("filename"),
                limit=96,
            )
            ranked_entries.append(
                {
                    "content": content,
                    "source_key": source_key,
                    "rank_score": round(cls._knowledge_entry_rank(entry, content, score), 4),
                    "metadata": metadata,
                }
            )
        ranked_entries.sort(key=lambda item: float(item.get("rank_score") or 0.0), reverse=True)
        for item in ranked_entries:
            content = str(item.get("content") or "")
            source_key = str(item.get("source_key") or "")
            key = content.casefold()
            if key in seen_content:
                continue
            source_key_normalized = source_key.casefold() if source_key else ""
            if source_key_normalized and source_key_normalized in seen_sources:
                continue
            seen_content.add(key)
            if source_key_normalized:
                seen_sources.add(source_key_normalized)
            cleaned_entries.append(item)
            if len(cleaned_entries) >= per_channel_limit:
                break
        return cleaned_entries

    @classmethod
    def _ranked_knowledge_entries(
        cls,
        entries: list[dict[str, Any]],
        *,
        per_channel_limit: int,
    ) -> list[str]:
        return [
            str(item.get("content") or "")
            for item in cls._ranked_knowledge_records(entries, per_channel_limit=per_channel_limit)
            if str(item.get("content") or "").strip()
        ]

    @classmethod
    def _ranked_visual_knowledge_candidates(
        cls,
        entries: list[dict[str, Any]],
        *,
        per_channel_limit: int,
    ) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
        ranked_entries: list[dict[str, Any]] = []
        seen_content: set[str] = set()
        seen_sources: set[str] = set()
        cleaned_entries: list[dict[str, Any]] = []
        rejection_reasons: dict[str, int] = {}
        candidate_count = 0
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            content = cls._clean_knowledge_content(entry.get("content"), limit=cls.MAX_KNOWLEDGE_CHARS)
            if not content:
                continue
            score = cls._knowledge_signal_score(content)
            if score < cls.MIN_KNOWLEDGE_SIGNAL_SCORE:
                continue
            metadata = cls._entry_metadata(entry)
            candidate_count += 1
            early_reason = cls._low_quality_exclusion_reason(metadata)
            if early_reason:
                rejection_reasons[early_reason] = int(rejection_reasons.get(early_reason) or 0) + 1
                continue
            source_key = cls._normalize_text(
                metadata.get("source_id") or metadata.get("asset_id") or metadata.get("filename"),
                limit=96,
            )
            ranked_entries.append(
                {
                    "content": content,
                    "source_key": source_key,
                    "rank_score": round(cls._knowledge_entry_rank(entry, content, score), 4),
                    "metadata": metadata,
                }
            )
        ranked_entries.sort(key=lambda item: float(item.get("rank_score") or 0.0), reverse=True)
        for item in ranked_entries:
            content = str(item.get("content") or "")
            source_key = str(item.get("source_key") or "")
            key = content.casefold()
            if key in seen_content:
                continue
            source_key_normalized = source_key.casefold() if source_key else ""
            if source_key_normalized and source_key_normalized in seen_sources:
                continue
            seen_content.add(key)
            if source_key_normalized:
                seen_sources.add(source_key_normalized)
            cleaned_entries.append(item)
            if len(cleaned_entries) >= per_channel_limit:
                break
        return cleaned_entries, candidate_count, rejection_reasons

    @classmethod
    def _visual_grounding_role(cls, channel: str) -> str:
        normalized = cls._normalize_text(channel, limit=32).casefold()
        if normalized in cls.VISUAL_PRIMARY_CHANNELS:
            return "primary"
        if normalized in cls.VISUAL_SUPPORTING_CHANNELS:
            return "supporting"
        return "fallback"

    @classmethod
    def _visual_grounding_allowed(cls, channel: str, metadata: dict[str, Any]) -> bool:
        if metadata.get("visual_grounding_allowed") is False:
            return False
        document_type = cls._normalize_text(metadata.get("document_type"), limit=48).casefold()
        if document_type in cls.VISUAL_BLOCKED_DOCUMENT_TYPES:
            return False
        return bool(cls._normalize_text(channel, limit=32))

    @classmethod
    def _visual_grounding_strength(cls, items: list[dict[str, Any]]) -> str:
        channels = {
            cls._normalize_text(item.get("channel"), limit=32).casefold()
            for item in items
            if isinstance(item, dict)
        }
        if not channels:
            return "none"
        if channels & cls.VISUAL_PRIMARY_CHANNELS:
            return "strong" if len(items) >= 2 else "supported"
        if channels & cls.VISUAL_SUPPORTING_CHANNELS:
            return "supported"
        return "fallback_only"

    @classmethod
    def _visual_knowledge_summary(cls, items: list[dict[str, Any]]) -> str:
        parts = [
            f"{cls._normalize_text(item.get('channel'), limit=32)}: {cls._normalize_text(item.get('content'), limit=180)}"
            for item in items[:4]
            if isinstance(item, dict)
            and cls._normalize_text(item.get("channel"), limit=32)
            and cls._normalize_text(item.get("content"), limit=180)
        ]
        return " | ".join(parts)

    @classmethod
    def _normalize_visual_rejection_reasons(cls, value: Any) -> dict[str, int]:
        reasons: dict[str, int] = {}
        if not isinstance(value, dict):
            return reasons
        for key, count in value.items():
            reason = cls._normalize_text(key, limit=64)
            if not reason:
                continue
            try:
                normalized_count = int(count or 0)
            except (TypeError, ValueError):
                continue
            if normalized_count <= 0:
                continue
            reasons[reason] = normalized_count
        return dict(sorted(reasons.items()))

    @classmethod
    def _visual_brief_item(
        cls,
        *,
        channel: str,
        content: Any,
        metadata: dict[str, Any],
        rank_score: Any = 0.0,
        role: str | None = None,
    ) -> dict[str, Any]:
        normalized_channel = cls._normalize_text(channel, limit=32).casefold()
        source_id = cls._normalize_text(
            metadata.get("source_id") or metadata.get("asset_id") or metadata.get("filename"),
            limit=96,
        )
        try:
            normalized_rank = round(float(rank_score or 0.0), 4)
        except (TypeError, ValueError):
            normalized_rank = 0.0
        return {
            "channel": normalized_channel,
            "role": cls._normalize_text(role, limit=24).casefold() or cls._visual_grounding_role(normalized_channel),
            "content": cls._clean_knowledge_content(content, limit=cls.MAX_KNOWLEDGE_CHARS),
            "document_type": cls._normalize_text(metadata.get("document_type"), limit=48).casefold(),
            "source_id": source_id,
            "rank_score": normalized_rank,
        }

    @classmethod
    def _select_visual_brief_items(
        cls,
        grouped: dict[str, list[dict[str, Any]]],
        *,
        overflow: list[dict[str, Any]] | None = None,
        rejection_reasons: dict[str, int] | None = None,
    ) -> tuple[list[dict[str, Any]], bool, dict[str, int]]:
        rejection_counts = dict(rejection_reasons or {})
        grouped_items = {
            cls._normalize_text(channel, limit=32).casefold(): [
                item for item in (items or []) if isinstance(item, dict)
            ]
            for channel, items in grouped.items()
        }
        overflow_items = [item for item in (overflow or []) if isinstance(item, dict)]
        has_primary_visual_evidence = any(
            grouped_items.get(channel)
            for channel in cls.VISUAL_PRIMARY_CHANNELS
        )
        template_items = grouped_items.get("template") or []
        template_suppressed = bool(has_primary_visual_evidence and template_items)
        if template_suppressed:
            rejection_counts["template_suppressed_by_primary_evidence"] = (
                int(rejection_counts.get("template_suppressed_by_primary_evidence") or 0)
                + len(template_items)
            )
            grouped_items["template"] = []

        items: list[dict[str, Any]] = []
        capacity_rejections = 0
        for channel in cls.VISUAL_KNOWLEDGE_PRIORITY:
            channel_items = grouped_items.get(channel, [])
            if not channel_items:
                continue
            channel_limit = cls.VISUAL_CHANNEL_ITEM_LIMITS.get(channel, 1)
            allowed_items = channel_items[:channel_limit]
            capacity_rejections += max(0, len(channel_items) - len(allowed_items))
            remaining_capacity = cls.MAX_VISUAL_KNOWLEDGE_ITEMS - len(items)
            if remaining_capacity <= 0:
                capacity_rejections += len(allowed_items)
                break
            items.extend(allowed_items[:remaining_capacity])
            capacity_rejections += max(0, len(allowed_items) - remaining_capacity)
            if len(items) >= cls.MAX_VISUAL_KNOWLEDGE_ITEMS:
                break
        if len(items) < cls.MAX_VISUAL_KNOWLEDGE_ITEMS and overflow_items:
            remaining_capacity = cls.MAX_VISUAL_KNOWLEDGE_ITEMS - len(items)
            items.extend(overflow_items[:remaining_capacity])
            capacity_rejections += max(0, len(overflow_items) - remaining_capacity)
        elif overflow_items:
            capacity_rejections += len(overflow_items)
        if capacity_rejections > 0:
            rejection_counts["selection_capacity_limit"] = (
                int(rejection_counts.get("selection_capacity_limit") or 0)
                + capacity_rejections
            )
        return items, template_suppressed, cls._normalize_visual_rejection_reasons(rejection_counts)

    @classmethod
    def _visual_abstention_reason(
        cls,
        *,
        items: list[dict[str, Any]],
        candidate_count: int,
        rejection_reasons: dict[str, int],
    ) -> str:
        if items:
            return ""
        if candidate_count <= 0:
            return "no_visual_brand_evidence"
        filtered_reasons = {
            reason: count
            for reason, count in rejection_reasons.items()
            if reason != "selection_capacity_limit" and int(count or 0) > 0
        }
        if len(filtered_reasons) == 1:
            return next(iter(filtered_reasons))
        return "no_eligible_visual_brand_evidence"

    @classmethod
    def _research_editorial_brief(cls, value: Any) -> dict[str, Any]:
        brief = value if isinstance(value, dict) else {}
        fact_model = brief.get("fact_model") if isinstance(brief.get("fact_model"), dict) else {}
        source_pack = []
        for item in (brief.get("source_pack") or [])[:6]:
            if not isinstance(item, dict):
                continue
            source_pack.append(
                {
                    "type": cls._normalize_text(item.get("type"), limit=24),
                    "label": cls._normalize_text(item.get("label"), limit=140),
                    "detail": cls._truncate_text_on_word_boundary(item.get("detail"), 220),
                    "source": cls._normalize_text(item.get("source"), limit=180),
                }
            )
        ranked_sources = []
        for item in (brief.get("ranked_sources") or [])[:4]:
            if not isinstance(item, dict):
                continue
            ranked_sources.append(
                {
                    "label": cls._normalize_text(item.get("label"), limit=140),
                    "detail": cls._truncate_text_on_word_boundary(item.get("detail"), 180),
                    "source": cls._normalize_text(item.get("source"), limit=180),
                }
            )
        outline = []
        for item in (brief.get("outline") or [])[:8]:
            if not isinstance(item, dict):
                continue
            outline.append(
                {
                    "index": cls._normalize_text(item.get("index"), limit=8),
                    "role": cls._normalize_text(item.get("role"), limit=32),
                    "purpose": cls._truncate_text_on_word_boundary(item.get("purpose"), 180),
                }
            )
        sample_editorial = brief.get("sample_editorial_brief") if isinstance(brief.get("sample_editorial_brief"), dict) else {}
        return {
            "active": bool(brief.get("active")),
            "mode": cls._normalize_text(brief.get("mode"), limit=32),
            "deliverable_type": cls._normalize_text(brief.get("deliverable_type"), limit=32),
            "platform_preset": cls._normalize_text(brief.get("platform_preset"), limit=32),
            "format": cls._normalize_text(brief.get("format"), limit=32),
            "format_family": cls._normalize_text(brief.get("format_family"), limit=32),
            "editorial_style": cls._normalize_text(brief.get("editorial_style"), limit=48),
            "topic_focus": cls._truncate_text_on_word_boundary(brief.get("topic_focus"), 180),
            "angle": cls._truncate_text_on_word_boundary(brief.get("angle"), 220),
            "thesis": cls._truncate_text_on_word_boundary(brief.get("thesis"), 260),
            "reader_payoff": cls._truncate_text_on_word_boundary(brief.get("reader_payoff"), 220),
            "hook_strategy": cls._truncate_text_on_word_boundary(brief.get("hook_strategy"), 220),
            "insight_hierarchy": cls._normalized_text_list(
                brief.get("insight_hierarchy"),
                item_limit=180,
                limit=6,
            ),
            "ordered_story_beats": cls._normalized_text_list(
                brief.get("ordered_story_beats"),
                item_limit=180,
                limit=8,
            ),
            "narrative_contract": cls._normalize_text(brief.get("narrative_contract"), limit=48),
            "outline": outline,
            "sample_editorial_brief": {
                "source": cls._normalize_text(sample_editorial.get("source"), limit=32),
                "family_name": cls._normalize_text(sample_editorial.get("family_name"), limit=72),
                "slide_count": int(sample_editorial.get("slide_count") or 0) or None,
                "story_roles": cls._normalized_text_list(sample_editorial.get("story_roles"), item_limit=40, limit=8),
                "headline_patterns": cls._normalized_text_list(sample_editorial.get("headline_patterns"), item_limit=120, limit=6),
                "sample_summaries": cls._normalized_text_list(sample_editorial.get("sample_summaries"), item_limit=160, limit=6),
                "explanation_styles": cls._normalized_text_list(sample_editorial.get("explanation_styles"), item_limit=48, limit=4),
                "copy_densities": cls._normalized_text_list(sample_editorial.get("copy_densities"), item_limit=24, limit=4),
                "closing_styles": cls._normalized_text_list(sample_editorial.get("closing_styles"), item_limit=32, limit=4),
                "proof_module_count": int(sample_editorial.get("proof_module_count") or 0) or None,
            },
            "fact_model": {
                "verified_facts": [
                    {
                        "label": cls._normalize_text(item.get("label"), limit=120),
                        "value": cls._truncate_text_on_word_boundary(item.get("value"), 180),
                        "source_title": cls._normalize_text(item.get("source_title"), limit=140),
                        "source_url": cls._normalize_text(item.get("source_url"), limit=220),
                    }
                    for item in (fact_model.get("verified_facts") or [])[:6]
                    if isinstance(item, dict)
                ],
                "inferences": cls._normalized_text_list(fact_model.get("inferences"), item_limit=180, limit=4),
                "uncertainties": cls._normalized_text_list(fact_model.get("uncertainties"), item_limit=180, limit=4),
            },
            "ranked_sources": ranked_sources,
            "citation_rules": {
                "style": cls._normalize_text((brief.get("citation_rules") or {}).get("style"), limit=48)
                if isinstance(brief.get("citation_rules"), dict)
                else "",
                "rules": cls._normalized_text_list(
                    (brief.get("citation_rules") or {}).get("rules") if isinstance(brief.get("citation_rules"), dict) else [],
                    item_limit=180,
                    limit=4,
                ),
            },
            "source_backing_rules": cls._normalized_text_list(brief.get("source_backing_rules"), item_limit=180, limit=4),
            "source_pack": source_pack,
            "source_count": int(brief.get("source_count") or len(source_pack) or 0),
            "preferred_slide_count": int(brief.get("preferred_slide_count") or 0) or None,
            "summary": cls._truncate_text_on_word_boundary(brief.get("summary"), 420),
            "disclaimer_requested": bool(brief.get("disclaimer_requested")),
            "disclaimer_placement": cls._normalize_text(brief.get("disclaimer_placement"), limit=24),
            "disclaimer_style": cls._normalize_text(brief.get("disclaimer_style"), limit=24),
            "needs_live_research": bool(brief.get("needs_live_research")),
            "research_status": cls._normalize_text(brief.get("research_status"), limit=32),
        }

    @classmethod
    def _format_family_plan(cls, value: Any) -> dict[str, Any]:
        plan = value if isinstance(value, dict) else {}
        return {
            "family": cls._normalize_text(plan.get("family"), limit=32),
            "deliverable_type": cls._normalize_text(plan.get("deliverable_type"), limit=32),
            "format": cls._normalize_text(plan.get("format"), limit=32),
            "platform_preset": cls._normalize_text(plan.get("platform_preset"), limit=32),
            "primary_unit": cls._normalize_text(plan.get("primary_unit"), limit=32),
            "body_shape": cls._normalize_text(plan.get("body_shape"), limit=48),
            "outline_mode": cls._normalize_text(plan.get("outline_mode"), limit=32),
            "content_structure": cls._normalized_text_list(plan.get("content_structure"), item_limit=80, limit=8),
            "required_components": cls._normalized_text_list(plan.get("required_components"), item_limit=64, limit=8),
            "optional_components": cls._normalized_text_list(plan.get("optional_components"), item_limit=64, limit=10),
            "copy_density": cls._normalize_text(plan.get("copy_density"), limit=32),
            "visual_density": cls._normalize_text(plan.get("visual_density"), limit=32),
            "metadata_fields": cls._normalized_text_list(plan.get("metadata_fields"), item_limit=64, limit=12),
            "planning_rules": cls._normalized_text_list(plan.get("planning_rules"), item_limit=180, limit=8),
            "preferred_slide_count": int(plan.get("preferred_slide_count") or 0) or None,
        }

    @classmethod
    def _content_plan(cls, value: Any) -> dict[str, Any]:
        plan = value if isinstance(value, dict) else {}
        format_family = cls._normalize_text(plan.get("format_family"), limit=32)
        metadata_fields = cls._normalized_text_list(plan.get("metadata_fields"), item_limit=64, limit=12)
        content_structure = cls._normalized_text_list(plan.get("content_structure"), item_limit=80, limit=8)
        planning_rules = cls._normalized_text_list(plan.get("planning_rules"), item_limit=180, limit=8)
        preferred_slide_count = int(plan.get("preferred_slide_count") or 0) or None
        sequence_contract = cls._normalize_text(plan.get("sequence_contract"), limit=48)
        if not sequence_contract:
            sequence_contract = (
                "native_carousel_metadata"
                if format_family == "carousel"
                else (
                    "native_infographic_sections"
                    if format_family == "infographic"
                    else ("native_static_panel_spec" if format_family == "static" else "flat_primary_payload")
                )
            )
        sequence_expectation = cls._normalize_text(plan.get("sequence_expectation"), limit=48)
        if not sequence_expectation:
            sequence_expectation = (
                "slide_by_slide_progression"
                if format_family == "carousel"
                else ("section_by_section_progression" if format_family == "infographic" else "single_surface_clarity")
            )
        return {
            "planning_family": cls._normalize_text(plan.get("planning_family"), limit=24),
            "deliverable_type": cls._normalize_text(plan.get("deliverable_type"), limit=32),
            "format_family": format_family,
            "primary_unit": cls._normalize_text(plan.get("primary_unit"), limit=32),
            "body_shape": cls._normalize_text(plan.get("body_shape"), limit=48),
            "outline_mode": cls._normalize_text(plan.get("outline_mode"), limit=32),
            "density_target": cls._normalize_text(plan.get("density_target"), limit=32),
            "content_structure": content_structure,
            "required_components": cls._normalized_text_list(plan.get("required_components"), item_limit=64, limit=8),
            "optional_components": cls._normalized_text_list(plan.get("optional_components"), item_limit=64, limit=10),
            "metadata_fields": metadata_fields,
            "planning_rules": planning_rules,
            "preferred_slide_count": preferred_slide_count,
            "sequence_contract": sequence_contract,
            "sequence_expectation": sequence_expectation,
            "native_metadata_fields": [
                field
                for field in metadata_fields
                if field
                in {
                    "carousel_slide_specs",
                    "infographic_section_specs",
                    "static_panel_spec",
                    "supporting_line",
                    "proof_points",
                    "stat_highlights",
                    "claim_evidence_pairs",
                    "trust_builders",
                }
            ][:6],
            "research_mode": cls._normalize_text(plan.get("research_mode"), limit=32),
            "ordered_story_beats": cls._normalized_text_list(
                plan.get("ordered_story_beats"),
                item_limit=180,
                limit=8,
            ),
            "carousel_archetype": cls._normalize_text(plan.get("carousel_archetype"), limit=48),
            "carousel_slide_grammar": [
                {
                    "role": cls._normalize_text(item.get("role"), limit=32),
                    "job": cls._truncate_text_on_word_boundary(item.get("job"), 180),
                }
                for item in (plan.get("carousel_slide_grammar") or [])[:8]
                if isinstance(item, dict)
            ],
            "carousel_archetype_rules": cls._normalized_text_list(
                plan.get("carousel_archetype_rules"),
                item_limit=180,
                limit=8,
            ),
            "sample_editorial_source": cls._normalize_text(plan.get("sample_editorial_source"), limit=32),
            "sample_story_roles": cls._normalized_text_list(plan.get("sample_story_roles"), item_limit=40, limit=8),
            "sample_headline_patterns": cls._normalized_text_list(plan.get("sample_headline_patterns"), item_limit=120, limit=6),
            "sample_summaries": cls._normalized_text_list(plan.get("sample_summaries"), item_limit=160, limit=6),
            "sample_explanation_styles": cls._normalized_text_list(plan.get("sample_explanation_styles"), item_limit=48, limit=4),
            "sample_copy_densities": cls._normalized_text_list(plan.get("sample_copy_densities"), item_limit=24, limit=4),
            "sample_closing_styles": cls._normalized_text_list(plan.get("sample_closing_styles"), item_limit=32, limit=4),
            "disclaimer_requested": bool(plan.get("disclaimer_requested")),
            "disclaimer_placement": cls._normalize_text(plan.get("disclaimer_placement"), limit=24),
        }

    @classmethod
    def _visual_plan(cls, value: Any) -> dict[str, Any]:
        plan = value if isinstance(value, dict) else {}
        format_family = cls._normalize_text(plan.get("format_family"), limit=32)
        preferred_slide_count = int(plan.get("preferred_slide_count") or 0) or None
        return {
            "planning_family": cls._normalize_text(plan.get("planning_family"), limit=24),
            "format_family": format_family,
            "primary_unit": cls._normalize_text(plan.get("primary_unit"), limit=32),
            "body_shape": cls._normalize_text(plan.get("body_shape"), limit=48),
            "density_target": cls._normalize_text(plan.get("density_target"), limit=32),
            "preferred_slide_count": preferred_slide_count,
            "page_strategy": cls._normalize_text(plan.get("page_strategy"), limit=24),
            "render_mode": cls._normalize_text(plan.get("render_mode"), limit=32),
            "execution_mode": (
                "multi_page_sequence"
                if (preferred_slide_count or 0) > 1 or format_family in {"carousel", "infographic"}
                else "single_page_surface"
            ),
            "visual_sequence_expectation": (
                "distinct_page_compositions"
                if format_family == "carousel"
                else ("stacked_section_hierarchy" if format_family == "infographic" else "single_hero_layout")
            ),
            "research_mode": cls._normalize_text(plan.get("research_mode"), limit=32),
        }

    @classmethod
    def _reference_asset_brief_item(cls, asset: dict[str, Any]) -> dict[str, Any]:
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        structural_cues = cls._normalized_text_list(
            metadata.get("structural_cues")
            or metadata.get("sequence_cues")
            or metadata.get("slide_pattern")
            or metadata.get("page_pattern"),
            item_limit=84,
            limit=4,
        )
        style_characteristics = metadata.get("style_characteristics") if isinstance(metadata.get("style_characteristics"), dict) else {}
        layout_dna = metadata.get("layout_dna") if isinstance(metadata.get("layout_dna"), dict) else (
            style_characteristics.get("layout_dna") if isinstance(style_characteristics.get("layout_dna"), dict) else {}
        )
        composition_logic = metadata.get("composition_logic") if isinstance(metadata.get("composition_logic"), dict) else (
            style_characteristics.get("composition_logic") if isinstance(style_characteristics.get("composition_logic"), dict) else {}
        )
        visual_craft_dna = metadata.get("visual_craft_dna") if isinstance(metadata.get("visual_craft_dna"), dict) else (
            style_characteristics.get("visual_craft_dna") if isinstance(style_characteristics.get("visual_craft_dna"), dict) else {}
        )
        subject_semantics = metadata.get("subject_semantics") if isinstance(metadata.get("subject_semantics"), dict) else (
            style_characteristics.get("subject_semantics") if isinstance(style_characteristics.get("subject_semantics"), dict) else {}
        )
        editorial_dna = metadata.get("editorial_dna") if isinstance(metadata.get("editorial_dna"), dict) else {}
        return {
            "asset_id": cls._normalize_text(asset.get("asset_id"), limit=48),
            "role": cls._normalize_text(asset.get("asset_role"), limit=32),
            "label": cls._normalize_text(metadata.get("label"), limit=64),
            "name": cls._normalize_text(
                metadata.get("name") or metadata.get("filename") or metadata.get("title"),
                limit=96,
            ),
            "storage_path": cls._normalize_text(asset.get("storage_path"), limit=240),
            "trust_level": cls._normalize_text(asset.get("trust_level"), limit=24),
            "format": cls._normalize_text(metadata.get("format") or metadata.get("content_format"), limit=24),
            "page_count": int(metadata.get("page_count") or 0) or None,
            "sequence_kind": cls._normalize_text(
                metadata.get("sequence_kind") or metadata.get("narrative_pattern"),
                limit=48,
            ),
            "structural_cues": structural_cues,
            "summary": cls._compose_summary(
                [
                    metadata.get("summary"),
                    metadata.get("sample_usage"),
                    metadata.get("notes"),
                    metadata.get("sequence_summary"),
                ],
                item_limit=120,
                summary_limit=180,
                max_items=2,
            ),
            "layout_dna": cls._compact_layout_dna(layout_dna),
            "composition_logic": cls._compact_composition_logic_dna(composition_logic),
            "visual_craft": cls._compact_visual_craft_dna(visual_craft_dna),
            "subject_semantics": cls._compact_subject_semantics_dna(subject_semantics),
            "editorial_dna": cls._compact_editorial_dna(editorial_dna),
        }

    @classmethod
    def _extract_detailed_visual_context(cls, items: list[dict[str, Any]]) -> dict[str, Any]:
        """🔥 PHASE 4: Extract rich visual context from items metadata"""
        context = {
            "layout_structures": [],
            "component_patterns": [],
            "visual_hierarchies": [],
            "spatial_relationships": [],
        }

        for item in items:
            if not isinstance(item, dict):
                continue

            metadata = item.get("metadata", {})
            if not isinstance(metadata, dict):
                continue

            # Extract layout structure
            layout_structure_raw = metadata.get("layout_structure_raw", {})
            if layout_structure_raw:
                context["layout_structures"].append(
                    {
                        "source": item.get("channel"),
                        "numbered_elements_count": len(layout_structure_raw.get("numbered_elements", [])),
                        "icon_text_pairs_count": len(layout_structure_raw.get("icon_text_pairs", [])),
                        "hierarchy_detected": layout_structure_raw.get("section_hierarchy", {}).get("hierarchy_detected", False),
                        "spatial_groups_count": len(layout_structure_raw.get("spatial_groups", [])),
                    }
                )

            # Extract component patterns
            component_motifs = metadata.get("component_motifs", {})
            if component_motifs:
                patterns = []
                if component_motifs.get("numbered_badges", {}).get("detected"):
                    patterns.append(f"numbered_badges_{component_motifs['numbered_badges'].get('count', 0)}")
                if component_motifs.get("icon_text_associations", {}).get("detected"):
                    patterns.append(f"icon_text_pairs_{component_motifs['icon_text_associations'].get('count', 0)}")
                if patterns:
                    context["component_patterns"].append(
                        {"source": item.get("channel"), "patterns": patterns}
                    )

            # Extract visual hierarchy
            visual_hierarchy = metadata.get("visual_hierarchy", {})
            if visual_hierarchy:
                context["visual_hierarchies"].append(
                    {
                        "focal_role": visual_hierarchy.get("focal_role"),
                        "reading_order": visual_hierarchy.get("reading_order", []),
                        "density": visual_hierarchy.get("density"),
                    }
                )

        return context

    @classmethod
    def _compact_layout_dna(cls, value: Any, *, zone_limit: int = 8) -> dict[str, Any]:
        layout_dna = value if isinstance(value, dict) else {}
        zones = layout_dna.get("zones") if isinstance(layout_dna.get("zones"), dict) else {}
        zone_list = layout_dna.get("zones") if isinstance(layout_dna.get("zones"), list) else []
        zone_instances = layout_dna.get("zone_instances") if isinstance(layout_dna.get("zone_instances"), list) else []
        compact_zones: list[dict[str, Any]] = []

        def _append_zone(candidate: dict[str, Any]) -> None:
            role = cls._normalize_text(candidate.get("role"), limit=32)
            if not role:
                return
            width = candidate.get("w")
            height = candidate.get("h")
            if width is not None or height is not None:
                try:
                    if float(width or 0) <= 0 or float(height or 0) <= 0:
                        return
                except (TypeError, ValueError):
                    return
            compact_zones.append(candidate)

        for role, zone in list(zones.items())[:zone_limit]:
            if not isinstance(zone, dict):
                continue
            normalized = zone.get("normalized") if isinstance(zone.get("normalized"), dict) else {}
            _append_zone(
                {
                    "role": cls._normalize_text(role, limit=32),
                    "x": normalized.get("x"),
                    "y": normalized.get("y"),
                    "w": normalized.get("w"),
                    "h": normalized.get("h"),
                    "text_capacity": cls._normalize_text(zone.get("text_capacity"), limit=24),
                    "alignment": cls._normalize_text(zone.get("alignment"), limit=24),
                }
            )
        if not compact_zones:
            for zone in zone_list[:zone_limit]:
                if not isinstance(zone, dict):
                    continue
                _append_zone(
                    {
                        "role": cls._normalize_text(zone.get("role"), limit=32),
                        "x": zone.get("x"),
                        "y": zone.get("y"),
                        "w": zone.get("w"),
                        "h": zone.get("h"),
                        "text_capacity": cls._normalize_text(zone.get("text_capacity"), limit=24),
                        "alignment": cls._normalize_text(zone.get("alignment"), limit=24),
                    }
                )
        if not compact_zones:
            for zone in zone_instances[:zone_limit]:
                if not isinstance(zone, dict):
                    continue
                normalized = zone.get("normalized") if isinstance(zone.get("normalized"), dict) else {}
                _append_zone(
                    {
                        "role": cls._normalize_text(zone.get("role"), limit=32),
                        "x": normalized.get("x"),
                        "y": normalized.get("y"),
                        "w": normalized.get("w"),
                        "h": normalized.get("h"),
                        "text_capacity": cls._normalize_text(zone.get("text_capacity"), limit=24),
                        "alignment": cls._normalize_text(zone.get("alignment"), limit=24),
                    }
                )
        return {
            "layout_type": cls._normalize_text(layout_dna.get("layout_type"), limit=48),
            "reading_direction": cls._normalize_text(layout_dna.get("reading_direction"), limit=32),
            "zones": [item for item in compact_zones if item.get("role")],
            "spacing": layout_dna.get("spacing", {}) if isinstance(layout_dna.get("spacing"), dict) else {},
        }

    @classmethod
    def _compact_zone_boxes(cls, value: Any, *, zone_limit: int = 8) -> list[dict[str, Any]]:
        zone_map = cls._compact_layout_dna(value, zone_limit=zone_limit)
        zone_boxes: list[dict[str, Any]] = []
        for zone in zone_map.get("zones", []):
            if not isinstance(zone, dict):
                continue
            role = cls._normalize_text(zone.get("role"), limit=32)
            if not role:
                continue
            try:
                x = float(zone.get("x"))
                y = float(zone.get("y"))
                w = float(zone.get("w"))
                h = float(zone.get("h"))
            except (TypeError, ValueError):
                continue
            if w <= 0 or h <= 0:
                continue
            zone_boxes.append(
                {
                    "role": role,
                    "x": round(x, 3),
                    "y": round(y, 3),
                    "w": round(w, 3),
                    "h": round(h, 3),
                    "alignment": cls._normalize_text(zone.get("alignment"), limit=24),
                    "text_capacity": cls._normalize_text(zone.get("text_capacity"), limit=24),
                }
            )
        return zone_boxes

    @classmethod
    def _compact_visual_craft_dna(cls, value: Any) -> dict[str, Any]:
        dna = value if isinstance(value, dict) else {}
        return {
            "depth_style": cls._normalize_text(dna.get("depth_style"), limit=32),
            "rendering_style": cls._normalize_text(dna.get("rendering_style"), limit=32),
            "lighting": cls._normalize_text(dna.get("lighting"), limit=32),
            "polish_level": cls._normalize_text(dna.get("polish_level"), limit=32),
            "material_cues": cls._summary_list(dna.get("material_cues"), limit=6, item_limit=28),
            "dimensionality_cues": cls._summary_list(dna.get("dimensionality_cues"), limit=6, item_limit=28),
        }

    @classmethod
    def _compact_composition_logic_dna(cls, value: Any) -> dict[str, Any]:
        dna = value if isinstance(value, dict) else {}
        return {
            "balance": cls._normalize_text(dna.get("balance"), limit=32),
            "framing": cls._normalize_text(dna.get("framing"), limit=32),
            "layering": cls._normalize_text(dna.get("layering"), limit=32),
            "depth_cues": cls._summary_list(dna.get("depth_cues"), limit=5, item_limit=28),
            "focal_path": cls._summary_list(dna.get("focal_path"), limit=5, item_limit=28),
        }

    @classmethod
    def _compact_subject_semantics_dna(cls, value: Any) -> dict[str, Any]:
        dna = value if isinstance(value, dict) else {}
        return {
            "scene_type": cls._normalize_text(dna.get("scene_type"), limit=32),
            "primary_subjects": cls._summary_list(dna.get("primary_subjects"), limit=6, item_limit=28),
            "domain_cues": cls._summary_list(dna.get("domain_cues"), limit=6, item_limit=28),
            "financial_objects": cls._summary_list(dna.get("financial_objects"), limit=6, item_limit=28),
            "human_presence": cls._normalize_text(dna.get("human_presence"), limit=32),
            "environment": cls._normalize_text(dna.get("environment"), limit=32),
            "abstraction_level": cls._normalize_text(dna.get("abstraction_level"), limit=32),
        }

    @classmethod
    def _compact_editorial_dna(cls, value: Any) -> dict[str, Any]:
        dna = value if isinstance(value, dict) else {}
        return {
            "format_family": cls._normalize_text(dna.get("format_family"), limit=24),
            "page_count_hint": dna.get("page_count_hint"),
            "story_arc_roles": cls._summary_list(dna.get("story_arc_roles"), limit=8, item_limit=28),
            "storytelling_mode": cls._normalize_text(dna.get("storytelling_mode"), limit=32),
            "headline_patterns": cls._summary_list(dna.get("headline_patterns"), limit=6, item_limit=40),
            "supporting_patterns": cls._summary_list(dna.get("supporting_patterns"), limit=6, item_limit=40),
            "editorial_signals": cls._summary_list(dna.get("editorial_signals"), limit=8, item_limit=32),
            "explanation_styles": cls._summary_list(
                dna.get("explanation_styles") or [dna.get("explanation_style")],
                limit=4,
                item_limit=36,
            ),
            "copy_density": cls._normalize_text(dna.get("copy_density"), limit=24),
            "closing_style": cls._normalize_text(dna.get("closing_style"), limit=32),
            "proof_module_count": dna.get("proof_module_count"),
        }

    @classmethod
    def _compact_asset_reference(cls, value: Any) -> str:
        text = cls._normalize_text(value)
        if not text:
            return ""
        return text

    @classmethod
    def _compact_sequence_pack(cls, value: Any) -> dict[str, Any]:
        pack = value if isinstance(value, dict) else {}
        slides: list[dict[str, Any]] = []
        story_roles: list[str] = []
        headline_hints: list[str] = []
        for item in (pack.get("slides") or [])[:8]:
            if not isinstance(item, dict):
                continue
            zone_map = item.get("zone_map") if isinstance(item.get("zone_map"), dict) else {}
            composition_logic = (
                item.get("composition_logic")
                if isinstance(item.get("composition_logic"), dict)
                else (zone_map.get("composition_logic") if isinstance(zone_map.get("composition_logic"), dict) else {})
            )
            visual_craft = (
                item.get("visual_craft_dna")
                if isinstance(item.get("visual_craft_dna"), dict)
                else (zone_map.get("visual_craft_dna") if isinstance(zone_map.get("visual_craft_dna"), dict) else {})
            )
            subject_semantics = (
                item.get("subject_semantics")
                if isinstance(item.get("subject_semantics"), dict)
                else (zone_map.get("subject_semantics") if isinstance(zone_map.get("subject_semantics"), dict) else {})
            )
            editorial_dna = (
                item.get("editorial_dna")
                if isinstance(item.get("editorial_dna"), dict)
                else (zone_map.get("editorial_dna") if isinstance(zone_map.get("editorial_dna"), dict) else {})
            )
            normalized_story_role = cls._normalize_text(item.get("story_role"), limit=32)
            normalized_headline_hint = cls._normalize_text(item.get("headline_hint"), limit=72)
            if normalized_story_role:
                story_roles.append(normalized_story_role)
            if normalized_headline_hint and not cls._looks_like_weak_sequence_hint(normalized_headline_hint):
                headline_hints.append(normalized_headline_hint)
            normalized_sequence_summary = cls._normalize_text(item.get("sequence_summary"), limit=120)
            if not normalized_sequence_summary:
                normalized_sequence_summary = cls._normalize_text(item.get("structural_cues"), limit=120)
            if not normalized_sequence_summary and normalized_headline_hint and not cls._looks_like_weak_sequence_hint(normalized_headline_hint):
                normalized_sequence_summary = normalized_headline_hint
            slides.append(
                {
                    "slide_index": item.get("slide_index"),
                    "template_name": cls._normalize_text(item.get("template_name"), limit=72),
                    "reference_asset_path": cls._compact_asset_reference(item.get("reference_asset_path")),
                    "story_role": normalized_story_role,
                    "headline_hint": normalized_headline_hint if not cls._looks_like_weak_sequence_hint(normalized_headline_hint) else "",
                    "structural_cues": cls._summary_list(item.get("structural_cues"), limit=4, item_limit=36),
                    "sequence_summary": normalized_sequence_summary,
                    "zone_map": cls._compact_layout_dna(zone_map, zone_limit=6),
                    "composition_logic": cls._compact_composition_logic_dna(composition_logic),
                    "visual_craft": cls._compact_visual_craft_dna(visual_craft),
                    "subject_semantics": cls._compact_subject_semantics_dna(subject_semantics),
                    "editorial_dna": cls._compact_editorial_dna(editorial_dna),
                }
            )
        return {
            "family_name": cls._normalize_text(pack.get("family_name"), limit=72),
            "sequence_kind": cls._normalize_text(pack.get("sequence_kind"), limit=48),
            "surface_policy": cls._normalize_text(pack.get("surface_policy"), limit=32),
            "slide_count": pack.get("slide_count"),
            "story_roles": cls._summary_list(story_roles, limit=8, item_limit=32),
            "headline_hints": cls._summary_list(headline_hints, limit=6, item_limit=72),
            "sequence_cues": cls._summary_list(pack.get("sequence_cues"), limit=8, item_limit=36),
            "slides": slides,
        }

    @classmethod
    def _visual_brief_payload(
        cls,
        items: list[dict[str, Any]],
        *,
        template_suppressed: bool,
        candidate_count: int,
        rejection_reasons: dict[str, int] | None = None,
        abstention_reason: str | None = None,
        compatibility_bypass_count: int = 0,
        missing_quality_metadata_count: int = 0,
    ) -> dict[str, Any]:
        runtime_config = cls._visual_grounding_runtime_config()
        cleaned_items: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for entry in items[: cls.MAX_VISUAL_KNOWLEDGE_ITEMS]:
            if not isinstance(entry, dict):
                continue
            channel = cls._normalize_text(entry.get("channel"), limit=32).casefold()
            content = cls._clean_knowledge_content(entry.get("content"), limit=cls.MAX_KNOWLEDGE_CHARS)
            if not channel or not content:
                continue
            key = (channel, content.casefold())
            if key in seen:
                continue
            seen.add(key)
            try:
                normalized_rank_score = round(float(entry.get("rank_score") or 0.0), 4)
            except (TypeError, ValueError):
                normalized_rank_score = 0.0
            cleaned_items.append(
                {
                    "channel": channel,
                    "role": cls._normalize_text(entry.get("role"), limit=24).casefold() or cls._visual_grounding_role(channel),
                    "content": content,
                    "document_type": cls._normalize_text(entry.get("document_type"), limit=48).casefold(),
                    "source_id": cls._normalize_text(entry.get("source_id"), limit=96),
                    "rank_score": normalized_rank_score,
                }
            )
        by_channel: dict[str, list[dict[str, Any]]] = {}
        for item in cleaned_items:
            by_channel.setdefault(str(item.get("channel") or "knowledge"), []).append(item)
        channel_priority = list(cls.VISUAL_KNOWLEDGE_PRIORITY)
        channels_present = [
            channel
            for channel in channel_priority
            if by_channel.get(channel)
        ]
        primary_channels_present = [
            channel
            for channel in channel_priority
            if channel in cls.VISUAL_PRIMARY_CHANNELS and by_channel.get(channel)
        ]
        normalized_rejections = cls._normalize_visual_rejection_reasons(rejection_reasons)
        normalized_candidate_count = max(cls._coerce_non_negative_int(candidate_count), len(cleaned_items))
        excluded_candidate_count = max(normalized_candidate_count - len(cleaned_items), 0)
        resolved_abstention_reason = cls._normalize_text(abstention_reason, limit=64) or cls._visual_abstention_reason(
            items=cleaned_items,
            candidate_count=normalized_candidate_count,
            rejection_reasons=normalized_rejections,
        )
        grounding_mode = "brand_knowledge" if cleaned_items else "llm_fallback"
        grounding_strength = cls._visual_grounding_strength(cleaned_items) if cleaned_items else "none"

        # 🔥 PHASE 4: Extract detailed visual context
        detailed_context = cls._extract_detailed_visual_context(items)

        return {
            "grounding_mode": grounding_mode,
            "grounding_strength": grounding_strength,
            "channel_priority": channel_priority,
            "channels_present": channels_present,
            "primary_channels_present": primary_channels_present,
            "template_suppressed": bool(template_suppressed),
            "suppressed_channels": ["template"] if template_suppressed else [],
            "selected_item_count": len(cleaned_items),
            "candidate_count": normalized_candidate_count,
            "excluded_candidate_count": excluded_candidate_count,
            "abstention_reason": resolved_abstention_reason if grounding_mode == "llm_fallback" else "",
            "rejection_reasons": normalized_rejections,
            "gate_version": runtime_config["gate_version"],
            "quality_metadata_policy": runtime_config["quality_metadata_policy"],
            "compatibility_bypass_count": cls._coerce_non_negative_int(compatibility_bypass_count),
            "missing_quality_metadata_count": cls._coerce_non_negative_int(missing_quality_metadata_count),
            "thresholds_used": runtime_config["thresholds"],
            "summary": cls._visual_knowledge_summary(cleaned_items),
            "items": cleaned_items,
            "by_channel": by_channel,
            "detailed_visual_context": detailed_context,  # 🔥 PHASE 4: NEW FIELD
        }

    @classmethod
    def _visual_grounding_diagnostics(cls, brief: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(brief, dict):
            return {
                "grounding_mode": "llm_fallback",
                "grounding_strength": "none",
                "abstention_reason": "no_visual_brand_evidence",
                "candidate_count": 0,
                "excluded_candidate_count": 0,
                "rejection_reasons": {},
                "quality_metadata_policy": cls._visual_grounding_runtime_config()["quality_metadata_policy"],
                "compatibility_bypass_count": 0,
                "missing_quality_metadata_count": 0,
                "gate_version": cls.VISUAL_GROUNDING_GATE_VERSION,
                "template_suppressed": False,
                "channels_present": [],
                "primary_channels_present": [],
            }
        return {
            "grounding_mode": cls._normalize_text(brief.get("grounding_mode"), limit=32) or "llm_fallback",
            "grounding_strength": cls._normalize_text(brief.get("grounding_strength"), limit=32) or "none",
            "abstention_reason": cls._normalize_text(brief.get("abstention_reason"), limit=64),
            "candidate_count": cls._coerce_non_negative_int(brief.get("candidate_count")),
            "excluded_candidate_count": cls._coerce_non_negative_int(brief.get("excluded_candidate_count")),
            "rejection_reasons": cls._normalize_visual_rejection_reasons(brief.get("rejection_reasons")),
            "quality_metadata_policy": cls._normalize_text(brief.get("quality_metadata_policy"), limit=32),
            "compatibility_bypass_count": cls._coerce_non_negative_int(brief.get("compatibility_bypass_count")),
            "missing_quality_metadata_count": cls._coerce_non_negative_int(brief.get("missing_quality_metadata_count")),
            "gate_version": cls._normalize_text(brief.get("gate_version"), limit=16) or cls.VISUAL_GROUNDING_GATE_VERSION,
            "template_suppressed": bool(brief.get("template_suppressed")),
            "channels_present": [
                cls._normalize_text(channel, limit=32)
                for channel in (brief.get("channels_present") or [])
                if cls._normalize_text(channel, limit=32)
            ],
            "primary_channels_present": [
                cls._normalize_text(channel, limit=32)
                for channel in (brief.get("primary_channels_present") or [])
                if cls._normalize_text(channel, limit=32)
            ],
        }

    @classmethod
    def coerce_visual_knowledge_brief(cls, value: Any) -> dict[str, Any]:
        channel_priority = list(cls.VISUAL_KNOWLEDGE_PRIORITY)
        runtime_config = cls._visual_grounding_runtime_config()
        require_quality_metadata = bool(runtime_config["require_quality_metadata"])
        if isinstance(value, list):
            grouped: dict[str, list[dict[str, Any]]] = {channel: [] for channel in channel_priority}
            overflow: list[dict[str, Any]] = []
            rejection_reasons: dict[str, int] = {}
            candidate_count = 0
            compatibility_bypass_count = 0
            missing_quality_metadata_count = 0
            for entry in value:
                if not isinstance(entry, dict):
                    continue
                channel = cls._normalize_text(entry.get("channel"), limit=32).casefold()
                content = cls._clean_knowledge_content(entry.get("content"), limit=cls.MAX_KNOWLEDGE_CHARS)
                if not channel or not content:
                    continue
                if cls._knowledge_signal_score(content) < cls.MIN_KNOWLEDGE_SIGNAL_SCORE:
                    continue
                metadata = {
                    "document_type": cls._normalize_text(entry.get("document_type"), limit=48).casefold(),
                    "source_id": cls._normalize_text(entry.get("source_id"), limit=96),
                    "visual_grounding_allowed": entry.get("visual_grounding_allowed"),
                }
                candidate_count += 1
                if cls._has_visual_quality_metadata(metadata):
                    allowed, reason = cls._visual_channel_gate(channel, metadata)
                else:
                    if require_quality_metadata:
                        allowed = False
                        reason = "missing_quality_metadata"
                        missing_quality_metadata_count += 1
                    else:
                        compatibility_bypass_count += 1
                        allowed = cls._visual_grounding_allowed(channel, metadata)
                        reason = "visual_grounding_blocked" if not allowed else ""
                if not allowed:
                    rejection_reasons[reason] = int(rejection_reasons.get(reason) or 0) + 1
                    continue
                item = cls._visual_brief_item(
                    channel=channel,
                    content=content,
                    metadata=metadata,
                    rank_score=entry.get("rank_score"),
                    role=entry.get("role"),
                )
                if channel in grouped:
                    grouped[channel].append(item)
                else:
                    overflow.append(item)
            items, template_suppressed, normalized_rejections = cls._select_visual_brief_items(
                grouped,
                overflow=overflow,
                rejection_reasons=rejection_reasons,
            )
            return cls._visual_brief_payload(
                items,
                template_suppressed=template_suppressed,
                candidate_count=candidate_count,
                rejection_reasons=normalized_rejections,
                compatibility_bypass_count=compatibility_bypass_count,
                missing_quality_metadata_count=missing_quality_metadata_count,
            )
        if not isinstance(value, dict):
            return cls._visual_brief_payload(
                [],
                template_suppressed=False,
                candidate_count=0,
                rejection_reasons={},
                abstention_reason="no_visual_brand_evidence",
                compatibility_bypass_count=0,
                missing_quality_metadata_count=0,
            )
        raw_items = value.get("items") if isinstance(value.get("items"), list) else []
        items: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        rejection_reasons = cls._normalize_visual_rejection_reasons(value.get("rejection_reasons"))
        compatibility_bypass_count = cls._coerce_non_negative_int(value.get("compatibility_bypass_count"))
        missing_quality_metadata_count = cls._coerce_non_negative_int(value.get("missing_quality_metadata_count"))
        stored_brief_payload = any(
            key in value
            for key in (
                "gate_version",
                "candidate_count",
                "quality_metadata_policy",
                "selected_item_count",
                "rejection_reasons",
            )
        )
        for entry in raw_items:
            if not isinstance(entry, dict):
                continue
            channel = cls._normalize_text(entry.get("channel"), limit=32).casefold()
            content = cls._clean_knowledge_content(entry.get("content"), limit=cls.MAX_KNOWLEDGE_CHARS)
            if not channel or not content:
                continue
            metadata = {
                "document_type": cls._normalize_text(entry.get("document_type"), limit=48).casefold(),
                "source_id": cls._normalize_text(entry.get("source_id"), limit=96),
                "visual_grounding_allowed": entry.get("visual_grounding_allowed"),
            }
            if cls._knowledge_signal_score(content) < cls.MIN_KNOWLEDGE_SIGNAL_SCORE:
                continue
            if cls._has_visual_quality_metadata(metadata):
                allowed, reason = cls._visual_channel_gate(channel, metadata)
            elif stored_brief_payload:
                allowed = cls._visual_grounding_allowed(channel, metadata)
                reason = "visual_grounding_blocked" if not allowed else ""
            else:
                if require_quality_metadata:
                    allowed = False
                    reason = "missing_quality_metadata"
                    missing_quality_metadata_count += 1
                else:
                    compatibility_bypass_count += 1
                    allowed = cls._visual_grounding_allowed(channel, metadata)
                    reason = "visual_grounding_blocked" if not allowed else ""
            if not allowed:
                rejection_reasons[reason] = int(rejection_reasons.get(reason) or 0) + 1
                continue
            key = (channel, content.casefold())
            if key in seen:
                continue
            seen.add(key)
            items.append(
                cls._visual_brief_item(
                    channel=channel,
                    content=content,
                    metadata=metadata,
                    rank_score=entry.get("rank_score"),
                    role=entry.get("role"),
                )
            )
        template_suppressed = bool(value.get("template_suppressed"))
        try:
            explicit_candidate_count = int(value.get("candidate_count") or 0)
        except (TypeError, ValueError):
            explicit_candidate_count = 0
        try:
            explicit_selected_count = int(value.get("selected_item_count") or 0)
        except (TypeError, ValueError):
            explicit_selected_count = 0
        candidate_count = max(explicit_candidate_count, explicit_selected_count, len(raw_items))
        return cls._visual_brief_payload(
            items,
            template_suppressed=template_suppressed,
            candidate_count=candidate_count,
            rejection_reasons=rejection_reasons,
            abstention_reason=cls._normalize_text(value.get("abstention_reason"), limit=64),
            compatibility_bypass_count=compatibility_bypass_count,
            missing_quality_metadata_count=missing_quality_metadata_count,
        )

    @classmethod
    def _knowledge_brief(cls, ordered_knowledge: dict[str, list[dict[str, Any]]]) -> list[dict[str, str]]:
        brief: list[dict[str, str]] = []
        for channel, entries in ordered_knowledge.items():
            for content in cls._ranked_knowledge_entries(entries, per_channel_limit=2):
                brief.append(
                    {
                        "channel": channel,
                        "content": content,
                    }
                )
                if len(brief) >= cls.MAX_KNOWLEDGE_ITEMS:
                    return brief
        return brief

    @classmethod
    def _visual_knowledge_brief(cls, ordered_knowledge: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = {channel: [] for channel in cls.VISUAL_KNOWLEDGE_PRIORITY}
        rejection_reasons: dict[str, int] = {}
        candidate_count = 0
        runtime_config = cls._visual_grounding_runtime_config()
        require_quality_metadata = bool(runtime_config["require_quality_metadata"])
        compatibility_bypass_count = 0
        missing_quality_metadata_count = 0
        for channel in cls.VISUAL_KNOWLEDGE_PRIORITY:
            channel_limit = cls.VISUAL_CHANNEL_ITEM_LIMITS.get(channel, 1)
            candidate_limit = max(channel_limit * 4, channel_limit + 2, 4)
            ranked_records, raw_candidate_count, early_rejections = cls._ranked_visual_knowledge_candidates(
                ordered_knowledge.get(channel, []) or [],
                per_channel_limit=candidate_limit,
            )
            candidate_count += raw_candidate_count
            for reason, count in early_rejections.items():
                rejection_reasons[reason] = int(rejection_reasons.get(reason) or 0) + int(count or 0)
            accepted_records: list[dict[str, Any]] = []
            for record in ranked_records:
                metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
                if cls._has_visual_quality_metadata(metadata):
                    allowed, reason = cls._visual_channel_gate(channel, metadata)
                elif require_quality_metadata:
                    allowed = False
                    reason = "missing_quality_metadata"
                    missing_quality_metadata_count += 1
                else:
                    compatibility_bypass_count += 1
                    allowed = cls._visual_grounding_allowed(channel, metadata)
                    reason = "visual_grounding_blocked" if not allowed else ""
                if not allowed:
                    rejection_reasons[reason] = int(rejection_reasons.get(reason) or 0) + 1
                    continue
                accepted_records.append(
                    cls._visual_brief_item(
                        channel=channel,
                        content=record.get("content"),
                        metadata=metadata,
                        rank_score=record.get("rank_score"),
                    )
                )
            grouped[channel] = accepted_records
        items, template_suppressed, normalized_rejections = cls._select_visual_brief_items(
            grouped,
            rejection_reasons=rejection_reasons,
        )
        return cls._visual_brief_payload(
            items,
            template_suppressed=template_suppressed,
            candidate_count=candidate_count,
            rejection_reasons=normalized_rejections,
            compatibility_bypass_count=compatibility_bypass_count,
            missing_quality_metadata_count=missing_quality_metadata_count,
        )

    @classmethod
    def _audience_brief(cls, audience: dict[str, Any], persona_context: dict[str, Any]) -> dict[str, Any]:
        segments = []
        for segment in audience.get("segments", []) or []:
            if isinstance(segment, dict):
                label = cls._normalize_text(segment.get("label") or segment.get("name"), limit=44)
                if label:
                    segments.append(label)
        persona_context = persona_context if isinstance(persona_context, dict) else {}
        audience_research_items = cls._audience_research_items(audience)
        audience_behaviors = cls._normalized_text_list(audience.get("behaviors"), item_limit=72, limit=4)
        audience_motivations = cls._normalized_text_list(audience.get("motivations"), item_limit=72, limit=4)
        audience_pain_points = cls._normalized_text_list(audience.get("pain_points"), item_limit=72, limit=4)
        audience_preferences = cls._normalized_text_list(audience.get("preferences"), item_limit=72, limit=4)
        audience_objections = cls._normalized_text_list(audience.get("objections"), item_limit=120, limit=4)
        audience_desired_outcomes = cls._normalized_text_list(audience.get("desired_outcomes"), item_limit=120, limit=4)
        audience_trust_signals = cls._normalized_text_list(audience.get("trust_signals"), item_limit=120, limit=4)
        audience_proof_cues = cls._normalized_text_list(audience.get("proof_cues"), item_limit=120, limit=4)
        audience_comparison_points = cls._normalized_text_list(audience.get("comparison_points"), item_limit=120, limit=4)
        persona_behaviors = cls._persona_content_behavior_items(persona_context.get("content_behavior"), limit=3)
        persona_goals = cls._normalized_text_list(persona_context.get("audience_goals"), item_limit=72, limit=3)
        persona_motivations = cls._normalized_text_list(persona_context.get("motivations"), item_limit=72, limit=3)
        persona_pain_points = cls._normalized_text_list(persona_context.get("fears_and_pain_points"), item_limit=72, limit=3)
        persona_objections = cls._normalized_text_list(persona_context.get("objections"), item_limit=72, limit=3)
        persona_language_preference = cls._normalize_text(persona_context.get("language_preference"), limit=48)
        persona_summary = cls._persona_summary(persona_context)
        explicit_research_summary = cls._normalize_text(audience.get("research_summary"), limit=420)
        research_summary = cls._compose_summary(
            [
                explicit_research_summary,
                *audience_research_items[:3],
                *audience_proof_cues[:1],
                *audience_trust_signals[:1],
                *audience_comparison_points[:1],
            ],
            item_limit=128,
            summary_limit=420,
            max_items=5,
        ) or explicit_research_summary
        research_signal_count = cls._coerce_non_negative_int(audience.get("research_signal_count"))
        return {
            "segments": cls._dedupe_items(segments, limit=3),
            "persona_name": cls._normalize_text(persona_context.get("name"), limit=48),
            "persona_role": cls._normalize_text(persona_context.get("role"), limit=40),
            "behaviors": audience_behaviors,
            "motivations": audience_motivations,
            "desired_outcomes": audience_desired_outcomes,
            "pain_points": audience_pain_points,
            "preferences": audience_preferences,
            "objections": audience_objections,
            "trust_signals": audience_trust_signals,
            "proof_cues": audience_proof_cues,
            "comparison_points": audience_comparison_points,
            "language_preference": persona_language_preference,
            "audience_research_behaviors": audience_behaviors,
            "audience_research_motivations": audience_motivations,
            "audience_research_pain_points": audience_pain_points,
            "audience_research_preferences": audience_preferences,
            "audience_research_objections": audience_objections,
            "persona_behaviors": persona_behaviors,
            "persona_goals": persona_goals,
            "persona_motivations": persona_motivations,
            "persona_pain_points": persona_pain_points,
            "persona_objections": persona_objections,
            "persona_language_preference": persona_language_preference,
            "persona_summary": persona_summary,
            "research_highlights": audience_research_items[:6],
            "research_signal_count": research_signal_count or len(audience_research_items),
            "research_summary": research_summary,
            "signal_weights": dict(cls.AUDIENCE_SIGNAL_WEIGHTS),
            "signal_priority_note": (
                "Prefer research-backed audience lanes when they conflict with persona defaults. "
                "Use persona lanes to refine phrasing, content behavior, and friction only when the audience research is missing or less specific."
            ),
        }

    @classmethod
    def _brand_foundations_summary(cls, foundations: dict[str, Any]) -> str:
        if not isinstance(foundations, dict):
            return ""
        current_schema_summary = cls._compose_summary(
            [
                foundations.get("brand_promise"),
                foundations.get("human_insight"),
                foundations.get("brand_advantage"),
                foundations.get("market_positioning"),
                foundations.get("business_problem_or_opportunity"),
                foundations.get("perception_challenge"),
                foundations.get("brand_mission"),
                foundations.get("brand_vision"),
            ],
            item_limit=88,
            summary_limit=220,
            max_items=4,
        )
        if current_schema_summary:
            return current_schema_summary
        return cls._compose_summary(
            [foundations.get("brand_foundation")],
            item_limit=220,
            summary_limit=220,
            max_items=1,
        )

    @classmethod
    def _copy_brief(
        cls,
        brand_context: dict[str, Any],
        persona_context: dict[str, Any],
        objective_context: dict[str, Any],
        session_memory: dict[str, Any],
    ) -> dict[str, Any]:
        voice = brand_context.get("voice_tone", {}) or {}
        guardrails = brand_context.get("guardrails", {}) or {}
        foundations = brand_context.get("foundations", {}) or {}
        persona_context = persona_context if isinstance(persona_context, dict) else {}
        objective_config = objective_context.get("configuration", {}) if isinstance(objective_context, dict) else {}
        latest_content = (session_memory or {}).get("latest_content_version", {}) or {}
        follow_up_intent = (session_memory or {}).get("follow_up_intent", {}) or {}
        uses_previous_output = cls._should_use_prior_copy_context(session_memory or {})
        persona_goals = cls._normalized_text_list(persona_context.get("audience_goals"), item_limit=88, limit=3)
        persona_motivations = cls._normalized_text_list(persona_context.get("motivations"), item_limit=88, limit=3)
        persona_pain_points = cls._normalized_text_list(persona_context.get("fears_and_pain_points"), item_limit=88, limit=3)
        persona_objections = cls._normalized_text_list(persona_context.get("objections"), item_limit=88, limit=3)
        persona_content_behavior = cls._persona_content_behavior_items(persona_context.get("content_behavior"), limit=3)
        persona_language_preference = cls._normalize_text(persona_context.get("language_preference"), limit=48)
        persona_summary = cls._persona_summary(persona_context)
        return {
            "brand_name": cls._normalize_text(brand_context.get("brand_name"), limit=72),
            "brand_description": cls._normalize_text(brand_context.get("brand_description"), limit=220),
            "tone_attributes": cls._dedupe_items([cls._normalize_text(item, 32) for item in voice.get("tone_attributes", []) or []], limit=4),
            "primary_emotion": cls._normalize_text(voice.get("primary_emotion"), limit=40),
            "avoided_emotion": cls._normalize_text(voice.get("avoided_emotion"), limit=40),
            "dos": cls._dedupe_items([cls._normalize_text(item, 88) for item in guardrails.get("dos", []) or []], limit=4),
            "donts": cls._dedupe_items([cls._normalize_text(item, 88) for item in guardrails.get("donts", []) or []], limit=4),
            "blocked_words": cls._dedupe_items([cls._normalize_text(item, 32) for item in guardrails.get("blocked_words", []) or []], limit=8),
            "positive_words": cls._dedupe_items([cls._normalize_text(item, 32) for item in guardrails.get("positive_word_bank", []) or []], limit=8),
            "brand_foundations": cls._brand_foundations_summary(foundations),
            "persona_name": cls._normalize_text(persona_context.get("name"), limit=48),
            "persona_role": cls._normalize_text(persona_context.get("role"), limit=40),
            "persona_goals": persona_goals,
            "persona_motivations": persona_motivations,
            "persona_pain_points": persona_pain_points,
            "persona_objections": persona_objections,
            "persona_content_behavior": persona_content_behavior,
            "persona_language_preference": persona_language_preference,
            "persona_messaging_summary": persona_summary,
            "objective_name": cls._normalize_text(objective_context.get("name"), limit=48),
            "objective_focus": cls._normalize_text(objective_context.get("description"), limit=180),
            "objective_market_positioning": cls._normalize_text(objective_config.get("market_positioning"), limit=120),
            "follow_up_mode": cls._normalize_text(follow_up_intent.get("mode"), limit=24),
            "prior_headline": cls._normalize_text(latest_content.get("headline"), limit=120) if uses_previous_output else "",
        }

    @classmethod
    def _lineage_inheritance_policy(cls, session_memory: dict[str, Any]) -> dict[str, Any]:
        request_lineage = (session_memory or {}).get("request_lineage") if isinstance((session_memory or {}).get("request_lineage"), dict) else {}
        inheritance_policy = request_lineage.get("inheritance_policy") if isinstance(request_lineage.get("inheritance_policy"), dict) else {}
        return inheritance_policy

    @classmethod
    def _should_use_prior_copy_context(cls, session_memory: dict[str, Any]) -> bool:
        inheritance_policy = cls._lineage_inheritance_policy(session_memory)
        explicit = inheritance_policy.get("inherit_copy_context")
        if explicit is not None:
            return bool(explicit)
        follow_up_intent = (session_memory or {}).get("follow_up_intent", {}) or {}
        return bool(follow_up_intent.get("uses_previous_output"))

    @classmethod
    def _should_use_prior_layout_context(cls, session_memory: dict[str, Any]) -> bool:
        inheritance_policy = cls._lineage_inheritance_policy(session_memory)
        explicit = inheritance_policy.get("inherit_layout_context")
        if explicit is not None:
            return bool(explicit)
        follow_up_intent = (session_memory or {}).get("follow_up_intent", {}) or {}
        return bool(follow_up_intent.get("uses_previous_output"))

    @classmethod
    def _summary_list(cls, value: Any, *, limit: int = 4, item_limit: int = 48) -> list[str]:
        if value in (None, ""):
            return []
        raw_items = value if isinstance(value, (list, tuple, set)) else [value]
        items = [
            cls._normalize_text(item, limit=item_limit)
            for item in raw_items
            if cls._normalize_text(item, limit=item_limit)
        ]
        return cls._dedupe_items(items, limit=limit)

    @classmethod
    def _join_summary(cls, values: list[str], *, limit: int = 180) -> str:
        return cls._normalize_text(", ".join(value for value in values if value), limit=limit)

    @classmethod
    def _reference_family_module_patterns(
        cls,
        *,
        zone_roles: list[str],
        story_roles: list[str],
        sequence_kind: str,
        content_structure_summary: str,
        motif_summary: str,
    ) -> list[str]:
        lowered_roles = {str(role or "").strip().casefold() for role in zone_roles}
        lowered_story_roles = {str(role or "").strip().casefold() for role in story_roles}
        sequence_text = str(sequence_kind or "").strip().casefold()
        content_text = str(content_structure_summary or "").strip().casefold()
        motif_text = str(motif_summary or "").strip().casefold()
        patterns: list[str] = []

        def add(name: str) -> None:
            if name not in patterns:
                patterns.append(name)

        if {"headline", "image"} <= lowered_roles or {"headline", "hero_visual"} <= lowered_roles:
            add("cover_hero_split")
        if any(role in lowered_roles for role in {"proof_points", "proof_point", "proof_module"}):
            add("proof_grid")
        if any(role in lowered_roles for role in {"stat_highlights", "stat_highlight"}):
            add("stat_callout")
        if any(role in lowered_roles for role in {"cta", "footer", "legal"}):
            add("closing_cta_strip")
        if "comparison" in sequence_text or "versus" in sequence_text or "compare" in content_text:
            add("comparison_module")
        if any(role in lowered_story_roles for role in {"structure", "detail", "comparison_item", "feature_cluster"}):
            add("sequence_explainer")
        if "icon" in motif_text or "badge" in motif_text:
            add("icon_label_stack")
        return patterns[:6]

    @classmethod
    def _reference_family_density_target(
        cls,
        *,
        format_name: str,
        editorial_dna: dict[str, Any],
        hierarchy_summary: str,
        content_structure_summary: str,
    ) -> str:
        text = " ".join(
            [
                str(editorial_dna.get("copy_density") or ""),
                str(hierarchy_summary or ""),
                str(content_structure_summary or ""),
            ]
        ).casefold()
        if any(token in text for token in ("airy", "generous", "minimal", "spacious", "calm")):
            return "airy"
        if any(token in text for token in ("dense", "tight", "packed", "comparison", "data story")):
            return "dense"
        if str(format_name or "").strip().casefold() == "infographic":
            return "balanced_dense"
        return "balanced"

    @classmethod
    def _reference_family_balance_target(
        cls,
        *,
        zone_roles: list[str],
        layout_type: str,
        composition_summary: str,
    ) -> str:
        lowered_roles = {str(role or "").strip().casefold() for role in zone_roles}
        text = f"{layout_type} {composition_summary}".casefold()
        if any(role in lowered_roles for role in {"image", "hero_visual", "primary_visual"}) and any(
            token in text for token in ("split", "hero", "editorial", "asymmetric", "anchored")
        ):
            return "visual_led_balanced"
        if any(role in lowered_roles for role in {"proof_points", "stat_highlights"}) and "infographic" in text:
            return "explainer_balanced"
        return "editorial_balanced"

    @classmethod
    def _reference_family_profile(
        cls,
        *,
        brand_visual_brief: dict[str, Any],
        template_fit_brief: dict[str, Any],
        content_format_brief: dict[str, Any],
    ) -> dict[str, Any]:
        brand_visual_brief = brand_visual_brief if isinstance(brand_visual_brief, dict) else {}
        template_fit_brief = template_fit_brief if isinstance(template_fit_brief, dict) else {}
        content_format_brief = content_format_brief if isinstance(content_format_brief, dict) else {}
        sequence_pack = template_fit_brief.get("sequence_pack") if isinstance(template_fit_brief.get("sequence_pack"), dict) else {}
        slides = [dict(item) for item in sequence_pack.get("slides", []) if isinstance(item, dict)]
        if not any([template_fit_brief, brand_visual_brief, sequence_pack]):
            return {}

        format_name = cls._normalize_text(content_format_brief.get("format"), limit=24)
        family_name = cls._normalize_text(
            sequence_pack.get("family_name")
            or template_fit_brief.get("template_name")
            or brand_visual_brief.get("dominant_layout_family"),
            limit=96,
        )
        sequence_kind = cls._normalize_text(sequence_pack.get("sequence_kind"), limit=64)
        surface_policy = cls._normalize_text(sequence_pack.get("surface_policy"), limit=32)
        story_roles = cls._dedupe_items(
            [
                cls._normalize_text(item, 40)
                for item in (
                    sequence_pack.get("story_roles")
                    or [slide.get("story_role") for slide in slides]
                )
                if cls._normalize_text(item, 40)
            ],
            limit=8,
        )
        template_zone_roles = cls._dedupe_items(
            [
                cls._normalize_text(item, 32)
                for item in (
                    template_fit_brief.get("template_zone_roles")
                    or brand_visual_brief.get("preferred_zone_roles")
                    or []
                )
                if cls._normalize_text(item, 32)
            ],
            limit=10,
        )
        approved_image_zone_roles = cls._dedupe_items(
            [
                role
                for role in template_zone_roles
                if any(token in role.casefold() for token in ("image", "hero", "visual", "icon", "illustration"))
            ]
            or [
                cls._normalize_text(role, 32)
                for role in ("image", "hero_visual", "primary_visual")
            ],
            limit=4,
        )
        text_zone_roles = cls._dedupe_items(
            [
                role
                for role in template_zone_roles
                if role.casefold() not in {"logo", "background"} and role not in approved_image_zone_roles
            ],
            limit=8,
        )
        editorial_dna = (
            template_fit_brief.get("template_editorial_dna")
            if isinstance(template_fit_brief.get("template_editorial_dna"), dict)
            else {}
        )
        layout_dna = (
            template_fit_brief.get("template_layout_dna")
            if isinstance(template_fit_brief.get("template_layout_dna"), dict)
            else {}
        )
        composition_logic = (
            template_fit_brief.get("template_composition_logic")
            if isinstance(template_fit_brief.get("template_composition_logic"), dict)
            else {}
        )
        module_patterns = cls._reference_family_module_patterns(
            zone_roles=template_zone_roles,
            story_roles=story_roles,
            sequence_kind=sequence_kind,
            content_structure_summary=cls._normalize_text(brand_visual_brief.get("content_structure_summary"), limit=200),
            motif_summary=cls._normalize_text(brand_visual_brief.get("motif_summary"), limit=180),
        )
        slide_profiles: list[dict[str, Any]] = []
        for slide in slides[:8]:
            zone_map = slide.get("zone_map") if isinstance(slide.get("zone_map"), dict) else {}
            slide_zone_roles = cls._dedupe_items(
                [
                    cls._normalize_text(zone.get("role"), 32)
                    for zone in (zone_map.get("zones") or [])
                    if isinstance(zone, dict) and cls._normalize_text(zone.get("role"), 32)
                ],
                limit=8,
            )
            slide_image_roles = cls._dedupe_items(
                [
                    role
                    for role in slide_zone_roles
                    if any(token in role.casefold() for token in ("image", "hero", "visual", "icon", "illustration"))
                ],
                limit=4,
            )
            slide_profiles.append(
                {
                    "slide_index": slide.get("slide_index"),
                    "story_role": cls._normalize_text(slide.get("story_role"), limit=40),
                    "headline_hint": cls._normalize_text(slide.get("headline_hint"), limit=96),
                    "layout_type": cls._normalize_text(zone_map.get("layout_type"), limit=64),
                    "zone_roles": slide_zone_roles,
                    "zone_boxes": cls._compact_zone_boxes(zone_map, zone_limit=8),
                    "approved_image_zone_roles": slide_image_roles or approved_image_zone_roles,
                    "module_patterns": cls._reference_family_module_patterns(
                        zone_roles=slide_zone_roles or template_zone_roles,
                        story_roles=[slide.get("story_role")],
                        sequence_kind=sequence_kind,
                        content_structure_summary=cls._normalize_text(slide.get("sequence_summary"), limit=160),
                        motif_summary=cls._normalize_text(brand_visual_brief.get("motif_summary"), limit=180),
                    ),
                }
            )
        return {
            "family_name": family_name,
            "format_family": format_name,
            "sequence_kind": sequence_kind,
            "surface_policy": surface_policy,
            "slide_count": len(slides) or None,
            "story_roles": story_roles,
            "layout_archetypes": cls._dedupe_items(
                [
                    cls._normalize_text(layout_dna.get("layout_type"), 64),
                    cls._normalize_text(template_fit_brief.get("template_name"), 72),
                    cls._normalize_text(brand_visual_brief.get("dominant_layout_family"), 64),
                ],
                limit=4,
            ),
            "layout_lock_strength": (
                "strict"
                if surface_policy == "lock_template_surface"
                else "strong"
                if surface_policy == "style_reference_only"
                else "guided"
                if cls._normalize_text(template_fit_brief.get("mode"), limit=24) == "adapted_template"
                else "light"
            ),
            "preferred_zone_roles": template_zone_roles,
            "approved_image_zone_roles": approved_image_zone_roles,
            "text_zone_roles": text_zone_roles,
            "module_patterns": module_patterns,
            "density_target": cls._reference_family_density_target(
                format_name=format_name,
                editorial_dna=editorial_dna,
                hierarchy_summary=cls._normalize_text(brand_visual_brief.get("hierarchy_summary"), limit=180),
                content_structure_summary=cls._normalize_text(brand_visual_brief.get("content_structure_summary"), limit=180),
            ),
            "image_text_balance_target": cls._reference_family_balance_target(
                zone_roles=template_zone_roles,
                layout_type=cls._normalize_text(layout_dna.get("layout_type"), limit=64),
                composition_summary=cls._normalize_text(brand_visual_brief.get("composition_logic_summary"), limit=180),
            ),
            "spacing_rhythm": cls._normalize_text(
                brand_visual_brief.get("hierarchy_summary")
                or brand_visual_brief.get("content_structure_summary"),
                limit=180,
            ),
            "composition_summary": cls._normalize_text(
                brand_visual_brief.get("composition_logic_summary"),
                limit=180,
            ),
            "visual_craft_summary": cls._normalize_text(
                brand_visual_brief.get("visual_craft_summary"),
                limit=180,
            ),
            "subject_semantics_summary": cls._normalize_text(
                brand_visual_brief.get("subject_semantics_summary"),
                limit=180,
            ),
            "slide_profiles": slide_profiles,
        }

    @classmethod
    def _visual_brief(
        cls,
        brand_context: dict[str, Any],
        layout_decision: dict[str, Any],
        template_context: dict[str, Any] | None,
        reference_assets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        visual_identity = brand_context.get("visual_identity", {}) or {}
        design_system = visual_identity.get("design_system", {}) if isinstance(visual_identity.get("design_system"), dict) else {}
        typography = visual_identity.get("typography", {}) or {}
        palette = cls._derived_palette_roles(visual_identity)
        reusable_assets = visual_identity.get("reusable_design_assets", []) or []
        uploaded_fonts = typography.get("uploaded_font_assets", []) or []
        template_name = cls._normalize_text(layout_decision.get("template_name"), limit=72)
        template_zones = []
        sequence_pack = template_context.get("sequence_pack") if isinstance(template_context, dict) else {}
        sequence_slides = [dict(item) for item in sequence_pack.get("slides", []) if isinstance(item, dict)] if isinstance(sequence_pack, dict) else []
        format_family = "carousel" if sequence_pack else "static"
        if template_context:
            zone_map = template_context.get("zones", []) or template_context.get("zone_map", {}).get("zones", []) or []
            for zone in zone_map[:6]:
                if not isinstance(zone, dict):
                    continue
                role = cls._normalize_text(zone.get("role"), limit=24)
                if role:
                    template_zones.append(role)
        decorative_labels = []
        for asset in reusable_assets:
            if not isinstance(asset, dict):
                continue
            if asset.get("review_status") != "approved":
                continue
            decorative_labels.append(cls._normalize_text(asset.get("label") or asset.get("asset_kind"), limit=48))
        layout_preferences = design_system.get("layout_preferences", {}) if isinstance(design_system.get("layout_preferences"), dict) else {}
        typography_preferences = design_system.get("typography_preferences", {}) if isinstance(design_system.get("typography_preferences"), dict) else {}
        hierarchy_preferences = design_system.get("visual_hierarchy", {}) if isinstance(design_system.get("visual_hierarchy"), dict) else {}
        content_structure = design_system.get("content_structure", {}) if isinstance(design_system.get("content_structure"), dict) else {}
        image_treatment = design_system.get("image_treatment", {}) if isinstance(design_system.get("image_treatment"), dict) else {}
        visual_craft = design_system.get("visual_craft", {}) if isinstance(design_system.get("visual_craft"), dict) else {}
        composition_logic = design_system.get("composition_logic", {}) if isinstance(design_system.get("composition_logic"), dict) else {}
        subject_semantics = design_system.get("subject_semantics", {}) if isinstance(design_system.get("subject_semantics"), dict) else {}
        brand_cues = design_system.get("brand_cues", {}) if isinstance(design_system.get("brand_cues"), dict) else {}
        editorial_patterns = design_system.get("editorial_patterns", {}) if isinstance(design_system.get("editorial_patterns"), dict) else {}
        background_style = visual_identity.get("background_style") if isinstance(visual_identity.get("background_style"), dict) else (
            design_system.get("background_style", {}) if isinstance(design_system.get("background_style"), dict) else {}
        )
        template_zone_map = (
            template_context.get("zone_map")
            if isinstance(template_context, dict) and isinstance(template_context.get("zone_map"), dict)
            else (template_context if isinstance(template_context, dict) else {})
        )
        sequence_pack = template_context.get("sequence_pack") if isinstance(template_context, dict) and isinstance(template_context.get("sequence_pack"), dict) else {}
        sequence_slides = [dict(item) for item in sequence_pack.get("slides", []) if isinstance(item, dict)] if isinstance(sequence_pack, dict) else []
        sequence_slide_zone_map = {}
        for slide in sequence_slides:
            zone_map = slide.get("zone_map") if isinstance(slide.get("zone_map"), dict) else {}
            if isinstance(zone_map, dict) and zone_map.get("zones"):
                sequence_slide_zone_map = zone_map
                break
        template_layout_dna = {}
        template_composition_logic = {}
        template_visual_craft_dna = {}
        template_subject_semantics = {}
        template_editorial_dna = {}
        for candidate in [template_zone_map, sequence_slide_zone_map, template_context]:
            if not isinstance(candidate, dict):
                continue
            if not template_layout_dna:
                if isinstance(candidate.get("layout_dna"), dict):
                    template_layout_dna = candidate.get("layout_dna") or {}
                elif candidate.get("zones"):
                    template_layout_dna = candidate
            if not template_composition_logic and isinstance(candidate.get("composition_logic"), dict):
                template_composition_logic = candidate.get("composition_logic") or {}
            if not template_visual_craft_dna and isinstance(candidate.get("visual_craft_dna"), dict):
                template_visual_craft_dna = candidate.get("visual_craft_dna") or {}
            if not template_subject_semantics and isinstance(candidate.get("subject_semantics"), dict):
                template_subject_semantics = candidate.get("subject_semantics") or {}
            if not template_editorial_dna and isinstance(candidate.get("editorial_dna"), dict):
                template_editorial_dna = candidate.get("editorial_dna") or {}
        if not template_composition_logic and isinstance(template_layout_dna, dict):
            inferred_zone_roles = [
                cls._normalize_text(zone.get("role"), limit=32)
                for zone in (template_layout_dna.get("zones") or [])
                if isinstance(zone, dict) and cls._normalize_text(zone.get("role"), limit=32)
            ]
            if inferred_zone_roles:
                template_composition_logic = {
                    "balance": "split_focus" if {"headline", "image"} <= set(inferred_zone_roles) else "structured_modular",
                    "framing": "stacked_sections" if inferred_zone_roles.count("body") > 1 else "editorial_panel",
                    "layering": "flat_editorial",
                }
        if not template_editorial_dna and sequence_slides:
            inferred_story_roles = cls._dedupe_items(
                [slide.get("story_role") for slide in sequence_slides],
                limit=8,
            )
            inferred_headline_patterns = cls._dedupe_items(
                [
                    slide.get("headline_hint")
                    for slide in sequence_slides
                    if not cls._looks_like_weak_sequence_hint(str(slide.get("headline_hint") or ""))
                ],
                limit=6,
            )
            inferred_supporting_patterns = cls._dedupe_items(
                [
                    slide.get("sequence_summary") or slide.get("structural_cues")
                    for slide in sequence_slides
                ],
                limit=6,
            )
            if inferred_story_roles or inferred_headline_patterns or inferred_supporting_patterns:
                template_editorial_dna = {
                    "format_family": format_family,
                    "page_count_hint": len(sequence_slides),
                    "story_arc_roles": inferred_story_roles,
                    "headline_patterns": inferred_headline_patterns,
                    "supporting_patterns": inferred_supporting_patterns,
                    "storytelling_mode": "sample_sequence_guided",
                }
        component_motifs = visual_identity.get("component_motifs") if isinstance(visual_identity.get("component_motifs"), dict) else (
            design_system.get("component_motifs", {}) if isinstance(design_system.get("component_motifs"), dict) else {}
        )
        gradient_preferences = visual_identity.get("gradient_preferences") if isinstance(visual_identity.get("gradient_preferences"), list) else (
            design_system.get("gradient_preferences", []) if isinstance(design_system.get("gradient_preferences"), list) else []
        )
        preferred_zone_roles = cls._summary_list(layout_preferences.get("preferred_zone_roles"), limit=8, item_limit=24)
        motif_keys = [
            cls._normalize_text(key.replace("_", " "), limit=36)
            for key, value in component_motifs.items()
            if value
        ]
        dominant_layout_family = cls._normalize_text(
            layout_preferences.get("dominant") or (layout_preferences.get("common") or [None])[0],
            limit=48,
        )
        background_style_summary = cls._join_summary(
            cls._summary_list(
                [
                    background_style.get("type"),
                    background_style.get("description"),
                    background_style.get("primary_hex"),
                ],
                limit=3,
                item_limit=48,
            ),
            limit=160,
        )
        motif_summary = cls._join_summary(cls._summary_list(motif_keys, limit=5, item_limit=36), limit=180)
        typography_summary = cls._join_summary(
            cls._summary_list(
                [
                    *(typography_preferences.get("heading_styles") or []),
                    *(typography_preferences.get("text_alignments") or []),
                    *(typography_preferences.get("dominant_cases") or []),
                    *(typography_preferences.get("emphasis_patterns") or []),
                ],
                limit=6,
                item_limit=40,
            ),
            limit=200,
        )
        hierarchy_summary = cls._join_summary(
            cls._summary_list(
                [
                    *(hierarchy_preferences.get("focal_roles") or []),
                    *(hierarchy_preferences.get("density_preferences") or []),
                    *(hierarchy_preferences.get("whitespace_preferences") or []),
                ],
                limit=6,
                item_limit=36,
            ),
            limit=180,
        )
        content_structure_summary = cls._join_summary(
            cls._summary_list(
                [
                    *(content_structure.get("storytelling_modes") or []),
                    content_structure.get("cta_prominence"),
                ],
                limit=4,
                item_limit=40,
            ),
            limit=160,
        )
        image_treatment_summary = cls._join_summary(
            cls._summary_list(
                [
                    *(image_treatment.get("styles") or []),
                    *(image_treatment.get("crops") or []),
                    *(image_treatment.get("subject_focus_modes") or []),
                ],
                limit=6,
                item_limit=36,
            ),
            limit=140,
        )
        visual_craft_summary = cls._join_summary(
            cls._summary_list(
                [
                    *(visual_craft.get("depth_styles") or []),
                    *(visual_craft.get("rendering_styles") or []),
                    *(visual_craft.get("lighting_modes") or []),
                    *(visual_craft.get("polish_levels") or []),
                    *(visual_craft.get("material_cues") or []),
                ],
                limit=8,
                item_limit=36,
            ),
            limit=220,
        )
        composition_logic_summary = cls._join_summary(
            cls._summary_list(
                [
                    *(composition_logic.get("balances") or []),
                    *(composition_logic.get("framings") or []),
                    *(composition_logic.get("layerings") or []),
                ],
                limit=6,
                item_limit=36,
            ),
            limit=180,
        )
        subject_semantics_summary = cls._join_summary(
            cls._summary_list(
                [
                    *(subject_semantics.get("scene_types") or []),
                    *(subject_semantics.get("primary_subjects") or []),
                    *(subject_semantics.get("domain_cues") or []),
                    *(subject_semantics.get("financial_objects") or []),
                    *(subject_semantics.get("human_presence_modes") or []),
                    *(subject_semantics.get("abstraction_levels") or []),
                ],
                limit=8,
                item_limit=36,
            ),
            limit=220,
        )
        brand_cue_summary = cls._join_summary(
            cls._summary_list(
                [
                    *(brand_cues.get("tone_keywords") or []),
                    *(brand_cues.get("trust_markers") or []),
                ],
                limit=6,
                item_limit=36,
            ),
            limit=180,
        )
        editorial_story_arc_summary = cls._join_summary(
            cls._summary_list(editorial_patterns.get("dominant_story_arc"), limit=8, item_limit=28),
            limit=200,
        )
        editorial_style_summary = cls._join_summary(
            cls._summary_list(editorial_patterns.get("explanation_styles"), limit=4, item_limit=36),
            limit=160,
        )
        logo_position = cls._normalize_text(
            visual_identity.get("logo_position") or design_system.get("logo_anchor"),
            limit=40,
        )
        visual_style_policy = (
            design_system.get("visual_style_policy", {})
            if isinstance(design_system.get("visual_style_policy"), dict)
            else {}
        )
        format_visual_style_profiles = (
            design_system.get("format_visual_style_profiles", {})
            if isinstance(design_system.get("format_visual_style_profiles"), dict)
            else {}
        )
        active_visual_style_policy = (
            format_visual_style_profiles.get(format_family, {})
            if isinstance(format_visual_style_profiles.get(format_family), dict)
            else {}
        ) or visual_style_policy
        visual_style_summary = cls._join_summary(
            cls._summary_list(
                [
                    active_visual_style_policy.get("dominant_image_mode") or visual_style_policy.get("dominant_image_mode"),
                    active_visual_style_policy.get("dominant_depth_mode") or visual_style_policy.get("dominant_depth_mode"),
                    active_visual_style_policy.get("dominant_rendering_mode") or visual_style_policy.get("dominant_rendering_mode"),
                    active_visual_style_policy.get("dominant_subject_mode") or visual_style_policy.get("dominant_subject_mode"),
                    active_visual_style_policy.get("dominant_support_mode") or visual_style_policy.get("dominant_support_mode"),
                    active_visual_style_policy.get("dominant_story_visual_role") or visual_style_policy.get("dominant_story_visual_role"),
                    active_visual_style_policy.get("style_consistency") or visual_style_policy.get("style_consistency"),
                    active_visual_style_policy.get("three_d_usage") or visual_style_policy.get("three_d_usage"),
                    active_visual_style_policy.get("reference_pattern_priority") or visual_style_policy.get("reference_pattern_priority"),
                ],
                limit=9,
                item_limit=28,
            ),
            limit=220,
        )
        reference_visual_profiles = []
        for reference in (visual_identity.get("reference_creatives", []) or [])[:6]:
            if not isinstance(reference, dict):
                continue
            profile = (
                reference.get("visual_style_profile")
                if isinstance(reference.get("visual_style_profile"), dict)
                else (
                    (reference.get("style_characteristics") or {}).get("visual_style_profile")
                    if isinstance(reference.get("style_characteristics"), dict)
                    else {}
                )
            )
            if not isinstance(profile, dict) or not profile:
                continue
            reference_visual_profiles.append(
                {
                    "asset_id": cls._normalize_text(reference.get("asset_id"), limit=64),
                    "image_mode": cls._normalize_text(profile.get("image_mode"), limit=24),
                    "depth_mode": cls._normalize_text(profile.get("depth_mode"), limit=24),
                    "rendering_mode": cls._normalize_text(profile.get("rendering_mode"), limit=24),
                    "subject_mode": cls._normalize_text(profile.get("subject_mode"), limit=24),
                    "support_mode": cls._normalize_text(profile.get("support_mode"), limit=24),
                    "story_visual_role": cls._normalize_text(profile.get("story_visual_role"), limit=24),
                    "consistency_hint": cls._normalize_text(profile.get("consistency_hint"), limit=24),
                }
            )
        return {
            "mode": cls._normalize_text(layout_decision.get("mode"), limit=24),
            "template_name": template_name,
            "template_rationale": cls._dedupe_items([cls._normalize_text(item, 120) for item in layout_decision.get("rationale", []) or []], limit=2),
            "template_zone_roles": cls._dedupe_items(template_zones, limit=6),
            "sequence_template_family": cls._normalize_text(sequence_pack.get("family_name"), limit=72) if isinstance(sequence_pack, dict) else "",
            "sequence_slide_count": len(sequence_slides),
            "palette_roles": {
                key: cls._normalize_text(value, limit=24)
                for key, value in palette.items()
                if cls._normalize_text(value, limit=24)
            },
            "font_families": cls._dedupe_items(
                [
                    cls._normalize_text(item.get("name"), limit=48)
                    for item in typography.get("font_families", []) or []
                    if isinstance(item, dict)
                ],
                limit=4,
            ),
            "uploaded_font_count": len(uploaded_fonts),
            "sample_count": int(design_system.get("sample_count") or 0) if str(design_system.get("sample_count") or "").isdigit() else 0,
            "dominant_layout_family": dominant_layout_family,
            "preferred_zone_roles": preferred_zone_roles,
            "background_style_summary": background_style_summary,
            "motif_summary": motif_summary,
            "typography_summary": typography_summary,
            "hierarchy_summary": hierarchy_summary,
            "content_structure_summary": content_structure_summary,
            "image_treatment_summary": image_treatment_summary,
            "visual_craft_summary": visual_craft_summary,
            "composition_logic_summary": composition_logic_summary,
            "subject_semantics_summary": subject_semantics_summary,
            "brand_cue_summary": brand_cue_summary,
            "editorial_story_arc_summary": editorial_story_arc_summary,
            "editorial_style_summary": editorial_style_summary,
            "visual_style_summary": visual_style_summary,
            "logo_position": logo_position,
            "template_layout_dna": cls._compact_layout_dna(template_layout_dna),
            "template_composition_logic": cls._compact_composition_logic_dna(template_composition_logic),
            "template_visual_craft": cls._compact_visual_craft_dna(template_visual_craft_dna),
            "template_subject_semantics": cls._compact_subject_semantics_dna(template_subject_semantics),
            "template_editorial_dna": cls._compact_editorial_dna(template_editorial_dna),
            "template_sequence_pack": cls._compact_sequence_pack(sequence_pack),
            "visual_style_policy": {
                "sample_count": int(active_visual_style_policy.get("sample_count") or visual_style_policy.get("sample_count") or 0),
                "dominant_image_mode": cls._normalize_text(
                    active_visual_style_policy.get("dominant_image_mode") or visual_style_policy.get("dominant_image_mode"),
                    limit=24,
                ),
                "dominant_depth_mode": cls._normalize_text(
                    active_visual_style_policy.get("dominant_depth_mode") or visual_style_policy.get("dominant_depth_mode"),
                    limit=24,
                ),
                "dominant_rendering_mode": cls._normalize_text(
                    active_visual_style_policy.get("dominant_rendering_mode") or visual_style_policy.get("dominant_rendering_mode"),
                    limit=24,
                ),
                "dominant_subject_mode": cls._normalize_text(
                    active_visual_style_policy.get("dominant_subject_mode") or visual_style_policy.get("dominant_subject_mode"),
                    limit=24,
                ),
                "dominant_support_mode": cls._normalize_text(
                    active_visual_style_policy.get("dominant_support_mode") or visual_style_policy.get("dominant_support_mode"),
                    limit=24,
                ),
                "dominant_story_visual_role": cls._normalize_text(
                    active_visual_style_policy.get("dominant_story_visual_role") or visual_style_policy.get("dominant_story_visual_role"),
                    limit=24,
                ),
                "style_consistency": cls._normalize_text(
                    active_visual_style_policy.get("style_consistency") or visual_style_policy.get("style_consistency"),
                    limit=24,
                ),
                "three_d_usage": cls._normalize_text(
                    active_visual_style_policy.get("three_d_usage") or visual_style_policy.get("three_d_usage"),
                    limit=24,
                ),
                "reference_pattern_priority": cls._normalize_text(
                    active_visual_style_policy.get("reference_pattern_priority") or visual_style_policy.get("reference_pattern_priority"),
                    limit=32,
                ),
                "image_modes": cls._summary_list(
                    active_visual_style_policy.get("image_modes") or visual_style_policy.get("image_modes"),
                    limit=4,
                    item_limit=24,
                ),
                "depth_modes": cls._summary_list(
                    active_visual_style_policy.get("depth_modes") or visual_style_policy.get("depth_modes"),
                    limit=4,
                    item_limit=24,
                ),
                "rendering_modes": cls._summary_list(
                    active_visual_style_policy.get("rendering_modes") or visual_style_policy.get("rendering_modes"),
                    limit=4,
                    item_limit=24,
                ),
                "subject_modes": cls._summary_list(
                    active_visual_style_policy.get("subject_modes") or visual_style_policy.get("subject_modes"),
                    limit=5,
                    item_limit=24,
                ),
                "support_modes": cls._summary_list(
                    active_visual_style_policy.get("support_modes") or visual_style_policy.get("support_modes"),
                    limit=5,
                    item_limit=24,
                ),
                "story_visual_roles": cls._summary_list(
                    active_visual_style_policy.get("story_visual_roles") or visual_style_policy.get("story_visual_roles"),
                    limit=5,
                    item_limit=24,
                ),
            },
            "format_visual_style_profiles": {
                key: value
                for key, value in format_visual_style_profiles.items()
                if isinstance(value, dict)
            },
            "reference_visual_profiles": reference_visual_profiles,
            "visual_craft": {
                "depth_styles": cls._summary_list(visual_craft.get("depth_styles"), limit=6, item_limit=28),
                "rendering_styles": cls._summary_list(visual_craft.get("rendering_styles"), limit=6, item_limit=28),
                "lighting_modes": cls._summary_list(visual_craft.get("lighting_modes"), limit=6, item_limit=28),
                "polish_levels": cls._summary_list(visual_craft.get("polish_levels"), limit=4, item_limit=28),
                "material_cues": cls._summary_list(visual_craft.get("material_cues"), limit=6, item_limit=28),
                "dimensionality_cues": cls._summary_list(visual_craft.get("dimensionality_cues"), limit=6, item_limit=28),
            },
            "composition_logic": {
                "balances": cls._summary_list(composition_logic.get("balances"), limit=4, item_limit=28),
                "framings": cls._summary_list(composition_logic.get("framings"), limit=4, item_limit=28),
                "layerings": cls._summary_list(composition_logic.get("layerings"), limit=4, item_limit=28),
            },
            "subject_semantics": {
                "scene_types": cls._summary_list(subject_semantics.get("scene_types"), limit=6, item_limit=28),
                "primary_subjects": cls._summary_list(subject_semantics.get("primary_subjects"), limit=6, item_limit=28),
                "domain_cues": cls._summary_list(subject_semantics.get("domain_cues"), limit=6, item_limit=28),
                "financial_objects": cls._summary_list(subject_semantics.get("financial_objects"), limit=6, item_limit=28),
                "human_presence_modes": cls._summary_list(subject_semantics.get("human_presence_modes"), limit=4, item_limit=28),
                "abstraction_levels": cls._summary_list(subject_semantics.get("abstraction_levels"), limit=4, item_limit=28),
            },
            "gradient_preferences": [
                {
                    "type": cls._normalize_text(item.get("type"), limit=24),
                    "direction": cls._normalize_text(item.get("direction"), limit=24),
                    "start_color": cls._normalize_text(item.get("start_color"), limit=16),
                    "end_color": cls._normalize_text(item.get("end_color"), limit=16),
                }
                for item in gradient_preferences[:3]
                if isinstance(item, dict)
            ],
            "style_direction": cls._normalize_text(
                " ".join(
                    value
                    for value in [
                        cls._normalize_text(item.get("style_characteristics"), limit=100)
                        for item in (visual_identity.get("reference_creatives", []) or [])[:2]
                        if isinstance(item, dict)
                    ]
                    + [
                        background_style_summary,
                        motif_summary,
                        hierarchy_summary,
                        content_structure_summary,
                        image_treatment_summary,
                        visual_craft_summary,
                        composition_logic_summary,
                        subject_semantics_summary,
                        editorial_story_arc_summary,
                        editorial_style_summary,
                    ]
                    if value
                ),
                limit=220,
            ),
            "decorative_assets": cls._dedupe_items(decorative_labels, limit=4),
            "reference_asset_roles": cls._dedupe_items(
                [
                    cls._normalize_text(asset.get("asset_role"), limit=32)
                    for asset in reference_assets
                    if isinstance(asset, dict)
                ],
                limit=6,
            ),
            "design_system": {
                "sample_count": int(design_system.get("sample_count") or 0) if str(design_system.get("sample_count") or "").isdigit() else 0,
                "dominant_layout_family": dominant_layout_family,
                "preferred_zone_roles": preferred_zone_roles,
                "background_style_summary": background_style_summary,
                "motif_summary": motif_summary,
                "typography_summary": typography_summary,
                "hierarchy_summary": hierarchy_summary,
                "content_structure_summary": content_structure_summary,
                "image_treatment_summary": image_treatment_summary,
                "visual_craft_summary": visual_craft_summary,
                "composition_logic_summary": composition_logic_summary,
                "subject_semantics_summary": subject_semantics_summary,
                "brand_cue_summary": brand_cue_summary,
                "editorial_story_arc_summary": editorial_story_arc_summary,
                "editorial_style_summary": editorial_style_summary,
                "visual_style_summary": visual_style_summary,
                "logo_position": logo_position,
                "visual_style_policy": {
                    "sample_count": int(visual_style_policy.get("sample_count") or 0),
                    "dominant_image_mode": cls._normalize_text(visual_style_policy.get("dominant_image_mode"), limit=24),
                    "dominant_depth_mode": cls._normalize_text(visual_style_policy.get("dominant_depth_mode"), limit=24),
                    "dominant_rendering_mode": cls._normalize_text(visual_style_policy.get("dominant_rendering_mode"), limit=24),
                    "dominant_subject_mode": cls._normalize_text(visual_style_policy.get("dominant_subject_mode"), limit=24),
                    "dominant_support_mode": cls._normalize_text(visual_style_policy.get("dominant_support_mode"), limit=24),
                    "dominant_story_visual_role": cls._normalize_text(visual_style_policy.get("dominant_story_visual_role"), limit=24),
                    "style_consistency": cls._normalize_text(visual_style_policy.get("style_consistency"), limit=24),
                    "three_d_usage": cls._normalize_text(visual_style_policy.get("three_d_usage"), limit=24),
                    "reference_pattern_priority": cls._normalize_text(visual_style_policy.get("reference_pattern_priority"), limit=32),
                    "image_modes": cls._summary_list(visual_style_policy.get("image_modes"), limit=4, item_limit=24),
                    "depth_modes": cls._summary_list(visual_style_policy.get("depth_modes"), limit=4, item_limit=24),
                    "rendering_modes": cls._summary_list(visual_style_policy.get("rendering_modes"), limit=4, item_limit=24),
                    "subject_modes": cls._summary_list(visual_style_policy.get("subject_modes"), limit=5, item_limit=24),
                    "support_modes": cls._summary_list(visual_style_policy.get("support_modes"), limit=5, item_limit=24),
                    "story_visual_roles": cls._summary_list(visual_style_policy.get("story_visual_roles"), limit=5, item_limit=24),
                },
                "format_visual_style_profiles": {
                    key: value
                    for key, value in format_visual_style_profiles.items()
                    if isinstance(value, dict)
                },
                "visual_craft": {
                    "depth_styles": cls._summary_list(visual_craft.get("depth_styles"), limit=6, item_limit=28),
                    "rendering_styles": cls._summary_list(visual_craft.get("rendering_styles"), limit=6, item_limit=28),
                    "lighting_modes": cls._summary_list(visual_craft.get("lighting_modes"), limit=6, item_limit=28),
                    "polish_levels": cls._summary_list(visual_craft.get("polish_levels"), limit=4, item_limit=28),
                    "material_cues": cls._summary_list(visual_craft.get("material_cues"), limit=6, item_limit=28),
                    "dimensionality_cues": cls._summary_list(visual_craft.get("dimensionality_cues"), limit=6, item_limit=28),
                },
                "composition_logic": {
                    "balances": cls._summary_list(composition_logic.get("balances"), limit=4, item_limit=28),
                    "framings": cls._summary_list(composition_logic.get("framings"), limit=4, item_limit=28),
                    "layerings": cls._summary_list(composition_logic.get("layerings"), limit=4, item_limit=28),
                },
                "subject_semantics": {
                    "scene_types": cls._summary_list(subject_semantics.get("scene_types"), limit=6, item_limit=28),
                    "primary_subjects": cls._summary_list(subject_semantics.get("primary_subjects"), limit=6, item_limit=28),
                    "domain_cues": cls._summary_list(subject_semantics.get("domain_cues"), limit=6, item_limit=28),
                    "financial_objects": cls._summary_list(subject_semantics.get("financial_objects"), limit=6, item_limit=28),
                    "human_presence_modes": cls._summary_list(subject_semantics.get("human_presence_modes"), limit=4, item_limit=28),
                    "abstraction_levels": cls._summary_list(subject_semantics.get("abstraction_levels"), limit=4, item_limit=28),
                },
                "editorial_patterns": {
                    "static": editorial_patterns.get("static", {}) if isinstance(editorial_patterns.get("static"), dict) else {},
                    "carousel": editorial_patterns.get("carousel", {}) if isinstance(editorial_patterns.get("carousel"), dict) else {},
                    "infographic": editorial_patterns.get("infographic", {}) if isinstance(editorial_patterns.get("infographic"), dict) else {},
                },
                "template_layout_dna": cls._compact_layout_dna(template_layout_dna),
                "template_composition_logic": cls._compact_composition_logic_dna(template_composition_logic),
                "template_visual_craft": cls._compact_visual_craft_dna(template_visual_craft_dna),
                "template_subject_semantics": cls._compact_subject_semantics_dna(template_subject_semantics),
                "template_editorial_dna": cls._compact_editorial_dna(template_editorial_dna),
            },
        }

    @classmethod
    def _objective_brief(cls, objective_context: dict[str, Any]) -> dict[str, Any]:
        configuration = objective_context.get("configuration", {}) if isinstance(objective_context, dict) else {}
        return {
            "name": cls._normalize_text(objective_context.get("name"), limit=64),
            "description": cls._normalize_text(objective_context.get("description"), limit=220),
            "primary_goal": cls._normalize_text(configuration.get("primary_goal"), limit=120),
            "conversion_priority": cls._normalize_text(configuration.get("conversion_priority"), limit=64),
            "market_positioning": cls._normalize_text(configuration.get("market_positioning"), limit=120),
            "cta_bias": cls._normalize_text(configuration.get("cta_bias"), limit=64),
        }

    @classmethod
    def _normalize_prompt_intelligence_platform_key(cls, value: Any) -> str:
        text = cls._normalize_text(value, limit=40).casefold()
        if not text:
            return ""
        text = text.replace("-", "_").replace(" ", "_").replace("/", "_").strip("_")
        while "__" in text:
            text = text.replace("__", "_")
        if text.startswith("instagram"):
            return "instagram"
        if text.startswith("linkedin"):
            return "linkedin"
        if text == "twitter" or text.startswith("twitter_") or text.startswith("x_"):
            return "x"
        if text.startswith("youtube"):
            return "youtube_thumbnail"
        return text

    @classmethod
    def _prompt_intelligence_platforms(cls, value: Any) -> list[str]:
        if value is None:
            return []
        raw_items = value if isinstance(value, (list, tuple, set)) else [value]
        normalized: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            text = cls._normalize_prompt_intelligence_platform_key(item)
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        return normalized

    @classmethod
    def _prompt_intelligence_starter_records(cls, value: Any) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        if value in (None, ""):
            return records
        if isinstance(value, dict):
            for key, item in value.items():
                platform_key = cls._normalize_prompt_intelligence_platform_key(key)
                platform_stub = [platform_key] if platform_key else []
                if isinstance(item, dict):
                    records.append(
                        {
                            **item,
                            **(
                                {"platforms": platform_stub}
                                if platform_stub and not (item.get("platforms") or item.get("platform") or item.get("platform_preset"))
                                else {}
                            ),
                        }
                    )
                    continue
                if isinstance(item, (list, tuple, set)):
                    for nested in item:
                        if isinstance(nested, dict):
                            records.append(
                                {
                                    **nested,
                                    **(
                                        {"platforms": platform_stub}
                                        if platform_stub
                                        and not (nested.get("platforms") or nested.get("platform") or nested.get("platform_preset"))
                                        else {}
                                    ),
                                }
                            )
                        elif nested not in (None, ""):
                            record = {"text": nested}
                            if platform_stub:
                                record["platforms"] = platform_stub
                            records.append(record)
                    continue
                record = {"text": item}
                if platform_stub:
                    record["platforms"] = platform_stub
                records.append(record)
            return records
        if isinstance(value, (list, tuple, set)):
            for item in value:
                if isinstance(item, dict):
                    records.append(item)
                elif item not in (None, ""):
                    records.append({"text": item})
            return records
        return [{"text": value}]

    @classmethod
    def _prompt_intelligence_lookup(cls, source: Any, key: str) -> Any:
        if not isinstance(source, dict):
            return None
        normalized_key = cls._normalize_prompt_intelligence_platform_key(key)
        if not normalized_key:
            return None
        for candidate_key, candidate_value in source.items():
            if cls._normalize_prompt_intelligence_platform_key(candidate_key) == normalized_key:
                return candidate_value
        return None

    @classmethod
    def _prompt_intelligence_lines(cls, value: Any, *, limit: int = 6) -> list[str]:
        lines: list[str] = []
        seen: set[str] = set()

        def _append(candidate: Any) -> None:
            text = cls._truncate_text_on_word_boundary(candidate, 120).strip(" ,.;:-")
            if not text:
                return
            key = cls._summary_fragment_key(text)
            if not key or key in seen:
                return
            seen.add(key)
            lines.append(text)

        def _visit(candidate: Any) -> None:
            if len(lines) >= limit or candidate in (None, ""):
                return
            if isinstance(candidate, str):
                _append(candidate)
                return
            if isinstance(candidate, (list, tuple, set)):
                for item in candidate:
                    _visit(item)
                    if len(lines) >= limit:
                        break
                return
            if isinstance(candidate, dict):
                preferred_keys = (
                    "rules",
                    "guidance",
                    "description",
                    "notes",
                    "summary",
                    "text",
                    "value",
                    "dos",
                    "donts",
                    "preferred",
                    "avoid",
                    "examples",
                    "example",
                    "hashtags",
                    "keywords",
                    "cta",
                    "hook",
                )
                visited_preferred = False
                for key in preferred_keys:
                    if key not in candidate:
                        continue
                    visited_preferred = True
                    _visit(candidate.get(key))
                    if len(lines) >= limit:
                        break
                if visited_preferred:
                    return
                for key, item in candidate.items():
                    normalized_key = str(key).strip().casefold()
                    if normalized_key in {
                        "platform",
                        "platforms",
                        "platform_preset",
                        "supported_platforms",
                        "id",
                        "channel",
                        "channels",
                    }:
                        continue
                    _visit(item)
                    if len(lines) >= limit:
                        break
                return
            _append(candidate)

        _visit(value)
        return lines

    @classmethod
    def _prompt_intelligence_brief(
        cls,
        prompt_intelligence: dict[str, Any],
        studio_panel: dict[str, Any],
    ) -> dict[str, Any]:
        prompt_intelligence = prompt_intelligence if isinstance(prompt_intelligence, dict) else {}
        platform_preset = cls._normalize_prompt_intelligence_platform_key(studio_panel.get("platform_preset"))
        raw_starters = cls._prompt_intelligence_starter_records(prompt_intelligence.get("prompt_starters") or [])
        starter_patterns: list[dict[str, Any]] = []
        seen_starters: set[str] = set()
        for item in raw_starters[:12]:
            if not isinstance(item, dict):
                continue
            text = cls._truncate_text_on_word_boundary(
                item.get("prompt")
                or item.get("starter")
                or item.get("text")
                or item.get("value")
                or item.get("label")
                or item.get("name"),
                140,
            ).strip()
            if not text:
                continue
            key = cls._summary_fragment_key(text)
            if key in seen_starters:
                continue
            seen_starters.add(key)
            record: dict[str, Any] = {"text": text}
            platforms = cls._prompt_intelligence_platforms(
                item.get("platforms") or item.get("platform") or item.get("platform_preset")
            )
            notes = cls._compose_summary(
                [
                    item.get("description"),
                    item.get("notes"),
                    item.get("objective"),
                    item.get("goal"),
                ],
                item_limit=72,
                summary_limit=140,
                max_items=2,
            )
            if platforms:
                record["platforms"] = platforms
            if notes:
                record["notes"] = notes
            starter_patterns.append(record)
        applicable_starters = [
            item for item in starter_patterns if not item.get("platforms") or platform_preset in item.get("platforms", [])
        ]
        starter_patterns = (applicable_starters or starter_patterns)[:4]
        starter_texts = [str(item.get("text") or "").strip() for item in starter_patterns if str(item.get("text") or "").strip()]

        platform_rules = prompt_intelligence.get("platform_rules") or {}
        current_platform_rules: list[str] = []
        global_rules: list[str] = []
        if isinstance(platform_rules, dict):
            nested_platform_rules = (
                platform_rules.get("platforms")
                or platform_rules.get("by_platform")
                or platform_rules.get("rules_by_platform")
                or {}
            )
            current_platform_rules = cls._prompt_intelligence_lines(
                [
                    cls._prompt_intelligence_lookup(platform_rules, platform_preset),
                    cls._prompt_intelligence_lookup(nested_platform_rules, platform_preset) if isinstance(nested_platform_rules, dict) else None,
                ],
                limit=4,
            )
            global_rules = cls._prompt_intelligence_lines(
                [
                    cls._prompt_intelligence_lookup(platform_rules, "global"),
                    cls._prompt_intelligence_lookup(platform_rules, "default"),
                    cls._prompt_intelligence_lookup(platform_rules, "all"),
                    cls._prompt_intelligence_lookup(platform_rules, "shared"),
                    cls._prompt_intelligence_lookup(platform_rules, "general"),
                ],
                limit=4,
            )
            if not current_platform_rules and not global_rules:
                fallback_rules = {
                    key: value
                    for key, value in platform_rules.items()
                    if cls._normalize_prompt_intelligence_platform_key(key)
                    not in {"platforms", "by_platform", "rules_by_platform"}
                }
                global_rules = cls._prompt_intelligence_lines(fallback_rules, limit=4)
        else:
            global_rules = cls._prompt_intelligence_lines(platform_rules, limit=4)

        summary = cls._compose_summary(
            [*starter_texts[:2], *current_platform_rules, *global_rules],
            item_limit=96,
            summary_limit=280,
            max_items=4,
        )
        return {
            "platform_preset": platform_preset,
            "starter_patterns": starter_patterns,
            "starter_texts": starter_texts[:4],
            "current_platform_rules": current_platform_rules[:4],
            "global_rules": global_rules[:4],
            "summary": summary,
        }

    @classmethod
    def _render_constraints(
        cls,
        prompt: str,
        studio_panel: dict[str, Any],
        layout_decision: dict[str, Any],
    ) -> dict[str, Any]:
        preset = cls._normalize_text(studio_panel.get("platform_preset"), limit=32) or "instagram"
        format_name = cls._normalize_text(studio_panel.get("format"), limit=32) or "static"
        size = studio_panel.get("size", {}) or {}
        prompt_words = len(str(prompt or "").split())
        return {
            "platform_preset": preset,
            "format": format_name,
            "file_type": cls._normalize_text(studio_panel.get("file_type"), limit=16),
            "canvas_size": {
                "width": int(size.get("width", 0) or 0),
                "height": int(size.get("height", 0) or 0),
            },
            "text_density": "high" if prompt_words > 30 else ("medium" if prompt_words > 16 else "low"),
            "max_headline_words": 8 if preset == "youtube_thumbnail" else (10 if preset in {"instagram", "x"} else 14),
            "max_body_sentences": 2 if preset in {"instagram", "youtube_thumbnail"} else 3,
            "prefer_compact_cta": preset in {"instagram", "x", "youtube_thumbnail"},
            "mode": cls._normalize_text(layout_decision.get("mode"), limit=24),
        }

    @classmethod
    def _session_brief(cls, session_memory: dict[str, Any], conversation_context: dict[str, Any]) -> dict[str, Any]:
        follow_up_intent = (session_memory or {}).get("follow_up_intent", {}) or {}
        latest_content = (session_memory or {}).get("latest_content_version", {}) or {}
        uses_previous_output = cls._should_use_prior_copy_context(session_memory)
        uses_prior_layout_context = cls._should_use_prior_layout_context(session_memory)
        prior_scene_graph = latest_content.get("scene_graph", {}) if isinstance(latest_content, dict) else {}
        prior_styles = prior_scene_graph.get("styles", {}) if isinstance(prior_scene_graph, dict) else {}
        prior_generation_decision = latest_content.get("generation_decision", {}) if isinstance(latest_content, dict) else {}
        prior_layout_archetype = (
            cls._normalize_text(prior_styles.get("layout_archetype"), limit=48)
            or cls._normalize_text(prior_generation_decision.get("layout_archetype"), limit=48)
            or cls._normalize_text((prior_generation_decision.get("planning_hints") or {}).get("layout_archetype"), limit=48)
        )
        return {
            "follow_up_mode": cls._normalize_text(follow_up_intent.get("mode"), limit=24),
            "uses_previous_output": uses_previous_output,
            "prior_headline": cls._normalize_text(latest_content.get("headline"), limit=120) if uses_previous_output else "",
            "prior_layout_archetype": prior_layout_archetype if uses_prior_layout_context else "",
            "regeneration_policy": (
                "Preserve strategic direction but choose a distinctly different layout archetype from the prior creative."
                if cls._normalize_text(follow_up_intent.get("mode"), limit=24) == "variant_of_previous"
                else (
                    "Treat the prior creative as the base and keep the layout family unless the user asks to change it."
                    if cls._normalize_text(follow_up_intent.get("mode"), limit=24) == "modify_previous"
                    else "Use prior outputs only as light background context."
                )
            ),
            "message_count": int((conversation_context or {}).get("message_count", 0) or 0),
        }

    @classmethod
    def _content_format_brief(
        cls,
        content_format_guide: dict[str, Any] | None,
        studio_panel: dict[str, Any],
    ) -> dict[str, Any]:
        guide = content_format_guide if isinstance(content_format_guide, dict) else {}
        if not guide:
            return {}
        format_name = cls._normalize_text(studio_panel.get("format"), limit=32).casefold() or "static"
        platform_preset = cls._normalize_prompt_intelligence_platform_key(studio_panel.get("platform_preset"))
        definitions = guide.get("definitions") if isinstance(guide.get("definitions"), dict) else {}
        expectations = guide.get("format_expectations") if isinstance(guide.get("format_expectations"), dict) else {}
        platform_guidance = guide.get("platform_guidance") if isinstance(guide.get("platform_guidance"), dict) else {}
        export_guidance = guide.get("export_guidance") if isinstance(guide.get("export_guidance"), dict) else {}
        legacy_rules = guide.get("rules") if isinstance(guide.get("rules"), dict) else {}

        current_expectations = expectations.get(format_name) if isinstance(expectations.get(format_name), dict) else {}
        current_platform_guidance = (
            platform_guidance.get(platform_preset)
            if isinstance(platform_guidance.get(platform_preset), dict)
            else {}
        )
        export_by_platform = (
            export_guidance.get("by_platform_format")
            if isinstance(export_guidance.get("by_platform_format"), dict)
            else {}
        )
        current_export_value = ""
        if isinstance(export_by_platform.get(platform_preset), dict):
            current_export_value = cls._normalize_text(
                export_by_platform.get(platform_preset, {}).get(format_name),
                limit=120,
            )
        if not current_export_value and isinstance(export_by_platform.get("all"), dict):
            current_export_value = cls._normalize_text(
                export_by_platform.get("all", {}).get(format_name),
                limit=120,
            )

        format_rules = cls._prompt_intelligence_lines(
            [
                current_expectations.get("structure"),
                current_expectations.get("include"),
                current_expectations.get("style"),
                current_expectations.get("quality_priorities"),
                legacy_rules.get(format_name),
            ],
            limit=8,
        )
        platform_rules = cls._prompt_intelligence_lines(
            [
                current_platform_guidance.get("notes"),
                legacy_rules.get(platform_preset),
            ],
            limit=6,
        )
        quality_priorities = cls._prompt_intelligence_lines(
            [
                current_expectations.get("quality_priorities"),
                guide.get("key_insights"),
            ],
            limit=6,
        )
        structural_expectations = cls._prompt_intelligence_lines(
            [
                current_expectations.get("structure"),
                current_expectations.get("include"),
                legacy_rules.get(format_name),
            ],
            limit=8,
        )
        export_rules = cls._prompt_intelligence_lines(
            [
                [f"{platform_preset.title()} {format_name}: {current_export_value}"] if current_export_value else [],
                export_guidance.get("lines"),
                guide.get("key_insights"),
            ],
            limit=6,
        )
        definition = cls._normalize_text(definitions.get(format_name), limit=320)
        summary = cls._compose_summary(
            [
                definition,
                cls._normalize_text(current_platform_guidance.get("summary"), limit=240),
                cls._normalize_text(guide.get("summary"), limit=320),
                *quality_priorities[:2],
            ],
            item_limit=140,
            summary_limit=320,
            max_items=4,
        )
        preferred_slide_count = current_expectations.get("preferred_slide_count")
        if not any([definition, format_rules, platform_rules, export_rules, quality_priorities, structural_expectations, summary]):
            return {}
        return {
            "source_path": cls._normalize_text(guide.get("source_path"), limit=180),
            "platform_preset": platform_preset,
            "format": format_name,
            "summary": summary,
            "format_definition": definition,
            "format_rules": format_rules,
            "platform_rules": platform_rules,
            "structural_expectations": structural_expectations,
            "quality_priorities": quality_priorities,
            "export_rules": export_rules,
            "preferred_slide_count": int(preferred_slide_count) if str(preferred_slide_count).isdigit() else None,
            "source_attribution_required": bool(current_expectations.get("source_attribution_required")),
        }

    def compile(
        self,
        *,
        prompt: str,
        brand_context: dict[str, Any],
        persona_context: dict[str, Any],
        objective_context: dict[str, Any],
        ordered_knowledge: dict[str, list[dict[str, Any]]],
        studio_panel: dict[str, Any],
        conversation_context: dict[str, Any] | None = None,
        session_memory: dict[str, Any] | None = None,
        template_context: dict[str, Any] | None = None,
        layout_decision: dict[str, Any] | None = None,
        reference_assets: list[dict[str, Any]] | None = None,
        template_candidates: list[dict[str, Any]] | None = None,
        asset_catalog: list[dict[str, Any]] | None = None,
        content_format_guide: dict[str, Any] | None = None,
        research_editorial_brief: dict[str, Any] | None = None,
        format_family_plan: dict[str, Any] | None = None,
        content_plan: dict[str, Any] | None = None,
        visual_plan: dict[str, Any] | None = None,
        resolution_instructions: str | None = None,
        research_summary: str | None = None,
    ) -> dict[str, Any]:
        audience = brand_context.get("audience_insights", {}) or {}
        decision = layout_decision or {}
        reference_assets = reference_assets or []
        template_candidates = template_candidates or []
        asset_catalog = asset_catalog or reference_assets
        visual_knowledge_brief = self._visual_knowledge_brief(ordered_knowledge)
        brand_visual_brief = self._visual_brief(
            brand_context=brand_context,
            layout_decision=decision,
            template_context=template_context,
            reference_assets=reference_assets,
        )
        template_fit_brief = {
            "mode": self._normalize_text(decision.get("mode"), limit=24),
            "confidence": decision.get("confidence"),
            "selected_template_id": self._normalize_text(decision.get("selected_template_id") or decision.get("template_id"), limit=72),
            "template_name": self._normalize_text(decision.get("template_name"), limit=72),
            "rationale": self._dedupe_items([self._normalize_text(item, 120) for item in decision.get("rationale", []) or []], limit=2),
            "adaptation_plan": decision.get("adaptation_plan", {}) or {},
            "template_zone_roles": self._dedupe_items(
                [
                    self._normalize_text(zone.get("role"), limit=24)
                    for zone in (
                        ((template_context.get("zone_map") or {}).get("zones") if isinstance(template_context, dict) and isinstance(template_context.get("zone_map"), dict) else [])
                        or next(
                            (
                                (slide.get("zone_map") or {}).get("zones", [])
                                for slide in (
                                    (template_context.get("sequence_pack") or {}).get("slides", [])
                                    if isinstance(template_context, dict) and isinstance(template_context.get("sequence_pack"), dict)
                                    else []
                                )
                                if isinstance(slide, dict) and isinstance(slide.get("zone_map"), dict) and (slide.get("zone_map") or {}).get("zones")
                            ),
                            [],
                        )
                        or (template_context.get("zones") if isinstance(template_context, dict) else [])
                        or []
                    )
                    if isinstance(zone, dict) and self._normalize_text(zone.get("role"), limit=24)
                ],
                limit=8,
            ),
            "template_layout_dna": self._compact_layout_dna(
                (
                    ((template_context.get("zone_map") or {}).get("layout_dna") if isinstance(template_context, dict) and isinstance(template_context.get("zone_map"), dict) else {})
                    or next(
                        (
                            (slide.get("zone_map") or {})
                            for slide in (
                                (template_context.get("sequence_pack") or {}).get("slides", [])
                                if isinstance(template_context, dict) and isinstance(template_context.get("sequence_pack"), dict)
                                else []
                            )
                            if isinstance(slide, dict) and isinstance(slide.get("zone_map"), dict) and (slide.get("zone_map") or {}).get("zones")
                        ),
                        {},
                    )
                    or (template_context.get("layout_dna") if isinstance(template_context, dict) else {})
                )
            ),
            "template_composition_logic": self._compact_composition_logic_dna(
                (
                    ((template_context.get("zone_map") or {}).get("composition_logic") if isinstance(template_context, dict) and isinstance(template_context.get("zone_map"), dict) else {})
                    or next(
                        (
                            (slide.get("zone_map") or {}).get("composition_logic", {})
                            for slide in (
                                (template_context.get("sequence_pack") or {}).get("slides", [])
                                if isinstance(template_context, dict) and isinstance(template_context.get("sequence_pack"), dict)
                                else []
                            )
                            if isinstance(slide, dict) and isinstance(slide.get("zone_map"), dict) and (slide.get("zone_map") or {}).get("composition_logic")
                        ),
                        {},
                    )
                    or (template_context.get("composition_logic") if isinstance(template_context, dict) else {})
                )
            ),
            "template_visual_craft": self._compact_visual_craft_dna(
                (
                    ((template_context.get("zone_map") or {}).get("visual_craft_dna") if isinstance(template_context, dict) and isinstance(template_context.get("zone_map"), dict) else {})
                    or next(
                        (
                            (slide.get("zone_map") or {}).get("visual_craft_dna", {})
                            for slide in (
                                (template_context.get("sequence_pack") or {}).get("slides", [])
                                if isinstance(template_context, dict) and isinstance(template_context.get("sequence_pack"), dict)
                                else []
                            )
                            if isinstance(slide, dict) and isinstance(slide.get("zone_map"), dict) and (slide.get("zone_map") or {}).get("visual_craft_dna")
                        ),
                        {},
                    )
                    or (template_context.get("visual_craft_dna") if isinstance(template_context, dict) else {})
                )
            ),
            "template_subject_semantics": self._compact_subject_semantics_dna(
                (
                    ((template_context.get("zone_map") or {}).get("subject_semantics") if isinstance(template_context, dict) and isinstance(template_context.get("zone_map"), dict) else {})
                    or next(
                        (
                            (slide.get("zone_map") or {}).get("subject_semantics", {})
                            for slide in (
                                (template_context.get("sequence_pack") or {}).get("slides", [])
                                if isinstance(template_context, dict) and isinstance(template_context.get("sequence_pack"), dict)
                                else []
                            )
                            if isinstance(slide, dict) and isinstance(slide.get("zone_map"), dict) and (slide.get("zone_map") or {}).get("subject_semantics")
                        ),
                        {},
                    )
                    or (template_context.get("subject_semantics") if isinstance(template_context, dict) else {})
                )
            ),
            "template_editorial_dna": self._compact_editorial_dna(
                (
                    ((template_context.get("zone_map") or {}).get("editorial_dna") if isinstance(template_context, dict) and isinstance(template_context.get("zone_map"), dict) else {})
                    or next(
                        (
                            (slide.get("zone_map") or {}).get("editorial_dna", {})
                            for slide in (
                                (template_context.get("sequence_pack") or {}).get("slides", [])
                                if isinstance(template_context, dict) and isinstance(template_context.get("sequence_pack"), dict)
                                else []
                            )
                            if isinstance(slide, dict) and isinstance(slide.get("zone_map"), dict) and (slide.get("zone_map") or {}).get("editorial_dna")
                        ),
                        {},
                    )
                    or (template_context.get("editorial_dna") if isinstance(template_context, dict) else {})
                )
            ),
            "sequence_pack": self._compact_sequence_pack(
                template_context.get("sequence_pack") if isinstance(template_context, dict) else {}
            ),
            "template_candidates": [
                {
                    "template_id": self._normalize_text(item.get("template_id"), limit=72),
                    "name": self._normalize_text(item.get("name"), limit=72),
                    "display_name": self._normalize_text(item.get("display_name"), limit=72),
                    "score": item.get("score"),
                    "match_type": self._normalize_text(item.get("match_type"), limit=32),
                    "format_family": self._normalize_text(item.get("format_family"), limit=24),
                    "is_primary_adaptation": bool(item.get("is_primary_adaptation")),
                    "selection_reason": self._normalize_text(item.get("selection_reason"), limit=40),
                    "recommendation_group_key": self._normalize_text(item.get("recommendation_group_key"), limit=64),
                    "editability_score": item.get("editability_score"),
                    "reinterpretation_suitability": item.get("reinterpretation_suitability"),
                    "style_only_suitability": item.get("style_only_suitability"),
                }
                for item in template_candidates[:6]
                if isinstance(item, dict)
            ],
        }
        content_format_brief = self._content_format_brief(
            content_format_guide,
            studio_panel,
        )
        reference_family_profile = self._reference_family_profile(
            brand_visual_brief=brand_visual_brief,
            template_fit_brief=template_fit_brief,
            content_format_brief=content_format_brief,
        )
        return {
            "brand_copy_brief": self._copy_brief(
                brand_context=brand_context,
                persona_context=persona_context,
                objective_context=objective_context,
                session_memory=session_memory or {},
            ),
            "brand_visual_brief": brand_visual_brief,
            "objective_brief": self._objective_brief(objective_context),
            "audience_brief": self._audience_brief(audience, persona_context),
            "prompt_intelligence_brief": self._prompt_intelligence_brief(
                brand_context.get("prompt_intelligence", {}) or {},
                studio_panel,
            ),
            "content_format_brief": content_format_brief,
            "research_editorial_brief": self._research_editorial_brief(research_editorial_brief),
            "format_family_plan": self._format_family_plan(format_family_plan),
            "content_plan": self._content_plan(content_plan),
            "visual_plan": self._visual_plan(visual_plan),
            "knowledge_brief": self._knowledge_brief(ordered_knowledge),
            "visual_knowledge_brief": visual_knowledge_brief,
            "visual_grounding_diagnostics": self._visual_grounding_diagnostics(visual_knowledge_brief),
            "render_constraints": self._render_constraints(prompt, studio_panel, decision),
            "session_brief": self._session_brief(session_memory or {}, conversation_context or {}),
            "template_fit_brief": template_fit_brief,
            "reference_family_profile": reference_family_profile,
            "reference_asset_brief": [
                self._reference_asset_brief_item(asset)
                for asset in reference_assets[:6]
                if isinstance(asset, dict)
            ],
            "asset_catalog": [
                {
                    "asset_id": self._normalize_text(asset.get("asset_id"), limit=72),
                    "role": self._normalize_text(asset.get("asset_role"), limit=32),
                    "trust_level": self._normalize_text(asset.get("trust_level"), limit=24),
                    "label": self._normalize_text((asset.get("metadata") or {}).get("label"), limit=64),
                    "storage_path": self._normalize_text(asset.get("storage_path"), limit=180),
                }
                for asset in asset_catalog[:12]
                if isinstance(asset, dict)
            ],
            "platform_constraints": {
                "platform_preset": self._normalize_text(studio_panel.get("platform_preset"), limit=32),
                "format": self._normalize_text(studio_panel.get("format"), limit=32),
                "file_type": self._normalize_text(studio_panel.get("file_type"), limit=16),
                "size": studio_panel.get("size", {}) or {},
            },
            "resolution_instructions": self._normalize_text(resolution_instructions, limit=240),
            "research_summary": self._normalize_text(research_summary, limit=640),
        }
