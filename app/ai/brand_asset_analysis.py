from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any
from typing import Callable

import cv2
import numpy as np
from PIL import Image, ImageFont

from app.ai.rag.ocr import OCRService
from app.ai.template_vision import TemplateVisionAnalyzer
from app.core.enums import BrandAssetCategory, BrandAssetField
from app.utils.image_assets import open_image_asset


COMMON_COLOR_NAMES = {
    "black",
    "white",
    "gray",
    "grey",
    "silver",
    "red",
    "orange",
    "yellow",
    "green",
    "blue",
    "navy",
    "teal",
    "purple",
    "violet",
    "pink",
    "brown",
    "gold",
    "beige",
}

COMMON_FONT_FAMILIES = (
    "DM Sans",
    "Manrope",
    "Inter",
    "Montserrat",
    "Poppins",
    "Open Sans",
    "Roboto",
    "Lato",
    "Nunito",
    "Playfair Display",
    "Merriweather",
    "Helvetica",
    "Arial",
    "Georgia",
    "Futura",
    "Gotham",
    "Avenir",
    "Proxima Nova",
    "Calibri",
)

PROMOTIONAL_COPY_TOKENS = {
    "apply now",
    "book now",
    "buy now",
    "call now",
    "click here",
    "contact us",
    "download now",
    "learn more",
    "limited time",
    "offer ends",
    "register now",
    "save now",
    "scan qr",
    "shop now",
    "sign up",
    "subscribe",
    "swipe up",
    "terms apply",
}

LEGAL_COPY_TOKENS = {
    "all rights reserved",
    "copyright",
    "disclaimer",
    "privacy policy",
    "regulated by",
    "subject to",
    "terms and conditions",
    "trademark",
}

VISUAL_SYSTEM_TOKENS = {
    "background",
    "badge",
    "brandmark",
    "color",
    "composition",
    "cta",
    "editorial",
    "font",
    "gradient",
    "grid",
    "header",
    "headline",
    "icon",
    "illustration",
    "layout",
    "logo",
    "mark",
    "motif",
    "palette",
    "pattern",
    "shape",
    "spacing",
    "style",
    "symbol",
    "texture",
    "typography",
    "visual",
    "zone",
}

AUDIENCE_EVIDENCE_FIELD_SPECS: dict[str, dict[str, Any]] = {
    "segments": {
        "aliases": (
            "audience",
            "audience segment",
            "audience segments",
            "persona",
            "personas",
            "segment",
            "segments",
            "target audience",
            "who this is for",
        ),
        "keywords": ("audience", "segment", "persona", "target audience"),
        "min_confidence": 0.62,
        "max_items": 6,
    },
    "behaviors": {
        "aliases": ("behavior", "behaviors", "behaviour", "behaviours", "content behavior", "usage"),
        "keywords": ("behavior", "behaviour", "habit", "usage", "uses", "reads", "compares", "researches"),
        "min_confidence": 0.62,
        "max_items": 6,
    },
    "motivations": {
        "aliases": ("motivation", "motivations", "need", "needs", "aspiration", "aspirations", "goal", "goals"),
        "keywords": ("motivation", "need", "needs", "goal", "goals", "wants", "seeks", "cares about"),
        "min_confidence": 0.62,
        "max_items": 6,
    },
    "pain_points": {
        "aliases": ("pain point", "pain points", "challenge", "challenges", "friction", "barrier", "barriers"),
        "keywords": ("pain", "pain point", "challenge", "friction", "barrier", "problem", "struggle"),
        "min_confidence": 0.62,
        "max_items": 6,
    },
    "objections": {
        "aliases": ("objection", "objections", "hesitation", "hesitations", "concern", "concerns", "worry", "worries"),
        "keywords": ("objection", "hesitation", "concern", "worry", "doubt", "skeptical", "skepticism", "pushback", "risk"),
        "min_confidence": 0.64,
        "max_items": 6,
    },
    "desired_outcomes": {
        "aliases": ("desired outcome", "desired outcomes", "outcome", "outcomes", "result", "results", "success", "benefit", "benefits"),
        "keywords": ("desired outcome", "outcome", "result", "success", "benefit", "priority", "win"),
        "min_confidence": 0.62,
        "max_items": 6,
    },
    "preferences": {
        "aliases": ("preference", "preferences", "channel preference", "content preference"),
        "keywords": ("prefer", "preference", "likes", "channel", "format", "tone"),
        "min_confidence": 0.62,
        "max_items": 6,
    },
    "trust_signals": {
        "aliases": ("trust signal", "trust signals", "credibility", "credibility cues", "reassurance"),
        "keywords": ("trust", "credibility", "reassurance", "transparent", "regulated", "secure", "compliance", "compliant", "verified", "testimonial", "case study", "review"),
        "min_confidence": 0.66,
        "max_items": 5,
    },
    "proof_cues": {
        "aliases": ("proof cue", "proof cues", "evidence", "data points", "proof"),
        "keywords": ("proof", "evidence", "benchmark", "metric", "measured", "performance", "track record", "stat", "data point"),
        "min_confidence": 0.66,
        "max_items": 5,
    },
    "comparison_points": {
        "aliases": ("comparison", "comparisons", "comparison point", "comparison points", "alternatives", "trade-offs"),
        "keywords": ("compare", "comparison", "versus", "vs", "instead of", "alternative", "trade-off", "difference", "deposits", "fds", "fixed-income option", "fixed income option"),
        "min_confidence": 0.66,
        "max_items": 5,
    },
}

AUDIENCE_DISALLOWED_CLASSIFICATIONS = {"cta_copy", "legal", "noise", "specimen", "template_copy"}
AUDIENCE_STATEMENT_VERBS = {
    "avoid",
    "avoids",
    "build",
    "builds",
    "care",
    "cares",
    "choose",
    "chooses",
    "compare",
    "compares",
    "explain",
    "explains",
    "fear",
    "fears",
    "hesitate",
    "hesitates",
    "need",
    "needs",
    "prefer",
    "prefers",
    "research",
    "researches",
    "seek",
    "seeks",
    "trust",
    "trusts",
    "use",
    "uses",
    "value",
    "values",
    "want",
    "wants",
    "worry",
    "worries",
}

SIGNAL_TYPE_KEYWORDS = {
    "background": {"background", "surface", "negative space", "texture"},
    "icons": {"badge", "brandmark", "icon", "illustration", "logo", "mark", "symbol"},
    "layout": {"alignment", "composition", "editorial", "grid", "hero", "layout", "split"},
    "motifs": {"curve", "graphic", "motif", "pattern", "shape", "style", "texture", "visual"},
    "palette": {"accent", "background", "color", "palette", "primary", "secondary"},
    "typography": {"font", "headline", "typeface", "typography"},
    "zones": {"body", "caption", "card", "cta", "footer", "header", "headline", "section", "zone"},
}

SINGLE_LETTER_RUN_PATTERN = re.compile(r"\b(?:[A-Za-z]\s+){6,}[A-Za-z]\b")
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


@dataclass(slots=True)
class AssetProcessingOutcome:
    routed_category: str
    channel: str
    extracted_text: str
    page_count: int
    structured_data: dict[str, Any] = field(default_factory=dict)
    normalized_data: dict[str, Any] = field(default_factory=dict)
    routing: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    confidence: float | None = None
    validation_state: str = "pending"
    template_analysis: dict[str, Any] | None = None
    template_tags: list[str] = field(default_factory=list)
    image_candidates: list[str] = field(default_factory=list)
    derived_assets: list[dict[str, Any]] = field(default_factory=list)
    source_format: str | None = None


