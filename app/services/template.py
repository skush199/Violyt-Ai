from __future__ import annotations

import logging
import json
from pathlib import Path
import re
from typing import Any
from uuid import UUID

from docx import Document
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.brand_asset_analysis import BrandAssetAnalyzer
from app.ai.rag.ocr import OCRService
from app.ai.template_vision import TemplateVisionAnalyzer
from app.core.enums import JobType, UsageMetricCode
from app.core.exceptions import NotFoundError
from app.core.studio import resolve_studio_panel_defaults
from app.integrations.object_storage import LocalObjectStorage
from app.models.knowledge import Template, TemplateMetadata
from app.repositories.brand import BrandSpaceRepository
from app.repositories.knowledge import TemplateMetadataRepository, TemplateRepository
from app.schemas.template import TemplateMetadataUpsertRequest, TemplateRecommendationResponse, TemplateUploadRequest
from app.services.asset_delivery import AssetDeliveryService
from app.services.jobs import JobService
from app.services.upload_preflight import UploadPreflightService
from app.services.usage import UsageLimitService

logger = logging.getLogger(__name__)


class TemplateService:
    TEMPLATE_MATCH_STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "its",
        "linkedin",
        "of",
        "on",
        "or",
        "platform",
        "post",
        "the",
        "this",
        "to",
        "with",
        "x",
        "jiraaf",
    }

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.templates = TemplateRepository(session)
        self.metadata = TemplateMetadataRepository(session)
        self.brands = BrandSpaceRepository(session)
        self.storage = LocalObjectStorage()
        self.jobs = JobService(session)
        self.vision = TemplateVisionAnalyzer()
        self.brand_asset_analyzer = BrandAssetAnalyzer()
        self.ocr = OCRService()
        self.usage = UsageLimitService(session)
        self.preflight = UploadPreflightService()
        self.asset_delivery = AssetDeliveryService()

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]+", text.lower())
            if len(token) > 2 and token not in TemplateService.TEMPLATE_MATCH_STOPWORDS
        }

    @staticmethod
    def _export_formats_for_template(storage_path: str) -> list[str]:
        suffix = Path(storage_path).suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            return ["png", "jpg", "pdf"]
        if suffix in {".doc", ".docx", ".pdf"}:
            return ["pdf", "doc"]
        return ["png", "jpg", "pdf", "doc"]

    @staticmethod
    def _resolve_vision_source(absolute_path: str, extracted: dict) -> str | None:
        suffix = Path(absolute_path).suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".webp"} and Path(absolute_path).exists():
            return absolute_path
        for image_path in extracted.get("images", []) or []:
            candidate = Path(str(image_path))
            if candidate.exists():
                return str(candidate)
        return None

    @staticmethod
    def _default_template_zones(width: int, height: int) -> list[dict[str, int | str]]:
        pad_x = max(48, int(width * 0.06))
        pad_y = max(40, int(height * 0.06))
        return [
            {"zone_id": "logo", "role": "logo", "x": width - pad_x - 180, "y": pad_y, "width": 180, "height": 80},
            {"zone_id": "headline", "role": "headline", "x": pad_x, "y": pad_y, "width": width - (pad_x * 2), "height": max(140, int(height * 0.18)), "max_lines": 3},
            {"zone_id": "body", "role": "body", "x": pad_x, "y": pad_y + max(150, int(height * 0.2)), "width": width - (pad_x * 2), "height": max(180, int(height * 0.24)), "max_lines": 8},
            {"zone_id": "image", "role": "image", "x": pad_x, "y": pad_y + max(360, int(height * 0.46)), "width": width - (pad_x * 2), "height": max(220, int(height * 0.28))},
            {"zone_id": "cta", "role": "cta", "x": pad_x, "y": height - pad_y - 100, "width": min(360, width - (pad_x * 2)), "height": 100, "max_lines": 2},
        ]

    @classmethod
    def _normalize_editable_zones(
        cls,
        editable_zones: list[dict[str, Any]] | None,
        width: int,
        height: int,
    ) -> list[dict[str, Any]]:
        defaults = cls._default_template_zones(width, height)
        fallback_by_role = {
            str(zone.get("role", "")): zone
            for zone in defaults
            if zone.get("role")
        }
        if not editable_zones:
            return defaults

        normalized: list[dict[str, Any]] = []
        for index, zone in enumerate(editable_zones):
            if not isinstance(zone, dict):
                continue
            role = str(zone.get("role") or zone.get("zone_id") or "").strip().lower()
            if not role:
                continue
            fallback = fallback_by_role.get(role) or defaults[min(index, len(defaults) - 1)]

            def _value_for(key: str, fallback_key: str) -> int:
                raw = zone.get(key)
                if isinstance(raw, (int, float)):
                    numeric = float(raw)
                    if 0 <= numeric <= 1:
                        scale = width if key in {"x", "width"} else height
                        return max(int(numeric * scale), 0)
                    return max(int(numeric), 0)
                return int(fallback[fallback_key])

            normalized.append(
                {
                    "zone_id": str(zone.get("zone_id") or fallback.get("zone_id") or role),
                    "role": role,
                    "x": _value_for("x", "x"),
                    "y": _value_for("y", "y"),
                    "width": max(_value_for("width", "width"), 1),
                    "height": max(_value_for("height", "height"), 1),
                    "max_lines": zone.get("max_lines", fallback.get("max_lines")),
                }
            )
        return normalized or defaults

    @staticmethod
    def _editable_fields_from_zones(zones: list[dict[str, Any]]) -> list[str]:
        allowed_roles = {"headline", "body", "cta", "logo", "image", "header", "footer"}
        roles = {
            str(zone.get("role", "")).strip().lower()
            for zone in zones
            if isinstance(zone, dict) and zone.get("role")
        }
        editable_fields = sorted(role for role in roles if role in allowed_roles)
        if "icons" not in editable_fields:
            editable_fields.append("icons")
        return editable_fields

    @staticmethod
    def _extract_docx_text(absolute_path: str, extracted: dict[str, object]) -> str:
        source_format = str(extracted.get("source_format") or "").lower()
        if source_format != "docx" and not absolute_path.lower().endswith(".docx"):
            return ""
        document = Document(absolute_path)
        return "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())

    @classmethod
    def _template_surface_policy(
        cls,
        *,
        text: str,
        source_format: str,
        zone_roles: set[str],
        rich_analysis: dict[str, Any],
    ) -> dict[str, Any]:
        word_count = len(re.findall(r"[A-Za-z0-9]+", text))
        text_length = len(text.strip())
        text_zone_count = len(zone_roles & {"headline", "body", "header", "footer", "proof_point", "stat_highlight", "cta"})
        style_map_count = len(rich_analysis.get("text_style_map", []) or [])
        heading_signal_count = sum(
            1
            for key in ("heading", "header", "footer")
            if str(rich_analysis.get(key) or "").strip()
        )
        raster_like = source_format.lower() in {"png", "jpg", "jpeg", "webp", "pdf"}

        risk_score = 0
        if raster_like:
            risk_score += 2
        if text_length >= 160:
            risk_score += 2
        elif text_length >= 80:
            risk_score += 1
        if word_count >= 24:
            risk_score += 2
        elif word_count >= 12:
            risk_score += 1
        if text_zone_count >= 3:
            risk_score += 1
        if style_map_count >= 3:
            risk_score += 1
        if heading_signal_count >= 2:
            risk_score += 1

        if risk_score >= 5:
            text_overlay_risk = "high"
        elif risk_score >= 3:
            text_overlay_risk = "medium"
        else:
            text_overlay_risk = "low"

        overlay_safe = not (
            raster_like
            and text_overlay_risk == "high"
            and (text_zone_count >= 2 or word_count >= 16 or text_length >= 120)
        )
        return {
            "surface_kind": "overlay_safe" if overlay_safe else "reference_only_flattened_text",
            "text_overlay_risk": text_overlay_risk,
            "overlay_safe": overlay_safe,
            "text_word_count": word_count,
            "text_character_count": text_length,
        }

    @staticmethod
    def _read_analysis_text(analysis_path: str | None) -> str:
        if not analysis_path:
            return ""
        path = Path(analysis_path)
        if not path.exists():
            return ""

        raw_text = path.read_text(encoding="utf-8", errors="replace").strip()
        if not raw_text:
            return ""
        if path.suffix.lower() != ".json":
            return raw_text
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            return raw_text
        return json.dumps(parsed, ensure_ascii=False, indent=2)

    @classmethod
    def _extract_font_names(cls, families: list[dict[str, Any]] | list[str] | None) -> set[str]:
        names: set[str] = set()
        for family in families or []:
            if isinstance(family, dict):
                candidate = str(family.get("name") or "").strip().lower()
            else:
                candidate = str(family).strip().lower()
            if candidate:
                names.add(candidate)
        return names

    @classmethod
    def _extract_palette_tokens(cls, entries: list[dict[str, Any]] | dict[str, Any] | None) -> set[str]:
        tokens: set[str] = set()
        if isinstance(entries, dict):
            iterable = [{"hex_code": value} for _key, value in entries.items()]
        else:
            iterable = entries or []
        for entry in iterable:
            if not isinstance(entry, dict):
                continue
            hex_code = str(entry.get("hex_code") or entry.get("value") or "").strip().lower()
            if hex_code:
                tokens.add(hex_code)
        return tokens

    @classmethod
    def _derive_content_patterns(cls, text: str, layout_type: str, zone_roles: set[str]) -> set[str]:
        lowered = text.lower()
        patterns: set[str] = set()
        if layout_type:
            patterns.add(layout_type)
        if any(token in lowered for token in ["launch", "introducing", "new product", "announcement"]):
            patterns.add("announcement")
        if any(token in lowered for token in ["benefit", "why", "how", "step", "insight", "explainer", "education"]):
            patterns.add("explainer")
        if any(token in lowered for token in ["compare", "comparison", "versus", "vs", "case 01", "case 02"]):
            patterns.add("comparison")
        if any(token in lowered for token in ["offer", "discount", "limited time", "sale", "register", "apply now"]):
            patterns.add("promotion")
        if any(token in lowered for token in ["testimonial", "customer", "review", "client story"]):
            patterns.add("testimonial")
        if any(token in lowered for token in ["data", "stat", "chart", "graph", "ranking", "rank", "percent", "report", "metrics", "inflation", "gdp", "growth", "economy"]):
            patterns.add("data_visualization")
        if "cta" in zone_roles:
            patterns.add("conversion")
        if "image" in zone_roles:
            patterns.add("visual_first")
        if len(zone_roles & {"body", "proof_point", "stat_highlight"}) >= 2 or "data" in lowered or "ranking" in lowered:
            patterns.add("information_dense")
        return patterns

    @classmethod
    def _prompt_signals(cls, prompt: str, studio_panel: dict[str, Any]) -> dict[str, Any]:
        lowered = prompt.lower()
        word_count = len(prompt.split())
        requested_patterns: set[str] = set()
        if any(token in lowered for token in ["launch", "introduce", "announcement"]):
            requested_patterns.add("announcement")
        if any(token in lowered for token in ["explainer", "insight", "education", "breakdown", "how to", "why "]):
            requested_patterns.add("explainer")
        if any(token in lowered for token in ["compare", "comparison", "versus", "vs ", "shift", "moving from", "transition", "switch"]):
            requested_patterns.add("comparison")
        if any(token in lowered for token in ["offer", "discount", "sale", "register", "apply", "download", "sign up"]):
            requested_patterns.update({"promotion", "conversion"})
        if any(token in lowered for token in ["testimonial", "customer story", "review"]):
            requested_patterns.add("testimonial")
        if any(token in lowered for token in ["data", "stat", "chart", "graph", "ranking", "rank", "percent", "report", "metrics", "number", "inflation", "gdp", "growth"]):
            requested_patterns.add("data_visualization")
        if any(token in lowered for token in ["3d", "3-d", "illustration", "character", "mascot", "animated", "cartoon"]):
            requested_patterns.add("illustration")

        wants_infographic = any(
            token in lowered
            for token in ["infographic", "carousel", "compare", "comparison", "explain", "breakdown", "steps", "insight", "shift", "moving from", "transition", "ranking", "rank", "data", "stat", "chart", "graph", "metrics", "inflation", "gdp"]
        )
        needs_cta = any(
            token in lowered
            for token in ["cta", "call to action", "apply", "book", "download", "register", "sign up", "learn more"]
        )
        needs_visual = any(
            token in lowered
            for token in ["image", "visual", "poster", "creative", "hero", "thumbnail", "photo", "graphic", "illustration", "3d", "character"]
        )
        text_density = "high" if word_count > 28 else ("medium" if word_count > 14 else "low")
        section_count_hint = 1
        count_match = re.search(r"\b(\d+)\s+(?:steps|slides|cards|panels|sections|reasons|benefits|points)\b", lowered)
        if count_match:
            try:
                section_count_hint = max(int(count_match.group(1)), 1)
            except ValueError:
                section_count_hint = 1
        elif wants_infographic:
            section_count_hint = 3

        return {
            "tokens": cls._tokenize(prompt),
            "platform": studio_panel.get("platform_preset"),
            "format": studio_panel.get("format"),
            "file_type": studio_panel.get("file_type"),
            "word_count": word_count,
            "text_density": text_density,
            "section_count_hint": section_count_hint,
            "wants_infographic": wants_infographic,
            "needs_cta": needs_cta,
            "needs_visual": needs_visual,
            "requested_patterns": requested_patterns,
        }

    @classmethod
    def _brand_signals(cls, brand_context: dict[str, Any] | None) -> dict[str, Any]:
        context = brand_context or {}
        identity = context.get("identity", {}) if isinstance(context.get("identity"), dict) else {}
        visual_identity = context.get("visual_identity", {}) if isinstance(context.get("visual_identity"), dict) else {}
        typography = visual_identity.get("typography", {}) if isinstance(visual_identity.get("typography"), dict) else {}
        guardrails = context.get("guardrails", {}) if isinstance(context.get("guardrails"), dict) else {}
        return {
            "logo_required": bool(identity.get("logo_asset_id") or identity.get("logo_asset_ids")),
            "palette_tokens": cls._extract_palette_tokens(
                visual_identity.get("palette_entries") or visual_identity.get("brand_color_palette")
            ),
            "font_names": cls._extract_font_names(typography.get("font_families", [])),
            "audience_available": bool(context.get("audience_insights")),
            "word_bank_strength": len(guardrails.get("positive_word_bank", []))
            + len(guardrails.get("negative_word_bank", [])),
        }

    @staticmethod
    def _normalize_format_family(value: Any) -> str | None:
        text = str(value or "").strip().lower()
        if not text:
            return None
        if text in {"carousel", "carousal", "slides", "multi_slide", "multi-slide", "multi_page", "multi-page"}:
            return "carousel"
        if text in {"infographic", "multi_section", "multi-section", "explainer_board", "explainer-board"}:
            return "infographic"
        if text in {"static", "single", "single_panel", "single-panel", "poster", "thumbnail", "post"}:
            return "static"
        return None

    @classmethod
    def _derive_format_family(
        cls,
        *,
        template: Template,
        metadata: TemplateMetadata | None,
        layout_type: str,
        page_count: int,
        zone_roles: set[str],
    ) -> str:
        explicit_candidates = [
            template.matcher_features_json.get("format_family") if isinstance(template.matcher_features_json, dict) else None,
            template.analysis_json.get("format_family"),
            ((template.analysis_json.get("editorial_dna") or {}) if isinstance(template.analysis_json.get("editorial_dna"), dict) else {}).get("format_family"),
            (metadata.zone_map.get("format_family") if metadata and isinstance(metadata.zone_map, dict) else None),
            layout_type,
            template.kind,
        ]
        for candidate in explicit_candidates:
            normalized = cls._normalize_format_family(candidate)
            if normalized:
                return normalized
        if page_count >= 3:
            return "carousel"
        if layout_type in {"infographic", "multi_section", "comparison"}:
            return "infographic"
        if len(zone_roles & {"body", "proof_point", "stat_highlight", "image"}) >= 3:
            return "infographic"
        return "static"

    @classmethod
    def _template_profile(cls, template: Template, metadata: TemplateMetadata | None) -> dict[str, Any]:
        matcher = template.matcher_features_json or {}
        zone_roles = {
            str(zone.get("role")).strip().lower()
            for zone in (metadata.zone_map.get("zones", []) if metadata else [])
            if isinstance(zone, dict) and zone.get("role")
        }
        keyword_source = " ".join(
            filter(
                None,
                [
                    template.name,
                    template.description or "",
                    *template.tags,
                    str(matcher.get("layout_type") or ""),
                    " ".join(str(pattern) for pattern in matcher.get("content_patterns", []) or []),
                ],
            )
        )
        title_source = " ".join(
            filter(
                None,
                [
                    template.name,
                    template.description or "",
                    str(template.analysis_json.get("source_filename") or ""),
                    str(template.analysis_json.get("filename") or ""),
                ],
            )
        )
        content_patterns = {
            str(pattern).strip().lower()
            for pattern in matcher.get("content_patterns", []) or []
            if str(pattern).strip()
        }
        layout_type = str(
            matcher.get("layout_type")
            or (metadata.zone_map.get("layout_type") if metadata else "")
            or template.analysis_json.get("layout_type")
            or template.kind
        ).strip().lower()
        if layout_type:
            content_patterns.add(layout_type)
        page_count = 0
        if metadata and isinstance(getattr(metadata, "sizing_rules", None), dict):
            for raw_count in (
                metadata.sizing_rules.get("page_count"),
                metadata.sizing_rules.get("slide_count"),
            ):
                try:
                    parsed = int(raw_count or 0)
                except (TypeError, ValueError):
                    parsed = 0
                if parsed > 0:
                    page_count = parsed
                    break
        if page_count <= 0:
            for raw_count in (
                template.analysis_json.get("page_count"),
                template.analysis_json.get("preflight_page_count"),
            ):
                try:
                    parsed = int(raw_count or 0)
                except (TypeError, ValueError):
                    parsed = 0
                if parsed > 0:
                    page_count = parsed
                    break
        format_family = cls._derive_format_family(
            template=template,
            metadata=metadata,
            layout_type=layout_type,
            page_count=page_count,
            zone_roles=zone_roles,
        )
        return {
            "tokens": cls._tokenize(keyword_source),
            "title_tokens": cls._tokenize(title_source),
            "ocr_tokens": cls._tokenize(
                " ".join(
                    filter(
                        None,
                        [
                            str(template.analysis_json.get("extracted_text_preview") or ""),
                            str(template.analysis_json.get("heading") or ""),
                            str(template.analysis_json.get("header") or ""),
                            str(template.analysis_json.get("footer") or ""),
                        ],
                    )
                )
            ),
            "layout_type": layout_type,
            "zone_roles": zone_roles,
            "supports_logo": "logo" in zone_roles,
            "supports_cta": "cta" in zone_roles,
            "supports_image": "image" in zone_roles,
            "supports_body": "body" in zone_roles,
            "multi_section_capable": len(zone_roles & {"body", "proof_point", "stat_highlight", "image"}) >= 2
            or layout_type in {"infographic", "carousel", "multi_section"},
            "platform_hints": set((metadata.platform_rules.get("supported_platforms", []) if metadata else []) or matcher.get("supported_platforms", []) or []),
            "export_formats": set((metadata.export_rules.get("supported_formats", []) if metadata else []) or matcher.get("supported_exports", []) or []),
            "palette_tokens": cls._extract_palette_tokens(matcher.get("palette", [])),
            "font_names": cls._extract_font_names(matcher.get("font_families", [])),
            "content_patterns": content_patterns,
            "brand_score": float(matcher.get("brand_score", template.analysis_json.get("brand_score", 0.0) or 0.0)),
            "editable_fields": set(metadata.editable_fields if metadata else []),
            "page_count": page_count,
            "surface_kind": str(
                matcher.get("surface_kind")
                or template.analysis_json.get("surface_kind")
                or "overlay_safe"
            ).strip().lower(),
            "text_overlay_risk": str(
                matcher.get("text_overlay_risk")
                or template.analysis_json.get("text_overlay_risk")
                or "low"
            ).strip().lower(),
            "overlay_safe": bool(
                matcher.get("overlay_safe", template.analysis_json.get("overlay_safe", True))
            ),
            "format_family": format_family,
        }

    @classmethod
    def _requested_carousel_slide_count_from_prompt(cls, prompt: str | None) -> int | None:
        raw = str(prompt or "")
        match = re.search(r"\b(\d{1,2})\s*(?:-| )?slides?\b", raw, re.IGNORECASE)
        if not match:
            match = re.search(r"\bslides?\s*:\s*(\d{1,2})\b", raw, re.IGNORECASE)
        if not match:
            return None
        try:
            value = int(match.group(1))
        except (TypeError, ValueError):
            return None
        return value if 1 < value <= 20 else None

    @classmethod
    def _adaptation_score_for_recommendation(
        cls,
        *,
        requested_format_family: str | None,
        template_profile: dict[str, Any],
        base_score: float,
        match_type: str,
        score_breakdown: dict[str, float] | None = None,
        requested_slide_count: int | None = None,
    ) -> float:
        adaptation_score = float(base_score)
        candidate_family = cls._normalize_format_family(template_profile.get("format_family"))
        if requested_format_family and candidate_family == requested_format_family:
            adaptation_score += 8.0
        if requested_format_family == "carousel":
            page_count = int(template_profile.get("page_count") or 0)
            if page_count >= 3:
                target_count = requested_slide_count or 5
                distance = abs(page_count - target_count)
                adaptation_score += max(0.0, 3.0 - (distance * 0.8))
                if distance >= 3:
                    adaptation_score -= min(float(distance - 2) * 0.5, 1.5)
            topical_fit = 0.0
            if isinstance(score_breakdown, dict):
                topical_fit = float(score_breakdown.get("keyword_overlap") or 0.0) + float(
                    score_breakdown.get("ocr_text_fit") or 0.0
                )
            if topical_fit:
                adaptation_score += min(topical_fit * 0.35, 3.0)
            else:
                adaptation_score -= 1.0
        elif requested_format_family == "infographic" and bool(template_profile.get("multi_section_capable")):
            adaptation_score += 3.0
        elif requested_format_family == "static" and not bool(template_profile.get("multi_section_capable")):
            adaptation_score += 1.5

        if match_type == "exact_template":
            adaptation_score += 4.0
        elif match_type == "adapted_template":
            adaptation_score += 2.0
        elif match_type == "reference_only":
            adaptation_score -= 2.0
        return round(adaptation_score, 2)

    @staticmethod
    def _sequence_recommendation_signature(value: Any) -> tuple[str, int] | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        raw = raw.split("?", 1)[0]
        stem = Path(raw).name
        if "." in stem:
            stem = Path(stem).stem
        normalized = re.sub(r"[\s_]+", "-", stem.strip())
        match = re.match(r"^(?P<family>.+?)-(?P<index>\d+)(?:-[0-9a-f]{8,})?$", normalized, flags=re.IGNORECASE)
        if not match:
            return None
        try:
            slide_index = int(match.group("index"))
        except ValueError:
            return None
        if slide_index <= 0:
            return None
        family = re.sub(r"[-_\s]+", "-", match.group("family")).strip("-").upper()
        return (family, slide_index) if family else None

    @staticmethod
    def _humanize_recommendation_family(value: str) -> str:
        normalized = re.sub(r"[-_\s]+", " ", str(value or "").strip()).strip()
        return normalized.title() if normalized else "Carousel Family"

    @classmethod
    def _collapse_carousel_recommendation_families(
        cls,
        recommendations: list[TemplateRecommendationResponse],
    ) -> list[TemplateRecommendationResponse]:
        grouped: list[TemplateRecommendationResponse] = []
        seen_families: set[str] = set()
        family_members: dict[str, list[TemplateRecommendationResponse]] = {}
        for recommendation in recommendations:
            family = str(recommendation.recommendation_group_key or "").strip()
            if recommendation.format_family == "carousel" and family:
                family_members.setdefault(family, []).append(recommendation)

        for recommendation in recommendations:
            family = str(recommendation.recommendation_group_key or "").strip()
            if recommendation.format_family != "carousel" or not family:
                grouped.append(recommendation)
                continue
            if family in seen_families:
                continue
            seen_families.add(family)
            members = family_members.get(family, [recommendation])
            representative = next(
                (
                    item
                    for item in members
                    if int((item.metadata or {}).get("sequence_position") or 0) == 1
                ),
                max(
                    members,
                    key=lambda item: float((item.metadata or {}).get("adaptation_score") or item.score or 0.0),
                ),
            )
            family_display_name = str((representative.metadata or {}).get("family_display_name") or "").strip() or representative.display_name or representative.name
            family_slide_count = max(
                len(members),
                max(
                    int((item.metadata or {}).get("sequence_position") or 0)
                    for item in members
                ),
            )
            updated_metadata = dict(representative.metadata or {})
            updated_metadata["family_member_count"] = len(members)
            updated_metadata["family_slide_count"] = family_slide_count
            updated_metadata["group_type"] = "carousel_family"
            grouped.append(
                representative.model_copy(
                    update={
                        "display_name": family_display_name,
                        "selection_reason": representative.selection_reason or "Carousel Match",
                        "metadata": updated_metadata,
                    }
                )
            )
        return grouped

    @classmethod
    def _annotate_recommendation_selection(
        cls,
        recommendations: list[TemplateRecommendationResponse],
        *,
        requested_format_family: str | None,
    ) -> list[TemplateRecommendationResponse]:
        labeled: list[TemplateRecommendationResponse] = []
        fallback_reason = {
            "carousel": "Carousel Match",
            "infographic": "Infographic Match",
            "static": "Static Match",
        }.get(requested_format_family, "Suggested Match")
        for index, recommendation in enumerate(recommendations):
            selection_reason = "Best Adaptation" if index == 0 else (recommendation.selection_reason or fallback_reason)
            labeled.append(
                recommendation.model_copy(
                    update={
                        "is_primary_adaptation": index == 0,
                        "selection_reason": selection_reason,
                    }
                )
            )
        return labeled

    @classmethod
    def _score_template(
        cls,
        prompt: str,
        studio_panel: dict,
        template: Template,
        metadata: TemplateMetadata | None,
        brand_context: dict[str, Any] | None = None,
    ) -> tuple[float, list[str], dict[str, float], dict, int]:
        score = 0.0
        reasons: list[str] = []
        breakdown = {
            "keyword_overlap": 0.0,
            "ocr_text_fit": 0.0,
            "platform_fit": 0.0,
            "export_fit": 0.0,
            "format_fit": 0.0,
            "brand_alignment": 0.0,
            "asset_coverage": 0.0,
            "content_structure": 0.0,
            "surface_safety": 0.0,
        }
        adaptation_plan: dict[str, object] = {}
        prompt_signals = cls._prompt_signals(prompt, studio_panel)
        brand_signals = cls._brand_signals(brand_context)
        template_profile = cls._template_profile(template, metadata)
        critical_misses = 0

        shared = prompt_signals["tokens"] & template_profile["tokens"]
        if shared:
            keyword_score = min(len(shared) * 1.5, 8.0)
            score += keyword_score
            breakdown["keyword_overlap"] = keyword_score
            reasons.append(f"keyword overlap: {', '.join(sorted(shared)[:5])}")
        title_topic_overlap = prompt_signals["tokens"] & template_profile.get("title_tokens", set())
        generic_title_tokens = {
            "carousel",
            "post",
            "creative",
            "template",
            "linkedin",
            "instagram",
            "static",
            "infographic",
            "analysis",
            "analyzer",
            "guide",
            "education",
            "planning",
            "strategy",
            "tips",
        }
        specific_title_overlap = {token for token in title_topic_overlap if token not in generic_title_tokens}
        if specific_title_overlap:
            title_topic_score = min(3.0 + (len(specific_title_overlap) * 2.0), 8.0)
            score += title_topic_score
            breakdown["topic_title_fit"] = title_topic_score
            reasons.append(f"template title/topic fit: {', '.join(sorted(specific_title_overlap)[:5])}")
        ocr_overlap = prompt_signals["tokens"] & template_profile["ocr_tokens"]
        if ocr_overlap:
            ocr_score = min(len(ocr_overlap) * 1.8, 6.0)
            score += ocr_score
            breakdown["ocr_text_fit"] = ocr_score
            reasons.append(f"template text fit: {', '.join(sorted(ocr_overlap)[:5])}")

        platform = prompt_signals["platform"]
        format_name = prompt_signals["format"]
        file_type = prompt_signals["file_type"]
        if template_profile["platform_hints"]:
            if platform in template_profile["platform_hints"]:
                score += 4.0
                breakdown["platform_fit"] = 4.0
                reasons.append(f"supports platform {platform}")
            else:
                adaptation_plan["platform_reframing_required"] = True
        if template_profile["export_formats"] and file_type in template_profile["export_formats"]:
            score += 2.0
            breakdown["export_fit"] = 2.0
            reasons.append(f"supports export {file_type}")
        if format_name and format_name == template.kind:
            score += 2.0
            breakdown["format_fit"] += 2.0
            reasons.append(f"kind matches {format_name}")
        page_count = int(template_profile.get("page_count") or 0)
        if format_name == "carousel":
            if page_count >= 3:
                carousel_score = min(4.0 + (page_count * 0.15), 5.5)
                score += carousel_score
                breakdown["format_fit"] += carousel_score
                reasons.append(f"multi-page carousel support ({page_count} slides)")
            elif template_profile["layout_type"] == "carousel":
                score += 2.5
                breakdown["format_fit"] += 2.5
                reasons.append("carousel layout semantics available")
            else:
                adaptation_plan["multi_slide_sequence_synthesis"] = True
                critical_misses += 2
                breakdown["format_fit"] -= 2.5
                reasons.append("single-page template needs carousel sequence synthesis")
        if template_profile["layout_type"] in {format_name, "carousel", "infographic"} and prompt_signals["wants_infographic"]:
            score += 2.5
            breakdown["content_structure"] += 2.5
            reasons.append("layout structure fits multi-section prompt")
            
        lowered_prompt = prompt.lower()
        if any(token in lowered_prompt for token in ["ranking", "positioned", "global", "world", "gdp", "economy", "inflation", "rank"]):
            # Use template name and tokens as a proxy for tags if tags aren't explicitly structured
            if any(token in template_profile["tokens"] | template_profile["ocr_tokens"] for token in ["globe", "world", "positioned", "rank", "ranking"]):
                score += 8.0
                reasons.append("template visual structure (globe/ranking) matches data-centric prompt")
                adaptation_plan["exact_template_preference"] = True
                
        requested_patterns = prompt_signals["requested_patterns"] & template_profile["content_patterns"]
        if requested_patterns:
            pattern_score = min(len(requested_patterns) * 1.5, 4.5)
            score += pattern_score
            breakdown["content_structure"] += pattern_score
            reasons.append(f"content pattern fit: {', '.join(sorted(requested_patterns))}")
        if {"headline", "body", "cta"}.issubset(template_profile["editable_fields"] | template_profile["zone_roles"]):
            score += 1.5
            breakdown["asset_coverage"] += 1.5
            reasons.append("template exposes editable text zones")
        if metadata and metadata.zone_map.get("background_style"):
            score += 1.0
            breakdown["brand_alignment"] += 1.0

        if not template_profile["overlay_safe"]:
            score = min(score, 6.8)
            breakdown["surface_safety"] = -4.0
            adaptation_plan["reference_style_only"] = True
            critical_misses += 3
            reasons.append("template contains baked-in text and is safer as a style reference than a render surface")

        if prompt_signals["needs_cta"]:
            if template_profile["supports_cta"]:
                score += 1.2
                breakdown["asset_coverage"] += 1.2
                reasons.append("template has a dedicated CTA zone")
            else:
                adaptation_plan["cta_reposition"] = True
                critical_misses += 1
        if prompt_signals["needs_visual"]:
            if template_profile["supports_image"]:
                score += 1.2
                breakdown["asset_coverage"] += 1.2
                reasons.append("template includes a visual slot")
            else:
                adaptation_plan["visual_slot_synthesis"] = True
                critical_misses += 1
        if prompt_signals["text_density"] == "high":
            if template_profile["supports_body"]:
                score += 1.5
                breakdown["content_structure"] += 1.5
                reasons.append("template can support text-heavy content")
            else:
                adaptation_plan["body_expansion_required"] = True
                critical_misses += 1
        if prompt_signals["section_count_hint"] > 1:
            if template_profile["multi_section_capable"]:
                section_score = min(2.0 + (prompt_signals["section_count_hint"] * 0.2), 3.5)
                score += section_score
                breakdown["content_structure"] += section_score
                reasons.append("template can support multi-section storytelling")
            else:
                adaptation_plan["multi_section_flow"] = True
                critical_misses += 1
        if brand_signals["logo_required"]:
            if template_profile["supports_logo"]:
                score += 1.0
                breakdown["brand_alignment"] += 1.0
                reasons.append("template reserves logo placement")
            else:
                adaptation_plan["logo_injection_required"] = True
                critical_misses += 1

        palette_overlap = len(brand_signals["palette_tokens"] & template_profile["palette_tokens"])
        if brand_signals["palette_tokens"] and template_profile["palette_tokens"]:
            palette_score = min(float(palette_overlap), 2.5)
            if palette_score:
                score += palette_score
                breakdown["brand_alignment"] += palette_score
                reasons.append("template palette aligns with validated brand colors")
            else:
                adaptation_plan["palette_override_to_brand_system"] = True
        font_overlap = len(brand_signals["font_names"] & template_profile["font_names"])
        if brand_signals["font_names"] and template_profile["font_names"]:
            font_score = min(float(font_overlap), 2.0)
            if font_score:
                score += font_score
                breakdown["brand_alignment"] += font_score
                reasons.append("template typography aligns with validated brand fonts")
            else:
                adaptation_plan["typography_override_to_brand_system"] = True

        if template.kind in {"layout", "hybrid"} and format_name in {"static", "carousel", "infographic"}:
            score += 1.5
            breakdown["format_fit"] += 1.5
        if template_profile["brand_score"]:
            brand_score = max(0.0, min(float(template_profile["brand_score"]), 10.0)) / 5.0
            score += brand_score
            breakdown["brand_alignment"] += brand_score

        if prompt_signals["word_count"] > 18:
            adaptation_plan["expand_headline_or_body"] = True
        if format_name in {"carousel", "infographic", "pdf", "doc"}:
            adaptation_plan["multi_section_flow"] = True
        if platform in {"instagram", "x"}:
            adaptation_plan["compact_cta"] = True
        if metadata and metadata.zone_map.get("zones"):
            zone_roles = template_profile["zone_roles"]
            if prompt_signals["wants_infographic"] and not {"headline", "body", "image"}.issubset(zone_roles):
                adaptation_plan["infographic_structure_synthesis"] = True
            if prompt_signals["text_density"] == "high" and "body" not in zone_roles:
                adaptation_plan["body_expansion_required"] = True
        return score, reasons, breakdown, adaptation_plan, critical_misses

    @staticmethod
    def _match_type_for_score(score: float, adaptation_plan: dict[str, object], critical_misses: int) -> str:
        structural_flags = {
            "multi_section_flow",
            "cta_reposition",
            "visual_slot_synthesis",
            "infographic_structure_synthesis",
            "body_expansion_required",
            "logo_injection_required",
            "platform_reframing_required",
        }
        structural_count = len(structural_flags & set(adaptation_plan))
        if score >= 11.0 and not adaptation_plan:
            return "exact_template"
        if score >= 8.0 and critical_misses <= 1 and structural_count <= 2:
            return "adapted_template"
        return "reference_only"

    async def upload(self, tenant_id: UUID, brand_space_id: UUID, payload: TemplateUploadRequest) -> Template:
        preflight = self.preflight.validate_base64_upload(
            filename=payload.filename,
            mime_type=payload.mime_type,
            content_base64=payload.content_base64,
        )
        stored = self.storage.save_bytes(tenant_id, brand_space_id, "templates", payload.filename, preflight.content)
        template = Template(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            name=payload.name,
            description=payload.description,
            kind=payload.kind,
            storage_path=stored.storage_path,
            analysis_json={
                "status": "queued",
                "source_format": preflight.detected_extension.lstrip("."),
                "file_size_bytes": preflight.size_bytes,
                "preflight_page_count": preflight.page_count,
                "preflight_hints": preflight.hints or {},
            },
            tags=payload.tags,
        )
        await self.templates.add(template)
        await self.metadata.add(
            TemplateMetadata(
                tenant_id=tenant_id,
                brand_space_id=brand_space_id,
                template_id=template.id,
                zone_map={},
                sizing_rules={},
                platform_rules={},
                editable_fields=[],
                export_rules={},
            )
        )
        await self.session.commit()
        await self.jobs.create(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            job_type=JobType.TEMPLATE_ANALYSIS,
            payload={"template_id": str(template.id)},
        )
        return template

    async def analyze(self, template_id: UUID) -> Template:
        template = await self.templates.get(template_id)
        if not template:
            raise NotFoundError("Template not found")
        template.analysis_json = {
            **(template.analysis_json or {}),
            "status": "processing",
        }
        await self.session.commit()

        width = 1080
        height = 1080
        absolute_path = self.storage.absolute_path(template.storage_path)
        template_kind = template.kind
        extracted = {"text": "", "images": [], "page_count": 0}
        page_count = 0
        try:
            extracted = self.ocr.extract(absolute_path)
            text = extracted.get("text", "")
            if not text:
                text = self._extract_docx_text(absolute_path, extracted)

            analysis_path = extracted.get("analysis_path")
            analysis_text = self._read_analysis_text(analysis_path)
            if analysis_text:
                text = "\n\n".join(part for part in [text, analysis_text] if part).strip()

            image_texts: list[str] = []
            for image_path in extracted.get("images", []) or []:
                if image_path == absolute_path:
                    continue
                try:
                    image_text = self.ocr.extract(str(image_path)).get("text", "")
                except Exception:  # noqa: BLE001
                    image_text = ""
                if image_text:
                    image_texts.append(image_text)
            if image_texts:
                text = "\n\n".join(part for part in [text, *image_texts] if part).strip()

            page_count = int(extracted.get("page_count") or 0)
            if text or extracted.get("images") or analysis_path:
                usage_amount = max(page_count, 1)
                await self.usage.enforce(template.tenant_id, UsageMetricCode.OCR_PAGES, usage_amount)
                await self.usage.increment(template.tenant_id, UsageMetricCode.OCR_PAGES, usage_amount)

            vision_source = self._resolve_vision_source(absolute_path, extracted)
            if vision_source:
                with Image.open(vision_source) as image:
                    width, height = image.size
            elif Path(absolute_path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                with Image.open(absolute_path) as image:
                    width, height = image.size
        except Exception as exc:  # noqa: BLE001
            template.analysis_json = {
                **(template.analysis_json or {}),
                "status": "failed",
                "error": str(exc),
                "page_count": page_count,
            }
            await self.session.commit()
            raise

        heuristic = {
            "background_style": {"dominant_mode": "graphic", "source": "heuristic"},
            "layout_type": template_kind,
            "editable_zones": self._default_template_zones(width, height),
            "icons": [],
            "platform_hints": ["instagram", "linkedin", "x", "youtube_thumbnail"],
        }
        vision_source = self._resolve_vision_source(absolute_path, extracted)
        vision = self.vision.analyze(vision_source, heuristic) if vision_source else heuristic
        normalized_zones = self._normalize_editable_zones(
            vision.get("editable_zones", heuristic["editable_zones"]),
            width,
            height,
        )
        _structured, normalized, rich_analysis = self.brand_asset_analyzer._extract_template_intelligence(
            text=text,
            absolute_path=absolute_path,
            images=extracted.get("images", []) or [],
            category="template",
            analysis_paths=extracted.get("analysis_paths", []) or [],
        )
        zone_roles = {
            str(zone.get("role")).strip().lower()
            for zone in normalized_zones
            if isinstance(zone, dict) and zone.get("role")
        }
        matcher_features = {
            "palette": normalized.get("palette", []),
            "font_families": normalized.get("font_families", []),
            "layout_type": rich_analysis.get("layout_type", vision.get("layout_type", template_kind)),
            "brand_score": rich_analysis.get("brand_score", vision.get("brand_score", template.analysis_json.get("brand_score", 0.0))),
            "zone_roles": sorted(zone_roles),
            "content_patterns": sorted(
                self._derive_content_patterns(
                    text,
                    rich_analysis.get("layout_type", vision.get("layout_type", template_kind)),
                    zone_roles,
                )
            ),
            "supported_platforms": vision.get("platform_hints", ["instagram", "linkedin", "x", "youtube_thumbnail"]),
            "supported_exports": self._export_formats_for_template(absolute_path),
        }
        surface_policy = self._template_surface_policy(
            text=text,
            source_format=str(extracted.get("source_format") or Path(absolute_path).suffix.lower().lstrip(".")),
            zone_roles=zone_roles,
            rich_analysis=rich_analysis,
        )
        matcher_features.update(
            {
                "surface_kind": surface_policy["surface_kind"],
                "text_overlay_risk": surface_policy["text_overlay_risk"],
                "overlay_safe": surface_policy["overlay_safe"],
            }
        )
        template.analysis_json = {
            "status": "indexed",
            "layout_type": rich_analysis.get("layout_type", vision.get("layout_type", template_kind)),
            "deterministic": True,
            "canvas_size": {"width": width, "height": height},
            "background_style": rich_analysis.get("background_style", vision.get("background_style", {})),
            "icons": rich_analysis.get("icons", vision.get("icons", [])),
            "page_count": page_count,
            "source_format": extracted.get("source_format") or Path(absolute_path).suffix.lower().lstrip("."),
            "analysis_source": "ocr_vision" if vision_source else "ocr_text",
            "extracted_text_preview": (text[:1500] if text else ""),
            "heading": rich_analysis.get("heading"),
            "header": rich_analysis.get("header"),
            "footer": rich_analysis.get("footer"),
            "heading_style": rich_analysis.get("heading_style"),
            "header_style": rich_analysis.get("header_style"),
            "footer_style": rich_analysis.get("footer_style"),
            "color_usage": rich_analysis.get("color_usage", []),
            "font_families": rich_analysis.get("font_families", []),
            "font_colors": rich_analysis.get("font_colors", []),
            "font_size_hints": rich_analysis.get("font_size_hints", []),
            "text_style_map": rich_analysis.get("text_style_map", []),
            "gradients": rich_analysis.get("gradients", []),
            "zones": normalized_zones,
            "surface_kind": surface_policy["surface_kind"],
            "text_overlay_risk": surface_policy["text_overlay_risk"],
            "overlay_safe": surface_policy["overlay_safe"],
            "text_word_count": surface_policy["text_word_count"],
            "text_character_count": surface_policy["text_character_count"],
            # Design DNA from vision AI — saved so zone_map can carry them forward
            "visual_mood": vision.get("visual_mood", ""),
            "design_style": vision.get("design_style", ""),
            "composition_style": vision.get("composition_style", ""),
            "typography_dna": vision.get("typography_dna", {}),
            "component_motifs": vision.get("component_motifs", {}),
            "infographic_elements": vision.get("infographic_elements", {}),
            "layout_dna": rich_analysis.get("layout_dna", {}),
            "composition_logic": rich_analysis.get("composition_logic", {}),
            "visual_craft_dna": rich_analysis.get("visual_craft_dna", {}),
            "subject_semantics": rich_analysis.get("subject_semantics", {}),
            "logo_anchor": vision.get("logo_anchor", ""),
            "editorial_dna": rich_analysis.get("editorial_dna", {}),
        }
        template.matcher_features_json = matcher_features
        metadata = await self.metadata.get_by_template(template.id)
        if metadata:
            metadata.zone_map = {
                "layout_type": template.analysis_json["layout_type"],
                "zones": template.analysis_json["zones"],
                "canvas_size": {"width": width, "height": height},
                "icons": template.analysis_json["icons"],
                "background_style": template.analysis_json["background_style"],
                "text_style_map": template.analysis_json.get("text_style_map", []),
                "gradients": template.analysis_json.get("gradients", []),
                # Design DNA fields from Vision AI analysis
                "typography_dna": template.analysis_json.get("typography_dna", {}),
                "component_motifs": template.analysis_json.get("component_motifs", {}),
                "infographic_elements": template.analysis_json.get("infographic_elements", {}),
                "layout_dna": template.analysis_json.get("layout_dna", {}),
                "composition_logic": template.analysis_json.get("composition_logic", {}),
                "visual_craft_dna": template.analysis_json.get("visual_craft_dna", {}),
                "subject_semantics": template.analysis_json.get("subject_semantics", {}),
                "logo_anchor": template.analysis_json.get("logo_anchor", ""),
                "visual_mood": template.analysis_json.get("visual_mood", ""),
                "design_style": template.analysis_json.get("design_style", ""),
                "composition_style": template.analysis_json.get("composition_style", ""),
                "editorial_dna": template.analysis_json.get("editorial_dna", {}),
                "surface_kind": template.analysis_json.get("surface_kind"),
                "text_overlay_risk": template.analysis_json.get("text_overlay_risk"),
                "overlay_safe": template.analysis_json.get("overlay_safe"),
            }
            metadata.sizing_rules = {
                "width": width,
                "height": height,
                "page_count": page_count,
            }
            metadata.platform_rules = {
                "supported_platforms": vision.get("platform_hints", ["instagram", "linkedin", "x", "youtube_thumbnail"]),
                "analysis_status": "indexed",
            }
            metadata.editable_fields = self._editable_fields_from_zones(normalized_zones)
            metadata.export_rules = {"supported_formats": self._export_formats_for_template(absolute_path)}
        await self.session.commit()
        logger.info(
            "template.analyze.complete template_id=%s brand_space_id=%s layout_type=%s page_count=%s zone_count=%s style_map_count=%s gradient_count=%s surface_kind=%s text_overlay_risk=%s overlay_safe=%s",
            template.id,
            template.brand_space_id,
            template.analysis_json.get("layout_type"),
            page_count,
            len(template.analysis_json.get("zones", []) or []),
            len(template.analysis_json.get("text_style_map", []) or []),
            len(template.analysis_json.get("gradients", []) or []),
            template.analysis_json.get("surface_kind"),
            template.analysis_json.get("text_overlay_risk"),
            template.analysis_json.get("overlay_safe"),
        )
        return template

    async def list(self, tenant_id: UUID, brand_space_id: UUID) -> list[Template]:
        return await self.templates.list_by_brand(brand_space_id, tenant_id)

    async def recommend(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        prompt: str,
        studio_panel: dict,
        brand_context: dict[str, Any] | None = None,
        limit: int = 5,
    ) -> list[TemplateRecommendationResponse]:
        resolved_panel = resolve_studio_panel_defaults(studio_panel)
        if brand_context is None:
            brand = await self.brands.get_scoped(tenant_id, brand_space_id)
            brand_context = brand.resolved_brand_context if brand else {}
        templates = await self.templates.list_by_brand(brand_space_id, tenant_id)
        recommendations: list[TemplateRecommendationResponse] = []
        # Determine if user has explicitly pinned a specific template.
        pinned_template_id: str | None = str(studio_panel.get("pinned_template_id") or "").strip() or None
        requested_format_family = self._normalize_format_family(resolved_panel.get("format"))

        for template in templates:
            metadata = await self.metadata.get_by_template(template.id)
            template_profile = self._template_profile(template, metadata)
            matcher = template.matcher_features_json or {}
            signature = self._sequence_recommendation_signature(template.name) or self._sequence_recommendation_signature(template.storage_path)
            recommendation_group_key = ""
            sequence_position = 0
            if signature is not None:
                recommendation_group_key = signature[0]
                sequence_position = signature[1]
            elif requested_format_family == "carousel" and int(template_profile.get("page_count") or 0) >= 3:
                recommendation_group_key = re.sub(r"[-_\s]+", "-", Path(template.storage_path).stem.strip()).strip("-").upper()
            score, reasons, breakdown, adaptation_plan, critical_misses = self._score_template(
                prompt,
                resolved_panel,
                template,
                metadata,
                brand_context,
            )
            # If user explicitly pinned this template, give it a massive score boost
            # so it always surfaces as rank #1 and is treated as exact_template.
            is_pinned = pinned_template_id and str(template.id) == pinned_template_id
            if is_pinned:
                score += 50.0  # Guaranteed rank #1
                reasons.insert(0, "user-pinned template — forcing exact_template adaptation")
            if score <= 0:
                continue
            match_type = self._match_type_for_score(score, adaptation_plan, critical_misses)
            # Pinned templates must always be exact_template or at minimum adapted_template
            if is_pinned and match_type not in {"exact_template", "adapted_template"}:
                match_type = "exact_template"
            decision_confidence = round(min(score / 14.0, 1.0), 2)
            adaptation_score = self._adaptation_score_for_recommendation(
                requested_format_family=requested_format_family,
                template_profile=template_profile,
                base_score=score,
                match_type=match_type,
                score_breakdown=breakdown,
                requested_slide_count=self._requested_carousel_slide_count_from_prompt(prompt),
            )
            recommendations.append(
                TemplateRecommendationResponse(
                    template_id=template.id,
                    name=template.name,
                    display_name=(
                        self._humanize_recommendation_family(recommendation_group_key)
                        if requested_format_family == "carousel" and recommendation_group_key
                        else template.name
                    ),
                    asset_url=self.asset_delivery.build_signed_url(
                        storage_path=template.storage_path,
                        filename=Path(template.storage_path).name,
                    ),
                    score=round(score, 2),
                    match_type=match_type,
                    decision_confidence=decision_confidence,
                    format_family=str(template_profile.get("format_family") or ""),
                    is_primary_adaptation=False,
                    selection_reason=None,
                    recommendation_group_key=recommendation_group_key or None,
                    reasons=reasons,
                    score_breakdown={key: round(value, 2) for key, value in breakdown.items()},
                    adaptation_plan=adaptation_plan,
                    metadata={
                        "kind": template.kind,
                        "tags": template.tags,
                        "supported_platforms": metadata.platform_rules.get("supported_platforms", []) if metadata else [],
                        "supported_exports": metadata.export_rules.get("supported_formats", []) if metadata else [],
                        "editable_fields": metadata.editable_fields if metadata else [],
                        "format_family": template_profile.get("format_family"),
                        "adaptation_score": adaptation_score,
                        "page_count": int(template_profile.get("page_count") or 0),
                        "layout_type": template_profile.get("layout_type"),
                        "sequence_family": recommendation_group_key or None,
                        "sequence_position": sequence_position or None,
                        "family_display_name": (
                            self._humanize_recommendation_family(recommendation_group_key)
                            if recommendation_group_key
                            else template.name
                        ),
                        "surface_kind": (
                            matcher.get("surface_kind")
                            or template.analysis_json.get("surface_kind")
                        ),
                        "text_overlay_risk": (
                            matcher.get("text_overlay_risk")
                            or template.analysis_json.get("text_overlay_risk")
                        ),
                        "overlay_safe": bool(
                            matcher.get(
                                "overlay_safe",
                                template.analysis_json.get("overlay_safe", True),
                            )
                        ),
                    },
                )
            )
        recommendations.sort(
            key=lambda item: (
                1 if self._normalize_format_family(item.metadata.get("format_family")) == requested_format_family else 0,
                float(item.metadata.get("adaptation_score", item.score) or item.score),
                item.score,
                item.decision_confidence or 0.0,
            ),
            reverse=True,
        )
        if requested_format_family == "carousel":
            recommendations = self._collapse_carousel_recommendation_families(recommendations)
        recommendations = self._annotate_recommendation_selection(
            recommendations,
            requested_format_family=requested_format_family,
        )
        logger.info(
            "template.recommend.complete brand_space_id=%s prompt_chars=%s platform=%s format=%s candidate_count=%s recommendations=%s",
            brand_space_id,
            len(prompt or ""),
            resolved_panel.get("platform_preset"),
            resolved_panel.get("format"),
            len(templates),
            [
                {
                    "template_id": item.template_id,
                    "name": item.name,
                    "display_name": item.display_name,
                    "score": item.score,
                    "match_type": item.match_type,
                    "decision_confidence": item.decision_confidence,
                    "format_family": item.format_family,
                    "is_primary_adaptation": item.is_primary_adaptation,
                    "selection_reason": item.selection_reason,
                    "recommendation_group_key": item.recommendation_group_key,
                    "surface_kind": item.metadata.get("surface_kind"),
                    "text_overlay_risk": item.metadata.get("text_overlay_risk"),
                    "overlay_safe": item.metadata.get("overlay_safe"),
                }
                for item in recommendations[:limit]
            ],
        )
        return recommendations[:limit]

    async def detail(self, tenant_id: UUID, brand_space_id: UUID, template_id: UUID) -> tuple[Template, TemplateMetadata | None]:
        template = await self.templates.get_scoped(template_id, tenant_id, brand_space_id)
        if not template:
            raise NotFoundError("Template not found")
        metadata = await self.metadata.get_by_template(template_id)
        return template, metadata

    async def update_metadata(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        template_id: UUID,
        payload: TemplateMetadataUpsertRequest,
    ) -> TemplateMetadata:
        template = await self.templates.get_scoped(template_id, tenant_id, brand_space_id)
        if not template:
            raise NotFoundError("Template not found")
        metadata = await self.metadata.get_by_template(template_id)
        if not metadata:
            raise NotFoundError("Template metadata not found")
        metadata.zone_map = payload.zone_map
        metadata.sizing_rules = payload.sizing_rules
        metadata.platform_rules = payload.platform_rules
        metadata.editable_fields = payload.editable_fields
        metadata.export_rules = payload.export_rules
        await self.session.commit()
        return metadata

    async def delete(self, tenant_id: UUID, brand_space_id: UUID, template_id: UUID) -> None:
        template = await self.templates.get_scoped(template_id, tenant_id, brand_space_id)
        if not template:
            raise NotFoundError("Template not found")
        self.storage.delete(template.storage_path)
        await self.templates.delete(template)
        await self.session.commit()