class BrandAssetAnalyzer:
    def __init__(self) -> None:
        self.ocr = OCRService()
        self.vision = TemplateVisionAnalyzer()

    def analyze(
        self,
        absolute_path: str,
        filename: str,
        mime_type: str,
        requested_field_key: str,
        desired_category: str | None = None,
        metadata: dict[str, Any] | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> AssetProcessingOutcome:
        extracted = self.ocr.extract(absolute_path, progress_callback=progress_callback)
        text = (extracted.get("text") or "").strip()
        images = [str(image) for image in (extracted.get("images") or []) if str(image).strip()]
        page_count = int(extracted.get("page_count") or 0)
        source_format = str(extracted.get("source_format") or Path(filename).suffix.lower().lstrip("."))
        extraction_warnings = [
            str(warning)
            for warning in (extracted.get("warnings") or [])
            if str(warning).strip()
        ]
        analysis_paths = [
            str(path)
            for path in (extracted.get("analysis_paths") or ([extracted.get("analysis_path")] if extracted.get("analysis_path") else []))
            if str(path).strip()
        ]

        routed_category, routing = self._route_category(
            text=text,
            filename=filename,
            mime_type=mime_type,
            requested_field_key=requested_field_key,
            desired_category=desired_category,
        )

        if not images and source_format == "pdf" and routed_category in {
            BrandAssetCategory.LOGO,
            BrandAssetCategory.REFERENCE_CREATIVE,
            BrandAssetCategory.TEMPLATE,
            BrandAssetCategory.MOOD_BOARD,
            BrandAssetCategory.KNOWLEDGE_OTHER,
        }:
            images = self.ocr.extract_visual_candidates(absolute_path)

        structured: dict[str, Any]
        normalized: dict[str, Any]
        template_analysis: dict[str, Any] | None = None

        if routed_category == BrandAssetCategory.LOGO:
            structured, normalized = self._extract_logo_data(text, absolute_path, images)
            channel = "metadata"
        elif routed_category == BrandAssetCategory.AUDIENCE_INSIGHT:
            structured, normalized = self._extract_audience_insights(text)
            channel = "audience_insights"
        elif routed_category in {
            BrandAssetCategory.REFERENCE_CREATIVE,
            BrandAssetCategory.TEMPLATE,
            BrandAssetCategory.USER_UPLOAD_FOR_GENERATION,  # 🔥 PHASE 3: Apply deep vision to user uploads
        }:
            structured, normalized, template_analysis = self._extract_template_intelligence(
                text=text,
                absolute_path=absolute_path,
                images=images,
                category=routed_category,
                analysis_paths=analysis_paths,
            )
            if routed_category == BrandAssetCategory.TEMPLATE:
                channel = "template"
            elif routed_category == BrandAssetCategory.USER_UPLOAD_FOR_GENERATION:
                channel = "user_upload"
            else:
                channel = "reference_creative"
        elif routed_category == BrandAssetCategory.MOOD_BOARD:
            structured, normalized = self._extract_mood_board(text, absolute_path, images)
            channel = "mood_board"
        elif routed_category == BrandAssetCategory.COLOR_PALETTE:
            structured, normalized = self._extract_palette(text, absolute_path, images)
            channel = "visual_identity"
        elif routed_category == BrandAssetCategory.TYPOGRAPHY_GUIDE:
            structured, normalized = self._extract_typography(
                text,
                absolute_path=absolute_path,
                source_format=source_format,
            )
            channel = "visual_identity"
        elif routed_category in {
            BrandAssetCategory.POSITIVE_WORD_BANK,
            BrandAssetCategory.NEGATIVE_WORD_BANK,
            BrandAssetCategory.REPLACEABLE_WORD_BANK,
        }:
            structured, normalized = self._extract_word_bank(text, routed_category)
            channel = "guardrail_support"
        else:
            structured, normalized = self._extract_other(text, absolute_path, images)
            channel = "brand"

        warnings = [*list(structured.get("warnings", [])), *extraction_warnings]
        validation_state = "warning" if warnings else "clean"
        if not text and not normalized:
            warnings.append("Low-confidence extraction. No strong structured signal was detected.")
            validation_state = "warning"

        derived_assets = self._derive_reusable_assets(
            absolute_path=absolute_path,
            routed_category=routed_category,
            structured_data=structured,
            normalized_data=normalized,
            template_analysis=template_analysis,
            image_candidates=images,
        )

        return AssetProcessingOutcome(
            routed_category=routed_category,
            channel=channel,
            extracted_text=text,
            page_count=page_count,
            structured_data=structured,
            normalized_data=normalized,
            routing=routing,
            warnings=warnings,
            confidence=routing.get("confidence"),
            validation_state=validation_state,
            template_analysis=template_analysis,
            template_tags=(template_analysis or {}).get("tags", []),
            image_candidates=images,
            derived_assets=derived_assets,
            source_format=source_format,
        )

    def _route_category(
        self,
        text: str,
        filename: str,
        mime_type: str,
        requested_field_key: str,
        desired_category: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if desired_category:
            return desired_category, {
                "requested_field_key": requested_field_key,
                "requested_category": desired_category,
                "routed_category": desired_category,
                "classifier": "explicit_override",
                "confidence": 1.0,
                "routing_reason": "Frontend explicitly selected the asset category.",
            }

        field_map = {
            BrandAssetField.LOGO: BrandAssetCategory.LOGO,
            BrandAssetField.AUDIENCE_INSIGHTS: BrandAssetCategory.AUDIENCE_INSIGHT,
            BrandAssetField.REFERENCE_CREATIVES: BrandAssetCategory.REFERENCE_CREATIVE,
            BrandAssetField.MOOD_BOARD: BrandAssetCategory.MOOD_BOARD,
            BrandAssetField.COLOR_PALETTE: BrandAssetCategory.COLOR_PALETTE,
            BrandAssetField.FONT_GUIDE: BrandAssetCategory.TYPOGRAPHY_GUIDE,
            BrandAssetField.POSITIVE_WORD_BANK: BrandAssetCategory.POSITIVE_WORD_BANK,
            BrandAssetField.NEGATIVE_WORD_BANK: BrandAssetCategory.NEGATIVE_WORD_BANK,
            BrandAssetField.REPLACEABLE_WORD_BANK: BrandAssetCategory.REPLACEABLE_WORD_BANK,
            BrandAssetField.BRAND_KNOWLEDGE_TEMPLATES: BrandAssetCategory.TEMPLATE,
        }
        if requested_field_key in field_map:
            category = field_map[requested_field_key]
            return category, {
                "requested_field_key": requested_field_key,
                "requested_category": category,
                "routed_category": category,
                "classifier": "field_map",
                "confidence": 0.98,
                "routing_reason": f"Field intent '{requested_field_key}' maps directly to '{category}'.",
            }

        lowered = f"{filename}\n{text}".lower()
        heuristics: list[tuple[str, list[str]]] = [
            (BrandAssetCategory.COLOR_PALETTE, ["#", "palette", "primary color", "secondary color", "accent"]),
            (BrandAssetCategory.TYPOGRAPHY_GUIDE, ["font", "typeface", "typography", "heading", "caption"]),
            (BrandAssetCategory.AUDIENCE_INSIGHT, ["audience", "segment", "motivation", "pain point", "behavior"]),
            (BrandAssetCategory.LOGO, ["logo", "brandmark", "clear space", "safe zone", "tagline"]),
            (BrandAssetCategory.TEMPLATE, ["template", "layout", "header", "footer", "cta", "hero"]),
            (BrandAssetCategory.MOOD_BOARD, ["mood board", "pattern", "icon", "decorative", "texture"]),
            (BrandAssetCategory.POSITIVE_WORD_BANK, ["positive word", "approved words", "preferred language"]),
            (BrandAssetCategory.NEGATIVE_WORD_BANK, ["negative word", "avoid saying", "blocked word"]),
            (BrandAssetCategory.REPLACEABLE_WORD_BANK, ["replace", "instead of", "say this"]),
        ]
        scores: dict[str, int] = {}
        for category, signals in heuristics:
            scores[category] = sum(1 for signal in signals if signal in lowered)
        best_category, best_score = max(scores.items(), key=lambda item: item[1], default=(BrandAssetCategory.KNOWLEDGE_OTHER, 0))
        if best_score <= 0:
            best_category = BrandAssetCategory.KNOWLEDGE_OTHER
        confidence = round(min(0.9, 0.45 + (best_score * 0.1)), 2) if best_score else 0.42
        return best_category, {
            "requested_field_key": requested_field_key,
            "requested_category": None,
            "routed_category": best_category,
            "classifier": "heuristic_router",
            "confidence": confidence,
            "routing_reason": f"Detected {best_score} matching classification signals for '{best_category}'.",
            "decision_json": {"scores": scores, "filename": filename, "mime_type": mime_type},
        }

    def _extract_logo_data(
        self,
        text: str,
        absolute_path: str,
        images: list[str],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        candidates = images or [absolute_path]
        palette = self._dominant_palette(candidates[0]) if candidates else []
        colors = self._extract_palette_from_text(text)
        color_entries = colors or palette
        tagline = self._guess_tagline(text)
        font_families = self._extract_fonts(text)
        compatibility = []
        lowered = text.lower()
        if "dark background" in lowered or "dark bg" in lowered:
            compatibility.append("dark")
        if "light background" in lowered or "light bg" in lowered or "white background" in lowered:
            compatibility.append("light")
        if not compatibility:
            compatibility = ["light", "dark"]
        size_rules = {
            "minimum_size": self._search_value(text, r"(?:minimum|min)\s+(?:logo\s+)?size[:\s]+([^\n]+)"),
            "clear_space": self._search_value(text, r"(?:clear\s+space|safe\s+zone)[:\s]+([^\n]+)"),
        }
        structured = {
            "logo_colors": color_entries,
            "size_rules": {key: value for key, value in size_rules.items() if value},
            "font_details": {"families": font_families},
            "tagline": tagline,
            "compatibility": compatibility,
            "warnings": [] if color_entries else ["No explicit logo palette detected; using low-confidence defaults."],
        }
        size_rule_terms = [
            f"{key.replace('_', ' ')} {value}"
            for key, value in structured["size_rules"].items()
        ]
        classified_lines = self._classified_text_lines(text)
        source_agreement = self._source_agreement(
            classified_lines,
            available_signal_types={
                signal_type
                for signal_type, enabled in {
                    "palette": bool(color_entries),
                    "typography": bool(font_families),
                    "background": bool(compatibility),
                }.items()
                if enabled
            },
        )
        logo_summary = self._summary_from_parts(
            [
                f"Logo palette: {', '.join(self._palette_summary_terms(color_entries, limit=4))}" if color_entries else "",
                f"Typography: {', '.join(self._font_summary_terms(font_families, limit=3))}" if font_families else "",
                f"Tagline: {tagline}" if tagline else "",
                f"Usage backgrounds: {', '.join(compatibility)}" if compatibility else "",
                f"Rules: {', '.join(size_rule_terms)}" if size_rule_terms else "",
            ],
            limit=320,
        )
        quality = self._analysis_quality(
            text=text,
            summary=logo_summary,
            salient_lines=self._salient_text_lines(
                text,
                keywords=["logo", "brandmark", "wordmark", "tagline", "clear space", "safe zone", "background"],
                limit=4,
                allowed_classifications={"visual_system", "unknown"},
            ),
            palette_count=len(color_entries),
            font_count=len(font_families),
            evidence_types=["logo", "palette", "typography", "usage_rules"],
            classified_lines=classified_lines,
            source_agreement=source_agreement,
        )
        structured["summary"] = logo_summary
        structured["visual_evidence_units"] = [
            unit
            for unit in [
                {
                    "kind": "palette",
                    "summary": f"Logo palette: {', '.join(self._palette_summary_terms(color_entries, limit=4))}",
                    "source": "hybrid",
                }
                if color_entries
                else None,
                {
                    "kind": "typography",
                    "summary": f"Typography: {', '.join(self._font_summary_terms(font_families, limit=3))}",
                    "source": "ocr",
                }
                if font_families
                else None,
                {
                    "kind": "background",
                    "summary": f"Usage backgrounds: {', '.join(compatibility)}",
                    "source": "ocr",
                }
                if compatibility
                else None,
            ]
            if isinstance(unit, dict)
        ]
        structured["classified_text_lines"] = classified_lines
        structured["analysis_quality"] = quality
        normalized = {
            "variants": [
                self._logo_variant_payload(
                    candidate_path=str(candidate),
                    text=text,
                    compatibility=compatibility,
                )
                for candidate in candidates
            ],
            "logo_colors": color_entries,
            "tagline": tagline,
            "font_family": font_families[0]["name"] if font_families else None,
            "size_rules": structured["size_rules"],
            "summary": logo_summary,
            "visual_evidence_units": structured["visual_evidence_units"],
            "classified_text_lines": classified_lines,
            "analysis_quality": quality,
            "usage_metadata": {
                "compatible_backgrounds": compatibility,
                "source_asset_count": len(candidates),
            },
        }
        return structured, normalized

    @staticmethod
    def _logo_candidate_dimensions(candidate_path: str) -> tuple[int, int]:
        try:
            with open_image_asset(candidate_path) as image:
                return image.size
        except Exception:  # noqa: BLE001
            return 0, 0

    @classmethod
    def _logo_variant_payload(
        cls,
        *,
        candidate_path: str,
        text: str,
        compatibility: list[str],
    ) -> dict[str, Any]:
        filename = Path(candidate_path).name
        lowered = f"{filename} {text}".casefold()
        width, height = cls._logo_candidate_dimensions(candidate_path)
        orientation = "flex"
        if width and height:
            aspect_ratio = width / max(height, 1)
            if aspect_ratio >= 1.45:
                orientation = "horizontal"
            elif aspect_ratio <= 0.8:
                orientation = "stacked"
            elif min(width, height) >= 1 and abs(width - height) / max(width, height) <= 0.15:
                orientation = "icon"
        if any(token in lowered for token in ("stacked", "vertical", "portrait", "badge", "seal")):
            orientation = "stacked"
        elif any(token in lowered for token in ("horizontal", "wide", "landscape", "lockup", "wordmark")):
            orientation = "horizontal"
        elif any(token in lowered for token in ("icon", "mark", "monogram", "symbol", "emblem")):
            orientation = "icon"

        background_variant = None
        if any(token in lowered for token in ("dark background", "dark bg")):
            background_variant = "dark"
        elif any(token in lowered for token in ("light background", "light bg", "white background")):
            background_variant = "light"
        elif any(token in lowered for token in ("reverse", "inverse", "negative", "white")):
            background_variant = "dark"
        elif any(token in lowered for token in ("dark", "black", "navy", "blue", "colour", "color")):
            background_variant = "light"

        variant_tags: list[str] = []
        if background_variant == "dark":
            variant_tags.append("light_on_dark")
        elif background_variant == "light":
            variant_tags.append("dark_on_light")
        if orientation == "horizontal":
            variant_tags.extend(["horizontal", "wordmark"])
        elif orientation == "stacked":
            variant_tags.append("stacked")
        elif orientation == "icon":
            variant_tags.append("icon_only")

        return {
            "storage_hint": filename,
            "compatibility": compatibility,
            "orientation": orientation,
            "background_variant": background_variant,
            "variant_tags": variant_tags,
            "dimensions": {"width": width, "height": height},
        }

    def _extract_audience_insights(self, text: str) -> tuple[dict[str, Any], dict[str, Any]]:
        lines = self._interesting_lines(text)
        audience_entries = self._audience_line_entries(text)
        research_evidence = {
            field: self._extract_audience_evidence(audience_entries, field)
            for field in AUDIENCE_EVIDENCE_FIELD_SPECS
        }
        segments = [item["value"] for item in research_evidence["segments"]]
        behaviors = [item["value"] for item in research_evidence["behaviors"]]
        motivations = [item["value"] for item in research_evidence["motivations"]]
        pain_points = [item["value"] for item in research_evidence["pain_points"]]
        objections = [item["value"] for item in research_evidence["objections"]]
        desired_outcomes = [item["value"] for item in research_evidence["desired_outcomes"]]
        preferences = [item["value"] for item in research_evidence["preferences"]]
        trust_signals = [item["value"] for item in research_evidence["trust_signals"]]
        proof_cues = [item["value"] for item in research_evidence["proof_cues"]]
        comparison_points = [item["value"] for item in research_evidence["comparison_points"]]
        demographics = self._extract_key_value_pairs(lines, ["age", "income", "region", "gender", "occupation"])
        psychographics = self._extract_key_value_pairs(lines, ["attitude", "value", "belief", "lifestyle"])
        evidence_snippets = self._dedupe_preserving_order(
            [
                item["source_snippet"]
                for field in ("segments", "motivations", "pain_points", "objections", "desired_outcomes", "trust_signals", "proof_cues", "comparison_points")
                for item in research_evidence[field][:2]
            ]
        )
        salient_lines = evidence_snippets[:5] or self._salient_text_lines(
            text,
            keywords=[
                "audience",
                "behavior",
                "channel",
                "challenge",
                "comparison",
                "friction",
                "goal",
                "motivation",
                "need",
                "objection",
                "pain",
                "persona",
                "preference",
                "proof",
                "segment",
                "trust",
            ],
            limit=5,
        )
        research_signal_count = sum(len(items) for items in research_evidence.values())
        summary = self._summary_from_parts(
            [
                f"Segments: {', '.join(segments[:3])}" if segments else "",
                f"Motivations: {', '.join(motivations[:3])}" if motivations else "",
                f"Pain points: {', '.join(pain_points[:3])}" if pain_points else "",
                f"Objections: {', '.join(objections[:3])}" if objections else "",
                f"Desired outcomes: {', '.join(desired_outcomes[:3])}" if desired_outcomes else "",
                f"Preferences: {', '.join(preferences[:3])}" if preferences else "",
                f"Trust signals: {', '.join(trust_signals[:2])}" if trust_signals else "",
                f"Proof cues: {', '.join(proof_cues[:2])}" if proof_cues else "",
                f"Comparison points: {', '.join(comparison_points[:2])}" if comparison_points else "",
                *salient_lines[:2],
            ],
            limit=320,
        )
        quality = self._analysis_quality(
            text=text,
            summary=summary,
            salient_lines=salient_lines,
            evidence_types=[
                "audience",
                "behaviors",
                "motivations",
                "pain_points",
                "objections",
                "desired_outcomes",
                "preferences",
                "trust_signals",
                "proof_cues",
                "comparison_points",
            ],
        )
        structured = {
            "audience_segments": [{"label": item} for item in segments],
            "behaviors": behaviors,
            "motivations": motivations,
            "pain_points": pain_points,
            "objections": objections,
            "desired_outcomes": desired_outcomes,
            "preferences": preferences,
            "trust_signals": trust_signals,
            "proof_cues": proof_cues,
            "comparison_points": comparison_points,
            "demographics": demographics,
            "psychographics": psychographics,
            "research_summary": summary,
            "research_evidence": research_evidence,
            "research_signal_count": research_signal_count,
            "analysis_quality": quality,
        }
        normalized = {
            "segments": segments,
            "behaviors": behaviors,
            "motivations": motivations,
            "pain_points": pain_points,
            "objections": objections,
            "desired_outcomes": desired_outcomes,
            "preferences": preferences,
            "trust_signals": trust_signals,
            "proof_cues": proof_cues,
            "comparison_points": comparison_points,
            "demographics": demographics,
            "psychographics": psychographics,
            "research_summary": summary,
            "research_evidence": research_evidence,
            "research_signal_count": research_signal_count,
            "analysis_quality": quality,
        }
        return structured, normalized

    def _load_visual_analysis(self, source_path: str | None, analysis_path: str | None = None) -> dict[str, Any]:
        path = Path(analysis_path) if analysis_path else None
        if path is None:
            if not source_path:
                return {}
            source = Path(source_path)
            if not source.exists():
                return {}
            path = source.with_name(f"{source.stem}_analysis.json")
        if not path.exists():
            return {}
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            parsed = json.loads(raw)
        except Exception:  # noqa: BLE001
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _page_analysis_text(analysis: dict[str, Any] | None) -> str:
        if not isinstance(analysis, dict):
            return ""
        lines: list[str] = []
        for entry in analysis.get("sentences") or []:
            if not isinstance(entry, dict):
                continue
            text = " ".join(str(entry.get("text", "")).split()).strip()
            if text:
                lines.append(text)
        return "\n".join(lines).strip()

    @classmethod
    def _page_density_score(cls, analysis: dict[str, Any] | None) -> float:
        if not isinstance(analysis, dict):
            return 0.0
        page_dimensions = analysis.get("page_dimensions") if isinstance(analysis.get("page_dimensions"), dict) else {}
        image_width = int(page_dimensions.get("image_width_px") or 0)
        image_height = int(page_dimensions.get("image_height_px") or 0)
        page_area = max(image_width * image_height, 1)
        text_area = 0
        sentence_count = 0
        for entry in analysis.get("sentences") or []:
            if not isinstance(entry, dict):
                continue
            sentence_count += 1
            _x, _y, width, height = cls._bbox_dimensions(entry.get("bounding_box"))
            text_area += max(width, 0) * max(height, 0)
        if sentence_count <= 0:
            return 0.0
        coverage = min(text_area / page_area, 1.0)
        return round((sentence_count * 0.08) + (coverage * 5.0), 4)

    @classmethod
    def _page_cta_score(
        cls,
        analysis: dict[str, Any] | None,
        *,
        page_index: int,
        total_pages: int,
    ) -> float:
        text = cls._page_analysis_text(analysis).casefold()
        token_score = sum(1.0 for token in PROMOTIONAL_COPY_TOKENS if token in text)
        footer_bonus = 0.75 if page_index == total_pages else 0.0
        return round(token_score + footer_bonus, 4)

    def _selected_page_records(
        self,
        *,
        absolute_path: str,
        images: list[str],
        analysis_paths: list[str] | None,
    ) -> list[dict[str, Any]]:
        image_candidates = [str(image) for image in images if str(image).strip() and Path(str(image)).exists()]
        if not image_candidates:
            if Path(absolute_path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} and Path(absolute_path).exists():
                image_candidates = [absolute_path]
            else:
                return []

        analysis_lookup: dict[str, str] = {}
        for analysis_path in analysis_paths or []:
            candidate = Path(str(analysis_path))
            if not candidate.exists():
                continue
            stem = candidate.stem
            image_stem = stem[:-9] if stem.endswith("_analysis") else stem
            analysis_lookup[image_stem] = str(candidate)

        records: list[dict[str, Any]] = []
        total_pages = len(image_candidates)
        for index, image_path in enumerate(image_candidates, start=1):
            image_candidate = Path(image_path)
            resolved_analysis_path = analysis_lookup.get(image_candidate.stem)
            analysis = self._load_visual_analysis(image_path, resolved_analysis_path)
            records.append(
                {
                    "page_index": index,
                    "total_pages": total_pages,
                    "image_path": image_path,
                    "analysis_path": resolved_analysis_path,
                    "analysis": analysis,
                    "density_score": self._page_density_score(analysis),
                    "cta_score": self._page_cta_score(analysis, page_index=index, total_pages=total_pages),
                }
            )
        return records

    @staticmethod
    def _dedupe_page_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for record in records:
            key = str(record.get("image_path") or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(record)
        return deduped

    def _select_representative_visual_pages(
        self,
        *,
        absolute_path: str,
        images: list[str],
        analysis_paths: list[str] | None,
    ) -> list[dict[str, Any]]:
        records = self._selected_page_records(
            absolute_path=absolute_path,
            images=images,
            analysis_paths=analysis_paths,
        )
        if len(records) <= 1:
            return records

        selected: list[dict[str, Any]] = [records[0]]
        interior_candidates = records[1:-1]
        if interior_candidates:
            densest = max(interior_candidates, key=lambda item: (float(item.get("density_score") or 0.0), -abs(int(item.get("page_index") or 0) - (len(records) / 2))))
            selected.append(densest)
        ending_candidates = sorted(records, key=lambda item: (float(item.get("cta_score") or 0.0), int(item.get("page_index") or 0)), reverse=True)
        selected.append(ending_candidates[0] if ending_candidates and float(ending_candidates[0].get("cta_score") or 0.0) > 0 else records[-1])
        return self._dedupe_page_records(selected)

    def _merge_text_style_maps(self, analyses: list[dict[str, Any]]) -> list[dict[str, Any]]:
        style_map: list[dict[str, Any]] = []
        seen: set[tuple[str, int, int, int, int]] = set()
        for analysis in analyses:
            for item in self._extract_text_style_map(analysis):
                bbox = item.get("bounding_box", {}) or {}
                key = (
                    str(item.get("text", "")).casefold(),
                    int(bbox.get("x", 0) or 0),
                    int(bbox.get("y", 0) or 0),
                    int(bbox.get("width", 0) or 0),
                    int(bbox.get("height", 0) or 0),
                )
                if key in seen:
                    continue
                seen.add(key)
                style_map.append(item)
        return style_map

    @staticmethod
    def _bbox_dimensions(bbox: dict[str, Any] | None) -> tuple[int, int, int, int]:
        if not isinstance(bbox, dict):
            return 0, 0, 0, 0
        x = int(bbox.get("x", 0) or 0)
        y = int(bbox.get("y", 0) or 0)
        width = int(bbox.get("w", bbox.get("width", 0)) or 0)
        height = int(bbox.get("h", bbox.get("height", 0)) or 0)
        return x, y, width, height

    @classmethod
    def _analysis_text_boxes(cls, analysis: dict[str, Any] | None) -> list[tuple[int, int, int, int]]:
        if not isinstance(analysis, dict):
            return []
        boxes: list[tuple[int, int, int, int]] = []
        for key in ("structured_text", "sentences"):
            entries = analysis.get(key) or []
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                x, y, width, height = cls._bbox_dimensions(entry.get("bounding_box"))
                if width <= 0 or height <= 0:
                    continue
                boxes.append((x, y, width, height))
        return boxes

    @classmethod
    def _is_text_dominated_crop(
        cls,
        crop_box: tuple[int, int, int, int] | None,
        analysis: dict[str, Any] | None,
    ) -> bool:
        if not crop_box:
            return False
        text_boxes = cls._analysis_text_boxes(analysis)
        if not text_boxes:
            return False

        left, top, right, bottom = crop_box
        crop_width = max(right - left, 0)
        crop_height = max(bottom - top, 0)
        crop_area = crop_width * crop_height
        if crop_area <= 0:
            return False

        overlap_area = 0
        max_single_overlap = 0.0
        for x, y, width, height in text_boxes:
            overlap_width = max(0, min(right, x + width) - max(left, x))
            overlap_height = max(0, min(bottom, y + height) - max(top, y))
            intersection = overlap_width * overlap_height
            if intersection <= 0:
                continue
            overlap_area += intersection
            max_single_overlap = max(max_single_overlap, intersection / crop_area)

        overlap_ratio = min(overlap_area / crop_area, 1.0)
        return overlap_ratio >= 0.55 or max_single_overlap >= 0.45

    @classmethod
    def _extract_sidecar_visual_regions(cls, analysis: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not isinstance(analysis, dict):
            return []
        page_dimensions = analysis.get("page_dimensions") or {}
        image_width = int(page_dimensions.get("image_width_px") or 0)
        image_height = int(page_dimensions.get("image_height_px") or 0)
        total_area = max(image_width * image_height, 1)
        candidate_boxes: list[tuple[int, int, int, int]] = []

        for color_entry in analysis.get("dominant_colors") or []:
            if not isinstance(color_entry, dict):
                continue
            for region in color_entry.get("regions") or []:
                if not isinstance(region, dict):
                    continue
                x = int(region.get("x", 0) or 0)
                y = int(region.get("y", 0) or 0)
                width = int(region.get("w", region.get("width", 0)) or 0)
                height = int(region.get("h", region.get("height", 0)) or 0)
                if width < 42 or height < 42:
                    continue
                area_ratio = (width * height) / total_area
                if area_ratio < 0.0025 or area_ratio > 0.09:
                    continue
                candidate_boxes.append((x, y, x + width, y + height))

        if not candidate_boxes:
            return []

        def _boxes_connect(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> bool:
            left_a, top_a, right_a, bottom_a = first
            left_b, top_b, right_b, bottom_b = second
            width_a = max(right_a - left_a, 1)
            height_a = max(bottom_a - top_a, 1)
            width_b = max(right_b - left_b, 1)
            height_b = max(bottom_b - top_b, 1)
            pad_a = max(28, int(min(max(width_a, height_a), 320) * 0.45))
            pad_b = max(28, int(min(max(width_b, height_b), 320) * 0.45))
            return not (
                (right_a + pad_a) < (left_b - pad_b)
                or (right_b + pad_b) < (left_a - pad_a)
                or (bottom_a + pad_a) < (top_b - pad_b)
                or (bottom_b + pad_b) < (top_a - pad_a)
            )

        clustered_boxes: list[tuple[int, int, int, int]] = []
        visited: set[int] = set()
        for index, box in enumerate(candidate_boxes):
            if index in visited:
                continue
            queue = [index]
            visited.add(index)
            cluster = [box]
            while queue:
                current_index = queue.pop()
                current = candidate_boxes[current_index]
                for candidate_index, candidate in enumerate(candidate_boxes):
                    if candidate_index in visited:
                        continue
                    if _boxes_connect(current, candidate):
                        visited.add(candidate_index)
                        queue.append(candidate_index)
                        cluster.append(candidate)
            left = min(item[0] for item in cluster)
            top = min(item[1] for item in cluster)
            right = max(item[2] for item in cluster)
            bottom = max(item[3] for item in cluster)
            width = max(right - left, 1)
            height = max(bottom - top, 1)
            area_ratio = (width * height) / total_area
            if area_ratio <= 0.18:
                clustered_boxes.append((left, top, right, bottom))

        candidate_boxes.extend(clustered_boxes)
        candidate_boxes.sort(
            key=lambda item: (max(item[2] - item[0], 1) * max(item[3] - item[1], 1)),
            reverse=True,
        )

        regions: list[dict[str, Any]] = []
        seen: list[tuple[int, int, int, int]] = []
        for left, top, right, bottom in candidate_boxes:
            crop_box = (left, top, right, bottom)
            width = max(right - left, 1)
            height = max(bottom - top, 1)
            area_ratio = (width * height) / total_area
            if cls._is_text_dominated_crop(crop_box, analysis):
                continue

            duplicate = False
            for existing_left, existing_top, existing_right, existing_bottom in seen:
                overlap_left = max(left, existing_left)
                overlap_top = max(top, existing_top)
                overlap_right = min(right, existing_right)
                overlap_bottom = min(bottom, existing_bottom)
                overlap_width = max(0, overlap_right - overlap_left)
                overlap_height = max(0, overlap_bottom - overlap_top)
                overlap_area = overlap_width * overlap_height
                area = max(width * height, 1)
                existing_area = max((existing_right - existing_left) * (existing_bottom - existing_top), 1)
                if overlap_area / area >= 0.82 or overlap_area / existing_area >= 0.82:
                    duplicate = True
                    break
            if duplicate:
                continue

            seen.append(crop_box)
            regions.append(
                {
                    "crop_box": crop_box,
                    "width": width,
                    "height": height,
                    "area_ratio": area_ratio,
                    "fill_ratio": 0.58,
                    "touches_border": (
                        left <= 6
                        or top <= 6
                        or right >= max(image_width - 6, 1)
                        or bottom >= max(image_height - 6, 1)
                    ),
                }
            )

        regions.sort(key=lambda item: item["area_ratio"], reverse=True)
        return regions[:8]

    @staticmethod
    def _hex_to_rgb(hex_code: str | None) -> tuple[int, int, int] | None:
        value = str(hex_code or "").strip()
        if not re.fullmatch(r"#?[0-9A-Fa-f]{6}", value):
            return None
        if not value.startswith("#"):
            value = f"#{value}"
        return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))

    @classmethod
    def _extract_text_excluded_visual_regions(
        cls,
        source_path: str,
        analysis: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        path = Path(source_path)
        if not path.exists():
            return []
        if not isinstance(analysis, dict):
            return []
        try:
            with open_image_asset(path) as image:
                rgb_image = image.convert("RGB")
                image_width, image_height = rgb_image.size
                rgb = np.array(rgb_image)
        except Exception:  # noqa: BLE001
            return []

        total_area = max(image_width * image_height, 1)
        background_hex = None
        color_categories = analysis.get("color_categories") or {}
        background_entries = color_categories.get("background") if isinstance(color_categories, dict) else None
        if isinstance(background_entries, list) and background_entries:
            background_hex = str((background_entries[0] or {}).get("hex") or "").strip()
        if not background_hex:
            dominant_colors = analysis.get("dominant_colors") or []
            if isinstance(dominant_colors, list) and dominant_colors:
                background_hex = str((dominant_colors[0] or {}).get("hex") or "").strip()
        background_rgb = cls._hex_to_rgb(background_hex) or (245, 245, 245)

        background = np.array(background_rgb, dtype=np.int16)
        color_delta = np.abs(rgb.astype(np.int16) - background).max(axis=2)
        threshold = 26 if max(background_rgb) >= 220 else 34
        mask = np.where(color_delta >= threshold, 255, 0).astype(np.uint8)

        for x, y, width, height in cls._analysis_text_boxes(analysis):
            pad_x = max(14, int(width * 0.08))
            pad_y = max(12, int(height * 0.18))
            left = max(0, x - pad_x)
            top = max(0, y - pad_y)
            right = min(image_width, x + width + pad_x)
            bottom = min(image_height, y + height + pad_y)
            mask[top:bottom, left:right] = 0

        kernel_size = max(5, int(round(min(image_width, image_height) * 0.006)))
        if kernel_size % 2 == 0:
            kernel_size += 1
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.dilate(mask, kernel, iterations=1)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        regions: list[dict[str, Any]] = []
        for contour in contours:
            x, y, width, height = cv2.boundingRect(contour)
            if width < 70 or height < 70:
                continue
            area_ratio = (width * height) / total_area
            if area_ratio < 0.01 or area_ratio > 0.2:
                continue
            if width < 160 and height < 140:
                continue
            crop_box = (x, y, x + width, y + height)
            if cls._is_text_dominated_crop(crop_box, analysis):
                continue
            contour_area = float(cv2.contourArea(contour))
            fill_ratio = contour_area / max(width * height, 1)
            if fill_ratio < 0.04:
                continue
            regions.append(
                {
                    "crop_box": crop_box,
                    "width": width,
                    "height": height,
                    "area_ratio": area_ratio,
                    "fill_ratio": round(fill_ratio, 4),
                    "touches_border": (
                        x <= 6
                        or y <= 6
                        or (x + width) >= max(image_width - 6, 1)
                        or (y + height) >= max(image_height - 6, 1)
                    ),
                }
            )

        regions.sort(key=lambda item: item["area_ratio"], reverse=True)
        return regions[:2]

    @staticmethod
    def _normalize_color_payload(color_payload: Any) -> dict[str, Any] | None:
        if not color_payload:
            return None
        if isinstance(color_payload, list):
            segments = [BrandAssetAnalyzer._normalize_color_payload(item) for item in color_payload]
            return segments[0] if segments and segments[0] else None
        if not isinstance(color_payload, dict):
            return None
        hex_code = str(color_payload.get("hex", color_payload.get("hex_code", "")) or "").strip().upper()
        if not hex_code.startswith("#") and re.fullmatch(r"[0-9A-Fa-f]{6}", hex_code):
            hex_code = f"#{hex_code}"
        if not hex_code:
            return None
        rgb_value = {
            "r": int(color_payload.get("r", 0) or 0),
            "g": int(color_payload.get("g", 0) or 0),
            "b": int(color_payload.get("b", 0) or 0),
        }
        return {
            "hex_code": hex_code,
            "color_name": color_payload.get("color_name"),
            "rgb_value": rgb_value,
        }

    def _estimate_font_size_from_bbox(self, bbox: dict[str, Any] | None) -> int | None:
        _x, _y, _width, height = self._bbox_dimensions(bbox)
        if height <= 0:
            return None
        return max(int(round(height * 0.76)), 8)

    def _extract_text_style_map(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        style_map: list[dict[str, Any]] = []
        seen: set[tuple[str, int, int]] = set()
        sentences = analysis.get("sentences", [])
        for entry in sentences if isinstance(sentences, list) else []:
            if not isinstance(entry, dict):
                continue
            text = " ".join(str(entry.get("text", "")).split()).strip()
            if not text:
                continue
            bbox = entry.get("bounding_box", {}) or {}
            x, y, width, height = self._bbox_dimensions(bbox)
            key = (text.casefold(), x, y)
            if key in seen:
                continue
            seen.add(key)
            text_color = entry.get("text_color")
            background_color = entry.get("background_color")
            style_map.append(
                {
                    "text": text,
                    "bounding_box": {"x": x, "y": y, "width": width, "height": height},
                    "font_color": self._normalize_color_payload(text_color),
                    "font_color_segments": [
                        payload
                        for payload in (
                            self._normalize_color_payload(item)
                            for item in (text_color if isinstance(text_color, list) else [])
                        )
                        if payload
                    ],
                    "background_color": self._normalize_color_payload(background_color),
                    "estimated_font_size": self._estimate_font_size_from_bbox(bbox),
                }
            )
        return style_map

    def _pick_text_style_role(
        self,
        style_map: list[dict[str, Any]],
        *,
        role: str,
        fallback_text: str | None = None,
    ) -> dict[str, Any] | None:
        if not style_map:
            return None
        if fallback_text:
            lookup = fallback_text.casefold().strip()
            for item in style_map:
                if str(item.get("text", "")).casefold().strip() == lookup:
                    return item

        ranked = []
        for item in style_map:
            bbox = item.get("bounding_box", {}) or {}
            _x, y, width, height = self._bbox_dimensions(bbox)
            estimated_size = int(item.get("estimated_font_size") or max(height, 1))
            score = estimated_size * 2
            if role == "heading":
                score += width // 30
                score -= y // 8
            elif role == "header":
                score -= y * 4
                score += 40 if y <= 140 else 0
            elif role == "footer":
                score += y * 4
            ranked.append((score, item))
        if not ranked:
            return None
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return ranked[0][1]

    def _exact_text_palette(self, style_map: list[dict[str, Any]]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in style_map:
            for color_payload in [
                item.get("font_color"),
                *item.get("font_color_segments", []),
            ]:
                if not isinstance(color_payload, dict):
                    continue
                hex_code = str(color_payload.get("hex_code", "")).upper()
                if not hex_code or hex_code in seen:
                    continue
                seen.add(hex_code)
                entries.append(
                    {
                        "role": "text",
                        "hex_code": hex_code,
                        "color_name": color_payload.get("color_name"),
                        "rgb_value": color_payload.get("rgb_value", {}),
                        "source": "vision_text_color",
                    }
                )
        return entries

    def _infer_image_gradient(self, image_path: str | None) -> list[dict[str, Any]]:
        if not image_path:
            return []
        path = Path(image_path)
        if not path.exists():
            return []
        try:
            with open_image_asset(path) as image:
                rgb = np.array(image.convert("RGB").resize((160, 160)))
        except Exception:  # noqa: BLE001
            return []

        def sample_hex(sample: np.ndarray) -> str:
            rgb_value = tuple(int(round(float(channel))) for channel in sample.tolist())
            return self._rgb_to_hex(rgb_value)

        def diff(a: np.ndarray, b: np.ndarray) -> float:
            return float(np.linalg.norm(a.astype(np.float32) - b.astype(np.float32)))

        top = rgb[:24, :, :].mean(axis=(0, 1))
        bottom = rgb[-24:, :, :].mean(axis=(0, 1))
        left = rgb[:, :24, :].mean(axis=(0, 1))
        right = rgb[:, -24:, :].mean(axis=(0, 1))
        center = rgb[56:104, 56:104, :].mean(axis=(0, 1))

        vertical_delta = diff(top, bottom)
        horizontal_delta = diff(left, right)
        strongest_delta = max(vertical_delta, horizontal_delta)
        if strongest_delta < 24:
            return []

        direction = "vertical" if vertical_delta >= horizontal_delta else "horizontal"
        start = top if direction == "vertical" else left
        end = bottom if direction == "vertical" else right
        mid = (start + end) / 2
        radial_bias = diff(center, mid)
        gradient_kind = "radial" if radial_bias > 30 and strongest_delta > 40 else "linear"
        return [
            {
                "type": gradient_kind,
                "direction": direction if gradient_kind == "linear" else "center_out",
                "start_color": sample_hex(start),
                "end_color": sample_hex(end),
                "mid_color": sample_hex(center),
                "confidence": round(min(0.96, 0.54 + (strongest_delta / 160)), 2),
                "source": "image_sampling",
            }
        ]

    @staticmethod
    def _zone_roles_in_reading_order(zones: list[dict[str, Any]] | None) -> list[str]:
        if not isinstance(zones, list):
            return []
        sortable: list[tuple[float, float, str]] = []
        for index, zone in enumerate(zones):
            if not isinstance(zone, dict):
                continue
            role = str(zone.get("role") or zone.get("zone_id") or "").strip().lower()
            if not role:
                continue
            try:
                x = float(zone.get("x", 0) or 0)
                y = float(zone.get("y", 0) or 0)
            except (TypeError, ValueError):
                x = float(index)
                y = float(index)
            sortable.append((y, x, role))
        ordered: list[str] = []
        seen: set[str] = set()
        for _, _, role in sorted(sortable):
            if role in seen:
                continue
            seen.add(role)
            ordered.append(role)
        return ordered

    def _derive_visual_hierarchy(
        self,
        *,
        vision: dict[str, Any],
        reusable_zones: list[dict[str, Any]],
        style_map: list[dict[str, Any]],
        heading_style: dict[str, Any] | None,
        cta_area: str | None,
    ) -> dict[str, Any]:
        existing = vision.get("visual_hierarchy") if isinstance(vision.get("visual_hierarchy"), dict) else {}
        reading_order = existing.get("reading_order")
        if not isinstance(reading_order, list) or not reading_order:
            reading_order = self._zone_roles_in_reading_order(reusable_zones)
        focal_role = str(existing.get("focal_role") or "").strip().lower()
        if not focal_role:
            if heading_style and heading_style.get("estimated_font_size"):
                focal_role = "headline"
            elif any(str(zone.get("role") or "").strip().lower() == "image" for zone in reusable_zones if isinstance(zone, dict)):
                focal_role = "image"
            elif cta_area:
                focal_role = "cta"
            else:
                focal_role = reading_order[0] if reading_order else "mixed"
        density = str(existing.get("density") or "").strip().lower()
        if not density:
            signal_count = len(reusable_zones) + min(len(style_map), 4)
            density = "dense" if signal_count >= 8 else ("balanced" if signal_count >= 4 else "airy")
        whitespace = str(existing.get("whitespace") or "").strip().lower()
        if not whitespace:
            whitespace = {"dense": "tight", "balanced": "moderate", "airy": "generous"}.get(density, "moderate")
        emphasis = str(existing.get("emphasis") or "").strip().lower()
        if not emphasis:
            emphasis = "headline_first" if focal_role == "headline" else ("visual_first" if focal_role == "image" else "balanced")
        return {
            **existing,
            "focal_role": focal_role,
            "reading_order": [str(role).strip().lower() for role in reading_order if str(role).strip()],
            "density": density,
            "whitespace": whitespace,
            "emphasis": emphasis,
        }

    def _derive_content_structure(
        self,
        *,
        vision: dict[str, Any],
        reusable_zones: list[dict[str, Any]],
        heading: str | None,
        footer: str | None,
        cta_area: str | None,
        classified_lines: list[dict[str, Any]],
    ) -> dict[str, Any]:
        existing = vision.get("content_structure") if isinstance(vision.get("content_structure"), dict) else {}
        zone_roles = {
            str(zone.get("role") or "").strip().lower()
            for zone in reusable_zones
            if isinstance(zone, dict) and str(zone.get("role") or "").strip()
        }
        proof_modules = int(existing.get("proof_modules") or 0)
        if proof_modules <= 0:
            proof_modules = sum(1 for role in zone_roles if role in {"body", "proof_points", "stat_highlights", "section_label"})
        legal_footer_present = bool(existing.get("legal_footer_present"))
        if not legal_footer_present:
            legal_footer_present = bool(
                footer
                and any(
                    str(item.get("classification") or "") == "legal"
                    and str(item.get("line") or "").strip().casefold() in str(footer).casefold()
                    for item in classified_lines
                    if isinstance(item, dict)
                )
            )
        cta_prominence = str(existing.get("cta_prominence") or "").strip().lower()
        if not cta_prominence:
            cta_prominence = "high" if ("cta" in zone_roles or cta_area) else "medium" if "headline" in zone_roles else "low"
        storytelling = str(existing.get("storytelling") or "").strip().lower()
        if not storytelling:
            if proof_modules >= 3:
                storytelling = "benefit_stack"
            elif "section_label" in zone_roles:
                storytelling = "steps"
            else:
                storytelling = "single_claim"
        return {
            **existing,
            "headline_present": bool(existing.get("headline_present", bool(heading or "headline" in zone_roles))),
            "support_present": bool(existing.get("support_present", bool({"body", "section_label", "supporting_line"} & zone_roles))),
            "proof_modules": proof_modules,
            "legal_footer_present": legal_footer_present,
            "cta_prominence": cta_prominence,
            "storytelling": storytelling,
        }

    def _derive_design_tokens(
        self,
        *,
        background_style: dict[str, Any],
        palette: list[dict[str, Any]],
        exact_text_palette: list[dict[str, Any]],
        gradients: list[dict[str, Any]],
    ) -> dict[str, Any]:
        normalized_palette = [item for item in palette if isinstance(item, dict)]
        normalized_text_palette = [item for item in exact_text_palette if isinstance(item, dict)]
        return {
            "background_color": background_style.get("primary_hex") if isinstance(background_style, dict) else None,
            "secondary_background_color": background_style.get("secondary_hex") if isinstance(background_style, dict) else None,
            "palette_roles": [str(item.get("role") or "").strip().lower() for item in normalized_palette if item.get("role")],
            "text_color_hexes": [
                str(item.get("hex_code") or "").strip().upper()
                for item in normalized_text_palette
                if str(item.get("hex_code") or "").strip()
            ][:6],
            "gradient_count": len([item for item in gradients if isinstance(item, dict)]),
        }

    @staticmethod
    def _editorial_story_arc_roles(
        *,
        page_count_hint: int,
        storytelling: str,
    ) -> list[str]:
        slide_count = max(1, int(page_count_hint or 1))
        if slide_count == 1:
            return ["hook"]
        if slide_count == 2:
            return ["hook", "takeaway"]
        if storytelling == "steps":
            return ["hook", *["structure"] * max(slide_count - 2, 1), "takeaway"][:slide_count]
        if storytelling == "benefit_stack":
            return ["hook", *["detail"] * max(slide_count - 3, 1), "strategic_meaning", "takeaway"][:slide_count]
        if storytelling == "comparison":
            return ["hook", "context", *["structure"] * max(slide_count - 4, 0), "strategic_meaning", "takeaway"][:slide_count]
        if storytelling == "data_story":
            return ["hook", "context", *["undercovered_angle"] * max(slide_count - 4, 0), "strategic_meaning", "takeaway"][:slide_count]
        return ["hook", "context", *["structure"] * max(slide_count - 4, 0), "strategic_meaning", "takeaway"][:slide_count]

    def _derive_editorial_dna(
        self,
        *,
        text: str,
        content_structure: dict[str, Any],
        visual_hierarchy: dict[str, Any],
        classified_lines: list[dict[str, Any]],
        template_copy_lines: list[str],
        page_count_hint: int,
        cta_area: str | None,
        footer: str | None,
    ) -> dict[str, Any]:
        storytelling = str(content_structure.get("storytelling") or "").strip().lower()
        proof_modules = int(content_structure.get("proof_modules") or 0)
        legal_footer_present = bool(content_structure.get("legal_footer_present") or footer)
        if page_count_hint >= 3:
            format_family = "carousel"
        elif storytelling in {"steps", "comparison", "benefit_stack", "data_story"} or proof_modules >= 3:
            format_family = "infographic"
        else:
            format_family = "static"
        word_count = len(re.findall(r"\b\w+\b", text or ""))
        if word_count >= 300:
            copy_density = "high"
        elif word_count >= 120:
            copy_density = "medium"
        else:
            copy_density = "low"
        if page_count_hint >= 4 and storytelling in {"steps", "benefit_stack"}:
            explanation_style = "stepwise_educational"
        elif page_count_hint >= 4 and storytelling in {"comparison", "data_story"}:
            explanation_style = "insight_explainer"
        elif page_count_hint >= 3:
            explanation_style = "paginated_explainer"
        else:
            explanation_style = "single_frame_summary"
        closing_style = "cta_close" if cta_area or str(content_structure.get("cta_prominence") or "").strip().lower() == "high" else "reflective_close"
        supporting_patterns = [
            str(item.get("line") or "").strip()
            for item in classified_lines
            if isinstance(item, dict)
            and str(item.get("classification") or "").strip() in {"template_copy", "cta_copy", "headline", "supporting_copy"}
            and str(item.get("line") or "").strip()
        ][:8]
        return {
            "format_family": format_family,
            "page_count_hint": max(1, int(page_count_hint or 1)),
            "story_arc_roles": self._editorial_story_arc_roles(
                page_count_hint=page_count_hint,
                storytelling=storytelling,
            ),
            "storytelling_mode": storytelling,
            "explanation_style": explanation_style,
            "copy_density": copy_density,
            "proof_module_count": proof_modules,
            "closing_style": closing_style,
            "disclaimer_present": legal_footer_present,
            "headline_patterns": template_copy_lines[:4],
            "supporting_patterns": supporting_patterns[:6],
            "editorial_signals": [
                cue
                for cue in [
                    storytelling,
                    explanation_style,
                    str(visual_hierarchy.get("focal_role") or "").strip().lower(),
                    str(visual_hierarchy.get("density") or "").strip().lower(),
                    "cta_present" if cta_area else "",
                    "legal_footer" if legal_footer_present else "",
                ]
                if cue
            ][:8],
        }

    def _derive_visual_craft_dna(
        self,
        *,
        vision: dict[str, Any],
        gradients: list[dict[str, Any]],
        component_motifs: dict[str, Any],
    ) -> dict[str, Any]:
        craft = vision.get("visual_craft_dna") if isinstance(vision.get("visual_craft_dna"), dict) else {}
        image_treatment = vision.get("image_treatment") if isinstance(vision.get("image_treatment"), dict) else {}
        design_style = str(vision.get("design_style") or "").strip().lower()

        depth_style = str(craft.get("depth_style") or "").strip().lower()
        if not depth_style:
            if design_style == "3d" or str(image_treatment.get("style") or "").strip().lower() == "3d":
                depth_style = "true_3d"
            elif gradients or component_motifs.get("shadows") not in (None, "", "none"):
                depth_style = "layered"
            else:
                depth_style = "flat"

        rendering_style = str(craft.get("rendering_style") or "").strip().lower()
        if not rendering_style:
            treatment_style = str(image_treatment.get("style") or "").strip().lower()
            rendering_style = {
                "photo": "photo",
                "illustration": "vector",
                "3d": "3d_render",
                "iconic": "vector",
                "abstract": "vector",
            }.get(treatment_style, "mixed" if treatment_style == "mixed" else "vector")

        lighting = str(craft.get("lighting") or "").strip().lower()
        if not lighting:
            shadows = str(component_motifs.get("shadows") or "").strip().lower()
            lighting = "soft" if shadows == "soft" else ("flat" if shadows in {"none", ""} else "ambient")

        material_cues = [
            str(item).strip()
            for item in (craft.get("material_cues") or [])
            if str(item).strip()
        ][:8]
        if not material_cues:
            if gradients:
                material_cues.append("gradient_surface")
            text_background_boxes = component_motifs.get("text_background_boxes") if isinstance(component_motifs.get("text_background_boxes"), dict) else {}
            if text_background_boxes.get("detected"):
                material_cues.append("boxed_label_panels")

        dimensionality_cues = [
            str(item).strip()
            for item in (craft.get("dimensionality_cues") or [])
            if str(item).strip()
        ][:8]
        if not dimensionality_cues:
            if gradients:
                dimensionality_cues.append("gradient_depth")
            if str(component_motifs.get("shadows") or "").strip().lower() not in {"", "none"}:
                dimensionality_cues.append("shadow_separation")

        polish_level = str(craft.get("polish_level") or "").strip().lower()
        if not polish_level:
            polish_level = "premium" if gradients or str(component_motifs.get("shadows") or "").strip().lower() == "soft" else "clean"

        return {
            "depth_style": depth_style,
            "rendering_style": rendering_style,
            "lighting": lighting,
            "polish_level": polish_level,
            "material_cues": material_cues,
            "dimensionality_cues": dimensionality_cues,
        }

    def _derive_subject_semantics(
        self,
        *,
        vision: dict[str, Any],
        template_copy_lines: list[str],
        classified_lines: list[dict[str, Any]],
    ) -> dict[str, Any]:
        semantics = vision.get("subject_semantics") if isinstance(vision.get("subject_semantics"), dict) else {}
        image_treatment = vision.get("image_treatment") if isinstance(vision.get("image_treatment"), dict) else {}
        infographic_elements = vision.get("infographic_elements") if isinstance(vision.get("infographic_elements"), dict) else {}

        scene_type = str(semantics.get("scene_type") or "").strip()
        if not scene_type:
            scene_type = "educational finance explainer" if str(image_treatment.get("style") or "").strip().lower() != "none" else "text-led explainer"

        primary_subjects = [
            str(item).strip()
            for item in (semantics.get("primary_subjects") or [])
            if str(item).strip()
        ][:8]
        if not primary_subjects:
            keywords = []
            for line in [*template_copy_lines, *[item.get("line") for item in classified_lines if isinstance(item, dict)][:8]]:
                text = str(line or "").strip().lower()
                if not text:
                    continue
                for token in ("retirement", "bond", "market", "income", "wealth", "future", "investing", "finance"):
                    if token in text and token not in keywords:
                        keywords.append(token)
            primary_subjects = keywords[:6]

        domain_cues = [
            str(item).strip()
            for item in (semantics.get("domain_cues") or [])
            if str(item).strip()
        ][:8]
        if not domain_cues:
            domain_cues = [item for item in primary_subjects if item in {"retirement", "bond", "market", "income", "wealth", "investing", "finance"}][:6]

        financial_objects = [
            str(item).strip()
            for item in (semantics.get("financial_objects") or [])
            if str(item).strip()
        ][:8]
        if not financial_objects:
            inferred_objects = []
            if str(infographic_elements.get("graphs") or "").strip().lower() not in {"", "none"}:
                inferred_objects.append("graph")
            if "bond" in " ".join(primary_subjects):
                inferred_objects.append("bond_visual")
            if "retirement" in " ".join(primary_subjects):
                inferred_objects.append("retirement_goal")
            financial_objects = inferred_objects[:6]

        human_presence = str(semantics.get("human_presence") or "").strip().lower()
        if not human_presence:
            human_presence = "none"

        environment = str(semantics.get("environment") or "").strip()
        if not environment:
            environment = "clean editorial canvas"

        abstraction_level = str(semantics.get("abstraction_level") or "").strip().lower()
        if not abstraction_level:
            abstraction_level = "conceptual" if str(image_treatment.get("style") or "").strip().lower() in {"illustration", "iconic", "abstract"} else "mixed"

        return {
            "scene_type": scene_type,
            "primary_subjects": primary_subjects,
            "domain_cues": domain_cues,
            "financial_objects": financial_objects,
            "human_presence": human_presence,
            "environment": environment,
            "abstraction_level": abstraction_level,
        }

    @staticmethod
    def _dedupe_visual_style_values(values: list[str], *, limit: int = 6) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
            if len(ordered) >= limit:
                break
        return ordered

    @staticmethod
    def _supports_visual_signal(value: Any) -> bool:
        normalized = str(value or "").strip().lower()
        return normalized not in {"", "none", "no", "false", "0", "null", "unknown"}

    @staticmethod
    def _rendering_family(rendering_mode: str) -> str:
        normalized = str(rendering_mode or "").strip().lower()
        return {
            "photo": "photo",
            "vector": "illustration",
            "3d_render": "3d",
        }.get(normalized, "mixed" if normalized in {"mixed", "composite"} else "")

    def _derive_visual_style_profile(
        self,
        *,
        vision: dict[str, Any],
        visual_craft_dna: dict[str, Any],
        subject_semantics: dict[str, Any],
        editorial_dna: dict[str, Any],
    ) -> dict[str, Any]:
        image_treatment = vision.get("image_treatment") if isinstance(vision.get("image_treatment"), dict) else {}
        infographic_elements = vision.get("infographic_elements") if isinstance(vision.get("infographic_elements"), dict) else {}
        design_style = str(vision.get("design_style") or "").strip().lower()
        treatment_style = str(image_treatment.get("style") or "").strip().lower()
        rendering_style = str(visual_craft_dna.get("rendering_style") or "").strip().lower()
        depth_style = str(visual_craft_dna.get("depth_style") or "").strip().lower()
        scene_type = str(subject_semantics.get("scene_type") or "").strip().lower()
        abstraction_level = str(subject_semantics.get("abstraction_level") or "").strip().lower()
        human_presence = str(subject_semantics.get("human_presence") or "").strip().lower()
        primary_subjects = [
            str(item or "").strip().lower()
            for item in (subject_semantics.get("primary_subjects") or [])
            if str(item or "").strip()
        ]
        storytelling_mode = str(editorial_dna.get("storytelling_mode") or "").strip().lower()
        explanation_style = str(editorial_dna.get("explanation_style") or "").strip().lower()
        closing_style = str(editorial_dna.get("closing_style") or "").strip().lower()
        story_roles = [
            str(item or "").strip().lower()
            for item in (editorial_dna.get("story_arc_roles") or [])
            if str(item or "").strip()
        ]
        image_signal_text = " ".join(
            [
                design_style,
                treatment_style,
                rendering_style,
                depth_style,
                scene_type,
                abstraction_level,
                " ".join(primary_subjects),
            ]
        )

        if "3d" in image_signal_text:
            image_mode = "3d"
        elif any(token in image_signal_text for token in ("photo", "photograph", "editorial", "lifestyle", "portrait", "food")):
            image_mode = "photo"
        elif any(token in image_signal_text for token in ("illustration", "vector", "iconic", "abstract", "diagram")):
            image_mode = "illustration"
        elif any(token in image_signal_text for token in ("mixed", "composite", "collage")):
            image_mode = "mixed"
        else:
            image_mode = "mixed" if rendering_style == "mixed" else "illustration"

        if depth_style == "true_3d":
            depth_mode = "true_3d"
        elif depth_style in {"layered", "3d_illusion"}:
            depth_mode = depth_style
        elif depth_style == "flat":
            depth_mode = "flat"
        elif "isometric" in image_signal_text or "2.5d" in image_signal_text:
            depth_mode = "3d_illusion"
        else:
            depth_mode = "flat"

        if rendering_style == "3d_render":
            rendering_mode = "3d_render"
        elif rendering_style in {"photo", "vector", "composite", "mixed"}:
            rendering_mode = rendering_style
        elif image_mode == "photo":
            rendering_mode = "photo"
        elif image_mode == "3d":
            rendering_mode = "3d_render"
        elif any(token in image_signal_text for token in ("collage", "overlay", "composite")):
            rendering_mode = "composite"
        else:
            rendering_mode = "vector"

        if any(token in " ".join(primary_subjects + [scene_type]) for token in ("food", "fish", "prawn", "seafood", "dish", "recipe", "meal")):
            subject_mode = "food"
        elif human_presence not in {"", "none"} or any(
            token in " ".join(primary_subjects + [scene_type])
            for token in ("human", "people", "person", "child", "parent", "coach", "team", "family", "patient")
        ):
            subject_mode = "human"
        elif any(token in " ".join(primary_subjects + [scene_type]) for token in ("dashboard", "app", "screen", "laptop", "mockup", "product")):
            subject_mode = "product_mockup"
        elif any(token in " ".join(primary_subjects + [scene_type]) for token in ("metaphor", "concept", "bias", "mindset", "journey")) or abstraction_level == "conceptual":
            subject_mode = "conceptual"
        elif self._supports_visual_signal(infographic_elements.get("graphs")) or self._supports_visual_signal(infographic_elements.get("icons")):
            subject_mode = "infographic"
        elif primary_subjects:
            subject_mode = "object"
        else:
            subject_mode = "mixed"

        has_graphs = any(
            self._supports_visual_signal(infographic_elements.get(key))
            for key in ("graphs", "charts", "data_visuals", "tables")
        )
        has_icons = any(
            self._supports_visual_signal(infographic_elements.get(key))
            for key in ("icons", "badges", "markers", "pictograms")
        )
        if has_graphs and has_icons:
            support_mode = "mixed"
        elif has_graphs:
            support_mode = "chart_led"
        elif has_icons:
            support_mode = "icon_led"
        elif image_mode == "photo":
            support_mode = "photo_led"
        elif subject_mode in {"food", "object", "product_mockup"} or image_mode == "3d":
            support_mode = "object_led"
        elif not self._supports_visual_signal(image_treatment.get("style")):
            support_mode = "text_led"
        else:
            support_mode = "mixed"

        if closing_style == "cta_close" or any(role in {"cta", "cta_close", "close", "ending", "closing"} for role in story_roles):
            story_visual_role = "cta_close"
        elif any(role in {"hook", "cover", "intro", "opening", "context"} for role in story_roles):
            story_visual_role = "hook_hero"
        elif storytelling_mode == "comparison":
            story_visual_role = "comparison"
        elif storytelling_mode in {"steps", "benefit_stack"} or explanation_style == "stepwise_educational":
            story_visual_role = "steps"
        elif storytelling_mode == "data_story" or has_graphs:
            story_visual_role = "data_story"
        else:
            story_visual_role = "detail_explainer"

        style_mix = self._dedupe_visual_style_values(
            [
                image_mode,
                depth_mode,
                rendering_mode,
                subject_mode,
                support_mode,
                story_visual_role,
            ],
            limit=8,
        )
        visual_families = {
            family
            for family in [
                image_mode if image_mode in {"photo", "illustration", "3d"} else "",
                self._rendering_family(rendering_mode),
                "3d" if depth_mode in {"true_3d", "3d_illusion"} else "",
            ]
            if family
        }
        consistency_hint = "mixed_mode" if image_mode == "mixed" or rendering_mode == "mixed" or len(visual_families) >= 2 else "single_mode"
        return {
            "image_mode": image_mode,
            "depth_mode": depth_mode,
            "rendering_mode": rendering_mode,
            "subject_mode": subject_mode,
            "support_mode": support_mode,
            "story_visual_role": story_visual_role,
            "style_mix": style_mix,
            "consistency_hint": consistency_hint,
        }

    def _extract_template_intelligence(
        self,
        text: str,
        absolute_path: str,
        images: list[str],
        category: str,
        analysis_paths: list[str] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        fallback = {
            "background_style": {"type": "graphic", "dominant_mode": "graphic", "source": "heuristic"},
            "layout_type": "multi_section",
            "editable_zones": [
                {"zone_id": "headline", "role": "headline"},
                {"zone_id": "body", "role": "body"},
                {"zone_id": "image", "role": "image"},
                {"zone_id": "cta", "role": "cta"},
            ],
            "visual_hierarchy": {},
            "content_structure": {},
            "image_treatment": {},
            "brand_cues": {},
            "icons": [],
            "platform_hints": ["instagram", "linkedin", "x", "pdf"],
        }
        selected_pages = self._select_representative_visual_pages(
            absolute_path=absolute_path,
            images=images,
            analysis_paths=analysis_paths,
        )
        vision_inputs = [str(item.get("image_path") or "") for item in selected_pages if str(item.get("image_path") or "").strip()]
        vision_source = vision_inputs[0] if vision_inputs else next((candidate for candidate in ([absolute_path, *images]) if Path(candidate).exists()), None)
        if len(vision_inputs) > 1:
            vision = TemplateVisionAnalyzer.analyze_pages(self.vision, vision_inputs, fallback)
        else:
            vision = self.vision.analyze(vision_source, fallback) if vision_source else fallback
        selected_analyses = [
            item.get("analysis")
            for item in selected_pages
            if isinstance(item.get("analysis"), dict)
        ]
        primary_analysis = max(
            selected_pages,
            key=lambda item: (float(item.get("density_score") or 0.0), float(item.get("cta_score") or 0.0)),
            default={},
        )
        analysis = primary_analysis.get("analysis") if isinstance(primary_analysis.get("analysis"), dict) else {}

        # 🔥 PHASE 3: Merge layout_structure from GCV into vision intelligence
        if analysis and "layout_structure" in analysis:
            vision = self._merge_layout_structure(vision, analysis["layout_structure"])

        layout_dna: dict[str, Any] = {}
        if vision_source:
            try:
                layout_dna = self.vision.extract_layout_dna(
                    vision_source,
                    base_analysis=vision,
                )
            except Exception:  # noqa: BLE001
                layout_dna = {}
        if layout_dna:
            existing_layout_structure = vision.get("layout_structure") if isinstance(vision.get("layout_structure"), dict) else {}
            vision["layout_structure"] = {
                **existing_layout_structure,
                "layout_dna": layout_dna,
            }

        fonts = self._extract_fonts(text)
        palette = self._extract_palette_from_text(text) or (self._dominant_palette(vision_source) if vision_source else [])
        style_map = self._merge_text_style_maps([analysis for analysis in selected_analyses if isinstance(analysis, dict)]) or self._extract_text_style_map(analysis)
        exact_text_palette = self._exact_text_palette(style_map)
        if exact_text_palette:
            existing = {entry.get("hex_code") for entry in palette if isinstance(entry, dict)}
            palette = [*palette, *[entry for entry in exact_text_palette if entry.get("hex_code") not in existing]]
        header = self._search_value(text, r"header[:\s]+([^\n]+)")
        footer = self._search_value(text, r"footer[:\s]+([^\n]+)")
        heading = self._guess_heading(text)
        header_style = self._pick_text_style_role(style_map, role="header", fallback_text=header)
        footer_style = self._pick_text_style_role(style_map, role="footer", fallback_text=footer)
        heading_style = self._pick_text_style_role(style_map, role="heading", fallback_text=heading)
        if header_style and header_style.get("text"):
            header = str(header_style.get("text"))
        if footer_style and footer_style.get("text"):
            footer = str(footer_style.get("text"))
        if heading_style and heading_style.get("text"):
            heading = str(heading_style.get("text"))
        cta_area = self._guess_cta(text)
        gradients = [
            *self._extract_gradients(text),
            *self._infer_image_gradient(vision_source),
        ]
        reusable_zones = vision.get("editable_zones", []) or fallback["editable_zones"]
        classified_lines = self._classified_text_lines(text)
        salient_lines = self._salient_text_lines(
            text,
            keywords=[
                "background",
                "color",
                "composition",
                "cta",
                "font",
                "gradient",
                "grid",
                "header",
                "headline",
                "icon",
                "layout",
                "palette",
                "spacing",
                "style",
                "texture",
                "typography",
            ],
            limit=5,
            allowed_classifications={"visual_system", "unknown"},
        )
        available_signal_types = {
            signal_type
            for signal_type, enabled in {
                "layout": bool(vision.get("layout_type")),
                "background": isinstance(vision.get("background_style"), dict) and bool((vision.get("background_style") or {}).get("dominant_mode")),
                "palette": bool(palette),
                "typography": bool(fonts),
                "zones": bool(reusable_zones),
                "icons": bool(vision.get("icons")),
                "motifs": bool(gradients),
            }.items()
            if enabled
        }
        source_agreement = self._source_agreement(
            classified_lines,
            available_signal_types=available_signal_types,
        )
        visual_hierarchy = self._derive_visual_hierarchy(
            vision=vision,
            reusable_zones=reusable_zones,
            style_map=style_map,
            heading_style=heading_style,
            cta_area=cta_area,
        )
        content_structure = self._derive_content_structure(
            vision=vision,
            reusable_zones=reusable_zones,
            heading=heading,
            footer=footer,
            cta_area=cta_area,
            classified_lines=classified_lines,
        )
        design_tokens = self._derive_design_tokens(
            background_style=vision.get("background_style", {}),
            palette=palette,
            exact_text_palette=exact_text_palette,
            gradients=gradients,
        )
        style_summary = self._summary_from_parts(
            [
                f"Layout {vision.get('layout_type', 'multi_section')}",
                f"Background {self._normalize_summary_fragment((vision.get('background_style') or {}).get('dominant_mode'), limit=40)}"
                if isinstance(vision.get("background_style"), dict)
                else "",
                f"Palette: {', '.join(self._palette_summary_terms(palette, limit=4))}" if palette else "",
                f"Typography: {', '.join(self._font_summary_terms(fonts, limit=3))}" if fonts else "",
                f"Editable zones: {', '.join(self._zone_summary_terms(reusable_zones, limit=5))}" if reusable_zones else "",
                *salient_lines[:2],
            ],
            limit=340,
        )
        visual_evidence_units = [
            unit
            for unit in [
                {"kind": "layout", "summary": f"Layout {vision.get('layout_type', 'multi_section')}", "source": "vision"},
                {
                    "kind": "background",
                    "summary": f"Background {self._normalize_summary_fragment((vision.get('background_style') or {}).get('dominant_mode'), limit=40)}",
                    "source": "vision",
                }
                if isinstance(vision.get("background_style"), dict)
                and self._normalize_summary_fragment((vision.get("background_style") or {}).get("dominant_mode"), limit=40)
                else None,
                {
                    "kind": "palette",
                    "summary": f"Palette: {', '.join(self._palette_summary_terms(palette, limit=4))}",
                    "source": "hybrid",
                }
                if palette
                else None,
                {
                    "kind": "typography",
                    "summary": f"Typography: {', '.join(self._font_summary_terms(fonts, limit=3))}",
                    "source": "hybrid",
                }
                if fonts
                else None,
                {
                    "kind": "zones",
                    "summary": f"Editable zones: {', '.join(self._zone_summary_terms(reusable_zones, limit=5))}",
                    "source": "vision",
                }
                if reusable_zones
                else None,
            ]
            if isinstance(unit, dict)
        ]
        template_copy_lines = self._template_copy_lines(
            heading,
            header,
            footer,
            *[
                item.get("line")
                for item in classified_lines
                if isinstance(item, dict)
                and str(item.get("classification") or "") in {"template_copy", "cta_copy"}
            ],
        )
        template_copy_summary = self._summary_from_parts(
            [f"Template copy cues: {', '.join(template_copy_lines)}" if template_copy_lines else ""],
            limit=220,
        )
        page_analysis_summary = vision.get("page_analysis_summary", []) if isinstance(vision.get("page_analysis_summary"), list) else []
        if not page_analysis_summary and selected_pages:
            page_analysis_summary = [
                {
                    "page_index": int(item.get("page_index") or 0),
                    "image_path": str(item.get("image_path") or ""),
                    "density_score": float(item.get("density_score") or 0.0),
                    "cta_score": float(item.get("cta_score") or 0.0),
                }
                for item in selected_pages
            ]
        analysis_confidence = float(vision.get("analysis_confidence") or 0.0) if str(vision.get("analysis_confidence") or "").strip() else 0.0
        if analysis_confidence <= 0.0 and selected_pages:
            analysis_confidence = 1.0 if vision_source else 0.0
        page_count_hint = max(
            len([item for item in images if str(item).strip()]),
            len(page_analysis_summary),
            1,
        )
        editorial_dna = self._derive_editorial_dna(
            text=text,
            content_structure=content_structure,
            visual_hierarchy=visual_hierarchy,
            classified_lines=classified_lines,
            template_copy_lines=template_copy_lines,
            page_count_hint=page_count_hint,
            cta_area=cta_area,
            footer=footer,
        )
        visual_craft_dna = self._derive_visual_craft_dna(
            vision=vision,
            gradients=gradients,
            component_motifs=vision.get("component_motifs", {}) if isinstance(vision.get("component_motifs"), dict) else {},
        )
        subject_semantics = self._derive_subject_semantics(
            vision=vision,
            template_copy_lines=template_copy_lines,
            classified_lines=classified_lines,
        )
        visual_style_profile = self._derive_visual_style_profile(
            vision=vision,
            visual_craft_dna=visual_craft_dna,
            subject_semantics=subject_semantics,
            editorial_dna=editorial_dna,
        )
        quality = self._analysis_quality(
            text=text,
            summary=style_summary,
            salient_lines=salient_lines,
            palette_count=len(palette),
            font_count=len(fonts),
            zone_count=len(reusable_zones),
            evidence_types=["layout", "palette", "typography", "zones", "visual_system"],
            classified_lines=classified_lines,
            source_agreement=source_agreement,
        )
        structured = {
            "heading": heading,
            "header": header,
            "footer": footer,
            "heading_style": heading_style,
            "header_style": header_style,
            "footer_style": footer_style,
            "fonts": fonts,
            "font_size_hints": self._extract_font_sizes(text) or [
                {
                    "value": item["estimated_font_size"],
                    "unit": "px",
                    "source": "visual_estimate",
                }
                for item in style_map
                if item.get("estimated_font_size")
            ][:8],
            "font_colors": exact_text_palette[:8] or palette[:3],
            "text_style_map": style_map,
            "gradients": gradients,
            "cards": self._has_tokens(text, ["card", "panel", "tile"]),
            "icons": vision.get("icons", []),
            "logos": self._has_tokens(text, ["logo", "brandmark"]),
            "layout_structure": {
                "layout_type": vision.get("layout_type", "multi_section"),
                "zones": reusable_zones,
            },
            "spacing_pattern": "balanced modular grid" if "grid" in text.lower() else "editorial",
            "cta_area": cta_area,
            "brand_score": round(0.55 + (0.05 * len(reusable_zones)) + (0.04 * len(palette[:3])), 2),
            "style_characteristics": {
                "background_style": vision.get("background_style", {}),
                "composition": "infographic" if "info" in text.lower() else "marketing creative",
                "component_motifs": vision.get("component_motifs", {}),
                "typography_dna": vision.get("typography_dna", {}),
                "infographic_elements": vision.get("infographic_elements", {}),
                "visual_hierarchy": visual_hierarchy,
                "content_structure": content_structure,
                "image_treatment": vision.get("image_treatment", {}),
                "layout_dna": layout_dna,
                "composition_logic": vision.get("composition_logic", {}),
                "visual_craft_dna": visual_craft_dna,
                "subject_semantics": subject_semantics,
                "visual_style_profile": visual_style_profile,
                "brand_cues": vision.get("brand_cues", {}),
                "design_tokens": design_tokens,
                "editorial_dna": editorial_dna,
                "layout_type": vision.get("layout_type"),
                "visual_mood": vision.get("visual_mood"),
                "design_style": vision.get("design_style"),
            },
            "color_usage": palette,
            "composition_style": vision.get("layout_type", "multi_section"),
            "infographic_blocks": self._extract_bucketed_items(
                self._interesting_lines(text),
                ["case", "step", "insight"],
                require_asset_label=False,
            ),
            "reusable_zones": reusable_zones,
            "style_summary": style_summary,
            "structure_summary": style_summary,
            "summary": style_summary,
            "visual_evidence_units": visual_evidence_units,
            "copy_lines": template_copy_lines,
            "copy_summary": template_copy_summary,
            "classified_text_lines": classified_lines,
            "analysis_quality": quality,
            "page_analysis_summary": page_analysis_summary,
            "analysis_confidence": round(analysis_confidence, 4),
            "visual_hierarchy": visual_hierarchy,
            "content_structure": content_structure,
            "image_treatment": vision.get("image_treatment", {}),
            "layout_dna": layout_dna,
            "composition_logic": vision.get("composition_logic", {}),
            "visual_craft_dna": visual_craft_dna,
            "subject_semantics": subject_semantics,
            "visual_style_profile": visual_style_profile,
            "brand_cues": vision.get("brand_cues", {}),
            "design_tokens": design_tokens,
            "editorial_dna": editorial_dna,
            "warnings": [],
        }
        normalized = {
            "template_type": category,
            "layout_type": vision.get("layout_type", "multi_section"),
            "reusable_zones": reusable_zones,
            "palette": palette,
            "font_families": fonts,
            "text_style_map": style_map,
            "gradients": gradients,
            "cta_area": cta_area,
            "brand_score": structured["brand_score"],
            "component_motifs": vision.get("component_motifs", {}),
            "typography_dna": vision.get("typography_dna", {}),
            "infographic_elements": vision.get("infographic_elements", {}),
            "visual_mood": vision.get("visual_mood"),
            "design_style": vision.get("design_style"),
            "logo_anchor": vision.get("logo_anchor"),
            "style_summary": style_summary,
            "structure_summary": style_summary,
            "summary": style_summary,
            "visual_evidence_units": visual_evidence_units,
            "copy_lines": template_copy_lines,
            "copy_summary": template_copy_summary,
            "classified_text_lines": classified_lines,
            "analysis_quality": quality,
            "page_analysis_summary": page_analysis_summary,
            "analysis_confidence": round(analysis_confidence, 4),
            "visual_hierarchy": visual_hierarchy,
            "content_structure": content_structure,
            "image_treatment": vision.get("image_treatment", {}),
            "layout_dna": layout_dna,
            "composition_logic": vision.get("composition_logic", {}),
            "visual_craft_dna": visual_craft_dna,
            "subject_semantics": subject_semantics,
            "visual_style_profile": visual_style_profile,
            "brand_cues": vision.get("brand_cues", {}),
            "design_tokens": design_tokens,
            "editorial_dna": editorial_dna,
        }
        template_analysis = {
            "layout_type": vision.get("layout_type", "multi_section"),
            "background_style": vision.get("background_style", {}),
            "editable_zones": reusable_zones,
            "icons": vision.get("icons", []),
            "platform_hints": vision.get("platform_hints", ["linkedin", "instagram"]),
            "component_motifs": vision.get("component_motifs", {}),
            "typography_dna": vision.get("typography_dna", {}),
            "infographic_elements": vision.get("infographic_elements", {}),
            "visual_mood": vision.get("visual_mood"),
            "design_style": vision.get("design_style"),
            "logo_anchor": vision.get("logo_anchor"),
            "heading": heading,
            "header": header,
            "footer": footer,
            "heading_style": heading_style,
            "header_style": header_style,
            "footer_style": footer_style,
            "color_usage": palette,
            "font_families": fonts,
            "font_colors": structured["font_colors"],
            "font_size_hints": structured["font_size_hints"],
            "text_style_map": style_map,
            "gradients": gradients,
            "cta_area": cta_area,
            "brand_score": structured["brand_score"],
            "reusable_zones": reusable_zones,
            "style_summary": style_summary,
            "structure_summary": style_summary,
            "summary": style_summary,
            "visual_evidence_units": visual_evidence_units,
            "copy_lines": template_copy_lines,
            "copy_summary": template_copy_summary,
            "classified_text_lines": classified_lines,
            "analysis_quality": quality,
            "page_analysis_summary": page_analysis_summary,
            "analysis_confidence": round(analysis_confidence, 4),
            "visual_hierarchy": visual_hierarchy,
            "content_structure": content_structure,
            "image_treatment": vision.get("image_treatment", {}),
            "layout_dna": layout_dna,
            "composition_logic": vision.get("composition_logic", {}),
            "visual_craft_dna": visual_craft_dna,
            "subject_semantics": subject_semantics,
            "visual_style_profile": visual_style_profile,
            "brand_cues": vision.get("brand_cues", {}),
            "design_tokens": design_tokens,
            "editorial_dna": editorial_dna,
            "tags": [
                token
                for token in {
                    category,
                    vision.get("layout_type", "multi_section"),
                    *(item.get("role", "") for item in reusable_zones if isinstance(item, dict)),
                }
                if token
            ],
        }
        return structured, normalized, template_analysis

    @staticmethod
    def _merge_layout_structure(
        intelligence: dict[str, Any], layout_structure: dict[str, Any]
    ) -> dict[str, Any]:
        """🔥 PHASE 3: Merge GCV layout structure into template intelligence"""
        component_motifs = intelligence.get("component_motifs", {})

        # Add numbered badges from detected numbered elements
        numbered_elements = layout_structure.get("numbered_elements", [])
        if numbered_elements:
            component_motifs["numbered_badges"] = {
                "detected": True,
                "count": len(numbered_elements),
                "patterns": list({elem.get("pattern", "") for elem in numbered_elements if elem.get("pattern")}),
                "shape": "rounded_rect",  # Inferred from common patterns
            }

        # Add icon associations
        icon_pairs = layout_structure.get("icon_text_pairs", [])
        if icon_pairs:
            component_motifs["icon_text_associations"] = {
                "detected": True,
                "count": len(icon_pairs),
                "icons": [pair.get("icon", "") for pair in icon_pairs[:5] if pair.get("icon")],
            }

        # Add section info to content_structure
        content_structure = intelligence.get("content_structure", {})
        hierarchy = layout_structure.get("section_hierarchy", {})
        if hierarchy.get("hierarchy_detected"):
            content_structure["hierarchy_levels"] = len(hierarchy.get("sections", []))
            content_structure["section_pattern"] = (
                "hierarchical_steps" if numbered_elements else "hierarchical_content"
            )

        intelligence["component_motifs"] = component_motifs
        intelligence["content_structure"] = content_structure
        intelligence["layout_structure_raw"] = layout_structure  # Preserve full data

        return intelligence

    def _extract_mood_board(
        self,
        text: str,
        absolute_path: str,
        images: list[str],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        palette = self._dominant_palette(next(iter(images or [absolute_path]), absolute_path))
        lines = self._interesting_lines(text)
        classified_lines = self._classified_text_lines(text)
        asset_labels: list[str] = []
        seen_asset_labels: set[str] = set()
        for line in lines:
            if not self._looks_like_asset_label(line):
                continue
            key = line.casefold()
            if key in seen_asset_labels:
                continue
            seen_asset_labels.add(key)
            asset_labels.append(line)
            if len(asset_labels) >= 16:
                break
        visual_terms = self._extract_bucketed_items(
            lines,
            ["icon", "symbol", "badge", "style", "mood", "visual", "pattern", "texture", "graphic", "element", "shape", "motif"],
        )
        if not visual_terms:
            visual_terms = asset_labels[:12]
        icon_terms = [
            item for item in visual_terms
            if any(keyword in item.casefold() for keyword in ("icon", "symbol", "badge", "mark", "logo"))
        ]
        style_terms = [item for item in visual_terms if item not in icon_terms]
        source_agreement = self._source_agreement(
            classified_lines,
            available_signal_types={
                signal_type
                for signal_type, enabled in {
                    "palette": bool(palette),
                    "icons": bool(icon_terms or asset_labels),
                    "motifs": bool(style_terms),
                }.items()
                if enabled
            },
        )
        style_summary = self._summary_from_parts(
            [
                f"Visual motifs: {', '.join(style_terms[:4])}" if style_terms else "",
                f"Icon assets: {', '.join(icon_terms[:4])}" if icon_terms else "",
                f"Palette: {', '.join(self._palette_summary_terms(palette, limit=3))}" if palette else "",
                f"Asset labels: {', '.join(asset_labels[:4])}" if asset_labels else "",
            ],
            limit=320,
        )
        quality = self._analysis_quality(
            text=text,
            summary=style_summary,
            salient_lines=self._salient_text_lines(
                text,
                keywords=["badge", "element", "graphic", "icon", "motif", "pattern", "shape", "style", "symbol", "texture", "visual"],
                limit=5,
                prefer_labels=True,
                allowed_classifications={"visual_system"},
            ),
            palette_count=len(palette),
            label_count=len(asset_labels),
            evidence_types=["palette", "asset_labels", "icons", "visual_system"],
            classified_lines=classified_lines,
            source_agreement=source_agreement,
        )
        visual_evidence_units = [
            unit
            for unit in [
                {
                    "kind": "motifs",
                    "summary": f"Visual motifs: {', '.join(style_terms[:4])}",
                    "source": "ocr",
                }
                if style_terms
                else None,
                {
                    "kind": "icons",
                    "summary": f"Icon assets: {', '.join(icon_terms[:4])}",
                    "source": "ocr",
                }
                if icon_terms
                else None,
                {
                    "kind": "palette",
                    "summary": f"Palette: {', '.join(self._palette_summary_terms(palette, limit=3))}",
                    "source": "image",
                }
                if palette
                else None,
            ]
            if isinstance(unit, dict)
        ]
        structured = {
            "style_summary": style_summary,
            "summary": style_summary,
            "asset_labels": [{"label": item} for item in asset_labels[:16]],
            "icon_assets": [{"label": item} for item in icon_terms],
            "micro_design_elements": [{"label": item} for item in style_terms[:6]],
            "decorative_assets": [{"label": item} for item in style_terms[6:12]],
            "enhancement_components": [{"label": item, "palette": palette[:2]} for item in style_terms[:4]],
            "visual_evidence_units": visual_evidence_units,
            "classified_text_lines": classified_lines,
            "analysis_quality": quality,
        }
        normalized = {
            "style_summary": structured["style_summary"],
            "summary": style_summary,
            "asset_labels": structured["asset_labels"],
            "icon_assets": structured["icon_assets"],
            "micro_design_elements": structured["micro_design_elements"],
            "decorative_assets": structured["decorative_assets"],
            "enhancement_components": structured["enhancement_components"],
            "palette": palette,
            "visual_evidence_units": visual_evidence_units,
            "classified_text_lines": classified_lines,
            "analysis_quality": quality,
        }
        return structured, normalized

    def _extract_palette(
        self,
        text: str,
        absolute_path: str,
        images: list[str],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        entries = self._extract_palette_from_text(text)
        if not entries:
            palette_source = next(iter(images or [absolute_path]), absolute_path)
            entries = self._dominant_palette(palette_source)
        classified_lines = self._classified_text_lines(text)
        source_agreement = self._source_agreement(
            classified_lines,
            available_signal_types={"palette"} if entries else set(),
        )
        summary = self._summary_from_parts(
            [
                f"Palette system: {', '.join(self._palette_summary_terms(entries, limit=5))}" if entries else "",
            ],
            limit=240,
        )
        quality = self._analysis_quality(
            text=text,
            summary=summary,
            salient_lines=self._salient_text_lines(
                text,
                keywords=["accent", "color", "palette", "primary", "secondary", "neutral"],
                limit=4,
                allowed_classifications={"visual_system", "unknown"},
            ),
            palette_count=len(entries),
            evidence_types=["palette"],
            classified_lines=classified_lines,
            source_agreement=source_agreement,
        )
        structured = {
            "palette_entries": entries,
            "summary": summary,
            "visual_evidence_units": [
                {
                    "kind": "palette",
                    "summary": f"Palette system: {', '.join(self._palette_summary_terms(entries, limit=5))}",
                    "source": "hybrid" if text.strip() else "image",
                }
            ]
            if entries
            else [],
            "classified_text_lines": classified_lines,
            "analysis_quality": quality,
            "warnings": [] if entries else ["No palette values detected."],
        }
        normalized = {
            "primary": entries[:3],
            "all": entries,
            "summary": summary,
            "visual_evidence_units": structured["visual_evidence_units"],
            "classified_text_lines": classified_lines,
            "analysis_quality": quality,
        }
        return structured, normalized

    def _extract_typography(
        self,
        text: str,
        *,
        absolute_path: str | None = None,
        source_format: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if absolute_path and (source_format in {"ttf", "otf"} or Path(absolute_path).suffix.lower() in {".ttf", ".otf"}):
            return self._extract_typography_from_font_file(absolute_path)
        fonts = self._extract_fonts(text)
        sizes = self._extract_font_sizes(text)
        classified_lines = self._classified_text_lines(text)
        hierarchy = {
            "heading": sizes[:2],
            "body": sizes[2:4],
            "caption": sizes[4:5],
        }
        source_agreement = self._source_agreement(
            classified_lines,
            available_signal_types={
                signal_type
                for signal_type, enabled in {
                    "typography": bool(fonts),
                    "zones": bool(hierarchy["heading"] or hierarchy["body"] or hierarchy["caption"]),
                }.items()
                if enabled
            },
        )
        summary = self._summary_from_parts(
            [
                f"Font families: {', '.join(self._font_summary_terms(fonts, limit=4))}" if fonts else "",
                f"Heading sizes: {', '.join(str(item.get('value')) + str(item.get('unit', '')) for item in hierarchy['heading'])}"
                if hierarchy["heading"]
                else "",
                f"Body sizes: {', '.join(str(item.get('value')) + str(item.get('unit', '')) for item in hierarchy['body'])}"
                if hierarchy["body"]
                else "",
            ],
            limit=260,
        )
        quality = self._analysis_quality(
            text=text,
            summary=summary,
            salient_lines=self._salient_text_lines(
                text,
                keywords=["body", "caption", "font", "heading", "typeface", "typography"],
                limit=4,
                allowed_classifications={"visual_system", "unknown"},
            ),
            font_count=len(fonts),
            evidence_types=["typography", "hierarchy"],
            classified_lines=classified_lines,
            source_agreement=source_agreement,
        )
        structured = {
            "font_families": fonts,
            "style_hierarchy": hierarchy,
            "usage_patterns": {
                "heading": self._search_value(text, r"heading[:\s]+([^\n]+)") or "",
                "body": self._search_value(text, r"body[:\s]+([^\n]+)") or "",
                "caption": self._search_value(text, r"caption[:\s]+([^\n]+)") or "",
            },
            "summary": summary,
            "visual_evidence_units": [
                unit
                for unit in [
                    {
                        "kind": "typography",
                        "summary": f"Font families: {', '.join(self._font_summary_terms(fonts, limit=4))}",
                        "source": "ocr",
                    }
                    if fonts
                    else None,
                    {
                        "kind": "zones",
                        "summary": "Hierarchy: heading, body, caption",
                        "source": "ocr",
                    }
                    if hierarchy["heading"] or hierarchy["body"] or hierarchy["caption"]
                    else None,
                ]
                if isinstance(unit, dict)
            ],
            "classified_text_lines": classified_lines,
            "analysis_quality": quality,
        }
        normalized = structured
        return structured, normalized

    def _extract_typography_from_font_file(self, absolute_path: str) -> tuple[dict[str, Any], dict[str, Any]]:
        font_path = Path(absolute_path)
        family_name = font_path.stem
        style_name = "Regular"
        warning: list[str] = []
        try:
            font = ImageFont.truetype(str(font_path), size=32)
            detected_family, detected_style = font.getname()
            family_name = detected_family or family_name
            style_name = detected_style or style_name
        except Exception as exc:  # noqa: BLE001
            warning.append(f"Font metadata could not be fully parsed: {exc}")

        font_entry = {
            "name": family_name,
            "style": style_name,
            "confidence": 0.99 if not warning else 0.82,
            "source": "uploaded_font_file",
            "filename": font_path.name,
            "exact": not warning,
        }
        summary = self._summary_from_parts(
            [f"Uploaded font family: {family_name}", f"Style: {style_name}"],
            limit=220,
        )
        classified_lines = [
            {
                "line": summary,
                "classification": "visual_system",
                "grounding_allowed": True,
                "signal_types": ["typography"],
                "quality_score": 8.5 if not warning else 6.6,
                "is_asset_label": False,
            }
        ]
        source_agreement = {
            "source_agreement_score": 1.0,
            "source_agreement_types": ["typography"],
            "observed_signal_types": ["typography"],
            "available_signal_types": ["typography"],
            "source_count": 2,
        }
        analysis_quality = {
            "analysis_quality_score": 9.2 if not warning else 7.4,
            "summary_quality_score": 8.8 if not warning else 7.0,
            "ocr_signal_score": 6.0,
            "source_agreement_score": source_agreement["source_agreement_score"],
            "ocr_noise_ratio": 0.0,
            "promotional_line_ratio": 0.0,
            "selected_line_count": 1,
            "candidate_line_count": 1,
            "visual_grounding_line_count": 1,
            "template_copy_line_count": 0,
            "evidence_types": ["typography", "font_file"],
            "source_agreement_types": source_agreement["source_agreement_types"],
            "observed_signal_types": source_agreement["observed_signal_types"],
            "available_signal_types": source_agreement["available_signal_types"],
            "line_classification_counts": {"visual_system": 1},
        }
        visual_evidence_units = [
            {
                "kind": "typography",
                "summary": f"Uploaded font family: {family_name} ({style_name})",
                "source": "font_file",
            }
        ]
        structured = {
            "font_families": [font_entry],
            "style_hierarchy": {},
            "usage_patterns": {
                "heading": family_name,
                "body": family_name,
                "caption": family_name,
            },
            "summary": summary,
            "visual_evidence_units": visual_evidence_units,
            "classified_text_lines": classified_lines,
            "analysis_quality": analysis_quality,
            "warnings": warning,
        }
        normalized = {
            **structured,
            "uploaded_font_file": {
                "filename": font_path.name,
                "family_name": family_name,
                "style_name": style_name,
            },
        }
        return structured, normalized

    def _extract_word_bank(self, text: str, category: str) -> tuple[dict[str, Any], dict[str, Any]]:
        raw_lines = self._interesting_lines(text)
        normalized_terms: list[str] = []
        phrase_map: dict[str, list[str]] = {}
        for line in raw_lines:
            lowered = line.lower()
            if category == BrandAssetCategory.REPLACEABLE_WORD_BANK and ("->" in line or "=>" in line or "replace" in lowered):
                source_text = line
                replacement_text = ""
                if "->" in line:
                    source_text, replacement_text = line.split("->", 1)
                elif "=>" in line:
                    source_text, replacement_text = line.split("=>", 1)
                else:
                    match = re.search(r"(?i)replace\s+(.+?)\s+with\s+(.+)", line)
                    if match:
                        source_text, replacement_text = match.group(1), match.group(2)
                source = re.sub(r"(?i)^replace\s+", "", source_text).strip(" :-").lower()
                replacements = [
                    item.strip(" :-")
                    for item in re.split(r"\band\b|,", replacement_text)
                    if item.strip(" :-")
                ]
                if source and replacements:
                    phrase_map[source] = replacements
                    normalized_terms.append(source)
                    continue
            if len(line.split()) <= 6:
                normalized_terms.append(line.lower())
        deduped = []
        seen = set()
        for term in normalized_terms:
            cleaned = " ".join(term.split()).strip(" ,.;:-")
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)
        structured = {
            "normalized_terms": deduped,
            "phrase_map": phrase_map,
        }
        normalized = structured
        return structured, normalized

    def _extract_other(
        self,
        text: str,
        absolute_path: str,
        images: list[str],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        palette = self._extract_palette_from_text(text) or (self._dominant_palette(next(iter(images or [absolute_path]), absolute_path)))
        fonts = self._extract_fonts(text)
        classified_lines = self._classified_text_lines(text)
        salient_lines = self._salient_text_lines(
            text,
            keywords=["audience", "brand", "color", "font", "layout", "logo", "palette", "style", "visual"],
            limit=4,
            allowed_classifications={"visual_system", "unknown"},
        )
        source_agreement = self._source_agreement(
            classified_lines,
            available_signal_types={
                signal_type
                for signal_type, enabled in {
                    "palette": bool(palette),
                    "typography": bool(fonts),
                }.items()
                if enabled
            },
        )
        summary = self._summary_from_parts(
            [
                *salient_lines,
                f"Palette: {', '.join(self._palette_summary_terms(palette, limit=3))}" if palette else "",
                f"Typography: {', '.join(self._font_summary_terms(fonts, limit=3))}" if fonts else "",
            ],
            limit=320,
        )
        quality = self._analysis_quality(
            text=text,
            summary=summary,
            salient_lines=salient_lines,
            palette_count=len(palette),
            font_count=len(fonts),
            evidence_types=["general_summary", "palette", "typography"],
            classified_lines=classified_lines,
            source_agreement=source_agreement,
        )
        structured = {
            "summary": summary,
            "palette": palette,
            "fonts": fonts,
            "visual_evidence_units": [
                unit
                for unit in [
                    {
                        "kind": "palette",
                        "summary": f"Palette: {', '.join(self._palette_summary_terms(palette, limit=3))}",
                        "source": "hybrid",
                    }
                    if palette
                    else None,
                    {
                        "kind": "typography",
                        "summary": f"Typography: {', '.join(self._font_summary_terms(fonts, limit=3))}",
                        "source": "ocr",
                    }
                    if fonts
                    else None,
                ]
                if isinstance(unit, dict)
            ],
            "classified_text_lines": classified_lines,
            "analysis_quality": quality,
        }
        normalized = structured
        return structured, normalized

    def _derive_reusable_assets(
        self,
        *,
        absolute_path: str,
        routed_category: str,
        structured_data: dict[str, Any],
        normalized_data: dict[str, Any],
        template_analysis: dict[str, Any] | None,
        image_candidates: list[str],
    ) -> list[dict[str, Any]]:
        allowed_suffixes = {".png", ".jpg", ".jpeg", ".webp"}
        candidate_paths: list[str] = []
        seen: set[str] = set()
        for path in [*image_candidates, absolute_path]:
            if not path:
                continue
            resolved = str(Path(path))
            if (
                resolved in seen
                or not Path(resolved).exists()
                or Path(resolved).suffix.lower() not in allowed_suffixes
            ):
                continue
            seen.add(resolved)
            candidate_paths.append(resolved)
        candidate_paths.sort(key=self._natural_sort_key)

        derived_assets: list[dict[str, Any]] = []
        for source_index, source_path in enumerate(candidate_paths):
            visual_analysis = self._load_visual_analysis(source_path)
            crop_regions = self._extract_visual_regions(source_path)
            supplemental_regions = self._extract_sidecar_visual_regions(visual_analysis)
            supplemental_regions.extend(
                self._extract_text_excluded_visual_regions(
                    source_path=source_path,
                    analysis=visual_analysis,
                )
            )
            for supplemental in supplemental_regions:
                supplemental_box = supplemental.get("crop_box")
                if not supplemental_box:
                    continue
                duplicate = False
                for existing in crop_regions:
                    existing_box = existing.get("crop_box")
                    if not existing_box:
                        continue
                    left_a, top_a, right_a, bottom_a = supplemental_box
                    left_b, top_b, right_b, bottom_b = existing_box
                    overlap_left = max(left_a, left_b)
                    overlap_top = max(top_a, top_b)
                    overlap_right = min(right_a, right_b)
                    overlap_bottom = min(bottom_a, bottom_b)
                    overlap_width = max(0, overlap_right - overlap_left)
                    overlap_height = max(0, overlap_bottom - overlap_top)
                    overlap_area = overlap_width * overlap_height
                    area_a = max((right_a - left_a) * (bottom_a - top_a), 1)
                    area_b = max((right_b - left_b) * (bottom_b - top_b), 1)
                    union_area = max(area_a + area_b - overlap_area, 1)
                    if overlap_area / union_area >= 0.72:
                        duplicate = True
                        break
                if not duplicate:
                    crop_regions.append(supplemental)
            if crop_regions:
                for region_index, region in enumerate(crop_regions, start=1):
                    asset_kind = self._classify_reusable_asset_kind(
                        routed_category=routed_category,
                        width=region["width"],
                        height=region["height"],
                        area_ratio=region["area_ratio"],
                        source_index=source_index,
                        source_path=source_path,
                        structured_data=structured_data,
                        template_analysis=template_analysis,
                    )
                    if (
                        asset_kind != "logo_variant"
                        and self._is_text_dominated_crop(region.get("crop_box"), visual_analysis)
                    ):
                        continue
                    if not self._is_reusable_region_eligible(
                        routed_category=routed_category,
                        asset_kind=asset_kind,
                        region=region,
                    ):
                        continue
                    derived_assets.append(
                        self._build_derived_asset_payload(
                            source_path=source_path,
                            routed_category=routed_category,
                            structured_data=structured_data,
                            normalized_data=normalized_data,
                            template_analysis=template_analysis,
                            asset_kind=asset_kind,
                            source_index=source_index,
                            region_index=region_index,
                            crop_box=region["crop_box"],
                            width=region["width"],
                            height=region["height"],
                            area_ratio=region["area_ratio"],
                        )
                    )
                continue

            with open_image_asset(source_path) as image:
                width, height = image.size
            asset_kind = self._classify_reusable_asset_kind(
                routed_category=routed_category,
                width=width,
                height=height,
                area_ratio=1.0,
                source_index=source_index,
                source_path=source_path,
                structured_data=structured_data,
                template_analysis=template_analysis,
            )
            if not self._should_keep_full_image_as_reusable_asset(
                routed_category=routed_category,
                source_path=source_path,
                width=width,
                height=height,
                asset_kind=asset_kind,
            ):
                continue
            derived_assets.append(
                self._build_derived_asset_payload(
                    source_path=source_path,
                    routed_category=routed_category,
                    structured_data=structured_data,
                    normalized_data=normalized_data,
                    template_analysis=template_analysis,
                    asset_kind=asset_kind,
                    source_index=source_index,
                    region_index=1,
                    crop_box=None,
                    width=width,
                    height=height,
                    area_ratio=1.0,
                    )
                )

        derived_assets = self._dedupe_and_rank_derived_assets(derived_assets)
        max_assets = max(16, min(120, len(candidate_paths) * 8))
        return derived_assets[:max_assets]

    @staticmethod
    def _crop_iou(first: tuple[int, int, int, int] | None, second: tuple[int, int, int, int] | None) -> float:
        if not first or not second:
            return 0.0
        left_a, top_a, right_a, bottom_a = first
        left_b, top_b, right_b, bottom_b = second
        overlap_left = max(left_a, left_b)
        overlap_top = max(top_a, top_b)
        overlap_right = min(right_a, right_b)
        overlap_bottom = min(bottom_a, bottom_b)
        overlap_width = max(0, overlap_right - overlap_left)
        overlap_height = max(0, overlap_bottom - overlap_top)
        overlap_area = overlap_width * overlap_height
        if overlap_area <= 0:
            return 0.0
        area_a = max((right_a - left_a) * (bottom_a - top_a), 1)
        area_b = max((right_b - left_b) * (bottom_b - top_b), 1)
        return overlap_area / max(area_a + area_b - overlap_area, 1)

    @classmethod
    def _dedupe_and_rank_derived_assets(cls, derived_assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        def _score(item: dict[str, Any]) -> tuple[float, float, float]:
            metadata = item.get("normalized_metadata") or {}
            review = metadata.get("asset_review") or {}
            dimensions = review.get("dimensions") or {}
            width = float(dimensions.get("width") or item.get("width") or 0)
            height = float(dimensions.get("height") or item.get("height") or 0)
            area = width * height
            confidence = float(item.get("confidence") or 0.0)
            area_ratio = float((item.get("source_metadata") or {}).get("area_ratio") or 0.0)
            return (confidence, area, area_ratio)

        ordered = sorted(derived_assets, key=_score, reverse=True)
        kept: list[dict[str, Any]] = []
        for candidate in ordered:
            crop_box = candidate.get("crop_box")
            label = str(candidate.get("label") or "").strip().casefold()
            source_filename = str((candidate.get("source_metadata") or {}).get("source_filename") or "").strip()
            is_duplicate = False
            for existing in kept:
                if str((existing.get("source_metadata") or {}).get("source_filename") or "").strip() != source_filename:
                    continue
                existing_box = existing.get("crop_box")
                if cls._crop_iou(tuple(crop_box) if crop_box else None, tuple(existing_box) if existing_box else None) < 0.45:
                    if crop_box and existing_box:
                        left_a, top_a, right_a, bottom_a = crop_box
                        left_b, top_b, right_b, bottom_b = existing_box
                        area_a = max((right_a - left_a) * (bottom_a - top_a), 1)
                        area_b = max((right_b - left_b) * (bottom_b - top_b), 1)
                        fully_contained = (
                            left_a >= left_b
                            and top_a >= top_b
                            and right_a <= right_b
                            and bottom_a <= bottom_b
                        )
                        if not (fully_contained and area_b >= (area_a * 2.6)):
                            continue
                        is_duplicate = True
                        break
                    else:
                        continue
                existing_label = str(existing.get("label") or "").strip().casefold()
                if label == existing_label or cls._crop_iou(tuple(crop_box) if crop_box else None, tuple(existing_box) if existing_box else None) >= 0.72:
                    is_duplicate = True
                    break
            if not is_duplicate:
                kept.append(candidate)

        kept.sort(
            key=lambda item: (
                cls._natural_sort_key(str((item.get("source_metadata") or {}).get("source_filename") or "")),
                -float(item.get("confidence") or 0.0),
            )
        )
        return kept

    @staticmethod
    def _is_reusable_region_eligible(
        *,
        routed_category: str,
        asset_kind: str,
        region: dict[str, Any],
    ) -> bool:
        width = int(region.get("width") or 0)
        height = int(region.get("height") or 0)
        area_ratio = float(region.get("area_ratio") or 0.0)
        fill_ratio = float(region.get("fill_ratio") or 0.0)
        touches_border = bool(region.get("touches_border"))
        aspect_ratio = width / max(height, 1)

        if width < 24 or height < 24:
            return False
        if asset_kind == "logo_variant":
            return area_ratio <= 0.55 and fill_ratio >= 0.08
        if asset_kind == "icon":
            return (
                min(width, height) >= 56
                and
                area_ratio <= 0.035
                and fill_ratio >= 0.12
                and not touches_border
                and 0.2 <= aspect_ratio <= 5.0
            )
        if asset_kind == "micro_design_element":
            return (
                area_ratio <= 0.07
                and fill_ratio >= 0.08
                and not (touches_border and area_ratio > 0.05)
                and 0.15 <= aspect_ratio <= 6.0
            )
        if asset_kind in {"decorative_asset", "enhancement_component"}:
            if routed_category not in {BrandAssetCategory.MOOD_BOARD, BrandAssetCategory.LOGO}:
                return False
            return area_ratio <= 0.1 and fill_ratio >= 0.05 and not (touches_border and area_ratio > 0.06)
        return False

    @staticmethod
    def _should_keep_full_image_as_reusable_asset(
        *,
        routed_category: str,
        source_path: str,
        width: int,
        height: int,
        asset_kind: str,
    ) -> bool:
        filename = Path(source_path).name.lower()
        if routed_category == BrandAssetCategory.LOGO:
            return True
        if asset_kind == "logo_variant":
            return width <= 1400 and height <= 1400 and width * height <= 1_200_000
        if routed_category not in {BrandAssetCategory.MOOD_BOARD, BrandAssetCategory.KNOWLEDGE_OTHER}:
            return False
        if asset_kind not in {"icon", "micro_design_element", "decorative_asset"}:
            return False
        if width > 900 or height > 900:
            return False
        if width * height > 420_000:
            return False
        return any(token in filename for token in ("icon", "logo", "badge", "stamp", "symbol", "mark"))

    @staticmethod
    def _expand_crop_box(
        crop_box: tuple[int, int, int, int] | None,
        *,
        source_path: str,
        asset_kind: str,
    ) -> tuple[int, int, int, int] | None:
        if not crop_box:
            return None
        path = Path(source_path)
        if not path.exists():
            return crop_box
        try:
            with open_image_asset(path) as image:
                image_width, image_height = image.size
        except Exception:  # noqa: BLE001
            return crop_box

        left, top, right, bottom = crop_box
        width = max(right - left, 1)
        height = max(bottom - top, 1)
        pad_ratio = 0.12 if asset_kind == "icon" else 0.08
        pad_x = max(10, int(round(width * pad_ratio)))
        pad_y = max(10, int(round(height * pad_ratio)))
        expanded = (
            max(0, left - pad_x),
            max(0, top - pad_y),
            min(image_width, right + pad_x),
            min(image_height, bottom + pad_y),
        )
        return expanded

    @staticmethod
    def _compute_crop_visual_quality(
        source_path: str,
        crop_box: tuple[int, int, int, int] | None,
    ) -> dict[str, float]:
        if not crop_box:
            return {}
        path = Path(source_path)
        if not path.exists():
            return {}
        try:
            with open_image_asset(path) as image:
                crop = image.convert("RGB").crop(crop_box)
                width, height = crop.size
                if width <= 1 or height <= 1:
                    return {}
                target_width = min(width, 160)
                target_height = min(height, 160)
                if (target_width, target_height) != crop.size:
                    crop = crop.resize((target_width, target_height))
                quantized = crop.quantize(colors=6)
                counts = sorted(quantized.getcolors() or [], reverse=True)
        except Exception:  # noqa: BLE001
            return {}

        total = sum(count for count, _ in counts) or 1
        top1_share = (counts[0][0] / total) if counts else 0.0
        top3_share = (sum(count for count, _ in counts[:3]) / total) if counts else 0.0
        return {
            "top1_share": round(float(top1_share), 4),
            "top3_share": round(float(top3_share), 4),
        }

    def _build_derived_asset_payload(
        self,
        *,
        source_path: str,
        routed_category: str,
        structured_data: dict[str, Any],
        normalized_data: dict[str, Any],
        template_analysis: dict[str, Any] | None,
        asset_kind: str,
        source_index: int,
        region_index: int,
        crop_box: tuple[int, int, int, int] | None,
        width: int,
        height: int,
        area_ratio: float,
    ) -> dict[str, Any]:
        palette = self._dominant_palette(source_path)
        expanded_crop_box = self._expand_crop_box(
            crop_box,
            source_path=source_path,
            asset_kind=asset_kind,
        )
        visual_quality = self._compute_crop_visual_quality(
            source_path=source_path,
            crop_box=expanded_crop_box,
        )
        if expanded_crop_box:
            expanded_width = max(expanded_crop_box[2] - expanded_crop_box[0], 1)
            expanded_height = max(expanded_crop_box[3] - expanded_crop_box[1], 1)
        else:
            expanded_width = width
            expanded_height = height
        label = self._derived_asset_label(
            routed_category=routed_category,
            structured_data=structured_data,
            template_analysis=template_analysis,
            asset_kind=asset_kind,
            source_index=source_index,
            region_index=region_index,
            source_path=source_path,
        )
        confidence = round(
            max(
                0.42,
                min(
                    0.94,
                    0.54
                    + (0.12 if crop_box else 0.0)
                    + (0.08 if asset_kind in {"icon", "micro_design_element", "logo_variant"} else 0.0)
                    + (0.06 if palette else 0.0),
                ),
            ),
            2,
        )
        review_payload = self._build_asset_review(
            routed_category=routed_category,
            asset_kind=asset_kind,
            width=expanded_width,
            height=expanded_height,
            area_ratio=area_ratio,
            crop_box=expanded_crop_box,
            confidence=confidence,
            visual_quality=visual_quality,
        )
        return {
            "source_path": source_path,
            "crop_box": list(expanded_crop_box) if expanded_crop_box else None,
            "asset_kind": asset_kind,
            "label": label,
            "width": expanded_width,
            "height": expanded_height,
            "confidence": confidence,
            "source_metadata": {
                "origin_category": routed_category,
                "source_index": source_index,
                "region_index": region_index,
                "source_filename": Path(source_path).name,
                "area_ratio": round(area_ratio, 4),
                "raw_crop_box": list(crop_box) if crop_box else None,
            },
            "normalized_metadata": {
                "palette": palette,
                "visual_quality": visual_quality,
                "render_eligible": review_payload["render_eligible"],
                "template_roles": (template_analysis or {}).get("icons", []),
                "usage_hints": normalized_data.get("usage_metadata", {}),
                "asset_review": review_payload,
                "review_class": review_payload["review_class"],
                "review_status": review_payload["review_status"],
                "review_reason": review_payload["review_reason"],
                **(self._extract_icon_metadata(source_path, label) if asset_kind == "icon" else {}),
            },
        }

    @staticmethod
    def _build_asset_review(
        *,
        routed_category: str,
        asset_kind: str,
        width: int,
        height: int,
        area_ratio: float,
        crop_box: tuple[int, int, int, int] | None,
        confidence: float,
        visual_quality: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        review_class = "fragment"
        review_status = "reference_only"
        review_reason = "Kept only as visual reference."
        visual_quality = visual_quality or {}
        top1_share = float(visual_quality.get("top1_share") or 0.0)
        top3_share = float(visual_quality.get("top3_share") or 0.0)
        clean_graphic = top1_share >= 0.43 and top3_share >= 0.89
        clean_micro_design = top1_share >= 0.5 and top3_share >= 0.89

        if asset_kind == "logo_variant":
            review_class = "logo"
            if confidence >= 0.58 and area_ratio <= 0.65:
                review_status = "approved"
                review_reason = "Logo-like crop approved for brand rendering."
            else:
                review_reason = "Low-confidence logo candidate kept as reference only."
        elif asset_kind == "icon":
            review_class = "icon"
            if crop_box and confidence >= 0.62 and area_ratio <= 0.025 and clean_graphic:
                review_status = "approved"
                review_reason = "Compact icon-like crop approved for rendering."
            else:
                review_reason = "Icon candidate did not meet visual cleanliness requirements."
        elif asset_kind == "micro_design_element":
            review_class = "micro_design"
            max_area_ratio = 0.07 if routed_category == BrandAssetCategory.MOOD_BOARD else 0.045
            if crop_box and confidence >= 0.64 and area_ratio <= max_area_ratio and clean_micro_design:
                review_status = "approved"
                review_reason = "Reusable micro design element approved for rendering."
            else:
                review_reason = "Micro design candidate did not meet visual cleanliness requirements."
        elif asset_kind in {"decorative_asset", "enhancement_component"}:
            review_class = "decorative"
            if (
                routed_category == BrandAssetCategory.MOOD_BOARD
                and crop_box
                and confidence >= 0.7
                and area_ratio <= 0.08
            ):
                review_status = "approved"
                review_reason = "Mood-board decorative asset approved for renderer accents."
            else:
                review_reason = "Decorative asset kept as reference only."
        elif asset_kind == "reference_fragment":
            review_class = "fragment"
            review_status = "reference_only"
            review_reason = "Reference fragment excluded from direct rendering."
        else:
            review_class = "fragment"
            review_status = "excluded"
            review_reason = "Asset did not meet reusable render-asset criteria."

        return {
            "review_class": review_class,
            "review_status": review_status,
            "review_reason": review_reason,
            "render_eligible": review_status == "approved" and review_class in {"logo", "icon", "micro_design", "decorative"},
            "dimensions": {"width": width, "height": height},
            "area_ratio": round(area_ratio, 4),
            "visual_quality": visual_quality,
        }

    def _derived_asset_label(
        self,
        *,
        routed_category: str,
        structured_data: dict[str, Any],
        template_analysis: dict[str, Any] | None,
        asset_kind: str,
        source_index: int,
        region_index: int,
        source_path: str,
    ) -> str:
        label_sources = self._collect_candidate_labels(structured_data, template_analysis)
        stem = Path(source_path).stem.replace("_", " ").replace("-", " ").strip() or "asset"
        if asset_kind == "logo_variant":
            if label_sources:
                offset = min(region_index - 1, len(label_sources) - 1)
                preferred = label_sources[offset][:160]
                if any(token in preferred.casefold() for token in ("logo", "wordmark", "brandmark", "lockup", "emblem", "monogram")):
                    return preferred
                return f"logo variant: {preferred}"[:180]
            return f"logo variant {source_index + 1}.{region_index}: {stem}"[:180]
        if label_sources:
            offset = min(region_index - 1, len(label_sources) - 1)
            return label_sources[offset][:180]
        return f"{asset_kind.replace('_', ' ')} {source_index + 1}.{region_index}: {stem}"[:180]

    @staticmethod
    def _looks_like_asset_label(value: str) -> bool:
        text = " ".join(str(value or "").strip().split())
        if not text:
            return False
        if len(text) > 80:
            return False
        if not re.match(r"^[A-Z0-9]", text):
            return False
        if text[-1] in {".", ",", ";", ":"}:
            return False
        words = re.findall(r"[A-Za-z0-9&#+']+", text)
        if not words or len(words) > 8:
            return False
        if text.upper() == text and len(words) <= 2:
            return False
        lowered = text.casefold()
        if any(token in lowered for token in PROMOTIONAL_COPY_TOKENS):
            return False
        if lowered.startswith(("the ", "a ", "an ")) and len(words) >= 4:
            return False
        if any(token in lowered for token in (" philosophy ", " followed ", " forms ", " used ", " create ", " extended ")):
            return False
        return True

    @staticmethod
    def _collect_candidate_labels(
        structured_data: dict[str, Any],
        template_analysis: dict[str, Any] | None = None,
    ) -> list[str]:
        candidates: list[str] = []

        def _visit(value: Any) -> None:
            if isinstance(value, dict):
                for key, nested in value.items():
                    if key in {"label", "name", "title"}:
                        text = " ".join(str(nested or "").split()).strip()
                        if text:
                            candidates.append(text)
                        continue
                    if key in {"asset_labels", "icon_assets", "micro_design_elements", "decorative_assets", "enhancement_components", "icons", "elements", "assets"}:
                        _visit(nested)
                return
            if isinstance(value, list):
                for item in value:
                    _visit(item)

        _visit(structured_data)
        if template_analysis:
            _visit(template_analysis)

        deduped: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            if not BrandAssetAnalyzer._looks_like_asset_label(item):
                continue
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    @staticmethod
    def _classify_reusable_asset_kind(
        *,
        routed_category: str,
        width: int,
        height: int,
        area_ratio: float,
        source_index: int,
        source_path: str,
        structured_data: dict[str, Any],
        template_analysis: dict[str, Any] | None,
    ) -> str:
        logoish = BrandAssetAnalyzer._looks_like_logo_candidate_source(
            source_path=source_path,
            structured_data=structured_data,
            template_analysis=template_analysis,
        )
        if routed_category == BrandAssetCategory.LOGO:
            return "logo_variant"
        if logoish and width <= 1400 and height <= 1400:
            return "logo_variant"
        aspect_ratio = width / max(height, 1)
        if routed_category == BrandAssetCategory.MOOD_BOARD:
            if area_ratio <= 0.02:
                return "icon"
            if area_ratio <= 0.08:
                return "micro_design_element"
            return "decorative_asset" if aspect_ratio >= 2.2 or aspect_ratio <= 0.45 else "enhancement_component"
        if routed_category in {BrandAssetCategory.REFERENCE_CREATIVE, BrandAssetCategory.TEMPLATE}:
            if area_ratio <= 0.018:
                return "icon"
            if area_ratio <= 0.08:
                return "micro_design_element"
            return "reference_fragment"
        if area_ratio <= 0.035:
            return "icon"
        return "decorative_asset"

    @staticmethod
    def _looks_like_logo_candidate_source(
        *,
        source_path: str,
        structured_data: dict[str, Any],
        template_analysis: dict[str, Any] | None,
    ) -> bool:
        label_sources = BrandAssetAnalyzer._collect_candidate_labels(structured_data, template_analysis)
        combined = " ".join(
            part.casefold()
            for part in [Path(source_path).name, *label_sources]
            if str(part or "").strip()
        )
        return any(token in combined for token in ("logo", "wordmark", "brandmark", "lockup", "emblem", "monogram"))

    def _extract_visual_regions(self, image_path: str) -> list[dict[str, Any]]:
        path = Path(image_path)
        if not path.exists():
            return []
        source = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if source is None:
            return []
        height, width = source.shape[:2]
        if height < 24 or width < 24:
            return []

        scale = min(1.0, 1400 / max(width, height))
        if scale < 1.0:
            resized = cv2.resize(source, (max(int(width * scale), 1), max(int(height * scale), 1)), interpolation=cv2.INTER_AREA)
        else:
            resized = source

        if resized.ndim == 2:
            gray = resized
            alpha = None
            rgb = cv2.cvtColor(resized, cv2.COLOR_GRAY2BGR)
        else:
            channels = resized.shape[2]
            if channels == 4:
                rgb = resized[:, :, :3]
                alpha = resized[:, :, 3]
            else:
                rgb = resized[:, :, :3]
                alpha = None
            gray = cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY)

        if alpha is not None and float(np.count_nonzero(alpha < 250)) / max(alpha.size, 1) > 0.01:
            mask = (alpha > 24).astype(np.uint8) * 255
        else:
            corner_size = max(6, min(resized.shape[0], resized.shape[1]) // 12)
            corner_samples = np.concatenate(
                [
                    rgb[:corner_size, :corner_size].reshape(-1, 3),
                    rgb[:corner_size, -corner_size:].reshape(-1, 3),
                    rgb[-corner_size:, :corner_size].reshape(-1, 3),
                    rgb[-corner_size:, -corner_size:].reshape(-1, 3),
                ],
                axis=0,
            )
            background_color = np.median(corner_samples, axis=0)
            diff = np.linalg.norm(rgb.astype(np.int16) - background_color.astype(np.int16), axis=2)
            mask = np.where((diff > 40) | (gray < 235), 255, 0).astype(np.uint8)

        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            contours = []

        total_area = resized.shape[0] * resized.shape[1]
        raw_regions: list[dict[str, Any]] = []
        regions: list[dict[str, Any]] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            contour_area = float(cv2.contourArea(contour))
            fill_ratio = contour_area / max((w * h), 1)
            area_ratio = (w * h) / max(total_area, 1)
            if w < 12 or h < 12 or area_ratio < 0.00018 or area_ratio > 0.82:
                continue
            raw_regions.append(
                {
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "area_ratio": area_ratio,
                    "fill_ratio": fill_ratio,
                    "contour_area": contour_area,
                }
            )
            if w < 28 or h < 28 or area_ratio < 0.0025:
                continue
            left = int(round(x / scale))
            top = int(round(y / scale))
            right = int(round((x + w) / scale))
            bottom = int(round((y + h) / scale))
            crop_width = max(right - left, 1)
            crop_height = max(bottom - top, 1)
            touches_border = (
                x <= 6
                or y <= 6
                or (x + w) >= (resized.shape[1] - 6)
                or (y + h) >= (resized.shape[0] - 6)
            )
            regions.append(
                {
                    "crop_box": (left, top, right, bottom),
                    "width": crop_width,
                    "height": crop_height,
                    "area_ratio": area_ratio,
                    "fill_ratio": round(fill_ratio, 4),
                    "touches_border": touches_border,
                }
            )

        if not raw_regions:
            try:
                rgb_for_quantize = cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)
                quantized = Image.fromarray(rgb_for_quantize).quantize(colors=10)
                quantized_pixels = np.array(quantized)
                palette_counts = sorted(quantized.getcolors() or [], reverse=True)
                quant_kernel = np.ones((3, 3), np.uint8)
                for count, color_index in palette_counts:
                    coverage = count / max(total_area, 1)
                    if coverage >= 0.42 or coverage <= 0.00035:
                        continue
                    component_mask = np.where(quantized_pixels == color_index, 255, 0).astype(np.uint8)
                    component_mask = cv2.morphologyEx(component_mask, cv2.MORPH_CLOSE, quant_kernel, iterations=1)
                    component_mask = cv2.morphologyEx(component_mask, cv2.MORPH_OPEN, quant_kernel, iterations=1)
                    component_contours, _ = cv2.findContours(component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    for contour in component_contours:
                        x, y, w, h = cv2.boundingRect(contour)
                        contour_area = float(cv2.contourArea(contour))
                        fill_ratio = contour_area / max((w * h), 1)
                        area_ratio = (w * h) / max(total_area, 1)
                        if w < 12 or h < 12 or area_ratio < 0.00018 or area_ratio > 0.5 or fill_ratio < 0.16:
                            continue
                        raw_regions.append(
                            {
                                "x": x,
                                "y": y,
                                "w": w,
                                "h": h,
                                "area_ratio": area_ratio,
                                "fill_ratio": fill_ratio,
                                "contour_area": contour_area,
                            }
                        )
                        if w < 28 or h < 28 or area_ratio < 0.0025:
                            continue
                        left = int(round(x / scale))
                        top = int(round(y / scale))
                        right = int(round((x + w) / scale))
                        bottom = int(round((y + h) / scale))
                        crop_width = max(right - left, 1)
                        crop_height = max(bottom - top, 1)
                        touches_border = (
                            x <= 6
                            or y <= 6
                            or (x + w) >= (resized.shape[1] - 6)
                            or (y + h) >= (resized.shape[0] - 6)
                        )
                        regions.append(
                            {
                                "crop_box": (left, top, right, bottom),
                                "width": crop_width,
                                "height": crop_height,
                                "area_ratio": area_ratio,
                                "fill_ratio": round(fill_ratio, 4),
                                "touches_border": touches_border,
                            }
                        )
            except Exception:  # noqa: BLE001
                pass

        def _boxes_connect(first: dict[str, Any], second: dict[str, Any]) -> bool:
            first_pad = max(18, int(min(max(first["w"], first["h"]), 220) * 0.4))
            second_pad = max(18, int(min(max(second["w"], second["h"]), 220) * 0.4))
            left_a = first["x"] - first_pad
            top_a = first["y"] - first_pad
            right_a = first["x"] + first["w"] + first_pad
            bottom_a = first["y"] + first["h"] + first_pad
            left_b = second["x"] - second_pad
            top_b = second["y"] - second_pad
            right_b = second["x"] + second["w"] + second_pad
            bottom_b = second["y"] + second["h"] + second_pad
            return not (
                right_a < left_b
                or right_b < left_a
                or bottom_a < top_b
                or bottom_b < top_a
            )

        clusters: list[list[dict[str, Any]]] = []
        visited: set[int] = set()
        for index, region in enumerate(raw_regions):
            if index in visited:
                continue
            queue = [index]
            visited.add(index)
            cluster_indices = [index]
            while queue:
                current_index = queue.pop()
                current = raw_regions[current_index]
                for candidate_index, candidate in enumerate(raw_regions):
                    if candidate_index in visited:
                        continue
                    if _boxes_connect(current, candidate):
                        visited.add(candidate_index)
                        queue.append(candidate_index)
                        cluster_indices.append(candidate_index)
            if len(cluster_indices) <= 1:
                continue
            cluster = [raw_regions[item] for item in cluster_indices]
            total_cluster_contour_area = sum(float(item.get("contour_area") or 0.0) for item in cluster)
            min_x = min(int(item["x"]) for item in cluster)
            min_y = min(int(item["y"]) for item in cluster)
            max_x = max(int(item["x"] + item["w"]) for item in cluster)
            max_y = max(int(item["y"] + item["h"]) for item in cluster)
            width = max_x - min_x
            height = max_y - min_y
            cluster_area_ratio = (width * height) / max(total_area, 1)
            if width < 28 or height < 28 or cluster_area_ratio < 0.002 or cluster_area_ratio > 0.3:
                continue
            fill_ratio = total_cluster_contour_area / max(width * height, 1)
            left = int(round(min_x / scale))
            top = int(round(min_y / scale))
            right = int(round(max_x / scale))
            bottom = int(round(max_y / scale))
            crop_width = max(right - left, 1)
            crop_height = max(bottom - top, 1)
            touches_border = (
                min_x <= 6
                or min_y <= 6
                or max_x >= (resized.shape[1] - 6)
                or max_y >= (resized.shape[0] - 6)
            )
            clusters.append(
                {
                    "crop_box": (left, top, right, bottom),
                    "width": crop_width,
                    "height": crop_height,
                    "area_ratio": cluster_area_ratio,
                    "fill_ratio": round(fill_ratio, 4),
                    "touches_border": touches_border,
                }
            )

        def _iou(first: dict[str, Any], second: dict[str, Any]) -> float:
            left_a, top_a, right_a, bottom_a = first["crop_box"]
            left_b, top_b, right_b, bottom_b = second["crop_box"]
            overlap_left = max(left_a, left_b)
            overlap_top = max(top_a, top_b)
            overlap_right = min(right_a, right_b)
            overlap_bottom = min(bottom_a, bottom_b)
            overlap_width = max(0, overlap_right - overlap_left)
            overlap_height = max(0, overlap_bottom - overlap_top)
            overlap_area = overlap_width * overlap_height
            if overlap_area <= 0:
                return 0.0
            first_area = max((right_a - left_a) * (bottom_a - top_a), 1)
            second_area = max((right_b - left_b) * (bottom_b - top_b), 1)
            return overlap_area / max(first_area + second_area - overlap_area, 1)

        for cluster in clusters:
            if any(_iou(cluster, existing) >= 0.78 for existing in regions):
                continue
            regions.append(cluster)

        regions.sort(key=lambda item: item["area_ratio"], reverse=True)
        deduped_regions: list[dict[str, Any]] = []
        for region in regions:
            left, top, right, bottom = region["crop_box"]
            region_area = max((right - left) * (bottom - top), 1)
            contained = False
            for existing in deduped_regions:
                existing_left, existing_top, existing_right, existing_bottom = existing["crop_box"]
                overlap_left = max(left, existing_left)
                overlap_top = max(top, existing_top)
                overlap_right = min(right, existing_right)
                overlap_bottom = min(bottom, existing_bottom)
                overlap_width = max(0, overlap_right - overlap_left)
                overlap_height = max(0, overlap_bottom - overlap_top)
                overlap_area = overlap_width * overlap_height
                existing_area = max((existing_right - existing_left) * (existing_bottom - existing_top), 1)
                if overlap_area / region_area >= 0.9 and existing_area >= (region_area * 2.2):
                    contained = True
                    break
            if contained:
                continue
            deduped_regions.append(region)

        regions = deduped_regions
        regions.sort(key=lambda item: item["area_ratio"], reverse=True)
        return regions[:8]

    @staticmethod
    def _interesting_lines(text: str) -> list[str]:
        if not text:
            return []
        lines = []
        for raw_line in text.splitlines():
            line = " ".join(raw_line.strip().split())
            if len(line) < 3:
                continue
            if re.fullmatch(r"[#=\-\s]+", line):
                continue
            lines.append(line)
        return lines

    @staticmethod
    def _extract_bucketed_items(lines: list[str], keywords: list[str], *, require_asset_label: bool = True) -> list[str]:
        items: list[str] = []
        seen: set[str] = set()
        for line in lines:
            lowered = line.lower()
            if keywords and not any(keyword in lowered for keyword in keywords):
                continue
            cleaned = re.sub(r"^[\-\d\.\)\s]+", "", line).strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            if require_asset_label and keywords and not BrandAssetAnalyzer._looks_like_asset_label(cleaned):
                continue
            seen.add(key)
            items.append(cleaned[:180])
            if len(items) >= 10:
                break
        return items

    @staticmethod
    def _dedupe_preserving_order(items: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            text = BrandAssetAnalyzer._normalize_summary_fragment(item, limit=220)
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(text)
        return deduped

    @classmethod
    def _audience_section_from_text(cls, value: str, *, strict: bool = True) -> str | None:
        cleaned = cls._normalize_summary_fragment(value, limit=96).casefold()
        cleaned = re.sub(r"^[\-\d\.\)\s]+", "", cleaned).strip(" :-")
        if not cleaned:
            return None
        for field, spec in AUDIENCE_EVIDENCE_FIELD_SPECS.items():
            for alias in spec["aliases"]:
                normalized_alias = str(alias or "").strip().casefold()
                if not normalized_alias:
                    continue
                if cleaned == normalized_alias:
                    return field
                if strict and cleaned.startswith(f"{normalized_alias} "):
                    return field
                if not strict and re.search(rf"\b{re.escape(normalized_alias)}\b", cleaned):
                    return field
        return None

    @classmethod
    def _audience_keyword_hits(cls, text: str, keywords: tuple[str, ...] | list[str]) -> list[str]:
        lowered = cls._normalize_summary_fragment(text, limit=220).casefold()
        hits: list[str] = []
        for keyword in keywords:
            normalized_keyword = str(keyword or "").strip().casefold()
            if not normalized_keyword:
                continue
            if len(normalized_keyword) <= 3 and " " not in normalized_keyword:
                matched = bool(re.search(rf"\b{re.escape(normalized_keyword)}\b", lowered))
            else:
                matched = bool(re.search(rf"\b{re.escape(normalized_keyword)}\b", lowered)) if " " not in normalized_keyword else normalized_keyword in lowered
            if matched:
                hits.append(normalized_keyword)
        return hits

    @classmethod
    def _looks_like_audience_statement(cls, value: str) -> bool:
        cleaned = cls._normalize_summary_fragment(value, limit=220)
        if not cleaned:
            return False
        words = re.findall(r"[A-Za-z0-9#&+'/-]+", cleaned)
        alpha_words = [word for word in words if re.search(r"[A-Za-z]", word)]
        if ":" in cleaned or len(alpha_words) >= 6:
            return True
        lowered_words = {word.casefold() for word in alpha_words}
        return bool(lowered_words & AUDIENCE_STATEMENT_VERBS)

    @classmethod
    def _audience_line_entries(cls, text: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        current_section: str | None = None
        current_section_index = -999
        for index, raw_line in enumerate(cls._interesting_lines(text)):
            cleaned = cls._normalize_summary_fragment(
                re.sub(r"^[\-\u2022\d\.\)\s]+", "", raw_line),
                limit=220,
            )
            if not cleaned:
                continue
            inline_section: str | None = None
            inline_value = ""
            if ":" in cleaned:
                label, value = cleaned.split(":", 1)
                inline_section = cls._audience_section_from_text(label, strict=True)
                inline_value = cls._normalize_summary_fragment(value, limit=180)
                if inline_section and not inline_value:
                    current_section = inline_section
                    current_section_index = index
                    continue
            if inline_section is None:
                header_section = cls._audience_section_from_text(cleaned, strict=True)
                if header_section and len(cleaned.split()) <= 6 and len(cleaned) <= 72:
                    current_section = header_section
                    current_section_index = index
                    continue
            inherited_section = current_section if current_section and (index - current_section_index) <= 6 else None
            classification = cls._classify_text_line(cleaned)
            entries.append(
                {
                    "line": cleaned,
                    "value": inline_value or cleaned,
                    "section": inline_section or inherited_section,
                    "section_source": "inline_label" if inline_section else "section_header" if inherited_section else "keyword",
                    "classification": str(classification.get("classification") or "unknown"),
                    "quality_score": float(classification.get("quality_score") or cls._line_quality_score(cleaned)),
                    "line_index": index,
                }
            )
            if inline_section:
                current_section = inline_section
                current_section_index = index
        return entries

    @classmethod
    def _audience_evidence_confidence(
        cls,
        entry: dict[str, Any],
        *,
        section_match: bool,
        keyword_hits: list[str],
    ) -> float:
        confidence = 0.18
        if section_match:
            confidence += 0.28
        section_source = str(entry.get("section_source") or "")
        if section_source == "inline_label":
            confidence += 0.28
        elif section_source == "section_header":
            confidence += 0.22
        if keyword_hits:
            confidence += min(0.18, len(keyword_hits) * 0.08)
        if len(keyword_hits) >= 2:
            confidence += 0.12
        confidence += min(0.22, max(float(entry.get("quality_score") or 0.0), 0.0) * 0.04)
        classification = str(entry.get("classification") or "unknown")
        if classification in AUDIENCE_DISALLOWED_CLASSIFICATIONS:
            confidence -= 0.24
        if section_source == "keyword" and not cls._looks_like_audience_statement(str(entry.get("line") or "")):
            confidence -= 0.2
        if section_source == "keyword" and len(str(entry.get("value") or "").split()) < 6:
            confidence -= 0.12
        return round(max(0.0, min(confidence, 0.98)), 2)

    @classmethod
    def _extract_audience_evidence(
        cls,
        entries: list[dict[str, Any]],
        field: str,
    ) -> list[dict[str, Any]]:
        spec = AUDIENCE_EVIDENCE_FIELD_SPECS.get(field, {})
        keywords = tuple(spec.get("keywords") or ())
        min_confidence = float(spec.get("min_confidence") or 0.62)
        max_items = int(spec.get("max_items") or 5)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in entries:
            section = str(entry.get("section") or "").strip()
            section_match = section == field
            if section and not section_match:
                continue
            keyword_hits = cls._audience_keyword_hits(str(entry.get("line") or ""), keywords)
            if not section_match and not keyword_hits:
                continue
            confidence = cls._audience_evidence_confidence(
                entry,
                section_match=section_match,
                keyword_hits=keyword_hits,
            )
            if confidence < min_confidence:
                continue
            value = cls._normalize_summary_fragment(entry.get("value"), limit=180)
            snippet = cls._normalize_summary_fragment(entry.get("line"), limit=220)
            if not value or not snippet:
                continue
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "value": value,
                    "source_snippet": snippet,
                    "section": field,
                    "match_mode": str(entry.get("section_source") or "keyword"),
                    "matched_keywords": keyword_hits[:4],
                    "confidence": confidence,
                }
            )
            if len(items) >= max_items:
                break
        return items

    @staticmethod
    def _normalize_summary_fragment(value: Any, limit: int = 96) -> str:
        text = " ".join(str(value or "").strip().split())
        if not text:
            return ""
        return text[:limit].rstrip(" ,.;:")

    @classmethod
    def _palette_summary_terms(cls, entries: list[dict[str, Any]] | None, *, limit: int = 4) -> list[str]:
        if not isinstance(entries, list):
            return []
        results: list[str] = []
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            role = cls._normalize_summary_fragment(entry.get("role"), limit=20)
            color = cls._normalize_summary_fragment(entry.get("hex_code") or entry.get("color_name"), limit=20)
            label = " ".join(part for part in (role, color) if part).strip()
            if not label:
                continue
            key = label.casefold()
            if key in seen:
                continue
            seen.add(key)
            results.append(label)
            if len(results) >= limit:
                break
        return results

    @classmethod
    def _font_summary_terms(cls, fonts: list[dict[str, Any]] | None, *, limit: int = 4) -> list[str]:
        if not isinstance(fonts, list):
            return []
        results: list[str] = []
        seen: set[str] = set()
        for entry in fonts:
            if not isinstance(entry, dict):
                continue
            text = cls._normalize_summary_fragment(entry.get("name"), limit=40)
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            results.append(text)
            if len(results) >= limit:
                break
        return results

    @classmethod
    def _zone_summary_terms(cls, zones: list[dict[str, Any]] | None, *, limit: int = 5) -> list[str]:
        if not isinstance(zones, list):
            return []
        results: list[str] = []
        seen: set[str] = set()
        for entry in zones:
            if not isinstance(entry, dict):
                continue
            text = cls._normalize_summary_fragment(entry.get("role") or entry.get("zone_id"), limit=32)
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            results.append(text)
            if len(results) >= limit:
                break
        return results

    @classmethod
    def _summary_from_parts(cls, parts: list[str], *, limit: int = 320) -> str:
        cleaned: list[str] = []
        seen: set[str] = set()
        for part in parts:
            text = cls._normalize_summary_fragment(part, limit=limit)
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(text)
        summary = ". ".join(cleaned)
        return summary[:limit].rstrip(" ,.;:")

    @classmethod
    def _template_copy_lines(cls, *values: Any, limit: int = 4) -> list[str]:
        lines: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = cls._normalize_summary_fragment(value, limit=140)
            if not text or len(text.split()) < 2:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            lines.append(text)
            if len(lines) >= limit:
                break
        return lines

    @classmethod
    def _line_signal_types(cls, line: str) -> list[str]:
        lowered = cls._normalize_summary_fragment(line, limit=220).casefold()
        if not lowered:
            return []
        signal_types = [
            signal_type
            for signal_type, keywords in SIGNAL_TYPE_KEYWORDS.items()
            if any(keyword in lowered for keyword in keywords)
        ]
        return sorted(dict.fromkeys(signal_types))

    @classmethod
    def _classify_text_line(cls, line: str) -> dict[str, Any]:
        cleaned = cls._normalize_summary_fragment(line, limit=220)
        if not cleaned:
            return {
                "line": "",
                "classification": "noise",
                "grounding_allowed": False,
                "signal_types": [],
                "quality_score": -999.0,
                "is_asset_label": False,
            }
        lowered = cleaned.casefold()
        words = re.findall(r"[A-Za-z0-9#&+'/-]+", cleaned)
        alpha_words = [word for word in words if re.search(r"[A-Za-z]", word)]
        specimen_markers = [token for token in alpha_words if token.lower() in FONT_SPECIMEN_MARKERS]
        uppercase_words = [word for word in words if word.isupper() and len(word) > 1]
        signal_types = cls._line_signal_types(cleaned)
        quality_score = cls._line_quality_score(cleaned)
        is_asset_label = cls._looks_like_asset_label(cleaned)
        zone_value_match = re.search(r"\b(header|headline|footer|cta|body|caption)\b\s*:\s*(.+)", lowered)
        zone_value_pattern = bool(zone_value_match)
        zone_value_text = str(zone_value_match.group(2) or "").strip() if zone_value_match else ""
        zone_value_words = re.findall(r"[A-Za-z0-9#&+'/-]+", zone_value_text)
        zone_value_alpha_words = [word for word in zone_value_words if re.search(r"[A-Za-z]", word)]
        zone_label = str(zone_value_match.group(1) or "").strip() if zone_value_match else ""
        style_spec_tokens = {
            "align",
            "bold",
            "color",
            "font",
            "grid",
            "hex",
            "italic",
            "layout",
            "manrope",
            "palette",
            "regular",
            "semibold",
            "size",
            "spacing",
            "style",
            "typography",
            "weight",
        }
        zone_value_looks_like_copy = bool(
            zone_value_pattern
            and zone_value_alpha_words
            and not any(token in zone_value_text for token in style_spec_tokens)
            and not re.search(r"#(?:[0-9a-f]{3}){1,2}\b|\b\d{1,3}px\b", zone_value_text)
            and len(zone_value_alpha_words) >= (2 if zone_label == "cta" else 4)
        )
        label = "unknown"
        if re.search(r"https?://|www\.|@[A-Za-z0-9_]+", cleaned) or len(alpha_words) < 2 or quality_score < -1.0:
            label = "noise"
        elif (
            FONT_SPECIMEN_PHRASE_PATTERN.search(cleaned)
            and len(specimen_markers) >= 2
        ) or SINGLE_LETTER_RUN_PATTERN.search(cleaned) or (
            len(specimen_markers) >= 3 and len(uppercase_words) >= max(4, len(words) // 2)
        ):
            label = "specimen"
        elif any(token in lowered for token in LEGAL_COPY_TOKENS):
            label = "legal"
        elif any(token in lowered for token in PROMOTIONAL_COPY_TOKENS):
            label = "cta_copy"
        elif zone_value_looks_like_copy:
            label = "template_copy"
        elif signal_types and (is_asset_label or quality_score >= 2.0):
            label = "visual_system"
        elif is_asset_label and len(alpha_words) >= 2:
            label = "visual_system"
        elif len(alpha_words) < 4:
            label = "noise"
        grounding_allowed = label == "visual_system"
        return {
            "line": cleaned,
            "classification": label,
            "grounding_allowed": grounding_allowed,
            "signal_types": signal_types,
            "quality_score": round(quality_score, 4),
            "is_asset_label": is_asset_label,
        }

    @classmethod
    def _classified_text_lines(cls, text: str, *, limit: int = 24) -> list[dict[str, Any]]:
        classified: list[dict[str, Any]] = []
        seen: set[str] = set()
        for line in cls._interesting_lines(text):
            item = cls._classify_text_line(line)
            cleaned = str(item.get("line") or "").strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            classified.append(item)
            if len(classified) >= limit:
                break
        return classified

    @staticmethod
    def _line_classification_counts(classified_lines: list[dict[str, Any]]) -> dict[str, int]:
        counts = Counter(
            str(item.get("classification") or "unknown")
            for item in classified_lines
            if isinstance(item, dict)
        )
        return {key: int(value) for key, value in sorted(counts.items()) if value}

    @classmethod
    def _source_agreement(
        cls,
        classified_lines: list[dict[str, Any]],
        *,
        available_signal_types: set[str] | None = None,
    ) -> dict[str, Any]:
        available = {
            str(signal_type or "").strip()
            for signal_type in (available_signal_types or set())
            if str(signal_type or "").strip()
        }
        observed = {
            signal_type
            for item in classified_lines
            if isinstance(item, dict) and item.get("grounding_allowed")
            for signal_type in (item.get("signal_types") or [])
            if str(signal_type or "").strip()
        }
        matched = observed & available
        union = observed | available
        if not observed or not available or not union:
            score = 0.0
        else:
            score = len(matched) / max(len(union), 1)
        return {
            "source_agreement_score": round(max(0.0, min(score, 1.0)), 4),
            "source_agreement_types": sorted(matched),
            "observed_signal_types": sorted(observed),
            "available_signal_types": sorted(available),
            "source_count": int(bool(observed)) + int(bool(available)),
        }

    @classmethod
    def _line_quality_score(
        cls,
        line: str,
        *,
        keywords: list[str] | None = None,
        prefer_label: bool = False,
    ) -> float:
        cleaned = cls._normalize_summary_fragment(line, limit=220)
        if not cleaned:
            return -999.0
        lowered = cleaned.casefold()
        words = re.findall(r"[A-Za-z0-9#&+'/-]+", cleaned)
        alpha_words = [word for word in words if re.search(r"[A-Za-z]", word)]
        if len(alpha_words) < 2:
            return -999.0
        score = 0.0
        score += min(len(alpha_words), 10) * 0.38
        score += (len({word.casefold() for word in alpha_words}) / max(len(alpha_words), 1)) * 1.5
        if 2 <= len(alpha_words) <= 14:
            score += 0.8
        if ":" in cleaned:
            score += 0.45
        if keywords and any(keyword in lowered for keyword in keywords):
            score += 2.6
        if any(token in lowered for token in VISUAL_SYSTEM_TOKENS):
            score += 0.7
        if cls._looks_like_asset_label(cleaned):
            score += 1.2 if prefer_label else 0.6
        digit_count = sum(character.isdigit() for character in cleaned)
        alpha_count = sum(character.isalpha() for character in cleaned)
        if digit_count and digit_count > alpha_count * 0.45:
            score -= 2.1
        if len(cleaned.split()) > 20:
            score -= 2.8
        if len(cleaned) > 180:
            score -= 1.6
        if any(token in lowered for token in PROMOTIONAL_COPY_TOKENS):
            score -= 2.4
        if re.search(r"https?://|www\.|@[A-Za-z0-9_]+", cleaned):
            score -= 2.5
        uppercase_words = [word for word in words if word.isupper() and len(word) > 1]
        if len(uppercase_words) >= max(4, len(words) // 2):
            score -= 1.8
        return round(score, 4)

    @classmethod
    def _salient_text_lines(
        cls,
        text: str,
        *,
        keywords: list[str] | None = None,
        limit: int = 4,
        prefer_labels: bool = False,
        minimum_score: float = 2.2,
        allowed_classifications: set[str] | None = None,
    ) -> list[str]:
        lines = cls._interesting_lines(text)
        scored: list[tuple[float, int, str]] = []
        for index, line in enumerate(lines):
            cleaned = cls._normalize_summary_fragment(line, limit=220)
            if not cleaned:
                continue
            classified = cls._classify_text_line(cleaned)
            if allowed_classifications and str(classified.get("classification") or "") not in allowed_classifications:
                continue
            score = cls._line_quality_score(
                cleaned,
                keywords=keywords,
                prefer_label=prefer_labels,
            )
            if score < minimum_score:
                continue
            scored.append((score, index, cleaned))
        if not scored and keywords:
            return cls._salient_text_lines(
                text,
                keywords=None,
                limit=limit,
                prefer_labels=prefer_labels,
                minimum_score=max(1.6, minimum_score - 0.6),
                allowed_classifications=allowed_classifications,
            )
        selected = sorted(sorted(scored, key=lambda item: item[0], reverse=True)[:limit], key=lambda item: item[1])
        deduped: list[str] = []
        seen: set[str] = set()
        for _, _, line in selected:
            key = line.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(line)
        return deduped

    @classmethod
    def _analysis_quality(
        cls,
        *,
        text: str,
        summary: str,
        salient_lines: list[str],
        palette_count: int = 0,
        font_count: int = 0,
        zone_count: int = 0,
        label_count: int = 0,
        evidence_types: list[str] | None = None,
        classified_lines: list[dict[str, Any]] | None = None,
        source_agreement: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        candidate_lines = cls._interesting_lines(text)
        classified = classified_lines or cls._classified_text_lines(text)
        classification_counts = cls._line_classification_counts(classified)
        candidate_count = len(candidate_lines)
        selected_count = len(salient_lines)
        noise_ratio = 0.0 if candidate_count <= 0 else max(0.0, min(1.0, 1.0 - (selected_count / candidate_count)))
        promotional_lines = int(classification_counts.get("cta_copy", 0))
        promotional_ratio = 0.0 if candidate_count <= 0 else min(promotional_lines / candidate_count, 1.0)
        summary_words = len(summary.split())
        normalized_evidence = [item for item in dict.fromkeys((evidence_types or [])) if item]
        agreement = source_agreement or {}
        source_agreement_score = max(0.0, min(float(agreement.get("source_agreement_score") or 0.0), 1.0))
        source_agreement_types = [
            str(item or "").strip()
            for item in (agreement.get("source_agreement_types") or [])
            if str(item or "").strip()
        ]
        visual_grounding_line_count = int(classification_counts.get("visual_system", 0))
        template_copy_line_count = int(classification_counts.get("template_copy", 0))
        specimen_line_count = int(classification_counts.get("specimen", 0))
        legal_line_count = int(classification_counts.get("legal", 0))
        signal_volume = selected_count + min(palette_count, 4) + min(font_count, 3) + min(zone_count, 4) + min(label_count, 4)
        analysis_score = 1.8 + min(signal_volume, 8) * 0.78 + min(len(normalized_evidence), 5) * 0.55
        analysis_score += min(summary_words, 28) / 12
        analysis_score += source_agreement_score * 2.8
        analysis_score += min(visual_grounding_line_count, 4) * 0.35
        analysis_score -= noise_ratio * 2.2
        analysis_score -= promotional_ratio * 4.0
        analysis_score -= min(template_copy_line_count, 4) * 0.3
        analysis_score -= min(specimen_line_count, 4) * 0.45
        analysis_score -= min(legal_line_count, 3) * 0.25
        summary_score = 1.5 + min(selected_count, 4) * 1.05 + min(len(normalized_evidence), 4) * 0.7
        summary_score += min(summary_words, 24) / 10
        summary_score += source_agreement_score * 2.1
        summary_score -= promotional_ratio * 4.0
        ocr_signal = (
            1.0
            + min(selected_count, 5) * 1.2
            + min(len(normalized_evidence), 5) * 0.55
            + (source_agreement_score * 1.8)
            - (noise_ratio * 1.2)
            - (promotional_ratio * 2.0)
        )
        return {
            "analysis_quality_score": round(max(0.0, min(analysis_score, 10.0)), 2),
            "summary_quality_score": round(max(0.0, min(summary_score, 10.0)), 2),
            "ocr_signal_score": round(max(0.0, min(ocr_signal, 10.0)), 2),
            "ocr_noise_ratio": round(noise_ratio, 4),
            "promotional_line_ratio": round(promotional_ratio, 4),
            "selected_line_count": selected_count,
            "candidate_line_count": candidate_count,
            "evidence_types": normalized_evidence,
            "line_classification_counts": classification_counts,
            "visual_grounding_line_count": visual_grounding_line_count,
            "template_copy_line_count": template_copy_line_count,
            "source_agreement_score": round(source_agreement_score, 4),
            "source_agreement_types": source_agreement_types,
            "observed_signal_types": [
                str(item or "").strip()
                for item in (agreement.get("observed_signal_types") or [])
                if str(item or "").strip()
            ],
            "available_signal_types": [
                str(item or "").strip()
                for item in (agreement.get("available_signal_types") or [])
                if str(item or "").strip()
            ],
            "source_count": int(agreement.get("source_count") or 0),
        }

    @staticmethod
    def _extract_key_value_pairs(lines: list[str], keys: list[str]) -> dict[str, str]:
        values: dict[str, str] = {}
        for line in lines:
            lowered = line.lower()
            for key in keys:
                if key not in lowered:
                    continue
                if ":" in line:
                    _, value = line.split(":", 1)
                    values[key] = value.strip()[:200]
                else:
                    values[key] = line[:200]
        return values

    @staticmethod
    def _search_value(text: str, pattern: str) -> str | None:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            return None
        return " ".join(match.group(1).split()).strip()

    @staticmethod
    def _guess_tagline(text: str) -> str | None:
        for line in text.splitlines():
            clean = " ".join(line.split()).strip()
            if 12 <= len(clean) <= 90 and "'" in clean:
                return clean
        return None

    @staticmethod
    def _guess_heading(text: str) -> str | None:
        for line in text.splitlines():
            clean = " ".join(line.split()).strip()
            if 8 <= len(clean) <= 120 and len(clean.split()) <= 14:
                return clean
        return None

    @staticmethod
    def _guess_cta(text: str) -> str | None:
        candidates = re.findall(r"(learn more|apply now|talk to us|get started|book now|download now)", text, flags=re.IGNORECASE)
        return candidates[0].title() if candidates else None

    @staticmethod
    def _has_tokens(text: str, tokens: list[str]) -> bool:
        lowered = text.lower()
        return any(token in lowered for token in tokens)

    @staticmethod
    def _extract_fonts(text: str) -> list[dict[str, Any]]:
        detected: list[dict[str, Any]] = []
        for family in COMMON_FONT_FAMILIES:
            if family.lower() in text.lower():
                detected.append({"name": family, "confidence": 0.88, "source": "text_match"})
        explicit = re.findall(
            r"(?i)(?:font|typeface|typography|heading font|body font)\s*[:\-]\s*([A-Za-z][A-Za-z0-9 &\-]{2,40})",
            text,
        )
        for item in explicit:
            cleaned = " ".join(item.split()).strip()
            if not cleaned:
                continue
            if any(existing["name"].lower() == cleaned.lower() for existing in detected):
                continue
            detected.append({"name": cleaned, "confidence": 0.74, "source": "explicit_label"})
        return detected[:8]

    @staticmethod
    def _extract_font_sizes(text: str) -> list[dict[str, Any]]:
        sizes = re.findall(r"(\d{1,3})\s*(?:pt|px)", text, flags=re.IGNORECASE)
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for size in sizes:
            if size in seen:
                continue
            seen.add(size)
            result.append({"value": int(size), "unit": "pt"})
        return result[:8]

    @staticmethod
    def _extract_gradients(text: str) -> list[dict[str, Any]]:
        gradients = re.findall(r"(?i)(linear gradient|radial gradient|gradient)", text)
        deduped = list(dict.fromkeys(item.lower() for item in gradients))
        return [
            {
                "type": "linear" if "linear" in item else ("radial" if "radial" in item else "gradient"),
                "direction": "unspecified",
                "source": "text_hint",
                "confidence": 0.46,
            }
            for item in deduped
        ]

    def _extract_palette_from_text(self, text: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        seen: set[str] = set()
        lowered = text.lower()
        for match in re.finditer(r"#[0-9a-fA-F]{6}", text):
            key = match.group(0).upper()
            if key in seen:
                continue
            seen.add(key)
            context = lowered[max(0, match.start() - 120): min(len(lowered), match.end() + 80)]
            entries.append(
                {
                    "role": self._infer_palette_role(context, key),
                    "hex_code": key,
                    "color_name": None,
                    "source": "text_hex",
                }
            )
        token_matches = list(re.finditer(r"[A-Za-z]+", lowered))
        token_counts = Counter(match.group(0) for match in token_matches)
        for match in token_matches:
            token = match.group(0)
            count = token_counts[token]
            if token not in COMMON_COLOR_NAMES or count < 1:
                continue
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            context = lowered[max(0, match.start() - 60): min(len(lowered), match.end() + 60)]
            entries.append(
                {
                    "role": self._infer_palette_role(context, token),
                    "hex_code": token,
                    "color_name": token.title(),
                    "source": "text_color_name",
                }
            )
        entries = self._rebalance_palette_roles(entries, lowered)
        return entries[:10]

    @staticmethod
    def _infer_palette_role(text: str, token: str) -> str:
        lowered = text.lower()
        semantic_window = f"{lowered} {token.lower()}".strip()
        if any(keyword in semantic_window for keyword in ("orange", "peel", "amber", "yellow", "gold")):
            return "secondary"
        if any(keyword in semantic_window for keyword in ("green", "mint", "teal", "caribbean")):
            return "secondary"
        if any(keyword in semantic_window for keyword in ("blue", "navy", "regal", "governor")):
            return "primary"
        if any(keyword in semantic_window for keyword in ("sand", "grey", "gray", "heart", "neutral")):
            return "neutral"

        role_hits = {
            role: max(
                lowered.rfind(role),
                lowered.rfind(f"{role} color"),
            )
            for role in ("primary", "secondary", "accent", "neutral")
        }
        best_role = max(role_hits.items(), key=lambda item: item[1])
        if best_role[1] >= 0:
            return best_role[0]
        return "accent"

    def _rebalance_palette_roles(self, entries: list[dict[str, Any]], lowered_text: str) -> list[dict[str, Any]]:
        hex_entries = [
            entry for entry in entries
            if isinstance(entry, dict) and str(entry.get("hex_code", "")).startswith("#")
        ]
        if len(hex_entries) < 3:
            return entries
        if "primary color" not in lowered_text and "secondary color" not in lowered_text:
            return entries

        def _rgb(hex_code: str) -> tuple[int, int, int] | None:
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", hex_code):
                return None
            return tuple(int(hex_code[index:index + 2], 16) for index in (1, 3, 5))

        scored = []
        for entry in hex_entries:
            hex_code = str(entry.get("hex_code") or "").upper()
            rgb = _rgb(hex_code)
            if rgb:
                scored.append((hex_code, rgb))

        blue_candidates = [
            (hex_code, rgb)
            for hex_code, rgb in scored
            if rgb[2] >= max(rgb[0], rgb[1]) and (rgb[2] - max(rgb[0], rgb[1])) >= 20
        ]
        warm_candidates = [
            (hex_code, rgb)
            for hex_code, rgb in scored
            if rgb[0] >= 200 and rgb[1] >= 110 and rgb[2] <= 140
        ]
        green_candidates = [
            (hex_code, rgb)
            for hex_code, rgb in scored
            if rgb[1] >= max(rgb[0], rgb[2]) and abs(rgb[1] - rgb[0]) >= 20
        ]
        neutral_candidates = [
            (hex_code, rgb)
            for hex_code, rgb in scored
            if max(rgb) - min(rgb) <= 24 and sum(rgb) >= 420
        ]

        primary_candidate = min(
            blue_candidates,
            key=lambda item: (
                sum(item[1]),
                abs(item[1][0] - item[1][1]),
                -item[1][2],
            ),
        )[0] if blue_candidates else None
        secondary_candidate = max(
            warm_candidates,
            key=lambda item: (
                item[1][0] + item[1][1] - item[1][2],
                item[1][0],
            ),
        )[0] if warm_candidates else None
        accent_candidate = max(
            green_candidates,
            key=lambda item: (
                item[1][1] - max(item[1][0], item[1][2]),
                item[1][1],
            ),
        )[0] if green_candidates else None
        neutral_candidate = max(neutral_candidates, key=lambda item: sum(item[1]))[0] if neutral_candidates else None

        for entry in entries:
            hex_code = str(entry.get("hex_code") or "").upper()
            if hex_code == primary_candidate:
                entry["role"] = "primary"
            elif hex_code == secondary_candidate:
                entry["role"] = "secondary"
            elif hex_code == accent_candidate:
                entry["role"] = "accent"
            elif hex_code == neutral_candidate:
                entry["role"] = "neutral"
        return entries

    @staticmethod
    def _rgb_to_hex(color: tuple[int, int, int]) -> str:
        return "#{:02X}{:02X}{:02X}".format(*color)

    def _dominant_palette(self, image_path: str) -> list[dict[str, Any]]:
        path = Path(image_path)
        if not path.exists():
            return []
        try:
            with open_image_asset(path) as image:
                image = image.convert("RGB")
                image.thumbnail((320, 320))
                quantized = image.quantize(colors=5)
                palette = quantized.getpalette() or []
                color_counts = sorted(quantized.getcolors() or [], reverse=True)
        except Exception:  # noqa: BLE001
            return []

        entries: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, (count, palette_index) in enumerate(color_counts):
            base = palette_index * 3
            rgb = tuple(palette[base: base + 3])
            if len(rgb) != 3:
                continue
            hex_code = self._rgb_to_hex(rgb)
            if hex_code in seen:
                continue
            seen.add(hex_code)
            role = "primary" if index < 2 else "accent"
            entries.append(
                {
                    "role": role,
                    "hex_code": hex_code,
                    "color_name": None,
                    "rgb_value": {"r": rgb[0], "g": rgb[1], "b": rgb[2]},
                    "source": "image_quantization",
                    "count": count,
                }
            )
        return entries

    @staticmethod
    def _extract_keywords_from_filename(filename: str) -> list[str]:
        """
        Extract keywords from icon filename.

        Examples:
            "chart-growth.svg" → ["chart", "growth"]
            "arrow_right_blue.svg" → ["arrow", "right", "blue"]
            "person-user-profile.png" → ["person", "user", "profile"]
        """
        # Remove extension and clean filename
        stem = Path(filename).stem
        # Replace separators with spaces
        cleaned = stem.replace("-", " ").replace("_", " ").lower()
        # Split into words and filter short words
        words = [word for word in cleaned.split() if len(word) > 2]
        return words


    def _extract_icon_metadata(self, source_path: str, label: str) -> dict[str, Any]:
        """
        Extract semantic metadata from icon file.

        Extracts keywords from filename and label for semantic matching.
        Works for ANY domain without hardcoded categories.

        Args:
            source_path: Path to icon file
            label: Icon label/description

        Returns:
            Dictionary with keywords for LLM-based semantic matching
        """
        # Extract keywords from filename
        filename_keywords = self._extract_keywords_from_filename(Path(source_path).name)

        # Extract keywords from label
        label_keywords = self._extract_keywords_from_filename(label)

        # Combine and deduplicate
        all_keywords = list(set(filename_keywords + label_keywords))

        return {
            "keywords": all_keywords,
        }

    @staticmethod
    def _natural_sort_key(value: str) -> list[int | str]:
        text = str(value)
        parts = re.split(r"(\d+)", text)
        return [int(part) if part.isdigit() else part.casefold() for part in parts if part]
