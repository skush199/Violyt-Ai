from __future__ import annotations

import logging
import base64
import json
import re
from copy import deepcopy
from io import BytesIO
from time import perf_counter
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from PIL import Image, ImageDraw
from pydantic import ValidationError

from app.ai.blueprint import BlueprintService
from app.ai.brand_intelligence import BrandIntelligenceService
from app.ai.context_resolution import ContextResolutionService
from app.ai.context_compiler import ContextCompilerService
from app.ai.contracts import (
    AIOrchestrationRequest,
    AIOrchestrationResponse,
    BlueprintPayload,
    CreativeDecisionPayload,
    GenerationSceneGraph,
    GeneratedImageAsset,
    GenerationTrace,
    MessageStrategyPayload,
    SceneGraphGeometry,
    SceneGraphValidationIssue,
    SceneGraphValidationReport,
    StructuredTextPayload,
)
from app.ai.guardrails import GuardrailService
from app.ai.prompt_intelligence import PromptIntelligenceService
from app.ai.providers.base import PromptEnvelope
from app.ai.providers.router import ProviderRouter
from app.core.config import get_settings
from app.core.exceptions import GenerationFailureError
from app.ai.tone_intelligence import ToneIntelligenceService
from app.integrations.object_storage import LocalObjectStorage
from app.services.generation_trace import GenerationTraceService
from app.utils.input_access_tracking import InputAccessTracker
from app.services.research_editorial_planning import ResearchEditorialPlanningService
from app.utils.palette_roles import derive_palette_roles

logger = logging.getLogger(__name__)


class AIOrchestratorService:
    IMAGE_PROMPT_MAX_LENGTH = 24000
    SCENE_GRAPH_REPAIR_ATTEMPTS = 2
    CONTENT_SEMANTIC_REPAIR_ATTEMPTS = 1
    IMAGE_QUALITY_MIN_SCORE = 0.72
    AI_FINAL_RENDER_FORMATS = {"static", "story", "poster", "carousel", "infographic"}
    TEMPLATE_LOCKED_IMAGE_LED_FORMATS = {"static", "story", "poster"}
    DEFAULT_LAYERS = ["background", "decorative", "primary_visual", "content", "brand", "footer"]
    PROMPT_ECHO_STOPWORDS = {
        "a",
        "an",
        "and",
        "book",
        "create",
        "design",
        "engaging",
        "for",
        "generate",
        "instagram",
        "lower",
        "make",
        "media",
        "post",
        "prompt",
        "shares",
        "social",
        "strategies",
        "that",
        "the",
        "tips",
        "to",
        "write",
    }
    TOPIC_ANCHOR_STOPWORDS = PROMPT_ECHO_STOPWORDS | {
        "audience",
        "brand",
        "carousel",
        "campaign",
        "confidence",
        "conversational",
        "copy",
        "friend",
        "headline",
        "indian",
        "intelligent",
        "journey",
        "length",
        "linkedin",
        "platform",
        "option",
        "options",
        "premium",
        "scannable",
        "slide",
        "slides",
        "smart",
        "smarter",
        "swipe",
        "tone",
        "tradeoffs",
        "visual",
        "wealth",
    }
    TOPIC_MATCH_NOISE_TOKENS = TOPIC_ANCHOR_STOPWORDS | {
        "accent",
        "adapted",
        "asset",
        "assets",
        "background",
        "body",
        "brief",
        "carousel",
        "color",
        "colors",
        "composition",
        "context",
        "creative",
        "creatives",
        "cta",
        "design",
        "editable",
        "export",
        "flat",
        "font",
        "format",
        "generated",
        "headline",
        "image",
        "infographic",
        "inter",
        "jiraaf",
        "label",
        "layout",
        "linkedin",
        "logo",
        "marketing",
        "metadata",
        "palette",
        "pdf",
        "platform",
        "primary",
        "reference",
        "social",
        "style",
        "surface",
        "template",
        "text",
        "trusted",
        "typography",
        "visual",
        "warning",
        "zone",
        "zones",
    }
    VISUAL_METADATA_COMPATIBILITY_STOPWORDS = TOPIC_ANCHOR_STOPWORDS | {
        "accent",
        "background",
        "brand-safe",
        "clean",
        "composition",
        "creative",
        "deep",
        "design",
        "direction",
        "editorial",
        "hero",
        "image",
        "layout",
        "look",
        "mood",
        "modern",
        "no",
        "palette",
        "polished",
        "poster",
        "premium",
        "prompt",
        "safe",
        "scene",
        "spacing",
        "style",
        "surface",
        "system",
        "text",
        "visuals",
        "warm",
        "with",
        "without",
    }
    CONTENT_ALLOCATION_STOPWORDS = TOPIC_ANCHOR_STOPWORDS | {
        "actually",
        "after",
        "around",
        "because",
        "beyond",
        "bigger",
        "cleanly",
        "detail",
        "details",
        "exactly",
        "explain",
        "explains",
        "generic",
        "hidden",
        "just",
        "keep",
        "matters",
        "missed",
        "more",
        "most",
        "next",
        "only",
        "reader",
        "really",
        "slide",
        "slides",
        "story",
        "than",
        "that",
        "their",
        "them",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "under",
        "what",
        "when",
        "where",
        "which",
        "while",
        "why",
        "will",
        "with",
    }
    VISUAL_METADATA_FIELD_LIMITS = {
        "visual_direction": 180,
        "design_style": 80,
        "image_prompt": 220,
    }
    DISALLOWED_GLYPH_PATTERN = re.compile(
        r"[\u2600-\u27BF\U0001F300-\U0001FAFF\ufe0e\ufe0f\u200d]"
    )
    MOJIBAKE_SYMBOL_PATTERN = re.compile(r"(?:âœ”ï¸\x8f|âœ”ï¸|âœ…|âž¡ï¸|ï¸|â€¢)")

    FALLBACK_COPY_INSTRUCTION_PREFIXES = (
        "address ",
        "anchor ",
        "back ",
        "build ",
        "connect ",
        "encourage ",
        "frame ",
        "ground ",
        "invite ",
        "keep ",
        "lead ",
        "prioritize ",
        "reinforce ",
        "show ",
        "start ",
        "translate ",
        "use ",
    )
    FALLBACK_COPY_DESCRIPTOR_MARKERS = (
        "-led",
        "brand-safe",
        "cta",
        "headline",
        "hook",
        "messaging",
        "outcome-first",
        "phrasing",
        "supporting copy",
        "supporting line",
    )
    OBJECTION_RESPONSE_MARKERS = (
        "backed",
        "guided",
        "no need",
        "plain english",
        "plain-english",
        "supported",
        "transparent",
        "without",
    )
    OBJECTION_RESPONSE_INSTRUCTION_PREFIXES = (
        "address ",
        "answer ",
        "handle ",
        "respond to ",
        "reassure ",
    )
    MISTAKE_CAROUSEL_SIGNAL_PATTERN = re.compile(
        r"\b(mistake|mistakes|pitfall|pitfalls|error|errors|wrong|misstep|missteps|avoid|avoiding|costly)\b",
        re.IGNORECASE,
    )
    MULTI_MISTAKE_SIGNAL_PATTERN = re.compile(
        r"\b(top|common|most|costly|biggest|these)\b[\w\s-]{0,40}\b(mistakes|pitfalls|errors|missteps)\b|\b(mistakes|pitfalls|errors|missteps)\b",
        re.IGNORECASE,
    )
    MISTAKE_GROUP_START_PATTERN = re.compile(
        r"^(?:mistake|mistakes|pitfall|pitfalls|error|errors|wrong move|misstep)\s*:\s*",
        re.IGNORECASE,
    )
    MISTAKE_WHY_PATTERN = re.compile(
        r"^(?:why|because|context)\s*:\s*",
        re.IGNORECASE,
    )
    IMPACT_LINE_PATTERN = re.compile(
        r"^(?:impact|why it matters|risk|result|consequence)\s*:\s*",
        re.IGNORECASE,
    )
    FIX_LINE_PATTERN = re.compile(
        r"^(?:fix|solution|what to do|instead|action|how to fix)\s*:\s*",
        re.IGNORECASE,
    )
    PROMOTIONAL_LINE_PATTERN = re.compile(
        r"\b(explore|discover|start|learn more|learn how|open doors?|today|platform|curated|trusted|transparent|regulated|guidance|opportunit(?:y|ies)|options?|simplif(?:y|ies)|offer(?:s|ing)?|empower(?:s|ing)?)\b",
        re.IGNORECASE,
    )
    NEGATIVE_MISTAKE_CANDIDATE_PATTERN = re.compile(
        r"\b(mistake|mistakes|pitfall|pitfalls|error|errors|risk|risky|fees?|default|loss|losses|duration|yield|credit|ignore|ignoring|underestimate|miss|missing|overlook|overlooking|concentration|volatility|interest rate)\b",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self.settings = get_settings()
        self.providers = ProviderRouter()
        self.guardrails = GuardrailService()
        self.prompts = PromptIntelligenceService()
        self.tone = ToneIntelligenceService()
        self.blueprints = BlueprintService()
        self.compiler = ContextCompilerService()
        self.brand_intelligence = BrandIntelligenceService()
        self.resolution = ContextResolutionService()
        self.trace = GenerationTraceService()
        self.storage = LocalObjectStorage()

    def _fallback_creative_decision(
        self,
        request: AIOrchestrationRequest,
        compiled_context: dict[str, Any],
    ) -> dict[str, Any]:
        planning_hints = dict(request.layout_decision or {})
        template_candidates = request.template_candidates or []
        hinted_mode = str(planning_hints.get("mode") or compiled_context.get("template_fit_brief", {}).get("mode") or "synthesized_layout")
        selected_template_id = str(planning_hints.get("template_id") or "").strip() or None
        reasoning = list(planning_hints.get("rationale") or planning_hints.get("reasoning") or [])
        if not reasoning:
            reasoning = ["Generated from backend planning hints while AI creative planning is unavailable."]
        return {
            "layout_mode": hinted_mode,
            "selected_template_id": selected_template_id,
            "confidence": float(planning_hints.get("confidence") or 0.58),
            "reasoning": reasoning,
            "adaptations": dict(planning_hints.get("adaptation_plan") or planning_hints.get("adaptations") or {}),
            "asset_strategy": dict(planning_hints.get("asset_strategy") or {}),
            "template_candidates": template_candidates[:6],
            "planning_hints": planning_hints,
        }

    @staticmethod
    def _normalize_template_lookup_key(value: object) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        text = re.sub(r"^[a-z]+://", "", text.casefold())
        text = text.rsplit("/", 1)[-1]
        text = text.rsplit("\\", 1)[-1]
        text = text.split("?", 1)[0]
        text = text.rsplit(".", 1)[0]
        text = re.sub(r"-[0-9a-f]{8,}$", "", text)
        text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
        return text

    @classmethod
    def _sequence_reference_signature(cls, value: object) -> tuple[str, int] | None:
        normalized = cls._normalize_template_lookup_key(value)
        if not normalized:
            return None
        match = re.match(r"^(?P<prefix>.+?)-(?P<index>\d{1,3})$", normalized)
        if not match:
            return None
        prefix = str(match.group("prefix") or "").strip("-")
        index = int(match.group("index") or 0)
        if not prefix or index <= 0:
            return None
        return prefix, index

    @classmethod
    def _storage_reference_candidates(cls, value: object) -> list[str]:
        raw = str(value or "").strip()
        if not raw:
            return []
        candidates: list[str] = [raw]
        try:
            parsed = urlparse(raw)
            query = parse_qs(parsed.query or "")
        except Exception:  # pragma: no cover - defensive parsing fallback
            query = {}
        for key in ("storage_path", "filename"):
            for item in query.get(key) or []:
                text = str(item or "").strip()
                if text:
                    candidates.append(text)
        for token in query.get("token") or []:
            token_payload = str(token or "").split(".", 1)[0].strip()
            if not token_payload:
                continue
            try:
                padding = "=" * (-len(token_payload) % 4)
                decoded = base64.urlsafe_b64decode(f"{token_payload}{padding}")
                payload = json.loads(decoded.decode("utf-8"))
            except Exception:  # pragma: no cover - corrupt or unexpected token
                continue
            if not isinstance(payload, dict):
                continue
            for key in ("storage_path", "filename"):
                text = str(payload.get(key) or "").strip()
                if text:
                    candidates.append(text)
        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = candidate.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
        return deduped

    @classmethod
    def _resolve_template_candidate_identifier(
        cls,
        template_reference: str | None,
        *,
        template_name: str | None = None,
        template_candidates: list[dict[str, Any]] | None = None,
    ) -> str | None:
        raw_reference = str(template_reference or "").strip()
        if raw_reference and re.fullmatch(r"[0-9a-fA-F-]{36}", raw_reference):
            return raw_reference
        normalized_targets = {
            cls._normalize_template_lookup_key(template_reference),
            cls._normalize_template_lookup_key(template_name),
        }
        if raw_reference:
            normalized_targets.add(cls._normalize_template_lookup_key(raw_reference))
        normalized_targets.discard("")
        for candidate in template_candidates or []:
            if not isinstance(candidate, dict):
                continue
            candidate_id = str(candidate.get("template_id") or "").strip()
            candidate_name = str(candidate.get("name") or "").strip()
            if not candidate_id:
                continue
            if cls._normalize_template_lookup_key(candidate_id) in normalized_targets:
                return candidate_id
            if cls._normalize_template_lookup_key(candidate_name) in normalized_targets:
                return candidate_id
        return raw_reference or None

    @classmethod
    def _template_sequence_pack(
        cls,
        request: AIOrchestrationRequest,
        creative_decision: CreativeDecisionPayload | None = None,
    ) -> dict[str, Any] | None:
        template_context = request.template_context if isinstance(request.template_context, dict) else {}
        pack = template_context.get("sequence_pack")
        if not isinstance(pack, dict):
            return None
        slides = pack.get("slides")
        if not isinstance(slides, list) or not slides:
            return None
        normalized_slides = [dict(item) for item in slides if isinstance(item, dict)]
        if not normalized_slides:
            return None
        normalized_slides.sort(key=lambda item: int(item.get("slide_index") or 0))
        return {
            **pack,
            "slide_count": max(int(pack.get("slide_count") or len(normalized_slides)), len(normalized_slides)),
            "slides": normalized_slides,
        }

    @classmethod
    def _sequence_pack_style_reference_surface_paths(
        cls,
        request: AIOrchestrationRequest,
        creative_decision: CreativeDecisionPayload | None = None,
    ) -> set[str]:
        pack = cls._template_sequence_pack(request, creative_decision=creative_decision)
        if not isinstance(pack, dict):
            return set()
        surface_policy = str(pack.get("surface_policy") or "").strip().lower()
        if surface_policy != "style_reference_only":
            return set()
        paths: set[str] = set()
        for slide in [dict(item) for item in pack.get("slides", []) if isinstance(item, dict)]:
            for key in ("reference_asset_path", "template_asset_path"):
                value = str(slide.get(key) or "").strip()
                if value:
                    paths.add(value)
        return paths

    @staticmethod
    def _structured_list_items(value: Any) -> list[str]:
        if isinstance(value, str):
            text = value
        else:
            text = AIOrchestratorService._coerce_text_value(value)
        if not text:
            return []
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if "\n" not in normalized:
            return []
        pattern = re.compile(
            r"(?:^|\n)\s*(?:\d+[.)]|[-*])\s+(.*?)(?=(?:\n\s*(?:\d+[.)]|[-*])\s+)|$)",
            re.S,
        )
        items = [
            AIOrchestratorService._sanitize_text_for_canvas(" ".join(match.group(1).split()))
            for match in pattern.finditer(normalized)
        ]
        cleaned = [item for item in items if item]
        return cleaned if len(cleaned) >= 2 else []

    @classmethod
    def _should_force_sequence_pack(
        cls,
        request: AIOrchestrationRequest,
        creative_decision: CreativeDecisionPayload | None = None,
    ) -> bool:
        format_name = str(request.studio_panel.get("format") or "").strip().lower()
        if format_name != "carousel":
            return False
        template_context = request.template_context if isinstance(request.template_context, dict) else {}
        pack = template_context.get("sequence_pack")
        if not isinstance(pack, dict):
            return False
        surface_policy = str(pack.get("surface_policy") or "").strip().lower()
        if surface_policy != "lock_template_surface":
            return False
        slides = [dict(item) for item in pack.get("slides", []) if isinstance(item, dict)]
        if len(slides) < 3:
            return False
        explicit_template_id = str(
            (creative_decision.selected_template_id if creative_decision else None)
            or ((request.layout_decision or {}).get("template_id") if isinstance(request.layout_decision, dict) else "")
            or ""
        ).strip()
        if not explicit_template_id:
            explicit_template_id = str(pack.get("selected_template_id") or "").strip()
        if not explicit_template_id:
            return False
        if creative_decision and str(creative_decision.layout_mode or "").strip().lower() == "exact_template":
            return True
        return True

    @classmethod
    def _slide_reference_images(
        cls,
        slide: dict[str, Any],
        reference_images: list[dict[str, Any]],
        *,
        request: AIOrchestrationRequest | None = None,
        creative_decision: CreativeDecisionPayload | None = None,
    ) -> list[dict[str, Any]]:
        slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
        desired_path = str(slide_metadata.get("reference_asset_path") or "").strip()
        desired_template_name = str(slide_metadata.get("reference_template_name") or "").strip()
        desired_signature = cls._sequence_reference_signature(desired_template_name)
        slide_index = int(slide.get("slide_index") or slide_metadata.get("reference_slide_index") or 1)
        slide_count = int(slide.get("slide_count") or slide_metadata.get("reference_slide_count") or 1)
        preferred_paths = cls._preferred_sequence_reference_paths(request, creative_decision=creative_decision)
        blocked_sequence_surface_paths: set[str] = set()
        if request is not None and creative_decision is not None:
            blocked_sequence_surface_paths = cls._sequence_pack_style_reference_surface_paths(
                request,
                creative_decision=creative_decision,
            )
        usable_reference_images = [
            dict(asset)
            for asset in reference_images
            if isinstance(asset, dict)
            and (
                str(asset.get("storage_path") or "").strip() not in blocked_sequence_surface_paths
                or str(asset.get("storage_path") or "").strip() in preferred_paths
            )
        ]
        if desired_path and (desired_path not in blocked_sequence_surface_paths or desired_path in preferred_paths):
            matched = [
                dict(asset)
                for asset in usable_reference_images
                if str(asset.get("storage_path") or "").strip() == desired_path
            ]
            if matched:
                topical_matches = cls._topic_relevant_reference_assets(
                    request,
                    creative_decision=creative_decision,
                    source_assets=usable_reference_images,
                    limit=2,
                )
                desired_score = max(
                    cls._reference_asset_topic_score(asset, request=request)
                    for asset in matched
                ) if request is not None else 0
                topical_score = max(
                    [cls._reference_asset_topic_score(asset, request=request) for asset in topical_matches]
                    or [0]
                ) if request is not None else 0
                if topical_matches and topical_score > max(desired_score, 0):
                    return cls._prepare_slide_reference_assets(
                        cls._merge_reference_asset_lists(matched, topical_matches),
                        slide_index=slide_index,
                        slide_count=slide_count,
                    )
                return cls._prepare_slide_reference_assets(
                    matched,
                    slide_index=slide_index,
                    slide_count=slide_count,
                )
            if request is not None:
                matched_asset = cls._reference_asset_by_storage_path(request, desired_path)
                if matched_asset is not None:
                    return cls._prepare_slide_reference_assets(
                        [matched_asset],
                        slide_index=slide_index,
                        slide_count=slide_count,
                    )
        if desired_signature:
            matched = []
            for asset in usable_reference_images:
                asset_signature = cls._sequence_reference_signature(
                    str((asset.get("metadata") or {}).get("label") or asset.get("storage_path") or "")
                )
                if asset_signature == desired_signature:
                    matched.append(dict(asset))
            if matched:
                return cls._prepare_slide_reference_assets(
                    matched,
                    slide_index=slide_index,
                    slide_count=slide_count,
                )
        return cls._prepare_slide_reference_assets(
            usable_reference_images,
            slide_index=slide_index,
            slide_count=slide_count,
        )

    @classmethod
    def _prepare_slide_reference_assets(
        cls,
        assets: list[dict[str, Any]],
        *,
        slide_index: int,
        slide_count: int,
    ) -> list[dict[str, Any]]:
        prepared: list[dict[str, Any]] = []
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            prepared_asset = dict(asset)
            page_index = cls._reference_asset_slide_page_index(
                prepared_asset,
                slide_index=slide_index,
                slide_count=slide_count,
            )
            if page_index is not None:
                metadata = dict(prepared_asset.get("metadata") or {})
                metadata["conditioning_page_index"] = page_index
                prepared_asset["metadata"] = metadata
            prepared.append(prepared_asset)
        return prepared

    @classmethod
    def _reference_asset_declared_page_count(cls, asset: dict[str, Any]) -> int:
        for candidate in (
            asset.get("page_count"),
            ((asset.get("metadata") or {}) if isinstance(asset.get("metadata"), dict) else {}).get("page_count"),
            ((asset.get("analysis") or {}) if isinstance(asset.get("analysis"), dict) else {}).get("page_count"),
        ):
            try:
                value = int(candidate)
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        return 0

    @classmethod
    def _reference_asset_slide_page_index(
        cls,
        asset: dict[str, Any],
        *,
        slide_index: int,
        slide_count: int,
    ) -> int | None:
        mime_type = str(asset.get("mime_type") or "").strip().lower()
        if mime_type != "application/pdf":
            return None
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        for candidate in (
            metadata.get("conditioning_page_index"),
            metadata.get("reference_page_index"),
            metadata.get("page_index"),
            metadata.get("page_number"),
        ):
            try:
                explicit = int(candidate)
            except (TypeError, ValueError):
                continue
            if explicit > 0:
                return explicit
        page_count = cls._reference_asset_declared_page_count(asset)
        if page_count <= 1:
            return 1
        normalized_slide_count = max(int(slide_count or 1), 1)
        normalized_slide_index = min(max(int(slide_index or 1), 1), normalized_slide_count)
        if normalized_slide_count == 1:
            return 1
        proportional = round(((normalized_slide_index - 1) / max(normalized_slide_count - 1, 1)) * (page_count - 1)) + 1
        return min(max(int(proportional), 1), page_count)

    @staticmethod
    def _merge_partial_sequence_specs(
        incoming: Any,
        fallback: Any,
        *,
        number_keys: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        fallback_items = [dict(item) for item in (fallback or []) if isinstance(item, dict)]
        incoming_items = [dict(item) for item in (incoming or []) if isinstance(item, dict)]
        if not incoming_items:
            return fallback_items
        if not fallback_items:
            return incoming_items
        if len(incoming_items) >= len(fallback_items):
            return incoming_items

        merged = [dict(item) for item in fallback_items]

        def _match_index(item: dict[str, Any], position: int) -> int | None:
            for key in number_keys:
                value = item.get(key)
                if isinstance(value, bool):
                    continue
                if isinstance(value, int) and 1 <= value <= len(merged):
                    return value - 1
                text = str(value or "").strip()
                if text.isdigit():
                    parsed = int(text)
                    if 1 <= parsed <= len(merged):
                        return parsed - 1
            if 0 <= position < len(merged):
                return position
            return None

        for position, item in enumerate(incoming_items):
            match_index = _match_index(item, position)
            if match_index is None:
                merged.append(item)
                continue
            existing = dict(merged[match_index] or {})
            merged[match_index] = {**existing, **item}
        return merged

    @classmethod
    def _preferred_sequence_reference_paths(
        cls,
        request: AIOrchestrationRequest | None,
        *,
        creative_decision: CreativeDecisionPayload | None = None,
    ) -> set[str]:
        if request is None:
            return set()
        pack = cls._template_sequence_pack(request, creative_decision=creative_decision)
        if not isinstance(pack, dict):
            return set()
        paths: set[str] = set()
        for slide in [item for item in (pack.get("slides") or []) if isinstance(item, dict)]:
            for key in ("reference_asset_path", "template_asset_path"):
                path = str(slide.get(key) or "").strip()
                if not path:
                    continue
                matched = cls._reference_asset_by_storage_path(request, path)
                if matched is not None:
                    storage_path = str(matched.get("storage_path") or "").strip()
                    if storage_path:
                        paths.add(storage_path)
                        continue
                paths.add(path)
        return paths

    @classmethod
    def _reference_asset_by_storage_path(
        cls,
        request: AIOrchestrationRequest,
        storage_path: str,
    ) -> dict[str, Any] | None:
        desired = str(storage_path or "").strip()
        if not desired:
            return None
        desired_candidates = cls._storage_reference_candidates(desired)
        desired_path_texts = {candidate.casefold() for candidate in desired_candidates if candidate}
        desired_filenames = {
            candidate.rsplit("/", 1)[-1].strip().casefold()
            for candidate in desired_candidates
            if "/" in candidate or "." in candidate
        }
        desired_signatures = {
            signature
            for signature in (cls._sequence_reference_signature(candidate) for candidate in desired_candidates)
            if signature is not None
        }
        for asset in (request.asset_catalog or request.reference_assets or []):
            if not isinstance(asset, dict):
                continue
            if not cls._reference_asset_is_visual_source(asset):
                continue
            asset_storage_path = str(asset.get("storage_path") or "").strip()
            asset_storage_path_text = asset_storage_path.casefold()
            asset_filename = asset_storage_path.rsplit("/", 1)[-1].strip().casefold()
            asset_label_signature = cls._sequence_reference_signature(
                str(((asset.get("metadata") or {}) if isinstance(asset.get("metadata"), dict) else {}).get("label") or asset_storage_path)
            )
            if asset_storage_path in desired_candidates:
                return dict(asset)
            if asset_storage_path_text and any(asset_storage_path_text in text for text in desired_path_texts):
                return dict(asset)
            if asset_filename and asset_filename in desired_filenames:
                return dict(asset)
            if asset_label_signature and asset_label_signature in desired_signatures:
                return dict(asset)
        return None

    @classmethod
    def _catalog_asset_by_storage_path(
        cls,
        request: AIOrchestrationRequest,
        storage_path: str,
    ) -> dict[str, Any] | None:
        desired = str(storage_path or "").strip()
        if not desired:
            return None
        desired_candidates = cls._storage_reference_candidates(desired)
        desired_path_texts = {candidate.casefold() for candidate in desired_candidates if candidate}
        desired_filenames = {
            candidate.rsplit("/", 1)[-1].strip().casefold()
            for candidate in desired_candidates
            if "/" in candidate or "." in candidate
        }
        for asset in (request.asset_catalog or request.reference_assets or []):
            if not isinstance(asset, dict):
                continue
            asset_storage_path = str(asset.get("storage_path") or "").strip()
            if not asset_storage_path:
                continue
            asset_storage_path_text = asset_storage_path.casefold()
            asset_filename = asset_storage_path.rsplit("/", 1)[-1].strip().casefold()
            if asset_storage_path in desired_candidates:
                return dict(asset)
            if asset_storage_path_text and any(asset_storage_path_text in text for text in desired_path_texts):
                return dict(asset)
            if asset_filename and asset_filename in desired_filenames:
                return dict(asset)
        return None

    @classmethod
    def _compact_slide_geometry_contract(
        cls,
        slide: dict[str, Any],
        scene_graph: GenerationSceneGraph,
        *,
        limit: int = 10,
    ) -> str:
        slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
        zone_map = slide_metadata.get("reference_zone_map") if isinstance(slide_metadata.get("reference_zone_map"), dict) else {}
        raw_zones = zone_map.get("zones") if isinstance(zone_map.get("zones"), list) else []
        geometry_manifest: list[dict[str, Any]] = []
        for item in raw_zones[:limit]:
            if not isinstance(item, dict):
                continue
            role = cls._normalize_metadata_text(item.get("role"), limit=32).casefold()
            x = item.get("x")
            y = item.get("y")
            w = item.get("w") if item.get("w") is not None else item.get("width")
            h = item.get("h") if item.get("h") is not None else item.get("height")
            if not role or any(value is None for value in (x, y, w, h)):
                continue
            try:
                geometry_manifest.append(
                    {
                        "role": role,
                        "type": "reference_zone",
                        "x": round(float(x), 3),
                        "y": round(float(y), 3),
                        "w": round(float(w), 3),
                        "h": round(float(h), 3),
                    }
                )
            except (TypeError, ValueError):
                continue
        if geometry_manifest:
            return json.dumps(geometry_manifest, separators=(",", ":"), ensure_ascii=True)
        return cls._compact_scene_graph_geometry(scene_graph, limit=limit)

    @staticmethod
    def _zone_position_label(x: float, y: float, w: float, h: float) -> str:
        center_x = x + (w / 2.0)
        center_y = y + (h / 2.0)
        vertical = "top" if center_y < 0.34 else "bottom" if center_y > 0.66 else "middle"
        horizontal = "left" if center_x < 0.34 else "right" if center_x > 0.66 else "center"
        if vertical == "middle" and horizontal == "center":
            return "center"
        if vertical == "middle":
            return horizontal
        if horizontal == "center":
            return vertical
        return f"{vertical}-{horizontal}"

    @classmethod
    def _reference_zone_layout_guidance(
        cls,
        slide: dict[str, Any],
        *,
        limit: int = 6,
    ) -> str:
        slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
        zone_map = slide_metadata.get("reference_zone_map") if isinstance(slide_metadata.get("reference_zone_map"), dict) else {}
        raw_zones = zone_map.get("zones") if isinstance(zone_map.get("zones"), list) else []
        normalized_zones: list[dict[str, Any]] = []
        for item in raw_zones:
            if not isinstance(item, dict):
                continue
            role = cls._normalize_metadata_text(item.get("role"), limit=32).casefold()
            x = item.get("x")
            y = item.get("y")
            w = item.get("w") if item.get("w") is not None else item.get("width")
            h = item.get("h") if item.get("h") is not None else item.get("height")
            if not role or any(value is None for value in (x, y, w, h)):
                continue
            try:
                zone = {
                    "role": role,
                    "x": float(x),
                    "y": float(y),
                    "w": float(w),
                    "h": float(h),
                }
            except (TypeError, ValueError):
                continue
            if zone["w"] <= 0.0 or zone["h"] <= 0.0:
                continue
            normalized_zones.append(zone)
        if not normalized_zones:
            return ""
        snippets: list[str] = []
        seen_roles: dict[str, int] = {}
        for zone in sorted(normalized_zones, key=lambda item: (item["y"], item["x"]))[:limit]:
            role = zone["role"]
            seen_roles[role] = seen_roles.get(role, 0) + 1
            role_label = role.replace("_", " ")
            if seen_roles[role] == 2:
                role_label = f"secondary {role_label}"
            elif seen_roles[role] > 2:
                role_label = f"{role_label} {seen_roles[role]}"
            position = cls._zone_position_label(zone["x"], zone["y"], zone["w"], zone["h"])
            width_label = "wide" if zone["w"] >= 0.55 else "compact" if zone["w"] <= 0.22 else ""
            height_label = "tall" if zone["h"] >= 0.22 else "shallow" if zone["h"] <= 0.08 else ""
            size_label = " ".join(part for part in [width_label, height_label] if part).strip()
            snippets.append(
                " ".join(
                    part
                    for part in [
                        role_label,
                        "block",
                        f"at the {position}",
                        f"({size_label})" if size_label else "",
                    ]
                    if part
                ).strip()
            )
        layout_type = cls._normalize_metadata_text(zone_map.get("layout_type"), limit=64)
        prefix = f"{layout_type} layout summary" if layout_type else "Reference slide layout summary"
        return f"{prefix}: {'; '.join(snippets)}."

    @classmethod
    def _request_has_authoritative_reference_zone_maps(
        cls,
        request: AIOrchestrationRequest | None,
    ) -> bool:
        if request is None:
            return False
        template_context = request.template_context if isinstance(request.template_context, dict) else {}
        sequence_pack = template_context.get("sequence_pack") if isinstance(template_context.get("sequence_pack"), dict) else {}
        for slide in [item for item in (sequence_pack.get("slides") or []) if isinstance(item, dict)]:
            zone_map = slide.get("zone_map") if isinstance(slide.get("zone_map"), dict) else {}
            raw_zones = zone_map.get("zones")
            if isinstance(raw_zones, list) and len(raw_zones) >= 3:
                return True
        return False

    @classmethod
    def _should_block_low_quality_final_render(cls, assessment: dict[str, Any]) -> bool:
        score = float(assessment.get("score") or 0.0)
        issues = {str(item).strip() for item in (assessment.get("issues") or []) if str(item).strip()}
        hard_failure_issues = {
            "missing_headline",
            "missing_primary_visual",
            "weak_geometry_contract",
            "sample_structure_underused",
            "sparse_scene_graph",
            "craft_direction_weak",
            "reference_family_zone_drift",
            "reference_family_layout_drift",
            "reference_family_geometry_drift",
        }
        if score < 0.62:
            return True
        return score < cls.IMAGE_QUALITY_MIN_SCORE and bool(issues & hard_failure_issues)

    def _fallback_message_strategy(
        self,
        request: AIOrchestrationRequest,
        compiled_context: dict[str, Any],
    ) -> dict[str, Any]:
        brand_copy_brief = compiled_context.get("brand_copy_brief", {}) or {}
        objective_brief = {
            **self._coerce_mapping(request.objective_context),
            **self._coerce_mapping(compiled_context.get("objective_brief")),
        }
        audience_brief = self._coerce_mapping(compiled_context.get("audience_brief"))
        audience_insights = self._coerce_mapping(request.resolved_brand_context.get("audience_insights"))
        persona_context = self._coerce_mapping(request.persona_context)
        knowledge_brief = compiled_context.get("knowledge_brief", []) or []
        prompt_intelligence_brief = compiled_context.get("prompt_intelligence_brief", {}) or {}
        prompt_starter_texts = self._normalize_metadata_list(prompt_intelligence_brief.get("starter_texts"), limit=4)
        prompt_platform_rules = self._normalize_metadata_list(prompt_intelligence_brief.get("current_platform_rules"), limit=4)
        prompt_global_rules = self._normalize_metadata_list(prompt_intelligence_brief.get("global_rules"), limit=4)
        prompt_intelligence_summary = self._coerce_text_value(prompt_intelligence_brief.get("summary"), "")
        audience_research_highlights = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(audience_brief.get("research_highlights"), limit=5),
                *self._normalize_metadata_list(audience_insights.get("research_highlights"), limit=5),
            ],
            limit=5,
        )
        audience_research_summary = self._coerce_text_value(
            audience_brief.get("research_summary") or audience_insights.get("research_summary"),
            "",
        )
        audience_research_note = self._coerce_text_value(
            " ".join(audience_research_highlights[:4]) or audience_research_summary,
            "",
        )
        audience_motivations = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(
                    audience_brief.get("audience_research_motivations") or audience_brief.get("motivations"),
                    limit=4,
                ),
                *self._normalize_metadata_list(audience_insights.get("motivations"), limit=4),
            ],
            limit=4,
        )
        audience_desired_outcomes = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(audience_brief.get("desired_outcomes"), limit=4),
                *self._normalize_metadata_list(audience_insights.get("desired_outcomes"), limit=4),
            ],
            limit=4,
        )
        audience_trust_signals = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(audience_brief.get("trust_signals"), limit=4),
                *self._normalize_metadata_list(audience_insights.get("trust_signals"), limit=4),
            ],
            limit=4,
        )
        audience_proof_cues = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(audience_brief.get("proof_cues"), limit=4),
                *self._normalize_metadata_list(audience_insights.get("proof_cues"), limit=4),
            ],
            limit=4,
        )
        audience_comparison_points = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(audience_brief.get("comparison_points"), limit=4),
                *self._normalize_metadata_list(audience_insights.get("comparison_points"), limit=4),
            ],
            limit=4,
        )
        audience_objections = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(
                    audience_brief.get("audience_research_objections") or audience_brief.get("objections"),
                    limit=4,
                ),
                *self._normalize_metadata_list(audience_insights.get("objections"), limit=4),
            ],
            limit=4,
        )
        persona_summary = self._coerce_text_value(
            brand_copy_brief.get("persona_messaging_summary")
            or audience_brief.get("persona_summary")
            or audience_insights.get("persona_summary")
            or persona_context.get("summary"),
            "",
        )
        persona_motivations = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(audience_brief.get("persona_motivations"), limit=4),
                *self._normalize_metadata_list(persona_context.get("motivations"), limit=4),
                *self._normalize_metadata_list(brand_copy_brief.get("persona_motivations"), limit=4),
            ],
            limit=4,
        )
        persona_pain_points = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(audience_brief.get("persona_pain_points"), limit=4),
                *self._normalize_metadata_list(persona_context.get("pain_points"), limit=4),
                *self._normalize_metadata_list(persona_context.get("fears_and_pain_points"), limit=4),
                *self._normalize_metadata_list(brand_copy_brief.get("persona_pain_points"), limit=4),
            ],
            limit=4,
        )
        persona_objections = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(audience_brief.get("persona_objections"), limit=4),
                *self._normalize_metadata_list(persona_context.get("objections"), limit=4),
                *self._normalize_metadata_list(brand_copy_brief.get("persona_objections"), limit=4),
            ],
            limit=4,
        )
        persona_language_preference = self._coerce_text_value(
            brand_copy_brief.get("persona_language_preference")
            or audience_brief.get("persona_language_preference")
            or audience_brief.get("language_preference")
            or audience_insights.get("language_preference")
            or persona_context.get("language_preference"),
            "",
        )
        audience_evidence_note = self._coerce_text_value(
            " ".join(
                [
                    *audience_desired_outcomes[:1],
                    *audience_proof_cues[:1],
                    *audience_comparison_points[:1],
                    *audience_trust_signals[:1],
                ]
            ),
            "",
        )
        primary_motivations = audience_motivations or persona_motivations
        primary_pain_points = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(
                    audience_brief.get("audience_research_pain_points") or audience_brief.get("pain_points"),
                    limit=4,
                ),
                *self._normalize_metadata_list(audience_insights.get("pain_points"), limit=4),
            ],
            limit=4,
        ) or persona_pain_points
        primary_objections = audience_objections or persona_objections
        prompt_topic = self._fallback_topic_focus(request.prompt, compiled_context=compiled_context)
        primary_research_highlight = audience_research_highlights[0] if audience_research_highlights else ""
        semantic_support_phrase = self._topic_specific_detail_lens(prompt_topic)
        fallback_primary_theme = self._coerce_text_value(
            prompt_topic
            or objective_brief.get("name")
            or objective_brief.get("primary_goal")
            or objective_brief.get("description")
            or brand_copy_brief.get("objective_focus")
            or brand_copy_brief.get("brand_description")
            or "Brand-led social campaign"
        )
        objection_grounding = (audience_proof_cues or audience_trust_signals or audience_research_highlights)[:1]
        objection_reassurance = self._coerce_text_value(
            (
                f"Address the objection '{primary_objections[0]}' with specific reassurance and ground it in '{objection_grounding[0]}'."
                if primary_objections and objection_grounding
                else f"Address the objection '{primary_objections[0]}' with specific reassurance and credible proof."
                if primary_objections
                else ""
            ),
            "",
        )
        pain_point_framing = self._coerce_text_value(
            (
                f"Lead from the pain point '{primary_pain_points[0]}' and resolve it with a clear benefit."
                if primary_pain_points
                else ""
            ),
            "",
        )
        prompt_text = self._coerce_text_value(request.prompt)
        keywords = [
            word
            for word in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", prompt_text)
            if word.casefold() not in self.PROMPT_ECHO_STOPWORDS
        ][:6]
        knowledge_line = ""
        if knowledge_brief:
            first_item = knowledge_brief[0] if isinstance(knowledge_brief[0], dict) else {}
            knowledge_line = self._coerce_text_value(first_item.get("content"), "")
        key_value_focus = self._coerce_text_value(
            (
                audience_desired_outcomes[0]
                if audience_desired_outcomes
                else audience_comparison_points[0]
                if audience_comparison_points
                else ""
            )
            or objective_brief.get("primary_goal")
            or objective_brief.get("description")
            or brand_copy_brief.get("brand_foundations")
            or "MISSING"
        )
        return {
            "primary_campaign_theme": fallback_primary_theme[:140] or "Brand-led social campaign",
            "core_audience_message": self._coerce_text_value(
                audience_research_note
                or audience_evidence_note
                or persona_summary
                or objective_brief.get("description")
                or prompt_intelligence_summary
                or knowledge_line
                or brand_copy_brief.get("brand_description")
                or "MISSING"
            ),
            "headline_direction": self._coerce_text_value(
                objective_brief.get("market_positioning")
                or (prompt_starter_texts[0] if prompt_starter_texts else "")
                or (f"Lead with the outcome '{audience_desired_outcomes[0]}'" if audience_desired_outcomes else "")
                or (f"Lead with the benefit '{primary_motivations[0]}'" if primary_motivations else "")
                or self._contextual_headline_fallback(
                    topic_focus=prompt_topic,
                    motivation=primary_motivations[0] if primary_motivations else "",
                    pain_point=primary_pain_points[0] if primary_pain_points else "",
                    research_highlight=audience_research_note or primary_research_highlight,
                    brand_foundations=brand_copy_brief.get("brand_foundations"),
                    knowledge_line=knowledge_line,
                    primary_goal=objective_brief.get("primary_goal"),
                    semantic_support_phrase=semantic_support_phrase,
                )
            ),
            "supporting_copy_direction": self._coerce_text_value(
                prompt_intelligence_summary
                or (prompt_platform_rules[0] if prompt_platform_rules else "")
                or objection_reassurance
                or pain_point_framing
                or audience_research_note
                or audience_evidence_note
                or (
                    f"Keep the copy readable for {persona_language_preference} language preference."
                    if persona_language_preference
                    else ""
                )
                or persona_summary
                or knowledge_line
                or (prompt_global_rules[0] if prompt_global_rules else "")
                or self._contextual_supporting_fallback(
                    topic_focus=prompt_topic,
                    motivation=primary_motivations[0] if primary_motivations else "",
                    pain_point=primary_pain_points[0] if primary_pain_points else "",
                    objection=primary_objections[0] if primary_objections else "",
                    brand_foundations=brand_copy_brief.get("brand_foundations"),
                    research_highlight=primary_research_highlight,
                    knowledge_line=knowledge_line,
                    semantic_support_phrase=semantic_support_phrase,
                )
            ),
            "cta_intent": self._coerce_text_value(
                objective_brief.get("cta_bias")
                or (prompt_platform_rules[1] if len(prompt_platform_rules) > 1 else "")
                or (prompt_global_rules[1] if len(prompt_global_rules) > 1 else "")
                or (prompt_platform_rules[0] if len(prompt_platform_rules) == 1 else "")
                or self._contextual_cta_fallback(
                    topic_focus=prompt_topic or fallback_primary_theme,
                    primary_goal=objective_brief.get("primary_goal"),
                    pain_point=primary_pain_points[0] if primary_pain_points else "",
                    objection=primary_objections[0] if primary_objections else "",
                )
            ),
            "key_value_proposition": key_value_focus,
            "important_keywords": keywords or ["MISSING"],
            "emotional_messaging_direction": self._coerce_text_value(
                brand_copy_brief.get("primary_emotion") or "MISSING"
            ),
            "what_must_be_avoided_in_messaging": self._normalize_metadata_list(
                brand_copy_brief.get("donts") or [brand_copy_brief.get("avoided_emotion") or "MISSING"],
                limit=6,
            )
            or ["MISSING"],
        }

    @staticmethod
    def _infer_layout_type(prompt: str, studio_panel: dict[str, Any], text_payload: dict[str, Any]) -> str:
        lowered_prompt = prompt.lower()
        format_name = str(studio_panel.get("format") or "static")
        if format_name == "infographic":
            return "infographic_stack"
        if any(token in lowered_prompt for token in ["tips", "tip", "strategies", "strategy", "steps", "checklist", "how to"]):
            return "checklist_card"
        if any(token in lowered_prompt for token in ["compare", "comparison", "versus", "vs "]):
            return "comparison_board"
        if len(str(text_payload.get("body") or "")) > 220:
            return "insight_split"
        return "editorial_hero"

    @staticmethod
    def _normalized_box(x: float, y: float, width: float, height: float) -> dict[str, Any]:
        return {"x": x, "y": y, "width": width, "height": height, "units": "normalized"}

    @staticmethod
    def _logo_safe_zone_geometry(scene_graph: GenerationSceneGraph | None) -> tuple[float, float, float, float] | None:
        if not isinstance(scene_graph, GenerationSceneGraph):
            return None
        for element in scene_graph.elements or []:
            role = str(element.role or element.element_type or "").strip().lower()
            if role != "logo":
                continue
            geometry = element.geometry
            try:
                x = float(geometry.x if geometry.x is not None else 0.0)
                y = float(geometry.y if geometry.y is not None else 0.0)
                width = float(geometry.width if geometry.width is not None else 0.0)
                height = float(geometry.height if geometry.height is not None else 0.0)
            except (TypeError, ValueError):
                return None
            if width <= 0 or height <= 0:
                return None
            units = str(geometry.units or "normalized").strip().lower()
            canvas_width = max(int(scene_graph.canvas.width or 1080), 1)
            canvas_height = max(int(scene_graph.canvas.height or 1080), 1)
            if units == "normalized" or max(abs(x), abs(y), abs(width), abs(height)) <= 1.5:
                return (x, y, width, height)
            return (
                x / canvas_width,
                y / canvas_height,
                width / canvas_width,
                height / canvas_height,
            )
        return None

    @classmethod
    def _logo_anchor_from_hint(cls, hint: str | None) -> tuple[str, str] | None:
        text = str(hint or "").strip().lower()
        if not text:
            return None
        text = text.replace("buttom", "bottom")
        vertical = "top" if "top" in text else ("bottom" if "bottom" in text else "middle")
        horizontal = "right" if "right" in text else ("left" if "left" in text else "center")
        if vertical == "middle" and horizontal == "center" and "center" not in text and "middle" not in text:
            return None
        return (vertical, horizontal)

    @classmethod
    def _normalize_logo_position_option(cls, value: Any) -> str:
        text = cls._normalize_metadata_text(value, limit=80).casefold()
        if not text:
            return ""
        text = text.replace("_", "-").replace("buttom", "bottom")
        anchor = cls._logo_anchor_from_hint(text)
        if anchor is None:
            if "center" in text or "middle" in text:
                return "center"
            return ""
        vertical, horizontal = anchor
        if vertical == "middle" and horizontal == "center":
            return "center"
        if vertical == "middle":
            return f"center-{horizontal}"
        if horizontal == "center":
            return f"{vertical}-center"
        return f"{vertical}-{horizontal}"

    @classmethod
    def _brand_logo_placement_policy(cls, brand_context: dict[str, Any] | None) -> dict[str, Any]:
        visual_identity = (
            brand_context.get("visual_identity", {}) if isinstance(brand_context, dict) else {}
        ) or {}
        placement = (
            visual_identity.get("logo_placement")
            if isinstance(visual_identity.get("logo_placement"), dict)
            else {}
        )
        allowed_positions: list[str] = []
        for raw_value in placement.get("allowed_positions") or placement.get("positions") or []:
            normalized = cls._normalize_logo_position_option(raw_value)
            if normalized and normalized not in allowed_positions:
                allowed_positions.append(normalized)
        has_explicit_allowed_positions = bool(allowed_positions)
        default_position = cls._normalize_logo_position_option(
            placement.get("default_position")
            or placement.get("preferred_position")
            or placement.get("logo_position")
        )
        promoted_position = cls._normalize_logo_position_option(
            visual_identity.get("logo_position")
            or (
                (visual_identity.get("design_system") or {})
                if isinstance(visual_identity.get("design_system"), dict)
                else {}
            ).get("logo_anchor")
        )
        if has_explicit_allowed_positions:
            if default_position and default_position not in allowed_positions:
                default_position = ""
        else:
            default_position = default_position or promoted_position
        if not default_position and allowed_positions:
            default_position = allowed_positions[0]
        if allowed_positions and default_position and default_position not in allowed_positions:
            default_position = allowed_positions[0] if allowed_positions else ""
        return {
            "allowed_positions": allowed_positions,
            "default_position": (
                default_position
                if (not allowed_positions or default_position in allowed_positions)
                else (allowed_positions[0] if allowed_positions else "")
            ),
        }

    @classmethod
    def _logo_position_priority_for_request(
        cls,
        request: AIOrchestrationRequest,
        creative_decision: CreativeDecisionPayload | None = None,
    ) -> list[str]:
        format_name = str(request.studio_panel.get("format") or "").strip().lower()
        layout_mode = str((creative_decision.layout_mode if isinstance(creative_decision, CreativeDecisionPayload) else "") or "").strip().lower()
        if format_name == "infographic":
            priority = ["top-right", "top-left", "top-center", "bottom-right", "bottom-left", "bottom-center", "center"]
        elif format_name == "carousel":
            priority = ["top-right", "top-left", "bottom-right", "bottom-left", "top-center", "bottom-center", "center"]
        else:
            priority = ["top-right", "top-left", "top-center", "bottom-right", "bottom-left", "bottom-center", "center"]
        if "footer" in layout_mode or "bottom" in layout_mode:
            priority = ["top-right", "top-left", "top-center", "bottom-right", "bottom-left", "bottom-center", "center"]
        return priority

    @classmethod
    def _effective_logo_position_hint(
        cls,
        *,
        request: AIOrchestrationRequest,
        creative_decision: CreativeDecisionPayload,
        text_payload: dict[str, Any],
        scene_graph_payload: dict[str, Any] | None = None,
    ) -> str:
        policy = cls._brand_logo_placement_policy(request.resolved_brand_context)
        allowed_positions = policy.get("allowed_positions") or []
        default_position = str(policy.get("default_position") or "")
        metadata = text_payload.get("metadata") if isinstance(text_payload.get("metadata"), dict) else {}
        asset_strategy = creative_decision.asset_strategy or {}
        planning_hints = creative_decision.planning_hints or {}
        scene_graph_payload = scene_graph_payload or {}
        styles = scene_graph_payload.get("styles") if isinstance(scene_graph_payload.get("styles"), dict) else {}
        validation_hints = scene_graph_payload.get("validation_hints") if isinstance(scene_graph_payload.get("validation_hints"), dict) else {}
        for candidate in (
            metadata.get("logo_position"),
            planning_hints.get("logo_position"),
            asset_strategy.get("logo_position"),
            styles.get("logo_position"),
            validation_hints.get("logo_position"),
        ):
            normalized = cls._normalize_logo_position_option(candidate)
            if normalized and (not allowed_positions or normalized in allowed_positions):
                return normalized
        if default_position:
            return default_position
        if not allowed_positions:
            for candidate in cls._logo_position_priority_for_request(request, creative_decision):
                if candidate:
                    return candidate
        for candidate in cls._logo_position_priority_for_request(request, creative_decision):
            if candidate in allowed_positions:
                return candidate
        return ""

    @classmethod
    def _logo_reserved_area_label(cls, hint: str | None) -> str:
        normalized = cls._normalize_logo_position_option(hint)
        return normalized or "reserved logo-safe"

    @classmethod
    def _default_logo_safe_zone_geometry(
        cls,
        request: AIOrchestrationRequest,
        *,
        anchor: tuple[str, str] | None,
    ) -> tuple[float, float, float, float]:
        width, height = cls._logo_box_profile_for_panel(request.studio_panel)
        reference_geometry = cls._reference_logo_safe_zone_geometry(request=request, anchor=anchor)
        vertical, horizontal = anchor or ("top", "right")
        size = (request.studio_panel or {}).get("size")
        size = size if isinstance(size, dict) else {}
        canvas_width = max(int(size.get("width") or 1080), 1)
        canvas_height = max(int(size.get("height") or 1080), 1)
        if reference_geometry is not None:
            _ref_x, _ref_y, ref_width, ref_height = reference_geometry
            width = max(min(width, ref_width), width * 0.75)
            height = max(min(height, ref_height), height * 0.75)
        margin_x = min(20 / canvas_width, max(1.0 - width, 0.0))
        margin_y = min(20 / canvas_height, max(1.0 - height, 0.0))
        if horizontal == "left":
            x = margin_x
        elif horizontal == "center":
            x = max((1.0 - width) / 2.0, 0.0)
        else:
            x = max(1.0 - width - margin_x, 0.0)
        if vertical == "bottom":
            y = max(1.0 - height - margin_y, 0.0)
        elif vertical == "middle":
            y = max((1.0 - height) / 2.0, 0.0)
        else:
            y = margin_y
        return (x, y, width, height)

    @classmethod
    def _snap_logo_safe_zone_geometry_to_anchor_edge(
        cls,
        *,
        request: AIOrchestrationRequest,
        geometry: tuple[float, float, float, float],
        anchor: tuple[str, str],
    ) -> tuple[float, float, float, float]:
        x, y, width, height = geometry
        size = (request.studio_panel or {}).get("size")
        size = size if isinstance(size, dict) else {}
        canvas_width = max(int(size.get("width") or 1080), 1)
        canvas_height = max(int(size.get("height") or 1080), 1)
        margin_x = min(20 / canvas_width, max(1.0 - width, 0.0))
        margin_y = min(20 / canvas_height, max(1.0 - height, 0.0))
        vertical, horizontal = anchor
        if horizontal == "left":
            x = margin_x
        elif horizontal == "right":
            x = max(1.0 - width - margin_x, 0.0)
        elif horizontal == "center":
            x = max((1.0 - width) / 2.0, 0.0)
        if vertical == "top":
            y = margin_y
        elif vertical == "bottom":
            y = max(1.0 - height - margin_y, 0.0)
        elif vertical == "middle":
            y = max((1.0 - height) / 2.0, 0.0)
        return (x, y, width, height)

    @classmethod
    def _cap_logo_safe_zone_geometry_to_profile(
        cls,
        *,
        request: AIOrchestrationRequest,
        geometry: tuple[float, float, float, float],
    ) -> tuple[float, float, float, float]:
        x, y, width, height = geometry
        preferred_width, preferred_height = cls._logo_box_profile_for_panel(request.studio_panel)
        return (x, y, min(width, preferred_width), min(height, preferred_height))

    @staticmethod
    def _logo_box_profile_for_panel(studio_panel: dict[str, Any] | None) -> tuple[float, float]:
        panel = studio_panel or {}
        format_name = str(panel.get("format") or "").strip().lower()
        size = panel.get("size") if isinstance(panel.get("size"), dict) else {}
        width_px = max(int(size.get("width") or 1080), 1)
        height_px = max(int(size.get("height") or 1080), 1)
        aspect_ratio = width_px / max(height_px, 1)
        if format_name == "carousel":
            return (0.2, 0.085)
        if format_name == "infographic":
            return (0.19, 0.08)
        if aspect_ratio >= 1.3:
            return (0.15, 0.075)
        return (0.17, 0.075)

    @classmethod
    def _reference_logo_safe_zone_geometry(
        cls,
        *,
        request: AIOrchestrationRequest,
        anchor: tuple[str, str] | None,
    ) -> tuple[float, float, float, float] | None:
        if anchor is None:
            return None
        visual_identity = (
            request.resolved_brand_context.get("visual_identity", {})
            if isinstance(request.resolved_brand_context, dict)
            else {}
        ) or {}
        candidates: list[tuple[float, float, float, float]] = []

        def _zone_geometry(zone: Any) -> tuple[float, float, float, float] | None:
            payload = cls._coerce_mapping(zone)
            if not payload:
                return None
            try:
                x = float(payload.get("x"))
                y = float(payload.get("y"))
                width = float(payload.get("width") if payload.get("width") is not None else payload.get("w"))
                height = float(payload.get("height") if payload.get("height") is not None else payload.get("h"))
            except (TypeError, ValueError):
                return None
            if min(x, y, width, height) < 0:
                return None
            if max(x, y, width, height) > 1.5:
                return None
            if width <= 0 or height <= 0:
                return None
            return (x, y, width, height)

        def _collect(zones: Any) -> None:
            for zone in cls._coerce_list(zones):
                payload = cls._coerce_mapping(zone)
                if str(payload.get("role") or "").strip().lower() != "logo":
                    continue
                geometry = _zone_geometry(payload)
                if geometry is None:
                    continue
                if cls._logo_anchor_from_hint(cls._anchor_from_logo_geometry(geometry)) == anchor:
                    candidates.append(geometry)

        for reference in cls._coerce_list(visual_identity.get("reference_creatives")):
            payload = cls._coerce_mapping(reference)
            _collect(payload.get("reusable_zones"))
            layout_structure = cls._coerce_mapping(payload.get("layout_structure"))
            _collect(layout_structure.get("zones"))
        for template_info in cls._coerce_list(visual_identity.get("template_intelligence")):
            payload = cls._coerce_mapping(template_info)
            analysis = cls._coerce_mapping(payload.get("analysis"))
            _collect(analysis.get("reusable_zones"))
            _collect(analysis.get("editable_zones"))
        if not candidates:
            return None

        def _median(values: list[float]) -> float:
            ordered = sorted(values)
            return ordered[len(ordered) // 2]

        return (
            _median([item[0] for item in candidates]),
            _median([item[1] for item in candidates]),
            _median([item[2] for item in candidates]),
            _median([item[3] for item in candidates]),
        )

    @staticmethod
    def _normalize_logo_background_tone(value: Any) -> str:
        text = str(value or "").strip().casefold()
        if not text:
            return ""
        normalized = text.replace("-", "_").replace(" ", "_")
        if any(token in normalized for token in ("light_on_dark", "dark_surface", "dark_background", "reverse", "inverse", "negative")):
            return "dark"
        if any(token in normalized for token in ("dark_on_light", "light_surface", "light_background", "full_color", "full_colour")):
            return "light"
        if any(token in normalized for token in ("neutral", "balanced", "mid_tone", "midtone")):
            return "neutral"
        return ""

    @classmethod
    def _resolve_logo_background_tone(
        cls,
        *,
        metadata: dict[str, Any] | None = None,
        creative_decision: CreativeDecisionPayload | dict[str, Any] | None = None,
        scene_graph: GenerationSceneGraph | None = None,
    ) -> str:
        candidates: list[Any] = []
        metadata = metadata if isinstance(metadata, dict) else {}
        candidates.append(metadata.get("logo_background_tone"))
        if isinstance(creative_decision, CreativeDecisionPayload):
            asset_strategy = creative_decision.asset_strategy or {}
        elif isinstance(creative_decision, dict):
            asset_strategy = creative_decision.get("asset_strategy") if isinstance(creative_decision.get("asset_strategy"), dict) else {}
        else:
            asset_strategy = {}
        candidates.extend(
            [
                asset_strategy.get("logo_background_tone"),
                asset_strategy.get("background_variant"),
                asset_strategy.get("logo_variant"),
            ]
        )
        if isinstance(scene_graph, GenerationSceneGraph):
            for element in scene_graph.elements or []:
                if str(element.role or element.element_type or "").strip().lower() != "logo":
                    continue
                candidates.extend(
                    [
                        (element.validation_hints or {}).get("logo_background_tone"),
                        (element.style or {}).get("logo_background_tone"),
                        (element.validation_hints or {}).get("logo_variant"),
                        (element.style or {}).get("logo_variant"),
                        element.asset.variant if element.asset else None,
                    ]
                )
        for value in candidates:
            normalized = cls._normalize_logo_background_tone(value)
            if normalized:
                return normalized
        return ""

    @classmethod
    def _logo_surface_guidance(
        cls,
        *,
        background_tone: str | None,
    ) -> str:
        tone = cls._normalize_logo_background_tone(background_tone)
        if tone == "light":
            return (
                "Keep the reserved logo zone on a calm light surface with low texture, soft gradients only, and clean edge contrast so the exact overlaid logo and its transparent edges read crisply."
            )
        if tone == "dark":
            return (
                "Keep the reserved logo zone on a calm dark surface with low texture and stable contrast so the exact overlaid logo and its transparent edges read crisply."
            )
        return (
            "Keep the reserved logo zone on a smooth, visually quiet surface with stable contrast and no noisy texture, glass effects, or cutout-like detail so the exact overlaid logo and its transparent edges read cleanly."
        )

    @classmethod
    def _normalize_logo_safe_zone_geometry(
        cls,
        *,
        request: AIOrchestrationRequest,
        geometry: tuple[float, float, float, float] | None,
        hint: str | None = None,
    ) -> tuple[float, float, float, float]:
        hint_anchor = cls._logo_anchor_from_hint(hint)
        reference_geometry = cls._reference_logo_safe_zone_geometry(request=request, anchor=hint_anchor)
        if geometry is None:
            return cls._default_logo_safe_zone_geometry(request, anchor=hint_anchor)
        x, y, width, height = geometry
        center_x = x + (width / 2.0)
        center_y = y + (height / 2.0)
        vertical = "top" if center_y <= 0.35 else ("bottom" if center_y >= 0.65 else "middle")
        horizontal = "left" if center_x <= 0.35 else ("right" if center_x >= 0.65 else "center")
        current_anchor = (vertical, horizontal)
        anchor_mismatch = bool(hint_anchor and hint_anchor != current_anchor)
        min_width, min_height = cls._logo_box_profile_for_panel(request.studio_panel)
        too_small = width < (min_width * 0.65) or height < (min_height * 0.65)
        if anchor_mismatch or too_small:
            return cls._default_logo_safe_zone_geometry(request, anchor=hint_anchor or current_anchor)
        if reference_geometry is not None:
            _ref_x, _ref_y, ref_width, ref_height = reference_geometry
            width_gap = abs(width - ref_width)
            height_gap = abs(height - ref_height)
            if width_gap >= 0.035 or height_gap >= 0.025:
                return cls._default_logo_safe_zone_geometry(request, anchor=hint_anchor or current_anchor)
        geometry = cls._cap_logo_safe_zone_geometry_to_profile(
            request=request,
            geometry=geometry,
        )
        return cls._snap_logo_safe_zone_geometry_to_anchor_edge(
            request=request,
            geometry=geometry,
            anchor=hint_anchor or current_anchor,
        )

    @classmethod
    def _logo_safe_zone_guidance(
        cls,
        request: AIOrchestrationRequest,
        scene_graph: GenerationSceneGraph | None = None,
        hint: str | None = None,
    ) -> str:
        geometry = cls._logo_safe_zone_geometry(scene_graph)
        geometry = cls._normalize_logo_safe_zone_geometry(request=request, geometry=geometry, hint=hint)
        x, y, width, height = geometry
        center_x = x + (width / 2.0)
        center_y = y + (height / 2.0)
        if center_y <= 0.33:
            vertical_anchor = "top"
        elif center_y >= 0.67:
            vertical_anchor = "bottom"
        else:
            vertical_anchor = "middle"
        if center_x <= 0.33:
            horizontal_anchor = "left"
        elif center_x >= 0.67:
            horizontal_anchor = "right"
        else:
            horizontal_anchor = "center"
        if horizontal_anchor == "center" and vertical_anchor == "middle":
            anchor_phrase = "center area"
        elif horizontal_anchor == "center":
            anchor_phrase = f"{vertical_anchor} center"
        elif vertical_anchor == "middle":
            anchor_phrase = f"middle {horizontal_anchor}"
        else:
            anchor_phrase = f"{vertical_anchor}-{horizontal_anchor}"
        width_pct = max(int(round(width * 100)), 8)
        height_pct = max(int(round(height * 100)), 5)
        return (
            f"Reserve a clean logo-safe zone in the {anchor_phrase} of the canvas, roughly {width_pct}% of the width and {height_pct}% of the height. "
            "Leave that area visually calm and empty with no text, icons, faces, charts, decorative marks, or high-contrast detail because the exact stored logo will be placed there later. "
            "Do not mark the zone with a visible badge, panel, tile, chip, colored patch, box, plate, or placeholder shape. "
            f"No headline, body copy, supporting text, proof point, stat, CTA, or any content element may appear inside or immediately adjacent to the {anchor_phrase} logo zone — keep a clear margin around it. "
            f"The {anchor_phrase} area must have a clean, calm, low-contrast background so the exact brand logo can sit there clearly without any content, text, or decorative element crowding it from any side."
        )

    @staticmethod
    def _prior_layout_archetype(request: AIOrchestrationRequest) -> str:
        latest_content = (request.session_memory or {}).get("latest_content_version", {}) or {}
        scene_graph = latest_content.get("scene_graph", {}) if isinstance(latest_content, dict) else {}
        styles = scene_graph.get("styles", {}) if isinstance(scene_graph, dict) else {}
        generation_decision = latest_content.get("generation_decision", {}) if isinstance(latest_content, dict) else {}
        archetype = (
            styles.get("layout_archetype")
            or generation_decision.get("layout_archetype")
            or (generation_decision.get("planning_hints") or {}).get("layout_archetype")
        )
        return str(archetype or "").strip().casefold()

    @staticmethod
    def _follow_up_mode(request: AIOrchestrationRequest) -> str:
        follow_up_intent = (request.session_memory or {}).get("follow_up_intent", {}) or {}
        return str(follow_up_intent.get("mode") or "").strip().casefold()

    @classmethod
    def _choose_layout_archetype(
        cls,
        *,
        request: AIOrchestrationRequest,
        candidates: list[str],
        default: str,
    ) -> str:
        follow_up_mode = cls._follow_up_mode(request)
        if follow_up_mode != "variant_of_previous":
            return default
        prior_archetype = cls._prior_layout_archetype(request)
        for candidate in candidates:
            if candidate.casefold() != prior_archetype:
                return candidate
        return default

    def _image_led_layout_profile(
        self,
        *,
        request: AIOrchestrationRequest,
        text_payload: dict[str, Any],
        compiled_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        size = request.studio_panel.get("size") or BlueprintService.PRESET_DIMENSIONS.get(
            request.studio_panel.get("platform_preset", "instagram"),
            BlueprintService.PRESET_DIMENSIONS["instagram"],
        )
        width = max(int(size.get("width") or 1080), 1)
        height = max(int(size.get("height") or 1080), 1)
        aspect_ratio = width / height
        format_name = str(request.studio_panel.get("format") or "static")
        layout_type = self._infer_layout_type(request.prompt, request.studio_panel, text_payload)

        # Prefer exact template/sample layout DNA from compiled context, then fall back to brand-level reference DNA.
        layout_dna = self._extract_layout_dna_from_compiled_context(compiled_context or {}, format_name)
        if not layout_dna:
            layout_dna = self._extract_layout_dna_from_brand_context(request.resolved_brand_context, format_name)
        if layout_dna and layout_dna.get("zones"):
            # Use extracted layout DNA instead of hardcoded profiles
            return self._build_profile_from_layout_dna(layout_dna, layout_type, format_name)

        if format_name == "story" or aspect_ratio <= 0.78:
            archetype = self._choose_layout_archetype(
                request=request,
                candidates=["story_focus_stack"],
                default="story_focus_stack",
            )
            return {
                "layout_type": layout_type,
                "layout_archetype": archetype,
                "hero_image": self._normalized_box(0.08, 0.1, 0.84, 0.42),
                "overlay_panel": self._normalized_box(0.05, 0.56, 0.9, 0.34),
                "logo": self._normalized_box(0.08, 0.59, 0.22, 0.06),
                "headline": self._normalized_box(0.08, 0.68, 0.78, 0.09),
                "supporting_line": self._normalized_box(0.08, 0.78, 0.78, 0.07),
                "proof_points": self._normalized_box(0.08, 0.86, 0.78, 0.09),
                "cta": self._normalized_box(0.08, 0.93, 0.38, 0.05),
                "decorative_shapes": [
                    {
                        "element_id": "accent_badge",
                        "element_type": "decorative_shape",
                        "role": "decorative_shape",
                        "layer": "decorative",
                        "geometry": self._normalized_box(0.74, 0.58, 0.16, 0.08),
                        "style": {"shape": "rounded_rect", "fill_role": "accent", "border_radius": 20},
                    }
                ],
            }

        if format_name == "infographic" or layout_type == "infographic_stack":
            archetype = self._choose_layout_archetype(
                request=request,
                candidates=["infographic_stack", "insight_corner_split", "comparison_corner_card"],
                default="infographic_stack",
            )
            return {
                "layout_type": layout_type,
                "layout_archetype": archetype,
                "hero_image": self._normalized_box(0.6, 0.14, 0.28, 0.24),
                "overlay_panel": self._normalized_box(0.05, 0.08, 0.9, 0.84),
                "logo": self._normalized_box(0.74, 0.1, 0.17, 0.06),
                "headline": self._normalized_box(0.08, 0.13, 0.48, 0.14),
                "supporting_line": self._normalized_box(0.08, 0.29, 0.46, 0.1),
                "proof_points": self._normalized_box(0.08, 0.43, 0.84, 0.3),
                "cta": self._normalized_box(0.08, 0.8, 0.34, 0.07),
                "decorative_shapes": [
                    {
                        "element_id": "stat_highlight_badge",
                        "element_type": "decorative_shape",
                        "role": "decorative_shape",
                        "layer": "decorative",
                        "geometry": self._normalized_box(0.08, 0.37, 0.18, 0.05),
                        "style": {"shape": "rounded_rect", "fill_role": "accent", "border_radius": 18},
                    },
                    {
                        "element_id": "section_divider",
                        "element_type": "decorative_shape",
                        "role": "decorative_shape",
                        "layer": "decorative",
                        "geometry": self._normalized_box(0.08, 0.73, 0.78, 0.01),
                        "style": {"shape": "line", "fill_role": "primary", "opacity": 0.15},
                    },
                ],
            }

        if aspect_ratio >= 1.45:
            if layout_type == "checklist_card":
                candidate_archetypes = ["wide_checklist_split", "wide_editorial_split", "wide_insight_split"]
                archetype = "wide_checklist_split"
            elif layout_type == "comparison_board":
                candidate_archetypes = ["wide_comparison_split", "wide_editorial_split", "wide_insight_split"]
                archetype = "wide_comparison_split"
            elif layout_type == "insight_split":
                candidate_archetypes = ["wide_insight_split", "wide_editorial_split", "wide_checklist_split"]
                archetype = "wide_insight_split"
            else:
                candidate_archetypes = ["wide_editorial_split", "wide_insight_split", "wide_checklist_split"]
                archetype = "wide_editorial_split"
            archetype = self._choose_layout_archetype(
                request=request,
                candidates=candidate_archetypes,
                default=archetype,
            )
            return {
                "layout_type": layout_type,
                "layout_archetype": archetype,
                "hero_image": self._normalized_box(0.56, 0.12, 0.36, 0.64),
                "overlay_panel": self._normalized_box(0.05, 0.08, 0.46, 0.8),
                "logo": self._normalized_box(0.08, 0.11, 0.2, 0.08),
                "headline": self._normalized_box(0.08, 0.21, 0.4, 0.16),
                "supporting_line": self._normalized_box(0.08, 0.4, 0.37, 0.12),
                "proof_points": self._normalized_box(0.08, 0.54, 0.34, 0.18),
                "cta": self._normalized_box(0.08, 0.79, 0.3, 0.09),
                "decorative_shapes": [
                    {
                        "element_id": "hero_accent_arc",
                        "element_type": "decorative_shape",
                        "role": "decorative_shape",
                        "layer": "decorative",
                        "geometry": self._normalized_box(0.78, 0.04, 0.13, 0.07),
                        "style": {"shape": "ellipse", "fill_role": "accent"},
                    }
                ],
            }

        if layout_type == "checklist_card":
            candidate_archetypes = ["checklist_corner_card", "editorial_corner_split", "insight_corner_split"]
            archetype = "checklist_corner_card"
        elif layout_type == "comparison_board":
            candidate_archetypes = ["comparison_corner_card", "editorial_corner_split", "insight_corner_split"]
            archetype = "comparison_corner_card"
        elif layout_type == "insight_split":
            candidate_archetypes = ["insight_corner_split", "editorial_corner_split", "checklist_corner_card"]
            archetype = "insight_corner_split"
        else:
            candidate_archetypes = ["editorial_corner_split", "insight_corner_split", "checklist_corner_card"]
            archetype = "editorial_corner_split"
        archetype = self._choose_layout_archetype(
            request=request,
            candidates=candidate_archetypes,
            default=archetype,
        )

        return {
            "layout_type": layout_type,
            "layout_archetype": archetype,
            "hero_image": self._normalized_box(0.54, 0.14, 0.34, 0.42),
            "overlay_panel": self._normalized_box(0.05, 0.08, 0.46, 0.8),
            "logo": self._normalized_box(0.08, 0.11, 0.2, 0.07),
            "headline": self._normalized_box(0.08, 0.2, 0.38, 0.16),
            "supporting_line": self._normalized_box(0.08, 0.38, 0.37, 0.11),
            "proof_points": self._normalized_box(0.08, 0.52, 0.34, 0.18),
            "cta": self._normalized_box(0.08, 0.78, 0.3, 0.08),
            "decorative_shapes": [
                {
                    "element_id": "hero_glow",
                    "element_type": "decorative_shape",
                    "role": "decorative_shape",
                    "layer": "decorative",
                    "geometry": self._normalized_box(0.79, 0.05, 0.13, 0.09),
                    "style": {"shape": "ellipse", "fill_role": "accent"},
                }
            ],
        }

    def _fallback_scene_graph(
        self,
        *,
        request: AIOrchestrationRequest,
        text_payload: dict[str, Any],
        creative_decision: dict[str, Any],
        compiled_context: dict[str, Any],
    ) -> dict[str, Any]:
        size = request.studio_panel.get("size") or BlueprintService.PRESET_DIMENSIONS.get(
            request.studio_panel.get("platform_preset", "instagram"),
            BlueprintService.PRESET_DIMENSIONS["instagram"],
        )
        layout_type = self._infer_layout_type(request.prompt, request.studio_panel, text_payload)
        palette_roles = dict((compiled_context.get("brand_visual_brief", {}) or {}).get("palette_roles", {}) or {})
        proof_points = list((text_payload.get("metadata") or {}).get("proof_points") or [])
        content_elements = [
            {
                "element_id": "background",
                "element_type": "background",
                "role": "background",
                "layer": "background",
                "geometry": {"x": 0, "y": 0, "width": 1, "height": 1, "units": "normalized"},
                "style": {
                    "fill_role": "background",
                    "primary_fill": palette_roles.get("background") or palette_roles.get("surface"),
                    "gradient_from": palette_roles.get("background") or palette_roles.get("surface"),
                    "gradient_to": palette_roles.get("primary"),
                },
            },
            {
                "element_id": "headline",
                "element_type": "text",
                "role": "headline",
                "layer": "content",
                "geometry": {"x": 0.08, "y": 0.09, "width": 0.68, "height": 0.16, "units": "normalized"},
                "text": text_payload.get("headline", ""),
                "style": {"font_size": 58, "font_role": "heading", "fill_role": "primary", "max_lines": 3},
            },
            {
                "element_id": "supporting_line",
                "element_type": "text",
                "role": "supporting_line",
                "layer": "content",
                "geometry": {"x": 0.08, "y": 0.24, "width": 0.68, "height": 0.1, "units": "normalized"},
                "text": (text_payload.get("metadata") or {}).get("supporting_line") or text_payload.get("body", ""),
                "style": {"font_size": 24, "font_role": "body", "fill_role": "secondary_text", "max_lines": 3},
            },
            {
                "element_id": "image",
                "element_type": "image",
                "role": "image",
                "layer": "primary_visual",
                "geometry": {"x": 0.56, "y": 0.22, "width": 0.34, "height": 0.46, "units": "normalized"},
                "style": {"fit": "cover", "border_radius": 28},
                "asset": {"asset_role": "ai_image"},
            },
            {
                "element_id": "cta",
                "element_type": "text",
                "role": "cta",
                "layer": "brand",
                "geometry": {"x": 0.08, "y": 0.8, "width": 0.34, "height": 0.09, "units": "normalized"},
                "text": text_payload.get("cta", ""),
                "style": {"font_size": 24, "font_role": "cta", "fill_role": "light_text", "background_fill_role": "primary", "max_lines": 2},
            },
            {
                "element_id": "logo",
                "element_type": "logo",
                "role": "logo",
                "layer": "brand",
                "geometry": {"x": 0.78, "y": 0.07, "width": 0.16, "height": 0.08, "units": "normalized"},
                "style": {"fit": "contain"},
                "asset": {"asset_role": "logo", "trust_level": "trusted"},
            },
            {
                "element_id": "decorative_glow",
                "element_type": "decorative_shape",
                "role": "decorative_shape",
                "layer": "decorative",
                "geometry": {"x": 0.72, "y": 0.12, "width": 0.2, "height": 0.14, "units": "normalized"},
                "style": {"shape": "ellipse", "fill_role": "accent"},
            },
        ]
        if proof_points:
            content_elements.insert(
                3,
                {
                    "element_id": "proof_points",
                    "element_type": "text",
                    "role": "proof_points",
                    "layer": "content",
                    "geometry": {"x": 0.08, "y": 0.36, "width": 0.4, "height": 0.28, "units": "normalized"},
                    "text": proof_points,
                    "style": {"font_size": 20, "font_role": "body", "fill_role": "secondary_text", "max_lines": 5},
                },
            )
        else:
            content_elements.insert(
                3,
                {
                    "element_id": "body",
                    "element_type": "text",
                    "role": "body",
                    "layer": "content",
                    "geometry": {"x": 0.08, "y": 0.36, "width": 0.44, "height": 0.28, "units": "normalized"},
                    "text": text_payload.get("body", ""),
                    "style": {"font_size": 20, "font_role": "body", "fill_role": "secondary_text", "max_lines": 5},
                },
            )
        if layout_type == "checklist_card":
            content_elements[2]["geometry"] = {"x": 0.08, "y": 0.24, "width": 0.38, "height": 0.1, "units": "normalized"}
            for element in content_elements:
                if element["role"] == "image":
                    element["geometry"] = {"x": 0.54, "y": 0.14, "width": 0.34, "height": 0.46, "units": "normalized"}
                    element["style"] = {
                        **dict(element.get("style") or {}),
                        "fit": "cover",
                        "border_radius": 34,
                    }
                if element["role"] == "cta":
                    element["geometry"] = {"x": 0.08, "y": 0.83, "width": 0.36, "height": 0.09, "units": "normalized"}
                    element["style"] = {
                        **dict(element.get("style") or {}),
                        "background_fill_role": "primary",
                        "fill_role": "light_text",
                    }
            content_elements = [
                element
                for element in content_elements
                if element["role"] not in {"proof_points", "body"}
            ]
            proof_rows = proof_points[:3] or self._sentences(text_payload.get("body", ""))[:3]
            row_y = 0.42
            for index, item in enumerate(proof_rows, start=1):
                y = row_y + ((index - 1) * 0.11)
                content_elements.extend(
                    [
                        {
                            "element_id": f"proof_card_{index}",
                            "element_type": "decorative_shape",
                            "role": "decorative_shape",
                            "layer": "decorative",
                            "geometry": {"x": 0.08, "y": y, "width": 0.38, "height": 0.085, "units": "normalized"},
                            "style": {"shape": "rounded_rect", "fill_role": "surface", "border_radius": 26},
                        },
                        {
                            "element_id": f"proof_accent_{index}",
                            "element_type": "decorative_shape",
                            "role": "decorative_shape",
                            "layer": "decorative",
                            "geometry": {"x": 0.095, "y": y + 0.018, "width": 0.024, "height": 0.048, "units": "normalized"},
                            "style": {"shape": "rounded_rect", "fill_role": "accent", "border_radius": 14},
                        },
                        {
                            "element_id": f"proof_text_{index}",
                            "element_type": "text",
                            "role": "body",
                            "layer": "content",
                            "geometry": {"x": 0.135, "y": y + 0.01, "width": 0.305, "height": 0.06, "units": "normalized"},
                            "text": item,
                            "style": {
                                "font_size": 22,
                                "font_role": "body_sans",
                                "fill_role": "secondary_text",
                                "max_lines": 2,
                            },
                        },
                    ]
                )
            content_elements.append(
                {
                    "element_id": "hero_glow",
                    "element_type": "decorative_shape",
                    "role": "decorative_shape",
                    "layer": "decorative",
                    "geometry": {"x": 0.67, "y": 0.08, "width": 0.22, "height": 0.14, "units": "normalized"},
                    "style": {"shape": "ellipse", "fill_role": "accent"},
                }
            )
        return {
            "version": "1.0",
            "canvas": {
                "width": int(size.get("width") or 1080),
                "height": int(size.get("height") or 1080),
                "platform": request.studio_panel.get("platform_preset", "instagram"),
                "file_type": request.studio_panel.get("file_type", "png"),
                "safe_margin": 48,
            },
            "layout_mode": creative_decision.get("layout_mode", "synthesized_layout"),
            "confidence": float(creative_decision.get("confidence") or 0.58),
            "layers": list(self.DEFAULT_LAYERS),
            "elements": content_elements,
            "styles": {
                "layout_type": layout_type,
                "layout_archetype": layout_type,
                "palette_roles": palette_roles,
            },
            "assets": [
                {
                    "asset_id": str(asset.get("asset_id") or ""),
                    "asset_role": str(asset.get("asset_role") or ""),
                    "storage_path": str(asset.get("storage_path") or ""),
                    "trust_level": str(asset.get("trust_level") or ""),
                }
                for asset in (request.asset_catalog or request.reference_assets)[:12]
                if isinstance(asset, dict)
            ],
            "template_adaptation": {
                **dict(creative_decision.get("adaptations") or {}),
                "selected_template_id": creative_decision.get("selected_template_id"),
            },
            "validation_hints": {"template_surface_policy": "reinterpret_if_flattened"},
        }

    @classmethod
    def _repair_common_mojibake(cls, value: str) -> str:
        text = value or ""
        if not any(token in text for token in ("Ã", "Â", "â€", "â€™", "â€œ", "â€”", "â€“", "â€¢")):
            return text
        try:
            repaired = text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text
        return repaired or text

    @classmethod
    def _sanitize_text_for_canvas(cls, value: str) -> str:
        text = cls._repair_common_mojibake(value or "")
        text = cls.MOJIBAKE_SYMBOL_PATTERN.sub(" ", text)
        text = cls.DISALLOWED_GLYPH_PATTERN.sub(" ", text)
        return " ".join(text.split()).strip()

    @classmethod
    def _normalized_prompt_tokens(cls, value: str) -> list[str]:
        cleaned = re.sub(r"[^a-z0-9\s]+", " ", (value or "").lower())
        return [
            token
            for token in cleaned.split()
            if token and token not in cls.PROMPT_ECHO_STOPWORDS
        ]

    @classmethod
    def _looks_like_prompt_echo(cls, value: Any, prompt: str) -> bool:
        candidate = cls._coerce_text_value(value)
        if not candidate:
            return False
        prompt_text = cls._coerce_text_value(prompt)
        if not prompt_text:
            return False
        lowered_candidate = candidate.lower().strip()
        if lowered_candidate.startswith(("create ", "make ", "design ", "generate ", "write ", "craft ")):
            return True
        candidate_tokens = cls._normalized_prompt_tokens(candidate)
        prompt_tokens = cls._normalized_prompt_tokens(prompt_text)
        if not candidate_tokens or not prompt_tokens:
            return False
        overlap_tokens = set(candidate_tokens) & set(prompt_tokens)
        overlap = len(overlap_tokens)
        prompt_instruction_markers = (
            "instagram post",
            "social media post",
            "create a",
            "make a",
            "design a",
            "generate a",
            "write a",
            "craft a",
            "cta for this post",
        )
        generic_fallback_starts = (
            "practical guidance for ",
            "smart strategies for ",
        )
        if lowered_candidate.startswith(generic_fallback_starts):
            return True
        audience_facing_starts = (
            "tips for ",
            "how to ",
            "ways to ",
            "why ",
            "want to ",
        )
        if lowered_candidate.startswith(audience_facing_starts) and not any(
            marker in lowered_candidate for marker in prompt_instruction_markers
        ):
            return False
        if not any(marker in lowered_candidate for marker in prompt_instruction_markers) and overlap <= 2:
            return False
        candidate_phrase = " ".join(candidate_tokens)
        prompt_phrase = " ".join(prompt_tokens)
        if candidate_phrase and (candidate_phrase in prompt_phrase or prompt_phrase in candidate_phrase):
            return True
        baseline = max(1, min(len(candidate_tokens), len(prompt_tokens)))
        return overlap >= 3 and (overlap / baseline) >= 0.8

    @classmethod
    def _has_mistake_carousel_signals(cls, *values: Any) -> bool:
        combined = " ".join(
            cls._normalize_metadata_text(value, limit=240)
            for value in values
            if cls._normalize_metadata_text(value, limit=240)
        )
        return bool(cls.MISTAKE_CAROUSEL_SIGNAL_PATTERN.search(combined))

    @classmethod
    def _prefers_multiple_mistake_slides(cls, *values: Any) -> bool:
        combined = " ".join(
            cls._normalize_metadata_text(value, limit=240)
            for value in values
            if cls._normalize_metadata_text(value, limit=240)
        )
        return bool(cls.MULTI_MISTAKE_SIGNAL_PATTERN.search(combined))

    @classmethod
    def _is_generic_carousel_education_label(cls, value: Any) -> bool:
        text = cls._normalize_metadata_text(value, limit=120).casefold()
        if not text:
            return False
        return (
            text in {"education", "tips", "key insight", "key point", "insight"}
            or text.startswith("key insight")
            or text.startswith("key point")
        )

    @classmethod
    def _is_promotional_line(cls, value: Any) -> bool:
        text = cls._normalize_metadata_text(value, limit=220)
        if not text:
            return False
        return bool(cls.PROMOTIONAL_LINE_PATTERN.search(text))

    @classmethod
    def _is_mistake_candidate_line(cls, value: Any) -> bool:
        text = cls._normalize_metadata_text(value, limit=220)
        if not text:
            return False
        if cls.MISTAKE_GROUP_START_PATTERN.match(text):
            return True
        if cls.IMPACT_LINE_PATTERN.match(text) or cls.FIX_LINE_PATTERN.match(text):
            return False
        return bool(cls.NEGATIVE_MISTAKE_CANDIDATE_PATTERN.search(text)) and not cls._is_promotional_line(text)

    @classmethod
    def _mistake_cover_headline(cls, *values: Any) -> str:
        combined = " ".join(
            cls._normalize_metadata_text(value, limit=240)
            for value in values
            if cls._normalize_metadata_text(value, limit=240)
        )
        focus = cls._prompt_topic_summary(combined)
        focus = re.sub(r"\b(?:top|common|most|costly)\b", " ", focus, flags=re.IGNORECASE)
        focus = " ".join(focus.split()).strip(" -:.;")
        if focus and "mistake" not in focus.casefold():
            return cls._normalize_metadata_text(f"Common {focus.title()} Mistakes To Avoid", limit=90)
        if focus:
            return cls._normalize_metadata_text(focus.title(), limit=90)
        return "Common Mistakes To Avoid"

    @classmethod
    def _strip_mistake_markers(cls, value: Any) -> str:
        cleaned = cls._normalize_metadata_text(value, limit=160)
        if not cleaned:
            return ""
        cleaned = cls.MISTAKE_GROUP_START_PATTERN.sub("", cleaned).strip(" -:.;")
        cleaned = cls.MISTAKE_WHY_PATTERN.sub("", cleaned).strip(" -:.;")
        cleaned = cls.IMPACT_LINE_PATTERN.sub("", cleaned).strip(" -:.;")
        cleaned = cls.FIX_LINE_PATTERN.sub("", cleaned).strip(" -:.;")
        return cleaned

    @classmethod
    def _infer_mistake_headline(cls, value: Any, *, fallback_focus: str = "", index: int = 1) -> str:
        cleaned = cls._strip_mistake_markers(value)
        lowered = cleaned.casefold()
        if "diversif" in lowered:
            return "Mistake: Not Diversifying Your Portfolio"
        if "yield" in lowered or "return" in lowered:
            return "Mistake: Chasing High Returns"
        if "credit quality" in lowered or "rating" in lowered or "risk" in lowered:
            return "Mistake: Ignoring Quality"
        if "duration" in lowered or "timing" in lowered:
            return "Mistake: Ignoring Timing"
        if cleaned:
            if cls._is_generic_carousel_education_label(cleaned):
                cleaned = ""
            elif str(value).strip().casefold().startswith("mistake:"):
                return cls._normalize_metadata_text(str(value).strip(), limit=110)
            else:
                return f"Mistake: {cleaned}"
        focus = cls._normalize_metadata_text(fallback_focus, limit=90).strip(" -:.;")
        if focus:
            return f"Mistake: {focus}"
        return f"Mistake: Key issue {index}"

    @classmethod
    def _mistake_supporting_line(cls, *values: Any) -> str:
        for candidate in values:
            cleaned = cls._normalize_metadata_text(candidate, limit=220)
            if not cleaned:
                continue
            if (
                cls.MISTAKE_GROUP_START_PATTERN.match(cleaned)
                or cls.IMPACT_LINE_PATTERN.match(cleaned)
                or cls.FIX_LINE_PATTERN.match(cleaned)
                or cls._is_promotional_line(cleaned)
            ):
                continue
            cleaned = cls.MISTAKE_WHY_PATTERN.sub("", cleaned).strip(" -:.;")
            if cleaned:
                return cleaned
        return ""

    @classmethod
    def _mistake_detail_groups(
        cls,
        *,
        headline: str,
        supporting_line: str,
        proof_points: list[str],
        stat_highlights: list[str],
        body_sentences: list[str],
    ) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        labeled_stream = [*proof_points, *body_sentences]
        for item in labeled_stream:
            cleaned = cls._normalize_metadata_text(item, limit=220)
            if not cleaned:
                continue
            if cls.MISTAKE_GROUP_START_PATTERN.match(cleaned):
                if current and (current.get("headline") or current.get("supporting_line") or current.get("proof_points")):
                    groups.append(current)
                current = {
                    "headline": cls._infer_mistake_headline(cleaned, fallback_focus=headline, index=len(groups) + 1),
                    "supporting_line": "",
                    "proof_points": [],
                }
                continue
            if current is None:
                continue
            if not current.get("supporting_line") and not cls.IMPACT_LINE_PATTERN.match(cleaned) and not cls.FIX_LINE_PATTERN.match(cleaned):
                current["supporting_line"] = cls._mistake_supporting_line(cleaned)
            else:
                normalized_line = cls._normalize_metadata_text(cleaned, limit=180)
                if normalized_line and not cls._is_promotional_line(normalized_line):
                    current.setdefault("proof_points", []).append(normalized_line)
        if current and (current.get("headline") or current.get("supporting_line") or current.get("proof_points")):
            groups.append(current)
        if groups:
            normalized_groups: list[dict[str, Any]] = []
            for index, group in enumerate(groups, start=1):
                normalized_groups.append(
                    {
                        "headline": cls._infer_mistake_headline(group.get("headline"), fallback_focus=headline, index=index),
                        "supporting_line": cls._mistake_supporting_line(group.get("supporting_line"), supporting_line),
                        "proof_points": cls._normalize_metadata_list(group.get("proof_points"), limit=3),
                    }
                )
            return normalized_groups

        evidence_pool = [
            value
            for value in [*stat_highlights, *proof_points, *body_sentences]
            if cls._is_mistake_candidate_line(value)
        ]
        fallback_focus = next(
            (
                cls._strip_mistake_markers(value)
                for value in evidence_pool
                if cls._strip_mistake_markers(value) and not cls._is_generic_carousel_education_label(value)
            ),
            cls._strip_mistake_markers(headline) or cls._strip_mistake_markers(supporting_line),
        )
        wants_multiple = cls._prefers_multiple_mistake_slides(headline, supporting_line, *proof_points, *stat_highlights, *body_sentences)
        target_groups = max(1, len(evidence_pool), 3 if wants_multiple else 2)
        heuristics: list[dict[str, Any]] = []
        for index in range(target_groups):
            title_source = evidence_pool[index] if index < len(evidence_pool) else fallback_focus
            body_slice = body_sentences[index * 2 : index * 2 + 2]
            why_source = cls._mistake_supporting_line(*(body_slice or [supporting_line, title_source]))
            detail_points: list[str] = []
            for point in proof_points[index * 2 : index * 2 + 4]:
                normalized = cls._normalize_metadata_text(point, limit=180)
                if not normalized:
                    continue
                if normalized == cls._normalize_metadata_text(title_source, limit=180):
                    continue
                if cls._is_promotional_line(normalized):
                    continue
                detail_points.append(normalized)
            if not detail_points:
                for sentence in body_sentences[index * 2 + 1 : index * 2 + 4]:
                    normalized = cls._normalize_metadata_text(sentence, limit=180)
                    if normalized and normalized != why_source and not cls._is_promotional_line(normalized):
                        detail_points.append(normalized)
            heuristics.append(
                {
                    "headline": cls._infer_mistake_headline(title_source, fallback_focus=fallback_focus, index=index + 1),
                    "supporting_line": why_source,
                    "proof_points": detail_points[:3],
                }
            )
        return heuristics

    @classmethod
    def _repair_prompt_echo_text_payload(
        cls,
        payload: StructuredTextPayload,
        *,
        prompt: str,
    ) -> StructuredTextPayload:
        raw = payload.model_dump(mode="json")
        metadata = dict(raw.get("metadata") or {})
        proof_points = cls._normalize_metadata_list(metadata.get("proof_points"), limit=4)
        stat_highlights = cls._normalize_metadata_list(metadata.get("stat_highlights"), limit=3)
        prompt_topic = cls._prompt_topic_summary(prompt)
        mistake_style = cls._has_mistake_carousel_signals(
            prompt,
            raw.get("headline"),
            raw.get("body"),
            metadata.get("supporting_line"),
            *proof_points,
            *stat_highlights,
        )
        if cls._looks_like_prompt_echo(raw.get("body"), prompt):
            if proof_points:
                raw["body"] = ". ".join(point.rstrip(" .") for point in proof_points[:3]).strip() + "."
            elif stat_highlights:
                raw["body"] = ". ".join(item.rstrip(" .") for item in stat_highlights[:3]).strip() + "."
            elif prompt_topic:
                raw["body"] = cls._body_from_prompt_topic(prompt_topic)
        if cls._looks_like_prompt_echo(metadata.get("supporting_line"), prompt):
            if proof_points:
                metadata["supporting_line"] = proof_points[0]
            elif prompt_topic:
                metadata["supporting_line"] = cls._supporting_line_from_prompt_topic(prompt_topic)
            elif raw.get("body"):
                metadata["supporting_line"] = cls._sentences(raw.get("body"))[:1][0] if cls._sentences(raw.get("body")) else raw.get("body", "")
        if cls._looks_like_prompt_echo(raw.get("cta"), prompt):
            brand_name = cls._normalize_metadata_text(metadata.get("brand"), limit=48) or "the brand"
            metadata.setdefault("cta_repaired", True)
            raw["cta"] = f"Explore more with {brand_name}"[:72]
        if cls._looks_like_prompt_echo(raw.get("headline"), prompt):
            fallback_headline = (
                ""
                if mistake_style and cls._is_generic_carousel_education_label(metadata.get("section_label"))
                else cls._normalize_metadata_text(metadata.get("section_label"), limit=72)
            )
            if fallback_headline:
                raw["headline"] = fallback_headline
            elif prompt_topic:
                raw["headline"] = (
                    cls._infer_mistake_headline(prompt_topic, fallback_focus=prompt_topic)
                    if mistake_style
                    else cls._headline_from_prompt_topic(prompt_topic)
                )
        metadata["proof_points"] = proof_points or metadata.get("proof_points", [])
        raw["metadata"] = metadata
        return StructuredTextPayload.model_validate(raw)

    @staticmethod
    def _text_payload_prompt_dict(payload: Any) -> dict[str, Any]:
        if hasattr(payload, "model_dump"):
            try:
                dumped = payload.model_dump(mode="json")
                if isinstance(dumped, dict):
                    return dumped
            except TypeError:
                pass
        metadata = getattr(payload, "metadata", {})
        return {
            "headline": getattr(payload, "headline", ""),
            "body": getattr(payload, "body", ""),
            "cta": getattr(payload, "cta", ""),
            "metadata": metadata if isinstance(metadata, dict) else {},
        }

    @classmethod
    def _prompt_topic_summary(cls, prompt: str) -> str:
        text = cls._coerce_text_value(prompt)
        if not text:
            return ""
        text = re.sub(
            r"^(?:please\s+)?(?:create|make|design|generate|write|craft)\s+(?:(?:an?|the)\s+)?",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\b(?:an?|the)?\s*(?:engaging|premium|professional|clean|high[- ]quality)\s+",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\b(?:instagram|linkedin|facebook|social media|social|post|image|graphic|creative|story|poster|static|carousel|thumbnail)\b",
            " ",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"\bthat\s+(?:shares?|highlights?|explains?)\b", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\babout\b", " ", text, flags=re.IGNORECASE)
        text = " ".join(text.replace("\n", " ").split())
        return text.strip(" ,.;:-")

    @classmethod
    def _headline_from_prompt_topic(cls, topic: str) -> str:
        cleaned = cls._normalize_metadata_text(topic, limit=72)
        if not cleaned:
            return "Brand Update"
        headline = cleaned.title()
        headline = re.sub(r"\bAnd\b", "and", headline)
        headline = re.sub(r"\bFor\b", "for", headline)
        headline = re.sub(r"\bTo\b", "to", headline)
        return headline[:72].rstrip(" ,.;:")

    @classmethod
    def _body_from_prompt_topic(cls, topic: str) -> str:
        cleaned = cls._normalize_metadata_text(topic, limit=160)
        if not cleaned:
            return ""
        topic_kind, focus = cls._prompt_topic_focus(cleaned)
        lens = cls._topic_specific_detail_lens(focus or cleaned)
        if topic_kind == "action" and focus:
            return f"Want to {focus}? Start with {lens}."
        if topic_kind == "why" and focus:
            focus_text = focus[0].upper() + focus[1:]
            return f"{focus_text} matters more when people get {lens}."
        headline = cls._headline_from_prompt_topic(cleaned)
        return f"{headline} starts with {lens}."

    @classmethod
    def _supporting_line_from_prompt_topic(cls, topic: str) -> str:
        cleaned = cls._normalize_metadata_text(topic, limit=120)
        if not cleaned:
            return ""
        topic_kind, focus = cls._prompt_topic_focus(cleaned)
        lens = cls._topic_specific_detail_lens(focus or cleaned)
        if topic_kind == "why" and focus:
            return f"{focus[0].upper() + focus[1:]} needs {lens}"
        if topic_kind == "action" and focus:
            return f"Start with {lens}"
        return f"Start with {lens}"

    @classmethod
    def _fallback_topic_focus(
        cls,
        prompt: str,
        *,
        compiled_context: dict[str, Any] | None = None,
    ) -> str:
        prompt_topic = cls._normalize_metadata_text(cls._prompt_topic_summary(prompt), limit=140)
        if prompt_topic:
            return prompt_topic
        compiled_context = compiled_context if isinstance(compiled_context, dict) else {}
        objective_brief = cls._coerce_mapping(compiled_context.get("objective_brief"))
        brand_copy_brief = cls._coerce_mapping(compiled_context.get("brand_copy_brief"))
        knowledge_brief = compiled_context.get("knowledge_brief", []) or []
        knowledge_line = ""
        if knowledge_brief and isinstance(knowledge_brief[0], dict):
            knowledge_line = cls._normalize_metadata_text(knowledge_brief[0].get("content"), limit=140)
        return cls._normalize_metadata_text(
            objective_brief.get("name")
            or objective_brief.get("primary_goal")
            or objective_brief.get("description")
            or brand_copy_brief.get("objective_focus")
            or brand_copy_brief.get("brand_foundations")
            or brand_copy_brief.get("brand_description")
            or knowledge_line,
            limit=140,
        )

    @classmethod
    def _prompt_topic_focus(cls, topic: str) -> tuple[str, str]:
        cleaned = cls._normalize_metadata_text(topic, limit=160)
        lowered = cleaned.casefold()
        patterns: list[tuple[str, str]] = [
            (r"^(?:tips?(?:\s+and\s+strateg(?:y|ies))?|strateg(?:y|ies)|ways|steps|ideas)\s+to\s+(.+)$", "action"),
            (r"^(?:tips?(?:\s+and\s+strateg(?:y|ies))?|strateg(?:y|ies)|ways|steps|ideas|guide|checklist)\s+for\s+(.+)$", "topic"),
            (r"^how to\s+(.+)$", "action"),
            (r"^guide to\s+(.+)$", "action"),
            (r"^checklist for\s+(.+)$", "topic"),
            (r"^why\s+(.+)$", "why"),
        ]
        for pattern, topic_kind in patterns:
            match = re.match(pattern, lowered, flags=re.IGNORECASE)
            if not match:
                continue
            focus = cls._normalize_metadata_text(match.group(1), limit=140)
            if focus:
                return topic_kind, focus
        return "topic", cleaned

    @classmethod
    def _topic_specific_detail_lens(cls, topic: str) -> str:
        lowered = cls._normalize_metadata_text(topic, limit=160).casefold()
        if not lowered:
            return "specific details people can act on right away"
        if any(token in lowered for token in ("price", "pricing", "cost", "afford", "budget", "save", "savings", "cheaper", "lower")):
            return "the choices that change price the most"
        if any(token in lowered for token in ("risk", "trust", "confidence", "safe", "safety", "secure", "clarity", "opaque")):
            return "proof and plain-English clarity people can trust"
        if any(token in lowered for token in ("compare", "comparison", "versus", "vs ", "choose", "choice", "option")):
            return "the trade-offs that make the decision easier"
        if any(token in lowered for token in ("learn", "understand", "explain", "guide", "checklist", "how to", "tips", "strategy", "strategies")):
            return "plain-language takeaways people can use quickly"
        if any(token in lowered for token in ("grow", "improve", "scale", "increase", "launch", "build")):
            return "the moves that make progress feel real"
        return "specific details people can act on right away"

    @classmethod
    def _contextual_headline_fallback(
        cls,
        *,
        topic_focus: str,
        motivation: str,
        pain_point: str,
        research_highlight: str,
        brand_foundations: Any,
        knowledge_line: str,
        primary_goal: Any,
        semantic_support_phrase: str,
    ) -> str:
        normalized_topic = cls._normalize_metadata_text(topic_focus, limit=120)
        normalized_motivation = cls._normalize_metadata_text(motivation, limit=96)
        normalized_pain_point = cls._normalize_metadata_text(pain_point, limit=96)
        normalized_research = cls._normalize_metadata_text(research_highlight, limit=120)
        normalized_foundations = cls._normalize_metadata_text(brand_foundations, limit=120)
        normalized_knowledge = cls._normalize_metadata_text(knowledge_line, limit=120)
        normalized_goal = cls._normalize_metadata_text(primary_goal, limit=96)
        if normalized_topic:
            if normalized_motivation and normalized_research:
                return (
                    f"Frame '{normalized_topic}' around '{normalized_motivation}', using this audience truth as the proof: "
                    f"{normalized_research}"
                )
            if normalized_motivation and normalized_foundations:
                return (
                    f"Frame '{normalized_topic}' around '{normalized_motivation}' while reinforcing "
                    f"{normalized_foundations}."
                )
            if normalized_pain_point and normalized_research:
                return (
                    f"Lead '{normalized_topic}' by resolving '{normalized_pain_point}' with this audience truth: "
                    f"{normalized_research}"
                )
            if normalized_motivation:
                return (
                    f"Lead '{normalized_topic}' with the payoff of '{normalized_motivation}', not a generic benefit list."
                )
            if normalized_research:
                return f"Lead '{normalized_topic}' with this audience truth: {normalized_research}"
            if normalized_foundations:
                return f"Lead '{normalized_topic}' in a way that reinforces {normalized_foundations}."
            if normalized_knowledge:
                return f"Ground '{normalized_topic}' in this concrete fact: {normalized_knowledge}"
            if normalized_goal:
                return f"Lead '{normalized_topic}' in a way that moves people toward {normalized_goal}."
            return f"Lead '{normalized_topic}' with {semantic_support_phrase} so the value feels earned."
        if normalized_foundations and normalized_goal:
            return f"Anchor the message in {normalized_foundations} and connect it to {normalized_goal}."
        if normalized_research:
            return f"Anchor the message in this audience truth: {normalized_research}"
        if normalized_foundations:
            return f"Anchor the message in {normalized_foundations} so it stays distinctive."
        if normalized_knowledge:
            return f"Anchor the message in this concrete fact: {normalized_knowledge}"
        return "Anchor the message in a concrete audience payoff and believable proof."

    @classmethod
    def _contextual_supporting_fallback(
        cls,
        *,
        topic_focus: str,
        motivation: str,
        pain_point: str,
        objection: str,
        brand_foundations: Any,
        research_highlight: str,
        knowledge_line: str,
        semantic_support_phrase: str,
    ) -> str:
        normalized_topic = cls._normalize_metadata_text(topic_focus, limit=120)
        normalized_motivation = cls._normalize_metadata_text(motivation, limit=96)
        normalized_pain_point = cls._normalize_metadata_text(pain_point, limit=96)
        normalized_objection = cls._normalize_metadata_text(objection, limit=96)
        normalized_foundations = cls._normalize_metadata_text(brand_foundations, limit=120)
        normalized_research = cls._normalize_metadata_text(research_highlight, limit=120)
        normalized_knowledge = cls._normalize_metadata_text(knowledge_line, limit=120)
        if normalized_topic and normalized_objection and normalized_research:
            return (
                f"Back '{normalized_topic}' with concrete proof that answers '{normalized_objection}', "
                f"starting from this audience signal: {normalized_research}"
            )
        if normalized_topic and normalized_objection and normalized_knowledge:
            return (
                f"Back '{normalized_topic}' with concrete proof that answers '{normalized_objection}', "
                f"using this fact: {normalized_knowledge}"
            )
        if normalized_topic and normalized_pain_point and normalized_motivation:
            return (
                f"Show how '{normalized_topic}' moves people from '{normalized_pain_point}' to "
                f"'{normalized_motivation}' with concrete detail."
            )
        if normalized_topic and normalized_foundations and normalized_knowledge:
            return (
                f"Show how '{normalized_topic}' delivers on {normalized_foundations}, using this fact: "
                f"{normalized_knowledge}"
            )
        if normalized_topic and normalized_foundations:
            return f"Show how '{normalized_topic}' delivers on {normalized_foundations} with concrete detail."
        if normalized_topic and normalized_research:
            return f"Use this audience signal as the proof lens for '{normalized_topic}': {normalized_research}"
        if normalized_topic:
            return f"Back '{normalized_topic}' with {semantic_support_phrase}, so the message sounds useful rather than generic."
        if normalized_research:
            return f"Use this audience signal as the proof lens: {normalized_research}"
        if normalized_knowledge:
            return f"Build the support copy around this concrete fact: {normalized_knowledge}"
        if normalized_foundations:
            return f"Translate {normalized_foundations} into concrete proof the audience can picture."
        return f"Back the message with {semantic_support_phrase} so it feels earned."

    @classmethod
    def _contextual_cta_fallback(
        cls,
        *,
        topic_focus: str,
        primary_goal: Any,
        pain_point: str,
        objection: str,
    ) -> str:
        normalized_goal = cls._normalize_metadata_text(primary_goal, limit=80)
        normalized_topic = cls._normalize_metadata_text(topic_focus, limit=120)
        normalized_pain_point = cls._normalize_metadata_text(pain_point, limit=96)
        normalized_objection = cls._normalize_metadata_text(objection, limit=96)
        if normalized_goal and normalized_topic:
            return (
                f"Invite a low-friction next step that helps the audience act on '{normalized_topic}' "
                f"and move toward {normalized_goal}."
            )
        if normalized_goal and normalized_objection:
            return (
                f"Invite a low-friction next step that helps skeptical readers validate the claim "
                f"and move toward {normalized_goal}."
            )
        if normalized_goal:
            return f"Invite a low-friction next step that moves the audience toward {normalized_goal}."
        if normalized_topic and normalized_objection:
            return (
                f"Invite a low-friction next step tied to '{normalized_topic}' so skeptical readers can validate it "
                f"for themselves."
            )
        if normalized_topic and normalized_pain_point:
            return (
                f"Invite a low-friction next step tied to '{normalized_topic}' that reduces the feeling of "
                f"'{normalized_pain_point}'."
            )
        if normalized_topic:
            return f"Invite a low-friction next step tied to '{normalized_topic}' so the CTA feels useful, not generic."
        return "Invite a low-friction next step that helps the audience act with more clarity."

    @classmethod
    def _looks_like_fallback_copy_scaffold(cls, value: Any) -> bool:
        text = cls._normalize_metadata_text(value, limit=220).casefold()
        if not text:
            return False
        if any(text.startswith(prefix) for prefix in cls.FALLBACK_COPY_INSTRUCTION_PREFIXES):
            return True
        return any(marker in text for marker in cls.FALLBACK_COPY_DESCRIPTOR_MARKERS)

    @classmethod
    def _usable_fallback_copy_text(
        cls,
        value: Any,
        *,
        limit: int,
        prompt: str,
    ) -> str:
        text = cls._normalize_metadata_text(value, limit=limit)
        if not text or text.casefold() == "missing":
            return ""
        if cls._looks_like_fallback_copy_scaffold(text):
            return ""
        if prompt and cls._looks_like_prompt_echo(text, prompt):
            return ""
        return text

    @classmethod
    def _fallback_copy_fragments(
        cls,
        candidates: list[Any],
        *,
        prompt: str,
        limit: int,
        max_items: int,
        exclude: list[str] | None = None,
    ) -> list[str]:
        fragments: list[str] = []
        seen = {
            cls._normalize_metadata_text(item, limit=limit).casefold()
            for item in (exclude or [])
            if cls._normalize_metadata_text(item, limit=limit)
        }
        for candidate in candidates:
            text = cls._usable_fallback_copy_text(candidate, limit=limit, prompt=prompt)
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            fragments.append(text.rstrip())
            seen.add(key)
            if len(fragments) >= max_items:
                break
        return fragments

    @classmethod
    def _fallback_headline_copy(
        cls,
        *,
        prompt: str,
        claim_evidence_pairs: list[dict[str, str]],
        desired_outcomes: list[str],
        key_value_proposition: Any,
        headline_direction: Any,
        primary_campaign_theme: Any,
        core_audience_message: Any,
    ) -> str:
        candidates: list[Any] = [
            *desired_outcomes[:2],
            key_value_proposition,
            *[pair.get("claim") for pair in claim_evidence_pairs if isinstance(pair, dict)],
            primary_campaign_theme,
            headline_direction,
            core_audience_message,
        ]
        fragments = cls._fallback_copy_fragments(
            candidates,
            prompt=prompt,
            limit=80,
            max_items=1,
        )
        if fragments:
            return fragments[0].rstrip(" .!?")
        prompt_topic = cls._prompt_topic_summary(prompt)
        if prompt_topic:
            return cls._headline_from_prompt_topic(prompt_topic)
        return "Brand Update"

    @classmethod
    def _fallback_body_copy(
        cls,
        *,
        prompt: str,
        headline: str,
        core_audience_message: Any,
        claim_evidence_pairs: list[dict[str, str]],
        trust_builders: list[str],
        proof_points: list[str],
        research_highlights: list[str],
        supporting_copy_direction: Any,
        key_value_proposition: Any,
    ) -> str:
        claim_lines = cls._claim_evidence_pair_lines(claim_evidence_pairs, limit=2)
        fragments = cls._fallback_copy_fragments(
            [
                core_audience_message,
                *claim_lines,
                *trust_builders[:2],
                *proof_points[:2],
                *research_highlights[:2],
                supporting_copy_direction,
                key_value_proposition,
            ],
            prompt=prompt,
            limit=180,
            max_items=2,
            exclude=[headline],
        )
        if fragments:
            return cls._normalize_metadata_text(" ".join(fragments), limit=220)
        prompt_topic = cls._prompt_topic_summary(prompt)
        if prompt_topic:
            return cls._body_from_prompt_topic(prompt_topic)
        return "See the details in a concrete, audience-relevant way."

    @classmethod
    def _fallback_cta_copy(
        cls,
        *,
        prompt: str,
        cta_intent: Any,
        primary_goal: Any,
        topic_focus: str,
        comparison_points: list[str],
        proof_cues: list[str],
        trust_signals: list[str],
    ) -> str:
        direct_cta = cls._usable_fallback_copy_text(cta_intent, limit=44, prompt=prompt)
        if direct_cta and len(direct_cta.split()) <= 6:
            return direct_cta.rstrip(" .!?")

        normalized_goal = cls._normalize_metadata_text(primary_goal, limit=80).casefold()
        normalized_intent = cls._normalize_metadata_text(cta_intent, limit=120).casefold()
        normalized_topic = cls._normalize_metadata_text(topic_focus, limit=120).casefold()

        if any(token in normalized_goal or token in normalized_intent for token in ("demo", "consult", "call")):
            return "Book a demo"
        if any(token in normalized_goal or token in normalized_intent for token in ("download", "guide", "report", "ebook")):
            return "Get the guide"
        if any(token in normalized_goal or token in normalized_intent for token in ("sign up", "signup", "register", "join", "subscribe")):
            return "Sign up"
        if comparison_points or any(
            token in normalized_intent or token in normalized_topic
            for token in ("compare", "comparison", "versus", "vs", "option", "options", "trade-off", "tradeoff", "difference")
        ):
            return "Compare the options"
        if proof_cues or trust_signals or any(
            token in normalized_intent or token in normalized_topic
            for token in ("proof", "trust", "clarity", "confidence", "details", "risk", "validate")
        ):
            return "See the details"
        if any(
            token in normalized_intent or token in normalized_topic
            for token in ("learn", "understand", "explain", "guide", "checklist", "tips", "strategy", "strategies", "how to")
        ):
            return "Get the details"
        return "See how it works"

    @classmethod
    def _looks_like_objection_response(cls, value: Any) -> bool:
        text = cls._normalize_metadata_text(value, limit=180)
        if not text:
            return False
        lowered = text.casefold()
        if any(lowered.startswith(prefix) for prefix in cls.OBJECTION_RESPONSE_INSTRUCTION_PREFIXES):
            return False
        return any(marker in lowered for marker in cls.OBJECTION_RESPONSE_MARKERS)

    @classmethod
    def _fallback_objection_handling_copy(
        cls,
        *,
        objections: list[str],
        pain_points: list[str],
        proof_cues: list[str],
        trust_signals: list[str],
        comparison_points: list[str],
        research_highlights: list[str],
    ) -> str:
        objection = cls._normalize_metadata_text(objections[0] if objections else "", limit=160)
        pain_point = cls._normalize_metadata_text(pain_points[0] if pain_points else "", limit=140)
        proof_cue = cls._normalize_metadata_text(proof_cues[0] if proof_cues else "", limit=140)
        trust_signal = cls._normalize_metadata_text(trust_signals[0] if trust_signals else "", limit=140)
        comparison_point = cls._normalize_metadata_text(comparison_points[0] if comparison_points else "", limit=140)
        research_highlight = cls._normalize_metadata_text(research_highlights[0] if research_highlights else "", limit=140)
        objection_context = f"{objection} {pain_point}".casefold()

        if any(
            token in objection_context
            for token in ("switch", "switching", "migrate", "migration", "change", "onboarding", "implementation", "rollout")
        ):
            anchor = trust_signal or proof_cue or "Guided onboarding"
            return cls._normalize_metadata_text(
                f"{anchor.rstrip('.')} so the next step feels lower-risk without forcing an overnight change.",
                limit=180,
            )
        if any(
            token in objection_context
            for token in ("risk", "return", "returns", "trust", "confidence", "opaque", "clarity", "clear", "proof")
        ):
            anchor = proof_cue or trust_signal or research_highlight or comparison_point or "Transparent downside framing"
            return cls._normalize_metadata_text(
                f"{anchor.rstrip('.')} with transparent downside framing so the trade-off feels clearer and easier to trust.",
                limit=180,
            )
        if any(
            token in objection_context
            for token in ("price", "pricing", "cost", "budget", "expensive", "afford", "value")
        ):
            anchor = comparison_point or proof_cue or trust_signal or "Transparent price framing"
            return cls._normalize_metadata_text(
                f"{anchor.rstrip('.')} so the value is easier to compare without guesswork.",
                limit=180,
            )
        anchor = proof_cue or trust_signal or comparison_point or research_highlight
        if anchor:
            return cls._normalize_metadata_text(
                f"{anchor.rstrip('.')} so the next step feels supported and lower risk.",
                limit=180,
            )
        if pain_point:
            return cls._normalize_metadata_text(
                "Without extra complexity, the next step gives the audience a clearer path forward.",
                limit=180,
            )
        return ""

    @classmethod
    def _sync_scene_graph_copy_from_text_payload(
        cls,
        *,
        elements: list[dict[str, Any]],
        text_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        metadata = cls._coerce_mapping(text_payload.get("metadata"))
        supporting_line = cls._normalize_metadata_text(
            metadata.get("supporting_line") or text_payload.get("body"),
            limit=220,
        )
        proof_points = cls._normalize_metadata_list(metadata.get("proof_points"), limit=4)
        stat_highlights = cls._normalize_metadata_list(metadata.get("stat_highlights"), limit=3)
        synced: list[dict[str, Any]] = []
        for element in elements:
            normalized = dict(element)
            role = str(normalized.get("role") or "").strip().lower()
            if role == "headline":
                normalized["text"] = text_payload.get("headline", "")
            elif role == "body":
                normalized["text"] = text_payload.get("body", "")
            elif role == "supporting_line":
                normalized["text"] = supporting_line
            elif role == "cta":
                normalized["text"] = text_payload.get("cta", "")
            elif role == "proof_points":
                normalized["text"] = proof_points or stat_highlights or cls._sentences(text_payload.get("body"))[:3]
            elif role == "stat_highlights":
                normalized["text"] = stat_highlights
            elif role == "section_label":
                normalized["text"] = cls._normalize_metadata_text(metadata.get("section_label"), limit=64)
            synced.append(normalized)
        return synced

    @classmethod
    def _contains_disallowed_glyphs(cls, value: str) -> bool:
        return bool(cls.DISALLOWED_GLYPH_PATTERN.search(value or "") or cls.MOJIBAKE_SYMBOL_PATTERN.search(value or ""))

    @staticmethod
    def _scene_graph_visible_elements(scene_graph: GenerationSceneGraph) -> list[Any]:
        return [element for element in scene_graph.elements if element.visible]

    def _should_apply_support_fallback(
        self,
        *,
        scene_graph: GenerationSceneGraph,
        validation_report: SceneGraphValidationReport,
    ) -> bool:
        visible_elements = self._scene_graph_visible_elements(scene_graph)
        content_elements = [element for element in visible_elements if element.role != "background"]
        severe_rules = {
            "missing_headline",
            "logo_required",
            "insufficient_scene_graph_structure",
            "missing_visual_emphasis",
            "asset_strategy_unfulfilled",
            "asset_strategy_overloaded",
            "icon_stamp_column",
            "icon_overuse_with_hero_image",
            "prompt_echo_copy",
            "topic_anchor_missing",
        }
        if len(content_elements) < 4:
            return True
        if any(issue.rule_id in severe_rules for issue in validation_report.issues):
            return True
        return False

    @staticmethod
    def _should_request_fresh_replan(validation_report: SceneGraphValidationReport) -> bool:
        severe_rules = {
            "missing_headline",
            "insufficient_scene_graph_structure",
            "missing_visual_emphasis",
            "topic_anchor_missing",
            "prompt_echo_copy",
        }
        return any(issue.rule_id in severe_rules for issue in validation_report.issues)

    @staticmethod
    def _fresh_replan_note(validation_report: SceneGraphValidationReport) -> str:
        issues = [str(issue.rule_id or "").strip() for issue in validation_report.issues if str(issue.rule_id or "").strip()]
        if not issues:
            return (
                "Discard the prior weak scene graph and create a fresh plan from the user prompt, "
                "brand knowledge, objective, and guardrails."
            )
        return (
            "Discard the prior weak scene graph instead of repairing around it. "
            "Create a fresh plan from the user prompt, brand knowledge, objective, and guardrails. "
            f"The prior plan failed on: {', '.join(issues)}."
        )

    @classmethod
    def _scene_graph_has_authoritative_geometry(cls, scene_graph: GenerationSceneGraph | None) -> bool:
        if not isinstance(scene_graph, GenerationSceneGraph):
            return False
        geometry_count = 0
        anchored_roles: set[str] = set()
        for element in scene_graph.elements:
            if not element.visible or element.role == "background":
                continue
            geometry = element.geometry or SceneGraphGeometry()
            if all(getattr(geometry, attr, None) is not None for attr in ("x", "y", "width", "height")):
                geometry_count += 1
                normalized_role = str(element.role or "").strip().lower()
                anchored_roles.add(normalized_role)
                if cls._scene_graph_element_is_visual_image_like(element):
                    anchored_roles.add("image")
        return geometry_count >= 3 or {"headline", "image", "cta"} <= anchored_roles

    @classmethod
    def _compiled_context_has_authoritative_layout(cls, compiled_context: dict[str, Any] | None) -> bool:
        context = dict(compiled_context or {})
        template_fit = cls._coerce_mapping(context.get("template_fit_brief"))
        brand_visual = cls._coerce_mapping(context.get("brand_visual_brief"))
        design_system = cls._coerce_mapping(brand_visual.get("design_system"))
        layout_dna = (
            template_fit.get("template_layout_dna")
            or design_system.get("template_layout_dna")
            or design_system.get("layout_dna")
        )
        sequence_pack = template_fit.get("sequence_pack") or design_system.get("template_sequence_pack")
        if isinstance(layout_dna, dict) and (
            layout_dna.get("zone_map")
            or layout_dna.get("zones")
            or layout_dna.get("layout_type")
        ):
            return True
        if isinstance(sequence_pack, dict) and (
            sequence_pack.get("pages")
            or sequence_pack.get("sequence")
            or sequence_pack.get("story_arc_roles")
            or sequence_pack.get("slides")
            or sequence_pack.get("sequence_cues")
        ):
            return True
        return False

    @classmethod
    def _scene_graph_element_is_visual_image_like(cls, element: SceneGraphElement | dict[str, Any] | None) -> bool:
        if element is None:
            return False
        if isinstance(element, dict):
            visible = bool(element.get("visible", True))
            role = str(element.get("role") or "").strip().casefold()
            element_type = str(element.get("element_type") or "").strip().casefold()
            asset_payload = element.get("asset") if isinstance(element.get("asset"), dict) else {}
        else:
            visible = bool(element.visible)
            role = str(element.role or "").strip().casefold()
            element_type = str(element.element_type or "").strip().casefold()
            asset_payload = (
                element.asset.model_dump(mode="json")
                if getattr(element, "asset", None) is not None
                else {}
            )
        if not visible or role == "background":
            return False
        if role == "image" or element_type == "image":
            return True
        image_like_roles = {
            "hero_visual",
            "hero_image",
            "primary_visual",
            "supporting_visual",
            "supporting_visuals",
            "illustration",
            "illustration_group",
            "infographic_cluster",
            "visual_cluster",
        }
        if role in image_like_roles:
            return True
        asset_role = str((asset_payload or {}).get("asset_role") or "").strip().casefold()
        return any(
            token in asset_role
            for token in ("image", "illustration", "photo", "render", "visual", "infographic")
        )

    @staticmethod
    def _compact_scene_graph_geometry(scene_graph: GenerationSceneGraph | None, limit: int = 8) -> str:
        if not isinstance(scene_graph, GenerationSceneGraph):
            return ""
        geometry_manifest: list[dict[str, Any]] = []
        for element in scene_graph.elements:
            if (
                not element.visible
                or element.role == "background"
                or str(element.element_type or "").strip().casefold() == "multi_slide_sequence"
            ):
                continue
            geometry = element.geometry or SceneGraphGeometry()
            if not all(getattr(geometry, attr, None) is not None for attr in ("x", "y", "width", "height")):
                continue
            entry = {
                "role": str(element.role or "").strip().lower(),
                "type": str(element.element_type or "").strip().lower(),
                "x": round(float(geometry.x), 3),
                "y": round(float(geometry.y), 3),
                "w": round(float(geometry.width), 3),
                "h": round(float(geometry.height), 3),
            }
            if geometry.anchor:
                entry["anchor"] = str(geometry.anchor)
            if geometry.z_index is not None:
                entry["z"] = int(geometry.z_index)
            if element.validation_hints:
                text_role = str((element.validation_hints or {}).get("text_role") or "").strip()
                if text_role:
                    entry["text_role"] = text_role
            geometry_manifest.append(entry)
            if len(geometry_manifest) >= limit:
                break
        if not geometry_manifest:
            return ""
        return json.dumps(geometry_manifest, separators=(",", ":"), ensure_ascii=True)

    @classmethod
    def _compact_layout_dna_contract(cls, compiled_context: dict[str, Any] | None, limit: int = 8) -> str:
        context = dict(compiled_context or {})
        template_fit = cls._coerce_mapping(context.get("template_fit_brief"))
        brand_visual = cls._coerce_mapping(context.get("brand_visual_brief"))
        design_system = cls._coerce_mapping(brand_visual.get("design_system"))
        layout_dna = (
            template_fit.get("template_layout_dna")
            or design_system.get("template_layout_dna")
            or design_system.get("layout_dna")
        )
        if not isinstance(layout_dna, dict):
            return ""
        payload: dict[str, Any] = {}
        layout_type = cls._normalize_metadata_text(layout_dna.get("layout_type"), limit=64)
        canvas_ratio = cls._normalize_metadata_text(layout_dna.get("canvas_ratio"), limit=32)
        if layout_type:
            payload["layout_type"] = layout_type
        if canvas_ratio:
            payload["ratio"] = canvas_ratio
        zones: list[dict[str, Any]] = []
        raw_zones = layout_dna.get("zone_map") or layout_dna.get("zones") or []
        if isinstance(raw_zones, dict):
            raw_zones = [
                {"role": key, **(value if isinstance(value, dict) else {})}
                for key, value in raw_zones.items()
            ]
        for item in raw_zones[:limit]:
            if not isinstance(item, dict):
                continue
            zone = {
                "role": cls._normalize_metadata_text(item.get("role") or item.get("zone_role"), limit=32),
                "x": item.get("x"),
                "y": item.get("y"),
                "w": item.get("width") if item.get("width") is not None else item.get("w"),
                "h": item.get("height") if item.get("height") is not None else item.get("h"),
            }
            if item.get("anchor"):
                zone["anchor"] = cls._normalize_metadata_text(item.get("anchor"), limit=24)
            if item.get("priority"):
                zone["priority"] = cls._normalize_metadata_text(item.get("priority"), limit=16)
            if all(zone.get(key) is not None for key in ("x", "y", "w", "h")) and zone.get("role"):
                for key in ("x", "y", "w", "h"):
                    zone[key] = round(float(zone[key]), 3)
                zones.append(zone)
        if zones:
            payload["zones"] = zones
        if not payload:
            return ""
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)

    @classmethod
    def _final_render_grounding_sections(
        cls,
        *,
        request: AIOrchestrationRequest,
        creative_decision: CreativeDecisionPayload,
        text_payload: StructuredTextPayload,
        compiled_context: dict[str, Any] | None,
        reference_assets: list[dict[str, Any]] | None,
        allow_template_surface_imitation: bool = False,
    ) -> list[str]:
        compiled_context = dict(compiled_context or {})
        metadata = text_payload.metadata or {}
        visual_identity = request.resolved_brand_context.get("visual_identity", {}) or {}
        asset_strategy = (creative_decision.asset_strategy if creative_decision else {}) or {}
        template_surface_policy = str(asset_strategy.get("template_surface_policy") or "").strip().lower()
        design_style = cls._normalize_metadata_text(metadata.get("design_style"), limit=80)
        visual_direction = cls._normalize_metadata_text(metadata.get("visual_direction"), limit=180)
        preferred_scene = cls._normalize_metadata_text(metadata.get("image_prompt"), limit=220)
        layout_decision = cls._compact_layout_decision(request.layout_decision)
        visual_knowledge_brief = ContextCompilerService.coerce_visual_knowledge_brief(
            compiled_context.get("visual_knowledge_brief"),
        )
        direct_brand_grounding = cls._brand_knowledge_visual_grounding(visual_knowledge_brief)
        grounding_mode = cls._normalize_metadata_text(visual_knowledge_brief.get("grounding_mode"), limit=32)
        grounding_strength = cls._normalize_metadata_text(visual_knowledge_brief.get("grounding_strength"), limit=32)
        grounding_abstention_reason = cls._normalize_metadata_text(
            visual_knowledge_brief.get("abstention_reason"),
            limit=64,
        )
        template_suppressed = bool(visual_knowledge_brief.get("template_suppressed"))
        include_reference_system = bool(reference_assets) or bool(visual_identity.get("reusable_design_assets"))
        reusable_assets = cls._compact_named_items(visual_identity.get("reusable_design_assets"), limit=4)
        reference_summary = cls._compact_reference_assets(reference_assets or [])
        dominant_visual_system = cls._normalized_dominant_visual_system(asset_strategy) or "generated_image"
        supporting_visual_system = cls._normalized_supporting_visual_system(asset_strategy)
        sections = [
            (
                f"Brand knowledge grounding mode: {grounding_mode or 'brand_knowledge'} (strength: {grounding_strength or 'supported'})."
                if direct_brand_grounding
                else (
                    f"Brand knowledge grounding mode: llm_fallback (reason: {grounding_abstention_reason})."
                    if grounding_abstention_reason
                    else "Brand knowledge grounding mode: llm_fallback."
                )
            ),
            (
                f"Brand knowledge grounding: {direct_brand_grounding}. Treat these retrieved brand-knowledge cues as the primary visual grounding contract."
                if direct_brand_grounding
                else "Brand knowledge grounding: no retrieved brand knowledge is available, so infer the visual through the approved copy, message strategy, and brand system."
            ),
            (
                "If retrieved brand knowledge is present, do not override it with a generic invented scene. Use model reasoning only to combine the retrieved cues coherently."
                if direct_brand_grounding
                else "Because retrieved brand knowledge is absent, derive the visual direction from the approved copy, message strategy, and brand system."
            ),
            (
                "Template-derived cues were suppressed because stronger visual identity or mood-board evidence exists."
                if direct_brand_grounding and template_suppressed
                else ""
            ),
            (
                "If the active brand grounding is fallback-only, use template and metadata cues only for structure, palette, spacing, and composition. Do not literalize template copy."
                if direct_brand_grounding and grounding_strength == "fallback_only"
                else ""
            ),
            f"Layout approach: {layout_decision}.",
            f"Dominant visual system: {dominant_visual_system}.",
            f"Supporting visual system: {supporting_visual_system or 'none'}.",
            (
                f"Reusable brand design assets available as stylistic cues: {reusable_assets}."
                if include_reference_system and reusable_assets and reusable_assets != "None"
                else ""
            ),
            (
                f"Reference asset system available: {reference_summary}."
                if include_reference_system and reference_summary and template_surface_policy != "style_reference_only"
                else ""
            ),
            (
                "When the active template policy is style-reference-only, preserve the uploaded sample's composition skeleton, region proportions, negative space, sequencing, and craft direction as closely as possible while reinterpreting all artwork and text from scratch. Do not trace or copy the literal sample surface."
                if template_surface_policy == "style_reference_only" and not allow_template_surface_imitation
                else ""
            ),
            (f"Fallback design style hint: {design_style}." if design_style else ""),
            (f"Fallback visual direction hint: {visual_direction}." if visual_direction else ""),
            (f"Fallback preferred scene hint: {preferred_scene}." if preferred_scene else ""),
        ]
        return [section for section in sections if section]

    @classmethod
    def _research_editorial_prompt_section(
        cls,
        request: AIOrchestrationRequest,
        compiled_context: dict[str, Any] | None = None,
    ) -> str:
        context = dict(compiled_context or {})
        request_brief = getattr(request, "research_editorial_brief", None)
        brief = (
            context.get("research_editorial_brief")
            if isinstance(context.get("research_editorial_brief"), dict)
            else request_brief
            if isinstance(request_brief, dict)
            else {}
        )
        if not isinstance(brief, dict):
            return (
                "Research discipline: prefer source-backed specificity when available, and never invent unsupported "
                "numbers, rankings, timelines, or market claims."
            )
        claim_pairs = cls._claim_evidence_pairs_from_research_brief(brief, limit=2)
        verified_facts = (
            (brief.get("fact_model") or {}).get("verified_facts")
            if isinstance(brief.get("fact_model"), dict)
            else []
        )
        if claim_pairs or verified_facts:
            return (
                "Research discipline: anchor specific claims to verified facts and approved claim-evidence pairs only. "
                "Keep the synthesis concise, and do not add extra statistics, rankings, or market assertions that are not supported."
            )
        needs_live_research = bool(brief.get("needs_live_research"))
        research_status = cls._normalize_metadata_text(brief.get("research_status"), limit=32).casefold()
        if needs_live_research or research_status in {"unavailable", "required", "missing"}:
            return (
                "Research discipline: when verified research is limited, stay descriptive and principle-led. "
                "Do not invent exact figures, dates, performance claims, or factual certainty."
            )
        return (
            "Research discipline: prefer source-backed specificity when available, and never invent unsupported "
            "numbers, rankings, timelines, or market claims."
        )

    @staticmethod
    def _consultant_quality_contract(*, for_visual_only: bool, for_carousel: bool) -> list[str]:
        layout_target = (
            "Use an advanced explanatory slide composition with deliberate grouping, alignment, rhythm, and negative space; "
            "do not collapse into a generic top-heading, middle-image, bottom-footer layout."
            if for_carousel
            else "Use an advanced explanatory composition with deliberate grouping, alignment, rhythm, and negative space; "
            "do not collapse into a generic top-heading, centered-visual, bottom-footer poster."
        )
        copy_target = (
            "Copy discipline: keep the message concise, high-signal, and editorially tight. Prefer one sharp headline, one supporting line, and only essential proof points. Remove filler, repetition, generic hype, and broad claims."
            if not for_visual_only
            else "Message discipline: make the visual support a concise, high-signal story rather than a vague or generic mood piece."
        )
        return [
            copy_target,
            f"Layout discipline: {layout_target}",
            "Brand and asset discipline: every image, icon, chart cue, or decorative asset must earn its place by explaining the message and matching the brand system. Prefer fewer stronger elements over decorative clutter or generic stock filler.",
        ]

    @classmethod
    def _multimodal_balance_contract(
        cls,
        *,
        format_name: str,
        supporting_line: str = "",
        proof_points: list[str] | None = None,
        claim_evidence_pairs: list[dict[str, str]] | None = None,
        for_visual_only: bool,
    ) -> list[str]:
        normalized_format = str(format_name or "").strip().casefold()
        proof_count = len([item for item in (proof_points or []) if cls._normalize_metadata_text(item, limit=140)])
        claim_count = len(
            [
                pair
                for pair in (claim_evidence_pairs or [])
                if isinstance(pair, dict)
                and (
                    cls._normalize_metadata_text(pair.get("claim"), limit=140)
                    or cls._normalize_metadata_text(pair.get("evidence"), limit=180)
                )
            ]
        )
        has_supporting_line = bool(cls._normalize_metadata_text(supporting_line, limit=220))
        evidence_density = proof_count + claim_count + (1 if has_supporting_line else 0)

        if for_visual_only:
            base = (
                "Premium multimodal balance: build one dominant explanatory visual system with one controlled supporting layer. "
                "Keep enough calm negative space for the backend text overlay, and do not let decorative visuals overpower the message."
            )
        elif normalized_format == "carousel":
            base = (
                "Premium multimodal balance: each slide should feel visually led but editorially grounded. "
                "Let the main image or explainer structure carry the concept, while headline, supporting line, and proof modules add only the necessary meaning."
            )
        elif normalized_format == "infographic":
            base = (
                "Premium multimodal balance: make the canvas a true visual explainer, not a text slab and not a decorative poster. "
                "Distribute evidence across modular visual sections with one clear focal path."
            )
        else:
            base = (
                "Premium multimodal balance: keep the creative visually led with concise text support. "
                "Do not turn the layout into either a text-heavy block or an empty hero image with token copy."
            )

        sections = [base]
        if evidence_density >= 4:
            sections.append(
                "Evidence-density rule: because the content carries multiple proof or claim modules, use deliberate evidence containers or callout regions instead of stacking all copy into one dense paragraph block."
            )
        else:
            sections.append(
                "Restraint rule: keep supporting evidence selective and high-signal so the composition stays premium rather than crowded."
            )
        sections.append(
            "Do not duplicate the same message in every modality. The visual should explain something the text does not fully restate, and the text should clarify what the visual implies."
        )
        return sections

    @staticmethod
    def _element_normalized_area(element: Any) -> float:
        geometry = getattr(element, "geometry", None)
        if geometry is None:
            return 0.0
        try:
            width = float(geometry.width if geometry.width is not None else 0.0)
            height = float(geometry.height if geometry.height is not None else 0.0)
        except (TypeError, ValueError):
            return 0.0
        if width <= 0 or height <= 0:
            return 0.0
        units = str(getattr(geometry, "units", "") or "normalized").strip().lower()
        if units == "normalized" or max(abs(width), abs(height)) <= 1.5:
            return max(min(width * height, 1.0), 0.0)
        return 0.0

    @classmethod
    def _scene_graph_text_like_element(cls, element: Any) -> bool:
        role = str(getattr(element, "role", "") or getattr(element, "element_type", "")).strip().lower()
        element_type = str(getattr(element, "element_type", "")).strip().lower()
        return role in {
            "headline",
            "supporting_line",
            "body",
            "proof_points",
            "stat_highlights",
            "cta",
            "section_label",
            "footer",
            "legal",
        } or element_type in {"text", "text_block", "text_group", "headline"}

    @classmethod
    def _multimodal_balance_issue(
        cls,
        scene_graph: GenerationSceneGraph,
        *,
        format_name: str,
    ) -> str:
        normalized_format = str(format_name or "").strip().casefold()
        if normalized_format not in {"static", "carousel", "infographic", "story", "poster"}:
            return ""
        visible_elements = [element for element in scene_graph.elements if element.visible and element.role != "background"]
        if not visible_elements:
            return ""
        text_elements = [element for element in visible_elements if cls._scene_graph_text_like_element(element)]
        image_elements = [element for element in visible_elements if cls._scene_graph_element_is_visual_image_like(element)]
        if not text_elements or not image_elements:
            return ""
        text_area = sum(cls._element_normalized_area(element) for element in text_elements)
        image_area = sum(cls._element_normalized_area(element) for element in image_elements)
        if text_area >= 0.58 and image_area <= 0.18:
            return "text_heavy"
        if image_area >= 0.78 and text_area <= 0.1 and len(text_elements) <= 2:
            return "image_heavy"
        return ""

    @classmethod
    def _reference_family_zone_boxes(cls, value: Any, *, limit: int = 10) -> list[dict[str, Any]]:
        zone_boxes: list[dict[str, Any]] = []
        for item in cls._coerce_list(value)[:limit]:
            if not isinstance(item, dict):
                continue
            role = cls._normalize_metadata_text(item.get("role"), limit=32).casefold()
            if not role:
                continue
            try:
                x = float(item.get("x"))
                y = float(item.get("y"))
                w = float(item.get("w") if item.get("w") is not None else item.get("width"))
                h = float(item.get("h") if item.get("h") is not None else item.get("height"))
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
                }
            )
        return zone_boxes

    @classmethod
    def _reference_family_zone_role_candidates(cls, role: str) -> list[str]:
        normalized = str(role or "").strip().casefold()
        mapping = {
            "headline": ["headline"],
            "supporting_line": ["supporting_line", "body"],
            "body": ["body", "supporting_line", "proof_points"],
            "proof_points": ["proof_points", "stat_highlights", "body"],
            "stat_highlights": ["stat_highlights", "proof_points"],
            "cta": ["cta", "footer"],
            "footer": ["footer", "cta", "legal"],
            "legal": ["legal", "footer"],
            "logo": ["logo"],
            "image": ["image", "hero_visual", "hero_image", "primary_visual", "illustration"],
            "hero_visual": ["hero_visual", "image", "hero_image", "primary_visual"],
            "hero_image": ["hero_image", "hero_visual", "image", "primary_visual"],
            "primary_visual": ["primary_visual", "hero_visual", "image", "hero_image"],
            "illustration": ["illustration", "primary_visual", "hero_visual", "image"],
        }
        return mapping.get(normalized, [normalized])

    @classmethod
    def _reference_family_role_box(
        cls,
        zone_boxes: list[dict[str, Any]],
        role: str,
        *,
        image_like: bool = False,
    ) -> dict[str, Any]:
        candidates = cls._reference_family_zone_role_candidates(role)
        if image_like:
            candidates = [
                *candidates,
                "hero_visual",
                "hero_image",
                "primary_visual",
                "illustration",
                "image",
            ]
        desired = {candidate for candidate in candidates if candidate}
        for zone in zone_boxes:
            zone_role = str(zone.get("role") or "").strip().casefold()
            if zone_role in desired:
                return zone
        return {}

    @staticmethod
    def _normalized_geometry_iou(current: dict[str, Any], target: dict[str, Any]) -> float:
        try:
            current_x = float(current.get("x"))
            current_y = float(current.get("y"))
            current_w = float(current.get("width") if current.get("width") is not None else current.get("w"))
            current_h = float(current.get("height") if current.get("height") is not None else current.get("h"))
            target_x = float(target.get("x"))
            target_y = float(target.get("y"))
            target_w = float(target.get("width") if target.get("width") is not None else target.get("w"))
            target_h = float(target.get("height") if target.get("height") is not None else target.get("h"))
        except (TypeError, ValueError):
            return 0.0
        if min(current_w, current_h, target_w, target_h) <= 0:
            return 0.0
        intersection_x1 = max(current_x, target_x)
        intersection_y1 = max(current_y, target_y)
        intersection_x2 = min(current_x + current_w, target_x + target_w)
        intersection_y2 = min(current_y + current_h, target_y + target_h)
        intersection_w = max(0.0, intersection_x2 - intersection_x1)
        intersection_h = max(0.0, intersection_y2 - intersection_y1)
        intersection = intersection_w * intersection_h
        if intersection <= 0:
            return 0.0
        current_area = current_w * current_h
        target_area = target_w * target_h
        union = current_area + target_area - intersection
        if union <= 0:
            return 0.0
        return intersection / union

    @classmethod
    def _reference_family_active_slide_profile(
        cls,
        compiled_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        profile = cls._reference_family_profile(compiled_context)
        slide_profiles = [dict(item) for item in profile.get("slide_profiles", []) if isinstance(item, dict)]
        return slide_profiles[0] if slide_profiles else {}

    @classmethod
    def _apply_reference_family_scene_defaults(
        cls,
        scene_graph_payload: dict[str, Any],
        *,
        compiled_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = dict(scene_graph_payload or {})
        profile = cls._reference_family_profile(compiled_context)
        if not profile:
            return payload
        slide_profile = cls._reference_family_active_slide_profile(compiled_context)
        zone_boxes = cls._reference_family_zone_boxes(slide_profile.get("zone_boxes") or profile.get("zone_boxes"))
        if not zone_boxes:
            return payload
        lock_strength = cls._normalize_metadata_text(profile.get("layout_lock_strength"), limit=24).casefold()
        minimum_iou = {"strict": 0.62, "strong": 0.45, "guided": 0.3}.get(lock_strength, 0.0)
        normalized_elements: list[dict[str, Any]] = []
        for element in cls._coerce_list(payload.get("elements")):
            if not isinstance(element, dict):
                normalized_elements.append(element)
                continue
            element_copy = dict(element)
            if not bool(element_copy.get("visible", True)):
                normalized_elements.append(element_copy)
                continue
            role = str(element_copy.get("role") or "").strip().casefold()
            if role == "background":
                normalized_elements.append(element_copy)
                continue
            target_box = cls._reference_family_role_box(
                zone_boxes,
                role,
                image_like=cls._scene_graph_element_is_visual_image_like(element_copy),
            )
            if not target_box:
                normalized_elements.append(element_copy)
                continue
            geometry = cls._coerce_mapping(element_copy.get("geometry"))
            current_iou = cls._normalized_geometry_iou(geometry, target_box) if geometry else 0.0
            if not geometry or current_iou < minimum_iou:
                element_copy["geometry"] = {
                    "x": target_box["x"],
                    "y": target_box["y"],
                    "width": target_box["w"],
                    "height": target_box["h"],
                    "units": "normalized",
                }
            validation_hints = cls._coerce_mapping(element_copy.get("validation_hints"))
            validation_hints.setdefault("reference_zone_role", str(target_box.get("role") or ""))
            validation_hints["reference_family_lock_strength"] = lock_strength or "guided"
            if validation_hints:
                element_copy["validation_hints"] = validation_hints
            normalized_elements.append(element_copy)
        styles = cls._coerce_mapping(payload.get("styles"))
        if not styles.get("layout_archetype"):
            styles["layout_archetype"] = (
                cls._normalize_metadata_text(slide_profile.get("layout_type"), limit=64)
                or next(iter(cls._normalize_metadata_list(profile.get("layout_archetypes"), limit=1)), "")
            )
        styles["reference_family_lock_strength"] = lock_strength or "guided"
        payload["styles"] = styles
        payload["elements"] = normalized_elements
        payload = cls._apply_context_visual_craft_hints(
            payload,
            compiled_context=compiled_context,
        )
        return payload

    @classmethod
    def _context_visual_craft_hints(
        cls,
        compiled_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        context = cls._coerce_mapping(compiled_context)
        brand_visual = cls._coerce_mapping(context.get("brand_visual_brief"))
        design_system = cls._coerce_mapping(brand_visual.get("design_system"))
        profile = cls._reference_family_profile(compiled_context)

        visual_craft = cls._coerce_mapping(
            design_system.get("visual_craft")
            or brand_visual.get("visual_craft")
            or profile.get("visual_craft")
        )
        composition_logic = cls._coerce_mapping(
            design_system.get("composition_logic")
            or brand_visual.get("composition_logic")
            or profile.get("composition_logic")
        )
        subject_semantics = cls._coerce_mapping(
            design_system.get("subject_semantics")
            or brand_visual.get("subject_semantics")
            or profile.get("subject_semantics")
        )

        def first_value(mapping: dict[str, Any], *keys: str) -> str:
            for key in keys:
                value = mapping.get(key)
                if isinstance(value, list):
                    value = next((item for item in value if str(item or "").strip()), "")
                text = cls._normalize_metadata_text(value, limit=80).casefold()
                if text:
                    return text
            return ""

        hints: dict[str, Any] = {}
        for target_key, source_keys in {
            "visual_depth_style": ("depth_styles", "depth_style"),
            "visual_rendering_style": ("rendering_styles", "rendering_style"),
            "visual_lighting_mode": ("lighting_modes", "lighting"),
            "visual_polish_level": ("polish_levels", "polish_level"),
            "composition_balance": ("balances", "balance"),
            "composition_framing": ("framings", "framing"),
            "composition_layering": ("layerings", "layering"),
            "subject_scene_type": ("scene_types", "scene_type"),
            "subject_abstraction_level": ("abstraction_levels", "abstraction_level"),
        }.items():
            source_mapping = (
                visual_craft
                if target_key.startswith("visual_")
                else composition_logic
                if target_key.startswith("composition_")
                else subject_semantics
            )
            value = first_value(source_mapping, *source_keys)
            if value:
                hints[target_key] = value

        primary_subjects = cls._normalize_metadata_list(subject_semantics.get("primary_subjects"), limit=4)
        financial_objects = cls._normalize_metadata_list(subject_semantics.get("financial_objects"), limit=4)
        material_cues = cls._normalize_metadata_list(visual_craft.get("material_cues"), limit=4)
        dimensionality_cues = cls._normalize_metadata_list(visual_craft.get("dimensionality_cues"), limit=4)
        if primary_subjects:
            hints["primary_subjects"] = primary_subjects
        if financial_objects:
            hints["financial_objects"] = financial_objects
        if material_cues:
            hints["material_cues"] = material_cues
        if dimensionality_cues:
            hints["dimensionality_cues"] = dimensionality_cues
        return hints

    @classmethod
    def _apply_context_visual_craft_hints(
        cls,
        scene_graph_payload: dict[str, Any],
        *,
        compiled_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        hints = cls._context_visual_craft_hints(compiled_context)
        if not hints:
            return scene_graph_payload
        payload = dict(scene_graph_payload or {})
        normalized_elements: list[dict[str, Any]] = []
        for element in cls._coerce_list(payload.get("elements")):
            if not isinstance(element, dict):
                normalized_elements.append(element)
                continue
            element_copy = dict(element)
            if cls._scene_graph_element_is_visual_image_like(element_copy):
                validation_hints = cls._coerce_mapping(element_copy.get("validation_hints"))
                for key, value in hints.items():
                    validation_hints.setdefault(key, value)
                element_copy["validation_hints"] = validation_hints
            normalized_elements.append(element_copy)
        payload["elements"] = normalized_elements
        return payload

    @classmethod
    def _reference_family_closeness(
        cls,
        scene_graph: GenerationSceneGraph,
        *,
        compiled_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        profile = cls._reference_family_profile(compiled_context)
        if not profile:
            return {"score": 1.0, "issues": []}
        slide_profile = cls._reference_family_active_slide_profile(compiled_context)
        zone_boxes = cls._reference_family_zone_boxes(slide_profile.get("zone_boxes") or profile.get("zone_boxes"))
        visible_roles: set[str] = set()
        for element in scene_graph.elements:
            if not element.visible:
                continue
            role = str(element.role or "").strip().casefold()
            if role:
                visible_roles.add(role)
            hint_role = cls._normalize_metadata_text((element.validation_hints or {}).get("reference_zone_role"), limit=32).casefold()
            if hint_role:
                visible_roles.add(hint_role)
            if cls._scene_graph_element_is_visual_image_like(element):
                visible_roles.update({"image", "hero_visual"})
        expected_roles = {
            str(role or "").strip().casefold()
            for role in cls._normalize_metadata_list(profile.get("preferred_zone_roles"), limit=12)
            if str(role or "").strip()
        }
        expected_image_roles = {
            str(role or "").strip().casefold()
            for role in cls._normalize_metadata_list(profile.get("approved_image_zone_roles"), limit=6)
            if str(role or "").strip()
        }
        module_patterns = {
            str(role or "").strip().casefold()
            for role in cls._normalize_metadata_list(profile.get("module_patterns"), limit=8)
            if str(role or "").strip()
        }
        issues: list[str] = []
        score = 1.0
        if expected_roles:
            overlap = len(expected_roles & visible_roles)
            coverage = overlap / max(len(expected_roles), 1)
            if coverage < 0.55:
                score -= 0.18
                issues.append("reference_family_zone_drift")
            elif coverage < 0.8:
                score -= 0.08
        if expected_image_roles and not (expected_image_roles & visible_roles):
            score -= 0.14
            issues.append("reference_family_image_zone_drift")
        current_archetype = str((scene_graph.styles or {}).get("layout_archetype") or (scene_graph.styles or {}).get("layout_type") or "").strip().casefold()
        target_archetypes = {
            str(item or "").strip().casefold()
            for item in cls._normalize_metadata_list(profile.get("layout_archetypes"), limit=6)
            if str(item or "").strip()
        }
        if current_archetype and target_archetypes and current_archetype not in target_archetypes:
            score -= 0.08
            issues.append("reference_family_layout_drift")
        module_role_map = {
            "cover_hero_split": {"headline", "image", "hero_visual"},
            "proof_grid": {"proof_points", "proof_point", "proof_module"},
            "stat_callout": {"stat_highlights", "stat_highlight"},
            "closing_cta_strip": {"cta", "footer"},
            "comparison_module": {"comparison", "body", "proof_points"},
            "sequence_explainer": {"body", "proof_points", "supporting_line"},
            "icon_label_stack": {"icon", "image"},
        }
        missing_modules = 0
        for pattern in module_patterns:
            expected = module_role_map.get(pattern, set())
            if expected and not (expected & visible_roles):
                missing_modules += 1
        if module_patterns and missing_modules >= max(1, len(module_patterns) // 2):
            score -= 0.12
            issues.append("reference_family_module_drift")
        if zone_boxes:
            geometry_matches = 0
            geometry_scores: list[float] = []
            for zone in zone_boxes[:6]:
                role = str(zone.get("role") or "").strip().casefold()
                if not role:
                    continue
                best_iou = 0.0
                for element in scene_graph.elements:
                    if not element.visible or element.role == "background":
                        continue
                    candidates = {
                        str(element.role or "").strip().casefold(),
                        cls._normalize_metadata_text((element.validation_hints or {}).get("reference_zone_role"), limit=32).casefold(),
                    }
                    if cls._scene_graph_element_is_visual_image_like(element):
                        candidates.update({"image", "hero_visual", "hero_image", "primary_visual", "illustration"})
                    if role not in candidates:
                        continue
                    geometry = element.geometry or SceneGraphGeometry()
                    best_iou = max(
                        best_iou,
                        cls._normalized_geometry_iou(
                            {
                                "x": geometry.x,
                                "y": geometry.y,
                                "width": geometry.width,
                                "height": geometry.height,
                            },
                            zone,
                        ),
                    )
                if best_iou >= 0.45:
                    geometry_matches += 1
                geometry_scores.append(best_iou)
            if geometry_scores:
                average_iou = sum(geometry_scores) / len(geometry_scores)
                if geometry_matches < max(1, min(len(geometry_scores), 2)) or average_iou < 0.34:
                    score -= 0.14
                    issues.append("reference_family_geometry_drift")
        return {"score": max(round(score, 2), 0.0), "issues": issues}

    @classmethod
    def _prompt_sequence_pack(cls, compiled_context: dict[str, Any] | None) -> dict[str, Any]:
        context = dict(compiled_context or {})
        template_fit = cls._coerce_mapping(context.get("template_fit_brief"))
        for candidate in (
            template_fit.get("sequence_pack"),
            template_fit.get("template_sequence_pack"),
            context.get("sequence_pack"),
        ):
            mapping = cls._coerce_mapping(candidate)
            if mapping and (
                mapping.get("slides")
                or mapping.get("family_name")
                or mapping.get("sequence_kind")
                or mapping.get("sequence_cues")
            ):
                return mapping
        return {}

    @classmethod
    def _reference_family_profile(cls, compiled_context: dict[str, Any] | None) -> dict[str, Any]:
        context = dict(compiled_context or {})
        profile = cls._coerce_mapping(context.get("reference_family_profile"))
        return profile if profile else {}

    @classmethod
    def _reference_family_slide_profile(
        cls,
        profile: dict[str, Any],
        slide: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(profile, dict) or not isinstance(slide, dict):
            return {}
        slide_profiles = [dict(item) for item in profile.get("slide_profiles", []) if isinstance(item, dict)]
        if not slide_profiles:
            return {}
        slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
        target_index = cls._int_or_none(slide_metadata.get("reference_slide_index")) or cls._int_or_none(slide.get("slide_index"))
        if target_index is not None:
            for candidate in slide_profiles:
                if cls._int_or_none(candidate.get("slide_index")) == target_index:
                    return candidate
        return slide_profiles[0]

    @classmethod
    def _reference_family_contract_sections(
        cls,
        compiled_context: dict[str, Any] | None,
        *,
        slide: dict[str, Any] | None = None,
        for_visual_only: bool,
    ) -> list[str]:
        profile = cls._reference_family_profile(compiled_context)
        if not profile:
            return []
        family_name = cls._normalize_metadata_text(profile.get("family_name"), limit=96)
        format_family = cls._normalize_metadata_text(profile.get("format_family"), limit=24)
        sequence_kind = cls._normalize_metadata_text(profile.get("sequence_kind"), limit=64)
        lock_strength = cls._normalize_metadata_text(profile.get("layout_lock_strength"), limit=24)
        preferred_zone_roles = cls._normalize_metadata_list(profile.get("preferred_zone_roles"), limit=8)
        image_zone_roles = cls._normalize_metadata_list(profile.get("approved_image_zone_roles"), limit=4)
        module_patterns = cls._normalize_metadata_list(profile.get("module_patterns"), limit=6)
        density_target = cls._normalize_metadata_text(profile.get("density_target"), limit=32)
        balance_target = cls._normalize_metadata_text(profile.get("image_text_balance_target"), limit=48)
        spacing_rhythm = cls._normalize_metadata_text(profile.get("spacing_rhythm"), limit=180)
        composition_summary = cls._normalize_metadata_text(profile.get("composition_summary"), limit=180)
        visual_craft_summary = cls._normalize_metadata_text(profile.get("visual_craft_summary"), limit=180)
        subject_summary = cls._normalize_metadata_text(profile.get("subject_semantics_summary"), limit=180)
        sections: list[str] = []
        descriptor = " / ".join(part for part in [family_name, sequence_kind] if part)
        if descriptor:
            sections.append(
                f"Reference family contract: {descriptor}. Treat this as a first-class target, not optional inspiration."
            )
        if lock_strength:
            sections.append(
                f"Reference family layout lock: {lock_strength}. Stay inside the approved family system rather than inventing a fresh layout grammar."
            )
        if preferred_zone_roles:
            sections.append(f"Reference family zone grammar: {', '.join(preferred_zone_roles)}.")
        if image_zone_roles:
            sections.append(
                f"Approved image zones only: generated imagery should live inside these family roles only: {', '.join(image_zone_roles)}."
            )
        if module_patterns:
            sections.append(
                f"Reference family module grammar: {', '.join(module_patterns)}. Compose from these approved module types instead of ad-hoc blocks."
            )
        if density_target or balance_target:
            sections.append(
                f"Reference family density target: {density_target or 'balanced'}. Image/text balance target: {balance_target or 'editorial_balanced'}."
            )
        if spacing_rhythm:
            sections.append(f"Reference family spacing rhythm: {spacing_rhythm}.")
        if composition_summary:
            sections.append(f"Reference family composition target: {composition_summary}.")
        if visual_craft_summary:
            sections.append(f"Reference family craft target: {visual_craft_summary}.")
        if subject_summary and not for_visual_only:
            sections.append(f"Reference family subject target: {subject_summary}.")

        slide_profile = cls._reference_family_slide_profile(profile, slide)
        if slide_profile:
            slide_roles = cls._normalize_metadata_list(slide_profile.get("zone_roles"), limit=8)
            slide_image_roles = cls._normalize_metadata_list(slide_profile.get("approved_image_zone_roles"), limit=4)
            slide_patterns = cls._normalize_metadata_list(slide_profile.get("module_patterns"), limit=6)
            slide_headline_hint = cls._normalize_metadata_text(slide_profile.get("headline_hint"), limit=96)
            slide_story_role = cls._normalize_metadata_text(slide_profile.get("story_role"), limit=40)
            if slide_story_role:
                sections.append(f"Reference family slide role target: {slide_story_role}.")
            if slide_headline_hint and not for_visual_only:
                sections.append(f"Reference family slide headline pattern: {slide_headline_hint}.")
            if slide_roles:
                sections.append(f"Reference family slide zone roles: {', '.join(slide_roles)}.")
            if slide_image_roles:
                sections.append(f"Reference family slide image zones: {', '.join(slide_image_roles)}.")
            if slide_patterns:
                sections.append(f"Reference family slide module patterns: {', '.join(slide_patterns)}.")
        elif format_family:
            sections.append(
                f"Reference family format target: {format_family}. Match its native layout behavior rather than a generic social post fallback."
            )
        return sections

    @classmethod
    def _sequence_pack_slide_authority(
        cls,
        sequence_pack: dict[str, Any],
        slide: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(sequence_pack, dict) or not isinstance(slide, dict):
            return {}
        slides = [dict(item) for item in sequence_pack.get("slides", []) if isinstance(item, dict)]
        if not slides:
            return {}
        slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
        target_index = cls._int_or_none(slide_metadata.get("reference_slide_index")) or cls._int_or_none(slide.get("slide_index"))
        target_name = cls._normalize_metadata_text(
            slide_metadata.get("reference_template_name") or slide.get("template_name"),
            limit=96,
        ).casefold()
        if target_index is not None:
            for candidate in slides:
                if cls._int_or_none(candidate.get("slide_index")) == target_index:
                    return candidate
        if target_name:
            for candidate in slides:
                if cls._normalize_metadata_text(candidate.get("template_name"), limit=96).casefold() == target_name:
                    return candidate
        return slides[0]

    @classmethod
    def _sequence_pack_mapping_summary(
        cls,
        value: Any,
        *,
        scalar_keys: tuple[str, ...],
        list_keys: tuple[str, ...],
        limit: int = 6,
        text_limit: int = 200,
    ) -> str:
        mapping = value if isinstance(value, dict) else {}
        parts: list[str] = []
        seen: set[str] = set()
        for key in scalar_keys:
            text = cls._normalize_metadata_text(mapping.get(key), limit=80)
            if text:
                normalized = text.casefold()
                if normalized not in seen:
                    seen.add(normalized)
                    parts.append(text)
            if len(parts) >= limit:
                break
        if len(parts) < limit:
            for key in list_keys:
                for item in cls._normalize_metadata_list(mapping.get(key), limit=limit):
                    normalized = item.casefold()
                    if normalized in seen:
                        continue
                    seen.add(normalized)
                    parts.append(item)
                    if len(parts) >= limit:
                        break
                if len(parts) >= limit:
                    break
        return cls._normalize_metadata_text(", ".join(parts), limit=text_limit)

    @classmethod
    def _sequence_blueprint_alignment_sections(
        cls,
        compiled_context: dict[str, Any] | None,
        *,
        slide: dict[str, Any] | None = None,
        for_carousel: bool,
        for_visual_only: bool,
    ) -> list[str]:
        sequence_pack = cls._prompt_sequence_pack(compiled_context)
        if not sequence_pack:
            return []
        family_name = cls._normalize_metadata_text(sequence_pack.get("family_name"), limit=96)
        sequence_kind = cls._normalize_metadata_text(sequence_pack.get("sequence_kind"), limit=64)
        surface_policy = cls._normalize_metadata_text(sequence_pack.get("surface_policy"), limit=32).casefold()
        slide_count = cls._int_or_none(sequence_pack.get("slide_count")) or 0
        story_roles = cls._normalize_metadata_list(sequence_pack.get("story_roles"), limit=8)
        sequence_cues = cls._normalize_metadata_list(sequence_pack.get("sequence_cues"), limit=8)
        headline_hints = cls._normalize_metadata_list(sequence_pack.get("headline_hints"), limit=4)

        sections: list[str] = []
        authority_label = " / ".join(part for part in [family_name, sequence_kind] if part)
        if authority_label or slide_count:
            sections.append(
                f"Sequence blueprint authority: {authority_label or 'approved sample sequence'}"
                f"{f' ({slide_count} slides)' if slide_count else ''}. "
                "This output must feel sample-driven and brand-driven, not like a generic social template."
            )
        if story_roles:
            sections.append(
                f"Sequence narrative rhythm: {' -> '.join(story_roles)}. Preserve this editorial progression in hierarchy, pacing, and information density."
            )
        if sequence_cues:
            sections.append(
                f"Sequence structural cues from the approved sample: {', '.join(sequence_cues)}."
            )
        if headline_hints and not for_visual_only:
            sections.append(
                f"Approved sample headline intents: {', '.join(headline_hints)}. Keep the visual explanation aligned to this level of specificity."
            )
        if surface_policy == "style_reference_only":
            sections.append(
                (
                    "Sample-driven enforcement: use the uploaded sample intelligence as the governing contract for composition, spacing rhythm, negative space, image treatment, and editorial pacing. "
                    "Rebuild the artwork from scratch, but do not downgrade into a generic carousel, infographic, or static social post."
                )
            )

        slide_authority = cls._sequence_pack_slide_authority(sequence_pack, slide)
        if not slide_authority:
            return sections

        reference_index = cls._int_or_none(slide_authority.get("slide_index"))
        story_role = cls._normalize_metadata_text(slide_authority.get("story_role"), limit=48)
        headline_hint = cls._normalize_metadata_text(slide_authority.get("headline_hint"), limit=96)
        structural_cues = cls._normalize_metadata_list(slide_authority.get("structural_cues"), limit=4)
        sequence_summary = cls._normalize_metadata_text(slide_authority.get("sequence_summary"), limit=160)
        zone_map = cls._coerce_mapping(slide_authority.get("zone_map"))
        composition_logic = cls._coerce_mapping(slide_authority.get("composition_logic"))
        visual_craft = cls._coerce_mapping(slide_authority.get("visual_craft"))
        subject_semantics = cls._coerce_mapping(slide_authority.get("subject_semantics"))
        editorial_dna = cls._coerce_mapping(slide_authority.get("editorial_dna"))

        slide_descriptor = []
        if reference_index is not None:
            slide_descriptor.append(f"slide {reference_index}")
        if slide_count:
            slide_descriptor.append(f"of {slide_count}")
        if story_role:
            slide_descriptor.append(f"role {story_role}")
        if slide_descriptor:
            sections.append(
                f"Current sample slide authority: {' '.join(slide_descriptor)}."
            )
        if headline_hint:
            sections.append(
                f"Current sample slide headline intent: {headline_hint}."
            )
        if structural_cues:
            sections.append(
                f"Current sample slide structural cues: {', '.join(structural_cues)}."
            )
        if sequence_summary and not for_visual_only:
            sections.append(
                f"Current sample slide explanation summary: {sequence_summary}."
            )
        layout_type = cls._normalize_metadata_text(zone_map.get("layout_type"), limit=64)
        if layout_type:
            sections.append(
                f"Current sample slide layout type: {layout_type}. Keep the image region, text-safe spacing, and composition balance consistent with this reference logic."
            )
        composition_summary = cls._sequence_pack_mapping_summary(
            composition_logic,
            scalar_keys=("balance", "framing", "layering"),
            list_keys=("depth_cues", "focal_path"),
            limit=6,
            text_limit=180,
        )
        if composition_summary:
            sections.append(f"Current sample slide composition cues: {composition_summary}.")
        visual_craft_summary = cls._sequence_pack_mapping_summary(
            visual_craft,
            scalar_keys=("depth_style", "rendering_style", "lighting", "polish_level"),
            list_keys=("material_cues", "dimensionality_cues"),
            limit=6,
            text_limit=180,
        )
        if visual_craft_summary:
            sections.append(f"Current sample slide craft cues: {visual_craft_summary}.")
        subject_summary = cls._sequence_pack_mapping_summary(
            subject_semantics,
            scalar_keys=("scene_type", "human_presence", "environment", "abstraction_level"),
            list_keys=("primary_subjects", "domain_cues", "financial_objects"),
            limit=7,
            text_limit=200,
        )
        if subject_summary:
            sections.append(f"Current sample slide subject cues: {subject_summary}.")
        editorial_summary = cls._sequence_pack_mapping_summary(
            editorial_dna,
            scalar_keys=("storytelling_mode", "copy_density", "closing_style"),
            list_keys=("story_arc_roles", "headline_patterns", "supporting_patterns", "editorial_signals", "explanation_styles"),
            limit=7,
            text_limit=200,
        )
        if editorial_summary:
            sections.append(f"Current sample slide editorial cues: {editorial_summary}.")
        return sections

    @classmethod
    def _sample_visual_alignment_sections(
        cls,
        compiled_context: dict[str, Any] | None,
        *,
        for_carousel: bool,
    ) -> list[str]:
        context = dict(compiled_context or {})
        template_fit = cls._coerce_mapping(context.get("template_fit_brief"))
        brand_visual = cls._coerce_mapping(context.get("brand_visual_brief"))
        design_system = cls._coerce_mapping(brand_visual.get("design_system"))
        sequence_pack = cls._prompt_sequence_pack(compiled_context)
        layout_dna = cls._coerce_mapping(
            template_fit.get("template_layout_dna")
            or design_system.get("template_layout_dna")
            or design_system.get("layout_dna")
        )
        composition_logic = cls._coerce_mapping(
            template_fit.get("template_composition_logic")
            or design_system.get("template_composition_logic")
            or design_system.get("composition_logic")
        )
        visual_craft = cls._coerce_mapping(
            template_fit.get("template_visual_craft")
            or design_system.get("template_visual_craft")
            or design_system.get("visual_craft")
        )
        subject_semantics = cls._coerce_mapping(
            template_fit.get("template_subject_semantics")
            or design_system.get("template_subject_semantics")
            or design_system.get("subject_semantics")
        )
        editorial_dna = cls._coerce_mapping(
            template_fit.get("template_editorial_dna")
            or design_system.get("template_editorial_dna")
        )

        def _joined_terms(*values: Any, limit: int = 6, text_limit: int = 180) -> str:
            collected: list[str] = []
            seen: set[str] = set()
            for value in values:
                for item in cls._normalize_metadata_list(value, limit=limit):
                    key = item.casefold()
                    if key in seen:
                        continue
                    seen.add(key)
                    collected.append(item)
                    if len(collected) >= limit:
                        break
                if len(collected) >= limit:
                    break
            return cls._normalize_metadata_text(", ".join(collected), limit=text_limit)

        active_authority = cls._normalize_metadata_text(
            template_fit.get("template_name")
            or sequence_pack.get("family_name")
            or design_system.get("dominant_layout_family"),
            limit=96,
        )
        zone_roles = cls._normalize_metadata_list(
            template_fit.get("template_zone_roles")
            or design_system.get("preferred_zone_roles"),
            limit=6,
        )
        hierarchy_summary = cls._normalize_metadata_text(
            design_system.get("hierarchy_summary"),
            limit=180,
        )
        content_structure_summary = cls._normalize_metadata_text(
            design_system.get("content_structure_summary"),
            limit=180,
        )
        visual_craft_summary = cls._normalize_metadata_text(
            design_system.get("visual_craft_summary")
            or _joined_terms(
                visual_craft.get("depth_styles") or visual_craft.get("depth_style"),
                visual_craft.get("rendering_styles") or visual_craft.get("rendering_style"),
                visual_craft.get("lighting_modes") or visual_craft.get("lighting"),
                visual_craft.get("polish_levels") or visual_craft.get("polish_level"),
                visual_craft.get("material_cues"),
                visual_craft.get("dimensionality_cues"),
                limit=7,
            ),
            limit=200,
        )
        composition_summary = cls._normalize_metadata_text(
            design_system.get("composition_logic_summary")
            or _joined_terms(
                composition_logic.get("balances") or composition_logic.get("balance"),
                composition_logic.get("framings") or composition_logic.get("framing"),
                composition_logic.get("layerings") or composition_logic.get("layering"),
                composition_logic.get("depth_cues"),
                composition_logic.get("focal_path"),
            ),
            limit=200,
        )
        subject_summary = cls._normalize_metadata_text(
            design_system.get("subject_semantics_summary")
            or _joined_terms(
                subject_semantics.get("scene_types") or subject_semantics.get("scene_type"),
                subject_semantics.get("primary_subjects"),
                subject_semantics.get("financial_objects"),
                subject_semantics.get("domain_cues"),
                subject_semantics.get("abstraction_levels") or subject_semantics.get("abstraction_level"),
                subject_semantics.get("environment"),
                limit=7,
            ),
            limit=200,
        )
        editorial_summary = cls._normalize_metadata_text(
            design_system.get("editorial_story_arc_summary")
            or design_system.get("editorial_style_summary")
            or _joined_terms(
                editorial_dna.get("story_arc_roles"),
                editorial_dna.get("headline_patterns"),
                editorial_dna.get("supporting_patterns"),
                editorial_dna.get("explanation_styles"),
                editorial_dna.get("storytelling_mode"),
                editorial_dna.get("editorial_signals"),
                editorial_dna.get("closing_style"),
                limit=6,
            ),
            limit=200,
        )
        layout_type = cls._normalize_metadata_text(layout_dna.get("layout_type"), limit=64)
        canvas_ratio = cls._normalize_metadata_text(layout_dna.get("canvas_ratio"), limit=32)

        sections: list[str] = []
        sections.append(
            (
                "Anti-generic rule: do not reduce this slide to a basic hero-left/text-right finance post, a flat 2D vector explainer, a smiling office-worker poster, or an arrow-and-bar-chart composition unless the approved sample explicitly uses that language."
                if for_carousel
                else "Anti-generic rule: do not default to flat 2D vector finance explainers, smiling office workers, isolated coin or plant metaphors, dashboard-tile collages, or rising-arrow hero scenes unless the approved sample explicitly uses that language."
            )
        )
        if active_authority:
            sections.append(
                f"Active sample/template authority: {active_authority}. Match its editorial hierarchy, spacing rhythm, and image-to-text balance instead of inventing a new generic finance layout."
            )
        if layout_type or canvas_ratio:
            descriptor = " ".join(part for part in [layout_type, canvas_ratio] if part).strip()
            sections.append(
                f"Sample layout DNA: {descriptor}. Preserve this composition archetype rather than reverting to a flat generic explainer layout."
            )
        if zone_roles:
            sections.append(
                f"Preferred zone-role rhythm from the selected sample: {', '.join(zone_roles)}. Keep these role neighborhoods distinct and do not collapse the slide into one hero-plus-text poster block."
            )
        if hierarchy_summary:
            sections.append(
                f"Sample hierarchy cues: {hierarchy_summary}. Keep the same focal emphasis and whitespace discipline."
            )
        if content_structure_summary:
            sections.append(
                f"Sample content-density cues: {content_structure_summary}. Preserve the same editorial pacing instead of overfilling the canvas."
            )
        if visual_craft_summary:
            sections.append(
                f"Sample visual-craft cues: {visual_craft_summary}. Favor dimensional, premium, editorially polished imagery with controlled depth and material detail when the sample allows it; do not fall back to flat low-detail vector treatment unless the sample is clearly minimal by design."
            )
        if composition_summary:
            sections.append(
                f"Sample composition cues: {composition_summary}. Preserve framing, layering, and negative-space behavior instead of centering one generic finance icon or illustration."
            )
        if subject_summary:
            sections.append(
                f"Sample subject cues: {subject_summary}. Choose topic-specific scenes and objects from this vocabulary instead of generic office workers, random coins, abstract arrows, or dashboard stickers."
            )
        if editorial_summary:
            sections.append(
                f"Sample editorial rhythm: {editorial_summary}. Avoid repeating the same slide composition or generic social-poster formula."
            )
        return [section for section in sections if section]

    @classmethod
    def _should_ignore_scene_graph_for_final_render(
        cls,
        *,
        generation_path: str,
        fresh_replan_attempted: bool,
        validation_report: SceneGraphValidationReport,
        scene_graph: GenerationSceneGraph,
        compiled_context: dict[str, Any] | None = None,
    ) -> bool:
        return (
            generation_path == "image_led_social"
            and fresh_replan_attempted
            and cls._should_request_fresh_replan(validation_report)
            and not cls._scene_graph_has_authoritative_geometry(scene_graph)
            and not cls._compiled_context_has_authoritative_layout(compiled_context)
        )

    @staticmethod
    def _final_render_ignore_note(validation_report: SceneGraphValidationReport) -> str:
        issues = [str(issue.rule_id or "").strip() for issue in validation_report.issues if str(issue.rule_id or "").strip()]
        if not issues:
            return (
                "The prior weak scene graph lacked enough usable geometry. Rebuild the composition around the extracted sample layout skeleton, "
                "brand system, and scene-safe geometry contract instead of improvising a new composition."
            )
        return (
            "The prior weak scene graph lacked enough usable geometry. Rebuild the composition around the extracted sample layout skeleton, "
            "brand system, and scene-safe geometry contract instead of improvising a new composition. "
            f"Do not repeat these failed planning traits: {', '.join(issues)}."
        )

    @staticmethod
    def _coerce_mapping(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if value is None:
            return {}
        if isinstance(value, (list, tuple, set)):
            merged: dict[str, Any] = {}
            text_items: list[str] = []
            for item in value:
                if isinstance(item, dict):
                    merged.update(item)
                else:
                    text = str(item).strip()
                    if text:
                        text_items.append(text)
            if merged:
                if text_items:
                    merged.setdefault("notes", "; ".join(text_items[:8]))
                return merged
            if text_items:
                return {"notes": "; ".join(text_items[:8])}
            return {}
        text = str(value).strip()
        return {"notes": text} if text else {}

    @staticmethod
    def _coerce_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, set):
            return list(value)
        return [value]

    @staticmethod
    def _normalize_trace_payload(payload: Any) -> Any:
        if isinstance(payload, str):
            return AIOrchestratorService._repair_common_mojibake(payload)
        if isinstance(payload, dict):
            return {
                key: AIOrchestratorService._normalize_trace_payload(value)
                for key, value in payload.items()
            }
        if isinstance(payload, list):
            return [AIOrchestratorService._normalize_trace_payload(value) for value in payload]
        if isinstance(payload, tuple):
            return [AIOrchestratorService._normalize_trace_payload(value) for value in payload]
        return payload

    @staticmethod
    def _trace_payload(trace_id: str | None, tracer: GenerationTraceService, filename: str, payload: Any) -> None:
        tracer.write_payload(
            trace_id,
            filename,
            AIOrchestratorService._normalize_trace_payload(payload),
        )

    @staticmethod
    def _trace_event(trace_id: str | None, tracer: GenerationTraceService, event: str, payload: Any | None = None) -> None:
        tracer.append_event(trace_id, event, payload)

    @classmethod
    def _compiled_font_families(cls, compiled_context: dict[str, Any]) -> list[str]:
        families: list[str] = []
        for item in (compiled_context.get("brand_visual_brief", {}) or {}).get("font_families", []) or []:
            normalized = cls._normalize_metadata_text(item, limit=64)
            if normalized and normalized not in families:
                families.append(normalized)
        return families

    @classmethod
    def _extract_font_sizes_from_brand_context(cls, brand_context: dict[str, Any]) -> dict[str, int]:
        """Extract font sizes from analyzed reference samples (typography_dna)"""
        # Default font sizes (fallback if not extracted)
        defaults = {
            "headline": 58,
            "subheading": 36,
            "body": 24,
            "caption": 16,
            "footer": 8
        }

        # Try to extract from reference creatives' typography_dna
        visual_identity = brand_context.get("visual_identity", {})
        reference_creatives = visual_identity.get("reference_creatives", [])

        for reference in reference_creatives:
            style_chars = reference.get("style_characteristics", {})
            typography_dna = style_chars.get("typography_dna", {})
            font_size_palette = typography_dna.get("font_size_palette", {})

            if font_size_palette:
                # Found font size palette from vision analysis!
                return {
                    "headline": int(font_size_palette.get("headline_pt", defaults["headline"])),
                    "subheading": int(font_size_palette.get("subheading_pt", defaults["subheading"])),
                    "body": int(font_size_palette.get("body_pt", defaults["body"])),
                    "caption": int(font_size_palette.get("caption_pt", defaults["caption"])),
                    "footer": int(font_size_palette.get("footer_pt", defaults["footer"]))
                }

        # Fallback to defaults if not found in references
        return defaults

    @classmethod
    def _extract_layout_dna_from_brand_context(cls, brand_context: dict[str, Any], format_hint: str) -> dict[str, Any] | None:
        """Extract layout DNA from reference creatives"""
        visual_identity = brand_context.get("visual_identity", {})
        reference_creatives = visual_identity.get("reference_creatives", [])

        for reference in reference_creatives:
            layout_structure = reference.get("layout_structure", {})
            dna = layout_structure.get("layout_dna")
            if dna and dna.get("zones"):
                return dna

        return None

    @classmethod
    def _extract_layout_dna_from_compiled_context(cls, compiled_context: dict[str, Any], format_hint: str) -> dict[str, Any] | None:
        brand_visual_brief = compiled_context.get("brand_visual_brief", {}) if isinstance(compiled_context, dict) else {}
        template_fit_brief = compiled_context.get("template_fit_brief", {}) if isinstance(compiled_context, dict) else {}
        candidates = [
            (template_fit_brief.get("template_layout_dna") if isinstance(template_fit_brief, dict) else {}),
            (brand_visual_brief.get("template_layout_dna") if isinstance(brand_visual_brief, dict) else {}),
            (
                ((brand_visual_brief.get("design_system") or {}).get("template_layout_dna"))
                if isinstance((brand_visual_brief.get("design_system") if isinstance(brand_visual_brief, dict) else {}), dict)
                else {}
            ),
        ]
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("zones"):
                return candidate
        return None

    @classmethod
    def _build_profile_from_layout_dna(cls, layout_dna: dict[str, Any], layout_type: str, format_name: str) -> dict[str, Any]:
        """Build layout profile from extracted layout DNA"""
        raw_zones = layout_dna.get("zones", {})
        spacing = layout_dna.get("spacing", {})
        zones: dict[str, dict[str, Any]] = {}

        if isinstance(raw_zones, dict):
            for role_name, zone in raw_zones.items():
                if not isinstance(zone, dict):
                    continue
                normalized = zone.get("normalized") if isinstance(zone.get("normalized"), dict) else {}
                zone_copy = dict(zone)
                zone_copy.setdefault("role", str(role_name))
                if normalized:
                    zone_copy["normalized"] = normalized
                elif all(zone.get(key) is not None for key in ("x", "y", "w", "h")):
                    zone_copy["normalized"] = {
                        "x": zone.get("x"),
                        "y": zone.get("y"),
                        "w": zone.get("w"),
                        "h": zone.get("h"),
                    }
                zones[str(role_name)] = zone_copy
        elif isinstance(raw_zones, list):
            for zone in raw_zones:
                if not isinstance(zone, dict):
                    continue
                role_name = str(zone.get("role") or zone.get("zone_role") or "").strip()
                if not role_name:
                    continue
                normalized = zone.get("normalized") if isinstance(zone.get("normalized"), dict) else {}
                zone_copy = dict(zone)
                zone_copy.setdefault("role", role_name)
                if normalized:
                    zone_copy["normalized"] = normalized
                elif all(zone.get(key) is not None for key in ("x", "y", "w", "h")):
                    zone_copy["normalized"] = {
                        "x": zone.get("x"),
                        "y": zone.get("y"),
                        "w": zone.get("w"),
                        "h": zone.get("h"),
                    }
                elif all(zone.get(key) is not None for key in ("x", "y", "width", "height")):
                    zone_copy["normalized"] = {
                        "x": zone.get("x"),
                        "y": zone.get("y"),
                        "w": zone.get("width"),
                        "h": zone.get("height"),
                    }
                zones[role_name] = zone_copy

        profile = {
            "layout_type": layout_type,
            "layout_archetype": cls._sanitize_scene_element_name(
                str(layout_dna.get("layout_type") or "extracted_from_sample")
            ) or "extracted_from_sample",
        }

        # Map zone roles to profile keys
        role_mapping = {
            "headline": "headline",
            "supporting_line": "supporting_line",
            "body": "supporting_line",
            "proof_points": "proof_points",
            "stat_highlights": "proof_points",
            "image": "hero_image",
            "hero_visual": "hero_image",
            "hero_image": "hero_image",
            "primary_visual": "hero_image",
            "logo": "logo",
            "cta": "cta",
        }

        for zone_role, profile_key in role_mapping.items():
            zone = zones.get(zone_role)
            if zone:
                normalized = zone.get("normalized", {})
                profile[profile_key] = cls._normalized_box(
                    normalized.get("x", 0),
                    normalized.get("y", 0),
                    normalized.get("w", 1),
                    normalized.get("h", 0.1)
                )

        content_boxes: list[dict[str, float]] = []
        for role_name, zone in zones.items():
            if not isinstance(zone, dict):
                continue
            normalized = zone.get("normalized", {}) if isinstance(zone.get("normalized"), dict) else {}
            if role_name in {"image", "logo"}:
                continue
            if all(isinstance(normalized.get(key), (int, float)) for key in ("x", "y", "w", "h")):
                content_boxes.append(normalized)
        if content_boxes:
            min_x = min(float(box.get("x") or 0.0) for box in content_boxes)
            min_y = min(float(box.get("y") or 0.0) for box in content_boxes)
            max_x = max(float(box.get("x") or 0.0) + float(box.get("w") or 0.0) for box in content_boxes)
            max_y = max(float(box.get("y") or 0.0) + float(box.get("h") or 0.0) for box in content_boxes)
            pad_x = float(spacing.get("x_padding") or spacing.get("padding_x") or 0.03)
            pad_y = float(spacing.get("y_padding") or spacing.get("padding_y") or 0.03)
            profile["overlay_panel"] = cls._normalized_box(
                max(min_x - pad_x, 0.0),
                max(min_y - pad_y, 0.0),
                min(max_x - min_x + pad_x * 2, 0.96),
                min(max_y - min_y + pad_y * 2, 0.96),
            )

        # Add proof_points fallback if body zone exists (typically below supporting line)
        if "proof_points" not in profile and "body" in zones:
            body_zone = zones["body"]
            normalized = body_zone.get("normalized", {})
            y_start = normalized.get("y", 0) + normalized.get("h", 0) + 0.05
            profile["proof_points"] = cls._normalized_box(0.08, y_start, 0.84, 0.3)

        overlay_panel = profile.get("overlay_panel") if isinstance(profile.get("overlay_panel"), dict) else {}
        if overlay_panel:
            panel_x = float(overlay_panel.get("x") or 0.05)
            panel_y = float(overlay_panel.get("y") or 0.08)
            panel_w = float(overlay_panel.get("width") or 0.84)
            panel_h = float(overlay_panel.get("height") or 0.76)
        else:
            panel_x, panel_y, panel_w, panel_h = 0.05, 0.08, 0.84, 0.76

        if "headline" not in profile:
            profile["headline"] = cls._normalized_box(panel_x, panel_y, min(panel_w, 0.62), 0.12)
        headline_box = profile.get("headline") if isinstance(profile.get("headline"), dict) else cls._normalized_box(panel_x, panel_y, min(panel_w, 0.62), 0.12)
        headline_y_end = float(headline_box.get("y") or panel_y) + float(headline_box.get("height") or 0.12)

        if "supporting_line" not in profile:
            profile["supporting_line"] = cls._normalized_box(
                panel_x,
                min(headline_y_end + 0.04, 0.86),
                min(panel_w, 0.72),
                0.1,
            )
        supporting_box = profile.get("supporting_line") if isinstance(profile.get("supporting_line"), dict) else {}
        supporting_y_end = float(supporting_box.get("y") or headline_y_end) + float(supporting_box.get("height") or 0.1)

        if "proof_points" not in profile:
            profile["proof_points"] = cls._normalized_box(
                panel_x,
                min(supporting_y_end + 0.04, 0.88),
                min(panel_w, 0.78),
                min(max(panel_h - (supporting_y_end - panel_y) - 0.18, 0.12), 0.24),
            )
        if "cta" not in profile:
            proof_box = profile.get("proof_points") if isinstance(profile.get("proof_points"), dict) else {}
            proof_y_end = float(proof_box.get("y") or supporting_y_end) + float(proof_box.get("height") or 0.16)
            profile["cta"] = cls._normalized_box(
                panel_x,
                min(proof_y_end + 0.04, 0.9),
                min(panel_w * 0.45, 0.34),
                0.08,
            )
        if "logo" not in profile:
            profile["logo"] = cls._normalized_box(min(panel_x + panel_w - 0.18, 0.78), max(panel_y - 0.04, 0.04), 0.16, 0.06)
        if "hero_image" not in profile:
            profile["hero_image"] = cls._normalized_box(min(panel_x + panel_w + 0.03, 0.56), 0.12, 0.32, 0.34)
        if "overlay_panel" not in profile:
            profile["overlay_panel"] = cls._normalized_box(panel_x, panel_y, panel_w, panel_h)

        return profile

    @staticmethod
    def _default_font_role_for_role(role: str) -> str:
        normalized = str(role or "").strip().lower()
        if normalized == "headline":
            return "heading_sans"
        if normalized == "cta":
            return "cta_sans"
        if normalized in {"footer", "legal"}:
            return "caption_sans"
        return "body_sans"

    @classmethod
    def _normalize_text_style_for_brand(
        cls,
        style: dict[str, Any],
        *,
        role: str,
        allowed_font_families: list[str],
        validation_hints: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(style or {})
        requested_family = str(
            normalized.get("font_family")
            or normalized.get("family")
            or normalized.get("fontFamily")
            or ""
        ).strip()
        normalized["font_role"] = str(normalized.get("font_role") or cls._default_font_role_for_role(role)).strip()
        if not requested_family:
            normalized.pop("font_family", None)
            return normalized
        validation_hints.setdefault("font_family_requested", requested_family)
        matched = next(
            (family for family in allowed_font_families if family.casefold() == requested_family.casefold()),
            None,
        )
        if matched:
            normalized["font_family"] = matched
            validation_hints["font_family_resolved"] = matched
            return normalized
        if allowed_font_families:
            normalized["font_family"] = allowed_font_families[0]
            validation_hints["font_family_resolved"] = allowed_font_families[0]
            validation_hints["font_family_normalized_from"] = requested_family
            return normalized
        normalized.pop("font_family", None)
        validation_hints["font_family_strategy"] = "renderer_fallback"
        return normalized

    @staticmethod
    def _major_asset_strategy_flags(asset_strategy: dict[str, Any]) -> dict[str, bool]:
        strategy = asset_strategy or {}
        return {
            "generated_image": bool(strategy.get("use_generated_image")),
            "template_background": bool(strategy.get("use_template_background")),
            "reference_assets": bool(strategy.get("use_brand_reference_assets")),
            "icon_sequence": bool(strategy.get("icon_sequence")),
        }

    @staticmethod
    def _normalized_dominant_visual_system(asset_strategy: dict[str, Any]) -> str:
        value = str((asset_strategy or {}).get("dominant_visual_system") or "").strip().lower()
        aliases = {
            "image_led": "generated_image",
            "generated_image": "generated_image",
            "hero_image": "generated_image",
            "template_led": "template_background",
            "exact_template": "template_background",
            "adapted_template": "template_background",
            "template_background": "template_background",
            "asset_led": "reference_assets",
            "reference_led": "reference_assets",
            "reference_assets": "reference_assets",
            "icon_led": "icon_sequence",
            "icon_sequence": "icon_sequence",
            "type_led": "type_led",
        }
        return aliases.get(value, value or "")

    @staticmethod
    def _normalized_supporting_visual_system(asset_strategy: dict[str, Any]) -> str:
        value = str(
            (asset_strategy or {}).get("supporting_visual_system")
            or (asset_strategy or {}).get("type_led_supporting_system")
            or ""
        ).strip().lower()
        aliases = {
            "iconography": "icon_sequence",
            "icons": "icon_sequence",
            "icon_led": "icon_sequence",
            "icon_sequence": "icon_sequence",
            "reference_assets": "reference_assets",
            "reference_led": "reference_assets",
            "asset_led": "reference_assets",
        }
        return aliases.get(value, value or "")

    @staticmethod
    def _visual_explanation_plan(
        request: AIOrchestrationRequest,
        text_payload: Any,
        creative_decision: CreativeDecisionPayload | None = None,
        reference_images: list[dict[str, Any]] | None = None,
        message_strategy: MessageStrategyPayload | None = None,
    ) -> dict[str, str]:
        metadata = getattr(text_payload, "metadata", None)
        metadata = metadata if isinstance(metadata, dict) else {}
        strategy_payload = message_strategy.model_dump(mode="json") if isinstance(message_strategy, MessageStrategyPayload) else {}
        asset_strategy = (creative_decision.asset_strategy if isinstance(creative_decision, CreativeDecisionPayload) else {}) or {}
        format_name = str((getattr(request, "studio_panel", {}) or {}).get("format") or "static").strip().lower()
        text = " ".join(
            AIOrchestratorService._coerce_text_value(part)
            for part in [
                getattr(request, "prompt", ""),
                getattr(text_payload, "headline", ""),
                getattr(text_payload, "body", ""),
                getattr(text_payload, "cta", ""),
                metadata.get("supporting_line"),
                metadata.get("visual_direction"),
                metadata.get("image_prompt"),
                metadata.get("proof_points"),
                metadata.get("stat_highlights"),
                strategy_payload.get("primary_campaign_theme"),
                strategy_payload.get("core_audience_message"),
                strategy_payload.get("important_keywords"),
            ]
            if AIOrchestratorService._coerce_text_value(part)
        ).casefold()
        proof_points = AIOrchestratorService._normalize_metadata_list(metadata.get("proof_points"), limit=6)
        supporting_visual_system = AIOrchestratorService._normalized_supporting_visual_system(asset_strategy)
        has_reference_images = bool(reference_images)
        explicit_data_visual_request = AIOrchestratorService._has_explicit_data_visual_request(
            getattr(request, "prompt", ""),
            text_payload=text_payload,
        )

        beginner_terms = (
            "first-time",
            "first time",
            "beginner",
            "beginners",
            "new investor",
            "new investors",
            "approachable",
            "easy start",
            "getting started",
            "start investing",
            "guided",
            "onboarding",
            "entry point",
            "entry-level",
            "simple access",
            "market is approachable",
            "free market is approachable",
        )
        process_terms = (
            "tips",
            "checklist",
            "steps",
            "step-by-step",
            "how to",
            "strategy",
            "strategies",
            "playbook",
            "roadmap",
            "journey",
            "process",
            "guide",
        )
        comparison_terms = (
            "compare",
            "comparison",
            "versus",
            " vs ",
            "before and after",
            "before/after",
            "confusion to clarity",
            "risk return",
            "risk-return",
            "risk and return",
            "old vs new",
            "trade-off",
            "tradeoff",
        )
        data_terms = (
            "market trend",
            "market trends",
            "trend",
            "trends",
            "graph",
            "chart",
            "data",
            "metric",
            "metrics",
            "percentage",
            "%",
        )

        def has_term(term: str) -> bool:
            normalized = term.strip().casefold()
            if not normalized:
                return False
            if normalized == "%":
                return "%" in text
            return bool(re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", text))

        def has_any(terms: tuple[str, ...]) -> bool:
            return any(has_term(term) for term in terms)

        if has_any(beginner_terms):
            return {
                "mode": "beginner_path",
                "need": "high",
                "density": "medium",
                "rationale": "Prompt asks for first-time, approachable, or guided-entry understanding.",
            }
        if has_any(comparison_terms):
            return {
                "mode": "comparison",
                "need": "medium",
                "density": "low" if format_name == "static" else "medium",
                "rationale": "Message benefits from a clear contrast or before-after transformation.",
            }
        if explicit_data_visual_request or has_any(data_terms):
            return {
                "mode": "data_cue",
                "need": "high" if format_name == "infographic" else "medium",
                "density": "medium" if format_name != "infographic" else "high",
                "rationale": "Message explicitly asks for chart-worthy information, numeric visualization, or diagrammatic evidence.",
            }
        if has_any(process_terms):
            return {
                "mode": "process_steps",
                "need": "high",
                "density": "medium",
                "rationale": "Message is instructional and should read visually as a simple sequence.",
            }
        if format_name in {"carousel", "infographic"} or supporting_visual_system == "icon_sequence":
            return {
                "mode": "icon_support",
                "need": "medium",
                "density": "low" if format_name == "static" else "medium",
                "rationale": "Format or proof points can benefit from restrained supporting symbols without a full diagram.",
            }
        if has_reference_images:
            return {
                "mode": "minimal_brand_scene",
                "need": "low",
                "density": "low",
                "rationale": "Reference assets can provide style while the message does not require extra explanation.",
            }
        return {
            "mode": "minimal_brand_scene",
            "need": "low",
            "density": "low",
            "rationale": "Message can be served by a clean brand scene without forced explanatory devices.",
        }

    @staticmethod
    def _has_explicit_data_visual_request(
        prompt: str,
        *,
        text_payload: StructuredTextPayload | None = None,
    ) -> bool:
        metadata = (text_payload.metadata or {}) if isinstance(text_payload, StructuredTextPayload) else {}
        combined = " ".join(
            part
            for part in [
                AIOrchestratorService._coerce_text_value(prompt),
                AIOrchestratorService._coerce_text_value(getattr(text_payload, "headline", "") if text_payload else ""),
                AIOrchestratorService._coerce_text_value(getattr(text_payload, "body", "") if text_payload else ""),
                AIOrchestratorService._coerce_text_value(metadata.get("supporting_line")),
                AIOrchestratorService._coerce_text_value(metadata.get("proof_points")),
                AIOrchestratorService._coerce_text_value(metadata.get("stat_highlights")),
            ]
            if AIOrchestratorService._coerce_text_value(part)
        ).casefold()
        if not combined:
            return False
        explicit_visual_terms = (
            "bar chart",
            "bar graph",
            "line chart",
            "line graph",
            "pie chart",
            "donut chart",
            "area chart",
            "graph",
            "chart",
            "timeline",
            "diagram",
            "visualization",
            "data viz",
            "infographic",
            "table",
            "matrix",
            "checklist",
            "step-by-step",
            "steps",
            "process",
            "flow",
        )
        if any(term in combined for term in explicit_visual_terms):
            return True
        if re.search(r"\b\d{4}\b", combined) and re.search(r"\b(chart|graph|trend|timeline|growth|decline|increase|decrease)\b", combined):
            return True
        if "%" in combined and re.search(r"\b(chart|graph|compare|comparison|trend|data|metric)\b", combined):
            return True
        return False

    @staticmethod
    def _visual_explanation_guidance(visual_plan: dict[str, Any] | None) -> str:
        plan = visual_plan if isinstance(visual_plan, dict) else {}
        mode = str(plan.get("mode") or "minimal_brand_scene").strip().lower()
        need = str(plan.get("need") or "low").strip().lower()
        density = str(plan.get("density") or "low").strip().lower()
        rationale = AIOrchestratorService._normalize_metadata_text(plan.get("rationale"), limit=180)
        guidance_by_mode = {
            "beginner_path": (
                "Use a beginner-friendly path, guided entry, simplified market steps, bond ladder, or confusion-to-clarity progression. "
                "Do not rely on a person holding a coin as the only visual idea."
            ),
            "process_steps": (
                "Use a simple sequence, pathway, checklist flow, or step markers that make the recommended actions understandable at a glance."
            ),
            "comparison": (
                "Use clear contrast zones, side-by-side comparison, or a visual transformation tied to the actual topic. "
                "Do not default to rising bar charts, stock arrows, generic finance dashboards, or a chart/graph-style hero image unless the copy explicitly contains quantitative chart data."
            ),
            "data_cue": (
                "Prefer tables, labeled figures, comparison blocks, ladders, or process markers before defaulting to charts. "
                "Use chart or graph motifs only when the copy includes explicit numeric series, time-based trends, or metric comparisons that truly need charting. "
                "Otherwise do not let a chart, bars, or arrow become the main hero image."
            ),
            "icon_support": (
                "Use a few premium integrated icons, diagram cues, or proof-point symbols only where they clarify the message; keep them secondary. "
                "Do not fall back to stock upward arrows, rising bars, generic finance app tiles, repeated chart stickers, or a graph-like hero image."
            ),
            "minimal_brand_scene": (
                "Keep visual explanation low. Do not force charts, dashboards, random icons, diagrams, or faux UI when the message works as a clean brand scene."
            ),
        }
        mode_guidance = guidance_by_mode.get(mode, guidance_by_mode["minimal_brand_scene"])
        return (
            f"Visual explanation plan: mode={mode}, need={need}, density={density}. "
            f"Rationale: {rationale}. {mode_guidance} "
            "Reference/template fit: if the reference is image-led, place the explanatory visual in the same image-emphasis region; "
            "if it is type-led or minimal, keep explanation subtle and lower density. "
            "Never let reference creatives force generic people imagery when this mode calls for an explainer."
        )

    def normalize_creative_decision_payload(
        self,
        raw: Any,
        fallback: dict[str, Any],
        *,
        request: AIOrchestrationRequest,
        compiled_context: dict[str, Any],
    ) -> CreativeDecisionPayload:
        payload = dict(fallback or {})
        if isinstance(raw, dict):
            payload.update(raw)
        payload["layout_mode"] = str(
            payload.get("layout_mode")
            or payload.get("mode")
            or fallback.get("layout_mode")
            or "synthesized_layout"
        )
        if payload["layout_mode"] not in {"exact_template", "adapted_template", "synthesized_layout"}:
            payload["layout_mode"] = "synthesized_layout"
        payload["selected_template_id"] = self._resolve_template_candidate_identifier(
            str(payload.get("selected_template_id") or payload.get("template_id") or "").strip() or None,
            template_name=(
                str(payload.get("template_name") or "").strip()
                or str((payload.get("planning_hints") or {}).get("template_name") or "").strip()
                or str((fallback.get("planning_hints") or {}).get("template_name") or "").strip()
                or None
            ),
            template_candidates=[
                item
                for item in self._coerce_list(payload.get("template_candidates") or request.template_candidates or [])
                if isinstance(item, dict)
            ],
        )
        try:
            payload["confidence"] = max(0.0, min(float(payload.get("confidence", 0.0)), 1.0))
        except (TypeError, ValueError):
            payload["confidence"] = float(fallback.get("confidence") or 0.0)
        payload["reasoning"] = [
            str(item).strip()
            for item in self._coerce_list(payload.get("reasoning") or payload.get("rationale") or fallback.get("reasoning") or [])
            if str(item).strip()
        ]
        payload["adaptations"] = self._coerce_mapping(payload.get("adaptations") or payload.get("adaptation_plan"))
        asset_strategy = self._coerce_mapping(payload.get("asset_strategy") or fallback.get("asset_strategy"))
        for key in ("use_generated_image", "use_template_background", "use_brand_reference_assets", "logo_injection_required"):
            if key in asset_strategy:
                asset_strategy[key] = bool(asset_strategy.get(key))
        if asset_strategy.get("logo"):
            asset_strategy.setdefault("logo_injection_required", True)
        if asset_strategy.get("template_surface_policy") == "style_reference_only":
            asset_strategy["use_template_background"] = False
        major_flags = self._major_asset_strategy_flags(asset_strategy)
        dominant = self._normalized_dominant_visual_system(asset_strategy)
        supporting = self._normalized_supporting_visual_system(asset_strategy)
        if not dominant:
            dominant = next((name for name, enabled in major_flags.items() if enabled), "generated_image")
        asset_strategy["dominant_visual_system"] = dominant
        if supporting:
            asset_strategy["supporting_visual_system"] = supporting
        if dominant == "generated_image":
            asset_strategy["use_generated_image"] = True
            if payload["layout_mode"] == "synthesized_layout" or asset_strategy.get("template_surface_policy") == "style_reference_only":
                asset_strategy["use_template_background"] = False
            if supporting != "reference_assets":
                asset_strategy["use_brand_reference_assets"] = False
            if supporting == "icon_sequence":
                asset_strategy["icon_sequence"] = True
                asset_strategy["use_brand_reference_assets"] = True
        elif dominant == "template_background":
            asset_strategy["use_template_background"] = payload["layout_mode"] in {"exact_template", "adapted_template"}
            asset_strategy["use_generated_image"] = False
            if asset_strategy.get("template_surface_policy") == "style_reference_only":
                asset_strategy["use_template_background"] = False
        elif dominant == "reference_assets":
            asset_strategy["use_brand_reference_assets"] = True
            asset_strategy["use_template_background"] = False
            asset_strategy["use_generated_image"] = False
        elif dominant == "icon_sequence":
            asset_strategy["icon_sequence"] = True
        if supporting == "icon_sequence":
            asset_strategy["icon_sequence"] = True
            if dominant in {"generated_image", "type_led"}:
                asset_strategy["use_brand_reference_assets"] = True
        payload["asset_strategy"] = asset_strategy
        payload["template_candidates"] = [
            item
            for item in self._coerce_list(payload.get("template_candidates") or request.template_candidates or [])
            if isinstance(item, dict)
        ]
        payload["planning_hints"] = {
            **self._coerce_mapping(fallback.get("planning_hints")),
            **self._coerce_mapping(payload.get("planning_hints")),
            "backend_compiled_template_fit": compiled_context.get("template_fit_brief", {}),
        }
        normalized = CreativeDecisionPayload.model_validate(payload)
        sequence_pack = self._template_sequence_pack(request, creative_decision=normalized)
        if isinstance(sequence_pack, dict):
            sequence_surface_policy = str(sequence_pack.get("surface_policy") or "").strip().lower()
            if sequence_surface_policy == "style_reference_only":
                normalized_payload = normalized.model_dump(mode="json")
                normalized_asset_strategy = self._coerce_mapping(normalized_payload.get("asset_strategy"))
                normalized_asset_strategy["template_surface_policy"] = "style_reference_only"
                normalized_asset_strategy["use_template_background"] = False
                normalized_asset_strategy["use_brand_reference_assets"] = True
                dominant_visual_system = self._normalized_dominant_visual_system(normalized_asset_strategy)
                if dominant_visual_system in {"", "template_background"}:
                    normalized_asset_strategy["dominant_visual_system"] = "generated_image"
                    normalized_asset_strategy["use_generated_image"] = True
                if normalized_payload.get("layout_mode") == "exact_template":
                    normalized_payload["layout_mode"] = "adapted_template"
                normalized_payload["asset_strategy"] = normalized_asset_strategy
                normalized_payload["reasoning"] = [
                    *[
                        str(item).strip()
                        for item in self._coerce_list(normalized_payload.get("reasoning") or [])
                        if str(item).strip()
                    ],
                    "Use the ordered reference sequence as story and slide guidance only; do not reuse the sample surface as the literal background.",
                ]
                normalized = CreativeDecisionPayload.model_validate(normalized_payload)
        if self._should_force_sequence_pack(request, creative_decision=normalized):
            normalized_payload = normalized.model_dump(mode="json")
            if normalized.layout_mode == "synthesized_layout":
                normalized_payload["layout_mode"] = "adapted_template"
            normalized_asset_strategy = self._coerce_mapping(normalized_payload.get("asset_strategy"))
            normalized_asset_strategy["use_template_background"] = True
            normalized_asset_strategy["use_brand_reference_assets"] = True
            normalized_asset_strategy["use_generated_image"] = False
            normalized_asset_strategy["template_surface_policy"] = "sequence_pack_locked"
            normalized_asset_strategy.setdefault("dominant_visual_system", "template_background")
            normalized_payload["asset_strategy"] = normalized_asset_strategy
            normalized_payload["reasoning"] = [
                *[
                    str(item).strip()
                    for item in self._coerce_list(normalized_payload.get("reasoning") or [])
                    if str(item).strip()
                ],
                "Forced to ordered reference sequence pack because a locked multi-slide template pack is available for this carousel.",
            ]
            normalized = CreativeDecisionPayload.model_validate(normalized_payload)
        return normalized

    def normalize_message_strategy_payload(
        self,
        raw: Any,
        fallback: dict[str, Any],
    ) -> MessageStrategyPayload:
        payload = dict(fallback or {})
        if isinstance(raw, dict):
            payload.update(raw)
        aliases = {
            "primary_campaign_theme": ["primary_campaign_theme", "Primary Campaign Theme"],
            "core_audience_message": ["core_audience_message", "Core Audience Message"],
            "headline_direction": ["headline_direction", "Headline Direction"],
            "supporting_copy_direction": ["supporting_copy_direction", "Supporting Copy Direction"],
            "cta_intent": ["cta_intent", "CTA Intent"],
            "key_value_proposition": ["key_value_proposition", "Key Value Proposition"],
            "important_keywords": ["important_keywords", "Important Keywords/Phrases", "keywords"],
            "emotional_messaging_direction": ["emotional_messaging_direction", "Emotional Messaging Direction"],
            "what_must_be_avoided_in_messaging": [
                "what_must_be_avoided_in_messaging",
                "What Must Be Avoided In Messaging",
                "avoid_messaging",
            ],
        }
        normalized: dict[str, Any] = {}
        for target, keys in aliases.items():
            value = None
            fallback_candidate = None
            for key in keys:
                candidate = payload.get(key) if key in payload else None
                if candidate is None or candidate == "":
                    continue
                if target in {"important_keywords", "what_must_be_avoided_in_messaging"}:
                    candidate_items = self._normalize_metadata_list(candidate, limit=8)
                    if candidate_items and any(item.strip().upper() != "MISSING" for item in candidate_items):
                        value = candidate_items
                        break
                    fallback_candidate = candidate_items
                    continue
                if str(candidate).strip() and str(candidate).strip().upper() != "MISSING":
                    value = candidate
                    break
                fallback_candidate = candidate
            if value is None:
                value = fallback_candidate
            if target in {"important_keywords", "what_must_be_avoided_in_messaging"}:
                normalized[target] = self._normalize_metadata_list(value, limit=8)
            else:
                text = self._coerce_text_value(value).strip()
                normalized[target] = text or self._coerce_text_value(fallback.get(target) or "MISSING")
        if not normalized["important_keywords"]:
            normalized["important_keywords"] = self._normalize_metadata_list(fallback.get("important_keywords"), limit=8) or ["MISSING"]
        if not normalized["what_must_be_avoided_in_messaging"]:
            normalized["what_must_be_avoided_in_messaging"] = (
                self._normalize_metadata_list(fallback.get("what_must_be_avoided_in_messaging"), limit=8) or ["MISSING"]
            )
        return MessageStrategyPayload.model_validate(normalized)

    @classmethod
    def _should_use_image_led_social(
        cls,
        request: AIOrchestrationRequest,
        compiled_context: dict[str, Any],
    ) -> bool:
        if not cls._image_generation_requested(request):
            return False
        platform = str(request.studio_panel.get("platform_preset") or "").strip().lower()
        format_name = str(request.studio_panel.get("format") or "").strip().lower()
        if platform not in {"instagram", "linkedin", "x", "youtube_thumbnail"}:
            return False
        if format_name not in cls.AI_FINAL_RENDER_FORMATS:
            return False
        ai_final_render_required = cls._request_requires_ai_final_render(request)
        if cls._should_force_sequence_pack(request) and not ai_final_render_required:
            return False
        planning_hints = request.layout_decision or {}
        mode = str(planning_hints.get("mode") or "").strip().lower()
        review_flags = {
            str(flag).strip().lower()
            for flag in cls._coerce_list(planning_hints.get("review_flags") or [])
            if str(flag).strip()
        }
        template_surface_policy = str(
            ((planning_hints.get("asset_strategy") or {}) if isinstance(planning_hints.get("asset_strategy"), dict) else {}).get("template_surface_policy")
            or ""
        ).strip().lower()
        template_fit_brief = compiled_context.get("template_fit_brief", {}) or {}
        template_confidence = 0.0
        try:
            template_confidence = float(template_fit_brief.get("confidence") or 0.0)
        except (TypeError, ValueError):
            template_confidence = 0.0
        if format_name in cls.TEMPLATE_LOCKED_IMAGE_LED_FORMATS and not ai_final_render_required:
            if mode == "exact_template" and not review_flags and template_surface_policy != "style_reference_only":
                return False
            if template_confidence >= 0.9 and mode == "exact_template" and template_surface_policy != "style_reference_only":
                return False
        return True

    @staticmethod
    def _image_generation_size(studio_panel: dict[str, Any]) -> str:
        size = studio_panel.get("size") or {}
        width = int(size.get("width") or 1080)
        height = int(size.get("height") or 1080)
        if width >= height * 1.2:
            return "1536x1024"
        if height >= width * 1.2:
            return "1024x1536"
        return "1024x1024"

    @staticmethod
    def _canvas_fit_guidance(studio_panel: dict[str, Any]) -> str:
        size = studio_panel.get("size") or {}
        width = int(size.get("width") or 1080)
        height = int(size.get("height") or 1080)
        if width <= 0 or height <= 0:
            width, height = 1080, 1080
        orientation = "square"
        if width >= height * 1.15:
            orientation = "landscape"
        elif height >= width * 1.15:
            orientation = "portrait"
        return (
            f"Canvas fit: design for the requested {width}x{height} {orientation} output ratio. "
            "Keep every headline, body line, proof point, CTA, logo-safe area, and visual focal subject fully inside a centered target-aspect safe frame with at least 8% inner margin. "
            "Never place CTA buttons, bullets, faces, hands, or key objects on the outer edge; if text feels tight, reduce copy density and scale down the layout instead of letting anything run below or outside the canvas."
        )

    @classmethod
    def _should_use_ai_final_render(
        cls,
        request: AIOrchestrationRequest,
        generation_path: str,
        creative_decision: CreativeDecisionPayload,
    ) -> bool:
        if not cls._image_generation_requested(request) or generation_path != "image_led_social":
            return False
        return cls._request_requires_ai_final_render(request)

    @classmethod
    def _image_generation_requested(cls, request: AIOrchestrationRequest) -> bool:
        if cls._request_requires_ai_final_render(request):
            return True
        return bool(request.generate_image)

    @classmethod
    def _request_requires_ai_final_render(cls, request: AIOrchestrationRequest) -> bool:
        format_name = str(request.studio_panel.get("format") or "").strip().lower()
        file_type = str(request.studio_panel.get("file_type") or "").strip().lower()
        return format_name in cls.AI_FINAL_RENDER_FORMATS and file_type in {"png", "jpg", "pdf", "doc"}

    @staticmethod
    def _ai_final_render_failure_message() -> str:
        return "AI final render failed and backend fallback rendering is disabled for this format."

    @staticmethod
    def _resolve_logo_box(scene_graph: GenerationSceneGraph) -> tuple[float, float, float, float] | None:
        for element in scene_graph.elements:
            if not element.visible or element.role != "logo":
                continue
            geometry = element.geometry
            if (
                geometry.x is None
                or geometry.y is None
                or geometry.width is None
                or geometry.height is None
            ):
                continue
            return (
                float(geometry.x),
                float(geometry.y),
                float(geometry.width),
                float(geometry.height),
            )
        return None

    @classmethod
    def _build_logo_mask_bytes(
        cls,
        *,
        scene_graph: GenerationSceneGraph,
        width: int,
        height: int,
    ) -> bytes | None:
        box = cls._resolve_logo_box(scene_graph)
        if box is None:
            left, top, box_width, box_height = 0.76, 0.06, 0.18, 0.1
        else:
            left, top, box_width, box_height = box
        x0 = max(int(left * width), 0)
        y0 = max(int(top * height), 0)
        x1 = min(int((left + box_width) * width), width)
        y1 = min(int((top + box_height) * height), height)
        if x1 <= x0 or y1 <= y0:
            return None

        mask = Image.new("RGBA", (width, height), (0, 0, 0, 255))
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((x0, y0, x1, y1), radius=max(min(x1 - x0, y1 - y0) // 5, 8), fill=(0, 0, 0, 0))
        buffer = BytesIO()
        mask.save(buffer, format="PNG")
        return buffer.getvalue()

    def _apply_ai_logo_edit_pass(
        self,
        *,
        image_provider,
        tenant_id,
        brand_space_id,
        prompt: str,
        base_asset_payload: dict[str, Any],
        logo_storage_path: str | None,
        scene_graph: GenerationSceneGraph,
        size: str | None,
        trace_id: str | None,
        trace_label: str,
    ) -> tuple[dict[str, Any], bool]:
        if not logo_storage_path or not self.storage.exists(logo_storage_path):
            return base_asset_payload, False
        base_storage_path = str(base_asset_payload.get("storage_path") or "").strip()
        if not base_storage_path or not self.storage.exists(base_storage_path):
            return base_asset_payload, False
        width = int(base_asset_payload.get("width") or 0)
        height = int(base_asset_payload.get("height") or 0)
        if width <= 0 or height <= 0:
            return base_asset_payload, False
        mask_png_bytes = self._build_logo_mask_bytes(
            scene_graph=scene_graph,
            width=width,
            height=height,
        )
        if not mask_png_bytes:
            return base_asset_payload, False
        try:
            edited_asset = self._edit_image_with_retries(
                image_provider=image_provider,
                tenant_id=tenant_id,
                brand_space_id=brand_space_id,
                prompt=(
                    f"{prompt}\n\n"
                    "Use the exact provided brand logo in the reserved logo area only. "
                    "Preserve the composition, copy layout, and overall design. "
                    "Do not add extra text, icons, or substitute marks."
                ),
                image_paths=[
                    self.storage.absolute_path(base_storage_path),
                    self.storage.absolute_path(logo_storage_path),
                ],
                size=size,
                mask_png_bytes=mask_png_bytes,
                trace_id=trace_id,
                trace_label=trace_label,
            )
            return edited_asset, True
        except Exception as exc:  # pragma: no cover - resilience path
            self._trace_payload(
                trace_id,
                self.trace,
                f"{trace_label}_error",
                {
                    "error": str(exc),
                    "logo_storage_path": logo_storage_path,
                    "base_storage_path": base_storage_path,
                },
            )
            return base_asset_payload, False

    def _fallback_image_led_scene_graph(
        self,
        *,
        request: AIOrchestrationRequest,
        text_payload: dict[str, Any],
        creative_decision: dict[str, Any],
        compiled_context: dict[str, Any],
    ) -> dict[str, Any]:
        size = request.studio_panel.get("size") or BlueprintService.PRESET_DIMENSIONS.get(
            request.studio_panel.get("platform_preset", "instagram"),
            BlueprintService.PRESET_DIMENSIONS["instagram"],
        )
        palette_roles = dict((compiled_context.get("brand_visual_brief", {}) or {}).get("palette_roles", {}) or {})
        proof_points = list((text_payload.get("metadata") or {}).get("proof_points") or [])

        # Extract font sizes from brand context (from analyzed reference samples)
        font_sizes = self._extract_font_sizes_from_brand_context(request.resolved_brand_context)

        layout_profile = self._image_led_layout_profile(
            request=request,
            text_payload=text_payload,
            compiled_context=compiled_context,
        )
        elements: list[dict[str, Any]] = [
            {
                "element_id": "background",
                "element_type": "background",
                "role": "background",
                "layer": "background",
                "geometry": self._normalized_box(0, 0, 1, 1),
                "style": {
                    "fill_role": "background",
                    "primary_fill": palette_roles.get("background") or palette_roles.get("surface"),
                    "gradient_from": palette_roles.get("background") or palette_roles.get("surface"),
                    "gradient_to": palette_roles.get("primary"),
                },
            },
            {
                "element_id": "hero_image",
                "element_type": "image",
                "role": "image",
                "layer": "primary_visual",
                "geometry": layout_profile["hero_image"],
                "style": {"fit": "cover", "border_radius": 28},
                "asset": {"asset_role": "ai_image"},
            },
            {
                "element_id": "overlay_panel",
                "element_type": "decorative_shape",
                "role": "decorative_shape",
                "layer": "decorative",
                "geometry": layout_profile["overlay_panel"],
                "style": {
                    "shape": "rounded_rect",
                    "fill_role": "surface",
                    "fill": "#FFFFFF",
                    "border_radius": 32,
                },
            },
            *layout_profile.get("decorative_shapes", []),
            {
                "element_id": "logo",
                "element_type": "logo",
                "role": "logo",
                "layer": "brand",
                "geometry": layout_profile["logo"],
                "style": {"fit": "contain"},
                "asset": {"asset_role": "logo", "trust_level": "trusted"},
            },
            {
                "element_id": "headline",
                "element_type": "text",
                "role": "headline",
                "layer": "content",
                "geometry": layout_profile["headline"],
                "text": text_payload.get("headline", ""),
                "style": {"font_size": font_sizes["headline"], "font_role": "heading", "fill_role": "primary", "max_lines": 3},
            },
            {
                "element_id": "supporting_line",
                "element_type": "text",
                "role": "supporting_line",
                "layer": "content",
                "geometry": layout_profile["supporting_line"],
                "text": (text_payload.get("metadata") or {}).get("supporting_line") or text_payload.get("body", ""),
                "style": {"font_size": font_sizes["body"], "font_role": "body", "fill_role": "secondary_text", "max_lines": 4},
            },
            {
                "element_id": "proof_points",
                "element_type": "text",
                "role": "proof_points",
                "layer": "content",
                "geometry": layout_profile["proof_points"],
                "text": proof_points[:4] or self._sentences(text_payload.get("body", ""))[:4],
                "style": {"font_size": 20, "font_role": "body", "fill_role": "secondary_text", "max_lines": 5},
            },
            {
                "element_id": "cta",
                "element_type": "text",
                "role": "cta",
                "layer": "brand",
                "geometry": layout_profile["cta"],
                "text": text_payload.get("cta", ""),
                "style": {
                    "font_size": 22,
                    "font_role": "cta",
                    "fill_role": "light_text",
                    "background_fill_role": "primary",
                    "max_lines": 2,
                },
            },
        ]
        return {
            "layout_mode": creative_decision.get("layout_mode") or "synthesized_layout",
            "confidence": creative_decision.get("confidence") or 0.72,
            "canvas": {
                "width": int(size.get("width") or 1080),
                "height": int(size.get("height") or 1080),
                "platform": request.studio_panel.get("platform_preset", "instagram"),
                "file_type": request.studio_panel.get("file_type", "png"),
                "safe_margin": 52,
            },
            "layers": ["background", "primary_visual", "decorative", "content", "brand", "footer"],
            "styles": {
                "layout_type": "image_led_social",
                "layout_archetype": layout_profile["layout_archetype"],
            },
            "assets": [],
            "template_adaptation": {
                **self._coerce_mapping(creative_decision.get("adaptations")),
                "selected_template_id": creative_decision.get("selected_template_id"),
            },
            "validation_hints": {
                "overlay_style": "image_led_social",
                "template_surface_policy": "style_reference_only",
                "layout_type": layout_profile["layout_type"],
            },
            "elements": elements,
        }

    @classmethod
    def _merge_repair_into_scene_graph(
        cls,
        existing_scene_graph: dict[str, Any],
        repair_scene_graph: dict[str, Any],
        repair_attempt: int,
    ) -> dict[str, Any]:
        """Merge repair response into existing scene graph instead of replacing it.

        LLM may return only the repaired elements, not the complete scene graph.
        This method merges repaired elements by element_id into the existing scene graph.

        Args:
            existing_scene_graph: Current complete scene graph
            repair_scene_graph: Repair response scene graph (may be partial)
            repair_attempt: Current repair attempt number for logging

        Returns:
            Merged scene graph with repairs applied
        """
        if not repair_scene_graph:
            logger.warning(f"Repair {repair_attempt}: Empty repair scene graph, keeping existing")
            return existing_scene_graph

        # Start with existing scene graph
        merged = existing_scene_graph.copy()

        # Check if repair has elements array
        repair_elements = repair_scene_graph.get("elements", [])
        existing_elements = merged.get("elements", [])

        if not repair_elements:
            logger.warning(f"Repair {repair_attempt}: No elements in repair response, keeping existing {len(existing_elements)} elements")
            return merged

        # Build element_id index of repaired elements
        repaired_by_id = {}
        for elem in repair_elements:
            elem_id = elem.get("element_id")
            if elem_id:
                repaired_by_id[elem_id] = elem

        if not repaired_by_id:
            logger.warning(f"Repair {repair_attempt}: No element_ids in repair response, treating as complete scene graph replacement")
            # If no element_ids, repair is likely a complete scene graph, not a partial update
            merged["elements"] = repair_elements
            logger.info(f"Repair {repair_attempt}: Replaced scene graph with {len(repair_elements)} elements")
        else:
            primary_text_roles = {
                "headline",
                "supporting_line",
                "body",
                "proof_points",
                "cta",
                "stat_highlights",
                "section_label",
                "footer",
                "legal",
            }
            existing_role_counts: dict[str, int] = {}
            existing_role_indexes: dict[str, list[int]] = {}
            for index, elem in enumerate(existing_elements):
                role = str(elem.get("role") or "").strip().lower()
                if not role:
                    continue
                existing_role_counts[role] = existing_role_counts.get(role, 0) + 1
                existing_role_indexes.setdefault(role, []).append(index)

            repair_role_counts: dict[str, int] = {}
            for elem in repair_elements:
                role = str(elem.get("role") or "").strip().lower()
                if role:
                    repair_role_counts[role] = repair_role_counts.get(role, 0) + 1

            # Merge: update existing elements that have matching IDs
            merged_count = 0
            for i, elem in enumerate(existing_elements):
                elem_id = elem.get("element_id")
                if elem_id and elem_id in repaired_by_id:
                    # Replace with repaired version
                    existing_elements[i] = repaired_by_id[elem_id]
                    merged_count += 1
                    logger.info(f"Repair {repair_attempt}: Merged repair for element '{elem_id}'")
                    del repaired_by_id[elem_id]

            # Add any new elements from repair that weren't in existing
            added_count = 0
            for new_elem in repaired_by_id.values():
                role = str(new_elem.get("role") or "").strip().lower()
                if role in primary_text_roles:
                    if repair_role_counts.get(role, 0) > 1 and existing_role_counts.get(role, 0) >= 1:
                        logger.warning(
                            "Repair %s: Skipping suspicious duplicate repaired text role '%s' to avoid multi-section scene drift",
                            repair_attempt,
                            role,
                        )
                        continue
                    existing_indexes = existing_role_indexes.get(role, [])
                    if len(existing_indexes) == 1 and repair_role_counts.get(role, 0) == 1:
                        replacement = dict(new_elem)
                        replacement["element_id"] = existing_elements[existing_indexes[0]].get("element_id") or replacement.get("element_id")
                        existing_elements[existing_indexes[0]] = replacement
                        merged_count += 1
                        logger.info(
                            "Repair %s: Merged repaired '%s' by role into existing element '%s'",
                            repair_attempt,
                            role,
                            replacement.get("element_id"),
                        )
                        continue
                existing_elements.append(new_elem)
                new_elem_id = new_elem.get("element_id", "unknown")
                logger.info(f"Repair {repair_attempt}: Added new element '{new_elem_id}' from repair")
                added_count += 1

            merged["elements"] = existing_elements
            logger.info(
                f"Repair {repair_attempt}: Merged {merged_count} elements, added {added_count} new elements, "
                f"final count: {len(existing_elements)} elements"
            )

        # Merge other top-level properties (styles, canvas, confidence, etc.)
        for key in ("styles", "canvas", "layout_mode", "confidence", "layers"):
            if key in repair_scene_graph:
                merged[key] = repair_scene_graph[key]
                logger.debug(f"Repair {repair_attempt}: Updated scene_graph.{key}")

        return merged

    def normalize_scene_graph_payload(
        self,
        raw: Any,
        *,
        fallback: dict[str, Any],
        creative_decision: CreativeDecisionPayload,
        text_payload: dict[str, Any],
        request: AIOrchestrationRequest,
        compiled_context: dict[str, Any],
        allow_recovery: bool = True,
    ) -> GenerationSceneGraph:
        payload = dict(fallback or {})
        if isinstance(raw, dict):
            payload.update(raw)
        payload["layout_mode"] = creative_decision.layout_mode
        raw_layers = payload.get("layers")
        raw_assets = payload.get("assets") or fallback.get("assets") or []
        canvas = self._coerce_mapping(payload.get("canvas"))
        size = request.studio_panel.get("size") or {}
        canvas.setdefault("width", int(size.get("width") or 1080))
        canvas.setdefault("height", int(size.get("height") or 1080))
        canvas.setdefault("platform", request.studio_panel.get("platform_preset", "instagram"))
        canvas.setdefault("file_type", request.studio_panel.get("file_type", "png"))
        canvas.setdefault("safe_margin", 48)
        payload["canvas"] = canvas
        try:
            payload["confidence"] = float(payload.get("confidence") or creative_decision.confidence or 0.0)
        except (TypeError, ValueError):
            payload["confidence"] = float(creative_decision.confidence or 0.0)
        payload["layers"] = self._normalize_scene_graph_layers(raw_layers or self.DEFAULT_LAYERS)
        if not payload["layers"]:
            payload["layers"] = list(self.DEFAULT_LAYERS)
        asset_catalog = self._normalize_scene_graph_assets(raw_assets)
        payload["assets"] = asset_catalog
        payload["template_adaptation"] = {
            **self._coerce_mapping(payload.get("template_adaptation")),
            **self._coerce_mapping(creative_decision.adaptations),
            "selected_template_id": creative_decision.selected_template_id,
        }
        payload["styles"] = {
            **self._coerce_mapping(fallback.get("styles")),
            **self._coerce_mapping(payload.get("styles")),
            "copy_snapshot": {
                "headline": text_payload.get("headline", ""),
                "body": text_payload.get("body", ""),
                "cta": text_payload.get("cta", ""),
            },
            "brand_visual_brief": compiled_context.get("brand_visual_brief", {}),
        }
        payload["validation_hints"] = {
            **self._coerce_mapping(fallback.get("validation_hints")),
            **self._coerce_mapping(payload.get("validation_hints")),
        }
        allowed_font_families = self._compiled_font_families(compiled_context)
        elements = payload.get("elements")
        source_elements = self._extract_scene_graph_source_elements(
            elements_source=elements,
            layers_source=raw_layers,
            fallback_source=(fallback or {}).get("elements") or [],
        )
        normalized_elements: list[dict[str, Any]] = []
        role_counts: dict[str, int] = {}
        seen_element_ids: set[str] = set()
        for item in self._coerce_list(source_elements):
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            source_key = str(normalized.pop("_source_key", "") or "").strip()
            if normalized.get("element_id") is None and normalized.get("id") is not None:
                normalized["element_id"] = normalized.get("id")
            if normalized.get("element_type") is None and normalized.get("type") is not None:
                normalized["element_type"] = normalized.get("type")
            if normalized.get("text") is None and source_key in {"headline", "supporting_line", "body", "proof_points", "cta", "footer", "legal", "section_label", "stat_highlights"}:
                source_value = item.get("text")
                if source_value is None:
                    source_value = item.get("value")
                if source_value is None:
                    source_value = item.get("content")
                normalized["text"] = source_value
            element_name_hint = self._sanitize_scene_element_name(
                normalized.get("element_id") or normalized.get("id") or normalized.get("role") or source_key
            )
            role_name = self._infer_scene_element_role(normalized, source_key=source_key)
            role_key = re.sub(r"[^a-z0-9]+", "_", role_name.casefold()).strip("_") or "element"
            role_counts[role_key] = role_counts.get(role_key, 0) + 1
            normalized.setdefault("role", role_key)
            normalized.setdefault("element_type", self._default_scene_element_type(normalized))
            normalized["element_type"] = self._normalize_scene_element_type(normalized.get("element_type"))
            normalized.setdefault(
                "element_id",
                element_name_hint or (role_key if role_counts[role_key] == 1 else f"{role_key}_{role_counts[role_key]}"),
            )
            element_id = str(normalized.get("element_id") or "").strip()
            if not element_id:
                element_id = role_key if role_counts[role_key] == 1 else f"{role_key}_{role_counts[role_key]}"
                normalized["element_id"] = element_id
            if element_id in seen_element_ids:
                continue
            seen_element_ids.add(element_id)
            normalized["geometry"] = self._normalize_scene_element_geometry(normalized)
            normalized["text"] = self._normalize_scene_element_text(normalized)
            normalized["validation_hints"] = self._coerce_mapping(normalized.get("validation_hints"))
            normalized["style"] = self._normalize_text_style_for_brand(
                self._normalize_scene_element_style(normalized),
                role=str(normalized.get("role") or normalized.get("element_type") or ""),
                allowed_font_families=allowed_font_families,
                validation_hints=normalized["validation_hints"],
            )
            asset_payload = self._coerce_mapping(normalized.get("asset"))
            if not asset_payload:
                for candidate_key in filter(None, [source_key, role_key, str(normalized.get("element_id") or "").strip()]):
                    candidate_asset = self._coerce_mapping(raw_assets.get(candidate_key) if isinstance(raw_assets, dict) else {})
                    if candidate_asset:
                        asset_payload = candidate_asset
                        break
            for key in ("asset_id", "asset_role", "storage_path", "trust_level", "variant", "notes"):
                if key not in asset_payload and normalized.get(key) is not None:
                    asset_payload[key] = normalized.get(key)
            normalized["asset"] = self._sanitize_scene_element_asset_payload(
                asset_payload,
                element=normalized,
                request=request,
            )
            normalized_elements.append(normalized)
        payload["elements"] = self._sync_scene_graph_copy_from_text_payload(
            elements=normalized_elements,
            text_payload=text_payload,
        )
        payload["elements"] = self._finalize_logo_scene_policy(
            scene_graph_payload=payload,
            elements=payload["elements"],
            request=request,
            text_payload=text_payload,
            creative_decision=creative_decision,
        )
        payload = self._apply_design_system_scene_defaults(
            scene_graph_payload=payload,
            request=request,
        )
        payload = self._apply_reference_family_scene_defaults(
            payload,
            compiled_context=compiled_context,
        )
        # Fix 2: Inject legal disclaimers from brand assets
        payload["elements"] = self._inject_legal_disclaimers(
            elements=payload["elements"],
            request=request,
            canvas=canvas,
        )
        # Fix 3: Apply CTA template styling to CTA elements
        payload["elements"] = self._apply_cta_template_styling(
            elements=payload["elements"],
            request=request,
        )
        # Fix 4: Apply component motif patterns (numbered badges, background boxes)
        payload["elements"] = self._apply_component_motif_patterns(
            elements=payload["elements"],
            request=request,
        )
        # Fix 5: Remap template colors to brand palette
        payload = self._remap_template_colors_to_brand_palette(
            scene_graph=payload,
            compiled_context=compiled_context,
            planning_hints=request.layout_decision if isinstance(request.layout_decision, dict) else None,
        )
        payload = self._collapse_stacked_carousel_scene_graph(
            payload,
            request=request,
        )
        try:
            return GenerationSceneGraph.model_validate(payload)
        except ValidationError:
            if not allow_recovery:
                raise
            logger.warning(
                "orchestrator.scene_graph_normalization_recovered brand_space_id=%s format=%s",
                request.brand_space_id,
                request.studio_panel.get("format"),
                exc_info=True,
            )
            recovery_payload = self._fallback_image_led_scene_graph(
                request=request,
                text_payload=text_payload,
                creative_decision=creative_decision.model_dump(mode="json"),
                compiled_context=compiled_context,
            )
            return self.normalize_scene_graph_payload(
                recovery_payload,
                fallback=fallback,
                creative_decision=creative_decision,
                text_payload=text_payload,
                request=request,
                compiled_context=compiled_context,
                allow_recovery=False,
            )

    def _extract_scene_graph_source_elements(
        self,
        *,
        elements_source: Any,
        layers_source: Any,
        fallback_source: Any,
    ) -> list[dict[str, Any]]:
        if isinstance(elements_source, list) and elements_source:
            return [dict(item) for item in elements_source if isinstance(item, dict)]

        layer_items = [dict(item) for item in self._coerce_list(layers_source) if isinstance(item, dict)]
        layer_keys = {
            self._sanitize_scene_element_name(
                str(item.get("role") or item.get("id") or item.get("element_id") or item.get("type") or "")
            )
            for item in layer_items
        }
        layer_keys.discard("")

        extracted: list[dict[str, Any]] = []
        if isinstance(elements_source, dict):
            for key, value in elements_source.items():
                source_key = self._sanitize_scene_element_name(key)
                if isinstance(value, dict):
                    candidate = dict(value)
                    candidate.setdefault("_source_key", key)
                    extracted.append(candidate)
                    continue
                if source_key in {"headline", "supporting_line", "body", "proof_points", "cta", "footer", "legal", "section_label", "stat_highlights"}:
                    if source_key in layer_keys:
                        continue
                    text_value = self._coerce_text_value(value).strip()
                    if not text_value:
                        continue
                    extracted.append({"_source_key": key, "role": source_key, "text": value})
        for item in layer_items:
            extracted.append(item)
        if extracted:
            return extracted
        if isinstance(fallback_source, list) and fallback_source:
            return [dict(item) for item in fallback_source if isinstance(item, dict)]
        if isinstance(fallback_source, dict):
            return self._extract_scene_graph_source_elements(
                elements_source=fallback_source,
                layers_source=[],
                fallback_source=[],
            )
        return []

    @classmethod
    def _carousel_slide_index_from_element_id(cls, value: Any) -> int | None:
        token = cls._sanitize_scene_element_name(value)
        if not token:
            return None
        match = re.match(r"slide_(\d+)_", token)
        if not match:
            return None
        try:
            return int(match.group(1))
        except (TypeError, ValueError):
            return None

    @classmethod
    def _geometry_frame_from_elements(cls, elements: list[dict[str, Any]]) -> dict[str, float] | None:
        geometry_candidates: list[dict[str, float]] = []
        preferred_roles = {"content_card", "panel", "overlay_panel", "card"}
        for element in elements:
            geometry = cls._coerce_mapping(element.get("geometry"))
            try:
                x = float(geometry.get("x"))
                y = float(geometry.get("y"))
                width = float(geometry.get("width"))
                height = float(geometry.get("height"))
            except (TypeError, ValueError):
                continue
            if width <= 0 or height <= 0:
                continue
            candidate = {"x": x, "y": y, "width": width, "height": height}
            if str(element.get("role") or "").strip().casefold() in preferred_roles:
                return candidate
            geometry_candidates.append(candidate)
        if not geometry_candidates:
            return None
        min_x = min(item["x"] for item in geometry_candidates)
        min_y = min(item["y"] for item in geometry_candidates)
        max_x = max(item["x"] + item["width"] for item in geometry_candidates)
        max_y = max(item["y"] + item["height"] for item in geometry_candidates)
        width = max_x - min_x
        height = max_y - min_y
        if width <= 0 or height <= 0:
            return None
        return {"x": min_x, "y": min_y, "width": width, "height": height}

    @classmethod
    def _localize_geometry_to_frame(
        cls,
        geometry: dict[str, Any],
        frame: dict[str, float],
    ) -> dict[str, Any]:
        localized = dict(geometry or {})
        try:
            x = float(localized.get("x"))
            y = float(localized.get("y"))
            width = float(localized.get("width"))
            height = float(localized.get("height"))
            frame_x = float(frame.get("x"))
            frame_y = float(frame.get("y"))
            frame_width = float(frame.get("width"))
            frame_height = float(frame.get("height"))
        except (TypeError, ValueError):
            return localized
        if frame_width <= 0 or frame_height <= 0:
            return localized
        localized["x"] = round((x - frame_x) / frame_width, 4)
        localized["y"] = round((y - frame_y) / frame_height, 4)
        localized["width"] = round(width / frame_width, 4)
        localized["height"] = round(height / frame_height, 4)
        localized["units"] = "normalized"
        return localized

    @classmethod
    def _collapse_stacked_carousel_scene_graph(
        cls,
        payload: dict[str, Any],
        *,
        request: AIOrchestrationRequest,
    ) -> dict[str, Any]:
        if str(request.studio_panel.get("format") or "").strip().lower() != "carousel":
            return payload
        elements = [dict(item) for item in cls._coerce_list(payload.get("elements")) if isinstance(item, dict)]
        if not elements:
            return payload
        slide_groups: dict[int, list[dict[str, Any]]] = {}
        shared_elements: list[dict[str, Any]] = []
        for element in elements:
            slide_index = cls._carousel_slide_index_from_element_id(element.get("element_id"))
            if slide_index is None:
                shared_elements.append(dict(element))
                continue
            slide_groups.setdefault(slide_index, []).append(dict(element))
        if len(slide_groups) < 2:
            return payload
        first_slide_index = min(slide_groups)
        first_slide_elements = [dict(item) for item in slide_groups.get(first_slide_index, [])]
        frame = cls._geometry_frame_from_elements(first_slide_elements)
        if frame is None:
            return payload

        collapsed_elements: list[dict[str, Any]] = []
        for element in shared_elements:
            role = str(element.get("role") or "").strip().casefold()
            element_id = str(element.get("element_id") or "").strip().casefold()
            if role not in {"background", "logo", "legal", "footer", "decorative_shape"}:
                continue
            if element_id.startswith("final_"):
                continue
            collapsed_elements.append(dict(element))
        for element in first_slide_elements:
            localized = dict(element)
            geometry = cls._coerce_mapping(localized.get("geometry"))
            if geometry:
                localized["geometry"] = cls._localize_geometry_to_frame(geometry, frame)
            collapsed_elements.append(localized)
        if not collapsed_elements:
            return payload

        styles = cls._coerce_mapping(payload.get("styles"))
        validation_hints = cls._coerce_mapping(payload.get("validation_hints"))
        styles.setdefault("carousel_scene_scope", "slide_1_localized")
        validation_hints["carousel_scene_scope"] = "slide_1_localized"
        payload["elements"] = collapsed_elements
        payload["styles"] = styles
        payload["validation_hints"] = validation_hints
        return payload

    @classmethod
    def _sanitize_scene_element_name(cls, value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().casefold()).strip("_")

    @classmethod
    def _infer_scene_element_role(cls, element: dict[str, Any], *, source_key: str = "") -> str:
        candidate_values = [
            element.get("role"),
            source_key,
            element.get("element_id"),
            element.get("id"),
            element.get("text_role"),
            element.get("asset_role"),
            element.get("type"),
            element.get("element_type"),
        ]
        for candidate in candidate_values:
            token = cls._sanitize_scene_element_name(candidate)
            if not token:
                continue
            if token in {"headline", "heading", "heading_sans", "title"}:
                return "headline"
            if token in {"supporting_line", "subheadline", "supporting_copy", "subhead"}:
                return "supporting_line"
            if token in {"body", "body_text", "body_sans", "copy"}:
                return "body"
            if token in {"proof_points", "bullet_list", "checklist", "stat_highlights"}:
                return "proof_points" if token != "stat_highlights" else "stat_highlights"
            if token in {"cta", "cta_button", "text_button", "button"}:
                return "cta"
            if token in {"logo", "logo_placeholder", "brand_logo"}:
                return "logo"
            if token in {"background", "color_fill"}:
                return "background"
            if token in {"image", "hero_image", "primary_image", "hero_visual", "photo_hero", "generated_image"}:
                return "image"
            if token in {"icon", "icons"}:
                return "icon"
            if token in {"decorative_shape", "background_shape", "micro_design_element", "footer_decor", "enhancement_component", "vector_shape", "shape", "minimal_accent", "circle_accent", "overlay_panel"}:
                return "decorative_shape"
            if "headline" in token:
                return "headline"
            if token.endswith("_image") or "image" in token or "hero" in token:
                return "image"
            if "logo" in token:
                return "logo"
        return "element"

    @classmethod
    def _normalize_scene_element_type(cls, value: Any) -> str:
        token = cls._sanitize_scene_element_name(value)
        if token in {"color_fill"}:
            return "background"
        if token in {"text_button"}:
            return "text"
        if token in {"vector_shape", "shape", "minimal_accent", "circle_accent"}:
            return "decorative_shape"
        if token in {"brand_logo", "logo_placeholder"}:
            return "logo"
        if token in {"photo_hero", "generated_image"}:
            return "image"
        return token or "decorative_shape"

    @classmethod
    def _normalize_scene_graph_layers(cls, value: Any) -> list[str]:
        normalized_layers: list[str] = []
        for item in cls._coerce_list(value):
            if isinstance(item, dict):
                label = item.get("layer") or item.get("id") or item.get("role") or item.get("type")
            else:
                label = item
            layer_name = str(label or "").strip()
            if layer_name:
                normalized_layers.append(layer_name)
        return normalized_layers

    @classmethod
    def _normalize_scene_graph_assets(cls, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            normalized_assets: list[dict[str, Any]] = []
            for key, item in value.items():
                asset_payload = cls._coerce_mapping(item)
                if not asset_payload:
                    continue
                asset_payload.setdefault("notes", str(key))
                normalized_assets.append(asset_payload)
            return normalized_assets
        return [
            item
            for item in cls._coerce_list(value)
            if isinstance(item, dict)
        ]

    @staticmethod
    def _parse_geometry_value(value: Any) -> float | int | None:
        """Convert geometry values including percentage strings to numeric values"""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            value = value.strip()
            # Handle percentage strings like '80%'
            if value.endswith('%'):
                try:
                    return float(value.rstrip('%')) / 100.0
                except (ValueError, TypeError):
                    return None
            # Try to parse as number
            try:
                if '.' in value:
                    return float(value)
                return int(value)
            except (ValueError, TypeError):
                return None
        return None

    @classmethod
    def _default_geometry_for_role(cls, role: str, anchor: str | None) -> dict[str, float]:
        """Provide safe default normalized geometry based on element role."""
        # Role-based defaults for common social media layouts
        defaults = {
            "background": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
            "headline": {"x": 0.08, "y": 0.12, "width": 0.84, "height": 0.15},
            "supporting_line": {"x": 0.08, "y": 0.30, "width": 0.84, "height": 0.08},
            "body": {"x": 0.08, "y": 0.42, "width": 0.84, "height": 0.25},
            "cta": {"x": 0.08, "y": 0.78, "width": 0.40, "height": 0.08},
            "logo": {"x": 0.85, "y": 0.85, "width": 0.10, "height": 0.10},
            "image": {"x": 0.15, "y": 0.20, "width": 0.70, "height": 0.50},
            "icon": {"x": 0.08, "y": 0.50, "width": 0.12, "height": 0.12},
            "decorative_shape": {"x": 0.70, "y": 0.10, "width": 0.25, "height": 0.25},
            "legal_footer": {"x": 0.05, "y": 0.92, "width": 0.90, "height": 0.05},
            "footer": {"x": 0.05, "y": 0.92, "width": 0.90, "height": 0.05},
        }

        default = defaults.get(role, {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.2})

        # Adjust based on anchor if provided
        if anchor:
            anchor_adjustments = {
                "top-left": {},
                "top-center": {"x": 0.5 - default["width"]/2},
                "top-right": {"x": 1.0 - default["width"]},
                "center": {"x": 0.5 - default["width"]/2, "y": 0.5 - default["height"]/2},
                "bottom-center": {"x": 0.5 - default["width"]/2, "y": 1.0 - default["height"]},
                "bottom-left": {"y": 1.0 - default["height"]},
                "bottom-right": {"x": 1.0 - default["width"], "y": 1.0 - default["height"]},
            }
            default.update(anchor_adjustments.get(anchor, {}))

        return default

    @classmethod
    def _normalize_scene_element_geometry(cls, element: dict[str, Any]) -> dict[str, Any]:
        geometry = element.get("geometry")
        if isinstance(geometry, str):
            role = str(element.get("role") or "").strip().lower()
            default_geometry = cls._default_geometry_for_role(role, geometry)
            return {**default_geometry, "anchor": geometry, "units": "normalized"}
        normalized_geometry = cls._coerce_mapping(geometry)
        # Parse percentage strings in existing geometry
        if normalized_geometry:
            for key in ("x", "y", "width", "height"):
                if key in normalized_geometry:
                    parsed = cls._parse_geometry_value(normalized_geometry[key])
                    if parsed is not None:
                        normalized_geometry[key] = parsed
            if "z_index" in normalized_geometry:
                parsed_z = cls._parse_geometry_value(normalized_geometry.get("z_index"))
                if parsed_z is None:
                    normalized_geometry.pop("z_index", None)
                else:
                    normalized_geometry["z_index"] = int(round(float(parsed_z)))
            if isinstance(normalized_geometry.get("padding"), dict):
                padding_payload: dict[str, float | int] = {}
                for key, value in list(normalized_geometry.get("padding", {}).items()):
                    parsed = cls._parse_geometry_value(value)
                    if parsed is not None:
                        padding_payload[str(key)] = parsed
                normalized_geometry["padding"] = padding_payload
            units = str(normalized_geometry.get("units") or "").strip().lower()
            is_normalized = units != "px"
            if not units:
                is_normalized = not any(
                    isinstance(normalized_geometry.get(metric), (int, float)) and float(normalized_geometry.get(metric)) > 1.0
                    for metric in ("x", "y", "width", "height")
                )
                if is_normalized:
                    normalized_geometry["units"] = "normalized"
            if is_normalized:
                x = normalized_geometry.get("x")
                y = normalized_geometry.get("y")
                width = normalized_geometry.get("width")
                height = normalized_geometry.get("height")
                if isinstance(width, (int, float)):
                    normalized_geometry["width"] = max(0.0, min(float(width), 1.0))
                if isinstance(height, (int, float)):
                    normalized_geometry["height"] = max(0.0, min(float(height), 1.0))
                width = normalized_geometry.get("width")
                height = normalized_geometry.get("height")
                if isinstance(x, (int, float)):
                    clamped_x = max(0.0, min(float(x), 1.0))
                    if isinstance(width, (int, float)) and clamped_x + float(width) > 1.0:
                        clamped_x = max(0.0, 1.0 - float(width))
                    normalized_geometry["x"] = clamped_x
                if isinstance(y, (int, float)):
                    clamped_y = max(0.0, min(float(y), 1.0))
                    if isinstance(height, (int, float)) and clamped_y + float(height) > 1.0:
                        clamped_y = max(0.0, 1.0 - float(height))
                    normalized_geometry["y"] = clamped_y
            if not all(normalized_geometry.get(metric) is not None for metric in ("x", "y", "width", "height")):
                role = str(element.get("role") or "").strip().lower()
                anchor = str(normalized_geometry.get("anchor") or element.get("anchor") or "").strip() or None
                default_geometry = cls._default_geometry_for_role(role, anchor)
                for metric, default_value in default_geometry.items():
                    normalized_geometry.setdefault(metric, default_value)
                normalized_geometry.setdefault("units", "normalized")
                logger.info(
                    "Applied default geometry for incomplete role '%s': x=%s, y=%s, width=%s, height=%s",
                    role,
                    normalized_geometry.get("x"),
                    normalized_geometry.get("y"),
                    normalized_geometry.get("width"),
                    normalized_geometry.get("height"),
                )
            return normalized_geometry
        position = cls._coerce_mapping(element.get("position"))
        size = element.get("size")
        area = cls._coerce_mapping(element.get("area"))
        max_size = cls._coerce_mapping(element.get("max_size"))
        geometry_payload: dict[str, Any] = {}
        if position.get("x") is not None:
            geometry_payload["x"] = cls._parse_geometry_value(position.get("x"))
        if position.get("y") is not None:
            geometry_payload["y"] = cls._parse_geometry_value(position.get("y"))
        width = None
        height = None
        if isinstance(size, dict):
            width = size.get("width")
            height = size.get("height")
        elif isinstance(size, (int, float)):
            width = size
            height = size
        width = area.get("width") if area.get("width") is not None else width
        height = area.get("height") if area.get("height") is not None else height
        width = max_size.get("width") if max_size.get("width") is not None else width
        height = max_size.get("height") if max_size.get("height") is not None else height
        width = element.get("max_width") if element.get("max_width") is not None else width
        height = element.get("max_height") if element.get("max_height") is not None else height
        if width is not None:
            geometry_payload["width"] = cls._parse_geometry_value(width)
        if height is not None:
            geometry_payload["height"] = cls._parse_geometry_value(height)
        anchor = element.get("anchor")
        if anchor:
            geometry_payload["anchor"] = anchor
        z_index = element.get("z_index")
        if z_index is not None:
            parsed_z = cls._parse_geometry_value(z_index)
            if parsed_z is not None:
                geometry_payload["z_index"] = int(round(float(parsed_z)))
        if geometry_payload:
            units = "normalized"
            for metric in ("x", "y", "width", "height"):
                value = geometry_payload.get(metric)
                if isinstance(value, (int, float)) and value > 1:
                    units = "px"
                    break
            geometry_payload.setdefault("units", units)

        # Apply default geometry if coordinates are missing
        if geometry_payload and not all(k in geometry_payload for k in ("x", "y", "width", "height")):
            role = element.get("role", "")
            anchor = geometry_payload.get("anchor") or element.get("anchor")
            default_geom = cls._default_geometry_for_role(role, anchor)
            geometry_payload.setdefault("x", default_geom["x"])
            geometry_payload.setdefault("y", default_geom["y"])
            geometry_payload.setdefault("width", default_geom["width"])
            geometry_payload.setdefault("height", default_geom["height"])
            logger.info(f"Applied default geometry for role '{role}': x={geometry_payload['x']}, y={geometry_payload['y']}, width={geometry_payload['width']}, height={geometry_payload['height']}")

        if not geometry_payload:
            role = str(element.get("role") or "").strip().lower()
            anchor = str(element.get("anchor") or "").strip() or None
            default_geom = cls._default_geometry_for_role(role, anchor)
            geometry_payload = {
                **default_geom,
                "units": "normalized",
            }
            if anchor:
                geometry_payload["anchor"] = anchor
            logger.info(
                "Applied default geometry for missing role '%s': x=%s, y=%s, width=%s, height=%s",
                role,
                geometry_payload["x"],
                geometry_payload["y"],
                geometry_payload["width"],
                geometry_payload["height"],
            )

        return geometry_payload

    @classmethod
    def _normalize_scene_element_style(cls, element: dict[str, Any]) -> dict[str, Any]:
        style = cls._coerce_mapping(element.get("style"))
        top_level_mappings = {
            "font_family": "font_family",
            "font": "font_family",
            "font_size": "font_size",
            "font_weight": "font_weight",
            "color": "fill",
            "background_color": "background_fill",
            "opacity": "opacity",
            "shape": "shape",
            "alignment": "text_align",
            "text_align": "text_align",
            "text_role": "font_role",
            "border_radius": "border_radius",
            "line_height": "line_height",
            "max_lines": "max_lines",
        }
        for source_key, target_key in top_level_mappings.items():
            if style.get(target_key) is None and element.get(source_key) is not None:
                style[target_key] = element.get(source_key)
        return style

    @classmethod
    def _normalize_scene_element_text(cls, element: dict[str, Any]) -> str | list[str] | None:
        raw_text = element.get("text")
        if raw_text is None:
            return None
        if isinstance(raw_text, list):
            normalized_list = [
                cls._repair_common_mojibake(cls._coerce_text_value(item)).strip()
                for item in raw_text
                if cls._repair_common_mojibake(cls._coerce_text_value(item)).strip()
            ]
            return normalized_list or None
        if isinstance(raw_text, dict):
            preferred_parts = [
                raw_text.get("headline"),
                raw_text.get("supporting_line"),
                raw_text.get("body"),
                raw_text.get("cta"),
            ]
            normalized_parts = [
                cls._repair_common_mojibake(cls._coerce_text_value(item)).strip()
                for item in preferred_parts
                if cls._repair_common_mojibake(cls._coerce_text_value(item)).strip()
            ]
            if normalized_parts:
                return "\n".join(normalized_parts[:3])
            fallback_text = cls._repair_common_mojibake(cls._coerce_text_value(raw_text)).strip()
            return fallback_text or None
        normalized_text = cls._repair_common_mojibake(cls._coerce_text_value(raw_text)).strip()
        return normalized_text or None

    @classmethod
    def _sanitize_scene_element_asset_payload(
        cls,
        asset_payload: dict[str, Any],
        *,
        element: dict[str, Any],
        request: AIOrchestrationRequest,
    ) -> dict[str, Any] | None:
        payload = cls._coerce_mapping(asset_payload)
        if not payload:
            return None
        role = str(element.get("role") or "").strip().lower()
        element_type = str(element.get("element_type") or "").strip().lower()
        storage_path = str(payload.get("storage_path") or "").strip()
        asset_role = str(payload.get("asset_role") or "").strip().lower()
        if storage_path.casefold() in {"unknown", "none", "null"}:
            storage_path = ""
        matched_asset = None
        if storage_path:
            matched_asset = cls._catalog_asset_by_storage_path(request, storage_path)
        if matched_asset is not None:
            payload = {
                "asset_id": matched_asset.get("asset_id"),
                "asset_role": matched_asset.get("asset_role"),
                "storage_path": matched_asset.get("storage_path"),
                "trust_level": matched_asset.get("trust_level"),
                "variant": payload.get("variant") or matched_asset.get("variant"),
                "notes": payload.get("notes") or matched_asset.get("notes"),
            }
            storage_path = str(payload.get("storage_path") or "").strip()
            asset_role = str(payload.get("asset_role") or "").strip().lower()
        if role == "logo" or asset_role in {"logo", "logo_variant"} or element_type == "logo":
            fallback_logo_path = str(request.logo_asset_path or "").strip()
            if fallback_logo_path and (not storage_path or matched_asset is None):
                payload["storage_path"] = fallback_logo_path
                payload.setdefault("asset_role", "logo")
                payload.setdefault("trust_level", "trusted")
                storage_path = fallback_logo_path
            if not storage_path:
                return None
        is_visual_image_like = (
            role in {"image", "hero_visual", "hero_image", "primary_visual", "supporting_visual", "illustration"}
            or element_type == "image"
        )
        if is_visual_image_like:
            if storage_path and str(storage_path).lower().endswith(".pdf"):
                return None
            if storage_path and matched_asset is None:
                return None
        return payload or None

    @staticmethod
    def _default_scene_element_type(element: dict[str, Any]) -> str:
        role = str(element.get("role") or "").strip().lower()
        asset_role = str(element.get("asset_role") or ((element.get("asset") or {}) if isinstance(element.get("asset"), dict) else {}).get("asset_role") or "").strip().lower()
        if role in {"headline", "supporting_line", "body", "proof_points", "cta", "footer", "legal", "section_label", "stat_highlights"}:
            return "text"
        if role == "logo" or asset_role == "logo":
            return "logo"
        if role in {"image", "hero_image"} or asset_role in {"ai_image", "image", "photo"}:
            return "image"
        if role == "icon" or asset_role == "icon":
            return "icon"
        if role == "background":
            return "background"
        if role in {"decorative_shape", "background_shape", "micro_design_element", "footer_decor"}:
            return "decorative_shape"
        return "text" if element.get("text") is not None else "decorative_shape"

    @classmethod
    def _logo_position_hint_from_payload(
        cls,
        *,
        request: AIOrchestrationRequest,
        text_payload: dict[str, Any],
        creative_decision: CreativeDecisionPayload,
        scene_graph_payload: dict[str, Any],
    ) -> str:
        return cls._effective_logo_position_hint(
            request=request,
            creative_decision=creative_decision,
            text_payload=text_payload,
            scene_graph_payload=scene_graph_payload,
        )

    @classmethod
    def _logo_variant_hint_from_decision(cls, creative_decision: CreativeDecisionPayload) -> str:
        asset_strategy = creative_decision.asset_strategy or {}
        for candidate in (
            asset_strategy.get("logo_variant"),
            asset_strategy.get("logo_variant_type"),
            asset_strategy.get("logo_variant_hint"),
        ):
            normalized = cls._normalize_logo_variant_hint(candidate)
            if normalized:
                return normalized
        return ""

    @classmethod
    def _coerce_logo_geometry_tuple(cls, geometry: Any) -> tuple[float, float, float, float] | None:
        candidate = cls._coerce_mapping(geometry)
        if not candidate:
            return None
        try:
            x = float(candidate.get("x"))
            y = float(candidate.get("y"))
            width = float(candidate.get("width"))
            height = float(candidate.get("height"))
        except (TypeError, ValueError):
            return None
        units = str(candidate.get("units") or "normalized").strip().lower()
        if units != "normalized" and max(abs(x), abs(y), abs(width), abs(height)) > 1.5:
            return None
        if width <= 0 or height <= 0:
            return None
        return (x, y, width, height)

    @classmethod
    def _coerce_canvas_geometry_tuple(
        cls,
        geometry: Any,
        *,
        request: AIOrchestrationRequest,
    ) -> tuple[float, float, float, float] | None:
        candidate = cls._coerce_mapping(geometry)
        if not candidate:
            return None
        try:
            x = float(candidate.get("x"))
            y = float(candidate.get("y"))
            width = float(candidate.get("width"))
            height = float(candidate.get("height"))
        except (TypeError, ValueError):
            return None
        if width <= 0 or height <= 0:
            return None
        units = str(candidate.get("units") or "normalized").strip().lower()
        if units == "normalized" or max(abs(x), abs(y), abs(width), abs(height)) <= 1.5:
            return (x, y, width, height)
        size = request.studio_panel.get("size") if isinstance(request.studio_panel.get("size"), dict) else {}
        canvas_width = max(float(size.get("width") or 1080), 1.0)
        canvas_height = max(float(size.get("height") or 1080), 1.0)
        return (
            x / canvas_width,
            y / canvas_height,
            width / canvas_width,
            height / canvas_height,
        )

    @staticmethod
    def _extract_visual_hierarchy_for_element(
        element: dict[str, Any], visual_context: dict[str, Any]
    ) -> dict[str, Any]:
        """🔥 PHASE 5: Extract visual hierarchy metadata for scene graph element"""
        role = element.get("role", "body")

        # Infer hierarchy level from visual reading order
        visual_hierarchies = visual_context.get("visual_hierarchies", [])
        hierarchy_level = "secondary"
        reading_order_position = None

        if visual_hierarchies:
            hierarchy = visual_hierarchies[0]
            reading_order = hierarchy.get("reading_order", [])
            if isinstance(reading_order, list) and role in reading_order:
                reading_order_position = reading_order.index(role)
                if reading_order_position == 0:
                    hierarchy_level = "primary"
                elif reading_order_position == 1:
                    hierarchy_level = "secondary"
                else:
                    hierarchy_level = "tertiary"

            if hierarchy.get("focal_role") == role:
                hierarchy_level = "primary"

        # Find associated icons
        associated_icons = []
        for pattern in visual_context.get("component_patterns", []):
            patterns_list = pattern.get("patterns", [])
            for p in patterns_list:
                if "icon_text_pairs" in p and role in ["headline", "subheading", "supporting"]:
                    associated_icons.append("icon_suggested")
                    break

        # Determine spatial group
        spatial_group = None
        layout_structures = visual_context.get("layout_structures", [])
        if layout_structures:
            struct = layout_structures[0]
            if struct.get("spatial_groups_count"):
                spatial_group = f"group_{reading_order_position if reading_order_position is not None else 0}"

        return {
            "hierarchy_level": hierarchy_level,
            "reading_order_position": reading_order_position,
            "associated_icons": associated_icons,
            "spatial_group": spatial_group,
        }

    @classmethod
    def _anchor_from_logo_geometry(cls, geometry: tuple[float, float, float, float]) -> str:
        x, y, width, height = geometry
        center_x = x + (width / 2.0)
        center_y = y + (height / 2.0)
        vertical = "top" if center_y <= 0.35 else ("bottom" if center_y >= 0.65 else "middle")
        horizontal = "left" if center_x <= 0.35 else ("right" if center_x >= 0.65 else "center")
        return f"{vertical}-{horizontal}"

    @staticmethod
    def _normalized_rects_overlap(
        first: tuple[float, float, float, float],
        second: tuple[float, float, float, float],
        *,
        gutter: float = 0.0,
    ) -> bool:
        first_left, first_top, first_width, first_height = first
        second_left, second_top, second_width, second_height = second
        first_right = first_left + first_width
        first_bottom = first_top + first_height
        second_right = second_left + second_width
        second_bottom = second_top + second_height
        return not (
            first_right <= (second_left - gutter)
            or second_right <= (first_left - gutter)
            or first_bottom <= (second_top - gutter)
            or second_bottom <= (first_top - gutter)
        )

    @classmethod
    def _repair_text_geometry_for_logo_safe_zone(
        cls,
        *,
        element: dict[str, Any],
        logo_geometry: tuple[float, float, float, float],
        request: AIOrchestrationRequest,
    ) -> dict[str, Any]:
        role = str(element.get("role") or "").strip().lower()
        if role not in {
            "headline",
            "supporting_line",
            "body",
            "proof_points",
            "stat_highlights",
            "section_label",
            "footer",
            "legal",
        }:
            return element
        geometry = cls._coerce_canvas_geometry_tuple(element.get("geometry"), request=request)
        if geometry is None:
            return element

        gutter = 0.02
        if not cls._normalized_rects_overlap(geometry, logo_geometry, gutter=gutter):
            return element

        x, y, width, height = geometry
        logo_x, logo_y, logo_width, logo_height = logo_geometry
        logo_left = max(logo_x - gutter, 0.0)
        logo_top = max(logo_y - gutter, 0.0)
        logo_right = min(logo_x + logo_width + gutter, 1.0)
        logo_bottom = min(logo_y + logo_height + gutter, 1.0)
        min_width = 0.26 if role == "headline" else 0.18
        page_margin = 0.04

        repaired_geometry = {"x": x, "y": y, "width": width, "height": height, "units": "normalized"}

        if x < logo_left:
            width_left = max(logo_left - x, 0.0)
            if width_left >= min_width:
                repaired_geometry["width"] = round(width_left, 4)
                element = dict(element)
                element["geometry"] = repaired_geometry
                validation_hints = cls._coerce_mapping(element.get("validation_hints"))
                validation_hints["avoids_logo_safe_zone"] = True
                element["validation_hints"] = validation_hints
                return element

        space_above = max(logo_top - page_margin, 0.0)
        space_below = max(1.0 - logo_bottom - page_margin, 0.0)
        if space_below >= height and space_below >= space_above:
            repaired_geometry["y"] = round(min(max(logo_bottom, y), 1.0 - page_margin - height), 4)
        elif space_above >= height:
            repaired_geometry["y"] = round(max(page_margin, logo_top - height), 4)
        elif x < logo_left:
            repaired_geometry["width"] = round(max(min_width, min(width, logo_left - x)), 4)
        else:
            repaired_geometry["x"] = round(min(max(page_margin, logo_right), 1.0 - page_margin - min(width, 0.4)), 4)
            repaired_geometry["width"] = round(min(width, 1.0 - repaired_geometry["x"] - page_margin), 4)

        element = dict(element)
        element["geometry"] = repaired_geometry
        validation_hints = cls._coerce_mapping(element.get("validation_hints"))
        validation_hints["avoids_logo_safe_zone"] = True
        element["validation_hints"] = validation_hints
        return element

    @classmethod
    def _finalize_logo_scene_policy(
        cls,
        *,
        scene_graph_payload: dict[str, Any],
        elements: list[dict[str, Any]],
        request: AIOrchestrationRequest,
        text_payload: dict[str, Any],
        creative_decision: CreativeDecisionPayload,
    ) -> list[dict[str, Any]]:
        logo_position_hint = cls._logo_position_hint_from_payload(
            request=request,
            text_payload=text_payload,
            creative_decision=creative_decision,
            scene_graph_payload=scene_graph_payload,
        )
        metadata = text_payload.get("metadata") if isinstance(text_payload.get("metadata"), dict) else {}
        logo_background_tone = cls._resolve_logo_background_tone(
            metadata=metadata,
            creative_decision=creative_decision,
        )
        logo_variant = cls._logo_variant_hint_from_decision(creative_decision)

        scene_graph_payload.setdefault("styles", {})

        # Fix 1: Apply brand background color dynamically (not hardcoded white)
        visual_identity = request.resolved_brand_context.get("visual_identity", {})
        brand_color_palette = visual_identity.get("brand_color_palette", {})
        if isinstance(brand_color_palette, dict) and "background" in brand_color_palette:
            background_color = brand_color_palette["background"]
            if background_color and background_color != "#FFFFFF":  # Only set if not default white
                scene_graph_payload["styles"]["background_fill"] = background_color

        if logo_position_hint:
            scene_graph_payload["styles"]["logo_position"] = logo_position_hint
        scene_graph_payload.setdefault("validation_hints", {})
        if logo_background_tone:
            scene_graph_payload["validation_hints"]["logo_background_tone"] = logo_background_tone
        if logo_position_hint:
            scene_graph_payload["validation_hints"]["logo_position"] = logo_position_hint
        scene_graph_payload["validation_hints"]["logo_overlay_only"] = True

        resolved_logo_geometry = cls._normalize_logo_safe_zone_geometry(
            request=request,
            geometry=None,
            hint=logo_position_hint or None,
        )
        finalized: list[dict[str, Any]] = []
        kept_logo = False
        for element in elements:
            normalized = dict(element)
            role = str(normalized.get("role") or normalized.get("element_type") or "").strip().lower()
            if role != "logo":
                finalized.append(
                    cls._repair_text_geometry_for_logo_safe_zone(
                        element=normalized,
                        logo_geometry=resolved_logo_geometry,
                        request=request,
                    )
                )
                continue
            geometry_tuple = cls._coerce_canvas_geometry_tuple(normalized.get("geometry"), request=request)
            resolved_geometry = cls._normalize_logo_safe_zone_geometry(
                request=request,
                geometry=geometry_tuple,
                hint=logo_position_hint or None,
            )
            resolved_logo_geometry = resolved_geometry
            anchor = cls._anchor_from_logo_geometry(resolved_geometry)
            normalized["geometry"] = {
                "x": round(resolved_geometry[0], 4),
                "y": round(resolved_geometry[1], 4),
                "width": round(resolved_geometry[2], 4),
                "height": round(resolved_geometry[3], 4),
                "units": "normalized",
                "anchor": anchor,
            }
            style = cls._coerce_mapping(normalized.get("style"))
            style.setdefault("fit", "contain")
            if logo_variant:
                style.setdefault("logo_variant", logo_variant)
            if logo_background_tone:
                style.setdefault("logo_background_tone", logo_background_tone)
            normalized["style"] = style
            validation_hints = cls._coerce_mapping(normalized.get("validation_hints"))
            validation_hints["logo_overlay_only"] = True
            validation_hints["logo_safe_zone_required"] = True
            validation_hints["logo_position"] = logo_position_hint or anchor
            if logo_background_tone:
                validation_hints["logo_background_tone"] = logo_background_tone
            if logo_variant:
                validation_hints["logo_variant"] = logo_variant
            normalized["validation_hints"] = validation_hints
            asset_payload = cls._coerce_mapping(normalized.get("asset"))
            asset_payload.setdefault("asset_role", "logo")
            asset_payload.setdefault("trust_level", "trusted")
            if logo_variant:
                asset_payload.setdefault("variant", logo_variant)
            normalized["asset"] = asset_payload
            if not kept_logo:
                finalized.append(normalized)
                kept_logo = True
        if kept_logo:
            finalized = [
                element
                if str(element.get("role") or "").strip().lower() == "logo"
                else cls._repair_text_geometry_for_logo_safe_zone(
                    element=element,
                    logo_geometry=resolved_logo_geometry,
                    request=request,
                )
                for element in finalized
            ]
        return finalized

    @classmethod
    def _inject_legal_disclaimers(
        cls,
        *,
        elements: list[dict[str, Any]],
        request: AIOrchestrationRequest,
        canvas: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Inject legal disclaimers from brand assets as footer elements"""
        # Get brand legal assets from resolved context
        brand_assets = request.resolved_brand_context.get("brand_assets", {})
        legal_disclaimers = brand_assets.get("legal_disclaimers", [])

        if not legal_disclaimers or not isinstance(legal_disclaimers, list):
            return elements

        # Get current format from studio panel
        current_format = request.studio_panel.get("format", "static")
        disclaimer_requested = bool(
            isinstance(request.research_editorial_brief, dict)
            and request.research_editorial_brief.get("disclaimer_requested")
        ) or ("disclaimer" in str(getattr(request, "prompt", "") or "").casefold())

        # Find applicable disclaimers for this format
        applicable_disclaimers = [
            disclaimer
            for disclaimer in legal_disclaimers
            if isinstance(disclaimer, dict)
            and current_format in disclaimer.get("applies_to_formats", [])
        ]

        if not applicable_disclaimers and disclaimer_requested:
            applicable_disclaimers = [
                disclaimer
                for disclaimer in legal_disclaimers
                if isinstance(disclaimer, dict) and str(disclaimer.get("text_template") or "").strip()
            ][:1]

        if not applicable_disclaimers:
            return elements

        # Use the first applicable disclaimer (could be enhanced to handle multiple)
        disclaimer = applicable_disclaimers[0]

        # Check if a legal footer already exists
        has_legal_footer = any(
            str(element.get("role") or "").strip().lower() in {"legal", "footer", "disclaimer"}
            for element in elements
        )

        if has_legal_footer:
            # Don't add duplicate legal footer
            return elements

        # Create legal footer element
        footer_text = disclaimer.get("text_template", "")
        if not footer_text:
            return elements

        # Get canvas dimensions
        canvas_width = canvas.get("width", 1080)
        canvas_height = canvas.get("height", 1080)

        # Position footer at bottom with small margin
        footer_geometry = {
            "x": 0.02,  # 2% margin from left
            "y": 0.96,  # 96% down from top (4% from bottom)
            "width": 0.96,  # 96% width
            "height": 0.03,  # 3% height
            "units": "normalized",
            "anchor": "bottom_left",
        }

        # Get styling from disclaimer
        font_size = int(disclaimer.get("font_size", 8))
        text_color = disclaimer.get("text_color", "#666666")

        # Create footer element
        footer_element = {
            "element_id": "legal_footer",
            "element_type": "text",
            "role": "legal",
            "text": footer_text,
            "geometry": footer_geometry,
            "style": {
                "font_size": font_size,
                "fill": text_color,
                "align": "left",
                "vertical_align": "bottom",
                "font_weight": "normal",
            },
            "visible": True,
            "validation_hints": {
                "legal_compliance": True,
                "required": True,
            },
        }

        # Add footer to elements list
        return [*elements, footer_element]

    @classmethod
    def _apply_cta_template_styling(
        cls,
        *,
        elements: list[dict[str, Any]],
        request: AIOrchestrationRequest,
    ) -> list[dict[str, Any]]:
        """Apply CTA template styling to CTA button elements"""
        # Get brand CTA templates from resolved context
        brand_assets = request.resolved_brand_context.get("brand_assets", {})
        cta_templates = brand_assets.get("cta_templates", [])

        if not cta_templates or not isinstance(cta_templates, list):
            return elements

        # Find default template or use first one
        default_template = next(
            (t for t in cta_templates if isinstance(t, dict) and t.get("is_default")),
            cta_templates[0] if cta_templates else None,
        )

        if not default_template:
            return elements

        # Apply styling to CTA elements
        styled_elements = []
        for element in elements:
            element_copy = dict(element)
            role = str(element_copy.get("role") or "").strip().lower()

            if role == "cta":
                # Apply CTA template styling
                style = cls._coerce_mapping(element_copy.get("style"))

                # Apply button colors
                button_color = default_template.get("button_color")
                button_text_color = default_template.get("button_text_color")
                if button_color:
                    style["background_fill"] = button_color
                if button_text_color:
                    style["fill"] = button_text_color

                # Apply button style (rounded, sharp, pill)
                button_style = default_template.get("button_style", "rounded")
                if button_style == "rounded":
                    style["border_radius"] = 8
                elif button_style == "pill":
                    style["border_radius"] = 999  # Very large radius for pill shape
                elif button_style == "sharp":
                    style["border_radius"] = 0

                # Store icon hint in validation_hints for renderer
                icon_hint = default_template.get("icon_hint")
                if icon_hint:
                    validation_hints = cls._coerce_mapping(element_copy.get("validation_hints"))
                    validation_hints["cta_icon_hint"] = icon_hint
                    element_copy["validation_hints"] = validation_hints

                element_copy["style"] = style

            styled_elements.append(element_copy)

        return styled_elements

    @classmethod
    def _apply_component_motif_patterns(
        cls,
        *,
        elements: list[dict[str, Any]],
        request: AIOrchestrationRequest,
    ) -> list[dict[str, Any]]:
        """Apply component motif patterns from brand visual references (numbered badges, background boxes)"""
        # Get visual references from resolved context
        visual_identity = request.resolved_brand_context.get("visual_identity", {})
        component_motifs = (
            visual_identity.get("component_motifs")
            if isinstance(visual_identity.get("component_motifs"), dict)
            else {}
        )

        if not component_motifs:
            reference_creatives = visual_identity.get("reference_creatives", [])
            if not reference_creatives or not isinstance(reference_creatives, list):
                return elements

            # Fallback: extract component motifs from visual references
            for reference in reference_creatives:
                if not isinstance(reference, dict):
                    continue
                style_chars = reference.get("style_characteristics", {})
                if isinstance(style_chars, dict):
                    motifs = style_chars.get("component_motifs", {})
                    if isinstance(motifs, dict) and motifs:
                        component_motifs.update(motifs)

        if not component_motifs:
            return elements

        # Check for numbered badge pattern
        has_numbered_badges = False
        badge_style = {}

        # Look for numbered badge indicators in component motifs
        # This could be detected by template vision or manually added
        if "numbered_badges" in component_motifs:
            numbered_badge_config = component_motifs["numbered_badges"]
            if isinstance(numbered_badge_config, dict) and numbered_badge_config.get("detected"):
                has_numbered_badges = True
                badge_style = numbered_badge_config

        # Check for background box pattern for subheadings
        has_background_boxes = False
        background_box_style = {}

        if "text_background_boxes" in component_motifs:
            bg_box_config = component_motifs["text_background_boxes"]
            if isinstance(bg_box_config, dict) and bg_box_config.get("detected"):
                has_background_boxes = True
                background_box_style = bg_box_config

        # Apply patterns to elements
        enhanced_elements = []
        for element in elements:
            element_copy = dict(element)
            role = str(element_copy.get("role") or "").strip().lower()

            # Fix 4: Apply numbered badges to list elements
            if has_numbered_badges and role in {"proof_points", "stat_highlights", "list"}:
                validation_hints = cls._coerce_mapping(element_copy.get("validation_hints"))
                validation_hints["uses_numbered_badges"] = True
                # TODO: Load default_badge_color from brand_visual_brief
                default_badge_color = "#F7941D"  # Fallback orange
                validation_hints["badge_style"] = {
                    "shape": badge_style.get("shape", "rounded_rect"),
                    "badge_color": badge_style.get("badge_color", default_badge_color),
                    "text_color": badge_style.get("text_color", "#FFFFFF"),
                    "radius_px": int(badge_style.get("radius_px", 12)),
                    "padding_px": int(badge_style.get("padding_px", 8)),
                    "number_format": badge_style.get("number_format", "01"),
                }
                element_copy["validation_hints"] = validation_hints

            # Fix 5: Apply background boxes to subheadings/supporting lines
            if has_background_boxes and role in {"supporting_line", "subheading", "section_label"}:
                applies_to_roles = background_box_style.get("applies_to_roles", [])
                if not applies_to_roles or role in applies_to_roles:
                    style = cls._coerce_mapping(element_copy.get("style"))

                    # Apply background box color
                    box_color = background_box_style.get("box_color")
                    if box_color:
                        style["background_fill"] = box_color

                    # Apply border radius
                    border_radius = background_box_style.get("border_radius_px")
                    if border_radius:
                        style["background_radius"] = int(border_radius)

                    # Store padding hints
                    padding_x = background_box_style.get("padding_x", 12)
                    padding_y = background_box_style.get("padding_y", 8)
                    validation_hints = cls._coerce_mapping(element_copy.get("validation_hints"))
                    validation_hints["background_box_padding"] = {
                        "x": int(padding_x),
                        "y": int(padding_y),
                    }

                    element_copy["style"] = style
                    element_copy["validation_hints"] = validation_hints

            enhanced_elements.append(element_copy)

        return enhanced_elements

    @classmethod
    def _remap_template_colors_to_brand_palette(
        cls,
        scene_graph: dict[str, Any],
        compiled_context: dict[str, Any],
        planning_hints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Remap template colors to brand palette using brand data (NO HARDCODED COLORS).

        Uses luminance-based semantic role analysis to map template colors to brand colors
        by understanding their purpose (text, background, accent) rather than hardcoded matches.
        """
        brand_color_system = cls._extract_brand_color_system(
            compiled_context,
            planning_hints=planning_hints,
        )
        if not brand_color_system:
            logger.warning("No brand color system found, skipping color remapping")
            return scene_graph

        # Build color mapping using semantic role analysis
        template_colors = cls._extract_template_colors(scene_graph)
        color_mapping = {}

        for template_color in template_colors:
            semantic_role = cls._analyze_color_semantic_role(template_color)
            brand_color = cls._get_brand_color_for_role(semantic_role, brand_color_system)

            if brand_color and template_color.lower() != brand_color.lower():
                color_mapping[template_color.lower()] = brand_color
                logger.info(f"Mapped {template_color} ({semantic_role}) → {brand_color}")

        # Apply mapping to all element styles
        if color_mapping:
            for element in scene_graph.get("elements", []):
                style = element.get("style", {})
                if not isinstance(style, dict):
                    continue
                for key in ("background_color", "fill_color", "text_color", "border_color", "background_fill", "fill"):
                    if key in style and style[key]:
                        color = str(style[key]).lower()
                        if color in color_mapping:
                            old_color = style[key]
                            style[key] = color_mapping[color]
                            logger.info(f"Remapped element '{element.get('role', 'unknown')}' {key} from {old_color} to {color_mapping[color]}")

        return scene_graph

    @classmethod
    def _normalize_palette_roles_color_system(
        cls,
        palette_roles: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(palette_roles, dict):
            return {}

        normalized_palette = {
            str(key).strip().lower(): str(value).strip()
            for key, value in palette_roles.items()
            if str(key).strip() and str(value).strip()
        }
        if not normalized_palette:
            return {}

        primary = normalized_palette.get("primary") or normalized_palette.get("brand_primary")
        secondary = normalized_palette.get("secondary") or normalized_palette.get("brand_secondary")
        accent = (
            normalized_palette.get("accent")
            or normalized_palette.get("highlight")
            or normalized_palette.get("cta")
            or secondary
        )
        background = (
            normalized_palette.get("background")
            or normalized_palette.get("canvas")
            or normalized_palette.get("surface")
        )
        surface = normalized_palette.get("surface") or background
        text = (
            normalized_palette.get("text")
            or normalized_palette.get("foreground")
            or normalized_palette.get("text_primary")
            or primary
        )
        validated_palette: list[str] = []
        for value in (primary, secondary, accent, background, surface, text):
            if value and value not in validated_palette:
                validated_palette.append(value)
        return {
            "primary": primary,
            "secondary": secondary,
            "accent": accent,
            "validated_palette": validated_palette,
            "text_primary": text,
            "text_secondary": normalized_palette.get("text_secondary") or secondary or text,
            "background_light": background,
            "background_dark": normalized_palette.get("background_dark") or primary,
            "neutral_light": normalized_palette.get("neutral_light") or surface or background,
            "neutral_dark": normalized_palette.get("neutral_dark") or normalized_palette.get("text_secondary") or primary,
        }

    @classmethod
    def _extract_brand_color_system(
        cls,
        compiled_context: dict[str, Any],
        *,
        planning_hints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Extract brand color system with semantic roles from brand data."""
        brand_profile = compiled_context.get("brand_profile", {})
        colors = brand_profile.get("colors", {}) if isinstance(brand_profile, dict) else {}
        if not isinstance(colors, dict):
            colors = {}
        if not colors:
            brand_visual_brief = cls._coerce_mapping(compiled_context.get("brand_visual_brief"))
            colors = cls._normalize_palette_roles_color_system(
                cls._coerce_mapping(brand_visual_brief.get("palette_roles"))
            )
        if not colors and isinstance(planning_hints, dict):
            colors = cls._normalize_palette_roles_color_system(
                cls._coerce_mapping(
                    cls._coerce_mapping(planning_hints.get("brand_rule_hints")).get("palette_roles")
                )
            )
        if not colors:
            return {}

        # Extract semantic color roles from brand analysis
        color_system = {
            "primary": colors.get("primary"),
            "secondary": colors.get("secondary"),
            "accent": colors.get("accent"),
            "validated_palette": colors.get("validated_palette", []),
            # Look for semantic roles in brand analysis
            "text_primary": colors.get("text_primary") or colors.get("primary"),
            "text_secondary": colors.get("text_secondary") or colors.get("secondary"),
            "background_light": colors.get("background_light") or colors.get("background_primary"),
            "background_dark": colors.get("background_dark") or colors.get("primary"),
            "neutral_light": colors.get("neutral_light"),
            "neutral_dark": colors.get("neutral_dark"),
        }

        # Filter out None values
        color_system = {k: v for k, v in color_system.items() if v}

        # Calculate luminance for each color for intelligent matching
        for key, color_value in list(color_system.items()):
            if key != "validated_palette" and isinstance(color_value, str):
                try:
                    color_system[f"{key}_luminance"] = cls._calculate_color_luminance(color_value)
                except Exception:
                    pass

        return color_system

    @classmethod
    def _analyze_color_semantic_role(cls, color_hex: str) -> str:
        """Analyze what semantic role a template color likely serves based on luminance."""
        try:
            luminance = cls._calculate_color_luminance(color_hex)
        except Exception:
            return "accent"  # Default fallback

        # Classify based on luminance and common patterns
        if luminance > 0.9:
            return "background_light"  # Very light colors → light backgrounds
        elif luminance > 0.7:
            return "neutral_light"  # Light neutrals → subtle backgrounds/borders
        elif luminance < 0.1:
            return "text_primary"  # Very dark colors → primary text
        elif luminance < 0.3:
            return "text_secondary"  # Dark colors → secondary text or dark backgrounds
        elif luminance < 0.5:
            return "neutral_dark"  # Medium-dark → neutral elements
        else:
            return "accent"  # Mid-range colors → accents/highlights

    @classmethod
    def _calculate_color_luminance(cls, color_hex: str) -> float:
        """Calculate relative luminance of a color (0.0 = black, 1.0 = white)."""
        # Remove # prefix
        hex_color = str(color_hex).lstrip("#").strip()

        # Convert to RGB
        try:
            r = int(hex_color[0:2], 16) / 255.0
            g = int(hex_color[2:4], 16) / 255.0
            b = int(hex_color[4:6], 16) / 255.0
        except (ValueError, IndexError):
            return 0.5  # Default to mid-range if parsing fails

        # Calculate relative luminance using standard formula
        def linearize(channel):
            if channel <= 0.03928:
                return channel / 12.92
            return ((channel + 0.055) / 1.055) ** 2.4

        r_lin = linearize(r)
        g_lin = linearize(g)
        b_lin = linearize(b)

        return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin

    @classmethod
    def _get_brand_color_for_role(cls, semantic_role: str, brand_color_system: dict[str, Any]) -> str | None:
        """Get brand color for a semantic role, with fallbacks from brand data."""
        # Direct match
        if semantic_role in brand_color_system:
            return brand_color_system[semantic_role]

        # Fallback logic based on role (using brand data only)
        fallback_chain = {
            "text_primary": ["text_primary", "primary", "validated_palette[0]"],
            "text_secondary": ["text_secondary", "secondary", "primary"],
            "background_light": ["background_light", "validated_palette[-1]", "accent"],
            "background_dark": ["background_dark", "primary"],
            "neutral_light": ["neutral_light", "background_light", "accent"],
            "neutral_dark": ["neutral_dark", "text_secondary", "primary"],
            "accent": ["accent", "secondary"],
        }

        for fallback_key in fallback_chain.get(semantic_role, []):
            if fallback_key.startswith("validated_palette["):
                # Extract from palette array
                palette = brand_color_system.get("validated_palette", [])
                if not isinstance(palette, list):
                    continue
                try:
                    if "[0]" in fallback_key and palette:
                        return palette[0]
                    elif "[-1]" in fallback_key and palette:
                        return palette[-1]
                except IndexError:
                    continue
            elif fallback_key in brand_color_system:
                return brand_color_system[fallback_key]

        # Last resort: first color in validated palette
        validated = brand_color_system.get("validated_palette", [])
        if isinstance(validated, list) and validated:
            return validated[0]

        return None

    @classmethod
    def _extract_brand_palette(cls, compiled_context: dict[str, Any]) -> list[str]:
        """Extract validated brand colors from context."""
        brand_profile = compiled_context.get("brand_profile", {})
        if not isinstance(brand_profile, dict):
            return []

        colors = brand_profile.get("colors", {})
        if not isinstance(colors, dict):
            return []

        validated_colors = colors.get("validated_palette", [])

        if not validated_colors or not isinstance(validated_colors, list):
            # Fallback to primary/secondary colors
            validated_colors = [
                colors.get("primary"),
                colors.get("secondary"),
                colors.get("accent"),
            ]
            validated_colors = [str(c).strip().upper() for c in validated_colors if c]

        return [str(c).strip().upper() for c in validated_colors if c]

    @classmethod
    def _extract_template_colors(cls, scene_graph: dict[str, Any]) -> set[str]:
        """Extract all colors used in scene graph."""
        colors = set()
        for element in scene_graph.get("elements", []):
            if not isinstance(element, dict):
                continue
            style = element.get("style", {})
            if not isinstance(style, dict):
                continue
            for key in ("background_color", "fill_color", "text_color", "border_color", "background_fill", "fill"):
                if key in style and style[key]:
                    colors.add(str(style[key]).strip())
        return colors

    @classmethod
    def _apply_design_system_scene_defaults(
        cls,
        *,
        scene_graph_payload: dict[str, Any],
        request: AIOrchestrationRequest,
    ) -> dict[str, Any]:
        payload = dict(scene_graph_payload)
        visual_identity = request.resolved_brand_context.get("visual_identity", {})
        if not isinstance(visual_identity, dict):
            return payload

        design_system = visual_identity.get("design_system", {})
        if not isinstance(design_system, dict):
            design_system = {}

        styles = cls._coerce_mapping(payload.get("styles"))
        background_style = (
            visual_identity.get("background_style")
            if isinstance(visual_identity.get("background_style"), dict)
            else (design_system.get("background_style", {}) if isinstance(design_system.get("background_style"), dict) else {})
        )
        if background_style:
            primary_hex = str(background_style.get("primary_hex") or "").strip()
            if primary_hex and not styles.get("background_fill"):
                styles["background_fill"] = primary_hex
            background_type = str(background_style.get("type") or background_style.get("dominant_mode") or "").strip()
            if background_type and not styles.get("background_style"):
                styles["background_style"] = background_type

        gradient_preferences = (
            visual_identity.get("gradient_preferences")
            if isinstance(visual_identity.get("gradient_preferences"), list)
            else (design_system.get("gradient_preferences", []) if isinstance(design_system.get("gradient_preferences"), list) else [])
        )
        first_gradient = next((item for item in gradient_preferences if isinstance(item, dict)), None)
        if first_gradient:
            if first_gradient.get("start_color") and not styles.get("gradient_from"):
                styles["gradient_from"] = first_gradient.get("start_color")
            if first_gradient.get("end_color") and not styles.get("gradient_to"):
                styles["gradient_to"] = first_gradient.get("end_color")

        promoted_logo_position = cls._normalize_logo_position_option(
            visual_identity.get("logo_position") or design_system.get("logo_anchor")
        )
        if promoted_logo_position and not styles.get("logo_position"):
            styles["logo_position"] = promoted_logo_position

        payload["styles"] = styles

        hierarchy = design_system.get("visual_hierarchy", {}) if isinstance(design_system.get("visual_hierarchy"), dict) else {}
        content_structure = design_system.get("content_structure", {}) if isinstance(design_system.get("content_structure"), dict) else {}
        image_treatment = design_system.get("image_treatment", {}) if isinstance(design_system.get("image_treatment"), dict) else {}
        visual_craft = design_system.get("visual_craft", {}) if isinstance(design_system.get("visual_craft"), dict) else {}
        composition_logic = design_system.get("composition_logic", {}) if isinstance(design_system.get("composition_logic"), dict) else {}
        subject_semantics = design_system.get("subject_semantics", {}) if isinstance(design_system.get("subject_semantics"), dict) else {}
        layout_preferences = design_system.get("layout_preferences", {}) if isinstance(design_system.get("layout_preferences"), dict) else {}

        focal_roles = {
            str(item).strip().lower()
            for item in (hierarchy.get("focal_roles") or [])
            if str(item).strip()
        }
        density_preference = str(((hierarchy.get("density_preferences") or [None])[0]) or "").strip().lower()
        whitespace_preference = str(((hierarchy.get("whitespace_preferences") or [None])[0]) or "").strip().lower()
        storytelling_mode = str(((content_structure.get("storytelling_modes") or [None])[0]) or "").strip().lower()
        cta_prominence = str(content_structure.get("cta_prominence") or "").strip().lower()
        preferred_zone_roles = {
            str(item).strip().lower()
            for item in (layout_preferences.get("preferred_zone_roles") or [])
            if str(item).strip()
        }
        image_styles = {
            str(item).strip().lower()
            for item in (image_treatment.get("styles") or [])
            if str(item).strip()
        }
        craft_depth = str(((visual_craft.get("depth_styles") or [None])[0]) or "").strip().lower()
        craft_rendering = str(((visual_craft.get("rendering_styles") or [None])[0]) or "").strip().lower()
        craft_lighting = str(((visual_craft.get("lighting_modes") or [None])[0]) or "").strip().lower()
        craft_polish = str(((visual_craft.get("polish_levels") or [None])[0]) or "").strip().lower()
        composition_balance = str(((composition_logic.get("balances") or [None])[0]) or "").strip().lower()
        composition_framing = str(((composition_logic.get("framings") or [None])[0]) or "").strip().lower()
        composition_layering = str(((composition_logic.get("layerings") or [None])[0]) or "").strip().lower()
        subject_scene_type = str(((subject_semantics.get("scene_types") or [None])[0]) or "").strip().lower()
        subject_abstraction = str(((subject_semantics.get("abstraction_levels") or [None])[0]) or "").strip().lower()
        subject_primary = [str(item).strip().lower() for item in (subject_semantics.get("primary_subjects") or []) if str(item).strip()][:4]
        subject_financial = [str(item).strip().lower() for item in (subject_semantics.get("financial_objects") or []) if str(item).strip()][:4]

        normalized_elements: list[dict[str, Any]] = []
        for element in cls._coerce_list(payload.get("elements")):
            if not isinstance(element, dict):
                normalized_elements.append(element)
                continue
            element_copy = dict(element)
            role = str(element_copy.get("role") or "").strip().lower()
            validation_hints = cls._coerce_mapping(element_copy.get("validation_hints"))
            style = cls._coerce_mapping(element_copy.get("style"))

            if role and role in focal_roles:
                validation_hints["brand_focal_role"] = True
            if density_preference and role in {"headline", "supporting_line", "body", "proof_points", "stat_highlights", "image"}:
                validation_hints.setdefault("design_density", density_preference)
            if whitespace_preference and role in {"headline", "supporting_line", "body", "proof_points", "image"}:
                validation_hints.setdefault("design_whitespace", whitespace_preference)
            if storytelling_mode and role in {"body", "proof_points", "stat_highlights", "section_label"}:
                validation_hints.setdefault("storytelling_mode", storytelling_mode)
            if cta_prominence and role == "cta":
                validation_hints.setdefault("cta_prominence", cta_prominence)
                if cta_prominence == "low":
                    style.setdefault("font_size", 22)
            if role in preferred_zone_roles:
                validation_hints.setdefault("preferred_zone_role", True)
            if image_styles and role == "image":
                validation_hints.setdefault("image_treatment_styles", sorted(image_styles))
                if craft_depth:
                    validation_hints.setdefault("visual_depth_style", craft_depth)
                if craft_rendering:
                    validation_hints.setdefault("visual_rendering_style", craft_rendering)
                if craft_lighting:
                    validation_hints.setdefault("visual_lighting_mode", craft_lighting)
                if craft_polish:
                    validation_hints.setdefault("visual_polish_level", craft_polish)
                if composition_balance:
                    validation_hints.setdefault("composition_balance", composition_balance)
                if composition_framing:
                    validation_hints.setdefault("composition_framing", composition_framing)
                if composition_layering:
                    validation_hints.setdefault("composition_layering", composition_layering)
                if subject_scene_type:
                    validation_hints.setdefault("subject_scene_type", subject_scene_type)
                if subject_abstraction:
                    validation_hints.setdefault("subject_abstraction_level", subject_abstraction)
                if subject_primary:
                    validation_hints.setdefault("primary_subjects", subject_primary)
                if subject_financial:
                    validation_hints.setdefault("financial_objects", subject_financial)

            if role == "background" and background_style:
                if background_style.get("primary_hex") and not style.get("background_fill"):
                    style["background_fill"] = background_style.get("primary_hex")
                if first_gradient and first_gradient.get("start_color") and first_gradient.get("end_color"):
                    style.setdefault("gradient_from", first_gradient.get("start_color"))
                    style.setdefault("gradient_to", first_gradient.get("end_color"))

            if validation_hints:
                element_copy["validation_hints"] = validation_hints
            if style:
                element_copy["style"] = style
            normalized_elements.append(element_copy)

        payload["elements"] = normalized_elements
        return payload

    @staticmethod
    def _design_system_prompt_guidance(visual_identity: dict[str, Any]) -> dict[str, str]:
        design_system = visual_identity.get("design_system", {}) if isinstance(visual_identity.get("design_system"), dict) else {}
        background_style = visual_identity.get("background_style") if isinstance(visual_identity.get("background_style"), dict) else (
            design_system.get("background_style", {}) if isinstance(design_system.get("background_style"), dict) else {}
        )
        component_motifs = visual_identity.get("component_motifs") if isinstance(visual_identity.get("component_motifs"), dict) else (
            design_system.get("component_motifs", {}) if isinstance(design_system.get("component_motifs"), dict) else {}
        )
        layout_preferences = design_system.get("layout_preferences", {}) if isinstance(design_system.get("layout_preferences"), dict) else {}
        hierarchy = design_system.get("visual_hierarchy", {}) if isinstance(design_system.get("visual_hierarchy"), dict) else {}
        content_structure = design_system.get("content_structure", {}) if isinstance(design_system.get("content_structure"), dict) else {}
        image_treatment = design_system.get("image_treatment", {}) if isinstance(design_system.get("image_treatment"), dict) else {}
        visual_craft = design_system.get("visual_craft", {}) if isinstance(design_system.get("visual_craft"), dict) else {}
        composition_logic = design_system.get("composition_logic", {}) if isinstance(design_system.get("composition_logic"), dict) else {}
        subject_semantics = design_system.get("subject_semantics", {}) if isinstance(design_system.get("subject_semantics"), dict) else {}
        editorial_patterns = design_system.get("editorial_patterns", {}) if isinstance(design_system.get("editorial_patterns"), dict) else {}
        brand_cues = design_system.get("brand_cues", {}) if isinstance(design_system.get("brand_cues"), dict) else {}

        motif_names = [str(key).replace("_", " ") for key, value in component_motifs.items() if value]
        return {
            "layout": AIOrchestratorService._normalize_metadata_text(
                layout_preferences.get("dominant") or ", ".join(str(item) for item in (layout_preferences.get("common") or [])[:3]),
                limit=120,
            ),
            "zones": AIOrchestratorService._normalize_metadata_text(
                ", ".join(str(item) for item in (layout_preferences.get("preferred_zone_roles") or [])[:6]),
                limit=140,
            ),
            "background": AIOrchestratorService._normalize_metadata_text(
                ", ".join(
                    part for part in [
                        str(background_style.get("type") or background_style.get("dominant_mode") or "").strip(),
                        str(background_style.get("primary_hex") or "").strip(),
                    ] if part
                ),
                limit=120,
            ),
            "motifs": AIOrchestratorService._normalize_metadata_text(", ".join(motif_names[:5]), limit=140),
            "hierarchy": AIOrchestratorService._normalize_metadata_text(
                ", ".join(
                    str(item)
                    for item in [
                        *((hierarchy.get("focal_roles") or [])[:2]),
                        *((hierarchy.get("density_preferences") or [])[:1]),
                        *((hierarchy.get("whitespace_preferences") or [])[:1]),
                    ]
                    if str(item).strip()
                ),
                limit=140,
            ),
            "content_structure": AIOrchestratorService._normalize_metadata_text(
                ", ".join(
                    str(item)
                    for item in [
                        *((content_structure.get("storytelling_modes") or [])[:2]),
                        content_structure.get("cta_prominence"),
                    ]
                    if str(item).strip()
                ),
                limit=140,
            ),
            "image_treatment": AIOrchestratorService._normalize_metadata_text(
                ", ".join(str(item) for item in (image_treatment.get("styles") or [])[:3]),
                limit=120,
            ),
            "visual_craft": AIOrchestratorService._normalize_metadata_text(
                ", ".join(
                    str(item)
                    for item in [
                        *((visual_craft.get("depth_styles") or [])[:2]),
                        *((visual_craft.get("rendering_styles") or [])[:2]),
                        *((visual_craft.get("lighting_modes") or [])[:1]),
                        *((visual_craft.get("polish_levels") or [])[:1]),
                    ]
                    if str(item).strip()
                ),
                limit=160,
            ),
            "composition": AIOrchestratorService._normalize_metadata_text(
                ", ".join(
                    str(item)
                    for item in [
                        *((composition_logic.get("balances") or [])[:2]),
                        *((composition_logic.get("framings") or [])[:2]),
                        *((composition_logic.get("layerings") or [])[:1]),
                    ]
                    if str(item).strip()
                ),
                limit=160,
            ),
            "subjects": AIOrchestratorService._normalize_metadata_text(
                ", ".join(
                    str(item)
                    for item in [
                        *((subject_semantics.get("scene_types") or [])[:2]),
                        *((subject_semantics.get("primary_subjects") or [])[:3]),
                        *((subject_semantics.get("financial_objects") or [])[:3]),
                        *((subject_semantics.get("abstraction_levels") or [])[:1]),
                    ]
                    if str(item).strip()
                ),
                limit=180,
            ),
            "editorial": AIOrchestratorService._normalize_metadata_text(
                ", ".join(
                    str(item)
                    for item in [
                        *(((editorial_patterns.get("carousel") or {}).get("dominant_story_arc") or [])[:3]),
                        *(((editorial_patterns.get("infographic") or {}).get("dominant_story_arc") or [])[:2]),
                        *(((editorial_patterns.get("static") or {}).get("dominant_story_arc") or [])[:2]),
                    ]
                    if str(item).strip()
                ),
                limit=180,
            ),
            "brand_cues": AIOrchestratorService._normalize_metadata_text(
                ", ".join(
                    str(item)
                    for item in [
                        *((brand_cues.get("tone_keywords") or [])[:3]),
                        *((brand_cues.get("trust_markers") or [])[:3]),
                    ]
                    if str(item).strip()
                ),
                limit=160,
            ),
            "logo_position": AIOrchestratorService._normalize_metadata_text(
                visual_identity.get("logo_position") or design_system.get("logo_anchor"),
                limit=40,
            ),
        }

    @staticmethod
    def _normalize_logo_variant_hint(variant_hint: Any) -> str:
        text = str(variant_hint or "").strip().casefold()
        if not text:
            return ""
        replacements = {
            "dark on light": "dark_on_light",
            "light on dark": "light_on_dark",
            "full color": "dark_on_light",
            "full-colour": "dark_on_light",
            "full colour": "dark_on_light",
            "reverse": "light_on_dark",
            "inverse": "light_on_dark",
            "negative": "light_on_dark",
            "vertical": "stacked",
            "lockup": "horizontal",
            "brandmark": "icon_only",
            "icon only": "icon_only",
            "compact": "icon_only",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return re.sub(r"[^a-z0-9_]+", "_", text).strip("_")

    @classmethod
    def _requested_logo_variant(
        cls,
        creative_decision: CreativeDecisionPayload,
        scene_graph: GenerationSceneGraph,
    ) -> str | None:
        asset_strategy = creative_decision.asset_strategy or {}
        candidate_values: list[Any] = [
            asset_strategy.get("logo_variant"),
            asset_strategy.get("logo_variant_type"),
            asset_strategy.get("logo_variant_hint"),
        ]
        logo_preferences = asset_strategy.get("logo_preferences")
        if isinstance(logo_preferences, dict):
            candidate_values.extend(
                [
                    logo_preferences.get("variant"),
                    logo_preferences.get("type"),
                    logo_preferences.get("background_variant"),
                ]
            )
        for element in scene_graph.elements:
            if element.role != "logo":
                continue
            if element.asset is not None:
                candidate_values.extend(
                    [
                        element.asset.variant,
                        element.asset.notes,
                    ]
                )
            candidate_values.extend(
                [
                    (element.style or {}).get("logo_variant"),
                    (element.validation_hints or {}).get("logo_variant"),
                ]
            )
        for value in candidate_values:
            normalized = cls._normalize_logo_variant_hint(value)
            if normalized:
                return normalized
        return None

    @classmethod
    def _score_logo_candidate_for_hint(cls, candidate: dict[str, Any], variant_hint: str) -> int:
        normalized_hint = cls._normalize_logo_variant_hint(variant_hint)
        score = int(candidate.get("source_priority") or 0)
        traits = candidate.get("traits", {}) or {}
        orientation = str(traits.get("orientation") or "flex")
        background_variant = str(traits.get("background_variant") or "")
        trust_level = str(candidate.get("trust_level") or "").strip().lower()
        if trust_level == "trusted":
            score += 4
        elif trust_level in {"usable_with_warning", "usable-with-warning"}:
            score += 1
        elif trust_level == "excluded":
            return -10_000

        if "dark_on_light" in normalized_hint:
            if background_variant == "light":
                score += 18
            elif background_variant == "dark":
                score -= 10
        if "light_on_dark" in normalized_hint:
            if background_variant == "dark":
                score += 18
            elif background_variant == "light":
                score -= 10
        if "horizontal" in normalized_hint or "wordmark" in normalized_hint:
            score += 16 if orientation == "horizontal" else -8
        if "stacked" in normalized_hint:
            score += 16 if orientation == "stacked" else -8
        if "icon_only" in normalized_hint:
            score += 14 if orientation == "icon" else -6
        return score

    @classmethod
    def _select_logo_candidate_for_render(
        cls,
        request: AIOrchestrationRequest,
        creative_decision: CreativeDecisionPayload,
        scene_graph: GenerationSceneGraph,
    ) -> tuple[str | None, str | None]:
        candidates = list(request.logo_asset_candidates or [])
        if not candidates:
            fallback_path = str(request.logo_asset_path or "").strip() or None
            return fallback_path, None

        requested_variant = cls._requested_logo_variant(creative_decision, scene_graph)
        if not requested_variant:
            fallback_path = str(request.logo_asset_path or "").strip() or None
            return fallback_path, None

        scored_candidates = sorted(
            candidates,
            key=lambda item: (
                cls._score_logo_candidate_for_hint(item, requested_variant),
                int(item.get("source_priority") or 0),
                str(item.get("storage_path") or ""),
            ),
            reverse=True,
        )
        selected_path = str(scored_candidates[0].get("storage_path") or "").strip() or None
        fallback_path = str(request.logo_asset_path or "").strip() or None
        if not selected_path:
            return fallback_path, requested_variant
        return selected_path, requested_variant

    @staticmethod
    def _reference_image_limit(studio_panel: dict[str, Any]) -> int:
        format_name = str(studio_panel.get("format") or "static").strip().lower()
        if format_name == "carousel":
            return 4
        if format_name in {"pdf", "doc"}:
            return 4
        if format_name == "infographic":
            return 2
        return 1

    @staticmethod
    def _asset_label_text(asset: dict[str, Any]) -> str:
        metadata = asset.get("metadata") if isinstance(asset, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        parts = [
            asset.get("asset_role"),
            asset.get("mime_type"),
            metadata.get("label"),
            metadata.get("name"),
            metadata.get("review_class"),
            metadata.get("review_reason"),
            asset.get("storage_path"),
        ]
        return " ".join(str(part).strip() for part in parts if str(part or "").strip()).casefold()

    @classmethod
    def _reference_asset_display_label(cls, asset: dict[str, Any]) -> str:
        metadata = cls._asset_metadata(asset)
        storage_path = str(asset.get("storage_path") or "").strip()
        filename = storage_path.replace("\\", "/").rsplit("/", 1)[-1]
        stem = filename.rsplit(".", 1)[0] if "." in filename else filename
        return cls._normalize_metadata_text(
            asset.get("label")
            or asset.get("name")
            or metadata.get("label")
            or metadata.get("name")
            or metadata.get("title")
            or stem
            or asset.get("asset_role")
            or asset.get("mime_type"),
            limit=72,
        )

    @classmethod
    def _reference_asset_is_visual_source(cls, asset: dict[str, Any]) -> bool:
        if not isinstance(asset, dict):
            return False
        mime_type = str(asset.get("mime_type") or "").strip().lower()
        if not (mime_type.startswith("image/") or mime_type == "application/pdf"):
            return False
        trust_level = str(asset.get("trust_level") or "").strip().lower()
        if trust_level in {"excluded", "reference_only"}:
            return False
        asset_role = str(asset.get("asset_role") or "").strip().lower()
        if asset_role in {"logo", "logo_variant"}:
            return False
        label_text = cls._asset_label_text(asset)
        if any(token in label_text for token in ("logo", "wordmark", "brandmark", "lockup", "emblem")):
            return False
        return True

    @classmethod
    def _reference_asset_topic_tokens(cls, asset: dict[str, Any]) -> set[str]:
        metadata = cls._asset_metadata(asset)
        parts: list[str] = [
            cls._asset_label_text(asset),
            str(metadata.get("summary") or ""),
            str(metadata.get("description") or ""),
            str(metadata.get("tags") or ""),
        ]
        tokens = set(cls._normalized_prompt_tokens(" ".join(parts)))
        return {
            token
            for token in tokens
            if len(token) >= 3
            and any(ch.isalpha() for ch in token)
            and token not in cls.TOPIC_MATCH_NOISE_TOKENS
            and not re.fullmatch(r"[a-f0-9]{8,}", token)
        }

    @classmethod
    def _request_topic_tokens(cls, request: AIOrchestrationRequest | None) -> set[str]:
        if request is None:
            return set()
        parts = [
            str(request.prompt or ""),
            json.dumps(request.research_editorial_brief or {}, default=str),
            json.dumps(request.objective_context or {}, default=str),
        ]
        tokens = set(cls._normalized_prompt_tokens(" ".join(parts)))
        generic = {
            "linkedin",
            "carousel",
            "slide",
            "slides",
            "tone",
            "short",
            "scannable",
            "conversational",
            "analytical",
            "intelligent",
            "brand",
            "jiraaf",
            "platform",
            "finance",
            "investment",
            "investments",
            "alternative",
            "indian",
        } | cls.TOPIC_MATCH_NOISE_TOKENS
        return {
            token
            for token in tokens
            if len(token) >= 3
            and any(ch.isalpha() for ch in token)
            and not any(ch.isdigit() for ch in token)
            and token not in generic
            and not re.fullmatch(r"[a-f0-9]{8,}", token)
        }

    @staticmethod
    def _brand_subject_focus_terms(
        request: AIOrchestrationRequest | None,
        *,
        limit: int = 6,
    ) -> list[str]:
        if request is None:
            return []
        visual_identity = (
            request.resolved_brand_context.get("visual_identity", {})
            if isinstance(request.resolved_brand_context, dict)
            else {}
        )
        if not isinstance(visual_identity, dict):
            visual_identity = {}
        design_system = visual_identity.get("design_system") if isinstance(visual_identity.get("design_system"), dict) else {}
        subject_semantics = design_system.get("subject_semantics") if isinstance(design_system.get("subject_semantics"), dict) else {}
        values: list[Any] = [
            visual_identity.get("subject_semantics_summary"),
            visual_identity.get("image_treatment_summary"),
            visual_identity.get("content_structure_summary"),
            subject_semantics.get("scene_types"),
            subject_semantics.get("primary_subjects"),
            subject_semantics.get("financial_objects"),
            subject_semantics.get("domain_cues"),
        ]
        terms: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized_value = value
            if isinstance(value, (list, tuple, set, dict)):
                normalized_value = json.dumps(value, default=str)
            for token in AIOrchestratorService._normalized_prompt_tokens(str(normalized_value or "")):
                if (
                    len(token) < 4
                    or token in AIOrchestratorService.TOPIC_MATCH_NOISE_TOKENS
                    or token in seen
                    or any(ch.isdigit() for ch in token)
                ):
                    continue
                seen.add(token)
                terms.append(token)
                if len(terms) >= limit:
                    return terms
        return terms

    @classmethod
    def _reference_asset_topic_score(
        cls,
        asset: dict[str, Any],
        *,
        request: AIOrchestrationRequest | None,
    ) -> int:
        request_tokens = cls._request_topic_tokens(request)
        if not request_tokens:
            return 0
        asset_tokens = cls._reference_asset_topic_tokens(asset)
        overlap = request_tokens & asset_tokens
        if not overlap:
            return 0
        high_signal = {
            "fta",
            "trade",
            "tariff",
            "tariffs",
            "exports",
            "export",
            "zealand",
            "agreement",
            "services",
            "visa",
            "bilateral",
        }
        high_signal_overlap = overlap & high_signal
        score = (len(high_signal_overlap) * 30) + ((len(overlap) - len(high_signal_overlap)) * 4)
        if str(asset.get("mime_type") or "").strip().lower() == "application/pdf":
            score += 4
        return score

    @classmethod
    def _topic_relevant_reference_assets(
        cls,
        request: AIOrchestrationRequest | None,
        *,
        creative_decision: CreativeDecisionPayload | None,
        source_assets: list[dict[str, Any]] | None = None,
        limit: int = 2,
    ) -> list[dict[str, Any]]:
        if request is None:
            return []
        raw_assets = source_assets or request.asset_catalog or request.reference_assets or []
        scored: list[tuple[int, dict[str, Any]]] = []
        for asset in raw_assets:
            if not isinstance(asset, dict) or not cls._reference_asset_is_visual_source(asset):
                continue
            score = cls._reference_asset_topic_score(asset, request=request)
            if score <= 0:
                continue
            scored.append((score, dict(asset)))
        if not scored:
            return []
        scored.sort(
            key=lambda item: (
                item[0],
                str(item[1].get("trust_level") or "").strip().lower() == "trusted",
                str(item[1].get("storage_path") or ""),
            ),
            reverse=True,
        )
        top_score = scored[0][0]
        if top_score >= 30:
            topic_floor = max(30, int(top_score * 0.6))
            scored = [item for item in scored if item[0] >= topic_floor]
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for _score, asset in scored:
            storage_path = str(asset.get("storage_path") or "").strip()
            if not storage_path or storage_path in seen:
                continue
            seen.add(storage_path)
            selected.append(asset)
            if len(selected) >= limit:
                break
        return selected

    @classmethod
    def _reference_topic_alignment_issue(
        cls,
        request: AIOrchestrationRequest,
        selected_reference_images: list[dict[str, Any]],
    ) -> str:
        selected_scores = [
            cls._reference_asset_topic_score(asset, request=request)
            for asset in selected_reference_images
            if isinstance(asset, dict)
        ]
        best_selected_score = max(selected_scores or [0])
        candidate_scores = [
            cls._reference_asset_topic_score(asset, request=request)
            for asset in (request.asset_catalog or request.reference_assets or [])
            if isinstance(asset, dict) and cls._reference_asset_is_visual_source(asset)
        ]
        best_available_score = max(candidate_scores or [0])
        if best_available_score < 30:
            return ""
        if best_selected_score <= 0:
            return "reference_topic_mismatch"
        if best_selected_score < int(best_available_score * 0.75):
            return "reference_topic_mismatch"
        return ""

    @staticmethod
    def _merge_reference_asset_lists(*groups: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for group in groups:
            for asset in group or []:
                if not isinstance(asset, dict):
                    continue
                storage_path = str(asset.get("storage_path") or "").strip()
                if not storage_path or storage_path in seen:
                    continue
                seen.add(storage_path)
                merged.append(dict(asset))
        return merged

    @classmethod
    def _asset_metadata(cls, asset: dict[str, Any]) -> dict[str, Any]:
        metadata = asset.get("metadata") if isinstance(asset, dict) else {}
        return metadata if isinstance(metadata, dict) else {}

    @classmethod
    def _asset_logo_cue_text(cls, asset: dict[str, Any]) -> str:
        metadata = cls._asset_metadata(asset)
        parts: list[str] = [cls._asset_label_text(asset)]
        skip_value_keys = {
            "brand",
            "brand_name",
            "brandname",
            "tenant",
            "tenant_name",
            "owner",
            "summary",
            "style_summary",
            "structure_summary",
            "content",
            "layout_structure",
            "reusable_zones",
            "editable_zones",
            "zones",
            "design_system",
        }

        def collect(value: Any, *, key: str = "", depth: int = 0) -> None:
            if depth > 4:
                return
            if isinstance(value, dict):
                for child_key, child_value in value.items():
                    child_key_text = str(child_key or "").strip().casefold()
                    if child_key_text:
                        parts.append(child_key_text)
                    if child_key_text in skip_value_keys:
                        continue
                    collect(child_value, key=child_key_text, depth=depth + 1)
                return
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    collect(item, key=key, depth=depth + 1)
                return
            text = str(value or "").strip()
            if text:
                parts.append(text.casefold())

        collect(metadata)
        analysis = asset.get("analysis") if isinstance(asset, dict) else None
        collect(analysis, key="analysis")
        return " ".join(parts)

    @classmethod
    def _reference_image_has_logo_cue(cls, asset: dict[str, Any]) -> bool:
        asset_role = str(asset.get("asset_role") or "").strip().casefold()
        if asset_role in {"logo", "logo_variant"}:
            return True
        metadata = cls._asset_metadata(asset)
        normalized_metadata = metadata.get("normalized_metadata")
        normalized_metadata = normalized_metadata if isinstance(normalized_metadata, dict) else {}
        source_metadata = metadata.get("source_metadata")
        source_metadata = source_metadata if isinstance(source_metadata, dict) else {}
        analysis = asset.get("analysis") if isinstance(asset.get("analysis"), dict) else {}
        explicit_logo_classes = {
            str(asset.get("review_class") or "").strip().casefold(),
            str(asset.get("asset_kind") or "").strip().casefold(),
            str(metadata.get("review_class") or "").strip().casefold(),
            str(metadata.get("asset_kind") or "").strip().casefold(),
            str(normalized_metadata.get("review_class") or "").strip().casefold(),
            str(source_metadata.get("review_class") or "").strip().casefold(),
            str(source_metadata.get("origin_category") or "").strip().casefold(),
        }
        if explicit_logo_classes & {"logo", "logo_variant", "wordmark", "brandmark"}:
            return True
        for candidate in (
            metadata.get("contains_logo"),
            metadata.get("logo_detected"),
            metadata.get("watermark_detected"),
            normalized_metadata.get("contains_logo"),
            normalized_metadata.get("logo_detected"),
            source_metadata.get("contains_logo"),
            source_metadata.get("logo_detected"),
            analysis.get("contains_logo"),
            analysis.get("logo_detected"),
            analysis.get("watermark_detected"),
        ):
            if candidate is True:
                return True
        cue_text = cls._asset_label_text(asset)
        return any(
            token in cue_text
            for token in (
                "logo",
                "wordmark",
                "brandmark",
                "brand mark",
                "brand signature",
                "lockup",
                "monogram",
                "watermark",
            )
        )

    @classmethod
    def _reference_conditioning_surface_kind(cls, asset: dict[str, Any]) -> str:
        metadata = cls._asset_metadata(asset)
        normalized_metadata = metadata.get("normalized_metadata")
        normalized_metadata = normalized_metadata if isinstance(normalized_metadata, dict) else {}
        source_metadata = metadata.get("source_metadata")
        source_metadata = source_metadata if isinstance(source_metadata, dict) else {}
        candidates = (
            metadata.get("surface_kind"),
            normalized_metadata.get("surface_kind"),
            source_metadata.get("surface_kind"),
        )
        return next((str(value).strip().lower() for value in candidates if str(value or "").strip()), "")

    @classmethod
    def _reference_conditioning_overlay_safe(cls, asset: dict[str, Any]) -> bool | None:
        metadata = cls._asset_metadata(asset)
        normalized_metadata = metadata.get("normalized_metadata")
        normalized_metadata = normalized_metadata if isinstance(normalized_metadata, dict) else {}
        source_metadata = metadata.get("source_metadata")
        source_metadata = source_metadata if isinstance(source_metadata, dict) else {}
        for value in (
            metadata.get("overlay_safe"),
            normalized_metadata.get("overlay_safe"),
            source_metadata.get("overlay_safe"),
        ):
            if isinstance(value, bool):
                return value
        return None

    @classmethod
    def _is_reference_image_asset(cls, asset: dict[str, Any]) -> bool:
        if not isinstance(asset, dict):
            return False
        mime_type = str(asset.get("mime_type") or "").strip().lower()
        if not mime_type.startswith("image/"):
            return False
        trust_level = str(asset.get("trust_level") or "").strip().lower()
        if trust_level in {"excluded", "reference_only"}:
            return False
        label_text = cls._asset_label_text(asset)
        if any(token in label_text for token in ("logo", "wordmark", "brandmark", "lockup", "emblem")):
            return False
        asset_role = str(asset.get("asset_role") or "").strip().lower()
        if asset_role in {"logo", "logo_variant"}:
            return False
        return True

    @classmethod
    def _is_conditioning_safe_reference_image_asset(
        cls,
        asset: dict[str, Any],
        *,
        creative_decision: CreativeDecisionPayload,
        request: AIOrchestrationRequest | None = None,
    ) -> bool:
        if not cls._reference_asset_is_visual_source(asset):
            return False
        metadata = cls._asset_metadata(asset)
        asset_role = str(asset.get("asset_role") or "").strip().lower()
        review_status = str(metadata.get("review_status") or "").strip().lower()
        surface_kind = cls._reference_conditioning_surface_kind(asset)
        overlay_safe = cls._reference_conditioning_overlay_safe(asset)
        template_surface_policy = str(
            ((creative_decision.asset_strategy or {}) if isinstance(creative_decision.asset_strategy, dict) else {}).get(
                "template_surface_policy"
            )
            or ""
        ).strip().lower()
        if review_status in {"reference_only", "excluded"}:
            return False
        if surface_kind == "reference_only_flattened_text":
            return False
        if overlay_safe is False:
            return False
        if asset_role == "template_preview":
            allow_conditioning = bool(
                metadata.get("allow_conditioning")
                or ((metadata.get("normalized_metadata") or {}) if isinstance(metadata.get("normalized_metadata"), dict) else {}).get(
                    "allow_conditioning"
                )
            )
            if not allow_conditioning:
                return False
        if template_surface_policy == "style_reference_only":
            preferred_paths = cls._preferred_sequence_reference_paths(request, creative_decision=creative_decision)
            asset_storage_path = str(asset.get("storage_path") or "").strip()
            if asset_role in {"template_preview", "reference_creative", "template"} and asset_storage_path not in preferred_paths:
                topic_score = cls._reference_asset_topic_score(asset, request=request) if request is not None else 0
                best_topic_score = 0
                if request is not None:
                    best_topic_score = max(
                        [
                            cls._reference_asset_topic_score(candidate, request=request)
                            for candidate in (request.asset_catalog or request.reference_assets or [])
                            if isinstance(candidate, dict) and cls._reference_asset_is_visual_source(candidate)
                        ]
                        or [0]
                    )
                if topic_score >= 30 and topic_score >= int(best_topic_score * 0.75):
                    return True
                return False
        return True

    @classmethod
    def _score_reference_image_candidate(
        cls,
        asset: dict[str, Any],
        *,
        request: AIOrchestrationRequest,
        creative_decision: CreativeDecisionPayload,
    ) -> int:
        asset_role = str(asset.get("asset_role") or "").strip().lower()
        trust_level = str(asset.get("trust_level") or "").strip().lower()
        label_text = cls._asset_label_text(asset)
        prompt_text = str(request.prompt or "").casefold()
        score = 0
        preferred_paths = cls._preferred_sequence_reference_paths(request, creative_decision=creative_decision)
        asset_storage_path = str(asset.get("storage_path") or "").strip()
        if trust_level == "trusted":
            score += 12
        elif trust_level in {"usable_with_warning", "usable-with-warning"}:
            score += 6
        if asset_storage_path and asset_storage_path in preferred_paths:
            score += 36
        if asset_role in {"reference_creative", "hero_image", "image", "photo"}:
            score += 10
        if asset_role in {"icon", "micro_design_element", "enhancement_component", "mood_board"}:
            score += 10 if str(request.studio_panel.get("format") or "").strip().lower() in {"carousel", "infographic"} else 6
        if "reference_creative" in label_text:
            score += 6
        score += cls._reference_asset_topic_score(asset, request=request)
        template_surface_policy = str(
            ((creative_decision.asset_strategy or {}) if isinstance(creative_decision.asset_strategy, dict) else {}).get(
                "template_surface_policy"
            )
            or ""
        ).strip().lower()
        if template_surface_policy == "style_reference_only" and asset_role in {"reference_creative", "template_preview", "template"}:
            if preferred_paths and asset_storage_path not in preferred_paths:
                score -= 28
            elif not preferred_paths:
                score -= 12
        keyword_map = {
            "travel": ["travel", "flight", "airport", "booking", "trip", "journey"],
            "finance": ["invest", "financial", "money", "growth", "portfolio", "business"],
            "lifestyle": ["person", "professional", "lifestyle", "team", "modern"],
        }
        for keywords in keyword_map.values():
            if any(token in prompt_text for token in keywords) and any(token in label_text for token in keywords):
                score += 8
                break
        format_name = str(request.studio_panel.get("format") or "static").strip().lower()
        if format_name == "carousel" and any(token in label_text for token in ("series", "set", "slide")):
            score += 4
        dominant_visual_system = cls._normalized_dominant_visual_system(creative_decision.asset_strategy or {})
        if dominant_visual_system in {"reference_assets", "asset_led"}:
            score += 4
        return score

    @classmethod
    def _select_reference_image_assets(
        cls,
        *,
        request: AIOrchestrationRequest,
        creative_decision: CreativeDecisionPayload,
    ) -> list[dict[str, Any]]:
        preferred_paths = cls._preferred_sequence_reference_paths(request, creative_decision=creative_decision)
        blocked_sequence_surface_paths = cls._sequence_pack_style_reference_surface_paths(
            request,
            creative_decision=creative_decision,
        )
        candidates = [
            dict(asset)
            for asset in (request.asset_catalog or request.reference_assets or [])
            if isinstance(asset, dict)
            and cls._reference_asset_is_visual_source(asset)
            and (
                str(asset.get("storage_path") or "").strip() not in blocked_sequence_surface_paths
                or str(asset.get("storage_path") or "").strip() in preferred_paths
            )
        ]
        if not candidates:
            return []
        template_surface_policy = str(
            ((creative_decision.asset_strategy or {}) if isinstance(creative_decision.asset_strategy, dict) else {}).get(
                "template_surface_policy"
            )
            or ""
        ).strip().lower()
        if template_surface_policy == "style_reference_only" and preferred_paths:
            preferred_candidates = [
                dict(asset)
                for asset in candidates
                if str(asset.get("storage_path") or "").strip() in preferred_paths
            ]
            if preferred_candidates:
                preferred_topic_score = max(
                    cls._reference_asset_topic_score(asset, request=request)
                    for asset in preferred_candidates
                )
                topical_candidates = cls._topic_relevant_reference_assets(
                    request,
                    creative_decision=creative_decision,
                    source_assets=candidates,
                    limit=max(cls._reference_image_limit(request.studio_panel), 2),
                )
                topical_score = max(
                    [cls._reference_asset_topic_score(asset, request=request) for asset in topical_candidates]
                    or [0]
                )
                if topical_candidates and topical_score > max(preferred_topic_score, 0):
                    candidates = topical_candidates
                else:
                    candidates = preferred_candidates
        strong_topic_candidates = cls._topic_relevant_reference_assets(
            request,
            creative_decision=creative_decision,
            source_assets=candidates,
            limit=max(cls._reference_image_limit(request.studio_panel), 2),
        )
        if strong_topic_candidates:
            strongest_topic_score = max(
                cls._reference_asset_topic_score(asset, request=request)
                for asset in strong_topic_candidates
            )
            if strongest_topic_score >= 30:
                strong_topic_paths = {
                    str(asset.get("storage_path") or "").strip()
                    for asset in strong_topic_candidates
                    if str(asset.get("storage_path") or "").strip()
                }
                candidates = [
                    dict(asset)
                    for asset in candidates
                    if str(asset.get("storage_path") or "").strip() in strong_topic_paths
                ]
        scored = sorted(
            candidates,
            key=lambda asset: (
                str(asset.get("storage_path") or "").strip() in preferred_paths,
                cls._is_conditioning_safe_reference_image_asset(asset, creative_decision=creative_decision, request=request),
                cls._score_reference_image_candidate(asset, request=request, creative_decision=creative_decision),
                str(asset.get("storage_path") or ""),
            ),
            reverse=True,
        )
        limit = cls._reference_image_limit(request.studio_panel)
        selected: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for asset in scored:
            storage_path = str(asset.get("storage_path") or "").strip()
            if not storage_path or storage_path in seen_paths:
                continue
            seen_paths.add(storage_path)
            selected.append(asset)
            if len(selected) >= limit:
                break
        return selected

    @classmethod
    def _conditioning_reference_image_assets(
        cls,
        reference_assets: list[dict[str, Any]],
        *,
        creative_decision: CreativeDecisionPayload,
        request: AIOrchestrationRequest | None = None,
    ) -> list[dict[str, Any]]:
        return [
            dict(asset)
            for asset in reference_assets
            if isinstance(asset, dict)
            and cls._is_conditioning_safe_reference_image_asset(asset, creative_decision=creative_decision, request=request)
        ]

    @classmethod
    def _carousel_sequence_uses_multiple_reference_images(
        cls,
        request: AIOrchestrationRequest | None,
    ) -> bool:
        if request is None:
            return False
        if str(request.studio_panel.get("format") or "").strip().lower() != "carousel":
            return False
        sequence_pack = cls._template_sequence_pack(request, creative_decision=None)
        if not isinstance(sequence_pack, dict):
            return False
        reference_paths: set[str] = set()
        for slide in [dict(item) for item in sequence_pack.get("slides", []) if isinstance(item, dict)]:
            for key in ("reference_asset_path", "template_asset_path"):
                storage_path = str(slide.get(key) or "").strip()
                if storage_path:
                    reference_paths.add(storage_path)
        return len(reference_paths) >= 2

    @classmethod
    def _filter_logo_bearing_conditioning_reference_images(
        cls,
        reference_assets: list[dict[str, Any]],
        *,
        exact_logo_overlay_required: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not exact_logo_overlay_required:
            return [dict(asset) for asset in reference_assets if isinstance(asset, dict)], []
        allowed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for asset in reference_assets:
            if not isinstance(asset, dict):
                continue
            if cls._reference_image_has_logo_cue(asset):
                skipped.append(dict(asset))
                continue
            allowed.append(dict(asset))
        return allowed, skipped

    def _filter_available_reference_image_assets(
        self,
        reference_assets: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        available: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        for asset in reference_assets:
            if not isinstance(asset, dict):
                continue
            storage_path = str(asset.get("storage_path") or "").strip()
            if not storage_path:
                missing.append(asset)
                continue
            if self.storage.exists(storage_path):
                available.append(asset)
            else:
                missing.append(asset)
        return available, missing

    def _reference_asset_conditioning_storage_path(
        self,
        asset: dict[str, Any],
        *,
        request: AIOrchestrationRequest,
        cache: dict[str, str],
    ) -> str:
        storage_path = str(asset.get("storage_path") or "").strip()
        if not storage_path or not self.storage.exists(storage_path):
            return ""
        mime_type = str(asset.get("mime_type") or "").strip().lower()
        if mime_type.startswith("image/"):
            return storage_path
        if mime_type != "application/pdf":
            return ""
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        requested_page_index = 1
        try:
            requested_page_index = int(metadata.get("conditioning_page_index") or 1)
        except (TypeError, ValueError):
            requested_page_index = 1
        cache_key = f"{storage_path}::page::{requested_page_index}"
        if cache_key in cache:
            return cache[cache_key]
        try:
            import fitz  # type: ignore[import-untyped]

            document = fitz.open(self.storage.absolute_path(storage_path))
            if len(document) <= 0:
                return ""
            page_offset = min(max(requested_page_index - 1, 0), max(len(document) - 1, 0))
            page = document[page_offset]
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            filename = storage_path.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
            stored = self.storage.save_bytes(
                tenant_id=request.tenant_id,
                brand_space_id=request.brand_space_id,
                category="generated/reference-conditioning",
                filename=f"{filename or 'reference'}-page-{page_offset + 1}.png",
                content=buffer.getvalue(),
            )
            cache[cache_key] = stored.storage_path
            return stored.storage_path
        except Exception as exc:  # pragma: no cover - defensive conditioning fallback
            logger.warning(
                "orchestrator.reference_pdf_conditioning_failed brand_space_id=%s storage_path=%s error=%s",
                request.brand_space_id,
                storage_path,
                exc,
            )
            return ""

    def _conditioning_reference_image_paths(
        self,
        reference_assets: list[dict[str, Any]],
        *,
        request: AIOrchestrationRequest,
        cache: dict[str, str],
    ) -> list[str]:
        paths: list[str] = []
        seen: set[str] = set()
        for asset in reference_assets:
            if not isinstance(asset, dict):
                continue
            storage_path = self._reference_asset_conditioning_storage_path(
                asset,
                request=request,
                cache=cache,
            )
            if not storage_path or storage_path in seen or not self.storage.exists(storage_path):
                continue
            seen.add(storage_path)
            paths.append(self.storage.absolute_path(storage_path))
        return paths

    @classmethod
    def _scene_graph_explicit_reference_assets(
        cls,
        scene_graph: GenerationSceneGraph,
        *,
        request: AIOrchestrationRequest,
    ) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for element in scene_graph.elements:
            if not cls._scene_graph_element_is_visual_image_like(element):
                continue
            asset = element.asset
            if asset is None:
                continue
            storage_path = str(asset.storage_path or "").strip()
            if not storage_path or storage_path in seen_paths:
                continue
            matched = cls._reference_asset_by_storage_path(request, storage_path)
            if matched is None:
                continue
            seen_paths.add(storage_path)
            assets.append(matched)
        return assets

    @staticmethod
    def _is_literal_reference_surface_role(asset_role: str | None) -> bool:
        normalized = str(asset_role or "").strip().casefold()
        return normalized in {
            "reference_creative",
            "template_preview",
            "template",
        }

    @classmethod
    def _asset_allows_literal_scene_binding(cls, asset: dict[str, Any]) -> bool:
        metadata = asset.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        return bool(
            metadata.get("literal_render_allowed")
            or metadata.get("renderer_safe_reference")
            or metadata.get("use_as_content_image")
        )

    @classmethod
    def _should_skip_literal_reference_binding(
        cls,
        scene_graph: GenerationSceneGraph,
        asset: dict[str, Any],
    ) -> bool:
        validation_hints = scene_graph.validation_hints if isinstance(scene_graph.validation_hints, dict) else {}
        template_surface_policy = str(validation_hints.get("template_surface_policy") or "").strip().lower()
        return (
            cls._is_literal_reference_surface_role(asset.get("asset_role"))
            and not cls._asset_allows_literal_scene_binding(asset)
            and (
                scene_graph.layout_mode == "synthesized_layout"
                or template_surface_policy == "style_reference_only"
            )
        )

    @staticmethod
    def bind_reference_assets(
        scene_graph: GenerationSceneGraph,
        reference_assets: list[dict[str, Any]],
    ) -> GenerationSceneGraph:
        if not reference_assets:
            return scene_graph
        scene_graph_data = scene_graph.model_dump(mode="json")
        existing_assets = list(scene_graph_data.get("assets") or [])
        existing_paths = {
            str(asset.get("storage_path") or "").strip()
            for asset in existing_assets
            if isinstance(asset, dict) and str(asset.get("storage_path") or "").strip()
        }
        for asset in reference_assets:
            if AIOrchestratorService._should_skip_literal_reference_binding(scene_graph, asset):
                continue
            storage_path = str(asset.get("storage_path") or "").strip()
            if not storage_path or storage_path in existing_paths:
                continue
            existing_paths.add(storage_path)
            existing_assets.append(
                {
                    "asset_id": str(asset.get("asset_id") or ""),
                    "asset_role": str(asset.get("asset_role") or "reference_creative"),
                    "storage_path": storage_path,
                    "trust_level": str(asset.get("trust_level") or "trusted"),
                    "notes": str(((asset.get("metadata") or {}) if isinstance(asset.get("metadata"), dict) else {}).get("label") or ""),
                }
            )
        scene_graph_data["assets"] = existing_assets
        image_elements = [
            element
            for element in scene_graph_data.get("elements", [])
            if isinstance(element, dict) and AIOrchestratorService._scene_graph_element_is_visual_image_like(element)
        ]
        asset_index = 0
        for element in image_elements:
            if asset_index >= len(reference_assets):
                break
            asset = reference_assets[asset_index]
            if AIOrchestratorService._should_skip_literal_reference_binding(scene_graph, asset):
                asset_index += 1
                continue
            asset_payload = dict(element.get("asset") or {})
            current_storage_path = str(asset_payload.get("storage_path") or "").strip()
            if current_storage_path:
                continue
            asset_payload["asset_id"] = str(asset.get("asset_id") or "") or asset_payload.get("asset_id")
            asset_payload["asset_role"] = str(asset.get("asset_role") or "reference_creative")
            asset_payload["storage_path"] = str(asset.get("storage_path") or "")
            asset_payload["trust_level"] = str(asset.get("trust_level") or "trusted")
            element["asset"] = asset_payload
            asset_index += 1
        return GenerationSceneGraph.model_validate(scene_graph_data)

    @classmethod
    def assess_creative_quality(
        cls,
        *,
        scene_graph: GenerationSceneGraph,
        creative_decision: CreativeDecisionPayload,
        validation_report: SceneGraphValidationReport,
        request: AIOrchestrationRequest,
        selected_reference_images: list[dict[str, Any]],
        used_support_fallback: bool,
        compiled_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        score = 0.92
        issues: list[str] = []
        issue_lookup = {issue.rule_id for issue in validation_report.issues}
        if validation_report.status != "clean":
            score -= min(len(validation_report.issues) * 0.06, 0.3)
            issues.extend(sorted(issue_lookup))
        if used_support_fallback:
            score -= 0.12
            issues.append("support_fallback_used")
        visible_elements = [element for element in scene_graph.elements if element.visible]
        content_elements = [element for element in visible_elements if element.role != "background"]
        if not cls._scene_graph_has_authoritative_geometry(scene_graph):
            score -= 0.1
            issues.append("weak_geometry_contract")
        elif cls._compiled_context_has_authoritative_layout(compiled_context):
            score += 0.03
        if len(content_elements) < 4:
            score -= 0.14
            issues.append("sparse_scene_graph")
        image_elements = [element for element in content_elements if cls._scene_graph_element_is_visual_image_like(element)]
        if not image_elements:
            score -= 0.08
            issues.append("missing_primary_visual")
        if not any(element.role == "logo" for element in content_elements):
            score -= 0.06
            issues.append("missing_logo")
        if "asset_strategy_overloaded" in issue_lookup:
            score -= 0.08
        follow_up_mode = cls._follow_up_mode(request)
        prior_archetype = cls._prior_layout_archetype(request)
        current_archetype = str((scene_graph.styles or {}).get("layout_archetype") or "").strip().casefold()
        if follow_up_mode == "variant_of_previous" and prior_archetype and current_archetype == prior_archetype:
            score -= 0.18
            issues.append("repeated_layout_archetype")
        if len(selected_reference_images) >= 2 and str(request.studio_panel.get("format") or "").strip().lower() == "carousel":
            bound_paths = {
                str((element.asset.storage_path if element.asset else "") or "").strip()
                for element in scene_graph.elements
                if cls._scene_graph_element_is_visual_image_like(element)
            }
            matched = sum(1 for asset in selected_reference_images if str(asset.get("storage_path") or "").strip() in bound_paths)
            if (
                matched < min(len(selected_reference_images), 2)
                and not cls._carousel_sequence_uses_multiple_reference_images(request)
            ):
                score -= 0.08
                issues.append("multi_image_underused")
        reference_topic_issue = cls._reference_topic_alignment_issue(request, selected_reference_images)
        if reference_topic_issue:
            score -= 0.24
            issues.append(reference_topic_issue)
        if image_elements:
            craft_supported = any(
                bool((element.validation_hints or {}).get(key))
                for element in image_elements
                for key in (
                    "visual_depth_style",
                    "visual_rendering_style",
                    "visual_polish_level",
                    "composition_balance",
                    "composition_framing",
                    "subject_scene_type",
                )
            )
            if not craft_supported:
                score -= 0.08
                issues.append("craft_direction_weak")
        reference_family_match = cls._reference_family_closeness(
            scene_graph,
            compiled_context=compiled_context,
        )
        if reference_family_match.get("issues"):
            score -= min((1.0 - float(reference_family_match.get("score") or 0.0)) * 0.2, 0.18)
            issues.extend(
                issue
                for issue in reference_family_match.get("issues", [])
                if issue not in issues
            )
        multimodal_issue = cls._multimodal_balance_issue(
            scene_graph,
            format_name=str(request.studio_panel.get("format") or ""),
        )
        if multimodal_issue:
            score -= 0.06
            issues.append(f"multimodal_balance_{multimodal_issue}")
        template_surface_policy = str(
            ((creative_decision.asset_strategy or {}) if isinstance(creative_decision.asset_strategy, dict) else {}).get("template_surface_policy")
            or ""
        ).strip().lower()
        has_reference_zone_maps = cls._request_has_authoritative_reference_zone_maps(request)
        if template_surface_policy == "style_reference_only" and selected_reference_images:
            if has_reference_zone_maps and not cls._scene_graph_has_authoritative_geometry(scene_graph):
                score -= 0.1
                issues.append("sample_structure_underused")
            elif not cls._compiled_context_has_authoritative_layout(compiled_context):
                score -= 0.08
                issues.append("sample_structure_underused")
        if template_surface_policy == "style_reference_only" and has_reference_zone_maps and not selected_reference_images:
            score -= 0.22
            issues.append("reference_conditioning_missing")
        if scene_graph.confidence < 0.55:
            score -= 0.06
            issues.append("low_scene_confidence")
        score = max(0.0, round(score, 2))
        return {
            "score": score,
            "issues": issues,
            "retry_recommended": score < cls.IMAGE_QUALITY_MIN_SCORE,
            "used_support_fallback": used_support_fallback,
            "selected_reference_image_count": len(selected_reference_images),
            "layout_archetype": current_archetype or None,
            "reference_family_match": reference_family_match,
        }

    @staticmethod
    def _quality_report_from_assessment(assessment: dict[str, Any]) -> SceneGraphValidationReport:
        issue_map = {
            "support_fallback_used": (
                "support_fallback_used",
                "Fallback composition was used and still needs a more premium, original layout.",
                "Produce a more premium scene graph without relying on the fallback archetype.",
            ),
            "sparse_scene_graph": (
                "quality_sparse_scene_graph",
                "Scene graph still reads as too sparse for a premium social creative.",
                "Increase hierarchy, supporting structure, and visual emphasis while keeping the layout clean.",
            ),
            "missing_primary_visual": (
                "quality_missing_primary_visual",
                "Creative lacks a convincing primary visual emphasis.",
                "Add or strengthen the hero visual treatment with cleaner negative space.",
            ),
            "missing_logo": (
                "quality_missing_logo",
                "Brand identity is still too weak because the logo treatment is missing.",
                "Include a clear logo placement in a brand-safe area.",
            ),
            "repeated_layout_archetype": (
                "quality_repeated_layout_archetype",
                "Variant/regenerate request reused the same layout archetype as the prior creative.",
                "Choose a distinctly different layout archetype and composition from the previous output.",
            ),
            "multi_image_underused": (
                "quality_multi_image_underused",
                "Multiple reference images were available but the composition did not make deliberate use of them.",
                "Use the strongest subset of the uploaded images in a purposeful multi-image composition.",
            ),
            "reference_topic_mismatch": (
                "quality_reference_topic_mismatch",
                "Selected reference imagery does not match the current request topic strongly enough.",
                "Use topic-relevant uploaded samples or factual source assets instead of generic brand/template assets that can leak unrelated objects.",
            ),
            "weak_geometry_contract": (
                "quality_weak_geometry_contract",
                "The current plan does not preserve a strong enough geometry contract for premium rendering.",
                "Return a scene graph with explicit normalized coordinates and stronger region discipline for headline, image, CTA, and logo-safe zones.",
            ),
            "craft_direction_weak": (
                "quality_craft_direction_weak",
                "The current plan lacks enough premium craft direction to match the sample's visual finish.",
                "Add stronger craft, rendering, composition, and subject guidance to the scene graph instead of generic visual placeholders.",
            ),
            "reference_family_zone_drift": (
                "quality_reference_family_zone_drift",
                "The current layout is drifting away from the approved reference family zone grammar.",
                "Bring the scene graph back toward the expected family zone roles, hierarchy, and region structure instead of using a generic layout.",
            ),
            "reference_family_image_zone_drift": (
                "quality_reference_family_image_zone_drift",
                "The current plan is not keeping imagery inside the approved reference family image zones.",
                "Place generated imagery only inside the expected image roles from the reference family profile.",
            ),
            "reference_family_layout_drift": (
                "quality_reference_family_layout_drift",
                "The current layout archetype is drifting away from the approved reference family.",
                "Use the reference family's intended layout archetype instead of a generic or unrelated composition.",
            ),
            "reference_family_geometry_drift": (
                "quality_reference_family_geometry_drift",
                "The current plan is drifting away from the approved reference-family region geometry.",
                "Bring the scene graph boxes back toward the sample-driven zone map so spacing, hierarchy, and negative space stay faithful to the approved family.",
            ),
            "reference_family_module_drift": (
                "quality_reference_family_module_drift",
                "The current plan is missing too much of the approved reference family module grammar.",
                "Recompose the creative using the expected module patterns such as proof grids, comparison modules, hero splits, or CTA strips.",
            ),
            "multimodal_balance_text_heavy": (
                "quality_multimodal_balance_text_heavy",
                "The current plan is too text-heavy relative to the supporting visual system.",
                "Give the composition a stronger image-led or explainer-led focal system and distribute evidence into cleaner modular regions instead of one dense text block.",
            ),
            "multimodal_balance_image_heavy": (
                "quality_multimodal_balance_image_heavy",
                "The current plan is visually dominant but under-supports the message with enough editorial structure.",
                "Add clearer headline, support, or evidence regions so the message feels deliberate rather than like a generic hero image.",
            ),
            "sample_structure_underused": (
                "quality_sample_structure_underused",
                "The current plan is underusing the uploaded sample's composition skeleton.",
                "Preserve the sample's region proportions, sequencing, and negative-space structure more strictly while still reinterpreting the artwork from scratch.",
            ),
            "reference_conditioning_missing": (
                "quality_reference_conditioning_missing",
                "The current plan lost the intended sample-reference visual conditioning and is likely to drift into generic imagery.",
                "Use the approved sample-family reference images for conditioning so palette, image treatment, and visual motifs stay closer to the selected brand/sample family.",
            ),
            "low_scene_confidence": (
                "quality_low_scene_confidence",
                "The current plan is not confident enough for final rendering.",
                "Return a clearer, more deliberate premium layout plan with stronger visual hierarchy.",
            ),
        }
        issues: list[SceneGraphValidationIssue] = []
        for item in assessment.get("issues", []) or []:
            mapped = issue_map.get(str(item))
            if not mapped:
                continue
            rule_id, message, correction = mapped
            issues.append(
                SceneGraphValidationIssue(
                    severity="warning",
                    rule_id=rule_id,
                    message=message,
                    expected_correction=correction,
                    repairable=True,
                )
            )
        return SceneGraphValidationReport(
            status="needs_repair" if issues else "clean",
            issues=issues,
            summary=[issue.message for issue in issues[:6]],
            repairable=True,
        )

    @staticmethod
    def _allowed_palette_values(compiled_context: dict[str, Any]) -> set[str]:
        palette_roles = (compiled_context.get("brand_visual_brief", {}) or {}).get("palette_roles", {}) or {}
        allowed = {str(value).strip().lower() for value in palette_roles.values() if str(value).strip()}
        allowed.update({"#ffffff", "#000000", "#111111", "#f8f8f8", "#f4f4f4", "#1f2937"})
        return allowed

    @classmethod
    def _normalize_topic_anchor_token(cls, token: str) -> str:
        text = str(token or "").strip().casefold()
        text = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", text)
        if len(text) <= 3:
            return ""
        if text.endswith("ies") and len(text) > 4:
            text = f"{text[:-3]}y"
        elif text.endswith("ing") and len(text) > 5:
            text = text[:-3]
        elif text.endswith("ed") and len(text) > 4:
            text = text[:-2]
        elif text.endswith("s") and len(text) > 4:
            text = text[:-1]
        return text if text and text not in cls.TOPIC_ANCHOR_STOPWORDS else ""

    @classmethod
    def _topic_anchor_keywords(cls, value: Any, *, limit: int = 8) -> set[str]:
        words = re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", cls._coerce_text_value(value))
        keywords: list[str] = []
        for word in words:
            token = cls._normalize_topic_anchor_token(word)
            if not token or token in keywords:
                continue
            keywords.append(token)
            if len(keywords) >= limit:
                break
        return set(keywords)

    @classmethod
    def _scene_graph_text_blob(cls, scene_graph: GenerationSceneGraph) -> str:
        parts: list[str] = []

        def collect(element: Any) -> None:
            if getattr(element, "text", None):
                parts.append(cls._coerce_text_value(element.text))
            if getattr(element, "content", None):
                parts.append(cls._coerce_text_value(element.content))
            for child in getattr(element, "elements", None) or []:
                collect(child)

        for element in scene_graph.elements:
            collect(element)
        return " ".join(part for part in parts if part)

    def validate_scene_graph(
        self,
        *,
        scene_graph: GenerationSceneGraph,
        creative_decision: CreativeDecisionPayload,
        request: AIOrchestrationRequest,
        compiled_context: dict[str, Any],
    ) -> SceneGraphValidationReport:
        issues: list[SceneGraphValidationIssue] = []
        allowed_palette = self._allowed_palette_values(compiled_context)
        allowed_fonts = {
            str(item).strip().casefold()
            for item in (compiled_context.get("brand_visual_brief", {}) or {}).get("font_families", []) or []
            if str(item).strip()
        }
        asset_trust: dict[str, str] = {}
        for asset in (request.asset_catalog or request.reference_assets):
            if not isinstance(asset, dict):
                continue
            asset_id = str(asset.get("asset_id") or "").strip()
            storage_path = str(asset.get("storage_path") or "").strip()
            trust_level = str(asset.get("trust_level") or "").strip().lower()
            if asset_id:
                asset_trust[asset_id] = trust_level
            if storage_path:
                asset_trust[storage_path] = trust_level

        requested_size = request.studio_panel.get("size") or {}
        if requested_size and (
            int(scene_graph.canvas.width) != int(requested_size.get("width") or scene_graph.canvas.width)
            or int(scene_graph.canvas.height) != int(requested_size.get("height") or scene_graph.canvas.height)
        ):
            issues.append(
                SceneGraphValidationIssue(
                    severity="warning",
                    rule_id="platform_canvas_mismatch",
                    message="Scene graph canvas does not match the requested platform size.",
                    expected_correction="Align the canvas width and height to the studio panel size.",
                    repairable=True,
                )
            )

        has_logo = any(element.visible and element.role == "logo" for element in scene_graph.elements)
        has_headline = any(element.visible and element.role == "headline" for element in scene_graph.elements)
        visible_elements = self._scene_graph_visible_elements(scene_graph)
        content_elements = [element for element in visible_elements if element.role != "background"]
        logo_geometry = self._logo_safe_zone_geometry(scene_graph)
        logo_position_hint = self._normalize_metadata_text(
            (scene_graph.styles or {}).get("logo_position")
            or (scene_graph.validation_hints or {}).get("logo_position"),
            limit=80,
        )
        logo_background_tone = self._resolve_logo_background_tone(
            creative_decision=creative_decision,
            scene_graph=scene_graph,
        )
        has_visual_emphasis = any(
            element.role in {"image", "icon", "decorative_shape", "logo"}
            or element.element_type in {"image", "icon", "decorative_shape", "background_shape", "logo"}
            for element in content_elements
        )
        session_brief = compiled_context.get("session_brief", {}) or {}
        follow_up_mode = str(session_brief.get("follow_up_mode") or "").strip().casefold()
        prior_layout_archetype = str(session_brief.get("prior_layout_archetype") or "").strip().casefold()
        current_layout_archetype = str((scene_graph.styles or {}).get("layout_archetype") or "").strip().casefold()
        identity = request.resolved_brand_context.get("identity", {}) or {}
        prompt_topic_keywords = self._topic_anchor_keywords(request.prompt)
        scene_text_blob = self._scene_graph_text_blob(scene_graph)
        if not has_headline:
            issues.append(
                SceneGraphValidationIssue(
                    severity="error",
                    rule_id="missing_headline",
                    message="Scene graph must include a visible headline element.",
                    expected_correction="Add a headline element with concrete geometry and styling.",
                    repairable=True,
                )
            )
        if (identity.get("logo_asset_id") or identity.get("logo_asset_ids") or identity.get("logo_assets")) and not has_logo:
            issues.append(
                SceneGraphValidationIssue(
                    severity="warning",
                    rule_id="logo_required",
                    message="Brand identity requires a logo element in the scene graph.",
                    expected_correction="Add a visible logo element in a safe brand placement.",
                    repairable=True,
                )
            )
        if has_logo and logo_geometry is None:
            issues.append(
                SceneGraphValidationIssue(
                    severity="warning",
                    rule_id="logo_geometry_unclear",
                    message="Logo element is present but the reserved overlay geometry is missing or invalid.",
                    expected_correction="Provide a concrete corner-based logo box with usable geometry for overlay.",
                    repairable=True,
                )
            )
        if has_logo and logo_geometry is not None and logo_position_hint:
            current_anchor = self._anchor_from_logo_geometry(logo_geometry)
            hint_anchor = self._logo_anchor_from_hint(logo_position_hint)
            if hint_anchor and current_anchor != f"{hint_anchor[0]}-{hint_anchor[1]}":
                issues.append(
                    SceneGraphValidationIssue(
                        severity="warning",
                        rule_id="logo_position_mismatch",
                        message="Logo geometry does not match the requested or stored logo position hint.",
                        expected_correction="Align the logo box to the intended logo_position corner.",
                        repairable=True,
                    )
                )
        if has_logo and not logo_background_tone:
            issues.append(
                SceneGraphValidationIssue(
                    severity="warning",
                    rule_id="logo_surface_tone_missing",
                    message="Logo reservation does not specify whether the surface behind the exact logo should be light, dark, or neutral.",
                    expected_correction="Set logo_background_tone or a matching logo_variant so the overlay uses a clearer contrast strategy.",
                    repairable=True,
                )
            )
        preset = str(request.studio_panel.get("platform_preset") or "").strip().lower()
        if preset in {"instagram", "linkedin", "x", "youtube_thumbnail"} and len(content_elements) < 4:
            issues.append(
                SceneGraphValidationIssue(
                    severity="warning",
                    rule_id="insufficient_scene_graph_structure",
                    message="Scene graph is too sparse for a social creative and will render as an under-designed poster.",
                    expected_correction="Add structured supporting elements such as proof_points, icons, decorative shapes, image, and logo.",
                    repairable=True,
                )
            )
        if preset in {"instagram", "linkedin"} and not has_visual_emphasis:
            issues.append(
                SceneGraphValidationIssue(
                    severity="warning",
                    rule_id="missing_visual_emphasis",
                    message="Scene graph lacks a primary visual or decorative emphasis element.",
                    expected_correction="Add an image, icon sequence, decorative shapes, or a prominent logo treatment.",
                    repairable=True,
                )
            )

        # Validate template format compatibility for carousel requests
        format_name = request.studio_panel.get("format", "").strip().lower()
        selected_template_id = creative_decision.selected_template_id

        if format_name in ("carousel", "instagram_carousel", "linkedin_carousel"):
            # Check if template supports multi-frame format
            if selected_template_id and len(scene_graph.elements) < 6:
                # Carousels should have richer element structure (typically 6+ elements per slide)
                issues.append(
                    SceneGraphValidationIssue(
                        severity="warning",
                        rule_id="template_format_mismatch",
                        element_path="scene_graph",
                        message=f"Template '{selected_template_id}' may not support carousel format (sparse element count: {len(scene_graph.elements)}). Carousels typically need 6+ elements per slide for rich structure.",
                        expected_correction="Use a carousel-compatible template or enrich the scene graph with more structural elements (background, headline, supporting_line, body, cta, logo, image, etc.).",
                        repairable=True,
                    )
                )

        if follow_up_mode == "variant_of_previous" and prior_layout_archetype and current_layout_archetype == prior_layout_archetype:
            issues.append(
                SceneGraphValidationIssue(
                    severity="warning",
                    rule_id="repeated_layout_archetype",
                    message="Variant/regenerate request reused the prior layout archetype.",
                    expected_correction="Choose a materially different layout archetype from the previous creative.",
                    repairable=True,
                )
            )
        if (
            follow_up_mode == "new_content"
            and prompt_topic_keywords
            and not (prompt_topic_keywords & self._topic_anchor_keywords(scene_text_blob))
        ):
            issues.append(
                SceneGraphValidationIssue(
                    severity="warning",
                    rule_id="topic_anchor_missing",
                    message="The current copy and layout drift away from the user's requested topic.",
                    expected_correction="Keep the user's topic visible in the headline, supporting copy, proof points, and overall campaign framing.",
                    repairable=True,
                )
            )

        reference_family_match = self._reference_family_closeness(
            scene_graph,
            compiled_context=compiled_context,
        )
        if reference_family_match.get("issues"):
            validation_issue_map = {
                "reference_family_zone_drift": (
                    "The scene graph is drifting away from the approved reference-family zone grammar.",
                    "Re-anchor the headline, proof, CTA, and visual regions to the approved family roles instead of using a generic layout.",
                ),
                "reference_family_image_zone_drift": (
                    "The scene graph is not keeping imagery inside the approved reference-family image regions.",
                    "Move generated imagery back into the approved family image zones and keep text regions clean.",
                ),
                "reference_family_layout_drift": (
                    "The scene graph layout archetype is drifting away from the approved reference family.",
                    "Use the reference family's layout archetype and spacing rhythm instead of a generic poster structure.",
                ),
                "reference_family_module_drift": (
                    "The scene graph is missing too much of the approved reference-family module grammar.",
                    "Recompose the scene using the expected family modules such as hero split, proof grid, comparison, or CTA strip.",
                ),
                "reference_family_geometry_drift": (
                    "The scene graph geometry is drifting away from the approved reference-family region structure.",
                    "Bring the element boxes back toward the sample-driven zone map and preserve its spacing and negative-space rhythm.",
                ),
            }
            existing_rule_ids = {str(issue.rule_id or "").strip() for issue in issues}
            for issue_id in reference_family_match.get("issues", []):
                if issue_id in existing_rule_ids:
                    continue
                message, correction = validation_issue_map.get(
                    str(issue_id),
                    (
                        "The scene graph is drifting away from the approved reference-family contract.",
                        "Bring the scene graph back toward the approved sample-driven structure.",
                    ),
                )
                issues.append(
                    SceneGraphValidationIssue(
                        severity="warning",
                        rule_id=str(issue_id),
                        message=message,
                        expected_correction=correction,
                        repairable=True,
                    )
                )
                existing_rule_ids.add(str(issue_id))

        asset_strategy = creative_decision.asset_strategy or {}
        asset_flags = self._major_asset_strategy_flags(asset_strategy)
        if sum(1 for enabled in asset_flags.values() if enabled) >= 3:
            issues.append(
                SceneGraphValidationIssue(
                    severity="warning",
                    rule_id="asset_strategy_overloaded",
                    message="Creative decision is mixing too many major visual systems in one social creative.",
                    expected_correction="Choose one dominant visual system and at most one supporting system.",
                    repairable=True,
                )
            )
        if creative_decision.layout_mode == "synthesized_layout" and asset_flags.get("template_background"):
            issues.append(
                SceneGraphValidationIssue(
                    severity="warning",
                    rule_id="asset_strategy_overloaded",
                    message="Synthesized layouts should not depend on a template background surface.",
                    expected_correction="Either switch to a template-led layout or remove template background usage.",
                    repairable=True,
                )
            )
        if asset_strategy.get("icon_sequence") and not any(element.role == "icon" for element in content_elements):
            issues.append(
                SceneGraphValidationIssue(
                    severity="warning",
                    rule_id="asset_strategy_unfulfilled",
                    message="Creative decision requested icons, but the scene graph does not include icon elements.",
                    expected_correction="Add icon elements or an explicit proof_points section supported by icons.",
                    repairable=True,
                )
            )
        if asset_strategy.get("background_element") and not any(
            element.role == "decorative_shape" or element.element_type in {"decorative_shape", "background_shape"}
            for element in content_elements
        ):
            issues.append(
                SceneGraphValidationIssue(
                    severity="warning",
                    rule_id="asset_strategy_unfulfilled",
                    message="Creative decision requested a background or decorative element, but the scene graph does not include one.",
                    expected_correction="Add decorative_shape or background_shape elements to carry the intended visual emphasis.",
                    repairable=True,
                )
            )
        icon_elements = [
            element
            for element in content_elements
            if element.role == "icon"
            and element.geometry.units == "normalized"
            and element.geometry.x is not None
            and element.geometry.y is not None
        ]
        if any(element.role == "image" for element in content_elements) and len(icon_elements) >= 3:
            issues.append(
                SceneGraphValidationIssue(
                    severity="warning",
                    rule_id="icon_overuse_with_hero_image",
                    message="Scene graph mixes a hero image with too many standalone icons, which reads as stamped rather than designed.",
                    expected_correction="Use either an image-led composition with restrained accents or integrate icons into structured proof cards.",
                    repairable=True,
                )
            )
        if len(icon_elements) >= 3:
            xs = [float(element.geometry.x or 0) for element in icon_elements]
            ys = sorted(float(element.geometry.y or 0) for element in icon_elements)
            if (max(xs) - min(xs)) <= 0.04 and (ys[-1] - ys[0]) >= 0.12:
                issues.append(
                    SceneGraphValidationIssue(
                        severity="warning",
                        rule_id="icon_stamp_column",
                        message="Icon elements are arranged as a simplistic vertical stamp column.",
                        expected_correction="Integrate icons into cards, proof rows, or a more composed visual rhythm.",
                        repairable=True,
                    )
                )

        for element in scene_graph.elements:
            geometry = element.geometry
            text_value = self._coerce_text_value(element.text)
            if text_value and self._contains_disallowed_glyphs(text_value):
                issues.append(
                    SceneGraphValidationIssue(
                        severity="warning",
                        rule_id="disallowed_text_glyphs",
                        element_id=element.element_id,
                        message=f"Element '{element.element_id}' contains emoji or symbol glyphs that are unsafe for clean brand rendering.",
                        expected_correction="Remove emoji-like glyphs and represent benefits with structured proof_points or icons instead.",
                        repairable=True,
                    )
                )
            if element.role in {"headline", "supporting_line", "body", "cta"} and self._looks_like_prompt_echo(text_value, request.prompt):
                issues.append(
                    SceneGraphValidationIssue(
                        severity="warning",
                        rule_id="prompt_echo_copy",
                        element_id=element.element_id,
                        message=f"Element '{element.element_id}' repeats the user's instruction instead of audience-facing copy.",
                        expected_correction="Rewrite the element into polished campaign language without repeating imperative prompt wording.",
                        repairable=True,
                    )
                )
            for style_key in ("fill", "primary_fill", "gradient_from", "gradient_to", "stroke", "background_fill"):
                style_value = str((element.style or {}).get(style_key) or "").strip().lower()
                if style_value and style_value.startswith("#") and style_value not in allowed_palette:
                    issues.append(
                        SceneGraphValidationIssue(
                            severity="warning",
                            rule_id="color_palette_violation",
                            element_id=element.element_id,
                            message=f"Element '{element.element_id}' uses color {style_value} outside the validated palette.",
                            expected_correction="Use validated palette roles or approved neutral colors.",
                            repairable=True,
                        )
                    )
            font_family = str((element.style or {}).get("font_family") or "").strip()
            if font_family and allowed_fonts and font_family.casefold() not in allowed_fonts:
                issues.append(
                    SceneGraphValidationIssue(
                        severity="warning",
                        rule_id="font_usage_violation",
                        element_id=element.element_id,
                        message=f"Element '{element.element_id}' uses font '{font_family}' outside the approved brand fonts.",
                        expected_correction="Use one of the validated brand font families.",
                        repairable=True,
                    )
                )
            if geometry.units == "normalized":
                numeric_values = [geometry.x, geometry.y, geometry.width, geometry.height]
                if any(value is None for value in numeric_values):
                    issues.append(
                        SceneGraphValidationIssue(
                            severity="error",
                            rule_id="missing_geometry",
                            element_id=element.element_id,
                            message=f"Element '{element.element_id}' is missing normalized geometry.",
                            expected_correction="Provide x, y, width, and height for the element.",
                            repairable=True,
                        )
                    )
                    continue
                # Check if element extends outside normalized canvas bounds
                # Use 3% tolerance (1.03) to avoid false positives from floating point rounding
                x_end = float((geometry.x or 0) + (geometry.width or 0))
                y_end = float((geometry.y or 0) + (geometry.height or 0))
                if (
                    float(geometry.x or 0) < -0.01  # Allow small negative tolerance
                    or float(geometry.y or 0) < -0.01
                    or float(geometry.width or 0) <= 0
                    or float(geometry.height or 0) <= 0
                    or x_end > 1.03  # 3% tolerance for rounding
                    or y_end > 1.03
                ):
                    issues.append(
                        SceneGraphValidationIssue(
                            severity="warning",
                            rule_id="layout_bounds_violation",
                            element_id=element.element_id,
                            message=f"Element '{element.element_id}' extends outside the normalized canvas bounds (x: {geometry.x}, y: {geometry.y}, width: {geometry.width}, height: {geometry.height}, x_end: {x_end:.4f}, y_end: {y_end:.4f}).",
                            expected_correction="Keep all element geometry within the 0..1 normalized canvas.",
                            repairable=True,
                        )
                    )
            if element.asset:
                asset_keys = [element.asset.asset_id, element.asset.storage_path]
                trust = next((asset_trust.get(str(key)) for key in asset_keys if key and asset_trust.get(str(key))), None)
                if trust in {"excluded", "reference_only"}:
                    issues.append(
                        SceneGraphValidationIssue(
                            severity="warning",
                            rule_id="asset_trust_violation",
                            element_id=element.element_id,
                            message=f"Element '{element.element_id}' references an asset that is not approved for direct use.",
                            expected_correction="Replace the asset with a trusted or usable-with-warning asset.",
                            repairable=True,
                        )
                    )

        return SceneGraphValidationReport(
            status="clean" if not issues else "needs_repair",
            issues=issues,
            summary=[issue.message for issue in issues[:6]],
            repairable=all(issue.repairable for issue in issues),
        )

    @staticmethod
    def _needs_generated_image(scene_graph: GenerationSceneGraph, creative_decision: CreativeDecisionPayload) -> bool:
        if not creative_decision.asset_strategy.get("use_generated_image", True):
            return False
        return any(
            element.visible
            and element.role == "image"
            and ((not element.asset) or ((element.asset.asset_role or "").strip() in {"", "ai_image"}))
            for element in scene_graph.elements
        )

    def _needs_generated_image_with_storage(
        self,
        scene_graph: GenerationSceneGraph,
        creative_decision: CreativeDecisionPayload,
    ) -> bool:
        if not creative_decision.asset_strategy.get("use_generated_image", True):
            return False
        for element in scene_graph.elements:
            if not element.visible or element.role != "image":
                continue
            asset = element.asset
            if not asset:
                return True
            asset_role = str(asset.asset_role or "").strip().lower()
            storage_path = str(asset.storage_path or "").strip()
            if asset_role in {"", "ai_image"}:
                return True
            if storage_path and self.storage.exists(storage_path):
                continue
            return True
        return False

    @staticmethod
    def bind_generated_assets(
        scene_graph: GenerationSceneGraph,
        generated_assets: list[GeneratedImageAsset],
    ) -> GenerationSceneGraph:
        if not generated_assets:
            return scene_graph
        scene_graph_data = scene_graph.model_dump(mode="json")
        asset_payload = generated_assets[0].model_dump(mode="json")
        existing_assets = list(scene_graph_data.get("assets") or [])
        existing_assets.append(
            {
                "asset_id": str(asset_payload["asset_id"]),
                "asset_role": asset_payload["asset_role"],
                "storage_path": asset_payload["storage_path"],
                "trust_level": "trusted",
            }
        )
        scene_graph_data["assets"] = existing_assets
        for element in scene_graph_data.get("elements", []):
            if element.get("role") != "image":
                continue
            asset = dict(element.get("asset") or {})
            asset.setdefault("asset_id", str(asset_payload["asset_id"]))
            asset["asset_role"] = asset_payload["asset_role"]
            asset["storage_path"] = asset_payload["storage_path"]
            asset["trust_level"] = "trusted"
            element["asset"] = asset
            break
        return GenerationSceneGraph.model_validate(scene_graph_data)

    def _generate_image_with_retries(
        self,
        *,
        image_provider,
        tenant_id,
        brand_space_id,
        prompt: str,
        size: str | None,
        trace_id: str | None,
        trace_label: str,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, max(int(self.settings.image_retry_attempts or 1), 1) + 1):
            try:
                payload = image_provider.generate(
                    tenant_id=tenant_id,
                    brand_space_id=brand_space_id,
                    prompt=prompt,
                    size=size,
                )
                if attempt > 1:
                    self._trace_payload(
                        trace_id,
                        self.trace,
                        f"{trace_label}_retry_{attempt:02d}",
                        {"attempt": attempt, "status": "success"},
                    )
                return payload
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                self._trace_payload(
                    trace_id,
                    self.trace,
                    f"{trace_label}_retry_{attempt:02d}",
                    {
                        "attempt": attempt,
                        "status": "error",
                        "error": str(exc),
                        "non_retryable": self._is_non_retryable_image_error(exc),
                    },
                )
                if self._is_non_retryable_image_error(exc):
                    break
        assert last_error is not None
        raise last_error

    def _edit_image_with_retries(
        self,
        *,
        image_provider,
        tenant_id,
        brand_space_id,
        prompt: str,
        image_paths: list[str],
        size: str | None,
        mask_png_bytes: bytes | None,
        trace_id: str | None,
        trace_label: str,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, max(int(self.settings.image_retry_attempts or 1), 1) + 1):
            try:
                payload = image_provider.edit(
                    tenant_id=tenant_id,
                    brand_space_id=brand_space_id,
                    prompt=prompt,
                    image_paths=image_paths,
                    size=size,
                    mask_png_bytes=mask_png_bytes,
                )
                if attempt > 1:
                    self._trace_payload(
                        trace_id,
                        self.trace,
                        f"{trace_label}_retry_{attempt:02d}",
                        {"attempt": attempt, "status": "success"},
                    )
                return payload
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                self._trace_payload(
                    trace_id,
                    self.trace,
                    f"{trace_label}_retry_{attempt:02d}",
                    {
                        "attempt": attempt,
                        "status": "error",
                        "error": str(exc),
                        "non_retryable": self._is_non_retryable_image_error(exc),
                    },
                )
                if self._is_non_retryable_image_error(exc):
                    break
        assert last_error is not None
        raise last_error

    def render_final_assets_only(
        self,
        *,
        request: AIOrchestrationRequest,
        text_payload: StructuredTextPayload,
        creative_decision: CreativeDecisionPayload,
        scene_graph: GenerationSceneGraph,
        message_strategy: MessageStrategyPayload | None = None,
        validation_report: SceneGraphValidationReport | None = None,
        generation_path: str | None = None,
        selected_reference_images: list[dict[str, Any]] | None = None,
        conditioning_reference_images: list[dict[str, Any]] | None = None,
        compiled_context: dict[str, Any] | None = None,
        quality_assessment: dict[str, Any] | None = None,
        quality_retry_attempts: int = 0,
        fresh_replan_attempted: bool = False,
    ) -> tuple[list[GeneratedImageAsset], GeneratedImageAsset | None, StructuredTextPayload, GenerationSceneGraph]:
        trace_id = request.generation_trace_id
        image_provider = self.providers.get_image_provider()
        generation_path = str(generation_path or "image_led_social").strip().lower() or "image_led_social"
        message_strategy = message_strategy or MessageStrategyPayload()
        validation_report = validation_report or SceneGraphValidationReport()
        compiled_context = dict(compiled_context or {})
        quality_assessment = dict(quality_assessment or {})
        selected_reference_images = [dict(asset) for asset in (selected_reference_images or []) if isinstance(asset, dict)]
        if not selected_reference_images:
            selected_reference_images = self._select_reference_image_assets(
                request=request,
                creative_decision=creative_decision,
            )
            selected_reference_images, _missing_reference_images = self._filter_available_reference_image_assets(
                selected_reference_images,
            )
        conditioning_reference_images = [dict(asset) for asset in (conditioning_reference_images or []) if isinstance(asset, dict)]
        if not conditioning_reference_images:
            conditioning_reference_images = self._conditioning_reference_image_assets(
                selected_reference_images,
                creative_decision=creative_decision,
                request=request,
            )

        scene_graph_ignored_for_final_render = self._should_ignore_scene_graph_for_final_render(
            generation_path=generation_path,
            fresh_replan_attempted=fresh_replan_attempted,
            validation_report=validation_report,
            scene_graph=scene_graph,
            compiled_context=compiled_context,
        )
        final_render_scene_graph = scene_graph
        final_render_retry_note: str | None = None
        if scene_graph_ignored_for_final_render:
            final_render_retry_note = self._final_render_ignore_note(validation_report)
            fallback_scene_graph = self._fallback_image_led_scene_graph(
                request=request,
                text_payload=text_payload.model_dump(mode="json"),
                creative_decision=creative_decision.model_dump(mode="json"),
                compiled_context=compiled_context,
            )
            final_render_scene_graph = self.normalize_scene_graph_payload(
                fallback_scene_graph,
                fallback=scene_graph.model_dump(mode="json"),
                creative_decision=creative_decision,
                text_payload=text_payload.model_dump(mode="json"),
                request=request,
                compiled_context=compiled_context,
            )
            self._trace_payload(
                trace_id,
                self.trace,
                "final_render_scene_graph_override",
                {
                    "reason": "render_only_scene_graph_rejected",
                    "issues": [issue.rule_id for issue in validation_report.issues],
                    "retry_note": final_render_retry_note,
                    "scene_graph": final_render_scene_graph.model_dump(mode="json"),
                },
            )

        visual_explanation_plan = self._visual_explanation_plan(
            request,
            text_payload,
            creative_decision,
            selected_reference_images,
            message_strategy,
        )
        if self._should_block_low_quality_final_render(quality_assessment):
            self._trace_payload(
                trace_id,
                self.trace,
                "final_render_blocked_low_quality",
                {
                    "quality_assessment": quality_assessment,
                    "reason": "quality_below_hard_threshold_before_render",
                },
            )
            raise GenerationFailureError(
                "Final render blocked because the planned creative is still below the minimum premium-quality threshold.",
                failure_type="validation_failure",
                reason_code="final_render_quality_blocked",
                user_safe_message="The current creative draft did not meet the minimum quality threshold, so generation was stopped instead of returning a weak result.",
                retryable=True,
                suggested_next_action="Refine the scene graph, reference conditioning, or slide structure and try generation again.",
                details={"quality_assessment": quality_assessment},
            )
        self._trace_payload(
            trace_id,
            self.trace,
            "visual_explanation_plan",
            visual_explanation_plan,
        )

        image_size = self._image_generation_size(request.studio_panel)
        is_carousel_render = str(request.studio_panel.get("format") or "").strip().lower() == "carousel"
        carousel_slide_specs = (
            self._build_carousel_slide_specs(
                text_payload,
                request=request,
                creative_decision=creative_decision,
            )
            if is_carousel_render
            else []
        )
        if carousel_slide_specs:
            text_payload = text_payload.model_copy(
                update={
                    "metadata": {
                        **(text_payload.metadata or {}),
                        "carousel_slide_specs": carousel_slide_specs,
                    }
                }
            )
        slide_specs = (
            carousel_slide_specs
            if is_carousel_render
            else [
                {
                    "role": "single",
                    "headline": text_payload.headline,
                    "supporting_line": (text_payload.metadata or {}).get("supporting_line") or text_payload.body,
                    "proof_points": self._normalize_metadata_list((text_payload.metadata or {}).get("proof_points"), limit=3),
                    "cta": text_payload.cta,
                    "slide_index": 1,
                    "slide_count": 1,
                }
            ]
        )
        logo_storage_path, requested_logo_variant = self._select_logo_candidate_for_render(
            request=request,
            creative_decision=creative_decision,
            scene_graph=final_render_scene_graph,
        )
        exact_logo_overlay_required = bool(logo_storage_path and self.storage.exists(logo_storage_path))
        prompt_reference_images = list(conditioning_reference_images)
        conditioning_reference_images, skipped_logo_reference_images = self._filter_logo_bearing_conditioning_reference_images(
            conditioning_reference_images,
            exact_logo_overlay_required=exact_logo_overlay_required,
        )
        topic_reference_images = self._topic_relevant_reference_assets(
            request,
            creative_decision=creative_decision,
            limit=2,
        )
        if topic_reference_images:
            prompt_reference_images = self._merge_reference_asset_lists(topic_reference_images, prompt_reference_images)
            conditioning_reference_images = self._merge_reference_asset_lists(
                topic_reference_images,
                conditioning_reference_images,
            )
        if skipped_logo_reference_images:
            prompt_reference_images = [*conditioning_reference_images, *skipped_logo_reference_images]
            self._trace_payload(
                trace_id,
                self.trace,
                "final_render_logo_bearing_reference_images_skipped",
                {
                    "reason": "exact_logo_overlay_requires_logo_free_conditioning",
                    "skipped_storage_paths": [
                        str(asset.get("storage_path") or "")
                        for asset in skipped_logo_reference_images
                    ],
                    "logo_storage_path": logo_storage_path,
                },
            )

        final_render_assets: list[GeneratedImageAsset] = []
        image_generation_error: str | None = None
        pdf_reference_conditioning_cache: dict[str, str] = {}
        try:
            for slide in slide_specs:
                slide_index = int(slide.get("slide_index") or 1)
                slide_count = int(slide.get("slide_count") or len(slide_specs))
                trace_suffix = f"_slide_{slide_index:02d}" if is_carousel_render else ""
                slide_prompt_reference_images = (
                    self._slide_reference_images(
                        slide,
                        prompt_reference_images,
                        request=request,
                        creative_decision=creative_decision,
                    )
                    if is_carousel_render
                    else [dict(asset) for asset in prompt_reference_images if isinstance(asset, dict)]
                )
                slide_conditioning_reference_images = (
                    self._slide_reference_images(
                        slide,
                        conditioning_reference_images,
                        request=request,
                        creative_decision=creative_decision,
                    )
                    if is_carousel_render
                    else [dict(asset) for asset in conditioning_reference_images if isinstance(asset, dict)]
                )
                slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
                desired_reference_path = str(slide_metadata.get("reference_asset_path") or "").strip()
                if desired_reference_path and not slide_prompt_reference_images:
                    matched_reference_asset = self._reference_asset_by_storage_path(request, desired_reference_path)
                    if matched_reference_asset is not None:
                        slide_prompt_reference_images = [matched_reference_asset]
                if desired_reference_path and not slide_conditioning_reference_images:
                    matched_reference_asset = self._reference_asset_by_storage_path(request, desired_reference_path)
                    if (
                        matched_reference_asset is not None
                        and self._is_conditioning_safe_reference_image_asset(
                            matched_reference_asset,
                            creative_decision=creative_decision,
                            request=request,
                        )
                    ):
                        slide_conditioning_reference_images = [matched_reference_asset]
                if (
                    is_carousel_render
                    and not slide_conditioning_reference_images
                    and not str(slide_metadata.get("reference_asset_path") or "").strip()
                ):
                    slide_conditioning_reference_images = [
                        dict(asset) for asset in conditioning_reference_images if isinstance(asset, dict)
                    ]
                reference_image_paths = self._conditioning_reference_image_paths(
                    slide_conditioning_reference_images,
                    request=request,
                    cache=pdf_reference_conditioning_cache,
                )
                if is_carousel_render:
                    final_render_prompt = self.build_carousel_slide_render_prompt(
                        request=request,
                        creative_decision=creative_decision,
                        message_strategy=message_strategy,
                        slide=slide,
                        scene_graph=final_render_scene_graph,
                        reference_images=slide_prompt_reference_images,
                        retry_note=final_render_retry_note,
                        visual_explanation_plan=visual_explanation_plan,
                        compiled_context=compiled_context,
                    )
                else:
                    final_render_prompt = self.build_final_render_prompt(
                        request=request,
                        text_payload=text_payload,
                        creative_decision=creative_decision,
                        scene_graph=final_render_scene_graph,
                        message_strategy=message_strategy,
                        reference_images=prompt_reference_images,
                        retry_note=final_render_retry_note,
                        visual_explanation_plan=visual_explanation_plan,
                        compiled_context=compiled_context,
                    )
                self._trace_payload(
                    trace_id,
                    self.trace,
                    f"final_render_prompt{trace_suffix}",
                    {
                        "prompt": final_render_prompt,
                        "size": image_size,
                        "model": self.settings.image_model,
                        "prompt_length": len(final_render_prompt),
                        "text_overlay_strategy": (
                            "ai_renders_approved_text_and_layout"
                            if is_carousel_render
                            else "backend_exact_text_on_ai_text_safe_substrate"
                        ),
                        "slide_index": slide_index,
                        "slide_count": slide_count,
                        "role": slide.get("role"),
                        "render_only": True,
                    },
                )
                if reference_image_paths:
                    asset = self._edit_image_with_retries(
                        image_provider=image_provider,
                        tenant_id=request.tenant_id,
                        brand_space_id=request.brand_space_id,
                        prompt=final_render_prompt,
                        image_paths=reference_image_paths,
                        size=image_size,
                        mask_png_bytes=None,
                        trace_id=trace_id,
                        trace_label=f"final_render_conditioned_generation{trace_suffix}",
                    )
                else:
                    asset = self._generate_image_with_retries(
                        image_provider=image_provider,
                        tenant_id=request.tenant_id,
                        brand_space_id=request.brand_space_id,
                        prompt=final_render_prompt,
                        size=image_size,
                        trace_id=trace_id,
                        trace_label=f"final_render_generation{trace_suffix}",
                    )
                base_asset = GeneratedImageAsset(
                    asset_id=uuid4(),
                    mime_type=asset["mime_type"],
                    storage_path=asset["storage_path"],
                    width=asset["width"],
                    height=asset["height"],
                    asset_role=asset["asset_role"],
                    metadata={
                        "provider": asset.get("provider"),
                        "model": asset.get("model") or self.settings.image_model,
                        "requested_size": asset.get("size", image_size),
                        "generation_path": generation_path,
                        "generation_stage": "base_final_render",
                        "reference_conditioned": bool(reference_image_paths),
                        "slide_index": slide_index,
                        "slide_count": slide_count,
                        "carousel_role": slide.get("role"),
                    },
                )
                slide_text_payload = StructuredTextPayload(
                    headline=str(slide.get("headline") or text_payload.headline),
                    body=self._carousel_slide_body_text(
                        slide,
                        fallback_text=str(slide.get("supporting_line") or text_payload.body),
                    ),
                    cta=str(slide.get("cta") or text_payload.cta),
                    hashtags=text_payload.hashtags,
                    metadata={
                        **(text_payload.metadata or {}),
                        "source": (
                            "structured_slide_spec"
                            if any(
                                str(slide.get(field) or "").strip()
                                for field in ("headline", "supporting_line", "body", "visual_focus", "cta")
                            )
                            or bool(slide.get("proof_points") or slide.get("body_points") or slide.get("stat_highlights"))
                            else str(((text_payload.metadata or {}) if isinstance(text_payload.metadata, dict) else {}).get("source") or "fallback")
                        ),
                        "supporting_line": str(slide.get("supporting_line") or text_payload.body),
                        "proof_points": list(slide.get("proof_points") or []),
                        "body_points": list(slide.get("body_points") or []),
                        "stat_highlights": list(slide.get("stat_highlights") or []),
                        "visual_focus": str(slide.get("visual_focus") or ""),
                        "transition_note": str(slide.get("transition_note") or ""),
                        "slide_role": str(slide.get("role") or ""),
                        "slide_index": slide_index,
                        "slide_count": slide_count,
                    },
                )
                final_asset_metadata = {
                    "render_source": "ai",
                    "generation_stage": "final_render",
                    "provider": asset.get("provider"),
                    "model": asset.get("model") or self.settings.image_model,
                    "prompt_length": len(final_render_prompt),
                    "text_overlay_strategy": (
                        "ai_renders_approved_text_and_layout"
                        if is_carousel_render
                        else "backend_exact_text_on_ai_text_safe_substrate"
                    ),
                    "requested_size": asset.get("size", image_size),
                    "generation_path": generation_path,
                    "layout_mode": creative_decision.layout_mode,
                    "scene_graph_used": not scene_graph_ignored_for_final_render,
                    "scene_graph_ignored_for_final_render": scene_graph_ignored_for_final_render,
                    "logo_composited_by_ai": False,
                    "base_storage_path": base_asset.storage_path,
                    "reference_conditioned_by_ai": bool(reference_image_paths),
                    "reference_image_storage_paths": [str(reference_asset.get("storage_path") or "") for reference_asset in slide_conditioning_reference_images],
                    "logo_bearing_reference_image_storage_paths_skipped": [str(reference_asset.get("storage_path") or "") for reference_asset in skipped_logo_reference_images],
                    "visual_explanation_mode": visual_explanation_plan.get("mode"),
                    "visual_explanation_need": visual_explanation_plan.get("need"),
                    "visual_explanation_density": visual_explanation_plan.get("density"),
                    "visual_explanation_rationale": visual_explanation_plan.get("rationale"),
                    "quality_assessment": quality_assessment,
                    "quality_retry_attempts": quality_retry_attempts,
                    "slide_index": slide_index,
                    "slide_count": slide_count,
                    "carousel_role": slide.get("role"),
                }
                if not is_carousel_render:
                    filtered_scene = final_render_scene_graph.model_copy(deep=True)
                    filtered_scene.elements = [e for e in filtered_scene.elements if e.role in ("legal", "footer", "disclaimer")]
                    final_asset_metadata["render_overlay_scene_graph"] = filtered_scene.model_dump(mode="json")
                    
                    filtered_text = slide_text_payload.model_copy(deep=True)
                    filtered_metadata = (filtered_text.metadata or {}).copy()
                    filtered_text.metadata = filtered_metadata
                    final_asset_metadata["render_overlay_text"] = filtered_text.model_dump(mode="json")
                if requested_logo_variant:
                    final_asset_metadata["requested_logo_variant"] = requested_logo_variant
                if logo_storage_path and self.storage.exists(logo_storage_path):
                    final_asset_metadata["logo_source_storage_path"] = logo_storage_path
                    final_asset_metadata["logo_overlay_strategy"] = "exact_asset_overlay"
                    self._trace_payload(
                        trace_id,
                        self.trace,
                        f"logo_overlay_deferred_to_export{trace_suffix}",
                        {
                            "reason": "preserve_exact_logo_asset",
                            "logo_storage_path": logo_storage_path,
                            "requested_logo_variant": requested_logo_variant,
                            "base_storage_path": base_asset.storage_path,
                            "slide_index": slide_index,
                            "slide_count": slide_count,
                            "render_only": True,
                        },
                    )
                final_render_assets.append(
                    GeneratedImageAsset(
                        asset_id=uuid4(),
                        mime_type=asset["mime_type"],
                        storage_path=asset["storage_path"],
                        width=asset["width"],
                        height=asset["height"],
                        asset_role="render_preview" if slide_index == 1 else "render_export",
                        metadata=final_asset_metadata,
                    )
                )
        except Exception as exc:  # pragma: no cover - resilience path
            image_generation_error = str(exc)
            logger.warning(
                "orchestrator.render_only.final_render_failed brand_space_id=%s error=%s",
                request.brand_space_id,
                image_generation_error,
            )
            self._trace_payload(trace_id, self.trace, "final_render_error", {"error": image_generation_error, "render_only": True})

        final_render_asset = final_render_assets[0] if final_render_assets else None
        if final_render_asset is None:
            raise GenerationFailureError(
                self._ai_final_render_failure_message(),
                failure_type="provider_failure",
                reason_code="ai_final_render_failed",
                user_safe_message="I couldn't generate the visual this time. Please regenerate.",
                retryable=True,
                rule_source="system",
                suggested_next_action="Regenerate the creative.",
                details={
                    "generation_path": generation_path,
                    "underlying_error": image_generation_error,
                    "stage": "orchestrator.render_only",
                },
            )
        self._trace_payload(
            trace_id,
            self.trace,
            "final_render_generation",
            {
                "slide_count": len(final_render_assets),
                "assets": [asset.model_dump(mode="json") for asset in final_render_assets],
                "render_only": True,
            },
        )
        return final_render_assets, final_render_asset, text_payload, final_render_scene_graph

    @classmethod
    def _clean_content_semantic_issue(
        cls,
        *,
        code: str,
        message: str,
        targeted_fields: list[str] | None = None,
        slide_indexes: list[int] | None = None,
        slide_targets: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "code": cls._normalize_metadata_text(code, limit=64),
            "message": cls._normalize_metadata_text(message, limit=240),
            "targeted_fields": [
                field
                for field in [cls._normalize_metadata_text(item, limit=48) for item in (targeted_fields or [])]
                if field
            ],
            "slide_indexes": [int(item) for item in (slide_indexes or []) if int(item) > 0],
            "slide_targets": [
                target
                for target in [cls._normalize_metadata_text(item, limit=64) for item in (slide_targets or [])]
                if target
            ],
        }

    @classmethod
    def _format_name_from_request(cls, request: AIOrchestrationRequest) -> str:
        return cls._normalize_metadata_text(request.studio_panel.get("format"), limit=32).casefold()

    @classmethod
    def _needs_content_semantic_validation(cls, request: AIOrchestrationRequest) -> bool:
        return cls._format_name_from_request(request) in {"carousel", "infographic", "static"}

    @classmethod
    def _build_content_semantic_rewrite_instruction(
        cls,
        *,
        format_name: str,
        issues: list[dict[str, Any]],
    ) -> str:
        issue_messages = [
            cls._normalize_metadata_text(issue.get("message"), limit=220)
            for issue in issues
            if isinstance(issue, dict)
        ]
        slide_scope = sorted(
            {
                f"slide {int(index)}"
                for issue in issues
                if isinstance(issue, dict)
                for index in (issue.get("slide_indexes") or [])
                if str(index).strip().isdigit()
            }
        )
        slide_targets = sorted(
            {
                cls._normalize_metadata_text(target, limit=48)
                for issue in issues
                if isinstance(issue, dict)
                for target in (issue.get("slide_targets") or [])
                if cls._normalize_metadata_text(target, limit=48)
            }
        )
        scope_text = ""
        if slide_scope or slide_targets:
            scope_text = f" Keep the rewrite scoped to {', '.join([*slide_scope, *slide_targets])} where possible."
        if format_name == "carousel":
            return (
                "Rewrite the structured carousel content so each slide carries one distinct editorial job and the sequence reads like a real narrative, not repeated summaries."
                f" Fix these issues: {'; '.join(issue_messages)}."
                " Strengthen metadata.carousel_slide_specs, body, proof_points, stat_highlights, and claim_evidence_pairs."
                " Remove CTA treatment from non-final slides and keep the closing slide distinct."
                " Do not change the campaign topic or visual direction unless required to support the copy structure."
                f"{scope_text}"
            )
        if format_name == "infographic":
            return (
                "Rewrite the structured infographic content so each section has a distinct job, distinct evidence, and a clear progression from overview to evidence to takeaway."
                f" Fix these issues: {'; '.join(issue_messages)}."
                " Strengthen metadata.infographic_section_specs, body, proof_points, stat_highlights, and claim_evidence_pairs."
                " Do not collapse the sections back into one repeated summary block."
                f"{scope_text}"
            )
        return (
            "Rewrite the structured static content so the panel has one dominant message with concrete support instead of generic or repeated lines."
            f" Fix these issues: {'; '.join(issue_messages)}."
            " Strengthen metadata.static_panel_spec, body, proof_points, stat_highlights, and claim_evidence_pairs."
            " Keep the message concise and keep CTA treatment secondary to the main claim."
        )

    @classmethod
    def _content_semantic_revision_scope(
        cls,
        *,
        issues: list[dict[str, Any]],
    ) -> dict[str, Any]:
        targeted_fields = sorted(
            {
                field
                for issue in issues
                if isinstance(issue, dict)
                for field in (issue.get("targeted_fields") or [])
                if cls._normalize_metadata_text(field, limit=48)
            }
        )
        slide_indexes = sorted(
            {
                int(index)
                for issue in issues
                if isinstance(issue, dict)
                for index in (issue.get("slide_indexes") or [])
                if str(index).strip().isdigit() and int(index) > 0
            }
        )
        slide_targets = sorted(
            {
                cls._normalize_metadata_text(target, limit=64)
                for issue in issues
                if isinstance(issue, dict)
                for target in (issue.get("slide_targets") or [])
                if cls._normalize_metadata_text(target, limit=64)
            }
        )
        scope: dict[str, Any] = {
            "targeted_fields": targeted_fields or ["body", "metadata"],
            "only_targeted": True,
            "preserve_visuals": True,
            "change_layout": False,
            "change_tone": False,
            "preserve_copy": False,
        }
        if slide_indexes:
            scope["slide_indexes"] = slide_indexes
        if slide_targets:
            scope["slide_targets"] = slide_targets
        return scope

    @classmethod
    def _content_semantic_rewrite_field_plan(
        cls,
        *,
        text_payload: StructuredTextPayload,
        issues: list[dict[str, Any]],
        format_name: str,
        request: AIOrchestrationRequest | None = None,
        creative_decision: CreativeDecisionPayload | None = None,
    ) -> dict[str, Any]:
        metadata = text_payload.metadata or {}
        plan = {
            "format": format_name,
            "headline": text_payload.headline,
            "cta": text_payload.cta,
            "must_preserve": {
                "hashtags": list(text_payload.hashtags or []),
                "supporting_line": cls._normalize_metadata_text(metadata.get("supporting_line"), limit=180),
                "preferred_slide_count": metadata.get("preferred_slide_count"),
            },
            "issues": issues,
        }
        if format_name == "carousel" and request is not None:
            normalized_slides = cls._build_carousel_slide_specs(
                text_payload,
                request=request,
                creative_decision=creative_decision,
            )
            targeted_slide_indexes = sorted(
                {
                    int(index)
                    for issue in issues
                    if isinstance(issue, dict)
                    for index in (issue.get("slide_indexes") or [])
                    if str(index).strip().isdigit() and int(index) > 0
                }
            )
            slide_contracts: list[dict[str, Any]] = []
            for index, slide in enumerate(normalized_slides, start=1):
                if targeted_slide_indexes and index not in targeted_slide_indexes:
                    continue
                slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
                slide_contracts.append(
                    {
                        "slide_number": index,
                        "story_role": cls._normalize_metadata_text(
                            slide_metadata.get("story_role") or slide.get("role"),
                            limit=48,
                        ),
                        "preferred_headline": cls._normalize_metadata_text(slide.get("headline"), limit=120),
                        "preferred_supporting_line": cls._normalize_metadata_text(slide.get("supporting_line"), limit=220),
                        "preferred_body": cls._normalize_metadata_text(
                            cls._carousel_slide_body_text(slide, fallback_text=""),
                            limit=320,
                        ),
                        "preferred_proof_points": cls._normalize_metadata_list(slide.get("proof_points"), limit=3),
                        "preferred_stat_highlights": cls._normalize_metadata_list(slide.get("stat_highlights"), limit=3),
                        "preferred_claim_evidence_pairs": cls._normalize_claim_evidence_pairs(
                            slide.get("claim_evidence_pairs"),
                            limit=2,
                        ),
                        "cta_must_be_empty": index < len(normalized_slides),
                    }
                )
            if slide_contracts:
                plan["preferred_slide_contracts"] = slide_contracts
        return plan

    @classmethod
    def _validate_content_semantics(
        cls,
        *,
        request: AIOrchestrationRequest,
        text_payload: StructuredTextPayload,
        compiled_context: dict[str, Any] | None = None,
        creative_decision: CreativeDecisionPayload | None = None,
    ) -> dict[str, Any]:
        format_name = cls._format_name_from_request(request)
        if format_name not in {"carousel", "infographic", "static"}:
            return {
                "status": "clean",
                "repairable": False,
                "format": format_name,
                "issues": [],
                "summary": [],
                "targeted_fields": [],
                "revision_scope": {},
            }

        issues: list[dict[str, Any]] = []
        metadata = text_payload.metadata or {}

        if format_name == "carousel":
            raw_structured_slides = [dict(item) for item in (metadata.get("carousel_slide_specs") or []) if isinstance(item, dict)]
            raw_seen_supports: set[str] = set()
            for index, raw_slide in enumerate(raw_structured_slides, start=1):
                raw_story_role = cls._normalize_metadata_text(
                    raw_slide.get("slide_role") or raw_slide.get("role"),
                    limit=48,
                ).casefold().replace(" ", "_")
                raw_headline = cls._normalize_metadata_text(
                    raw_slide.get("headline") or raw_slide.get("title"),
                    limit=120,
                )
                raw_support = cls._normalize_metadata_text(
                    raw_slide.get("supporting_line") or raw_slide.get("body"),
                    limit=220,
                )
                raw_cta = cls._normalize_metadata_text(raw_slide.get("cta"), limit=90)
                if index < len(raw_structured_slides) and raw_cta:
                    issues.append(
                        cls._clean_content_semantic_issue(
                            code="carousel_raw_interior_cta",
                            message=f"Generated slide {index} still includes CTA copy before the closing slide.",
                            targeted_fields=["metadata"],
                            slide_indexes=[index],
                            slide_targets=[raw_story_role or f"slide_{index}"],
                        )
                    )
                if index > 1 and (cls._is_promotional_line(raw_headline) or cls._is_generic_carousel_education_label(raw_headline)):
                    issues.append(
                        cls._clean_content_semantic_issue(
                            code="carousel_raw_generic_headline",
                            message=f"Generated slide {index} uses a generic or CTA-like headline instead of a specific editorial label.",
                            targeted_fields=["metadata"],
                            slide_indexes=[index],
                            slide_targets=[raw_story_role or f"slide_{index}"],
                        )
                    )
                if raw_support and raw_support.casefold() in raw_seen_supports and index > 1:
                    issues.append(
                        cls._clean_content_semantic_issue(
                            code="carousel_raw_repeated_support",
                            message=f"Generated slide {index} repeats supporting copy from an earlier slide.",
                            targeted_fields=["body", "metadata"],
                            slide_indexes=[index],
                            slide_targets=[raw_story_role or f"slide_{index}"],
                        )
                    )
                if raw_support:
                    raw_seen_supports.add(raw_support.casefold())
            slides = cls._build_carousel_slide_specs(
                text_payload,
                request=request,
                creative_decision=creative_decision,
            )
            if len(slides) < 3:
                issues.append(
                    cls._clean_content_semantic_issue(
                        code="carousel_too_short",
                        message="The carousel sequence is too short to carry a real hook, middle progression, and close.",
                        targeted_fields=["body", "metadata"],
                    )
                )
            expected_roles = cls._carousel_expected_story_roles(
                request=request,
                metadata=metadata,
                fallback_slides=slides,
                slide_count=len(slides),
            )
            actual_roles = [
                cls._normalize_metadata_text(
                    ((slide.get("metadata") or {}).get("story_role") if isinstance(slide.get("metadata"), dict) else slide.get("role")),
                    limit=48,
                ).casefold().replace(" ", "_")
                for slide in slides
            ]
            for normalized_role in [
                cls._normalize_metadata_text(role, limit=48).casefold().replace(" ", "_")
                for role in expected_roles
            ]:
                if normalized_role and normalized_role not in actual_roles:
                    issues.append(
                        cls._clean_content_semantic_issue(
                            code="carousel_missing_story_role",
                            message=f"The carousel is missing a clear {normalized_role} slide in the intended sequence.",
                            targeted_fields=["body", "metadata"],
                            slide_targets=[normalized_role],
                        )
                    )
            seen_supports: set[str] = set()
            for index, slide in enumerate(slides, start=1):
                slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
                story_role = cls._normalize_metadata_text(
                    slide_metadata.get("story_role") or slide.get("role"),
                    limit=48,
                ).casefold().replace(" ", "_")
                support = cls._normalize_metadata_text(slide.get("supporting_line"), limit=220)
                headline = cls._normalize_metadata_text(slide.get("headline"), limit=120)
                proof_points = cls._normalize_metadata_list(slide.get("proof_points"), limit=3)
                claim_pairs = cls._normalize_claim_evidence_pairs(slide.get("claim_evidence_pairs"), limit=2)
                if index < len(slides) and cls._normalize_metadata_text(slide.get("cta"), limit=90):
                    issues.append(
                        cls._clean_content_semantic_issue(
                            code="carousel_interior_cta",
                            message=f"Slide {index} still contains CTA treatment before the closing slide.",
                            targeted_fields=["metadata"],
                            slide_indexes=[index],
                            slide_targets=[story_role],
                        )
                    )
                if support and support.casefold() in seen_supports and story_role not in {"hook", "closing", "takeaway"}:
                    issues.append(
                        cls._clean_content_semantic_issue(
                            code="carousel_repeated_support",
                            message=f"Slide {index} repeats supporting copy instead of carrying a distinct idea.",
                            targeted_fields=["body", "metadata"],
                            slide_indexes=[index],
                            slide_targets=[story_role],
                        )
                    )
                if support:
                    seen_supports.add(support.casefold())
                if index > 1 and cls._is_generic_carousel_education_label(headline):
                    issues.append(
                        cls._clean_content_semantic_issue(
                            code="carousel_generic_headline",
                            message=f"Slide {index} still uses a generic educational label instead of a specific editorial job.",
                            targeted_fields=["metadata"],
                            slide_indexes=[index],
                            slide_targets=[story_role],
                        )
                    )
                if story_role in {"structure", "undercovered_angle", "strategic_meaning", "analysis", "what_matters"} and not (claim_pairs or proof_points):
                    issues.append(
                        cls._clean_content_semantic_issue(
                            code="carousel_missing_evidence_anchor",
                            message=f"Slide {index} lacks a concrete evidence anchor for its analytical role.",
                            targeted_fields=["body", "metadata"],
                            slide_indexes=[index],
                            slide_targets=[story_role],
                        )
                    )

        elif format_name == "infographic":
            sections = [dict(item) for item in (metadata.get("infographic_section_specs") or []) if isinstance(item, dict)]
            if len(sections) < 2:
                issues.append(
                    cls._clean_content_semantic_issue(
                        code="infographic_too_flat",
                        message="The infographic still reads like one flat message instead of a structured sectioned explainer.",
                        targeted_fields=["body", "metadata"],
                    )
                )
            evidence_sections = 0
            seen_section_heads: set[str] = set()
            for index, section in enumerate(sections, start=1):
                role = cls._normalize_metadata_text(section.get("section_role"), limit=48).casefold().replace(" ", "_")
                headline = cls._normalize_metadata_text(section.get("headline") or section.get("section_label"), limit=120)
                claim_pairs = cls._normalize_claim_evidence_pairs(section.get("claim_evidence_pairs"), limit=2)
                proof_points = cls._normalize_metadata_list(section.get("proof_points"), limit=3)
                if role == "evidence":
                    evidence_sections += 1
                if headline and headline.casefold() in seen_section_heads and role not in {"overview", "takeaway"}:
                    issues.append(
                        cls._clean_content_semantic_issue(
                            code="infographic_repeated_section",
                            message=f"Section {index} repeats a prior section instead of advancing the explainer.",
                            targeted_fields=["body", "metadata"],
                            slide_indexes=[index],
                            slide_targets=[role],
                        )
                    )
                if headline:
                    seen_section_heads.add(headline.casefold())
                if role in {"evidence", "detail", "analysis", "takeaway"} and not (claim_pairs or proof_points):
                    issues.append(
                        cls._clean_content_semantic_issue(
                            code="infographic_missing_evidence",
                            message=f"Section {index} lacks a distinct proof or claim/evidence anchor.",
                            targeted_fields=["body", "metadata"],
                            slide_indexes=[index],
                            slide_targets=[role],
                        )
                    )
            if sections and evidence_sections == 0:
                issues.append(
                    cls._clean_content_semantic_issue(
                        code="infographic_missing_evidence_section",
                        message="The infographic has no clear evidence section to carry the factual payload.",
                        targeted_fields=["body", "metadata"],
                        slide_targets=["evidence"],
                    )
                )

        elif format_name == "static":
            panel = metadata.get("static_panel_spec") if isinstance(metadata.get("static_panel_spec"), dict) else {}
            dominant_message = cls._normalize_metadata_text(panel.get("dominant_message"), limit=180)
            supporting_line = cls._normalize_metadata_text(metadata.get("supporting_line"), limit=180)
            proof_points = cls._normalize_metadata_list(metadata.get("proof_points"), limit=3)
            claim_pairs = cls._normalize_claim_evidence_pairs(panel.get("claim_evidence_pairs") or metadata.get("claim_evidence_pairs"), limit=1)
            if not dominant_message:
                issues.append(
                    cls._clean_content_semantic_issue(
                        code="static_missing_dominant_message",
                        message="The static creative does not yet have one dominant message.",
                        targeted_fields=["body", "metadata"],
                    )
                )
            if dominant_message and supporting_line and dominant_message.casefold() == supporting_line.casefold() and not proof_points:
                issues.append(
                    cls._clean_content_semantic_issue(
                        code="static_too_repetitive",
                        message="The static creative repeats the same line without concrete supporting proof.",
                        targeted_fields=["body", "metadata"],
                    )
                )
            if not proof_points and not claim_pairs:
                issues.append(
                    cls._clean_content_semantic_issue(
                        code="static_missing_support",
                        message="The static creative still needs a concrete proof or claim/evidence support line.",
                        targeted_fields=["body", "metadata"],
                    )
                )

        summary = [
            cls._normalize_metadata_text(issue.get("message"), limit=220)
            for issue in issues[:6]
            if isinstance(issue, dict)
        ]
        revision_scope = cls._content_semantic_revision_scope(issues=issues) if issues else {}
        targeted_fields = list(revision_scope.get("targeted_fields") or [])
        return {
            "status": "needs_rewrite" if issues else "clean",
            "repairable": bool(issues),
            "format": format_name,
            "issues": issues,
            "summary": summary,
            "targeted_fields": targeted_fields,
            "revision_scope": revision_scope,
            "rewrite_instruction": (
                cls._build_content_semantic_rewrite_instruction(
                    format_name=format_name,
                    issues=issues,
                )
                if issues
                else ""
            ),
        }

    def _repair_text_payload_semantics_if_needed(
        self,
        *,
        request: AIOrchestrationRequest,
        generation_provider: Any,
        text_payload: StructuredTextPayload,
        compiled_context: dict[str, Any],
        message_strategy: MessageStrategyPayload,
        creative_decision: CreativeDecisionPayload | None,
        brand_name: str,
        trace_id: str,
    ) -> tuple[StructuredTextPayload, dict[str, Any], int]:
        report = self._validate_content_semantics(
            request=request,
            text_payload=text_payload,
            compiled_context=compiled_context,
            creative_decision=creative_decision,
        )
        attempts = 0
        while (
            report.get("status") != "clean"
            and bool(report.get("repairable"))
            and attempts < self.CONTENT_SEMANTIC_REPAIR_ATTEMPTS
        ):
            attempts += 1
            rewrite_envelope = self.prompts.compose_rewrite_envelope(
                original_prompt=request.prompt,
                rewrite_instruction=str(report.get("rewrite_instruction") or "").strip(),
                current_payload=text_payload.model_dump(mode="json"),
                compiled_context=compiled_context,
                message_strategy=message_strategy.model_dump(mode="json"),
                tone_analysis={},
                rewrite_field_plan=self._content_semantic_rewrite_field_plan(
                    text_payload=text_payload,
                    issues=list(report.get("issues") or []),
                    format_name=str(report.get("format") or self._format_name_from_request(request)),
                    request=request,
                    creative_decision=creative_decision,
                ),
                studio_panel=request.studio_panel,
                targeted_fields=list(report.get("targeted_fields") or []),
                revision_scope=report.get("revision_scope") if isinstance(report.get("revision_scope"), dict) else {},
            )
            rewrite_response = generation_provider.generate_structured_json(
                rewrite_envelope,
                fallback=text_payload.model_dump(mode="json"),
            )
            self._trace_payload(
                trace_id,
                self.trace,
                f"content_semantic_repair_{attempts:02d}",
                {
                    "report": report,
                    "prompt": {
                        "system": rewrite_envelope.system,
                        "user": rewrite_envelope.user,
                    },
                    "response": rewrite_response,
                },
            )
            text_dict = self.normalize_text_payload(
                rewrite_response,
                text_payload.model_dump(mode="json"),
                brand_name=brand_name,
                compiled_context=compiled_context,
                prompt=request.prompt,
            )
            text_payload = StructuredTextPayload(**text_dict)
            text_payload = self._repair_prompt_echo_text_payload(text_payload, prompt=request.prompt)
            report = self._validate_content_semantics(
                request=request,
                text_payload=text_payload,
                compiled_context=compiled_context,
                creative_decision=creative_decision,
            )
        return text_payload, report, attempts

    def generate(self, request: AIOrchestrationRequest) -> AIOrchestrationResponse:
        started_at = perf_counter()
        latency_ms: dict[str, float] = {}
        trace_id = request.generation_trace_id
        self._trace_payload(
            trace_id,
            self.trace,
            "orchestrator_request",
            {
                "prompt": request.prompt,
                "studio_panel": request.studio_panel,
                "template_candidates": request.template_candidates,
                "layout_decision": request.layout_decision,
                "reference_assets": request.reference_assets,
                "asset_catalog": request.asset_catalog,
                "platform_constraints": request.platform_constraints,
                "resolved_brand_context": request.resolved_brand_context,
                "persona_context": request.persona_context,
                "objective_context": request.objective_context,
                "validation_report": request.validation_report,
                "template_context": request.template_context,
                "content_format_guide": request.content_format_guide,
                "live_research": request.live_research,
                "research_editorial_brief": request.research_editorial_brief,
                "template_context_used": bool(request.template_context),
                "template_sequence_pack_slide_count": (
                    len(
                        [
                            item
                            for item in (((request.template_context or {}).get("sequence_pack") or {}) if isinstance((request.template_context or {}).get("sequence_pack"), dict) else {}).get("slides", [])
                            if isinstance(item, dict)
                        ]
                    )
                    if isinstance(request.template_context, dict)
                    else 0
                ),
            },
        )
        self._trace_event(trace_id, self.trace, "orchestrator.generate.start", {"brand_space_id": str(request.brand_space_id)})
        input_access_tracker = request.input_access_tracker if isinstance(request.input_access_tracker, InputAccessTracker) else InputAccessTracker()
        request.resolved_brand_context = input_access_tracker.wrap_source("brand_context", request.resolved_brand_context)
        request.persona_context = input_access_tracker.wrap_source("persona_context", request.persona_context)
        request.objective_context = input_access_tracker.wrap_source("objective_context", request.objective_context)
        request.retrieved_knowledge = input_access_tracker.wrap_source("retrieved_knowledge", request.retrieved_knowledge)
        request.template_context = input_access_tracker.wrap_source("template_context", request.template_context or {})
        request.content_format_guide = input_access_tracker.wrap_source("content_format_guide", request.content_format_guide or {})
        request.template_candidates = input_access_tracker.wrap_source("template_candidates", request.template_candidates)
        request.reference_assets = input_access_tracker.wrap_source("reference_assets", request.reference_assets)
        request.asset_catalog = input_access_tracker.wrap_source("asset_catalog", request.asset_catalog)
        request.logo_asset_candidates = input_access_tracker.wrap_source("logo_candidates", request.logo_asset_candidates)
        request.live_research = input_access_tracker.wrap_source("live_research", request.live_research or {})
        self.guardrails.validate_prompt(request.prompt, request.resolved_brand_context.get("guardrails", {}))
        plan_started_at = perf_counter()
        plan = self.resolution.build_plan(
            brand_context=request.resolved_brand_context,
            persona_context=request.persona_context,
            objective_context=request.objective_context,
            retrieved_knowledge=request.retrieved_knowledge,
        )
        latency_ms["resolution_ms"] = round((perf_counter() - plan_started_at) * 1000, 2)
        research_provider = self.providers.get_text_provider("research")
        generation_provider = self.providers.get_text_provider("generation")
        image_provider = self.providers.get_image_provider()

        # Initialize generation trace for decision tracking
        generation_trace = GenerationTrace(
            provider=generation_provider.__class__.__name__,
            model=get_settings().llm_model,
            fallback_used=False,
            layout_source="synthesized",  # Will be updated based on template_context
            layout_reason="Default initialization",
            background_source="synthesized",
            cta_source="text_payload",  # Will be updated if brand CTA template is used
            legal_source="none",  # Will be updated if legal assets are injected
            rag_embedding_type="openai" if get_settings().openai_api_key else "hash",
            renderer_policy="instagram_square_default",  # TODO: Extract from platform_constraints
        )

        compile_started_at = perf_counter()
        compiled_context = self.compiler.compile(
            prompt=request.prompt,
            brand_context=request.resolved_brand_context,
            persona_context=request.persona_context,
            objective_context=request.objective_context,
            ordered_knowledge=plan.ordered_knowledge,
            studio_panel=request.studio_panel,
            conversation_context=request.conversation_context,
            session_memory=request.session_memory,
            template_context=request.template_context,
            layout_decision=request.layout_decision,
            reference_assets=request.reference_assets,
            content_format_guide=request.content_format_guide,
            research_editorial_brief=request.research_editorial_brief,
            format_family_plan=request.format_family_plan,
            content_plan=request.content_plan,
            visual_plan=request.visual_plan,
            resolution_instructions=plan.instructions,
            research_summary="",
        )
        latency_ms["context_compile_ms"] = round((perf_counter() - compile_started_at) * 1000, 2)

        research_started_at = perf_counter()
        research_context_payload = {
            "brand_copy_brief": compiled_context.get("brand_copy_brief", {}),
            "audience_brief": compiled_context.get("audience_brief", {}),
            "objective_brief": compiled_context.get("objective_brief", {}),
            "knowledge_brief": compiled_context.get("knowledge_brief", []),
            "template_fit_brief": compiled_context.get("template_fit_brief", {}),
            "prompt_intelligence_brief": compiled_context.get("prompt_intelligence_brief", {}),
            "research_editorial_brief": compiled_context.get("research_editorial_brief", {}),
            "format_family_plan": compiled_context.get("format_family_plan", {}),
            "content_plan": compiled_context.get("content_plan", {}),
            "visual_plan": compiled_context.get("visual_plan", {}),
            "live_research": request.live_research,
        }
        research_summary = research_provider.generate_text(
            PromptEnvelope(
                system=(
                    "Synthesize the provided brand and audience context into a compact downstream research memo for generation. "
                    "Preserve concrete audience motivations, pain points, objections, preferences, behaviors, differentiators, proof cues, "
                    "and non-redundant specifics when present. If a research-editorial brief is active, preserve its thesis, angle, insight hierarchy, "
                    "and outline rather than collapsing the topic into generic social commentary. Keep it brand-safe, but do not genericize the audience into vague filler. "
                    "Prefer 4-6 short sentences or semicolon-separated lines with concrete guidance."
                ),
                user=(
                    f"Prompt: {request.prompt}\n"
                    f"Research context: {research_context_payload}\n"
                    f"Conflict resolution policy: {plan.instructions}"
                ),
            ),
            fallback=(
                "Preserve concrete audience motivations, pain points, objections, preferences, and retrieved knowledge in a concise brand-safe memo."
            ),
        )
        latency_ms["research_ms"] = round((perf_counter() - research_started_at) * 1000, 2)
        compiled_context["research_summary"] = research_summary
        self._trace_payload(trace_id, self.trace, "compiled_context", compiled_context)
        brand_name = request.resolved_brand_context.get("brand_name", "Violyt")
        platform_preset = request.studio_panel.get("platform_preset", "social")
        format_name = request.studio_panel.get("format", "static")
        fallback_message_strategy = self._fallback_message_strategy(request, compiled_context)
        audience_brief = self._coerce_mapping(compiled_context.get("audience_brief"))
        audience_insights = self._coerce_mapping(request.resolved_brand_context.get("audience_insights"))
        persona_context = self._coerce_mapping(request.persona_context)
        audience_research_highlights = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(audience_brief.get("research_highlights"), limit=3),
                *self._normalize_metadata_list(audience_insights.get("research_highlights"), limit=3),
            ],
            limit=3,
        )
        audience_objections = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(
                    audience_brief.get("audience_research_objections") or audience_brief.get("objections"),
                    limit=3,
                ),
                *self._normalize_metadata_list(audience_insights.get("objections"), limit=3),
            ],
            limit=3,
        )
        audience_desired_outcomes = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(audience_brief.get("desired_outcomes"), limit=3),
                *self._normalize_metadata_list(audience_insights.get("desired_outcomes"), limit=3),
            ],
            limit=3,
        )
        audience_preferences = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(audience_brief.get("preferences"), limit=3),
                *self._normalize_metadata_list(audience_insights.get("preferences"), limit=3),
            ],
            limit=3,
        )
        audience_pain_points = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(
                    audience_brief.get("audience_research_pain_points") or audience_brief.get("pain_points"),
                    limit=3,
                ),
                *self._normalize_metadata_list(audience_insights.get("pain_points"), limit=3),
            ],
            limit=3,
        )
        persona_objections = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(audience_brief.get("persona_objections"), limit=3),
                *self._normalize_metadata_list(persona_context.get("objections"), limit=3),
            ],
            limit=3,
        )
        persona_pain_points = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(audience_brief.get("persona_pain_points"), limit=3),
                *self._normalize_metadata_list(persona_context.get("pain_points"), limit=3),
                *self._normalize_metadata_list(persona_context.get("fears_and_pain_points"), limit=3),
            ],
            limit=3,
        )
        resolved_objections = audience_objections or persona_objections
        resolved_pain_points = audience_pain_points or persona_pain_points
        audience_trust_signals = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(audience_brief.get("trust_signals"), limit=3),
                *self._normalize_metadata_list(audience_insights.get("trust_signals"), limit=3),
            ],
            limit=3,
        )
        audience_proof_cues = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(audience_brief.get("proof_cues"), limit=3),
                *self._normalize_metadata_list(audience_insights.get("proof_cues"), limit=3),
            ],
            limit=3,
        )
        audience_comparison_points = self._normalize_metadata_list(
            [
                *self._normalize_metadata_list(audience_brief.get("comparison_points"), limit=3),
                *self._normalize_metadata_list(audience_insights.get("comparison_points"), limit=3),
            ],
            limit=3,
        )
        fallback_evidence_pool = [
            *audience_proof_cues,
            *audience_trust_signals,
            *audience_comparison_points,
            *audience_research_highlights,
        ]
        fallback_claim_sources = audience_desired_outcomes or [fallback_message_strategy.get("key_value_proposition")]
        fallback_claim_evidence_pairs = self._normalize_claim_evidence_pairs(
            [
                {
                    "claim": claim,
                    "evidence": fallback_evidence_pool[index:index + 1]
                    or fallback_evidence_pool[:1]
                    or [compiled_context.get("research_summary") or fallback_message_strategy.get("core_audience_message")],
                }
                for index, claim in enumerate(fallback_claim_sources[:2])
                if claim
            ],
            limit=2,
        )
        fallback_hook_type = (
            "comparison-led"
            if audience_comparison_points
            else "proof-led"
            if audience_proof_cues or audience_trust_signals or audience_research_highlights
            else "problem-solution"
            if resolved_objections or resolved_pain_points
            else "benefit-led"
            if audience_desired_outcomes or audience_preferences
            else "brand-led"
        )
        fallback_claim_evidence_lines = self._claim_evidence_pair_lines(
            fallback_claim_evidence_pairs,
            limit=2,
        )
        fallback_headline = self._fallback_headline_copy(
            prompt=request.prompt,
            claim_evidence_pairs=fallback_claim_evidence_pairs,
            desired_outcomes=audience_desired_outcomes,
            key_value_proposition=fallback_message_strategy.get("key_value_proposition"),
            headline_direction=fallback_message_strategy.get("headline_direction"),
            primary_campaign_theme=fallback_message_strategy.get("primary_campaign_theme"),
            core_audience_message=fallback_message_strategy.get("core_audience_message"),
        )
        fallback_body = self._fallback_body_copy(
            prompt=request.prompt,
            headline=fallback_headline,
            core_audience_message=fallback_message_strategy.get("core_audience_message"),
            claim_evidence_pairs=fallback_claim_evidence_pairs,
            trust_builders=audience_trust_signals[:2] or audience_proof_cues[:2],
            proof_points=audience_proof_cues[:2] or audience_research_highlights[:2],
            research_highlights=audience_research_highlights,
            supporting_copy_direction=fallback_message_strategy.get("supporting_copy_direction"),
            key_value_proposition=fallback_message_strategy.get("key_value_proposition"),
        )
        fallback_cta = self._fallback_cta_copy(
            prompt=request.prompt,
            cta_intent=fallback_message_strategy.get("cta_intent"),
            primary_goal=(compiled_context.get("objective_brief", {}) or {}).get("primary_goal"),
            topic_focus=(
                self._fallback_topic_focus(request.prompt, compiled_context=compiled_context)
                or fallback_message_strategy.get("primary_campaign_theme")
                or self._coerce_text_value(request.prompt)
            ),
            comparison_points=audience_comparison_points,
            proof_cues=audience_proof_cues,
            trust_signals=audience_trust_signals,
        )
        fallback_supporting_line = self._normalize_metadata_text(
            fallback_claim_evidence_lines[0]
            if fallback_claim_evidence_lines
            else audience_research_highlights[0]
            if audience_research_highlights
            else fallback_body,
            limit=180,
        )
        fallback_proof_points = self._normalize_metadata_list(
            [
                *fallback_claim_evidence_lines,
                *audience_proof_cues[:2],
                *audience_trust_signals[:2],
                *audience_research_highlights[:2],
            ],
            limit=4,
        )
        fallback_objection_handling_line = self._fallback_objection_handling_copy(
            objections=resolved_objections,
            pain_points=resolved_pain_points,
            proof_cues=audience_proof_cues,
            trust_signals=audience_trust_signals,
            comparison_points=audience_comparison_points,
            research_highlights=audience_research_highlights,
        )
        fallback_metadata = {
            "source": "fallback",
            "research_summary": research_summary,
            "section_label": platform_preset.replace("_", " ").title(),
            "supporting_line": fallback_supporting_line,
            "proof_points": fallback_proof_points,
            "stat_highlights": [],
            "hook_type": fallback_hook_type,
            "objection_handling": self._normalize_metadata_list(
                ([fallback_objection_handling_line] if self._looks_like_objection_response(fallback_objection_handling_line) else [])
                or ([fallback_message_strategy.get("supporting_copy_direction")] if self._looks_like_objection_response(fallback_message_strategy.get("supporting_copy_direction")) else []),
                limit=2,
            ),
            "trust_builders": audience_trust_signals[:2] or audience_proof_cues[:2] or audience_research_highlights[:2] or audience_preferences[:2],
            "claim_evidence_pairs": fallback_claim_evidence_pairs,
            "visual_direction": f"Premium brand-safe {platform_preset} visual that explains the requested content with a clear, content-specific focal concept.",
            "design_style": "editorial brand campaign creative" if format_name != "infographic" else "structured premium infographic",
            "image_prompt": f"Premium {brand_name} campaign visual with no text, built around the concrete idea in the user prompt.",
        }
        fallback_text = {
            "headline": fallback_headline,
            "body": fallback_body,
            "cta": fallback_cta,
            "hashtags": [f"#{brand_name.replace(' ', '')}"],
            "metadata": fallback_metadata,
        }
        use_image_led_social = self._should_use_image_led_social(request, compiled_context)
        generation_path = "image_led_social" if use_image_led_social else "scene_graph_social"
        message_strategy = MessageStrategyPayload.model_validate(fallback_message_strategy)
        fallback_creative_decision = self._fallback_creative_decision(request, compiled_context)
        if use_image_led_social:
            fallback_creative_decision = {
                **fallback_creative_decision,
                "layout_mode": "synthesized_layout" if not fallback_creative_decision.get("selected_template_id") else "adapted_template",
                "asset_strategy": {
                    **self._coerce_mapping(fallback_creative_decision.get("asset_strategy")),
                    "use_generated_image": True,
                    "use_template_background": False,
                    "use_brand_reference_assets": False,
                    "logo_injection_required": True,
                    "background_element": True,
                    "type_led": True,
                    "dominant_visual_system": "generated_image",
                    "template_surface_policy": "style_reference_only",
                },
            }
            message_strategy_started_at = perf_counter()
            message_strategy_envelope = self.prompts.compose_message_strategy_envelope(
                user_prompt=request.prompt,
                compiled_context=compiled_context,
                studio_panel=request.studio_panel,
            )
            self._trace_payload(
                trace_id,
                self.trace,
                "message_strategy_prompt",
                {
                    "system": message_strategy_envelope.system,
                    "user": message_strategy_envelope.user,
                    "compiled_sections": sorted(compiled_context.keys()),
                },
            )
            message_strategy_response = generation_provider.generate_structured_json(
                message_strategy_envelope,
                fallback=fallback_message_strategy,
            )
            latency_ms["message_strategy_ms"] = round((perf_counter() - message_strategy_started_at) * 1000, 2)
            self._trace_payload(trace_id, self.trace, "message_strategy_response", message_strategy_response)
            message_strategy = self.normalize_message_strategy_payload(
                message_strategy_response,
                fallback_message_strategy,
            )
            fallback_scene_graph = self._fallback_image_led_scene_graph(
                request=request,
                text_payload=fallback_text,
                creative_decision=fallback_creative_decision,
                compiled_context=compiled_context,
            )
            planning_envelope = self.prompts.compose_image_led_social_envelope(
                user_prompt=request.prompt,
                compiled_context=compiled_context,
                studio_panel=request.studio_panel,
                message_strategy=message_strategy.model_dump(mode="json"),
                validation_report=request.validation_report,
            )
        else:
            fallback_scene_graph = self._fallback_scene_graph(
                request=request,
                text_payload=fallback_text,
                creative_decision=fallback_creative_decision,
                compiled_context=compiled_context,
            )
            planning_envelope = self.prompts.compose_creative_planning_envelope(
                user_prompt=request.prompt,
                compiled_context=compiled_context,
                studio_panel=request.studio_panel,
                validation_report=request.validation_report,
            )
        self._trace_payload(
            trace_id,
            self.trace,
            "planning_prompt",
            {
                "system": planning_envelope.system,
                "user": planning_envelope.user,
                "compiled_sections": sorted(compiled_context.keys()),
                "generation_path": generation_path,
            },
        )
        text_started_at = perf_counter()
        planning_response = generation_provider.generate_structured_json(
            planning_envelope,
            fallback={
                **fallback_text,
                "creative_decision": fallback_creative_decision,
                "scene_graph": fallback_scene_graph,
            },
        )
        self._trace_payload(trace_id, self.trace, "planning_response", planning_response)
        text_dict = self.normalize_text_payload(
            planning_response,
            fallback_text,
            brand_name=brand_name,
            compiled_context=compiled_context,
            prompt=request.prompt,
        )
        text_payload = StructuredTextPayload(**text_dict)
        text_payload = self._repair_prompt_echo_text_payload(text_payload, prompt=request.prompt)
        latency_ms["text_generation_ms"] = round((perf_counter() - text_started_at) * 1000, 2)
        if not use_image_led_social and isinstance(planning_response.get("message_strategy"), dict):
            message_strategy = self.normalize_message_strategy_payload(
                planning_response.get("message_strategy"),
                fallback_message_strategy,
            )
        creative_decision = self.normalize_creative_decision_payload(
            planning_response.get("creative_decision"),
            fallback_creative_decision,
            request=request,
            compiled_context=compiled_context,
        )

        # Update generation trace with layout decision
        if creative_decision.layout_mode == "exact_template":
            generation_trace.layout_source = "brand_design_system"
            generation_trace.layout_reason = f"Using exact template: {creative_decision.selected_template_id or 'unknown'}"
        elif creative_decision.layout_mode == "adapted_template":
            generation_trace.layout_source = "reference_template"
            generation_trace.layout_reason = f"Adapted from template: {creative_decision.selected_template_id or 'unknown'}"
        else:
            generation_trace.layout_source = "synthesized"
            generation_trace.layout_reason = "No template selected, synthesizing layout from brand guidelines"

        # Update background source based on asset strategy
        asset_strategy = creative_decision.asset_strategy
        if asset_strategy.get("use_template_background"):
            generation_trace.background_source = "reference_template"
        elif asset_strategy.get("use_generated_image"):
            generation_trace.background_source = "ai_generated"
        elif asset_strategy.get("use_brand_reference_assets"):
            generation_trace.background_source = "brand_assets"

        logger.info(f"Layout source: {generation_trace.layout_source} - {generation_trace.layout_reason}")

        content_semantic_report = {
            "status": "clean",
            "repairable": False,
            "format": self._format_name_from_request(request),
            "issues": [],
            "summary": [],
            "targeted_fields": [],
            "revision_scope": {},
        }
        content_semantic_repair_attempts = 0
        if self._needs_content_semantic_validation(request):
            text_payload, content_semantic_report, content_semantic_repair_attempts = self._repair_text_payload_semantics_if_needed(
                request=request,
                generation_provider=generation_provider,
                text_payload=text_payload,
                compiled_context=compiled_context,
                message_strategy=message_strategy,
                creative_decision=creative_decision,
                brand_name=brand_name,
                trace_id=trace_id,
            )
        scene_graph = self.normalize_scene_graph_payload(
            planning_response.get("scene_graph"),
            fallback=fallback_scene_graph,
            creative_decision=creative_decision,
            text_payload=text_payload.model_dump(mode="json"),
            request=request,
            compiled_context=compiled_context,
        )

        # Update CTA source in trace
        brand_assets = request.resolved_brand_context.get("brand_assets", {})
        cta_templates = brand_assets.get("cta_templates", [])
        if cta_templates and isinstance(cta_templates, list):
            generation_trace.cta_source = "brand_cta_template"
            logger.info("CTA source: brand_cta_template")
        else:
            generation_trace.cta_source = "text_payload"
            logger.info("CTA source: text_payload (no brand CTA template available)")

        # Check for legal assets
        legal_assets = brand_assets.get("legal_text", [])
        if legal_assets:
            generation_trace.legal_source = "brand_legal_asset"
            logger.info("Legal source: brand_legal_asset")
        else:
            generation_trace.legal_source = "none"

        # Update renderer policy from platform
        platform = str(request.studio_panel.get("platform_preset", "instagram")).strip().lower()
        canvas_size = scene_graph.canvas.width if scene_graph.canvas else 1080
        generation_trace.renderer_policy = f"{platform}_{canvas_size}x{canvas_size}_default"
        logger.info(f"Renderer policy: {generation_trace.renderer_policy}")

        validation_report = self.validate_scene_graph(
            scene_graph=scene_graph,
            creative_decision=creative_decision,
            request=request,
            compiled_context=compiled_context,
        )

        # Track quality history for circuit breaker
        repair_quality_history: list[float] = []
        initial_quality = self.assess_creative_quality(
            scene_graph=scene_graph,
            creative_decision=creative_decision,
            validation_report=validation_report,
            request=request,
            selected_reference_images=[],  # Reference images not selected yet at this point
            used_support_fallback=False,
            compiled_context=compiled_context,
        )
        repair_quality_history.append(initial_quality["score"])
        logger.info(f"Initial quality score before repairs: {initial_quality['score']}")

        repair_attempts = 0
        while (
            validation_report.status != "clean"
            and validation_report.repairable
            and repair_attempts < self.SCENE_GRAPH_REPAIR_ATTEMPTS
        ):
            repair_attempts += 1

            # Cache current state before repair attempt for potential rollback
            previous_scene_graph = scene_graph.model_copy(deep=True)
            previous_creative_decision = creative_decision.model_copy(deep=True)

            repair_envelope = self.prompts.compose_scene_graph_repair_envelope(
                user_prompt=request.prompt,
                compiled_context=compiled_context,
                studio_panel=request.studio_panel,
                current_scene_graph=scene_graph.model_dump(mode="json"),
                creative_decision=creative_decision.model_dump(mode="json"),
                validation_report=validation_report.model_dump(mode="json"),
                repair_quality_history=repair_quality_history,
            )
            repair_response = generation_provider.generate_structured_json(
                repair_envelope,
                fallback={
                    "creative_decision": creative_decision.model_dump(mode="json"),
                    "scene_graph": scene_graph.model_dump(mode="json"),
                },
            )
            self._trace_payload(
                trace_id,
                self.trace,
                f"repair_{repair_attempts:02d}",
                {
                    "validation_report": validation_report.model_dump(mode="json"),
                    "prompt": {
                        "system": repair_envelope.system,
                        "user": repair_envelope.user,
                    },
                    "response": repair_response,
                },
            )
            creative_decision = self.normalize_creative_decision_payload(
                repair_response.get("creative_decision"),
                creative_decision.model_dump(mode="json"),
                request=request,
                compiled_context=compiled_context,
            )

            # CRITICAL FIX: Merge repair response into existing scene graph instead of replacing
            # LLM may return only repaired elements, not the complete scene graph
            repaired_scene_graph_dict = repair_response.get("scene_graph", {})
            merged_scene_graph_dict = self._merge_repair_into_scene_graph(
                existing_scene_graph=scene_graph.model_dump(mode="json"),
                repair_scene_graph=repaired_scene_graph_dict,
                repair_attempt=repair_attempts,
            )

            scene_graph = self.normalize_scene_graph_payload(
                merged_scene_graph_dict,
                fallback=scene_graph.model_dump(mode="json"),
                creative_decision=creative_decision,
                text_payload=text_payload.model_dump(mode="json"),
                request=request,
                compiled_context=compiled_context,
            )
            validation_report = self.validate_scene_graph(
                scene_graph=scene_graph,
                creative_decision=creative_decision,
                request=request,
                compiled_context=compiled_context,
            )

            # Quality circuit breaker: assess quality and stop if degrading
            current_quality = self.assess_creative_quality(
                scene_graph=scene_graph,
                creative_decision=creative_decision,
                validation_report=validation_report,
                request=request,
                selected_reference_images=[],  # Reference images not selected yet at this point
                used_support_fallback=False,
                compiled_context=compiled_context,
            )
            current_score = current_quality["score"]
            previous_score = repair_quality_history[-1]
            repair_quality_history.append(current_score)

            logger.info(f"Repair attempt {repair_attempts} quality: {current_score:.2f} (previous: {previous_score:.2f}, delta: {current_score - previous_score:+.2f})")

            # Circuit breaker: stop if quality degrades significantly
            if current_score < previous_score - 0.15:
                logger.warning(
                    f"Quality degraded by {previous_score - current_score:.2f} "
                    f"(from {previous_score:.2f} to {current_score:.2f}). Breaking repair loop and reverting to previous state."
                )
                # Revert to previous state
                scene_graph = previous_scene_graph
                creative_decision = previous_creative_decision
                validation_report = self.validate_scene_graph(
                    scene_graph=scene_graph,
                    creative_decision=creative_decision,
                    request=request,
                    compiled_context=compiled_context,
                )
                # Remove the degraded score from history
                repair_quality_history.pop()
                logger.info(f"Reverted to previous state with quality score: {previous_score:.2f}")
                break

        fresh_replan_attempted = False
        if self._should_apply_support_fallback(scene_graph=scene_graph, validation_report=validation_report) and self._should_request_fresh_replan(
            validation_report
        ):
            fresh_replan_attempted = True
            replan_note = self._fresh_replan_note(validation_report)
            if generation_path == "image_led_social":
                fresh_replan_envelope = self.prompts.compose_image_led_social_envelope(
                    user_prompt=request.prompt,
                    compiled_context=compiled_context,
                    studio_panel=request.studio_panel,
                    message_strategy=message_strategy.model_dump(mode="json"),
                    validation_report=validation_report.model_dump(mode="json"),
                    replan_note=replan_note,
                )
            else:
                fresh_replan_envelope = self.prompts.compose_creative_planning_envelope(
                    user_prompt=request.prompt,
                    compiled_context=compiled_context,
                    studio_panel=request.studio_panel,
                    validation_report=validation_report.model_dump(mode="json"),
                    replan_note=replan_note,
                )
            fresh_replan_response = generation_provider.generate_structured_json(
                fresh_replan_envelope,
                fallback={
                    **fallback_text,
                    "creative_decision": fallback_creative_decision,
                    "scene_graph": fallback_scene_graph,
                },
            )
            self._trace_payload(
                trace_id,
                self.trace,
                "fresh_replan_01",
                {
                    "validation_report": validation_report.model_dump(mode="json"),
                    "prompt": {
                        "system": fresh_replan_envelope.system,
                        "user": fresh_replan_envelope.user,
                    },
                    "response": fresh_replan_response,
                },
            )
            text_dict = self.normalize_text_payload(
                fresh_replan_response,
                fallback_text,
                brand_name=brand_name,
                compiled_context=compiled_context,
                prompt=request.prompt,
            )
            text_payload = StructuredTextPayload(**text_dict)
            text_payload = self._repair_prompt_echo_text_payload(text_payload, prompt=request.prompt)
            if not use_image_led_social and isinstance(fresh_replan_response.get("message_strategy"), dict):
                message_strategy = self.normalize_message_strategy_payload(
                    fresh_replan_response.get("message_strategy"),
                    fallback_message_strategy,
                )
            creative_decision = self.normalize_creative_decision_payload(
                fresh_replan_response.get("creative_decision"),
                fallback_creative_decision,
                request=request,
                compiled_context=compiled_context,
            )
            if self._needs_content_semantic_validation(request):
                text_payload, content_semantic_report, extra_semantic_attempts = self._repair_text_payload_semantics_if_needed(
                    request=request,
                    generation_provider=generation_provider,
                    text_payload=text_payload,
                    compiled_context=compiled_context,
                    message_strategy=message_strategy,
                    creative_decision=creative_decision,
                    brand_name=brand_name,
                    trace_id=trace_id,
                )
                content_semantic_repair_attempts += extra_semantic_attempts
            scene_graph = self.normalize_scene_graph_payload(
                fresh_replan_response.get("scene_graph"),
                fallback=fallback_scene_graph,
                creative_decision=creative_decision,
                text_payload=text_payload.model_dump(mode="json"),
                request=request,
                compiled_context=compiled_context,
            )
            validation_report = self.validate_scene_graph(
                scene_graph=scene_graph,
                creative_decision=creative_decision,
                request=request,
                compiled_context=compiled_context,
            )
        used_support_fallback = False
        if self._should_apply_support_fallback(scene_graph=scene_graph, validation_report=validation_report):
            issues = [issue.rule_id for issue in validation_report.issues]
            logger.warning(
                "orchestrator.generate.unresolved_scene_graph brand_space_id=%s issues=%s",
                request.brand_space_id,
                issues,
            )
            self._trace_event(
                trace_id,
                self.trace,
                "orchestrator.generate.unresolved_scene_graph",
                {"issues": issues, "generation_path": generation_path},
            )
            self._trace_payload(
                trace_id,
                self.trace,
                "validation_advisory.json",
                {
                    "issues": issues,
                    "status": validation_report.status,
                    "repair_attempts": repair_attempts,
                    "fresh_replan_attempted": fresh_replan_attempted,
                    "generation_path": generation_path,
                    "note": "Application-side validation remained unresolved, but AI rendering will continue because validation is advisory for generation.",
                },
            )
        selected_reference_images = self._select_reference_image_assets(
            request=request,
            creative_decision=creative_decision,
        )
        selected_reference_images, missing_reference_images = self._filter_available_reference_image_assets(
            selected_reference_images,
        )
        if not selected_reference_images:
            explicit_reference_images = self._scene_graph_explicit_reference_assets(
                scene_graph,
                request=request,
            )
            explicit_reference_images, explicit_missing_reference_images = self._filter_available_reference_image_assets(
                explicit_reference_images,
            )
            if explicit_reference_images:
                selected_reference_images = explicit_reference_images
            missing_reference_images.extend(explicit_missing_reference_images)
        conditioning_reference_images = self._conditioning_reference_image_assets(
            selected_reference_images,
            creative_decision=creative_decision,
            request=request,
        )
        scene_graph_reference_images = (
            conditioning_reference_images
            if self._should_use_ai_final_render(request, generation_path, creative_decision)
            else selected_reference_images
        )
        if missing_reference_images:
            missing_paths = [
                str(asset.get("storage_path") or "").strip()
                for asset in missing_reference_images
                if str(asset.get("storage_path") or "").strip()
            ]
            logger.warning(
                "orchestrator.generate.reference_assets_missing brand_space_id=%s count=%s",
                request.brand_space_id,
                len(missing_reference_images),
            )
            self._trace_payload(
                trace_id,
                self.trace,
                "missing_reference_images",
                {"count": len(missing_reference_images), "storage_paths": missing_paths},
            )
        scene_graph = self.bind_reference_assets(scene_graph, scene_graph_reference_images)
        quality_assessment = self.assess_creative_quality(
            scene_graph=scene_graph,
            creative_decision=creative_decision,
            validation_report=validation_report,
            request=request,
            selected_reference_images=scene_graph_reference_images,
            used_support_fallback=used_support_fallback,
            compiled_context=compiled_context,
        )
        quality_retry_attempts = 0
        while (
            generation_path == "image_led_social"
            and float(quality_assessment.get("score") or 0.0) < float(self.settings.image_quality_min_score or self.IMAGE_QUALITY_MIN_SCORE)
            and quality_retry_attempts < max(int(self.settings.image_quality_retry_attempts or 1), 0)
        ):
            quality_retry_attempts += 1
            quality_report = self._quality_report_from_assessment(quality_assessment)
            repair_envelope = self.prompts.compose_scene_graph_repair_envelope(
                user_prompt=request.prompt,
                compiled_context=compiled_context,
                studio_panel=request.studio_panel,
                current_scene_graph=scene_graph.model_dump(mode="json"),
                creative_decision=creative_decision.model_dump(mode="json"),
                validation_report=quality_report.model_dump(mode="json"),
            )
            repair_response = generation_provider.generate_structured_json(
                repair_envelope,
                fallback={
                    "creative_decision": creative_decision.model_dump(mode="json"),
                    "scene_graph": scene_graph.model_dump(mode="json"),
                },
            )
            self._trace_payload(
                trace_id,
                self.trace,
                f"quality_retry_{quality_retry_attempts:02d}",
                {
                    "quality_assessment": quality_assessment,
                    "validation_report": quality_report.model_dump(mode="json"),
                    "prompt": {
                        "system": repair_envelope.system,
                        "user": repair_envelope.user,
                    },
                    "response": repair_response,
                },
            )
            creative_decision = self.normalize_creative_decision_payload(
                repair_response.get("creative_decision"),
                creative_decision.model_dump(mode="json"),
                request=request,
                compiled_context=compiled_context,
            )

            # CRITICAL FIX: Merge repair response into existing scene graph instead of replacing
            # LLM may return only repaired elements, not the complete scene graph
            repaired_scene_graph_dict = repair_response.get("scene_graph", {})
            merged_scene_graph_dict = self._merge_repair_into_scene_graph(
                existing_scene_graph=scene_graph.model_dump(mode="json"),
                repair_scene_graph=repaired_scene_graph_dict,
                repair_attempt=quality_retry_attempts,
            )

            scene_graph = self.normalize_scene_graph_payload(
                merged_scene_graph_dict,
                fallback=scene_graph.model_dump(mode="json"),
                creative_decision=creative_decision,
                text_payload=text_payload.model_dump(mode="json"),
                request=request,
                compiled_context=compiled_context,
            )
            selected_reference_images = self._select_reference_image_assets(
                request=request,
                creative_decision=creative_decision,
            )
            selected_reference_images, retry_missing_reference_images = self._filter_available_reference_image_assets(
                selected_reference_images,
            )
            if not selected_reference_images:
                explicit_reference_images = self._scene_graph_explicit_reference_assets(
                    scene_graph,
                    request=request,
                )
                explicit_reference_images, explicit_missing_reference_images = self._filter_available_reference_image_assets(
                    explicit_reference_images,
                )
                if explicit_reference_images:
                    selected_reference_images = explicit_reference_images
                retry_missing_reference_images.extend(explicit_missing_reference_images)
            conditioning_reference_images = self._conditioning_reference_image_assets(
                selected_reference_images,
                creative_decision=creative_decision,
                request=request,
            )
            scene_graph_reference_images = (
                conditioning_reference_images
                if self._should_use_ai_final_render(request, generation_path, creative_decision)
                else selected_reference_images
            )
            scene_graph = self.bind_reference_assets(scene_graph, scene_graph_reference_images)
            validation_report = self.validate_scene_graph(
                scene_graph=scene_graph,
                creative_decision=creative_decision,
                request=request,
                compiled_context=compiled_context,
            )
            quality_assessment = self.assess_creative_quality(
                scene_graph=scene_graph,
                creative_decision=creative_decision,
                validation_report=validation_report,
                request=request,
                selected_reference_images=scene_graph_reference_images,
                used_support_fallback=used_support_fallback,
                compiled_context=compiled_context,
            )
        self.guardrails.validate_output(
            f"{text_payload.headline}\n{text_payload.body}\n{text_payload.cta}",
            request.resolved_brand_context.get("guardrails", {}),
        )

        scene_graph_ignored_for_final_render = self._should_ignore_scene_graph_for_final_render(
            generation_path=generation_path,
            fresh_replan_attempted=fresh_replan_attempted,
            validation_report=validation_report,
            scene_graph=scene_graph,
            compiled_context=compiled_context,
        )
        final_render_scene_graph = scene_graph
        final_render_retry_note: str | None = None
        if scene_graph_ignored_for_final_render:
            final_render_retry_note = self._final_render_ignore_note(validation_report)
            final_render_scene_graph_payload = self._fallback_image_led_scene_graph(
                request=request,
                text_payload=text_payload.model_dump(mode="json"),
                creative_decision=creative_decision.model_dump(mode="json"),
                compiled_context=compiled_context,
            )
            final_render_scene_graph = self.normalize_scene_graph_payload(
                final_render_scene_graph_payload,
                fallback=fallback_scene_graph,
                creative_decision=creative_decision,
                text_payload=text_payload.model_dump(mode="json"),
                request=request,
                compiled_context=compiled_context,
            )
            self._trace_payload(
                trace_id,
                self.trace,
                "final_render_scene_graph_override",
                {
                    "reason": "scene_graph_rejected_after_fresh_replan",
                    "issues": [issue.rule_id for issue in validation_report.issues],
                    "retry_note": final_render_retry_note,
                    "scene_graph": final_render_scene_graph.model_dump(mode="json"),
                },
            )

        visual_explanation_plan = self._visual_explanation_plan(
            request,
            text_payload,
            creative_decision,
            selected_reference_images,
            message_strategy,
        )
        if self._should_block_low_quality_final_render(quality_assessment):
            self._trace_payload(
                trace_id,
                self.trace,
                "final_render_blocked_low_quality",
                {
                    "quality_assessment": quality_assessment,
                    "reason": "quality_below_hard_threshold_before_render",
                },
            )
            raise GenerationFailureError(
                "Final render blocked because the planned creative is still below the minimum premium-quality threshold.",
                failure_type="validation_failure",
                reason_code="final_render_quality_blocked",
                user_safe_message="The current creative draft did not meet the minimum quality threshold, so generation was stopped instead of returning a weak result.",
                retryable=True,
                suggested_next_action="Refine the scene graph, reference conditioning, or slide structure and try generation again.",
                details={"quality_assessment": quality_assessment},
            )
        self._trace_payload(
            trace_id,
            self.trace,
            "visual_explanation_plan",
            visual_explanation_plan,
        )

        tone_started_at = perf_counter()
        tone_analysis = self.tone.evaluate(
            content=f"{text_payload.headline}. {text_payload.body}. {text_payload.cta}",
            brand_context=request.resolved_brand_context,
            persona_context=request.persona_context,
            content_payload=text_payload.model_dump(mode="json"),
            message_strategy=message_strategy.model_dump(mode="json"),
            objective_context=request.objective_context,
        )
        latency_ms["tone_ms"] = round((perf_counter() - tone_started_at) * 1000, 2)

        blueprint_started_at = perf_counter()
        blueprint = self.blueprints.from_scene_graph(
            scene_graph=final_render_scene_graph if scene_graph_ignored_for_final_render else scene_graph,
            studio_panel=request.studio_panel,
            text_payload=text_payload.model_dump(mode="json"),
            brand_rules_applied=BlueprintService._brand_rules_applied(request.resolved_brand_context),
        )
        latency_ms["blueprint_ms"] = round((perf_counter() - blueprint_started_at) * 1000, 2)

        generated_assets: list[GeneratedImageAsset] = []
        final_render_assets: list[GeneratedImageAsset] = []
        final_render_asset: GeneratedImageAsset | None = None
        render_authority = "backend"
        image_generation_error: str | None = None
        image_size = self._image_generation_size(request.studio_panel)
        is_carousel_render = str(request.studio_panel.get("format") or "").strip().lower() == "carousel"
        carousel_slide_specs = (
            self._build_carousel_slide_specs(
                text_payload,
                request=request,
                creative_decision=creative_decision,
            )
            if is_carousel_render
            else []
        )
        if carousel_slide_specs:
            text_payload = text_payload.model_copy(
                update={
                    "metadata": {
                        **(text_payload.metadata or {}),
                        "carousel_slide_specs": carousel_slide_specs,
                    }
                }
            )
        ai_final_render_required = self._should_use_ai_final_render(request, generation_path, creative_decision)
        if ai_final_render_required:
            try:
                final_render_started_at = perf_counter()
                slide_specs = (
                    carousel_slide_specs
                    if is_carousel_render
                    else [
                        {
                            "role": "single",
                            "headline": text_payload.headline,
                            "supporting_line": (text_payload.metadata or {}).get("supporting_line") or text_payload.body,
                            "proof_points": self._normalize_metadata_list((text_payload.metadata or {}).get("proof_points"), limit=3),
                            "cta": text_payload.cta,
                            "slide_index": 1,
                            "slide_count": 1,
                        }
                    ]
                )
                logo_storage_path, requested_logo_variant = self._select_logo_candidate_for_render(
                    request=request,
                    creative_decision=creative_decision,
                    scene_graph=final_render_scene_graph,
                )
                exact_logo_overlay_required = bool(logo_storage_path and self.storage.exists(logo_storage_path))
                prompt_reference_images = list(conditioning_reference_images)
                conditioning_reference_images, skipped_logo_reference_images = self._filter_logo_bearing_conditioning_reference_images(
                    conditioning_reference_images,
                    exact_logo_overlay_required=exact_logo_overlay_required,
                )
                topic_reference_images = self._topic_relevant_reference_assets(
                    request,
                    creative_decision=creative_decision,
                    limit=2,
                )
                if topic_reference_images:
                    prompt_reference_images = self._merge_reference_asset_lists(topic_reference_images, prompt_reference_images)
                    conditioning_reference_images = self._merge_reference_asset_lists(
                        topic_reference_images,
                        conditioning_reference_images,
                    )
                if skipped_logo_reference_images:
                    prompt_reference_images = [*conditioning_reference_images, *skipped_logo_reference_images]
                    self._trace_payload(
                        trace_id,
                        self.trace,
                        "final_render_logo_bearing_reference_images_skipped",
                        {
                            "reason": "exact_logo_overlay_requires_logo_free_conditioning",
                            "skipped_storage_paths": [
                                str(asset.get("storage_path") or "")
                                for asset in skipped_logo_reference_images
                            ],
                            "logo_storage_path": logo_storage_path,
                        },
                    )
                pdf_reference_conditioning_cache: dict[str, str] = {}
                for slide in slide_specs:
                    slide_index = int(slide.get("slide_index") or 1)
                    slide_count = int(slide.get("slide_count") or len(slide_specs))
                    trace_suffix = f"_slide_{slide_index:02d}" if is_carousel_render else ""
                    slide_prompt_reference_images = (
                        self._slide_reference_images(
                            slide,
                            prompt_reference_images,
                            request=request,
                            creative_decision=creative_decision,
                        )
                        if is_carousel_render
                        else [dict(asset) for asset in prompt_reference_images if isinstance(asset, dict)]
                    )
                    slide_conditioning_reference_images = (
                        self._slide_reference_images(
                            slide,
                            conditioning_reference_images,
                            request=request,
                            creative_decision=creative_decision,
                        )
                        if is_carousel_render
                        else [dict(asset) for asset in conditioning_reference_images if isinstance(asset, dict)]
                    )
                    slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
                    desired_reference_path = str(slide_metadata.get("reference_asset_path") or "").strip()
                    if desired_reference_path and not slide_prompt_reference_images:
                        matched_reference_asset = self._reference_asset_by_storage_path(request, desired_reference_path)
                        if matched_reference_asset is not None:
                            slide_prompt_reference_images = [matched_reference_asset]
                    if desired_reference_path and not slide_conditioning_reference_images:
                        matched_reference_asset = self._reference_asset_by_storage_path(request, desired_reference_path)
                        if (
                            matched_reference_asset is not None
                            and self._is_conditioning_safe_reference_image_asset(
                                matched_reference_asset,
                                creative_decision=creative_decision,
                                request=request,
                            )
                        ):
                            slide_conditioning_reference_images = [matched_reference_asset]
                    if (
                        is_carousel_render
                        and not slide_conditioning_reference_images
                        and not str(slide_metadata.get("reference_asset_path") or "").strip()
                    ):
                        slide_conditioning_reference_images = [
                            dict(asset) for asset in conditioning_reference_images if isinstance(asset, dict)
                        ]
                    reference_image_paths = self._conditioning_reference_image_paths(
                        slide_conditioning_reference_images,
                        request=request,
                        cache=pdf_reference_conditioning_cache,
                    )
                    if is_carousel_render:
                        final_render_prompt = self.build_carousel_slide_render_prompt(
                            request=request,
                            creative_decision=creative_decision,
                            message_strategy=message_strategy,
                            slide=slide,
                            scene_graph=final_render_scene_graph,
                            reference_images=slide_prompt_reference_images,
                            retry_note=final_render_retry_note,
                            visual_explanation_plan=visual_explanation_plan,
                            compiled_context=compiled_context,
                        )
                    else:
                        final_render_prompt = self.build_final_render_prompt(
                            request=request,
                            text_payload=text_payload,
                            creative_decision=creative_decision,
                            scene_graph=final_render_scene_graph,
                            message_strategy=message_strategy,
                            reference_images=prompt_reference_images,
                            retry_note=final_render_retry_note,
                            visual_explanation_plan=visual_explanation_plan,
                            compiled_context=compiled_context,
                        )
                    self._trace_payload(
                        trace_id,
                        self.trace,
                        f"final_render_prompt{trace_suffix}",
                        {
                            "prompt": final_render_prompt,
                            "size": image_size,
                            "model": self.settings.image_model,
                            "prompt_length": len(final_render_prompt),
                            "text_overlay_strategy": (
                                "ai_renders_approved_text_and_layout"
                                if is_carousel_render
                                else "backend_exact_text_on_ai_text_safe_substrate"
                            ),
                            "slide_index": slide_index,
                            "slide_count": slide_count,
                            "role": slide.get("role"),
                        },
                    )
                    if reference_image_paths:
                        asset = self._edit_image_with_retries(
                            image_provider=image_provider,
                            tenant_id=request.tenant_id,
                            brand_space_id=request.brand_space_id,
                            prompt=final_render_prompt,
                            image_paths=reference_image_paths,
                            size=image_size,
                            mask_png_bytes=None,
                            trace_id=trace_id,
                            trace_label=f"final_render_conditioned_generation{trace_suffix}",
                        )
                    else:
                        asset = self._generate_image_with_retries(
                            image_provider=image_provider,
                            tenant_id=request.tenant_id,
                            brand_space_id=request.brand_space_id,
                            prompt=final_render_prompt,
                            size=image_size,
                            trace_id=trace_id,
                            trace_label=f"final_render_generation{trace_suffix}",
                        )
                    base_asset = GeneratedImageAsset(
                        asset_id=uuid4(),
                        mime_type=asset["mime_type"],
                        storage_path=asset["storage_path"],
                        width=asset["width"],
                        height=asset["height"],
                        asset_role=asset["asset_role"],
                        metadata={
                            "provider": asset.get("provider"),
                            "model": asset.get("model") or self.settings.image_model,
                            "requested_size": asset.get("size", image_size),
                            "generation_path": generation_path,
                            "generation_stage": "base_final_render",
                            "reference_conditioned": bool(reference_image_paths),
                            "slide_index": slide_index,
                            "slide_count": slide_count,
                            "carousel_role": slide.get("role"),
                        },
                    )
                    slide_text_payload = StructuredTextPayload(
                        headline=str(slide.get("headline") or text_payload.headline),
                        body=self._carousel_slide_body_text(
                            slide,
                            fallback_text=str(slide.get("supporting_line") or text_payload.body),
                        ),
                        cta=str(slide.get("cta") or text_payload.cta),
                        hashtags=text_payload.hashtags,
                        metadata={
                            **(text_payload.metadata or {}),
                            "source": (
                                "structured_slide_spec"
                                if any(
                                    str(slide.get(field) or "").strip()
                                    for field in ("headline", "supporting_line", "body", "visual_focus", "cta")
                                )
                                or bool(slide.get("proof_points") or slide.get("body_points") or slide.get("stat_highlights"))
                                else str(((text_payload.metadata or {}) if isinstance(text_payload.metadata, dict) else {}).get("source") or "fallback")
                            ),
                            "supporting_line": str(slide.get("supporting_line") or text_payload.body),
                            "proof_points": list(slide.get("proof_points") or []),
                            "body_points": list(slide.get("body_points") or []),
                            "stat_highlights": list(slide.get("stat_highlights") or []),
                            "visual_focus": str(slide.get("visual_focus") or ""),
                            "transition_note": str(slide.get("transition_note") or ""),
                            "slide_role": str(slide.get("role") or ""),
                            "slide_index": slide_index,
                            "slide_count": slide_count,
                        },
                    )
                    final_asset_payload = asset
                    final_asset_metadata = {
                        "render_source": "ai",
                        "generation_stage": "final_render",
                        "provider": asset.get("provider"),
                        "model": asset.get("model") or self.settings.image_model,
                        "prompt_length": len(final_render_prompt),
                        "text_overlay_strategy": (
                            "ai_renders_approved_text_and_layout"
                            if is_carousel_render
                            else "backend_exact_text_on_ai_text_safe_substrate"
                        ),
                        "requested_size": asset.get("size", image_size),
                        "generation_path": generation_path,
                        "layout_mode": creative_decision.layout_mode,
                        "scene_graph_used": not scene_graph_ignored_for_final_render,
                        "scene_graph_used": not scene_graph_ignored_for_final_render,
                        "scene_graph_ignored_for_final_render": scene_graph_ignored_for_final_render,
                        "logo_composited_by_ai": False,
                        "base_storage_path": base_asset.storage_path,
                        "reference_conditioned_by_ai": bool(reference_image_paths),
                        "reference_image_storage_paths": [str(reference_asset.get("storage_path") or "") for reference_asset in slide_conditioning_reference_images],
                        "logo_bearing_reference_image_storage_paths_skipped": [str(reference_asset.get("storage_path") or "") for reference_asset in skipped_logo_reference_images],
                        "visual_explanation_mode": visual_explanation_plan.get("mode"),
                        "visual_explanation_need": visual_explanation_plan.get("need"),
                        "visual_explanation_density": visual_explanation_plan.get("density"),
                        "visual_explanation_rationale": visual_explanation_plan.get("rationale"),
                        "quality_assessment": quality_assessment,
                        "quality_retry_attempts": quality_retry_attempts,
                        "slide_index": slide_index,
                        "slide_count": slide_count,
                        "carousel_role": slide.get("role"),
                    }
                    if not is_carousel_render:
                        filtered_scene = final_render_scene_graph.model_copy(deep=True)
                        filtered_scene.elements = [e for e in filtered_scene.elements if e.role in ("legal", "footer", "disclaimer")]
                        final_asset_metadata["render_overlay_scene_graph"] = filtered_scene.model_dump(mode="json")
                        
                        filtered_text = slide_text_payload.model_copy(deep=True)
                        filtered_metadata = (filtered_text.metadata or {}).copy()
                        filtered_text.metadata = filtered_metadata
                        final_asset_metadata["render_overlay_text"] = filtered_text.model_dump(mode="json")
                    if requested_logo_variant:
                        final_asset_metadata["requested_logo_variant"] = requested_logo_variant
                    if logo_storage_path and self.storage.exists(logo_storage_path):
                        final_asset_metadata["logo_source_storage_path"] = logo_storage_path
                        final_asset_metadata["logo_overlay_strategy"] = "exact_asset_overlay"
                        self._trace_payload(
                            trace_id,
                            self.trace,
                            f"logo_overlay_deferred_to_export{trace_suffix}",
                            {
                                "reason": "preserve_exact_logo_asset",
                                "logo_storage_path": logo_storage_path,
                                "requested_logo_variant": requested_logo_variant,
                                "base_storage_path": base_asset.storage_path,
                                "slide_index": slide_index,
                                "slide_count": slide_count,
                            },
                        )
                    final_render_assets.append(
                        GeneratedImageAsset(
                            asset_id=uuid4(),
                            mime_type=final_asset_payload["mime_type"],
                            storage_path=final_asset_payload["storage_path"],
                            width=final_asset_payload["width"],
                            height=final_asset_payload["height"],
                            asset_role="render_preview" if slide_index == 1 else "render_export",
                            metadata=final_asset_metadata,
                        )
                    )
                latency_ms["final_render_ms"] = round((perf_counter() - final_render_started_at) * 1000, 2)
                final_render_asset = final_render_assets[0] if final_render_assets else None
                render_authority = "ai"
                self._trace_payload(
                    trace_id,
                    self.trace,
                    "final_render_generation",
                    {
                        "slide_count": len(final_render_assets),
                        "assets": [asset.model_dump(mode="json") for asset in final_render_assets],
                    },
                )
            except Exception as exc:  # pragma: no cover - resilience path
                image_generation_error = str(exc)
                latency_ms["final_render_ms"] = round(latency_ms.get("final_render_ms", 0.0), 2)
                logger.warning(
                    "orchestrator.generate.final_render_failed brand_space_id=%s error=%s",
                    request.brand_space_id,
                    image_generation_error,
                )
                self._trace_payload(trace_id, self.trace, "final_render_error", {"error": image_generation_error})
        if ai_final_render_required and final_render_asset is None:
            raise GenerationFailureError(
                self._ai_final_render_failure_message(),
                failure_type="provider_failure",
                reason_code="ai_final_render_failed",
                user_safe_message="I couldn't generate the visual this time. Please regenerate.",
                retryable=True,
                rule_source="system",
                suggested_next_action="Regenerate the creative.",
                details={
                    "generation_path": generation_path,
                    "underlying_error": image_generation_error,
                },
            )
        if (
            self._image_generation_requested(request)
            and not ai_final_render_required
            and final_render_asset is None
            and self._needs_generated_image_with_storage(scene_graph, creative_decision)
        ):
            try:
                image_started_at = perf_counter()
                image_prompt = self.build_image_prompt(
                    request,
                    text_payload,
                    creative_decision,
                    message_strategy,
                    compiled_context=compiled_context,
                    visual_explanation_plan=visual_explanation_plan,
                )
                self._trace_payload(trace_id, self.trace, "image_prompt", {"prompt": image_prompt})
                asset = self._generate_image_with_retries(
                    image_provider=image_provider,
                    tenant_id=request.tenant_id,
                    brand_space_id=request.brand_space_id,
                    prompt=image_prompt,
                    size=image_size,
                    trace_id=trace_id,
                    trace_label="image_generation",
                )
                latency_ms["image_generation_ms"] = round((perf_counter() - image_started_at) * 1000, 2)
                self._trace_payload(trace_id, self.trace, "image_generation", asset)
                generated_assets.append(
                    GeneratedImageAsset(
                        asset_id=uuid4(),
                        mime_type=asset["mime_type"],
                        storage_path=asset["storage_path"],
                        width=asset["width"],
                        height=asset["height"],
                        asset_role=asset["asset_role"],
                        metadata={
                            "provider": asset.get("provider"),
                            "requested_size": asset.get("size", image_size),
                            "generation_path": generation_path,
                            "visual_explanation_mode": visual_explanation_plan.get("mode"),
                            "visual_explanation_need": visual_explanation_plan.get("need"),
                            "visual_explanation_density": visual_explanation_plan.get("density"),
                            "visual_explanation_rationale": visual_explanation_plan.get("rationale"),
                        },
                    )
                )
            except Exception as exc:  # pragma: no cover - resilience path
                image_generation_error = str(exc)
                latency_ms["image_generation_ms"] = round(latency_ms.get("image_generation_ms", 0.0), 2)
                logger.warning(
                    "orchestrator.generate.image_failed brand_space_id=%s error=%s",
                    request.brand_space_id,
                    image_generation_error,
                )
                self._trace_payload(trace_id, self.trace, "image_generation_error", {"error": image_generation_error})
        scene_graph = self.bind_generated_assets(scene_graph, generated_assets)
        blueprint = self.blueprints.from_scene_graph(
            scene_graph=scene_graph,
            studio_panel=request.studio_panel,
            text_payload=text_payload.model_dump(mode="json"),
            brand_rules_applied=BlueprintService._brand_rules_applied(request.resolved_brand_context),
        )

        explainability = {
            "retrieval_channels": [channel for channel, items in request.retrieved_knowledge.items() if items],
            "retrieval_match_counts": {
                channel: len(items)
                for channel, items in request.retrieved_knowledge.items()
            },
            "guardrails_applied": request.resolved_brand_context.get("guardrails", {}),
            "selected_persona": request.persona_context,
            "selected_objective": request.objective_context,
            "brand_context_snapshot": request.resolved_brand_context,
            "research_summary": research_summary,
            "conversation_context": request.conversation_context,
            "session_memory": request.session_memory,
            "template_context_used": bool(request.template_context),
            "context_resolution": plan.metadata,
            "generation_path": generation_path,
            "message_strategy": message_strategy.model_dump(mode="json"),
            "layout_decision": creative_decision.model_dump(mode="json"),
            "creative_decision": creative_decision.model_dump(mode="json"),
            "scene_graph": scene_graph.model_dump(mode="json"),
            "final_render_scene_graph": final_render_scene_graph.model_dump(mode="json") if scene_graph_ignored_for_final_render else None,
            "validation_report": validation_report.model_dump(mode="json"),
            "content_semantic_validation": content_semantic_report,
            "content_semantic_repair_attempts": content_semantic_repair_attempts,
            "repair_attempts": repair_attempts,
            "fresh_replan_attempted": fresh_replan_attempted,
            "scene_graph_ignored_for_final_render": scene_graph_ignored_for_final_render,
            "render_authority": render_authority,
            "planning_hints": request.layout_decision,
            "compiled_context": compiled_context,
            "visual_grounding": compiled_context.get("visual_grounding_diagnostics")
            or compiled_context.get("visual_knowledge_brief")
            or {},
            "selected_reference_images": selected_reference_images,
            "conditioning_reference_images": conditioning_reference_images,
            "visual_explanation_plan": visual_explanation_plan,
            "visual_explanation_mode": visual_explanation_plan.get("mode"),
            "visual_explanation_need": visual_explanation_plan.get("need"),
            "visual_explanation_density": visual_explanation_plan.get("density"),
            "quality_assessment": quality_assessment,
            "quality_retry_attempts": quality_retry_attempts,
            "providers": {
                "research": research_provider.provider_name,
                "generation": generation_provider.provider_name,
                "image": image_provider.provider_name,
            },
            "generation_trace": generation_trace.model_dump(mode="json"),
            "input_access_summary": input_access_tracker.build_summary(),
        }
        explainability["token_usage"] = self.estimate_token_usage(
            input_segments=[
                json.dumps(message_strategy.model_dump(mode="json"), default=str),
                planning_envelope.system,
                planning_envelope.user,
                research_summary,
                json.dumps(request.reference_assets, default=str),
                json.dumps(selected_reference_images, default=str),
            ],
            output_segments=[
                text_payload.headline,
                text_payload.body,
                text_payload.cta,
                " ".join(text_payload.hashtags),
                json.dumps(text_payload.metadata, default=str),
            ],
        )
        explainability["latency_ms"] = {
            **latency_ms,
            "total_ms": round((perf_counter() - started_at) * 1000, 2),
        }
        explainability["generation_trace_id"] = trace_id
        if image_generation_error:
            explainability["image_generation_error"] = image_generation_error
        if final_render_asset is not None:
            explainability["final_render_asset"] = final_render_asset.model_dump(mode="json")
        if final_render_assets:
            explainability["final_render_assets"] = [
                asset.model_dump(mode="json") for asset in final_render_assets
            ]
        self._trace_payload(
            trace_id,
            self.trace,
            "orchestrator_final",
            {
                "message_strategy": message_strategy.model_dump(mode="json"),
                "text": text_payload.model_dump(mode="json"),
                "creative_decision": creative_decision.model_dump(mode="json"),
                "scene_graph": scene_graph.model_dump(mode="json"),
                "validation_report": validation_report.model_dump(mode="json"),
                "content_semantic_validation": content_semantic_report,
                "content_semantic_repair_attempts": content_semantic_repair_attempts,
                "blueprint": blueprint.model_dump(mode="json"),
                "image_assets": [asset.model_dump(mode="json") for asset in generated_assets],
                "final_render_asset": final_render_asset.model_dump(mode="json") if final_render_asset else None,
                "final_render_assets": [asset.model_dump(mode="json") for asset in final_render_assets],
                "render_authority": render_authority,
                "explainability": explainability,
                "tone_analysis": tone_analysis,
            },
        )
        return AIOrchestrationResponse(
            message_strategy=message_strategy,
            text=text_payload,
            creative_decision=creative_decision,
            scene_graph=scene_graph,
            validation_report=validation_report,
            repair_attempts=repair_attempts,
            blueprint=BlueprintPayload(**blueprint.model_dump()),
            image_assets=generated_assets,
            final_render_assets=final_render_assets,
            final_render_asset=final_render_asset,
            render_authority=render_authority,
            explainability=explainability,
            tone_analysis=tone_analysis,
            generation_trace=generation_trace,
        )

    @staticmethod
    def normalize_text_payload(
        text_dict: dict,
        fallback: dict,
        brand_name: str | None = None,
        compiled_context: dict[str, Any] | None = None,
        prompt: str | None = None,
    ) -> dict:
        normalized = dict(fallback)
        normalized.update(text_dict or {})

        hashtags = normalized.get("hashtags")
        if isinstance(hashtags, str):
            tokens = re.split(r"[\s,]+", hashtags.strip())
            normalized["hashtags"] = [token for token in tokens if token]
        elif isinstance(hashtags, tuple):
            normalized["hashtags"] = list(hashtags)
        elif not isinstance(hashtags, list):
            normalized["hashtags"] = list(fallback.get("hashtags", []))

        normalized["hashtags"] = [
            str(tag).strip()
            for tag in normalized["hashtags"]
            if str(tag).strip()
        ]

        for field in ("headline", "body", "cta"):
            normalized[field] = AIOrchestratorService._coerce_text_value(
                normalized.get(field),
                fallback.get(field, ""),
            )

        metadata = normalized.get("metadata")
        normalized["metadata"] = AIOrchestratorService.normalize_metadata_payload(
            metadata,
            fallback.get("metadata", {}),
            body=normalized.get("body"),
            brand_name=brand_name,
            compiled_context=compiled_context,
        )
        research_editorial_brief = (
            compiled_context.get("research_editorial_brief")
            if isinstance(compiled_context, dict) and isinstance(compiled_context.get("research_editorial_brief"), dict)
            else {}
        )
        normalized = ResearchEditorialPlanningService.enforce_source_backing(
            normalized,
            prompt_text=str(prompt or ""),
            brief=research_editorial_brief,
        )

        return normalized

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if value > 0 else None
        text = str(value or "").strip()
        return int(text) if text.isdigit() and int(text) > 0 else None

    @classmethod
    def _rough_collection_length(cls, value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, str):
            chunks = cls._normalize_metadata_list(value, limit=64)
            return len(chunks)
        if isinstance(value, dict):
            return len(
                [
                    item
                    for item in value.values()
                    if item is not None and item != "" and item != [] and item != {}
                ]
            )
        if isinstance(value, (list, tuple, set)):
            return len(
                [
                    item
                    for item in value
                    if item is not None and item != "" and item != [] and item != {}
                ]
            )
        return 1

    @classmethod
    def _dynamic_metadata_limits(
        cls,
        *,
        metadata: dict[str, Any],
        body: str | None = None,
        compiled_context: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        content_format_brief = (
            compiled_context.get("content_format_brief")
            if isinstance(compiled_context, dict) and isinstance(compiled_context.get("content_format_brief"), dict)
            else {}
        )
        format_name = str(content_format_brief.get("format") or "").strip().casefold()
        preferred_slide_count = cls._int_or_none(
            metadata.get("preferred_slide_count")
            or metadata.get("slide_count")
            or content_format_brief.get("preferred_slide_count")
        )
        sentence_count = len(cls._sentences(body))
        proof_count = cls._rough_collection_length(metadata.get("proof_points"))
        stat_count = cls._rough_collection_length(metadata.get("stat_highlights"))
        objection_count = cls._rough_collection_length(metadata.get("objection_handling"))
        trust_count = cls._rough_collection_length(metadata.get("trust_builders"))
        claim_count = cls._rough_collection_length(metadata.get("claim_evidence_pairs"))
        if format_name == "carousel":
            story_span = max(
                preferred_slide_count or 0,
                sentence_count,
                proof_count,
                stat_count,
                trust_count,
            )
            return {
                "proof_points": max(proof_count, sentence_count, (preferred_slide_count or 0) * 2, max(story_span, 4)),
                "stat_highlights": max(stat_count, preferred_slide_count or 0, min(sentence_count, max(story_span, 3))),
                "objection_handling": max(objection_count, preferred_slide_count or 0, 3),
                "trust_builders": max(trust_count, preferred_slide_count or 0, 4),
                "claim_evidence_pairs": max(claim_count, preferred_slide_count or 0, 3),
            }
        if format_name == "infographic":
            info_span = max(sentence_count, proof_count, stat_count, preferred_slide_count or 0)
            return {
                "proof_points": max(proof_count, info_span, 4),
                "stat_highlights": max(stat_count, preferred_slide_count or 0, 4),
                "objection_handling": max(objection_count, 3),
                "trust_builders": max(trust_count, 4),
                "claim_evidence_pairs": max(claim_count, 3),
            }
        return {
            "proof_points": max(proof_count, min(max(sentence_count, 1), 6), 3),
            "stat_highlights": max(stat_count, min(sentence_count, 4), 2),
            "objection_handling": max(objection_count, 3),
            "trust_builders": max(trust_count, 3),
            "claim_evidence_pairs": max(claim_count, 3),
        }

    @staticmethod
    def normalize_metadata_payload(
        metadata: Any,
        fallback: dict[str, Any],
        body: str | None = None,
        brand_name: str | None = None,
        compiled_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base = dict(fallback or {})
        if isinstance(metadata, dict):
            merged_metadata = dict(metadata)
            if isinstance(base.get("carousel_slide_specs"), list) and isinstance(metadata.get("carousel_slide_specs"), list):
                merged_metadata["carousel_slide_specs"] = AIOrchestratorService._merge_partial_sequence_specs(
                    metadata.get("carousel_slide_specs"),
                    base.get("carousel_slide_specs"),
                    number_keys=("slide_number", "slide_index"),
                )
            if isinstance(base.get("infographic_section_specs"), list) and isinstance(metadata.get("infographic_section_specs"), list):
                merged_metadata["infographic_section_specs"] = AIOrchestratorService._merge_partial_sequence_specs(
                    metadata.get("infographic_section_specs"),
                    base.get("infographic_section_specs"),
                    number_keys=("section_number", "index"),
                )
            base.update(merged_metadata)

        limits = AIOrchestratorService._dynamic_metadata_limits(
            metadata=base,
            body=body,
            compiled_context=compiled_context,
        )
        base["proof_points"] = AIOrchestratorService._normalize_metadata_list(
            base.get("proof_points"),
            limit=limits["proof_points"],
        )
        base["stat_highlights"] = AIOrchestratorService._normalize_metadata_list(
            base.get("stat_highlights"),
            limit=limits["stat_highlights"],
        )
        base["hook_type"] = AIOrchestratorService._normalize_metadata_text(base.get("hook_type"), limit=40)
        base["objection_handling"] = AIOrchestratorService._normalize_metadata_list(
            base.get("objection_handling"),
            limit=limits["objection_handling"],
        )
        research_claim_pairs = AIOrchestratorService._claim_evidence_pairs_from_research_brief(
            (compiled_context or {}).get("research_editorial_brief"),
            limit=limits["claim_evidence_pairs"],
        )
        base["claim_evidence_pairs"] = AIOrchestratorService._merge_claim_evidence_pairs(
            base.get("claim_evidence_pairs"),
            research_claim_pairs,
            limit=limits["claim_evidence_pairs"],
        )
        base["trust_builders"] = AIOrchestratorService._normalize_metadata_list(
            base.get("trust_builders"),
            limit=limits["trust_builders"],
        )
        claim_evidence_lines = AIOrchestratorService._claim_evidence_pair_lines(
            base["claim_evidence_pairs"],
            limit=limits["claim_evidence_pairs"],
        )

        sentences = AIOrchestratorService._sentences(body)
        if not base["proof_points"] and claim_evidence_lines:
            base["proof_points"] = claim_evidence_lines[: limits["proof_points"]]
        if not base["proof_points"] and base["trust_builders"]:
            base["proof_points"] = base["trust_builders"][: limits["proof_points"]]
        if not base["proof_points"] and sentences:
            base["proof_points"] = sentences[: limits["proof_points"]]

        supporting_line = (
            base.get("supporting_line")
            or base.get("subheadline")
            or (claim_evidence_lines[0] if claim_evidence_lines else "")
            or (base["trust_builders"][0] if base["trust_builders"] else "")
            or (sentences[0] if sentences else (base["proof_points"][0] if base["proof_points"] else ""))
        )
        base["supporting_line"] = AIOrchestratorService._normalize_metadata_text(supporting_line, limit=180)
        base["subheadline"] = AIOrchestratorService._normalize_metadata_text(base.get("subheadline"), limit=110)
        base["section_label"] = AIOrchestratorService._normalize_metadata_text(
            base.get("section_label") or base.get("campaign_label") or brand_name or "",
            limit=26,
        )
        base["logo_position"] = AIOrchestratorService._normalize_metadata_text(base.get("logo_position"), limit=40)
        base["logo_background_tone"] = AIOrchestratorService._normalize_logo_background_tone(
            base.get("logo_background_tone")
        )
        base["visual_direction"] = AIOrchestratorService._normalize_metadata_text(
            base.get("visual_direction"),
            limit=180,
        )
        base["design_style"] = AIOrchestratorService._normalize_metadata_text(base.get("design_style"), limit=80)
        base["image_prompt"] = AIOrchestratorService._normalize_metadata_text(base.get("image_prompt"), limit=220)

        colors = base.get("brand_colors") or base.get("colors")
        if isinstance(colors, dict):
            base["brand_colors"] = {str(key): str(value) for key, value in colors.items()}

        base, _ = AIOrchestratorService._sanitize_visual_metadata_fields(
            base,
            compiled_context=compiled_context,
        )
        format_name = AIOrchestratorService._normalized_output_format_name(compiled_context)
        if format_name == "static":
            base = AIOrchestratorService._repair_static_metadata_semantics(
                base,
                body=body or "",
            )
        elif format_name == "infographic":
            base = AIOrchestratorService._repair_infographic_metadata_semantics(
                base,
                body=body or "",
            )

        return base

    @staticmethod
    def _normalized_output_format_name(compiled_context: dict[str, Any] | None) -> str:
        content_format_brief = (compiled_context or {}).get("content_format_brief")
        if isinstance(content_format_brief, dict):
            format_name = str(content_format_brief.get("format") or "").strip().casefold()
            if format_name:
                return format_name
        format_family_plan = (compiled_context or {}).get("format_family_plan")
        if isinstance(format_family_plan, dict):
            family = str(format_family_plan.get("family") or "").strip().casefold()
            if family in {"static", "infographic", "carousel"}:
                return family
        return ""

    @classmethod
    def _dedupe_metadata_collection(
        cls,
        items: list[str],
        *,
        blocked_texts: list[str],
        limit: int,
    ) -> list[str]:
        blocked = {
            cls._normalize_metadata_text(text, limit=180).casefold()
            for text in blocked_texts
            if cls._normalize_metadata_text(text, limit=180)
        }
        cleaned: list[str] = []
        for item in items:
            normalized = cls._normalize_metadata_text(item, limit=180)
            if not normalized:
                continue
            lowered = normalized.casefold()
            if lowered in blocked:
                continue
            if any(lowered == existing.casefold() for existing in cleaned):
                continue
            cleaned.append(normalized)
            if len(cleaned) >= limit:
                break
        return cleaned

    @classmethod
    def _normalize_static_panel_spec(
        cls,
        value: Any,
        *,
        headline: str,
        supporting_line: str,
        proof_points: list[str],
        stat_highlights: list[str],
        claim_evidence_pairs: list[dict[str, str]],
        cta: str,
        body: str,
    ) -> dict[str, Any]:
        raw = value if isinstance(value, dict) else {}
        dominant_message = cls._normalize_metadata_text(
            raw.get("dominant_message") or supporting_line or headline or body,
            limit=180,
        )
        supporting_lines = cls._normalize_metadata_list(
            raw.get("supporting_lines"),
            limit=2,
        ) or ([supporting_line] if supporting_line else [])
        return {
            "panel_goal": cls._normalize_metadata_text(raw.get("panel_goal"), limit=48) or "single_dominant_message",
            "dominant_message": dominant_message,
            "supporting_lines": supporting_lines[:2],
            "proof_points": proof_points[:2],
            "stat_highlights": stat_highlights[:2],
            "claim_evidence_pairs": cls._normalize_claim_evidence_pairs(raw.get("claim_evidence_pairs"), limit=1)
            or claim_evidence_pairs[:1],
            "visual_focus": cls._normalize_metadata_text(raw.get("visual_focus"), limit=160)
            or cls._normalize_metadata_text(raw.get("visual_direction"), limit=160),
            "cta_mode": cls._normalize_metadata_text(raw.get("cta_mode"), limit=48)
            or ("integrated_cta" if cta else "no_cta"),
        }

    @classmethod
    def _normalize_infographic_section_specs(
        cls,
        value: Any,
        *,
        headline: str,
        supporting_line: str,
        proof_points: list[str],
        stat_highlights: list[str],
        claim_evidence_pairs: list[dict[str, str]],
        body: str,
    ) -> list[dict[str, Any]]:
        raw_sections = [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []
        normalized_sections: list[dict[str, Any]] = []
        if raw_sections:
            for index, item in enumerate(raw_sections, start=1):
                section_headline = cls._normalize_metadata_text(
                    item.get("headline") or item.get("section_label") or item.get("title"),
                    limit=120,
                )
                section_body = cls._normalize_metadata_text(
                    item.get("body") or item.get("description") or item.get("summary"),
                    limit=260,
                )
                section_points = cls._normalize_metadata_list(item.get("body_points"), limit=3)
                section_proof = cls._normalize_metadata_list(item.get("proof_points"), limit=3)
                section_stats = cls._normalize_metadata_list(item.get("stat_highlights"), limit=3)
                section_claims = cls._normalize_claim_evidence_pairs(item.get("claim_evidence_pairs"), limit=2)
                normalized_sections.append(
                    {
                        "section_number": int(item.get("section_number") or item.get("index") or index),
                        "section_role": cls._normalize_metadata_text(item.get("section_role") or item.get("role"), limit=48)
                        or ("overview" if index == 1 else "takeaway" if index == len(raw_sections) else "detail"),
                        "section_label": cls._normalize_metadata_text(item.get("section_label") or item.get("label"), limit=40),
                        "headline": section_headline,
                        "body": section_body,
                        "body_points": section_points,
                        "proof_points": section_proof,
                        "stat_highlights": section_stats,
                        "claim_evidence_pairs": section_claims,
                        "visual_focus": cls._normalize_metadata_text(item.get("visual_focus"), limit=160),
                    }
                )
        if normalized_sections:
            return normalized_sections[:4]

        sentences = cls._sentences(body)
        claim_lines = cls._claim_evidence_pair_lines(claim_evidence_pairs, limit=3)
        sections: list[dict[str, Any]] = [
            {
                "section_number": 1,
                "section_role": "overview",
                "section_label": "Overview",
                "headline": supporting_line or headline,
                "body": sentences[0] if sentences else supporting_line or headline,
                "body_points": [],
                "proof_points": proof_points[:2],
                "stat_highlights": stat_highlights[:1],
                "claim_evidence_pairs": [],
                "visual_focus": "",
            }
        ]
        if stat_highlights or claim_lines:
            sections.append(
                {
                    "section_number": len(sections) + 1,
                    "section_role": "evidence",
                    "section_label": "Key numbers" if stat_highlights else "Evidence",
                    "headline": "Key numbers" if stat_highlights else "Evidence",
                    "body": claim_lines[0] if claim_lines else (sentences[1] if len(sentences) > 1 else ""),
                    "body_points": [],
                    "proof_points": proof_points[2:4],
                    "stat_highlights": stat_highlights[:3],
                    "claim_evidence_pairs": claim_evidence_pairs[:2],
                    "visual_focus": "",
                }
            )
        sections.append(
            {
                "section_number": len(sections) + 1,
                "section_role": "takeaway",
                "section_label": "What to know",
                "headline": "What to know",
                "body": sentences[-1] if len(sentences) > 1 else supporting_line or headline,
                "body_points": proof_points[:2],
                "proof_points": proof_points[:3],
                "stat_highlights": [],
                "claim_evidence_pairs": [],
                "visual_focus": "",
            }
        )
        return sections[:4]

    @classmethod
    def _repair_static_metadata_semantics(
        cls,
        metadata: dict[str, Any],
        *,
        body: str,
    ) -> dict[str, Any]:
        repaired = dict(metadata or {})
        sentences = cls._sentences(body)
        headline = cls._normalize_metadata_text(repaired.get("headline"), limit=180)
        cta = cls._normalize_metadata_text(repaired.get("cta"), limit=90)
        original_supporting_line = cls._normalize_metadata_text(repaired.get("supporting_line"), limit=180)
        supporting_line = original_supporting_line
        raw_proof_points = cls._normalize_metadata_list(repaired.get("proof_points"), limit=3)
        raw_stat_highlights = cls._normalize_metadata_list(repaired.get("stat_highlights"), limit=3)
        if (
            not supporting_line
            or (cta and supporting_line.casefold() == cta.casefold())
            or any(supporting_line.casefold() == item.casefold() for item in [*raw_proof_points, *raw_stat_highlights] if item)
        ):
            supporting_line = next(
                (
                    cls._normalize_metadata_text(candidate, limit=180)
                    for candidate in [*sentences[1:3], *repaired.get("proof_points", [])]
                    if cls._normalize_metadata_text(candidate, limit=180)
                    and cls._normalize_metadata_text(candidate, limit=180).casefold() not in {
                        headline.casefold(),
                        cta.casefold() if cta else "",
                    }
                ),
                supporting_line or "",
            )
        repaired["supporting_line"] = supporting_line
        repaired["proof_points"] = cls._dedupe_metadata_collection(
            raw_proof_points,
            blocked_texts=[headline, original_supporting_line, supporting_line, cta],
            limit=2,
        )
        repaired["stat_highlights"] = cls._dedupe_metadata_collection(
            raw_stat_highlights,
            blocked_texts=[headline, original_supporting_line, supporting_line, cta, *repaired["proof_points"]],
            limit=2,
        )
        normalized_claim_pairs = cls._normalize_claim_evidence_pairs(repaired.get("claim_evidence_pairs"), limit=3)
        if normalized_claim_pairs:
            allocations = cls._allocate_claim_evidence_pairs_to_slots(
                [
                    {
                        "role": "static",
                        "headline": headline,
                        "supporting_line": supporting_line,
                        "body": body,
                        "proof_points": repaired["proof_points"],
                        "stat_highlights": repaired["stat_highlights"],
                    }
                ],
                claim_evidence_pairs=normalized_claim_pairs,
                format_family="static",
            )
            assigned_pairs = allocations[0] if allocations else []
            if assigned_pairs:
                claim_lines = cls._claim_evidence_pair_lines(assigned_pairs, limit=1)
                repaired["proof_points"] = cls._dedupe_metadata_collection(
                    [*claim_lines, *repaired["proof_points"]],
                    blocked_texts=[headline, original_supporting_line, supporting_line, cta],
                    limit=2,
                )
                repaired["claim_evidence_pairs"] = assigned_pairs
        repaired["static_panel_spec"] = cls._normalize_static_panel_spec(
            repaired.get("static_panel_spec"),
            headline=headline,
            supporting_line=supporting_line,
            proof_points=repaired["proof_points"],
            stat_highlights=repaired["stat_highlights"],
            claim_evidence_pairs=cls._normalize_claim_evidence_pairs(repaired.get("claim_evidence_pairs"), limit=1),
            cta=cta,
            body=body,
        )
        return repaired

    @classmethod
    def _repair_infographic_metadata_semantics(
        cls,
        metadata: dict[str, Any],
        *,
        body: str,
    ) -> dict[str, Any]:
        repaired = dict(metadata or {})
        sentences = cls._sentences(body)
        headline = cls._normalize_metadata_text(repaired.get("headline"), limit=180)
        cta = cls._normalize_metadata_text(repaired.get("cta"), limit=90)
        supporting_line = cls._normalize_metadata_text(repaired.get("supporting_line"), limit=180)
        claim_lines = cls._claim_evidence_pair_lines(
            cls._normalize_claim_evidence_pairs(repaired.get("claim_evidence_pairs"), limit=4),
            limit=4,
        )
        repaired["proof_points"] = cls._dedupe_metadata_collection(
            cls._normalize_metadata_list(repaired.get("proof_points"), limit=5) or claim_lines or sentences[1:5],
            blocked_texts=[headline, supporting_line, cta],
            limit=4,
        )
        repaired["stat_highlights"] = cls._dedupe_metadata_collection(
            cls._normalize_metadata_list(repaired.get("stat_highlights"), limit=4),
            blocked_texts=[headline, supporting_line, cta, *repaired["proof_points"]],
            limit=3,
        )
        normalized_claim_pairs = cls._normalize_claim_evidence_pairs(repaired.get("claim_evidence_pairs"), limit=4)
        repaired["claim_evidence_pairs"] = normalized_claim_pairs
        if not supporting_line:
            supporting_line = next(
                (
                    cls._normalize_metadata_text(candidate, limit=180)
                    for candidate in [*sentences[:2], *repaired["proof_points"]]
                    if cls._normalize_metadata_text(candidate, limit=180)
                    and cls._normalize_metadata_text(candidate, limit=180).casefold() != headline.casefold()
                ),
                "",
            )
        repaired["supporting_line"] = supporting_line
        section_label = cls._normalize_metadata_text(repaired.get("section_label"), limit=26)
        if not section_label or section_label.casefold() in {"insights", "highlights"}:
            if repaired["stat_highlights"]:
                section_label = "Key numbers"
            elif repaired["proof_points"]:
                section_label = "What to know"
        repaired["section_label"] = section_label
        repaired["infographic_section_specs"] = cls._normalize_infographic_section_specs(
            repaired.get("infographic_section_specs"),
            headline=headline,
            supporting_line=supporting_line,
            proof_points=repaired["proof_points"],
            stat_highlights=repaired["stat_highlights"],
            claim_evidence_pairs=normalized_claim_pairs,
            body=body,
        )
        section_allocations = cls._allocate_claim_evidence_pairs_to_slots(
            repaired["infographic_section_specs"],
            claim_evidence_pairs=normalized_claim_pairs,
            format_family="infographic",
        )
        for index, section in enumerate(repaired["infographic_section_specs"]):
            assigned_pairs = section_allocations[index] if index < len(section_allocations) else []
            section["claim_evidence_pairs"] = assigned_pairs
            claim_lines = cls._claim_evidence_pair_lines(assigned_pairs, limit=2)
            if claim_lines:
                section["proof_points"] = cls._dedupe_metadata_collection(
                    [*claim_lines, *cls._normalize_metadata_list(section.get("proof_points"), limit=3)],
                    blocked_texts=[
                        section.get("headline"),
                        section.get("section_label"),
                        section.get("body"),
                    ],
                    limit=3,
                )
                section["body_points"] = cls._dedupe_metadata_collection(
                    [*cls._normalize_metadata_list(section.get("body_points"), limit=3), *claim_lines],
                    blocked_texts=[section.get("headline"), section.get("section_label")],
                    limit=3,
                )
        return repaired

    @classmethod
    def _visual_metadata_keywords(cls, value: Any, *, limit: int = 12) -> set[str]:
        keywords: list[str] = []
        for word in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", cls._coerce_text_value(value).casefold()):
            normalized = word.rstrip("'")
            if not normalized or normalized in cls.VISUAL_METADATA_COMPATIBILITY_STOPWORDS:
                continue
            if normalized.isdigit():
                continue
            keywords.append(normalized)
            if len(keywords) >= limit:
                break
        return set(keywords)

    @classmethod
    def _visual_metadata_evidence_keywords(
        cls,
        *,
        brief: dict[str, Any],
        compiled_context: dict[str, Any] | None = None,
    ) -> set[str]:
        evidence_keywords: set[str] = set()
        evidence_texts: list[Any] = [brief.get("summary"), (compiled_context or {}).get("brand_visual_brief")]
        for item in (brief.get("items") or [])[:5]:
            if isinstance(item, dict):
                evidence_texts.append(item.get("content"))
        for entry in evidence_texts:
            evidence_keywords.update(cls._visual_metadata_keywords(entry, limit=16))
        return evidence_keywords

    @classmethod
    def _sanitize_visual_metadata_fields(
        cls,
        metadata: dict[str, Any],
        *,
        compiled_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[str]]:
        cleaned = dict(metadata or {})
        if not cleaned or not compiled_context:
            return cleaned, []

        brief = ContextCompilerService.coerce_visual_knowledge_brief(
            compiled_context.get("visual_knowledge_brief"),
        )
        if cls._normalize_metadata_text(brief.get("grounding_mode"), limit=32) != "brand_knowledge":
            return cleaned, []

        items = brief.get("items") if isinstance(brief.get("items"), list) else []
        if not items:
            return cleaned, []

        evidence_keywords = cls._visual_metadata_evidence_keywords(
            brief=brief,
            compiled_context=compiled_context,
        )
        if not evidence_keywords:
            return cleaned, []

        grounding_strength = cls._normalize_metadata_text(brief.get("grounding_strength"), limit=32) or "supported"
        removed_fields: list[str] = []
        for field, limit in cls.VISUAL_METADATA_FIELD_LIMITS.items():
            text = cls._normalize_metadata_text(cleaned.get(field), limit=limit)
            cleaned[field] = text
            if not text:
                continue
            field_keywords = cls._visual_metadata_keywords(text, limit=10)
            if not field_keywords:
                cleaned[field] = ""
                removed_fields.append(field)
                continue
            if field_keywords & evidence_keywords:
                continue
            if grounding_strength in {"strong", "supported", "fallback_only"}:
                cleaned[field] = ""
                removed_fields.append(field)
        return cleaned, removed_fields

    @staticmethod
    def _normalize_metadata_text(value: Any, limit: int) -> str:
        text = AIOrchestratorService._coerce_text_value(value)
        text = " ".join(text.strip().split())
        if not text:
            return ""
        if len(text) <= limit:
            return text
        sentences = AIOrchestratorService._sentences(text)
        if len(sentences) > 1:
            collected: list[str] = []
            for sentence in sentences:
                joined = " ".join([*collected, sentence]).strip()
                if len(joined) > limit:
                    break
                collected.append(sentence)
            if collected:
                return " ".join(collected).strip()
        truncation_limit = max(limit - 3, 1)
        candidate = text[:truncation_limit].rstrip(" ,.;:")
        if " " in candidate:
            candidate = candidate.rsplit(" ", 1)[0].rstrip(" ,.;:")
        candidate = candidate or text[:truncation_limit].rstrip(" ,.;:")
        return f"{candidate}..." if candidate else text[:limit].rstrip(" ,.;:")

    @staticmethod
    def _normalize_metadata_list(value: Any, limit: int) -> list[str]:
        if value is None:
            return []

        raw_items: list[str] = []
        if isinstance(value, str):
            chunks = re.split(r"(?:\r?\n|[;|])+|\s*•\s*|\s*[-*]\s+|(?:✔️|✓|✅|➜|➡️|âœ”ï¸|â€¢)\s*", value)
            if len(chunks) == 1:
                chunks = re.split(r",\s+|(?<=[.!?])\s+", value)
            raw_items = chunks
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                if isinstance(item, dict):
                    raw_items.append(str(item.get("label") or item.get("text") or item.get("value") or "").strip())
                else:
                    raw_items.append(str(item).strip())
        else:
            raw_items = [str(value).strip()]

        cleaned: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            # Treat only real numbered bullets ("1. item", "1) item") as
            # list markers. Decimal facts like "70.03%" must stay intact.
            text = re.sub(r"^\s*(?:[#*\-]+|\d+[.)]\s+)", "", item).strip()
            if not text:
                continue
            text = AIOrchestratorService._sanitize_text_for_canvas(text)
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(AIOrchestratorService._normalize_metadata_text(text, limit=90))
            if len(cleaned) >= limit:
                break
        return cleaned

    @classmethod
    def _normalize_claim_evidence_pairs(cls, value: Any, limit: int) -> list[dict[str, str]]:
        items = cls._coerce_list(value)
        pairs: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in items:
            claim = ""
            evidence = ""
            if isinstance(item, dict):
                claim = cls._normalize_metadata_text(
                    item.get("claim") or item.get("headline") or item.get("proposition") or item.get("text"),
                    limit=96,
                )
                evidence = cls._normalize_metadata_text(
                    item.get("evidence") or item.get("proof") or item.get("support") or item.get("reason"),
                    limit=140,
                )
            else:
                text = cls._coerce_text_value(item)
                if not text:
                    continue
                text = re.sub(r"(?i)^\s*claim\s*:\s*", "", text).strip()
                if "|" in text:
                    left, right = text.split("|", 1)
                    claim = cls._normalize_metadata_text(left, limit=96)
                    evidence = cls._normalize_metadata_text(
                        re.sub(r"(?i)^\s*evidence\s*:\s*", "", right).strip(),
                        limit=140,
                    )
                else:
                    claim = cls._normalize_metadata_text(text, limit=96)
            if claim.upper() == "MISSING":
                claim = ""
            if evidence.upper() == "MISSING":
                evidence = ""
            if not claim and not evidence:
                continue
            key = f"{claim.casefold()}|{evidence.casefold()}"
            if key in seen:
                continue
            seen.add(key)
            pairs.append({"claim": claim, "evidence": evidence})
            if len(pairs) >= limit:
                break
        return pairs

    @classmethod
    def _claim_evidence_pairs_from_research_brief(
        cls,
        brief: Any,
        *,
        limit: int,
    ) -> list[dict[str, str]]:
        if not isinstance(brief, dict):
            return []
        candidates: list[dict[str, str]] = []
        fact_model = brief.get("fact_model") if isinstance(brief.get("fact_model"), dict) else {}
        for fact in (fact_model.get("verified_facts") or [])[: max(limit * 2, 4)]:
            if not isinstance(fact, dict):
                continue
            claim = cls._normalize_metadata_text(
                fact.get("label") or fact.get("claim") or fact.get("headline") or fact.get("title"),
                limit=96,
            )
            evidence = cls._normalize_metadata_text(
                fact.get("value") or fact.get("detail") or fact.get("source_title") or fact.get("source"),
                limit=140,
            )
            if claim or evidence:
                candidates.append({"claim": claim, "evidence": evidence})
        for item in (brief.get("source_pack") or [])[: max(limit * 2, 4)]:
            if not isinstance(item, dict):
                continue
            if cls._normalize_metadata_text(item.get("type"), limit=32) not in {"verified_fact", "ranked_source"}:
                continue
            claim = cls._normalize_metadata_text(
                item.get("label") or item.get("headline") or item.get("title"),
                limit=96,
            )
            evidence = cls._normalize_metadata_text(
                item.get("detail") or item.get("source"),
                limit=140,
            )
            if claim or evidence:
                candidates.append({"claim": claim, "evidence": evidence})
        return cls._normalize_claim_evidence_pairs(candidates, limit=limit)

    @classmethod
    def _merge_claim_evidence_pairs(
        cls,
        primary: Any,
        secondary: Any,
        *,
        limit: int,
    ) -> list[dict[str, str]]:
        return cls._normalize_claim_evidence_pairs(
            [*cls._coerce_list(primary), *cls._coerce_list(secondary)],
            limit=limit,
        )

    @classmethod
    def _claim_evidence_pair_lines(cls, pairs: list[dict[str, str]], limit: int) -> list[str]:
        lines: list[str] = []
        for pair in pairs[:limit]:
            if not isinstance(pair, dict):
                continue
            claim = cls._normalize_metadata_text(pair.get("claim"), limit=96)
            evidence = cls._normalize_metadata_text(pair.get("evidence"), limit=160)
            line = claim
            if claim and evidence:
                line = cls._normalize_metadata_text(f"{claim}: {evidence}", limit=180)
            elif evidence:
                line = evidence
            if line:
                lines.append(line)
        return lines

    @classmethod
    def _content_allocation_keywords(cls, *values: Any, limit: int = 18) -> set[str]:
        keywords: list[str] = []
        for value in values:
            for word in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", cls._coerce_text_value(value).casefold()):
                normalized = word.rstrip("'")
                if not normalized or normalized in cls.CONTENT_ALLOCATION_STOPWORDS:
                    continue
                if normalized.isdigit():
                    continue
                keywords.append(normalized)
                if len(keywords) >= limit:
                    return set(keywords)
        return set(keywords)

    @classmethod
    def _claim_evidence_slot_capacity(cls, role: str, *, format_family: str) -> int:
        normalized = cls._normalize_metadata_text(role, limit=48).casefold().replace(" ", "_")
        if format_family == "static":
            return 1
        if format_family == "infographic":
            if normalized == "evidence":
                return 2
            if normalized in {"overview", "analysis", "detail", "takeaway"}:
                return 1
            return 1
        if normalized in {"hook", "cover", "opening", "title", "context", "setup", "intro"}:
            return 0
        if normalized in {"close", "closing", "cta", "final"}:
            return 0
        if normalized == "takeaway":
            return 1
        return 1

    @classmethod
    def _claim_evidence_slot_priority(cls, role: str, *, format_family: str) -> int:
        normalized = cls._normalize_metadata_text(role, limit=48).casefold().replace(" ", "_")
        if format_family == "static":
            return 5
        if normalized in {"structure", "deal_structure", "what_happened", "mechanics", "breakdown", "evidence"}:
            return 5
        if normalized in {"undercovered_angle", "missed_angle", "angle", "strategic_meaning", "implications", "implication", "analysis", "what_matters"}:
            return 4
        if normalized in {"detail", "overview", "takeaway"}:
            return 3
        if normalized in {"hook", "cover", "opening", "title"}:
            return 1
        if normalized in {"close", "closing", "cta", "final"}:
            return 0
        return 2

    @classmethod
    def _claim_evidence_pair_role_hint(cls, pair: dict[str, str]) -> str:
        text = " ".join(
            part
            for part in [
                cls._normalize_metadata_text(pair.get("claim"), limit=96),
                cls._normalize_metadata_text(pair.get("evidence"), limit=160),
            ]
            if part
        ).casefold()
        if re.search(r"strategic|signal|alignment|position|shape|long[- ]term|implication", text):
            return "strategic_meaning"
        if re.search(r"mobility|services|miss|overlook|hidden|undercovered|clause|condition", text):
            return "undercovered_angle"
        if re.search(r"tariff|goods?|access|terms?|cuts?|structure|mechanic|breakdown", text):
            return "structure"
        return "detail"

    @classmethod
    def _score_claim_evidence_pair_for_slot(
        cls,
        pair: dict[str, str],
        *,
        role: str,
        slot_texts: list[Any],
    ) -> int:
        claim = cls._normalize_metadata_text(pair.get("claim"), limit=96)
        evidence = cls._normalize_metadata_text(pair.get("evidence"), limit=160)
        pair_text = " ".join(part for part in [claim, evidence] if part).strip()
        if not pair_text:
            return -1
        slot_text = " ".join(cls._coerce_text_value(item) for item in slot_texts if cls._coerce_text_value(item)).strip()
        slot_keywords = cls._content_allocation_keywords(slot_text, limit=18)
        pair_keywords = cls._content_allocation_keywords(pair_text, limit=12)
        score = len(slot_keywords & pair_keywords) * 3
        lowered_pair = pair_text.casefold()
        lowered_slot = slot_text.casefold()
        if claim and claim.casefold() in lowered_slot:
            score += 4
        if evidence and evidence.casefold() in lowered_slot:
            score += 3
        if re.search(r"\d", pair_text) and re.search(r"\d", slot_text):
            score += 2

        normalized_role = cls._normalize_metadata_text(role, limit=48).casefold().replace(" ", "_")
        role_hint = cls._claim_evidence_pair_role_hint(pair)
        if role_hint == normalized_role:
            score += 12
        elif (
            normalized_role in {"structure", "deal_structure", "what_happened", "mechanics", "breakdown", "undercovered_angle", "missed_angle", "angle", "strategic_meaning", "implications", "implication", "analysis", "what_matters"}
            and role_hint in {"structure", "undercovered_angle", "strategic_meaning"}
            and role_hint != normalized_role
        ):
            score -= 4
        if normalized_role in {"structure", "deal_structure", "what_happened", "mechanics", "breakdown", "evidence"} and re.search(r"\d|%|tariff|access|goods?|terms?|cuts?|structure|mechanic", lowered_pair):
            score += 3
        if normalized_role in {"structure", "deal_structure", "what_happened", "mechanics", "breakdown"} and re.search(r"tariff|goods?|access|terms?|cuts?|structure", lowered_pair):
            score += 4
        if normalized_role in {"undercovered_angle", "missed_angle", "angle"} and re.search(r"miss|overlook|hidden|clause|condition|but|however|unless|asymmetr", lowered_pair):
            score += 3
        if normalized_role in {"undercovered_angle", "missed_angle", "angle"} and re.search(r"mobility|services|miss|overlook|hidden|clause", lowered_pair):
            score += 4
        if normalized_role in {"strategic_meaning", "implications", "implication", "analysis", "what_matters", "takeaway"} and re.search(r"signal|strategy|strategic|long[- ]term|alignment|shape|implication|position", lowered_pair):
            score += 3
        if normalized_role in {"strategic_meaning", "implications", "implication", "analysis", "what_matters"} and re.search(r"signal|strategic|alignment|position|shape", lowered_pair):
            score += 4
        return score

    @classmethod
    def _allocate_claim_evidence_pairs_to_slots(
        cls,
        slots: list[dict[str, Any]],
        *,
        claim_evidence_pairs: list[dict[str, str]],
        format_family: str,
    ) -> list[list[dict[str, str]]]:
        allocations: list[list[dict[str, str]]] = [[] for _ in slots]
        if not slots or not claim_evidence_pairs:
            return allocations

        slot_specs: list[dict[str, Any]] = []
        for index, slot in enumerate(slots):
            role = cls._normalize_metadata_text(
                slot.get("story_role") or slot.get("section_role") or slot.get("role"),
                limit=48,
            )
            slot_specs.append(
                {
                    "index": index,
                    "role": role,
                    "capacity": cls._claim_evidence_slot_capacity(role, format_family=format_family),
                    "priority": cls._claim_evidence_slot_priority(role, format_family=format_family),
                    "texts": [
                        slot.get("headline"),
                        slot.get("section_label"),
                        slot.get("supporting_line"),
                        slot.get("body"),
                        slot.get("body_points"),
                        slot.get("proof_points"),
                        slot.get("stat_highlights"),
                    ],
                }
            )

        unused = list(claim_evidence_pairs)
        ordered_specs = sorted(slot_specs, key=lambda item: (-item["priority"], item["index"]))
        for spec in ordered_specs:
            if spec["capacity"] <= 0 or not unused:
                continue
            scored = sorted(
                (
                    (
                        cls._score_claim_evidence_pair_for_slot(
                            pair,
                            role=spec["role"],
                            slot_texts=spec["texts"],
                        ),
                        pair_index,
                        pair,
                    )
                    for pair_index, pair in enumerate(unused)
                ),
                key=lambda item: (item[0], -item[1]),
                reverse=True,
            )
            best_score, best_index, best_pair = scored[0]
            if best_score <= 0 and spec["priority"] < 4 and format_family != "static":
                continue
            allocations[spec["index"]].append(best_pair)
            unused.pop(best_index)

        while unused:
            expandable = [
                spec
                for spec in ordered_specs
                if spec["capacity"] > len(allocations[spec["index"]])
            ]
            if not expandable:
                break
            best_spec = expandable[0]
            best_pair_index = 0
            best_score = -1
            for pair_index, pair in enumerate(unused):
                score = cls._score_claim_evidence_pair_for_slot(
                    pair,
                    role=best_spec["role"],
                    slot_texts=best_spec["texts"],
                )
                if score > best_score:
                    best_score = score
                    best_pair_index = pair_index
            allocations[best_spec["index"]].append(unused.pop(best_pair_index))
        return allocations

    @staticmethod
    def _sentences(value: Any) -> list[str]:
        structured_items = AIOrchestratorService._structured_list_items(value)
        if structured_items:
            return structured_items
        text = AIOrchestratorService._coerce_text_value(value)
        if not text:
            return []
        return [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", text.strip())
            if sentence.strip()
        ]

    @staticmethod
    def _coerce_text_value(value: Any, fallback: str = "") -> str:
        if value is None:
            return fallback
        if isinstance(value, str):
            return AIOrchestratorService._sanitize_text_for_canvas(value)
        if isinstance(value, dict):
            preferred = value.get("text") or value.get("label") or value.get("value") or value.get("content")
            if preferred is not None:
                return AIOrchestratorService._coerce_text_value(preferred, fallback)
            serialized = json.dumps(value, default=str)
            return AIOrchestratorService._sanitize_text_for_canvas(serialized) if serialized != "{}" else fallback
        if isinstance(value, (list, tuple, set)):
            pieces = [
                AIOrchestratorService._coerce_text_value(item).strip()
                for item in value
            ]
            joined = " ".join(piece for piece in pieces if piece)
            return AIOrchestratorService._sanitize_text_for_canvas(joined) or fallback
        return AIOrchestratorService._sanitize_text_for_canvas(str(value))

    @staticmethod
    def _compact_infographic_section_specs(value: Any) -> str:
        if not isinstance(value, list):
            return ""
        sections: list[str] = []
        for item in value[:4]:
            if not isinstance(item, dict):
                continue
            role = AIOrchestratorService._normalize_metadata_text(item.get("section_role"), limit=32)
            headline = AIOrchestratorService._normalize_metadata_text(
                item.get("headline") or item.get("section_label"),
                limit=80,
            )
            proof = AIOrchestratorService._compact_named_items(item.get("proof_points"), limit=2)
            stats = AIOrchestratorService._compact_named_items(item.get("stat_highlights"), limit=2)
            claims = AIOrchestratorService._compact_named_items(
                AIOrchestratorService._claim_evidence_pair_lines(
                    AIOrchestratorService._normalize_claim_evidence_pairs(item.get("claim_evidence_pairs"), limit=2),
                    limit=1,
                ),
                limit=1,
            )
            parts = [part for part in [role, headline, proof, stats, claims] if part]
            if parts:
                sections.append(" | ".join(parts))
        return "; ".join(sections[:4])

    @staticmethod
    def _compact_static_panel_spec(value: Any) -> str:
        if not isinstance(value, dict):
            return ""
        dominant = AIOrchestratorService._normalize_metadata_text(value.get("dominant_message"), limit=120)
        supporting = AIOrchestratorService._compact_named_items(value.get("supporting_lines"), limit=2)
        proof = AIOrchestratorService._compact_named_items(value.get("proof_points"), limit=2)
        stats = AIOrchestratorService._compact_named_items(value.get("stat_highlights"), limit=2)
        claims = AIOrchestratorService._compact_named_items(
            AIOrchestratorService._claim_evidence_pair_lines(
                AIOrchestratorService._normalize_claim_evidence_pairs(value.get("claim_evidence_pairs"), limit=1),
                limit=1,
            ),
            limit=1,
        )
        return " | ".join(part for part in [dominant, supporting, proof, stats, claims] if part)

    @staticmethod
    def _disclaimer_overlay_guidance(request: AIOrchestrationRequest) -> str:
        brief = request.research_editorial_brief if isinstance(request.research_editorial_brief, dict) else {}
        requested = bool(brief.get("disclaimer_requested"))
        if not requested:
            prompt_lower = str(getattr(request, "prompt", "") or "").casefold()
            requested = "disclaimer" in prompt_lower
        if not requested:
            return ""
        placement = AIOrchestratorService._normalize_metadata_text(
            brief.get("disclaimer_placement"),
            limit=24,
        ) or "bottom_footer"
        style = AIOrchestratorService._normalize_metadata_text(
            brief.get("disclaimer_style"),
            limit=24,
        ) or "subtle"
        if placement == "bottom_footer":
            return (
                "Reserve a thin quiet strip at the bottom for a small legal disclaimer overlay. "
                f"Keep this bottom zone clean, high-contrast, and free of CTA buttons, icons, or decorative clutter. Disclaimer style: {style}."
            )
        return (
            f"Reserve a small compliant disclaimer zone in the requested placement ({placement}). "
            f"Keep that zone visually quiet and readable. Disclaimer style: {style}."
        )

    @staticmethod
    def _text_overlay_substrate_contract(
        *,
        headline: Any,
        supporting_line: Any = "",
        body: Any = "",
        proof_points: Any = None,
        claim_evidence_pairs: Any = None,
        cta: Any = "",
        slide_role: Any = "",
    ) -> list[str]:
        normalized_headline = AIOrchestratorService._normalize_metadata_text(headline, limit=180)
        normalized_supporting = AIOrchestratorService._normalize_metadata_text(supporting_line, limit=220)
        normalized_body = AIOrchestratorService._normalize_metadata_text(body, limit=260)
        normalized_proof_items = AIOrchestratorService._normalize_metadata_list(proof_points, limit=3)
        claim_lines = AIOrchestratorService._compact_named_items(
            AIOrchestratorService._claim_evidence_pair_lines(
                AIOrchestratorService._normalize_claim_evidence_pairs(claim_evidence_pairs, limit=2),
                limit=2,
            ),
            limit=2,
        )
        normalized_cta = AIOrchestratorService._normalize_metadata_text(cta, limit=80)
        normalized_role = AIOrchestratorService._normalize_metadata_text(slide_role, limit=48)
        semantic_parts: list[str] = []
        if normalized_role:
            semantic_parts.append(f"role={normalized_role}")
        if normalized_headline:
            semantic_parts.append("headline zone requires a large editorial title surface")
        if normalized_supporting:
            semantic_parts.append("support zone requires a compact explanatory line surface")
        if normalized_body and normalized_body.casefold() != normalized_supporting.casefold():
            semantic_parts.append("body zone requires a calm paragraph or callout surface")
        if normalized_proof_items:
            semantic_parts.append(f"proof module count={len(normalized_proof_items)}")
        if claim_lines:
            semantic_parts.append("evidence zones require distinct proof/callout shells")
        if normalized_cta:
            semantic_parts.append("CTA zone requires an empty button or footer shell")
        semantic_summary = " | ".join(semantic_parts) if semantic_parts else "reserve clean copy surfaces"
        cta_guidance = (
            "If a CTA exists, create only an empty premium CTA-safe shell or footer surface in the reserved CTA region; do not write CTA words inside it."
            if normalized_cta
            else "Do not create a visible CTA button unless the layout contract reserves a CTA region; keep any unused CTA area quiet."
        )
        return [
            "TEXT OVERLAY CONTRACT: create a premium visual substrate for exact backend text overlay, not a finished text poster.",
            "Do not render any readable words, letters, numbers, bullets, labels, captions, CTA text, legal text, sample text, or pseudo-text anywhere in the AI image.",
            f"Copy surface plan, with exact words intentionally withheld from image generation: {semantic_summary}.",
            "Design clean empty text-safe regions that visibly belong to the layout: quiet panels, soft cards, divider rules, accent tabs, callout shells, and calm negative space.",
            cta_guidance,
            "The backend will place the exact approved headline, body, proof, CTA, legal copy, and logo after image generation, so preserve stable contrast, alignment, and clean surfaces in every reserved text zone.",
        ]

    @staticmethod
    def _final_text_render_contract(
        *,
        headline: Any,
        supporting_line: Any = "",
        body: Any = "",
        proof_points: Any = None,
        claim_evidence_pairs: Any = None,
        cta: Any = "",
        slide_role: Any = "",
        legal_footer: Any = "",
    ) -> list[str]:
        normalized_headline = AIOrchestratorService._normalize_metadata_text(headline, limit=180)
        normalized_supporting = AIOrchestratorService._normalize_metadata_text(supporting_line, limit=220)
        normalized_body = AIOrchestratorService._normalize_metadata_text(body, limit=260)
        normalized_proof_items = AIOrchestratorService._normalize_metadata_list(proof_points, limit=3)
        claim_lines = AIOrchestratorService._claim_evidence_pair_lines(
            AIOrchestratorService._normalize_claim_evidence_pairs(claim_evidence_pairs, limit=2),
            limit=2,
        )
        normalized_cta = AIOrchestratorService._normalize_metadata_text(cta, limit=80)
        normalized_role = AIOrchestratorService._normalize_metadata_text(slide_role, limit=48)
        normalized_footer = AIOrchestratorService._normalize_metadata_text(legal_footer, limit=360)

        guidance = [
            "FINAL TEXT RENDER CONTRACT: render the finished slide with the exact approved readable copy inside the intended text regions.",
            "Do not add any extra readable words, repeated shadow headlines, watermark text, background typography, pseudo-text, lorem ipsum, sample labels, random numbers, or stray glyphs anywhere else in the image.",
            "Keep all readable text confined to the reserved text-safe zones with clean hierarchy, stable alignment, strong contrast, and correct spelling.",
        ]
        if normalized_footer:
            guidance.append(
                "Reserve a thin quiet bottom footer-safe zone for the exact legal footer that will be composited after image generation."
            )
            guidance.append("Do not render, invent, paraphrase, or approximate legal footer text inside the AI image.")
            guidance.append(
                "Keep the bottom footer zone clean, low-noise, and high-contrast enough for a small exact compliance footer overlay without overpowering the composition."
            )
        else:
            guidance.append("Do not invent a legal footer, disclaimer paragraph, or CTA copy beyond the approved text below.")
        if normalized_role:
            guidance.append(f"Approved slide role for this exact copy: {normalized_role}.")
        if normalized_headline:
            guidance.append(f'Use this headline verbatim in the headline zone: "{normalized_headline}".')
        if normalized_supporting:
            guidance.append(f'Use this supporting line verbatim in the support zone: "{normalized_supporting}".')
        if normalized_body and normalized_body.casefold() != normalized_supporting.casefold():
            guidance.append(f'Use this body copy verbatim in the body zone: "{normalized_body}".')
        if normalized_proof_items:
            guidance.append(
                "Use these exact proof or callout lines as readable on-canvas copy in distinct modules: "
                + "; ".join(f'"{item}"' for item in normalized_proof_items)
                + "."
            )
        elif claim_lines:
            guidance.append(
                "If the slide needs evidence callouts, use only these approved claim/evidence anchors as readable copy: "
                + "; ".join(f'"{item}"' for item in claim_lines)
                + "."
            )
        if normalized_cta:
            guidance.append(f'Use this CTA verbatim only in the CTA zone: "{normalized_cta}".')
        else:
            guidance.append("Do not invent a CTA button or footer strip on this slide.")
        guidance.append(
            "Render the copy as part of the finished design, not as empty shells for later backend overlay."
        )
        return guidance

    @staticmethod
    def _scene_graph_legal_footer_text(scene_graph: GenerationSceneGraph) -> str:
        for element in scene_graph.elements:
            role = str(element.role or "").strip().casefold()
            if role not in {"legal", "footer", "disclaimer"}:
                continue
            text = AIOrchestratorService._normalize_metadata_text(element.text, limit=420)
            if text:
                return text
        return ""

    @staticmethod
    def _compose_prompt_sections(
        *,
        required_sections: list[str],
        optional_sections: list[str],
        limit: int,
    ) -> str:
        parts: list[str] = []
        current_length = 0
        for section in [item for item in required_sections if item and not item.endswith(": .")]:
            separator = 1 if parts else 0
            section_length = len(section) + separator
            if parts and current_length + section_length > limit:
                break
            if not parts and len(section) > limit:
                return AIOrchestratorService._trim_prompt(section, limit)
            if separator:
                current_length += 1
            parts.append(section)
            current_length += len(section)
        for section in [item for item in optional_sections if item and not item.endswith(": .")]:
            separator = 1 if parts else 0
            section_length = len(section) + separator
            if current_length + section_length > limit:
                continue
            if separator:
                current_length += 1
            parts.append(section)
            current_length += len(section)
        return AIOrchestratorService._trim_prompt(" ".join(parts), limit)


    @staticmethod
    def build_final_render_prompt(
        request: AIOrchestrationRequest,
        text_payload: StructuredTextPayload,
        creative_decision: CreativeDecisionPayload,
        scene_graph: GenerationSceneGraph,
        message_strategy: MessageStrategyPayload | None = None,
        reference_images: list[dict[str, Any]] | None = None,
        retry_note: str | None = None,
        visual_explanation_plan: dict[str, Any] | None = None,
        compiled_context: dict[str, Any] | None = None,
    ) -> str:
        compiled_context = dict(compiled_context or {})
        metadata = text_payload.metadata or {}
        visual_identity = request.resolved_brand_context.get("visual_identity", {}) or {}
        design_system_guidance = AIOrchestratorService._design_system_prompt_guidance(visual_identity)
        palette = AIOrchestratorService._compact_palette_summary(visual_identity)
        palette_guidance = AIOrchestratorService._palette_role_guidance(visual_identity)
        strict_palette_contract = AIOrchestratorService._strict_palette_contract(visual_identity)
        typography = AIOrchestratorService._compact_typography_summary(visual_identity)
        asset_strategy = creative_decision.asset_strategy if isinstance(creative_decision.asset_strategy, dict) else {}
        template_surface_policy = str(asset_strategy.get("template_surface_policy") or "").strip().lower()
        proof_points = AIOrchestratorService._compact_named_items(metadata.get("proof_points"), limit=4)
        infographic_sections = AIOrchestratorService._compact_infographic_section_specs(metadata.get("infographic_section_specs"))
        static_panel_spec = AIOrchestratorService._compact_static_panel_spec(metadata.get("static_panel_spec"))
        geometry_contract = AIOrchestratorService._compact_scene_graph_geometry(scene_graph)
        layout_dna_contract = AIOrchestratorService._compact_layout_dna_contract(compiled_context)
        layout_archetype = AIOrchestratorService._normalize_metadata_text(
            (scene_graph.styles or {}).get("layout_archetype")
            or (creative_decision.planning_hints or {}).get("layout_archetype")
            or creative_decision.layout_mode,
            limit=120,
        )
        message_theme = ""
        emotional_direction = ""
        if isinstance(message_strategy, MessageStrategyPayload):
            message_theme = AIOrchestratorService._normalize_metadata_text(
                message_strategy.primary_campaign_theme,
                limit=180,
            )
            emotional_direction = AIOrchestratorService._normalize_metadata_text(
                message_strategy.emotional_messaging_direction,
                limit=100,
            )
        brand_name = AIOrchestratorService._normalize_metadata_text(
            request.resolved_brand_context.get("brand_name") or "",
            limit=80,
        )
        file_type = str(request.studio_panel.get("file_type") or "png").upper()
        platform = str(request.studio_panel.get("platform_preset") or "social")
        format_name = str(request.studio_panel.get("format") or "static")
        explicit_data_visual_request = AIOrchestratorService._has_explicit_data_visual_request(
            getattr(request, "prompt", ""),
            text_payload=text_payload,
        )
        canvas_fit_guidance = AIOrchestratorService._canvas_fit_guidance(request.studio_panel)
        supporting_visual_system = AIOrchestratorService._normalized_supporting_visual_system(creative_decision.asset_strategy or {})
        iconography_supported = (
            format_name in {"carousel", "infographic"}
            or supporting_visual_system == "icon_sequence"
            or bool((creative_decision.asset_strategy or {}).get("icon_sequence"))
        )
        logo_position_hint = AIOrchestratorService._effective_logo_position_hint(
            request=request,
            creative_decision=creative_decision,
            text_payload=AIOrchestratorService._text_payload_prompt_dict(text_payload),
        )
        logo_safe_zone_guidance = AIOrchestratorService._logo_safe_zone_guidance(
            request,
            scene_graph,
            hint=logo_position_hint,
        )
        reserved_logo_area = AIOrchestratorService._logo_reserved_area_label(logo_position_hint)
        logo_surface_guidance = AIOrchestratorService._logo_surface_guidance(
            background_tone=AIOrchestratorService._resolve_logo_background_tone(
                metadata=metadata,
                creative_decision=creative_decision,
                scene_graph=scene_graph,
            )
        )
        format_guidance = {
            "carousel": (
                "Treat this as a premium carousel panel or cover image with strong sectioning, "
                "slide-safe hierarchy, concise card-like structure, and a self-contained visual story panel rather than a plain poster."
            ),
            "infographic": (
                "Treat this as a genuine infographic, not a plain headline poster. Build a modular visual explainer "
                "with 3-4 clearly separated sections and strong vertical pacing. Only use chart, icon, or diagram callouts "
                "when the supplied content clearly requires them. Do not default to stock growth arrows, rising bars, or generic finance stickers."
            ),
        }.get(format_name, "Treat this as one finished branded social image.")
        reference_summary = AIOrchestratorService._compact_reference_assets(reference_images or [])
        grounding_sections = AIOrchestratorService._final_render_grounding_sections(
            request=request,
            creative_decision=creative_decision,
            text_payload=text_payload,
            compiled_context=compiled_context,
            reference_assets=reference_images,
        )
        research_quality_section = AIOrchestratorService._research_editorial_prompt_section(
            request,
            compiled_context,
        )
        consultant_contract = AIOrchestratorService._consultant_quality_contract(
            for_visual_only=False,
            for_carousel=format_name == "carousel",
        )
        multimodal_balance_contract = AIOrchestratorService._multimodal_balance_contract(
            format_name=format_name,
            supporting_line=AIOrchestratorService._normalize_metadata_text(metadata.get("supporting_line") or text_payload.body, limit=220),
            proof_points=AIOrchestratorService._normalize_metadata_list(metadata.get("proof_points"), limit=4),
            claim_evidence_pairs=AIOrchestratorService._normalize_claim_evidence_pairs(metadata.get("claim_evidence_pairs"), limit=3),
            for_visual_only=False,
        )
        reference_family_contract = AIOrchestratorService._reference_family_contract_sections(
            compiled_context,
            for_visual_only=False,
        )
        sequence_alignment_sections = AIOrchestratorService._sequence_blueprint_alignment_sections(
            compiled_context,
            for_carousel=format_name == "carousel",
            for_visual_only=False,
        )
        visual_plan = visual_explanation_plan or AIOrchestratorService._visual_explanation_plan(
            request,
            text_payload,
            creative_decision,
            reference_images,
            message_strategy,
        )
        visual_plan_guidance = AIOrchestratorService._visual_explanation_guidance(visual_plan)
        disclaimer_overlay_guidance = AIOrchestratorService._disclaimer_overlay_guidance(request)
        text_overlay_contract = AIOrchestratorService._text_overlay_substrate_contract(
            headline=text_payload.headline,
            supporting_line=metadata.get("supporting_line") or text_payload.body,
            body=text_payload.body,
            proof_points=metadata.get("proof_points"),
            claim_evidence_pairs=metadata.get("claim_evidence_pairs"),
            cta=text_payload.cta,
        )
        sections = [
            "Create one finished premium branded social creative.",
            f"Brand context only: {brand_name}. Use this for palette, tone, and approved copy context only, never as a logo, masthead, signature, watermark, or standalone brand mark.",
            f"LOGO RULE — no exceptions: the AI base creative must contain zero logos, wordmarks, brand-name signatures, monograms, watermarks, logo-like shapes, or brand marks anywhere in the image. Do not render, invent, stylize, emboss, or hint at any logo, initials, or brand identity element. The exact stored brand logo is applied as a separate asset after generation — never recreate it.",
            f"The {reserved_logo_area} area is strictly reserved for the brand logo asset. Do not place any headline, body copy, supporting text, proof point, CTA, icon, or visual element inside or immediately adjacent to this corner.",
            logo_safe_zone_guidance,
            logo_surface_guidance,
            disclaimer_overlay_guidance,
            f"Platform: {platform}.",
            f"Format: {format_name}.",
            f"Output type: {file_type}.",
            format_guidance,
            canvas_fit_guidance,
            f"Creative mode: {creative_decision.layout_mode}.",
            f"Layout archetype: {layout_archetype}.",
            (
                f"Scene-graph geometry contract JSON: {geometry_contract}. Preserve these normalized regions closely; only make tiny adjustments for readability and never recompose from scratch."
                if geometry_contract
                else ""
            ),
            (
                f"Template/layout DNA contract JSON: {layout_dna_contract}. Use this as the authoritative composition skeleton for region balance, hierarchy, and spacing."
                if layout_dna_contract
                else ""
            ),
            "Respect the reference/template layout strictly: preserve the contracted regions, spacing rhythm, text-safe negative space, and image-zone discipline before adding decorative detail.",
            f"Campaign theme: {message_theme}.",
            f"Emotional direction: {emotional_direction}.",
            *text_overlay_contract,
            f"Use these proof points only as semantic visual cues, not readable bullets: {proof_points}.",
            (
                f"Infographic section plan to preserve: {infographic_sections}."
                if infographic_sections and format_name == "infographic"
                else ""
            ),
            (
                f"Static panel plan to preserve: {static_panel_spec}."
                if static_panel_spec and format_name == "static"
                else ""
            ),
            research_quality_section,
            *consultant_contract,
            *multimodal_balance_contract,
            *reference_family_contract,
            *sequence_alignment_sections,
            f"Brand palette to honor: {palette}.",
            f"Palette role guidance: {palette_guidance}.",
            strict_palette_contract,
            f"Typography direction: {typography}.",
            f"Brand design-system layout guidance: {design_system_guidance.get('layout')}." if design_system_guidance.get("layout") else "",
            f"Preferred zone roles from the brand system: {design_system_guidance.get('zones')}." if design_system_guidance.get("zones") else "",
            f"Background style guidance from the brand system: {design_system_guidance.get('background')}." if design_system_guidance.get("background") else "",
            f"Motif guidance from the brand system: {design_system_guidance.get('motifs')}." if design_system_guidance.get("motifs") else "",
            f"Hierarchy guidance from the brand system: {design_system_guidance.get('hierarchy')}." if design_system_guidance.get("hierarchy") else "",
            f"Content-structure guidance from the brand system: {design_system_guidance.get('content_structure')}." if design_system_guidance.get("content_structure") else "",
            f"Image-treatment guidance from the brand system: {design_system_guidance.get('image_treatment')}." if design_system_guidance.get("image_treatment") else "",
            f"Visual-craft guidance from the brand system: {design_system_guidance.get('visual_craft')}." if design_system_guidance.get("visual_craft") else "",
            f"Composition guidance from the brand system: {design_system_guidance.get('composition')}." if design_system_guidance.get("composition") else "",
            f"Subject guidance from the brand system: {design_system_guidance.get('subjects')}." if design_system_guidance.get("subjects") else "",
            f"Editorial rhythm guidance from the brand system: {design_system_guidance.get('editorial')}." if design_system_guidance.get("editorial") else "",
            f"Brand-cue guidance from the brand system: {design_system_guidance.get('brand_cues')}." if design_system_guidance.get("brand_cues") else "",
            *grounding_sections,
            f"Reference images available for composition: {reference_summary}.",
            "Current request subject matter overrides reference subject matter: preserve only approved palette, spacing, layout rhythm, and visual craft from references; never import unrelated objects, industries, products, or scenes from a template.",
            "Render a cohesive, modern, client-ready finished visual with clean hierarchy, premium spacing, and a clear focal path.",
            "Do not crop or crowd any reserved text, CTA, logo, or legal-safe region. If space feels tight, simplify the visual substrate instead of pushing zones to the edge.",
            "All reserved overlay regions must remain fully inside the export frame; do not let cards, shells, dividers, or image subjects touch or cross the crop boundary.",
            "Avoid defaulting to a plain text poster when the requested format calls for a richer explanatory layout.",
            "Make the supporting visual explain the exact topic and benefit from the approved copy intent and user prompt, while leaving all words for backend overlay.",
            visual_plan_guidance,
            "Prefer content-specific explanatory imagery: product or process metaphors, comparison setups, outcome-focused objects, or structured visual anchors directly implied by the copy.",
            "Do not default to a standalone business portrait, generic investor, or unrelated editorial person. Use people only when their action clearly explains the message.",
            (
                "When the composition supports explanation, use refined iconography, diagram cues, comparison motifs, or modular visual anchors to make the piece informative rather than decorative. Avoid repetitive stock finance motifs such as rising bars with arrows unless they are semantically required."
                if iconography_supported
                else "Favor one clear content-led visual focal subject so the base does not collapse into a generic portrait, blank gradient, or empty color field."
            ),
            (
                "Do not add bar-chart icons, rising-arrow symbols, dashboard tiles, comparison stickers, decorative finance mini-graphics, or a chart/graph/bar-and-arrow hero image unless the user explicitly asked for a chart, graph, table, timeline, diagram, or infographic data visualization."
                if not explicit_data_visual_request
                else "If a chart or diagram is explicitly requested, keep it literal, sparse, and directly tied to the supplied data instead of using generic symbolic finance icons."
            ),
            (
                "If the brand design system implies airy hierarchy or generous whitespace, preserve clean negative space instead of packing every proof point into the frame."
                if "airy" in str(design_system_guidance.get("hierarchy") or "").casefold() or "generous" in str(design_system_guidance.get("hierarchy") or "").casefold()
                else ""
            ),
            (
                "If the brand design system implies dense editorial comparison or data-story structure, allow a richer multi-block composition instead of collapsing into one oversized hero subject."
                if any(token in str(design_system_guidance.get("content_structure") or "").casefold() for token in ("comparison", "data", "benefit", "steps"))
                else ""
            ),
            (
                "Bias away from generic business-person imagery when the brand design system points toward diagram-led, icon-led, editorial, or abstract treatment."
                if any(token in str(design_system_guidance.get("image_treatment") or "").casefold() for token in ("diagram", "icon", "editorial", "abstract", "illustration"))
                else ""
            ),
            "Respect the reference/template layout strictly: place visual emphasis only where the selected layout reserves image space, preserve text-safe negative space, and keep the composition skeleton stable.",
            (
                "When sequence guidance is style-reference-only, preserve the sample's region proportions, spacing rhythm, negative space, and composition balance as closely as possible while rebuilding the artwork from scratch. Do not copy the literal sample surface, but do imitate its structural discipline."
                if template_surface_policy == "style_reference_only"
                else ""
            ),
            "Use one coherent composition, not a collage of unrelated stickers, icons, or panels.",
            "Keep every future text-overlay surface clean, calm, high-contrast, and intentionally aligned with premium editorial spacing.",
            "Avoid generic clip-art, fake logos, placeholder UI, awkward overlaps, washed-out buttons, repeated poster templates, or low-contrast pale text on pale backgrounds.",
            AIOrchestratorService._normalize_metadata_text(retry_note, limit=220),
        ]
        return AIOrchestratorService._trim_prompt(
            " ".join(section for section in sections if section and not section.endswith(": .")),
            AIOrchestratorService.IMAGE_PROMPT_MAX_LENGTH,
        )

    @classmethod
    def _collapse_carousel_segments(cls, segments: list[str], max_slides: int) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for segment in segments:
            normalized = " ".join(str(segment or "").split()).strip()
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(normalized)
        if not cleaned:
            return [""]
        if len(cleaned) <= max_slides:
            return cleaned
        collapsed = cleaned[: max_slides - 1]
        collapsed.append(" ".join(cleaned[max_slides - 1 :]).strip())
        return collapsed

    @classmethod
    def _carousel_semantic_tokens(cls, *values: Any) -> set[str]:
        combined = " ".join(
            cls._normalize_metadata_text(value, limit=260)
            for value in values
            if cls._normalize_metadata_text(value, limit=260)
        )
        if not combined:
            return set()
        cleaned = re.sub(r"[^a-z0-9\s]+", " ", combined.casefold())
        stopwords = set(cls.PROMPT_ECHO_STOPWORDS) | {
            "slide",
            "slides",
            "carousel",
            "cover",
            "hook",
            "intro",
            "detail",
            "closing",
            "close",
            "final",
            "point",
            "points",
            "section",
            "sections",
            "insight",
            "insights",
            "what",
            "why",
            "how",
            "this",
            "that",
            "these",
            "those",
            "with",
            "from",
            "into",
            "over",
            "under",
        }
        return {
            token
            for token in cleaned.split()
            if len(token) > 2 and token not in stopwords
        }

    @classmethod
    def _carousel_slides_semantically_overlap(
        cls,
        first: dict[str, Any],
        second: dict[str, Any],
    ) -> bool:
        first_headline = cls._normalize_metadata_text(first.get("headline"), limit=140)
        second_headline = cls._normalize_metadata_text(second.get("headline"), limit=140)
        first_support = cls._normalize_metadata_text(first.get("supporting_line"), limit=220)
        second_support = cls._normalize_metadata_text(second.get("supporting_line"), limit=220)
        if first_headline and first_headline.casefold() == second_headline.casefold():
            if not first_support or not second_support or first_support.casefold() == second_support.casefold():
                return True
        if first_support and first_support.casefold() == second_support.casefold():
            return True

        first_tokens = cls._carousel_semantic_tokens(
            first_headline,
            first_support,
            *(first.get("proof_points") or []),
        )
        second_tokens = cls._carousel_semantic_tokens(
            second_headline,
            second_support,
            *(second.get("proof_points") or []),
        )
        if not first_tokens or not second_tokens:
            return False
        overlap = len(first_tokens & second_tokens)
        if overlap == 0:
            return False
        jaccard = overlap / max(1, len(first_tokens | second_tokens))
        containment = overlap / max(1, min(len(first_tokens), len(second_tokens)))
        return jaccard >= 0.84 or containment >= 0.9

    @classmethod
    def _carousel_headline_subject(cls, headline: str) -> str:
        text = cls._normalize_metadata_text(headline, limit=160)
        if not text:
            return ""
        patterns = (
            r"\binside the (?P<subject>[^?!.]+)",
            r"\bhow (?P<subject>.+?) could impact\b",
            r"\bhow (?P<subject>.+?) works\b",
            r"\bwhy (?P<subject>.+?) matters\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            subject = cls._normalize_metadata_text(match.group("subject"), limit=96)
            if subject:
                return subject
        stripped = re.sub(
            r"^(?:what(?:'s| is)?|why|how|beyond|balancing|inside)\s+",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip(" ,.;:-")
        if stripped:
            words = stripped.split()
            return " ".join(words[:6]).strip(" ,.;:-")
        return ""

    @classmethod
    def _carousel_contextual_role_title(cls, role: str, *, headline: str, cta: str) -> str:
        normalized_role = str(role or "").strip().casefold().replace(" ", "_")
        subject = cls._carousel_headline_subject(headline)
        if not subject:
            return ""
        if normalized_role in {"structure", "deal_structure", "what_happened", "mechanics", "breakdown"}:
            return f"How {subject} works"
        if normalized_role in {"undercovered_angle", "missed_angle", "angle"}:
            return f"What {subject} reveals"
        if normalized_role in {"implications", "implication", "strategic_meaning", "analysis"}:
            return f"Why {subject} matters"
        if normalized_role in {"takeaway", "close", "closing", "cta", "final"}:
            return f"What {subject} means next"
        if normalized_role in {"solution_intro"}:
            return f"How {subject} helps"
        return ""

    @classmethod
    def _carousel_role_title(cls, role: str, *, headline: str, cta: str) -> str:
        normalized_role = str(role or "").strip().casefold().replace(" ", "_")
        contextual_title = cls._carousel_contextual_role_title(normalized_role, headline=headline, cta=cta)
        if normalized_role in {"hook", "cover", "opening", "title"}:
            return headline or "Why this matters now"
        if normalized_role in {"intro", "context", "setup"}:
            return "What happened"
        if normalized_role in {"list_item"}:
            return "One item to understand"
        if normalized_role in {"comparison_item"}:
            return "How this option works"
        if normalized_role in {"problem_frame"}:
            return "The problem to solve"
        if normalized_role in {"solution_intro"}:
            return "How the solution responds"
        if normalized_role in {"feature_cluster"}:
            return "What this helps you see"
        if normalized_role in {"value_close"}:
            return contextual_title or "Why this matters in practice"
        if normalized_role in {"structure", "deal_structure", "what_happened", "mechanics", "breakdown"}:
            return contextual_title or "What actually changed"
        if normalized_role in {"undercovered_angle", "missed_angle", "angle"}:
            return contextual_title or "What most coverage missed"
        if normalized_role in {"implications", "implication", "strategic_meaning", "analysis"}:
            return contextual_title or "Why it matters beyond the headline"
        if normalized_role in {"takeaway", "close", "closing", "cta", "final"}:
            return contextual_title or "What to do with this insight"
        return "What to know next"

    @classmethod
    def _clean_carousel_cta_text(
        cls,
        value: Any,
        *,
        headline: str = "",
        supporting_line: str = "",
    ) -> str:
        text = cls._normalize_metadata_text(value, limit=90).rstrip(" .")
        text = re.sub(r"\s*(?:\.{2,}|…)\s*$", "", text).strip()
        if not text:
            return ""
        words = text.split()
        lowered = text.casefold()
        if len(words) <= 6 and not re.search(r"\b(with\s+[a-z0-9]+|open doors?|learn how|learn more|discover more)\b", lowered):
            return text
        combined = " ".join(
            cls._normalize_metadata_text(part, limit=180).casefold()
            for part in (text, headline, supporting_line)
            if cls._normalize_metadata_text(part, limit=180)
        )
        if "fixed" in combined and "income" in combined:
            return "Explore fixed-income options"
        if "bond" in combined:
            return "Explore bond options"
        if "invest" in combined or "portfolio" in combined:
            return "Explore investment options"
        if re.search(r"\b(read|guide|report|article|analysis)\b", combined):
            return "Read the full analysis"
        return "Explore the next step"

    @classmethod
    def _carousel_story_role(
        cls,
        role: Any,
        *,
        index: int,
        slide_count: int,
        has_cta: bool = False,
    ) -> str:
        normalized = cls._normalize_metadata_text(role, limit=40).casefold().replace(" ", "_")
        if normalized in {"hook", "cover", "opening", "title"}:
            return "hook" if index == 1 else "cover"
        if normalized in {"intro", "context", "setup"}:
            return "intro"
        if normalized in {"close", "closing", "cta", "final"}:
            return "closing"
        if index == 1 and slide_count >= 3:
            return "hook"
        if index == slide_count or has_cta:
            return "closing"
        return "detail"

    @classmethod
    def _carousel_story_role_token(cls, story_role: Any) -> str:
        return cls._normalize_metadata_text(story_role, limit=48).casefold().replace(" ", "_")

    @staticmethod
    def _carousel_generic_story_roles() -> set[str]:
        return {"", "detail", "details", "intro", "context", "setup"}

    @classmethod
    def _carousel_infer_archetype(
        cls,
        *,
        request: AIOrchestrationRequest | None,
        metadata: dict[str, Any],
    ) -> str:
        if isinstance(metadata.get("carousel_archetype"), str) and str(metadata.get("carousel_archetype") or "").strip():
            return str(metadata.get("carousel_archetype") or "").strip().casefold()
        content_plan = getattr(request, "content_plan", {}) if request is not None else {}
        if isinstance(content_plan, dict):
            explicit = str(content_plan.get("carousel_archetype") or "").strip().casefold()
            if explicit:
                return explicit

        text_fragments: list[str] = []
        role_tokens: set[str] = set()
        for candidate in cls._carousel_explicit_outline_candidates(request, metadata):
            if not isinstance(candidate, dict):
                continue
            text_fragments.extend(
                [
                    str(candidate.get("title") or ""),
                    str(candidate.get("description") or ""),
                    str(candidate.get("role") or ""),
                    str(candidate.get("purpose") or ""),
                ]
            )
            role_token = cls._carousel_story_role_token(
                candidate.get("role") or candidate.get("slide_role") or candidate.get("purpose")
            )
            if role_token:
                role_tokens.add(role_token)
        if request is not None:
            text_fragments.append(str(getattr(request, "prompt", "") or ""))
            sequence_pack = cls._template_sequence_pack(request, creative_decision=None)
            if isinstance(sequence_pack, dict):
                text_fragments.extend(
                    [
                        str(sequence_pack.get("family_name") or ""),
                        str(sequence_pack.get("surface_policy") or ""),
                    ]
                )
                for slide in [dict(item) for item in sequence_pack.get("slides", []) if isinstance(item, dict)]:
                    text_fragments.extend(
                        [
                            str(slide.get("template_name") or ""),
                            str(slide.get("headline_hint") or ""),
                            str(slide.get("sequence_summary") or ""),
                            str(slide.get("story_role") or ""),
                        ]
                    )
                    role_token = cls._carousel_story_role_token(slide.get("story_role"))
                    if role_token:
                        role_tokens.add(role_token)
        if role_tokens & {"undercovered_angle", "missed_angle", "strategic_meaning", "what_happened", "deal_structure"}:
            return "editorial_reveal"
        if role_tokens & {"problem_frame", "solution_intro", "feature_cluster", "value_close"}:
            return "problem_solution_feature"
        if role_tokens & {"comparison_item"}:
            return "comparison_framework"
        if role_tokens & {"list_item"}:
            return "list_teaching"

        lowered = " ".join(fragment.casefold() for fragment in text_fragments if fragment).strip()
        if re.search(r"\b(bias|biases|mistake|mistakes|myth|myths|habit|habits|pitfall|pitfalls|behavioural|behavioral)\b", lowered):
            return "list_teaching"
        if re.search(r"\b(compare|comparison|versus|vs\.?|barbell|bullet|ladder|option|options|strategy|strategies)\b", lowered):
            return "comparison_framework"
        if re.search(r"\b(analyzer|tool|dashboard|feature|features|workflow|solution|problem|platform|decision)\b", lowered):
            return "problem_solution_feature"
        if re.search(r"\b(coverage|headline|undercovered|strategic|deal|implication|trade|missed|overlooked)\b", lowered):
            return "editorial_reveal"
        return ""

    @classmethod
    def _carousel_archetype_role_sequence(
        cls,
        archetype: str,
        *,
        slide_count: int,
    ) -> list[str]:
        normalized = str(archetype or "").strip().casefold()
        if slide_count <= 0:
            return []
        if normalized == "editorial_reveal":
            if slide_count == 1:
                return ["hook"]
            if slide_count == 2:
                return ["hook", "takeaway"]
            if slide_count == 3:
                return ["hook", "structure", "takeaway"]
            if slide_count == 4:
                return ["hook", "structure", "undercovered_angle", "strategic_meaning"]
            return ["hook", "structure", "undercovered_angle", "strategic_meaning"] + ["takeaway"] * (slide_count - 4)
        if normalized == "list_teaching":
            if slide_count == 1:
                return ["hook"]
            return ["hook"] + ["list_item"] * max(slide_count - 2, 0) + ["takeaway"]
        if normalized == "comparison_framework":
            if slide_count == 1:
                return ["hook"]
            return ["hook"] + ["comparison_item"] * max(slide_count - 2, 0) + ["takeaway"]
        if normalized == "problem_solution_feature":
            if slide_count == 1:
                return ["problem_frame"]
            if slide_count == 2:
                return ["problem_frame", "value_close"]
            if slide_count == 3:
                return ["problem_frame", "solution_intro", "value_close"]
            return ["problem_frame", "solution_intro"] + ["feature_cluster"] * max(slide_count - 3, 0) + ["value_close"]
        if normalized == "ordered_story":
            if slide_count == 1:
                return ["hook"]
            return ["hook"] + ["detail"] * max(slide_count - 2, 0) + ["takeaway"]
        return []

    @classmethod
    def _carousel_archetype_outline(
        cls,
        archetype: str,
        *,
        slide_count: int,
    ) -> list[dict[str, Any]]:
        roles = cls._carousel_archetype_role_sequence(archetype, slide_count=slide_count)
        outline: list[dict[str, Any]] = []
        for role in roles:
            outline.append(
                {
                    "title": "",
                    "description": "",
                    "role": role,
                }
            )
        return outline

    @classmethod
    def _carousel_role_for_archetype(
        cls,
        explicit_role: Any,
        *,
        archetype: str,
        index: int,
        slide_count: int,
    ) -> str:
        normalized_explicit = cls._carousel_story_role_token(explicit_role)
        role_sequence = cls._carousel_archetype_role_sequence(archetype, slide_count=slide_count)
        archetype_role = role_sequence[index - 1] if index - 1 < len(role_sequence) else ""
        if archetype_role and normalized_explicit in cls._carousel_generic_story_roles():
            return archetype_role
        return normalized_explicit or archetype_role

    @classmethod
    def _carousel_body_point_budget(
        cls,
        story_role: Any,
        *,
        is_final_slide: bool = False,
    ) -> int:
        normalized = cls._carousel_story_role_token(story_role)
        if normalized in {"hook", "cover", "opening", "title"}:
            return 0
        if normalized in {"takeaway", "close", "closing", "cta", "final", "value_close"} or is_final_slide:
            return 2
        if normalized in {"implications", "implication", "strategic_meaning", "analysis", "what_matters"}:
            return 2
        if normalized in {"list_item", "comparison_item", "feature_cluster"}:
            return 3
        if normalized in {"problem_frame", "solution_intro", "undercovered_angle", "missed_angle", "angle", "structure", "deal_structure", "what_happened", "mechanics", "breakdown"}:
            return 2
        return 2

    @classmethod
    def _carousel_role_point_budget(
        cls,
        story_role: Any,
        *,
        is_final_slide: bool = False,
    ) -> int:
        normalized = cls._carousel_story_role_token(story_role)
        if normalized in {"hook", "cover", "opening", "title"}:
            return 0
        if normalized in {"takeaway", "close", "closing", "cta", "final"} or is_final_slide:
            return 0
        if normalized in {"value_close"}:
            return 0
        if normalized in {"implications", "implication", "strategic_meaning", "analysis", "what_matters"}:
            return 0
        if normalized in {"list_item", "comparison_item", "problem_frame", "solution_intro"}:
            return 1
        if normalized in {"feature_cluster"}:
            return 2
        if normalized in {"undercovered_angle", "missed_angle", "angle"}:
            return 2
        if normalized in {"structure", "deal_structure", "what_happened", "mechanics", "breakdown"}:
            return 3
        if normalized in {"intro", "context", "setup"}:
            return 1
        return 2

    @classmethod
    def _carousel_support_score(
        cls,
        story_role: Any,
        text: Any,
    ) -> int:
        normalized_role = cls._carousel_story_role_token(story_role)
        lowered = cls._normalize_metadata_text(text, limit=220).casefold()
        if not lowered:
            return 0
        score = 0
        if normalized_role in {"hook", "cover", "opening", "title"} and re.search(
            r"missed|overlook|headline|really means|what .*dont tell|what .*don't tell|beyond the headline",
            lowered,
        ):
            score += 4
        if normalized_role in {"hook", "cover", "opening", "title"} and re.search(
            r"mobility|services|tariff|duty|70%|100%|signal|strategic|alignment|clause|condition",
            lowered,
        ):
            score -= 3
        if normalized_role in {"hook", "cover", "opening", "title"} and re.search(
            r"not just|beyond|really means|what the headline",
            lowered,
        ):
            score += 2
        if normalized_role in {"structure", "deal_structure", "what_happened", "mechanics", "breakdown"} and re.search(
            r"tariff|duty|access|open|protected|trade volume|what changed|deal terms|phased",
            lowered,
        ):
            score += 5
        if normalized_role in {"list_item"} and re.search(
            r"bias|mistake|myth|habit|example|consequence|trap|tendency",
            lowered,
        ):
            score += 5
        if normalized_role in {"comparison_item"} and re.search(
            r"compare|versus|vs\.?|barbell|bullet|ladder|duration|yield|fit|works",
            lowered,
        ):
            score += 5
        if normalized_role in {"problem_frame"} and re.search(
            r"problem|pain|friction|manual|messy|hard to|blind spot|inefficient",
            lowered,
        ):
            score += 5
        if normalized_role in {"solution_intro"} and re.search(
            r"solution|responds|helps|simplifies|brings together|introduces",
            lowered,
        ):
            score += 5
        if normalized_role in {"feature_cluster"} and re.search(
            r"feature|screen|dashboard|analyzer|monitor|track|filter|compare|workflow",
            lowered,
        ):
            score += 5
        if normalized_role in {"value_close"} and re.search(
            r"value|decision|confidence|clarity|why it matters|what you gain",
            lowered,
        ):
            score += 5
        if normalized_role in {"undercovered_angle", "missed_angle", "angle"} and re.search(
            r"missed|overlook|hidden|mobility|services|clause|condition|string|accountability|rare",
            lowered,
        ):
            score += 5
        if normalized_role in {"implications", "implication", "strategic_meaning", "analysis", "what_matters"} and re.search(
            r"signal|strategic|alignment|template|future|gateway|position|bigger|shape|why it matters",
            lowered,
        ):
            score += 5
        if normalized_role in {"takeaway", "close", "closing", "cta", "final"} and re.search(
            r"watch|next|what to do|read the full|explore|learn more",
            lowered,
        ):
            score += 4
        return score

    @classmethod
    def _carousel_bullet_lines(cls, value: Any, *, limit: int = 4) -> list[str]:
        if isinstance(value, list):
            return cls._normalize_metadata_list(value, limit=limit)
        text = cls._normalize_metadata_text(value, limit=600)
        if not text:
            return []
        fragments = re.split(r"(?:\r?\n|[;•]| - )+", text)
        lines: list[str] = []
        for fragment in fragments:
            normalized = cls._normalize_metadata_text(fragment.strip(" -*"), limit=180)
            if normalized:
                lines.append(normalized)
        if not lines:
            lines = cls._sentences(text)
        return cls._normalize_metadata_list(lines, limit=limit)

    @classmethod
    def _carousel_explicit_outline_candidates(
        cls,
        request: AIOrchestrationRequest | None,
        metadata: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidate_lists: list[Any] = [
            metadata.get("carousel_outline"),
            metadata.get("outline"),
        ]
        if request is not None:
            template_context = request.template_context if isinstance(request.template_context, dict) else {}
            sequence_pack = template_context.get("sequence_pack") if isinstance(template_context, dict) else {}
            sequence_outline = []
            if isinstance(sequence_pack, dict):
                for slide in [dict(item) for item in sequence_pack.get("slides", []) if isinstance(item, dict)]:
                    sequence_outline.append(
                        {
                            "title": str(slide.get("headline_hint") or slide.get("template_name") or "").strip(),
                            "description": str(slide.get("sequence_summary") or "").strip(),
                            "role": str(slide.get("story_role") or "").strip(),
                        }
                    )
            candidate_lists.extend(
                [
                    getattr(request, "content_plan", {}).get("slides") if isinstance(getattr(request, "content_plan", {}), dict) else None,
                    getattr(request, "content_plan", {}).get("story_outline") if isinstance(getattr(request, "content_plan", {}), dict) else None,
                    request.research_editorial_brief.get("outline") if isinstance(request.research_editorial_brief, dict) else None,
                    sequence_outline,
                ]
            )
        for candidate in candidate_lists:
            if not isinstance(candidate, list):
                continue
            normalized_items = [item for item in candidate if isinstance(item, (dict, str)) and item]
            if normalized_items:
                return [dict(item) if isinstance(item, dict) else {"title": str(item)} for item in normalized_items]
        return []

    @classmethod
    def _carousel_outline_candidates(
        cls,
        request: AIOrchestrationRequest | None,
        metadata: dict[str, Any],
    ) -> list[dict[str, Any]]:
        explicit_outline = cls._carousel_explicit_outline_candidates(request, metadata)
        if explicit_outline:
            return explicit_outline
        carousel_archetype = cls._carousel_infer_archetype(request=request, metadata=metadata)
        if carousel_archetype:
            sequence_count = 0
            if request is not None:
                content_plan = getattr(request, "content_plan", {})
                if isinstance(content_plan, dict):
                    sequence_count = cls._int_or_none(content_plan.get("preferred_slide_count")) or 0
                sequence_pack = cls._template_sequence_pack(request, creative_decision=None)
                if isinstance(sequence_pack, dict):
                    sequence_count = sequence_count or cls._int_or_none(sequence_pack.get("slide_count")) or 0
                if isinstance(request.research_editorial_brief, dict):
                    sequence_count = sequence_count or cls._int_or_none(request.research_editorial_brief.get("preferred_slide_count")) or 0
            sequence_count = sequence_count or cls._int_or_none(metadata.get("preferred_slide_count")) or 0
            sequence_count = sequence_count or 5
            return cls._carousel_archetype_outline(carousel_archetype, slide_count=sequence_count)
        return []

    @staticmethod
    def _metadata_text_has_truncation_marker(value: Any) -> bool:
        text = AIOrchestratorService._coerce_text_value(value)
        return "..." in text or "…" in text

    @classmethod
    def _metadata_text_without_truncation_marker(cls, value: Any, *, limit: int) -> str:
        text = cls._normalize_metadata_text(value, limit=limit)
        if not cls._metadata_text_has_truncation_marker(text):
            return text
        cleaned = re.split(r"(?:\.{3}|…)", text, maxsplit=1)[0].strip(" ,.;:-")
        return cleaned if len(cleaned.split()) >= 3 else ""

    @classmethod
    def _carousel_texts_semantically_overlap(cls, first: Any, second: Any) -> bool:
        first_tokens = cls._carousel_semantic_tokens(first)
        second_tokens = cls._carousel_semantic_tokens(second)
        if not first_tokens or not second_tokens:
            return False
        overlap = len(first_tokens & second_tokens)
        if overlap == 0:
            return False
        containment = overlap / max(1, min(len(first_tokens), len(second_tokens)))
        return containment >= 0.82

    @classmethod
    def _sanitize_carousel_slide_specs(
        cls,
        slides: list[dict[str, Any]],
        *,
        request: AIOrchestrationRequest | None = None,
    ) -> list[dict[str, Any]]:
        sanitized: list[dict[str, Any]] = []
        prompt_topic = cls._normalize_metadata_text((request.prompt if request is not None else ""), limit=180)
        request_topic_tokens = cls._request_topic_tokens(request) if request is not None else set()
        topic_token_candidates = request_topic_tokens or cls._topic_anchor_keywords(prompt_topic)
        if not topic_token_candidates and prompt_topic:
            topic_token_candidates = {
                token
                for token in cls._normalized_prompt_tokens(prompt_topic)
                if len(token) >= 3
                and token not in cls.TOPIC_MATCH_NOISE_TOKENS
                and not any(ch.isdigit() for ch in token)
                and not re.fullmatch(r"[a-f0-9]{8,}", token)
            }
        topic_keywords = ", ".join(sorted(topic_token_candidates)[:8])
        brand_subject_terms = cls._brand_subject_focus_terms(request)
        for slide in slides:
            if not isinstance(slide, dict):
                continue
            cleaned = dict(slide)
            for key, limit in (
                ("headline", 120),
                ("supporting_line", 220),
                ("body", 320),
                ("cta", 90),
                ("transition_note", 160),
            ):
                if key in cleaned:
                    cleaned[key] = cls._metadata_text_without_truncation_marker(cleaned.get(key), limit=limit)

            body_text = cls._normalize_metadata_text(cleaned.get("body"), limit=320)
            support_text = cls._normalize_metadata_text(cleaned.get("supporting_line"), limit=220)
            semantic_anchors = [body_text, support_text]
            for key, item_limit in (("proof_points", 120), ("body_points", 140), ("stat_highlights", 90)):
                values = []
                for item in cleaned.get(key) or []:
                    item_text = cls._metadata_text_without_truncation_marker(item, limit=item_limit)
                    if not item_text:
                        continue
                    if any(cls._carousel_texts_semantically_overlap(item_text, anchor) for anchor in semantic_anchors if anchor):
                        continue
                    if any(cls._carousel_texts_semantically_overlap(item_text, existing) for existing in values):
                        continue
                    values.append(item_text)
                cleaned[key] = values

            pairs = []
            for pair in cleaned.get("claim_evidence_pairs") or []:
                if not isinstance(pair, dict):
                    continue
                claim = cls._metadata_text_without_truncation_marker(pair.get("claim"), limit=120)
                evidence = cls._metadata_text_without_truncation_marker(pair.get("evidence"), limit=180)
                if claim and evidence:
                    pairs.append({"claim": claim, "evidence": evidence})
            if "claim_evidence_pairs" in cleaned:
                cleaned["claim_evidence_pairs"] = pairs

            raw_visual_focus = cleaned.get("visual_focus")
            visual_focus_from_reference = isinstance(raw_visual_focus, dict)
            if isinstance(raw_visual_focus, dict):
                visual_focus = cls._normalize_metadata_text(
                    raw_visual_focus.get("description")
                    or raw_visual_focus.get("visual_focus")
                    or raw_visual_focus.get("text")
                    or raw_visual_focus.get("label"),
                    limit=180,
                )
            else:
                visual_focus = cls._normalize_metadata_text(raw_visual_focus, limit=180)
            lowered_focus = visual_focus.casefold()
            generic_visual_focus = bool(
                lowered_focus
                and any(
                    token in lowered_focus
                    for token in (
                        "conceptual map",
                        "formal signing",
                        "signing ceremony",
                        "diplomatic handshake",
                        "handshake",
                        "professional photo or illustration",
                        "symbolizing international trade",
                        "trade icons",
                        "icons representing",
                        "vector icons showing",
                        "scale icon",
                        "analytics visual",
                        "clean, inviting graphic",
                        "infographic showing",
                        "platform interface",
                        "bond investment visual",
                        "curated investment opportunities",
                        "visual highlighting",
                        "reassurance symbols",
                        "shields or checkmarks",
                        "platform interface",
                        "conceptual infographic",
                        "showing india",
                        "showing trade links",
                        "reference_image",
                        "storage_path",
                    )
                )
            )
            if (
                not visual_focus
                or lowered_focus in {"unknown", "none", "n/a"}
                or '"storage_path": "unknown"' in lowered_focus
                or "'storage_path': 'unknown'" in lowered_focus
                or generic_visual_focus
                or visual_focus_from_reference
            ):
                story_role = cls._normalize_metadata_text(
                    (
                        (cleaned.get("metadata") or {}).get("story_role")
                        if isinstance(cleaned.get("metadata"), dict)
                        else ""
                    )
                    or cleaned.get("role")
                    or cleaned.get("slide_role"),
                    limit=48,
                )
                evidence_cues = cls._normalize_metadata_list(
                    [
                        *(cleaned.get("proof_points") or []),
                        *(cleaned.get("body_points") or []),
                        *(cleaned.get("stat_highlights") or []),
                    ],
                    limit=3,
                )
                semantic_subjects = cls._normalize_metadata_list(
                    [
                        cleaned.get("headline"),
                        cleaned.get("supporting_line"),
                        *(cleaned.get("body_points") or []),
                        *(cleaned.get("proof_points") or []),
                    ],
                    limit=3,
                )
                role_focus_line = {
                    "hook": "Build a bold opening metaphor tied directly to the story and spread the hero across the lower or side canvas instead of reducing it to a tiny badge cluster.",
                    "cover": "Build a bold opening metaphor tied directly to the story and spread the hero across the lower or side canvas instead of reducing it to a tiny badge cluster.",
                    "opening": "Build a bold opening metaphor tied directly to the story and spread the hero across the lower or side canvas instead of reducing it to a tiny badge cluster.",
                    "structure": "Show the mechanism explicitly with one analytical centerpiece, segmented comparison, or process-led composition rather than a decorative symbol.",
                    "undercovered_angle": "Reveal the overlooked layer with evidence-led objects, sector cues, document fragments, or hidden-detail metaphors instead of generic cooperation symbols.",
                    "strategic_meaning": "Show systems, linkages, networks, or second-order outcomes so the visual explains why the fact matters beyond the event itself.",
                    "takeaway": "Use a concrete decision-support or product-context surface that makes the next action feel informed and credible rather than ceremonial or abstract.",
                    "closing": "Use a concrete decision-support or product-context surface that makes the next action feel informed and credible rather than ceremonial or abstract.",
                }.get(story_role.casefold(), "Choose one strong explanatory composition that advances the story instead of repeating the previous slide's visual formula.")
                focus_parts = [
                    f"Visual brief for this slide: {cleaned.get('headline')}",
                    (
                        "visual evidence cues: "
                        + "; ".join(evidence_cues)
                        if evidence_cues
                        else ""
                    ),
                    role_focus_line,
                    f"primary concepts: {'; '.join(semantic_subjects)}" if semantic_subjects else "",
                    f"story role: {story_role}" if story_role else "",
                    (
                        "brand subject cues: "
                        + ", ".join(brand_subject_terms)
                        if brand_subject_terms
                        else ""
                    ),
                    f"supporting idea: {cleaned.get('supporting_line')}" if cleaned.get("supporting_line") else "",
                    f"topic anchors: {topic_keywords}" if topic_keywords else "",
                    cls._story_role_visual_execution_guidance(story_role),
                    "avoid importing objects or labels from unrelated reference templates",
                ]
                cleaned["visual_focus"] = cls._normalize_metadata_text(
                    ". ".join(part for part in focus_parts if part),
                    limit=420,
                )
            else:
                cleaned["visual_focus"] = visual_focus
            sanitized.append(cleaned)
        return sanitized

    @classmethod
    def _normalize_structured_carousel_slides(
        cls,
        raw_slides: list[Any],
        *,
        headline: str,
        supporting_line: str,
        cta: str,
        proof_points: list[str],
        stat_highlights: list[str],
        target_slide_count: int,
        mistake_style: bool,
        fallback_slides: list[dict[str, Any]],
        carousel_archetype: str = "",
    ) -> list[dict[str, Any]]:
        normalized_slides: list[dict[str, Any]] = []
        fallback_count = len(fallback_slides)
        slide_count_hint = target_slide_count or len(raw_slides) or fallback_count
        for index, raw_slide in enumerate(raw_slides, start=1):
            if not isinstance(raw_slide, dict):
                continue
            fallback_slide = fallback_slides[index - 1] if index - 1 < fallback_count else {}
            slide_metadata = raw_slide.get("metadata") if isinstance(raw_slide.get("metadata"), dict) else {}
            explicit_title = cls._normalize_metadata_text(
                raw_slide.get("headline")
                or raw_slide.get("title")
                or raw_slide.get("label")
                or raw_slide.get("section_title"),
                limit=120,
            )
            support_candidates = [
                raw_slide.get("supporting_line"),
                raw_slide.get("body"),
                raw_slide.get("summary"),
                raw_slide.get("description"),
                raw_slide.get("detail"),
                fallback_slide.get("supporting_line"),
                supporting_line,
            ]
            resolved_support = next(
                (
                    cls._normalize_metadata_text(candidate, limit=220)
                    for candidate in support_candidates
                    if cls._normalize_metadata_text(candidate, limit=220)
                ),
                "",
            )
            raw_points = (
                raw_slide.get("proof_points")
                or raw_slide.get("bullets")
                or raw_slide.get("key_points")
                or raw_slide.get("stat_highlights")
                or raw_slide.get("facts")
                or raw_slide.get("callouts")
            )
            slide_points = cls._normalize_metadata_list(raw_points, limit=4)
            if not slide_points:
                slide_points = cls._normalize_metadata_list(fallback_slide.get("proof_points"), limit=3)
            if not slide_points and resolved_support:
                slide_points = [
                    point
                    for point in [resolved_support, *proof_points[:2], *stat_highlights[:1]]
                    if point and point.casefold() != resolved_support.casefold()
                ][:3]
            role = cls._carousel_story_role(
                cls._carousel_role_for_archetype(
                    raw_slide.get("role") or raw_slide.get("slide_role") or slide_metadata.get("story_role"),
                    archetype=carousel_archetype,
                    index=index,
                    slide_count=slide_count_hint,
                ),
                index=index,
                slide_count=slide_count_hint,
                has_cta=False,
            )
            story_role = cls._normalize_metadata_text(
                cls._carousel_role_for_archetype(
                    raw_slide.get("role") or raw_slide.get("slide_role") or slide_metadata.get("story_role"),
                    archetype=carousel_archetype,
                    index=index,
                    slide_count=slide_count_hint,
                ),
                limit=48,
            )
            normalized_story_role = cls._carousel_story_role_token(story_role or role)
            point_budget = cls._carousel_role_point_budget(
                normalized_story_role,
                is_final_slide=index == slide_count_hint,
            )
            body_point_budget = cls._carousel_body_point_budget(
                normalized_story_role,
                is_final_slide=index == slide_count_hint,
            )
            if explicit_title and cls._is_generic_carousel_education_label(explicit_title):
                explicit_title = ""
            if mistake_style:
                resolved_title = explicit_title or cls._infer_mistake_headline(
                    raw_slide.get("headline") or resolved_support or slide_points[:1],
                    fallback_focus=supporting_line or headline,
                    index=index,
                )
            else:
                resolved_title = (
                    explicit_title
                    or cls._normalize_metadata_text(fallback_slide.get("headline"), limit=120)
                    or cls._carousel_role_title(story_role or role, headline=headline, cta=cta)
                )
            slide = {
                "role": role,
                "headline": resolved_title,
                "supporting_line": resolved_support,
                "body": cls._carousel_slide_body_text(
                    raw_slide,
                    fallback_text=cls._normalize_metadata_text(fallback_slide.get("body"), limit=320) or resolved_support,
                ),
                "body_points": cls._normalize_metadata_list(
                    raw_slide.get("body_points"),
                    limit=max(body_point_budget, 1),
                ),
                "proof_points": [
                    point
                    for point in slide_points
                    if not resolved_support or point.casefold() != resolved_support.casefold()
                ][:point_budget],
                "stat_highlights": cls._normalize_metadata_list(raw_slide.get("stat_highlights"), limit=3),
                "cta": cls._normalize_metadata_text(raw_slide.get("cta"), limit=90) or (cta if role == "closing" else ""),
                "visual_focus": cls._normalize_metadata_text(raw_slide.get("visual_focus"), limit=160),
                "transition_note": cls._normalize_metadata_text(raw_slide.get("transition_note"), limit=160),
                "metadata": {
                    **slide_metadata,
                    "story_role": story_role or role,
                    "carousel_archetype": carousel_archetype or slide_metadata.get("carousel_archetype") or "",
                },
            }
            if not slide["body_points"] and body_point_budget:
                slide["body_points"] = cls._normalize_metadata_list(
                    raw_slide.get("proof_points")
                    or raw_slide.get("bullets")
                    or raw_slide.get("key_points")
                    or fallback_slide.get("body_points")
                    or fallback_slide.get("proof_points"),
                    limit=body_point_budget,
                )
            if not slide["body_points"] and body_point_budget and slide["supporting_line"]:
                slide["body_points"] = [slide["supporting_line"]]
            if not slide["headline"]:
                continue
            if not slide["supporting_line"] and slide["proof_points"]:
                slide["supporting_line"] = slide["proof_points"][0]
                slide["proof_points"] = slide["proof_points"][1:4]
            normalized_slides.append(slide)

        deduped: list[dict[str, Any]] = []
        for slide in normalized_slides:
            slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
            slide_story_role = cls._normalize_metadata_text(
                slide_metadata.get("story_role") or slide.get("role"),
                limit=48,
            ).casefold().replace(" ", "_")
            if any(
                cls._carousel_slides_semantically_overlap(slide, existing)
                and cls._normalize_metadata_text(
                    (
                        existing.get("metadata").get("story_role")
                        if isinstance(existing.get("metadata"), dict)
                        else existing.get("role")
                    )
                    or existing.get("role"),
                    limit=48,
                ).casefold().replace(" ", "_")
                == slide_story_role
                for existing in deduped
            ):
                continue
            deduped.append(slide)
        desired_slide_count = max(
            3,
            min(
                slide_count_hint or fallback_count or 0,
                fallback_count or slide_count_hint or 0,
            ),
        )
        if len(deduped) < desired_slide_count:
            for fallback_slide in fallback_slides:
                if any(cls._carousel_slides_semantically_overlap(fallback_slide, existing) for existing in deduped):
                    continue
                deduped.append(dict(fallback_slide))
                if len(deduped) >= desired_slide_count:
                    break
        return deduped

    @classmethod
    def _outline_to_carousel_slides(
        cls,
        outline: list[dict[str, Any]],
        *,
        headline: str,
        supporting_line: str,
        cta: str,
        proof_points: list[str],
        stat_highlights: list[str],
        body_sentences: list[str],
        request: AIOrchestrationRequest | None,
        target_slide_count: int,
        carousel_archetype: str = "",
    ) -> list[dict[str, Any]]:
        if not outline:
            return []
        insight_hierarchy = []
        if request is not None and isinstance(request.research_editorial_brief, dict):
            insight_hierarchy = cls._normalize_metadata_list(
                request.research_editorial_brief.get("insight_hierarchy"),
                limit=8,
            )
        support_pool = cls._normalize_metadata_list(
            [*body_sentences, supporting_line, *insight_hierarchy],
            limit=max(target_slide_count * 2, 8) if target_slide_count else 8,
        )
        proof_pool = cls._normalize_metadata_list(
            [*stat_highlights, *proof_points, *insight_hierarchy],
            limit=max(target_slide_count * 2, 8) if target_slide_count else 8,
        )
        slides: list[dict[str, Any]] = []
        used_supports: list[str] = []
        used_proof_points: set[str] = set()
        limited_outline = outline[:target_slide_count] if target_slide_count else outline
        slide_count = len(limited_outline)
        for index, item in enumerate(limited_outline, start=1):
            role_source = cls._carousel_role_for_archetype(
                item.get("role") or item.get("slide_role") or item.get("purpose"),
                archetype=carousel_archetype,
                index=index,
                slide_count=slide_count,
            ) or item.get("role") or item.get("slide_role") or item.get("purpose")
            role = cls._carousel_story_role(role_source, index=index, slide_count=slide_count)
            story_role = cls._normalize_metadata_text(role_source, limit=48) or role
            normalized_story_role = cls._carousel_story_role_token(story_role)
            title = cls._normalize_metadata_text(
                item.get("headline")
                or item.get("title")
                or item.get("label"),
                limit=120,
            )
            if title and cls._is_generic_carousel_education_label(title):
                title = ""
            item_bullets = cls._carousel_bullet_lines(
                item.get("proof_points")
                or item.get("bullets")
                or item.get("description"),
                limit=4,
            )
            item_notes = cls._carousel_bullet_lines(item.get("purpose"), limit=3)
            support_candidates = [
                *item_bullets,
                *item_notes,
                cls._normalize_metadata_text(item.get("supporting_line"), limit=220),
                cls._normalize_metadata_text(item.get("summary"), limit=220),
                cls._normalize_metadata_text(item.get("description"), limit=220),
            ]
            resolved_support = ""
            ranked_supports: list[tuple[int, int, str]] = []
            for position, candidate in enumerate([*support_candidates, *support_pool]):
                normalized = cls._normalize_metadata_text(candidate, limit=220)
                if not normalized:
                    continue
                if any(normalized.casefold() == existing.casefold() for existing in used_supports):
                    continue
                ranked_supports.append(
                    (
                        cls._carousel_support_score(normalized_story_role, normalized),
                        -position,
                        normalized,
                    )
                )
            if ranked_supports:
                ranked_supports.sort(reverse=True)
                resolved_support = ranked_supports[0][2]
                used_supports.append(resolved_support)
            explicit_points: list[str] = []
            for candidate in item_bullets:
                normalized = cls._normalize_metadata_text(candidate, limit=180)
                if not normalized:
                    continue
                if resolved_support and normalized.casefold() == resolved_support.casefold():
                    continue
                if normalized in explicit_points:
                    continue
                explicit_points.append(normalized)
                if len(explicit_points) >= 3:
                    break
            point_budget = cls._carousel_role_point_budget(
                normalized_story_role,
                is_final_slide=index == slide_count,
            )
            body_point_budget = cls._carousel_body_point_budget(
                normalized_story_role,
                is_final_slide=index == slide_count,
            )
            slide_points = explicit_points[:point_budget]
            if point_budget > len(slide_points) and normalized_story_role not in {
                "hook",
                "cover",
                "opening",
                "title",
                "implications",
                "implication",
                "strategic_meaning",
                "analysis",
                "what_matters",
                "takeaway",
                "close",
                "closing",
                "cta",
                "final",
            }:
                for candidate in proof_pool:
                    normalized = cls._normalize_metadata_text(candidate, limit=180)
                    if not normalized:
                        continue
                    lowered = normalized.casefold()
                    if resolved_support and lowered == resolved_support.casefold():
                        continue
                    if lowered in used_proof_points:
                        continue
                    if normalized in slide_points:
                        continue
                    slide_points.append(normalized)
                    used_proof_points.add(lowered)
                    if len(slide_points) >= point_budget:
                        break
            body_text = cls._normalize_metadata_text(
                item.get("body")
                or item.get("detail")
                or item.get("summary")
                or item.get("description")
                or item.get("purpose"),
                limit=320,
            )
            body_points = item_notes[:body_point_budget]
            if not body_points and body_point_budget:
                body_points = explicit_points[:body_point_budget]
            if not body_points and body_point_budget and resolved_support:
                body_points = [resolved_support]
            resolved_title = title or cls._carousel_role_title(str(role_source or role), headline=headline, cta=cta)
            slide = {
                "role": role,
                "headline": resolved_title,
                "supporting_line": resolved_support or supporting_line or headline,
                "body": body_text or resolved_support or "",
                "body_points": body_points,
                "proof_points": slide_points,
                "cta": cta if role == "closing" else "",
                "metadata": {"story_role": story_role, "carousel_archetype": carousel_archetype},
            }
            slides.append(slide)

        deduped: list[dict[str, Any]] = []
        for slide in slides:
            slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
            slide_story_role = cls._normalize_metadata_text(
                slide_metadata.get("story_role") or slide.get("role"),
                limit=48,
            ).casefold().replace(" ", "_")
            if any(
                cls._carousel_slides_semantically_overlap(slide, existing)
                and cls._normalize_metadata_text(
                    (
                        existing.get("metadata").get("story_role")
                        if isinstance(existing.get("metadata"), dict)
                        else existing.get("role")
                    )
                    or existing.get("role"),
                    limit=48,
                ).casefold().replace(" ", "_")
                == slide_story_role
                for existing in deduped
            ):
                continue
            deduped.append(slide)
        return deduped

    @classmethod
    def _carousel_slide_body_text(
        cls,
        slide: dict[str, Any],
        *,
        fallback_text: str = "",
    ) -> str:
        for key in ("body", "detail", "summary", "description", "narrative"):
            text = cls._normalize_metadata_text(slide.get(key), limit=320)
            if text:
                return text
        body_points = cls._normalize_metadata_list(slide.get("body_points"), limit=4)
        if body_points:
            return ". ".join(body_points).strip()[:320]
        supporting_line = cls._normalize_metadata_text(slide.get("supporting_line"), limit=220)
        proof_points = cls._normalize_metadata_list(slide.get("proof_points"), limit=3)
        if supporting_line and proof_points:
            return f"{supporting_line} {' '.join(proof_points[:2])}".strip()[:320]
        if supporting_line:
            return supporting_line
        if proof_points:
            return ". ".join(proof_points).strip()[:320]
        return cls._normalize_metadata_text(fallback_text, limit=320)

    @classmethod
    def _carousel_expected_story_roles(
        cls,
        *,
        request: AIOrchestrationRequest | None,
        metadata: dict[str, Any],
        fallback_slides: list[dict[str, Any]],
        slide_count: int,
    ) -> list[str]:
        carousel_archetype = cls._carousel_infer_archetype(request=request, metadata=metadata)
        archetype_roles = cls._carousel_archetype_role_sequence(
            carousel_archetype,
            slide_count=slide_count,
        )
        outline = cls._carousel_outline_candidates(request, metadata)
        if outline:
            roles: list[str] = []
            for index, item in enumerate(outline[:slide_count], start=1):
                role = cls._carousel_role_for_archetype(
                    item.get("role") or item.get("slide_role") or item.get("purpose"),
                    archetype=carousel_archetype,
                    index=index,
                    slide_count=slide_count,
                )
                if not role:
                    if index == 1:
                        role = "hook"
                    elif index == slide_count:
                        role = "takeaway"
                    else:
                        role = "detail"
                roles.append(role)
            return roles
        if archetype_roles:
            return archetype_roles
        roles = []
        for index, slide in enumerate(fallback_slides[:slide_count], start=1):
            slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
            role = cls._carousel_role_for_archetype(
                slide_metadata.get("story_role") or slide.get("role"),
                archetype=carousel_archetype,
                index=index,
                slide_count=slide_count,
            )
            if not role:
                if index == 1:
                    role = "hook"
                elif index == slide_count:
                    role = "takeaway"
                else:
                    role = "detail"
            roles.append(role)
        return roles

    @classmethod
    def _carousel_story_role_guidance(cls, story_role: str) -> str:
        normalized = cls._normalize_metadata_text(story_role, limit=48).casefold().replace(" ", "_")
        if normalized in {"hook", "cover", "opening", "title"}:
            return "This slide must hook the reader immediately with the hidden angle, not recap the entire story."
        if normalized in {"context", "setup", "intro"}:
            return "This slide should frame the context cleanly and set up the analytical sequence."
        if normalized in {"list_item"}:
            return "This slide should teach exactly one item using a repeated mini-structure such as concept, explanation, example, and consequence."
        if normalized in {"comparison_item"}:
            return "This slide should cover one option only using what it is, how it works, and where it fits."
        if normalized in {"problem_frame"}:
            return "This slide should define the pain point clearly before the solution appears."
        if normalized in {"solution_intro"}:
            return "This slide should introduce the solution and response pattern without turning into a feature dump."
        if normalized in {"feature_cluster"}:
            return "This slide should explain one capability cluster or workflow clearly, not the entire product story."
        if normalized in {"value_close"}:
            return "This slide should close on practical value or decision payoff, not generic hype."
        if normalized in {"structure", "deal_structure", "what_happened", "mechanics", "breakdown"}:
            return "This slide should unpack the factual structure or mechanics clearly, not jump to generic implications."
        if normalized in {"undercovered_angle", "missed_angle", "angle"}:
            return "This slide should surface what most coverage missed, overlooked, or simplified."
        if normalized in {"implications", "implication", "strategic_meaning", "analysis", "what_matters"}:
            return "This slide should explain the strategic implication or second-order meaning, not repeat the hook."
        if normalized in {"takeaway", "close", "closing", "cta", "final"}:
            return "This slide should close the sequence cleanly and contain the only CTA treatment if one is used."
        return "This slide should advance the story with one distinct idea."

    @classmethod
    def _carousel_is_editorial_close_role(cls, story_role: str) -> bool:
        normalized = cls._normalize_metadata_text(story_role, limit=48).casefold().replace(" ", "_")
        return normalized not in {"", "takeaway", "close", "closing", "cta", "final"}

    @classmethod
    def _enforce_carousel_editorial_progression(
        cls,
        slides: list[dict[str, Any]],
        *,
        request: AIOrchestrationRequest | None,
        metadata: dict[str, Any],
        fallback_slides: list[dict[str, Any]],
        headline: str,
        supporting_line: str,
        cta: str,
    ) -> list[dict[str, Any]]:
        if not slides:
            return []
        repaired = [deepcopy(slide) for slide in slides]
        slide_count = len(repaired)
        expected_story_roles = cls._carousel_expected_story_roles(
            request=request,
            metadata=metadata,
            fallback_slides=fallback_slides,
            slide_count=slide_count,
        )
        first_headline = cls._normalize_metadata_text(repaired[0].get("headline"), limit=140)
        used_supports: set[str] = set()
        for index, slide in enumerate(repaired, start=1):
            fallback_slide = fallback_slides[index - 1] if index - 1 < len(fallback_slides) else {}
            slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
            expected_story_role = expected_story_roles[index - 1] if index - 1 < len(expected_story_roles) else ""
            broad_role = "hook" if index == 1 else "closing" if index == slide_count else "intro" if expected_story_role == "context" else "detail"
            current_story_role = cls._normalize_metadata_text(
                slide_metadata.get("story_role") or slide.get("role"),
                limit=48,
            ).casefold().replace(" ", "_")
            story_role = expected_story_role or current_story_role or broad_role
            slide["role"] = broad_role
            slide_metadata["story_role"] = story_role
            slide_metadata["role_guidance"] = cls._carousel_story_role_guidance(story_role)

            normalized_headline = cls._normalize_metadata_text(slide.get("headline"), limit=120)
            needs_role_title = (
                not normalized_headline
                or cls._is_generic_carousel_education_label(normalized_headline)
                or (index > 1 and first_headline and normalized_headline.casefold() == first_headline.casefold())
                or (index < slide_count and cls._is_promotional_line(normalized_headline))
            )
            if needs_role_title:
                slide["headline"] = (
                    cls._normalize_metadata_text(fallback_slide.get("headline"), limit=120)
                    or cls._carousel_role_title(story_role, headline=headline, cta=cta)
                )

            slide_support = cls._normalize_metadata_text(slide.get("supporting_line"), limit=220)
            fallback_support = cls._normalize_metadata_text(fallback_slide.get("supporting_line"), limit=220)
            if (
                not slide_support
                or slide_support.casefold() in used_supports
                or (index > 1 and supporting_line and slide_support.casefold() == supporting_line.casefold())
            ):
                slide_support = fallback_support or slide_support or supporting_line or headline
                slide["supporting_line"] = slide_support
            if slide_support:
                used_supports.add(slide_support.casefold())

            body_text = cls._carousel_slide_body_text(slide, fallback_text=cls._carousel_slide_body_text(fallback_slide, fallback_text=slide_support))
            if body_text:
                slide["body"] = body_text

            if index < slide_count:
                slide["cta"] = ""
            else:
                slide["cta"] = cls._normalize_metadata_text(cta or slide.get("cta"), limit=90)
                if cls._carousel_is_editorial_close_role(story_role):
                    if not slide["headline"] or cls._is_promotional_line(slide["headline"]):
                        fallback_headline = cls._normalize_metadata_text(fallback_slide.get("headline"), limit=120)
                        if cls._is_promotional_line(fallback_headline):
                            fallback_headline = ""
                        slide["headline"] = (
                            fallback_headline
                            or cls._carousel_role_title(story_role, headline=headline, cta=cta)
                        )
                elif not slide["headline"] or cls._is_promotional_line(slide["headline"]):
                    slide["headline"] = cls._carousel_role_title("closing", headline=headline, cta=cta)

            if not cls._normalize_metadata_list(slide.get("proof_points"), limit=3):
                fallback_points = cls._normalize_metadata_list(fallback_slide.get("proof_points"), limit=3)
                if fallback_points:
                    slide["proof_points"] = fallback_points

            fallback_stats = cls._normalize_metadata_list(fallback_slide.get("stat_highlights"), limit=3)
            current_stats = cls._normalize_metadata_list(slide.get("stat_highlights"), limit=3)
            slide["stat_highlights"] = current_stats or fallback_stats
            slide["metadata"] = slide_metadata
        return repaired

    @classmethod
    def _validate_carousel_semantic_progression(
        cls,
        slides: list[dict[str, Any]],
        *,
        request: AIOrchestrationRequest | None,
        metadata: dict[str, Any],
        fallback_slides: list[dict[str, Any]],
        headline: str,
        supporting_line: str,
        cta: str,
    ) -> list[dict[str, Any]]:
        if not slides:
            return []
        repaired = [deepcopy(slide) for slide in slides]
        expected_story_roles = cls._carousel_expected_story_roles(
            request=request,
            metadata=metadata,
            fallback_slides=fallback_slides,
            slide_count=max(len(repaired), len(fallback_slides)),
        )
        desired_count = max(
            len(repaired),
            len(expected_story_roles),
            min(max(len(fallback_slides), 0), max(len(expected_story_roles), 0)),
        )
        if desired_count > len(repaired):
            for index in range(len(repaired), desired_count):
                fallback_slide = fallback_slides[index] if index < len(fallback_slides) else {}
                fallback_copy = dict(fallback_slide) if isinstance(fallback_slide, dict) else {}
                if not fallback_copy:
                    role = expected_story_roles[index] if index < len(expected_story_roles) else ("takeaway" if index == desired_count - 1 else "detail")
                    fallback_copy = {
                        "role": "closing" if index == desired_count - 1 else "detail",
                        "headline": cls._carousel_role_title(role, headline=headline, cta=cta),
                        "supporting_line": supporting_line or headline,
                        "proof_points": [],
                        "cta": cls._normalize_metadata_text(cta, limit=90) if index == desired_count - 1 else "",
                        "metadata": {"story_role": role},
                    }
                repaired.append(fallback_copy)

        hook_slide = repaired[0]
        prior_slides: list[dict[str, Any]] = []
        seen_roles: dict[str, int] = {}
        for index, slide in enumerate(repaired, start=1):
            fallback_slide = fallback_slides[index - 1] if index - 1 < len(fallback_slides) else {}
            slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
            expected_story_role = expected_story_roles[index - 1] if index - 1 < len(expected_story_roles) else ""
            current_story_role = cls._normalize_metadata_text(
                slide_metadata.get("story_role") or slide.get("role"),
                limit=48,
            ).casefold().replace(" ", "_")
            story_role = expected_story_role or current_story_role or ("takeaway" if index == len(repaired) else "detail")
            slide_metadata["story_role"] = story_role
            slide_metadata["role_guidance"] = cls._carousel_story_role_guidance(story_role)
            seen_roles[story_role] = seen_roles.get(story_role, 0) + 1

            semantic_overlap_with_hook = index > 1 and cls._carousel_slides_semantically_overlap(slide, hook_slide)
            semantic_overlap_with_prior = any(
                cls._carousel_slides_semantically_overlap(slide, prior)
                for prior in prior_slides
            )
            duplicate_non_detail_role = story_role not in {"detail", "details"} and seen_roles[story_role] > 1
            needs_semantic_repair = semantic_overlap_with_hook or semantic_overlap_with_prior or duplicate_non_detail_role

            if needs_semantic_repair:
                fallback_headline = cls._normalize_metadata_text(fallback_slide.get("headline"), limit=120)
                fallback_support = cls._normalize_metadata_text(fallback_slide.get("supporting_line"), limit=220)
                fallback_body = cls._carousel_slide_body_text(
                    fallback_slide,
                    fallback_text=fallback_support or supporting_line or headline,
                )
                fallback_points = cls._normalize_metadata_list(fallback_slide.get("proof_points"), limit=3)
                fallback_stats = cls._normalize_metadata_list(fallback_slide.get("stat_highlights"), limit=3)
                preferred_headline = fallback_headline or cls._carousel_role_title(story_role, headline=headline, cta=cta)
                if story_role in {"undercovered_angle", "missed_angle", "angle"}:
                    normalized_preferred = cls._normalize_metadata_text(preferred_headline, limit=120).casefold()
                    if normalized_preferred in {
                        cls._normalize_metadata_text(headline, limit=120).casefold(),
                        cls._normalize_metadata_text(hook_slide.get("headline"), limit=120).casefold(),
                        "the overlooked headline",
                    }:
                        preferred_headline = cls._carousel_role_title("undercovered_angle", headline=headline, cta=cta)
                if story_role in {"implications", "implication", "strategic_meaning", "analysis", "what_matters"}:
                    normalized_preferred = cls._normalize_metadata_text(preferred_headline, limit=120).casefold()
                    if normalized_preferred in {
                        cls._normalize_metadata_text(headline, limit=120).casefold(),
                        cls._normalize_metadata_text(hook_slide.get("headline"), limit=120).casefold(),
                    }:
                        preferred_headline = cls._carousel_role_title("strategic_meaning", headline=headline, cta=cta)
                slide["headline"] = preferred_headline
                if fallback_support:
                    slide["supporting_line"] = fallback_support
                elif semantic_overlap_with_hook or semantic_overlap_with_prior:
                    slide["supporting_line"] = cls._normalize_metadata_text(
                        cls._carousel_slide_body_text(slide, fallback_text=supporting_line or headline),
                        limit=220,
                    ) or cls._carousel_role_title(story_role, headline=headline, cta=cta)
                if fallback_body:
                    slide["body"] = fallback_body
                if fallback_points:
                    slide["proof_points"] = fallback_points
                if fallback_stats:
                    slide["stat_highlights"] = fallback_stats

            if index < len(repaired):
                slide["cta"] = ""
            else:
                slide["cta"] = cls._normalize_metadata_text(cta or slide.get("cta"), limit=90)
                if cls._carousel_is_editorial_close_role(story_role):
                    slide_metadata["story_role"] = story_role
                    slide_metadata["role_guidance"] = cls._carousel_story_role_guidance(story_role)
                    if (
                        not cls._normalize_metadata_text(slide.get("headline"), limit=120)
                        or cls._is_promotional_line(str(slide.get("headline") or ""))
                    ):
                        fallback_headline = cls._normalize_metadata_text(fallback_slide.get("headline"), limit=120)
                        if cls._is_promotional_line(fallback_headline):
                            fallback_headline = ""
                        slide["headline"] = (
                            fallback_headline
                            or cls._carousel_role_title(story_role, headline=headline, cta=cta)
                        )
                else:
                    slide_metadata["story_role"] = "takeaway"
                    slide_metadata["role_guidance"] = cls._carousel_story_role_guidance("takeaway")
                    if (
                        not cls._normalize_metadata_text(slide.get("headline"), limit=120)
                        or cls._is_promotional_line(slide.get("headline"))
                    ):
                        slide["headline"] = cls._carousel_role_title("takeaway", headline=headline, cta=cta)

            if story_role in {"undercovered_angle", "missed_angle", "angle"} and (
                not cls._normalize_metadata_text(slide.get("headline"), limit=120)
                or cls._is_promotional_line(str(slide.get("headline") or ""))
                or cls._normalize_metadata_text(slide.get("headline"), limit=120).casefold() == "the overlooked headline"
            ):
                slide["headline"] = cls._carousel_role_title("undercovered_angle", headline=headline, cta=cta)
            if story_role in {"implications", "implication", "strategic_meaning", "analysis", "what_matters"} and (
                not cls._normalize_metadata_text(slide.get("headline"), limit=120)
                or cls._is_promotional_line(str(slide.get("headline") or ""))
            ):
                slide["headline"] = cls._carousel_role_title("strategic_meaning", headline=headline, cta=cta)

            slide["metadata"] = slide_metadata
            prior_slides.append(slide)
        return repaired

    @classmethod
    def _apply_claim_evidence_to_carousel_slides(
        cls,
        slides: list[dict[str, Any]],
        *,
        claim_evidence_pairs: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        if not slides or not claim_evidence_pairs:
            return slides
        repaired = [deepcopy(slide) for slide in slides]
        slot_views = []
        for slide in repaired:
            slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
            slot_views.append(
                {
                    "story_role": slide_metadata.get("story_role") or slide.get("role"),
                    "headline": slide.get("headline"),
                    "supporting_line": slide.get("supporting_line"),
                    "body": slide.get("body"),
                    "body_points": slide.get("body_points"),
                    "proof_points": slide.get("proof_points"),
                    "stat_highlights": slide.get("stat_highlights"),
                }
            )
        allocations = cls._allocate_claim_evidence_pairs_to_slots(
            slot_views,
            claim_evidence_pairs=claim_evidence_pairs,
            format_family="carousel",
        )
        for index, slide in enumerate(repaired):
            assigned_pairs = allocations[index] if index < len(allocations) else []
            slide["claim_evidence_pairs"] = assigned_pairs
            claim_lines = cls._claim_evidence_pair_lines(assigned_pairs, limit=2)
            if not claim_lines:
                continue
            slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
            story_role = cls._normalize_metadata_text(
                slide_metadata.get("story_role") or slide.get("role"),
                limit=48,
            ).casefold().replace(" ", "_")
            existing_proof_points = cls._normalize_metadata_list(slide.get("proof_points"), limit=3)
            existing_body_points = cls._normalize_metadata_list(slide.get("body_points"), limit=3)
            if story_role in {"hook", "cover", "opening", "title"}:
                slide["proof_points"] = []
                slide["body_points"] = existing_body_points[:1]
            elif story_role in {"implications", "implication", "strategic_meaning", "analysis", "what_matters", "takeaway", "close", "closing", "cta", "final"}:
                slide["proof_points"] = []
                slide["body_points"] = cls._dedupe_metadata_collection(
                    [
                        *existing_body_points,
                        *claim_lines,
                    ],
                    blocked_texts=[slide.get("headline"), slide.get("supporting_line")],
                    limit=2,
                )
            else:
                slide["proof_points"] = cls._dedupe_metadata_collection(
                    [
                        *existing_proof_points,
                        *claim_lines,
                    ],
                    blocked_texts=[slide.get("headline"), slide.get("supporting_line"), slide.get("cta")],
                    limit=3,
                )
                slide["body_points"] = cls._dedupe_metadata_collection(
                    [
                        *existing_body_points,
                        *claim_lines,
                    ],
                    blocked_texts=[slide.get("headline"), slide.get("supporting_line")],
                    limit=3,
                )
            if story_role in {
                "structure",
                "deal_structure",
                "what_happened",
                "mechanics",
                "breakdown",
                "undercovered_angle",
                "missed_angle",
                "angle",
                "strategic_meaning",
                "implications",
                "implication",
                "analysis",
                "what_matters",
            }:
                body_text = cls._normalize_metadata_text(slide.get("body"), limit=320)
                supporting = cls._normalize_metadata_text(slide.get("supporting_line"), limit=220)
                if not body_text or body_text.casefold() == supporting.casefold():
                    slide["body"] = claim_lines[0]
        return repaired

    @classmethod
    def _fallback_carousel_slide_specs(
        cls,
        *,
        text_payload: StructuredTextPayload,
        request: AIOrchestrationRequest | None,
        creative_decision: CreativeDecisionPayload | None,
        metadata: dict[str, Any],
        headline: str,
        body_sentences: list[str],
        supporting_line: str,
        proof_points: list[str],
        stat_highlights: list[str],
        target_slide_count: int,
        sequence_pack_slides: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        mistake_style = cls._has_mistake_carousel_signals(
            headline,
            supporting_line,
            text_payload.body,
            metadata.get("section_label"),
            *proof_points,
            *stat_highlights,
        )
        if mistake_style:
            wants_multiple = cls._prefers_multiple_mistake_slides(
                headline,
                supporting_line,
                text_payload.body,
                *proof_points,
                *stat_highlights,
            )
            mistake_groups = cls._mistake_detail_groups(
                headline=headline,
                supporting_line=supporting_line,
                proof_points=proof_points,
                stat_highlights=stat_highlights,
                body_sentences=body_sentences,
            )
            minimum_detail_count = 3 if wants_multiple else 1
            detail_slot_count = (
                max(target_slide_count - 2, len(mistake_groups), minimum_detail_count)
                if target_slide_count
                else max(len(mistake_groups), minimum_detail_count)
            )
            while len(mistake_groups) < detail_slot_count:
                fallback_index = len(mistake_groups) + 1
                fallback_focus = (
                    cls._strip_mistake_markers(
                        stat_highlights[fallback_index - 1]
                        if fallback_index - 1 < len(stat_highlights)
                        else proof_points[min((fallback_index - 1) * 2, len(proof_points) - 1)] if proof_points else supporting_line or headline
                    )
                    or cls._strip_mistake_markers(supporting_line)
                    or cls._strip_mistake_markers(headline)
                )
                heuristic_points = []
                for point in proof_points[(fallback_index - 1) * 2 : (fallback_index - 1) * 2 + 4]:
                    normalized = cls._normalize_metadata_text(point, limit=180)
                    if normalized and not cls._is_promotional_line(normalized):
                        heuristic_points.append(normalized)
                mistake_groups.append(
                    {
                        "headline": cls._infer_mistake_headline(fallback_focus, fallback_focus=fallback_focus, index=fallback_index),
                        "supporting_line": cls._mistake_supporting_line(
                            *body_sentences[(fallback_index - 1) * 2 : (fallback_index - 1) * 2 + 2],
                            supporting_line,
                        ),
                        "proof_points": heuristic_points,
                    }
                )
            cover_headline = headline
            if not cover_headline or cls._is_generic_carousel_education_label(cover_headline):
                cover_headline = cls._mistake_cover_headline(headline, supporting_line, text_payload.body, *proof_points, *stat_highlights)
            slides = [
                {
                    "role": "hook",
                    "headline": cover_headline or headline,
                    "supporting_line": supporting_line,
                    "proof_points": [],
                    "cta": "",
                }
            ]
            for index, group in enumerate(mistake_groups[:detail_slot_count], start=1):
                points = cls._normalize_metadata_list(group.get("proof_points"), limit=3)
                impact_lines = [point for point in points if cls.IMPACT_LINE_PATTERN.match(point)]
                fix_lines = [point for point in points if cls.FIX_LINE_PATTERN.match(point)]
                if not impact_lines:
                    inferred_impact = next(
                        (
                            cls._normalize_metadata_text(sentence, limit=180)
                            for sentence in body_sentences
                            if cls.IMPACT_LINE_PATTERN.match(cls._normalize_metadata_text(sentence, limit=180))
                        ),
                        "",
                    )
                    if inferred_impact:
                        impact_lines.append(inferred_impact)
                if not fix_lines:
                    inferred_fix = next(
                        (
                            cls._normalize_metadata_text(sentence, limit=180)
                            for sentence in body_sentences
                            if cls.FIX_LINE_PATTERN.match(cls._normalize_metadata_text(sentence, limit=180))
                        ),
                        "",
                    )
                    if inferred_fix:
                        fix_lines.append(inferred_fix)
                detail_points = [*impact_lines[:1], *fix_lines[:1]]
                remaining_points = [point for point in points if point not in detail_points]
                detail_points.extend(remaining_points[: max(0, 3 - len(detail_points))])
                slides.append(
                    {
                        "role": "detail",
                        "headline": cls._normalize_metadata_text(group.get("headline"), limit=90)
                        or cls._infer_mistake_headline("", fallback_focus=supporting_line or headline, index=index),
                        "supporting_line": cls._mistake_supporting_line(group.get("supporting_line"), supporting_line),
                        "proof_points": detail_points[:3],
                        "cta": "",
                    }
                )
            closing_headline = cls._normalize_metadata_text(
                text_payload.cta or supporting_line or headline,
                limit=120,
            ) or headline
            closing_line = cls._normalize_metadata_text(
                next(
                    (
                        candidate
                        for candidate in [
                            supporting_line,
                            *(sentence for sentence in reversed(body_sentences) if sentence.strip()),
                            text_payload.body,
                        ]
                        if cls._normalize_metadata_text(candidate, limit=200)
                        and cls._normalize_metadata_text(candidate, limit=200).casefold() != closing_headline.casefold()
                    ),
                    "",
                ),
                limit=200,
            )
            slides.append(
                {
                    "role": "closing",
                    "headline": closing_headline,
                    "supporting_line": closing_line,
                    "proof_points": [],
                    "cta": cls._normalize_metadata_text(text_payload.cta or closing_headline, limit=90),
                }
            )
            return slides

        outline_slides = cls._outline_to_carousel_slides(
            cls._carousel_outline_candidates(request, metadata),
            headline=headline,
            supporting_line=supporting_line,
            cta=cls._normalize_metadata_text(text_payload.cta, limit=90),
            proof_points=proof_points,
            stat_highlights=stat_highlights,
            body_sentences=body_sentences,
            request=request,
            target_slide_count=target_slide_count or len(sequence_pack_slides),
            carousel_archetype=cls._carousel_infer_archetype(request=request, metadata=metadata),
        )
        if outline_slides:
            return outline_slides

        detail_segments = cls._collapse_carousel_segments(
            body_sentences,
            max_slides=max(target_slide_count - 2, 1) if target_slide_count else max(len(body_sentences), 1),
        )
        if not detail_segments:
            detail_segments = cls._collapse_carousel_segments(proof_points, max_slides=max(target_slide_count - 2, 1) if target_slide_count else max(len(proof_points), 1))
        unique_support_candidates = cls._normalize_metadata_list(
            [
                *detail_segments,
                *stat_highlights,
                *proof_points,
                supporting_line,
                headline,
            ],
            limit=max((target_slide_count or 4) * 3, 8),
        )
        include_intro_slide = bool(
            (target_slide_count and target_slide_count >= 5)
            or (len(stat_highlights) > 1 and len(detail_segments) > 2)
        )
        detail_slot_count = (
            max(target_slide_count - (3 if include_intro_slide else 2), len(detail_segments), 1)
            if target_slide_count
            else max(len(detail_segments), 1)
        )
        while len(detail_segments) < detail_slot_count and unique_support_candidates:
            next_candidate = next(
                (
                    candidate
                    for candidate in unique_support_candidates
                    if candidate and candidate not in detail_segments and candidate.casefold() != supporting_line.casefold()
                ),
                "",
            )
            if not next_candidate:
                break
            detail_segments.append(next_candidate)
        slides = [
            {
                "role": "cover",
                "headline": headline,
                "supporting_line": supporting_line,
                "proof_points": proof_points[: min(len(proof_points), 3) or 0],
                "cta": "",
            }
        ]
        if include_intro_slide:
            intro_headline = cls._normalize_metadata_text(stat_highlights[0] if stat_highlights else "", limit=120)
            if not intro_headline or cls._is_generic_carousel_education_label(intro_headline):
                intro_headline = "What changed"
            intro_support = next(
                (
                    candidate
                    for candidate in unique_support_candidates
                    if candidate.casefold() not in {headline.casefold(), supporting_line.casefold()}
                ),
                supporting_line,
            )
            slides.append(
                {
                    "role": "intro",
                    "headline": intro_headline,
                    "supporting_line": intro_support,
                    "proof_points": [
                        point
                        for point in proof_points[:3]
                        if point.casefold() != cls._normalize_metadata_text(intro_support, limit=180).casefold()
                    ][:3],
                    "cta": "",
                }
            )

        used_titles = {headline.casefold()} if headline else set()
        used_supports = {supporting_line.casefold()} if supporting_line else set()
        for index, segment in enumerate(detail_segments[:detail_slot_count], start=1):
            segment_text = cls._normalize_metadata_text(segment, limit=220)
            title_candidates = [
                stat_highlights[index - 1] if index - 1 < len(stat_highlights) else "",
                proof_points[(index - 1) * 2] if (index - 1) * 2 < len(proof_points) else "",
                segment_text,
            ]
            detail_title = next(
                (
                    cls._normalize_metadata_text(candidate, limit=90)
                    for candidate in title_candidates
                    if cls._normalize_metadata_text(candidate, limit=90)
                    and not cls._is_generic_carousel_education_label(candidate)
                    and cls._normalize_metadata_text(candidate, limit=90).casefold() not in used_titles
                ),
                "",
            )
            if not detail_title:
                detail_title = cls._carousel_role_title("detail", headline=headline, cta=text_payload.cta)
                if index > 1:
                    detail_title = f"{detail_title} {index}"
            used_titles.add(detail_title.casefold())
            detail_support = segment_text
            if not detail_support or detail_support.casefold() in used_supports:
                detail_support = next(
                    (
                        candidate
                        for candidate in unique_support_candidates
                        if candidate.casefold() not in used_supports
                    ),
                    supporting_line or headline,
                )
            used_supports.add(detail_support.casefold())
            detail_points = [
                point
                for point in proof_points[(index - 1) * 2 : (index - 1) * 2 + 3]
                if cls._normalize_metadata_text(point, limit=180)
                and cls._normalize_metadata_text(point, limit=180).casefold() != detail_support.casefold()
            ]
            if not detail_points:
                detail_points = [
                    candidate
                    for candidate in unique_support_candidates
                    if candidate.casefold() != detail_support.casefold()
                ][:2]
            slides.append(
                {
                    "role": "detail",
                    "headline": detail_title,
                    "supporting_line": detail_support,
                    "proof_points": detail_points[:3],
                    "cta": "",
                }
            )

        closing_headline = cls._normalize_metadata_text(text_payload.cta or headline, limit=120) or headline
        closing_line = next(
            (
                candidate
                for candidate in reversed(unique_support_candidates)
                if candidate
                and candidate.casefold() not in {closing_headline.casefold(), (text_payload.cta or "").casefold()}
                and candidate.casefold() not in used_supports
            ),
            "",
        )
        if not closing_line:
            closing_line = next(
                (
                    candidate
                    for candidate in reversed(unique_support_candidates)
                    if candidate
                    and candidate.casefold() not in {closing_headline.casefold(), (text_payload.cta or "").casefold()}
                ),
                supporting_line or headline,
            )
        closing_points = [
            candidate
            for candidate in [*stat_highlights[-2:], *proof_points[-2:]]
            if cls._normalize_metadata_text(candidate, limit=180)
            and cls._normalize_metadata_text(candidate, limit=180).casefold() != cls._normalize_metadata_text(closing_line, limit=180).casefold()
        ][:3]
        slides.append(
            {
                "role": "closing",
                "headline": closing_headline,
                "supporting_line": cls._normalize_metadata_text(closing_line, limit=200),
                "proof_points": closing_points,
                "cta": cls._normalize_metadata_text(text_payload.cta, limit=90),
            }
        )
        return slides

    @classmethod
    def _build_carousel_slide_specs(
        cls,
        text_payload: StructuredTextPayload,
        *,
        request: AIOrchestrationRequest | None = None,
        creative_decision: CreativeDecisionPayload | None = None,
    ) -> list[dict[str, Any]]:
        metadata = text_payload.metadata or {}
        headline = cls._normalize_metadata_text(text_payload.headline, limit=180)
        body_sentences = cls._sentences(text_payload.body)
        proof_point_limit = max(
            cls._rough_collection_length(metadata.get("proof_points")),
            len(body_sentences),
            6,
        )
        stat_highlight_limit = max(
            cls._rough_collection_length(metadata.get("stat_highlights")),
            min(len(body_sentences), 8),
            4,
        )
        supporting_line = cls._normalize_metadata_text(
            metadata.get("supporting_line") or text_payload.body,
            limit=220,
        )
        clean_cta = cls._clean_carousel_cta_text(
            text_payload.cta,
            headline=headline,
            supporting_line=supporting_line,
        )
        proof_points = cls._normalize_metadata_list(metadata.get("proof_points"), limit=proof_point_limit)
        stat_highlights = cls._normalize_metadata_list(metadata.get("stat_highlights"), limit=stat_highlight_limit)
        claim_evidence_pairs = cls._merge_claim_evidence_pairs(
            metadata.get("claim_evidence_pairs"),
            cls._claim_evidence_pairs_from_research_brief(
                (request.research_editorial_brief if request is not None else None),
                limit=max(proof_point_limit, 4),
            ),
            limit=max(proof_point_limit, 4),
        )
        sequence_pack = (
            cls._template_sequence_pack(request, creative_decision=creative_decision)
            if request is not None
            else None
        )
        sequence_pack_slides = (
            [dict(item) for item in sequence_pack.get("slides", []) if isinstance(item, dict)]
            if isinstance(sequence_pack, dict)
            else []
        )
        carousel_archetype = cls._carousel_infer_archetype(request=request, metadata=metadata)
        outline_slide_count = len(cls._carousel_outline_candidates(request, metadata))
        target_slide_count = (
            cls._int_or_none(
                len(sequence_pack_slides) or outline_slide_count or metadata.get("preferred_slide_count")
                if (len(sequence_pack_slides) or outline_slide_count)
                else metadata.get("preferred_slide_count")
            )
            or cls._int_or_none(
                metadata.get("preferred_slide_count")
                or metadata.get("slide_count")
                or ((request.research_editorial_brief or {}).get("preferred_slide_count") if request and isinstance(request.research_editorial_brief, dict) else None)
            )
            or len(sequence_pack_slides)
            or outline_slide_count
        )
        mistake_style = cls._has_mistake_carousel_signals(
            headline,
            supporting_line,
            text_payload.body,
            metadata.get("section_label"),
            *proof_points,
            *stat_highlights,
        )
        fallback_slides = cls._fallback_carousel_slide_specs(
            text_payload=text_payload,
            request=request,
            creative_decision=creative_decision,
            metadata=metadata,
            headline=headline,
            body_sentences=body_sentences,
            supporting_line=supporting_line,
            proof_points=proof_points,
            stat_highlights=stat_highlights,
            target_slide_count=target_slide_count,
            sequence_pack_slides=sequence_pack_slides,
        )
        structured_source = metadata.get("carousel_slide_specs") or metadata.get("slides")
        if isinstance(structured_source, list) and structured_source:
            normalized_slides = cls._normalize_structured_carousel_slides(
                structured_source,
                headline=headline,
                supporting_line=supporting_line,
                cta=clean_cta,
                proof_points=proof_points,
                stat_highlights=stat_highlights,
                target_slide_count=target_slide_count or len(structured_source),
                mistake_style=mistake_style,
                fallback_slides=fallback_slides,
                carousel_archetype=carousel_archetype,
            )
        else:
            normalized_slides = [dict(slide) for slide in fallback_slides]

        if len(normalized_slides) < 3:
            normalized_slides.insert(
                1,
                {
                    "role": "detail",
                    "headline": (
                        cls._infer_mistake_headline(stat_highlights[0] if stat_highlights else supporting_line, fallback_focus=headline, index=1)
                        if mistake_style
                        else stat_highlights[0] if stat_highlights else "Why it matters"
                    ),
                    "supporting_line": cls._mistake_supporting_line(supporting_line, headline) if mistake_style else supporting_line or headline,
                    "proof_points": ([] if mistake_style else proof_points[:2]),
                    "cta": "",
                },
            )

        if sequence_pack_slides:
            for index, slide in enumerate(normalized_slides):
                if index >= len(sequence_pack_slides):
                    break
                pack_slide = sequence_pack_slides[index]
                slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
                slide["metadata"] = {
                    **slide_metadata,
                    "reference_slide_index": int(pack_slide.get("slide_index") or index + 1),
                    "reference_slide_count": len(sequence_pack_slides),
                    "reference_template_id": str(pack_slide.get("template_id") or ""),
                    "reference_template_name": str(pack_slide.get("template_name") or ""),
                    "reference_template_asset_path": str(pack_slide.get("template_asset_path") or ""),
                    "reference_asset_path": str(pack_slide.get("reference_asset_path") or ""),
                    "reference_zone_map": pack_slide.get("zone_map"),
                    "reference_editable_fields": list(pack_slide.get("editable_fields") or []),
                    "logo_position": str(pack_slide.get("logo_position") or "").strip() or None,
                    "carousel_archetype": slide_metadata.get("carousel_archetype") or carousel_archetype,
                }

        normalized_slides = cls._enforce_carousel_editorial_progression(
            normalized_slides,
            request=request,
            metadata=metadata,
            fallback_slides=fallback_slides,
            headline=headline,
            supporting_line=supporting_line,
            cta=clean_cta,
        )
        normalized_slides = cls._validate_carousel_semantic_progression(
            normalized_slides,
            request=request,
            metadata=metadata,
            fallback_slides=fallback_slides,
            headline=headline,
            supporting_line=supporting_line,
            cta=clean_cta,
        )
        normalized_slides = cls._apply_claim_evidence_to_carousel_slides(
            normalized_slides,
            claim_evidence_pairs=claim_evidence_pairs,
        )
        normalized_slides = cls._sanitize_carousel_slide_specs(
            normalized_slides,
            request=request,
        )

        slide_count = len(normalized_slides)
        for index, slide in enumerate(normalized_slides, start=1):
            slide["slide_index"] = index
            slide["slide_count"] = slide_count
            slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
            slide["metadata"] = {
                **slide_metadata,
                "carousel_archetype": slide_metadata.get("carousel_archetype") or carousel_archetype,
            }
        return normalized_slides

    @staticmethod
    def build_carousel_slide_render_prompt(
        request: AIOrchestrationRequest,
        creative_decision: CreativeDecisionPayload,
        message_strategy: MessageStrategyPayload | None,
        slide: dict[str, Any],
        scene_graph: GenerationSceneGraph,
        reference_images: list[dict[str, Any]] | None = None,
        retry_note: str | None = None,
        visual_explanation_plan: dict[str, Any] | None = None,
        compiled_context: dict[str, Any] | None = None,
    ) -> str:
        compiled_context = dict(compiled_context or {})
        visual_identity = request.resolved_brand_context.get("visual_identity", {}) or {}
        design_system_guidance = AIOrchestratorService._design_system_prompt_guidance(visual_identity)
        palette = AIOrchestratorService._compact_palette_summary(visual_identity)
        palette_guidance = AIOrchestratorService._palette_role_guidance(visual_identity)
        strict_palette_contract = AIOrchestratorService._strict_palette_contract(visual_identity)
        typography = AIOrchestratorService._compact_typography_summary(visual_identity)
        brand_name = AIOrchestratorService._normalize_metadata_text(
            request.resolved_brand_context.get("brand_name") or "",
            limit=80,
        )
        platform = str(request.studio_panel.get("platform_preset") or "social")
        file_type = str(request.studio_panel.get("file_type") or "png").upper()
        canvas_fit_guidance = AIOrchestratorService._canvas_fit_guidance(request.studio_panel)
        reference_summary = AIOrchestratorService._compact_reference_assets(reference_images or [])
        slide_metadata = slide.get("metadata") if isinstance(slide.get("metadata"), dict) else {}
        has_reference_zone_map = isinstance(slide_metadata.get("reference_zone_map"), dict) and bool(
            (slide_metadata.get("reference_zone_map") or {}).get("zones")
        )
        planning_hints = creative_decision.planning_hints if isinstance(creative_decision.planning_hints, dict) else {}
        asset_strategy = creative_decision.asset_strategy if isinstance(creative_decision.asset_strategy, dict) else {}
        template_surface_policy = str(asset_strategy.get("template_surface_policy") or "").strip().lower()
        geometry_contract = AIOrchestratorService._compact_slide_geometry_contract(slide, scene_graph)
        reference_zone_guidance = AIOrchestratorService._reference_zone_layout_guidance(slide)
        layout_dna_contract = AIOrchestratorService._compact_layout_dna_contract(compiled_context)
        logo_position_hint = AIOrchestratorService._effective_logo_position_hint(
            request=request,
            creative_decision=creative_decision,
            text_payload={
                "headline": slide.get("headline"),
                "body": slide.get("supporting_line"),
                "cta": slide.get("cta"),
                "metadata": slide_metadata,
            },
        )
        logo_safe_zone_guidance = AIOrchestratorService._logo_safe_zone_guidance(
            request,
            hint=logo_position_hint,
        )
        reserved_logo_area = AIOrchestratorService._logo_reserved_area_label(logo_position_hint)
        logo_surface_guidance = AIOrchestratorService._logo_surface_guidance(
            background_tone=AIOrchestratorService._resolve_logo_background_tone(
                metadata=slide_metadata,
                creative_decision=creative_decision,
            )
        )
        slide_index = int(slide.get("slide_index") or 1)
        slide_count = int(slide.get("slide_count") or 1)
        story_role = AIOrchestratorService._normalize_metadata_text(
            slide_metadata.get("story_role") or slide.get("role"),
            limit=48,
        )
        carousel_archetype = AIOrchestratorService._normalize_metadata_text(
            slide_metadata.get("carousel_archetype"),
            limit=64,
        )
        message_theme = ""
        emotional_direction = ""
        if isinstance(message_strategy, MessageStrategyPayload):
            message_theme = AIOrchestratorService._normalize_metadata_text(
                message_strategy.primary_campaign_theme,
                limit=180,
            )
            emotional_direction = AIOrchestratorService._normalize_metadata_text(
                message_strategy.emotional_messaging_direction,
                limit=100,
            )
        slide_text_payload = StructuredTextPayload(
            headline=AIOrchestratorService._normalize_metadata_text(slide.get("headline"), limit=180),
            body=AIOrchestratorService._carousel_slide_body_text(
                slide,
                fallback_text=AIOrchestratorService._normalize_metadata_text(slide.get("supporting_line"), limit=220),
            ),
            cta=AIOrchestratorService._normalize_metadata_text(slide.get("cta"), limit=80),
            hashtags=[],
            metadata={
                "supporting_line": slide.get("supporting_line"),
                "proof_points": slide.get("proof_points"),
                "body_points": slide.get("body_points"),
                "stat_highlights": slide.get("stat_highlights"),
                "claim_evidence_pairs": slide.get("claim_evidence_pairs"),
                "visual_focus": slide.get("visual_focus"),
                "transition_note": slide.get("transition_note"),
                **slide_metadata,
            },
        )
        visual_plan = visual_explanation_plan or AIOrchestratorService._visual_explanation_plan(
            request,
            slide_text_payload,
            creative_decision,
            reference_images,
            message_strategy,
        )
        grounding_sections = AIOrchestratorService._final_render_grounding_sections(
            request=request,
            creative_decision=creative_decision,
            text_payload=slide_text_payload,
            compiled_context=compiled_context,
            reference_assets=reference_images,
        )
        research_quality_section = AIOrchestratorService._research_editorial_prompt_section(
            request,
            compiled_context,
        )
        consultant_contract = AIOrchestratorService._consultant_quality_contract(
            for_visual_only=False,
            for_carousel=True,
        )
        multimodal_balance_contract = AIOrchestratorService._multimodal_balance_contract(
            format_name="carousel",
            supporting_line=AIOrchestratorService._normalize_metadata_text(slide.get("supporting_line"), limit=220),
            proof_points=AIOrchestratorService._normalize_metadata_list(slide.get("proof_points"), limit=3),
            claim_evidence_pairs=AIOrchestratorService._normalize_claim_evidence_pairs(slide.get("claim_evidence_pairs"), limit=2),
            for_visual_only=False,
        )
        reference_family_contract = AIOrchestratorService._reference_family_contract_sections(
            compiled_context,
            slide=slide,
            for_visual_only=False,
        )
        sample_alignment_sections = AIOrchestratorService._sample_visual_alignment_sections(
            compiled_context,
            for_carousel=True,
        )
        sequence_alignment_sections = AIOrchestratorService._sequence_blueprint_alignment_sections(
            compiled_context,
            slide=slide,
            for_carousel=True,
            for_visual_only=False,
        )
        visual_plan_guidance = AIOrchestratorService._visual_explanation_guidance(visual_plan)
        disclaimer_overlay_guidance = AIOrchestratorService._disclaimer_overlay_guidance(request)
        legal_footer_text = AIOrchestratorService._scene_graph_legal_footer_text(scene_graph)
        palette_execution_contract = AIOrchestratorService._palette_role_execution_contract(
            visual_identity,
            has_cta=bool(AIOrchestratorService._normalize_metadata_text(slide.get("cta"), limit=80)),
            has_legal_footer=bool(legal_footer_text),
        )
        story_role_visual_execution = AIOrchestratorService._story_role_visual_execution_guidance(
            story_role,
            has_cta=bool(AIOrchestratorService._normalize_metadata_text(slide.get("cta"), limit=80)),
        )
        direct_text_contract = AIOrchestratorService._final_text_render_contract(
            headline=slide.get("headline"),
            supporting_line=slide.get("supporting_line"),
            body=AIOrchestratorService._carousel_slide_body_text(slide, fallback_text=""),
            proof_points=slide.get("proof_points") or slide.get("body_points") or slide.get("stat_highlights"),
            claim_evidence_pairs=slide.get("claim_evidence_pairs"),
            cta=slide.get("cta"),
            slide_role=story_role or slide.get("role"),
            legal_footer=legal_footer_text,
        )
        factual_visual_anchors = AIOrchestratorService._dedupe_metadata_collection(
            [
                *AIOrchestratorService._normalize_metadata_list(slide.get("stat_highlights"), limit=3),
                *AIOrchestratorService._claim_evidence_pair_lines(
                    AIOrchestratorService._normalize_claim_evidence_pairs(slide.get("claim_evidence_pairs"), limit=2),
                    limit=2,
                ),
                *AIOrchestratorService._normalize_metadata_list(slide.get("proof_points"), limit=3),
                *AIOrchestratorService._normalize_metadata_list(slide.get("body_points"), limit=2),
            ],
            blocked_texts=[
                slide.get("headline"),
                slide.get("supporting_line"),
                slide.get("cta"),
            ],
            limit=4,
        )
        reference_template_name = AIOrchestratorService._normalize_metadata_text(
            slide_metadata.get("reference_template_name"),
            limit=96,
        )
        reference_slide_index = int(slide_metadata.get("reference_slide_index") or slide_index)
        reference_slide_count = int(slide_metadata.get("reference_slide_count") or slide_count)
        reference_image_guidance = (
            "Sequence guidance available for spacing and hierarchy only; do not reproduce or trace the uploaded sample slide artwork."
            if template_surface_policy == "style_reference_only"
            else f"Reference images available for composition: {reference_summary}."
        )
        reference_anchor_guidance = (
            (
                f"Primary layout anchor for this slide: uploaded reference '{reference_template_name}' "
                f"(reference slide {reference_slide_index} of {reference_slide_count})."
            )
            if reference_template_name and template_surface_policy != "style_reference_only"
            else (
                f"Preserve the narrative position of slide {reference_slide_index} of {reference_slide_count}, "
                "but reinterpret the visual from scratch instead of reusing the uploaded sample slide surface."
                if template_surface_policy == "style_reference_only"
                else ""
            )
        )
        sections = [
            f"Create the finished visual for slide {slide_index} of {slide_count} in one cohesive premium branded carousel series.",
            f"Brand context only: {brand_name}. Use this for palette, tone, and approved copy context only, never as a logo, masthead, signature, watermark, or standalone brand mark.",
            f"LOGO RULE — no exceptions: the AI base creative must contain zero logos, wordmarks, brand-name signatures, monograms, watermarks, logo-like shapes, or brand marks anywhere in the slide image. Do not render, invent, stylize, or hint at any logo, initials, or brand identity element. The exact stored brand logo is applied as a separate asset after generation.",
            f"The {reserved_logo_area} area is strictly reserved for the brand logo. Do not place any headline, body copy, supporting text, proof point, CTA, icon, or visual element inside or immediately adjacent to this corner.",
            logo_safe_zone_guidance,
            logo_surface_guidance,
            disclaimer_overlay_guidance,
            f"Platform: {platform}.",
            f"Output type: {file_type}.",
            canvas_fit_guidance,
            f"Creative mode: {creative_decision.layout_mode}.",
            (
                (
                    f"Reference-zone geometry contract JSON: {geometry_contract}. Treat these regions as the authoritative slide skeleton. Preserve region proportions, spacing rhythm, and negative space closely; only make tiny readability adjustments and never recompose the slide from scratch."
                    if has_reference_zone_map
                    else f"Scene-graph geometry contract JSON: {geometry_contract}. Preserve these normalized regions closely; only make tiny adjustments for readability and never recompose the slide from scratch."
                )
                if geometry_contract
                else ""
            ),
            reference_zone_guidance,
            (
                f"Template/layout DNA contract JSON: {layout_dna_contract}. Use this as the authoritative slide skeleton for region balance, hierarchy, and spacing."
                if layout_dna_contract
                else ""
            ),
            "Respect the reference/template layout strictly: preserve the contracted regions, spacing rhythm, text-safe negative space, and image-zone discipline before adding decorative detail.",
            f"Slide role: {slide.get('role')}.",
            f"Story role: {story_role}.",
            (f"Carousel archetype: {carousel_archetype}." if carousel_archetype else ""),
            AIOrchestratorService._carousel_story_role_guidance(story_role),
            "Carousel visual-diversity contract: do not reuse the same hero subject, gesture, icon, chart, document, flag, or stock business motif across slides. Make this slide's image metaphor unique to its story role while keeping the series visually consistent.",
            "Role-based visual language: hook slides may use a broad conceptual anchor; structure slides should show mechanism/process; undercovered-angle slides should show evidence, documents, or hidden-layer metaphors; strategic-meaning slides should show network/map/outcome systems; closing slides should show an action/product/context surface.",
            f"Campaign theme: {message_theme}.",
            f"Emotional direction: {emotional_direction}.",
            *direct_text_contract,
            (
                f"This slide needs {len(AIOrchestratorService._normalize_metadata_list(slide.get('proof_points'), limit=3))} proof/callout module(s); render only the approved proof copy and keep those modules concise, legible, and spatially distinct."
                if AIOrchestratorService._normalize_metadata_list(slide.get("proof_points"), limit=3)
                else "Do not repeat the factual bullet list on this slide unless the story role explicitly requires it."
            ),
            (
                "If claim-evidence anchors are present, show only the approved claim/evidence copy in concise readable callouts and do not fabricate extra stats or labels."
                if AIOrchestratorService._normalize_claim_evidence_pairs(slide.get("claim_evidence_pairs"), limit=2)
                else ""
            ),
            (
                "Visual evidence contract: make the image system explain these approved specifics rather than falling back to generic treaty symbolism: "
                + "; ".join(f'"{item}"' for item in factual_visual_anchors)
                + "."
                if factual_visual_anchors
                else ""
            ),
            (
                "If this slide includes a CTA, render only the approved CTA text in the reserved CTA region and keep the treatment premium and restrained."
                if AIOrchestratorService._normalize_metadata_text(slide.get("cta"), limit=80)
                else (
                    "Do not add a CTA button on this slide; preserve only a thin quiet legal-footer-safe strip at the bottom."
                    if legal_footer_text
                    else "Do not add a CTA button or footer treatment on this slide."
                )
            ),
            research_quality_section,
            *consultant_contract,
            *multimodal_balance_contract,
            *reference_family_contract,
            *sequence_alignment_sections,
            *sample_alignment_sections,
            (
                f"Visual focus for this slide: {AIOrchestratorService._normalize_metadata_text(slide.get('visual_focus'), limit=420)}."
                if AIOrchestratorService._normalize_metadata_text(slide.get("visual_focus"), limit=420)
                else ""
            ),
            story_role_visual_execution,
            (
                f"Transition note from the sequence: {AIOrchestratorService._normalize_metadata_text(slide.get('transition_note'), limit=160)}."
                if AIOrchestratorService._normalize_metadata_text(slide.get("transition_note"), limit=160)
                else ""
            ),
            f"Brand palette to honor: {palette}.",
            f"Palette role guidance: {palette_guidance}.",
            strict_palette_contract,
            palette_execution_contract,
            f"Typography direction: {typography}.",
            f"Brand design-system layout guidance: {design_system_guidance.get('layout')}." if design_system_guidance.get("layout") else "",
            f"Preferred zone roles from the brand system: {design_system_guidance.get('zones')}." if design_system_guidance.get("zones") else "",
            f"Background style guidance from the brand system: {design_system_guidance.get('background')}." if design_system_guidance.get("background") else "",
            f"Motif guidance from the brand system: {design_system_guidance.get('motifs')}." if design_system_guidance.get("motifs") else "",
            f"Hierarchy guidance from the brand system: {design_system_guidance.get('hierarchy')}." if design_system_guidance.get("hierarchy") else "",
            f"Content-structure guidance from the brand system: {design_system_guidance.get('content_structure')}." if design_system_guidance.get("content_structure") else "",
            f"Image-treatment guidance from the brand system: {design_system_guidance.get('image_treatment')}." if design_system_guidance.get("image_treatment") else "",
            f"Visual-craft guidance from the brand system: {design_system_guidance.get('visual_craft')}." if design_system_guidance.get("visual_craft") else "",
            f"Composition guidance from the brand system: {design_system_guidance.get('composition')}." if design_system_guidance.get("composition") else "",
            f"Subject guidance from the brand system: {design_system_guidance.get('subjects')}." if design_system_guidance.get("subjects") else "",
            f"Editorial rhythm guidance from the brand system: {design_system_guidance.get('editorial')}." if design_system_guidance.get("editorial") else "",
            f"Brand-cue guidance from the brand system: {design_system_guidance.get('brand_cues')}." if design_system_guidance.get("brand_cues") else "",
            *grounding_sections,
            reference_image_guidance,
            reference_anchor_guidance,
            "Current slide subject matter overrides reference subject matter: preserve only approved palette, spacing, layout rhythm, and visual craft from references; never import unrelated objects, industries, products, or scenes from a template.",
            (
                "Use the reference slide zone-map as the authoritative per-slide geometry skeleton. Keep the headline, support copy, image region, CTA region, and legal strip in the same proportional neighborhoods instead of collapsing them into a single full-canvas content block."
                if geometry_contract
                else ""
            ),
            "Keep this slide visually consistent with the rest of the carousel series in palette, mood, and hierarchy.",
            "Use one clean composition with slide-safe spacing, strong focal emphasis, and clean future-copy integration.",
            "Do not crop or crowd any reserved text, CTA, logo, or legal-safe region. If space is tight, simplify the visual substrate instead of pushing zones to the edge.",
            "All reserved slide text and CTA surfaces must remain fully inside the export frame; do not let bottom shells, cards, dividers, or image subjects touch or cross the crop boundary.",
            "Make the slide visual communicate the exact approved idea from this slide's copy intent and user prompt, with the actual approved words rendered cleanly inside the layout.",
            visual_plan_guidance,
            "Prefer content-specific explanatory imagery, comparison cues, process metaphors, product-context objects, or restrained data/diagram anchors over a generic business person.",
            "Use people only when their action or setting directly explains the slide message; do not default to a standalone portrait for investor confidence or expertise themes.",
            "Avoid defaulting to generic handshake, flag-only, treaty-signing, or stock business celebration visuals unless the approved slide copy explicitly centers bilateral symbolism or ceremony.",
            (
                "If the brand design system implies airy hierarchy or generous whitespace, keep the slide cleaner and preserve negative space instead of overfilling every region."
                if "airy" in str(design_system_guidance.get("hierarchy") or "").casefold() or "generous" in str(design_system_guidance.get("hierarchy") or "").casefold()
                else ""
            ),
            (
                "If the brand design system implies comparison, steps, or data-story structure, let this slide use modular explainer composition rather than a plain poster block."
                if any(token in str(design_system_guidance.get("content_structure") or "").casefold() for token in ("comparison", "data", "benefit", "steps"))
                else ""
            ),
            (
                "Bias away from generic business-person imagery when the brand design system points toward diagram-led, icon-led, editorial, or abstract treatment."
                if any(token in str(design_system_guidance.get("image_treatment") or "").casefold() for token in ("diagram", "icon", "editorial", "abstract", "illustration"))
                else ""
            ),
            "Respect the reference/template layout for this slide strictly by keeping visual emphasis inside the intended image region, preserving text-safe negative space, and maintaining the sample's composition skeleton.",
            (
                "Do not recreate the uploaded sample slide's literal illustration, text, or surface details. "
                "Do preserve its region proportions, spacing rhythm, balance, and sequencing cues as closely as possible."
                if template_surface_policy == "style_reference_only"
                else ""
            ),
            "Do not render fake UI chrome, logos, or unrelated charts unless they are directly implied by the supplied text.",
            AIOrchestratorService._normalize_metadata_text(retry_note, limit=220),
        ]
        optional_prefixes = (
            "Brand design-system layout guidance:",
            "Preferred zone roles from the brand system:",
            "Background style guidance from the brand system:",
            "Motif guidance from the brand system:",
            "Hierarchy guidance from the brand system:",
            "Content-structure guidance from the brand system:",
            "Image-treatment guidance from the brand system:",
            "Visual-craft guidance from the brand system:",
            "Composition guidance from the brand system:",
            "Subject guidance from the brand system:",
            "Editorial rhythm guidance from the brand system:",
            "Brand-cue guidance from the brand system:",
            "If the brand design system implies airy hierarchy",
            "If the brand design system implies comparison",
            "Bias away from generic business-person imagery",
            "Reference family contract:",
            "Reference family layout lock:",
            "Reference family zone grammar:",
            "Reference family module grammar:",
            "Reference family density target:",
            "Image/text balance target:",
            "Reference family spacing rhythm:",
            "Reference family composition target:",
            "Reference family craft target:",
            "Reference family subject target:",
        )
        required_sections: list[str] = []
        optional_sections: list[str] = []
        for section in sections:
            cleaned = str(section or "").strip()
            if not cleaned or cleaned.endswith(": ."):
                continue
            target = optional_sections if cleaned.startswith(optional_prefixes) else required_sections
            target.append(cleaned)
        return AIOrchestratorService._compose_prompt_sections(
            required_sections=required_sections,
            optional_sections=optional_sections,
            limit=AIOrchestratorService.IMAGE_PROMPT_MAX_LENGTH,
        )

    @staticmethod
    def build_logo_composite_prompt(
        request: AIOrchestrationRequest,
        text_payload: StructuredTextPayload,
        scene_graph: GenerationSceneGraph,
        selected_logo_variant: str | None = None,
    ) -> str:
        platform = str(request.studio_panel.get("platform_preset") or "social")
        format_name = str(request.studio_panel.get("format") or "static")
        headline = AIOrchestratorService._normalize_metadata_text(text_payload.headline, limit=140)
        supporting_line = AIOrchestratorService._normalize_metadata_text(
            (text_payload.metadata or {}).get("supporting_line") or text_payload.body,
            limit=180,
        )
        variant_guidance = (
            f"Use the logo variant best matching this request: {selected_logo_variant}."
            if selected_logo_variant
            else ""
        )
        return AIOrchestratorService._trim_prompt(
            " ".join(
                [
                    "Edit the first input image by compositing the exact logo from the second input image into the masked region only.",
                    f"Platform: {platform}.",
                    f"Format: {format_name}.",
                    f"Headline context: {headline}.",
                    f"Supporting copy context: {supporting_line}.",
                    variant_guidance,
                    "Use the second image exactly as the brand logo reference.",
                    "Preserve the logo wording, colors, shape, and aspect ratio with high fidelity.",
                    "Place the logo cleanly inside the masked area with professional spacing and no distortion.",
                    "Do not change any other part of the base creative outside the masked region.",
                    "Do not invent a new logo, do not stylize the logo, and do not add any extra text.",
                ]
            ),
            AIOrchestratorService.IMAGE_PROMPT_MAX_LENGTH,
        )

    @staticmethod
    def build_image_prompt(
        request: AIOrchestrationRequest,
        text_payload: StructuredTextPayload,
        creative_decision: CreativeDecisionPayload | None = None,
        message_strategy: MessageStrategyPayload | None = None,
        compiled_context: dict[str, Any] | None = None,
        visual_explanation_plan: dict[str, Any] | None = None,
    ) -> str:
        compiled_context = compiled_context or {}
        creative_decision = creative_decision or CreativeDecisionPayload()
        metadata, sanitized_visual_fields = AIOrchestratorService._sanitize_visual_metadata_fields(
            text_payload.metadata or {},
            compiled_context=compiled_context,
        )
        visual_identity = request.resolved_brand_context.get("visual_identity", {})
        palette = AIOrchestratorService._compact_palette_summary(visual_identity)
        palette_guidance = AIOrchestratorService._palette_role_guidance(visual_identity)
        strict_palette_contract = AIOrchestratorService._strict_palette_contract(visual_identity)
        typography = AIOrchestratorService._compact_typography_summary(visual_identity)
        asset_strategy = (creative_decision.asset_strategy if creative_decision else {}) or {}
        template_surface_policy = str(asset_strategy.get("template_surface_policy") or "").strip().lower()
        dominant_visual_system = AIOrchestratorService._normalized_dominant_visual_system(asset_strategy) or "generated_image"
        supporting_visual_system = AIOrchestratorService._normalized_supporting_visual_system(asset_strategy)
        format_name = str(request.studio_panel.get("format") or "static").strip().lower()
        explicit_data_visual_request = AIOrchestratorService._has_explicit_data_visual_request(
            request.prompt,
            text_payload=text_payload,
        )
        iconography_supported = (
            format_name in {"carousel", "infographic"}
            or supporting_visual_system == "icon_sequence"
            or bool(asset_strategy.get("icon_sequence"))
        )
        include_reference_system = (
            dominant_visual_system in {"reference_assets", "icon_sequence"}
            or supporting_visual_system in {"reference_assets", "icon_sequence"}
            or (iconography_supported and bool(asset_strategy.get("use_brand_reference_assets")))
        )
        reusable_assets = (
            AIOrchestratorService._compact_named_items(
                visual_identity.get("reusable_design_assets"),
                limit=4,
            )
            if include_reference_system
            else "Do not directly embed brand icon sets or decorative assets into the generated image."
        )
        proof_points = AIOrchestratorService._compact_named_items(metadata.get("proof_points"), limit=4)
        stat_highlights = AIOrchestratorService._compact_named_items(metadata.get("stat_highlights"), limit=3)
        reference_assets = (
            "Sequence-approved style guidance only; do not recreate, trace, or literalize uploaded sample slides."
            if template_surface_policy == "style_reference_only"
            else (
                AIOrchestratorService._compact_reference_assets(request.reference_assets)
                if include_reference_system
                else "Use these only as abstract style guidance, not as literal icon or logo content."
            )
        )
        layout_decision = AIOrchestratorService._compact_layout_decision(request.layout_decision)
        if template_surface_policy == "style_reference_only" and "template " in layout_decision.casefold():
            layout_decision = (
                "adapted sequence-guided composition using approved spacing, hierarchy, and zones only; "
                "do not reproduce the uploaded sample artwork"
            )
        design_style = AIOrchestratorService._normalize_metadata_text(metadata.get("design_style"), limit=80)
        visual_direction = AIOrchestratorService._normalize_metadata_text(metadata.get("visual_direction"), limit=180)
        preferred_scene = AIOrchestratorService._normalize_metadata_text(metadata.get("image_prompt"), limit=220)
        visual_knowledge_brief = ContextCompilerService.coerce_visual_knowledge_brief(
            compiled_context.get("visual_knowledge_brief"),
        )
        direct_brand_grounding = AIOrchestratorService._brand_knowledge_visual_grounding(
            visual_knowledge_brief,
        )
        grounding_mode = AIOrchestratorService._normalize_metadata_text(
            visual_knowledge_brief.get("grounding_mode"),
            limit=32,
        )
        grounding_strength = AIOrchestratorService._normalize_metadata_text(
            visual_knowledge_brief.get("grounding_strength"),
            limit=32,
        )
        grounding_abstention_reason = AIOrchestratorService._normalize_metadata_text(
            visual_knowledge_brief.get("abstention_reason"),
            limit=64,
        )
        template_suppressed = bool(visual_knowledge_brief.get("template_suppressed"))
        use_llm_fallback_visual_metadata = grounding_mode == "llm_fallback" or not direct_brand_grounding
        secondary_visual_hints = " | ".join(
            part
            for part in [
                f"visual direction={visual_direction}" if visual_direction else "",
                f"design style={design_style}" if design_style else "",
                f"preferred scene={preferred_scene}" if preferred_scene else "",
            ]
            if part
        )
        strategy_payload = message_strategy.model_dump(mode="json") if isinstance(message_strategy, MessageStrategyPayload) else {}
        message_theme = AIOrchestratorService._normalize_metadata_text(strategy_payload.get("primary_campaign_theme"), limit=180)
        audience_message = AIOrchestratorService._normalize_metadata_text(strategy_payload.get("core_audience_message"), limit=220)
        emotional_direction = AIOrchestratorService._normalize_metadata_text(strategy_payload.get("emotional_messaging_direction"), limit=120)
        keywords = ", ".join(strategy_payload.get("important_keywords") or []) or "None"
        avoid_list = ", ".join(strategy_payload.get("what_must_be_avoided_in_messaging") or []) or "None"
        stripped_prompt_theme = AIOrchestratorService._normalize_metadata_text(
            re.sub(
                r"^(create|make|design|generate|write|craft)\s+(an?|the)?\s*(engaging|compelling|instagram|social|media|post|creative|visual)*\s*",
                "",
                request.prompt,
                flags=re.IGNORECASE,
            ).strip()
            or request.prompt,
            limit=220,
        )
        resolved_copy_theme = AIOrchestratorService._normalize_metadata_text(
            " ".join(
                part
                for part in [
                    text_payload.headline,
                    metadata.get("supporting_line") or "",
                    text_payload.body,
                ]
                if AIOrchestratorService._coerce_text_value(part).strip()
            ),
            limit=220,
        )
        semantic_visual_brief = AIOrchestratorService._normalize_metadata_text(
            " ".join(
                part
                for part in [
                    stripped_prompt_theme,
                    text_payload.headline,
                    metadata.get("supporting_line") or "",
                    text_payload.body,
                    proof_points if proof_points != "None" else "",
                    stat_highlights if stat_highlights != "None" else "",
                ]
                if AIOrchestratorService._coerce_text_value(part).strip()
            ),
            limit=340,
        )
        stripped_prompt_keywords = AIOrchestratorService._topic_anchor_keywords(stripped_prompt_theme)
        resolved_copy_keywords = AIOrchestratorService._topic_anchor_keywords(resolved_copy_theme)
        theme_anchor = (
            stripped_prompt_theme
            if stripped_prompt_keywords and resolved_copy_keywords and stripped_prompt_keywords & resolved_copy_keywords
            else (message_theme or resolved_copy_theme or stripped_prompt_theme)
        )
        logo_position_hint = AIOrchestratorService._effective_logo_position_hint(
            request=request,
            creative_decision=creative_decision,
            text_payload=AIOrchestratorService._text_payload_prompt_dict(text_payload),
        )
        logo_safe_zone_guidance = AIOrchestratorService._logo_safe_zone_guidance(
            request,
            hint=logo_position_hint,
        )
        reserved_logo_area = AIOrchestratorService._logo_reserved_area_label(logo_position_hint)
        logo_surface_guidance = AIOrchestratorService._logo_surface_guidance(
            background_tone=AIOrchestratorService._resolve_logo_background_tone(
                metadata=metadata,
                creative_decision=creative_decision,
            )
        )
        visual_plan = visual_explanation_plan or AIOrchestratorService._visual_explanation_plan(
            request,
            text_payload,
            creative_decision,
            request.reference_assets,
            message_strategy,
        )
        research_quality_section = AIOrchestratorService._research_editorial_prompt_section(
            request,
            compiled_context,
        )
        consultant_contract = AIOrchestratorService._consultant_quality_contract(
            for_visual_only=True,
            for_carousel=format_name == "carousel",
        )
        multimodal_balance_contract = AIOrchestratorService._multimodal_balance_contract(
            format_name=format_name,
            supporting_line=AIOrchestratorService._normalize_metadata_text(metadata.get("supporting_line") or text_payload.body, limit=220),
            proof_points=AIOrchestratorService._normalize_metadata_list(metadata.get("proof_points"), limit=4),
            claim_evidence_pairs=AIOrchestratorService._normalize_claim_evidence_pairs(metadata.get("claim_evidence_pairs"), limit=3),
            for_visual_only=True,
        )
        reference_family_contract = AIOrchestratorService._reference_family_contract_sections(
            compiled_context,
            for_visual_only=True,
        )
        visual_plan_guidance = AIOrchestratorService._visual_explanation_guidance(visual_plan)
        sample_alignment_sections = AIOrchestratorService._sample_visual_alignment_sections(
            compiled_context,
            for_carousel=format_name == "carousel",
        )
        sequence_alignment_sections = AIOrchestratorService._sequence_blueprint_alignment_sections(
            compiled_context,
            for_carousel=format_name == "carousel",
            for_visual_only=True,
        )

        sections = [
            "Create a clean supporting visual aligned to the brand system.",
            f"LOGO RULE — no exceptions: do not render, invent, stylize, or hint at any logo, wordmark, monogram, brand mark, initials, or branded signature anywhere in the generated image. The exact stored brand logo is applied as a separate overlay after generation — never recreate it.",
            f"The {reserved_logo_area} area is strictly reserved for the brand logo. Do not place any icon, illustration element, text, or visual detail inside or immediately adjacent to this corner.",
            logo_safe_zone_guidance,
            logo_surface_guidance,
            f"Theme: {theme_anchor}.",
            f"Message strategy theme: {message_theme}.",
            f"Core audience message: {audience_message}.",
            f"Emotional direction: {emotional_direction}.",
            f"Important keywords: {keywords}.",
            f"Avoid these messaging cues in the visual: {avoid_list}.",
            f"Platform: {request.studio_panel.get('platform_preset', 'social')}.",
            f"Format: {request.studio_panel.get('format', 'static')}.",
            f"Headline intent: {AIOrchestratorService._normalize_metadata_text(text_payload.headline, limit=160)}.",
            f"Body summary: {AIOrchestratorService._normalize_metadata_text(text_payload.body, limit=260)}.",
            f"Semantic visual brief: communicate this exact idea visually, without relying on text: {semantic_visual_brief}.",
            (
                f"Brand knowledge grounding mode: {grounding_mode or 'brand_knowledge'} (strength: {grounding_strength or 'supported'})."
                if direct_brand_grounding
                else (
                    f"Brand knowledge grounding mode: llm_fallback (reason: {grounding_abstention_reason})."
                    if grounding_abstention_reason
                    else "Brand knowledge grounding mode: llm_fallback."
                )
            ),
            (
                f"Brand knowledge grounding: {direct_brand_grounding}. Use these retrieved brand-knowledge cues as the primary source of visual grounding."
                if direct_brand_grounding
                else "Brand knowledge grounding: no retrieved brand knowledge is available, so infer the visual grounding from the approved copy, message strategy, and brand visual system."
            ),
            (
                "If retrieved brand knowledge is present, do not override it with a generic LLM-invented scene. Use LLM reasoning only to interpret and combine the retrieved cues coherently."
                if direct_brand_grounding
                else "Because retrieved brand knowledge is absent, generate the visual direction through LLM reasoning from the approved copy, message strategy, and brand visual system."
            ),
            (
                "Template-derived cues were suppressed because stronger visual_identity or mood_board evidence exists."
                if direct_brand_grounding and template_suppressed
                else ""
            ),
            (
                "If the active brand grounding is fallback-only, use template or metadata cues only for structure, palette, spacing, and composition. Do not literalize template copy."
                if direct_brand_grounding and grounding_strength == "fallback_only"
                else ""
            ),
            (
                "When sequence guidance is style-reference-only, treat uploaded sample slides as strict composition and craft references. "
                "Preserve their region proportions, negative space, sequencing, balance, and composition rhythm closely, but rebuild the artwork, poster surface, text blocks, background illustration, and sample typography from scratch."
                if template_surface_policy == "style_reference_only"
                else ""
            ),
            (
                f"LLM fallback visual direction: {visual_direction}."
                if use_llm_fallback_visual_metadata and visual_direction
                else ""
            ),
            (
                f"LLM fallback design style: {design_style}."
                if use_llm_fallback_visual_metadata and design_style
                else ""
            ),
            (
                f"LLM fallback preferred scene: {preferred_scene}."
                if use_llm_fallback_visual_metadata and preferred_scene
                else ""
            ),
            (
                f"Secondary synthesis hints from approved metadata: {secondary_visual_hints}. "
                "Use these only if they reinforce the retrieved brand-grounded cues and never let them override or "
                "reintroduce suppressed template or rejected channel ideas."
                if not use_llm_fallback_visual_metadata and secondary_visual_hints
                else ""
            ),
            (
                f"Discarded incompatible model-generated visual metadata for: {', '.join(sanitized_visual_fields)}."
                if sanitized_visual_fields
                else ""
            ),
            f"Brand palette: {palette}.",
            f"Palette role guidance: {palette_guidance}.",
            strict_palette_contract,
            f"Typography vibe: {typography}.",
            f"Layout approach: {layout_decision}.",
            f"Dominant visual system: {dominant_visual_system}.",
            f"Supporting visual system: {supporting_visual_system or 'none'}.",
            f"Key proof points: {proof_points}.",
            f"Stat highlights: {stat_highlights}.",
            f"Reusable decorative cues: {reusable_assets}.",
            f"Reference assets: {reference_assets}.",
            *sample_alignment_sections,
            *sequence_alignment_sections,
            research_quality_section,
            *consultant_contract,
            *multimodal_balance_contract,
            *reference_family_contract,
            (
                "Visual quality bar: premium, high-end, richly detailed, polished editorial campaign imagery with depth, "
                "controlled lighting, elegant negative space, and brand-safe color accents."
            ),
            "Choose background tones from true background or surface palette evidence rather than overpowering the canvas with a strong secondary brand color.",
            "Maintain clear contrast between any light surfaces and darker emphasis colors so later text placement stays readable and never fades into a white or dull field.",
            (
                "Prefer one coherent content-led hero concept: a product or process metaphor, comparison setup, outcome-focused object composition, "
                "or structured explainer centerpiece tied directly to the semantic visual brief. Do not default to a standalone professional portrait or generic lifestyle scene."
            ),
            visual_plan_guidance,
            (
                "If the requested format is carousel or infographic, build a richer explainer composition with a clear focal subject and only the minimum supporting structure truly required by the content. Do not default to rising bars, upward arrows, dashboard tiles, symbolic finance stickers, or a chart/graph hero unless the user explicitly asked for chart or diagram content."
                if iconography_supported
                else "Keep the composition focused on one premium content-specific scene rather than many small supporting motifs."
            ),
            (
                "Reserve calm negative space where headline and CTA can sit cleanly after rendering. "
                "Respect the selected reference/template layout by composing the focal visual for the reserved image area. Do not compose the image like a finished poster."
            ),
            (
                "Avoid clip-art, flat stock-style icon grids, low-detail collage aesthetics, childish illustration, "
                "or generic corporate poster art."
            ),
            (
                "If reusable icons or diagram cues are available, you may integrate a small number of them as premium, brand-consistent supporting elements rather than ignoring them completely."
                if include_reference_system and iconography_supported
                else "Do not directly embed brand icon sets or decorative assets into the generated image."
            ),
            (
                "Do not include any text, typography, letters, numbers, logos, CTA buttons, UI panels, "
                "poster layouts, or branded wordmarks in the image. "
                "Generate only a clean visual, illustration, texture, or scene that the backend renderer can place into the layout."
            ),
            (
                "Do not paint random sticker-like icons, fake logos, faux UI panels, or cluttered symbol dumps. Any infographic or iconographic support must feel intentional, premium, and integrated into the overall composition."
                if iconography_supported
                else "Do not paint standalone icons, infographic symbols, tables, badges, checkmarks, or faux UI graphics onto the scene unless they exist as real-world objects inside the photographed environment."
            ),
            (
                "If the prompt is about tips, strategies, comparisons, or financial education, keep the scene topic-led and avoid auto-inserting symbolic growth charts, rising bars, arrows, finance app mini-graphics, or a graph-like hero composition. Only add chart or diagram elements when the user explicitly requested them."
                if iconography_supported
                else "If the prompt is about tips, strategies, or comparisons, still create one premium unified hero scene rather than a collage of icon stickers."
            ),
            (
                "Do not add bar-chart icons, rising-arrow symbols, dashboard tiles, comparison stickers, decorative finance mini-graphics, or a chart/graph/bar-and-arrow hero image unless the user explicitly asked for a chart, graph, table, timeline, diagram, or infographic data visualization."
                if not explicit_data_visual_request
                else "If a chart or diagram is explicitly requested, keep it literal, sparse, and directly tied to the supplied data instead of using generic symbolic finance icons."
            ),
        ]
        prompt = " ".join(section for section in sections if section and not section.endswith(": ."))
        return AIOrchestratorService._trim_prompt(prompt, AIOrchestratorService.IMAGE_PROMPT_MAX_LENGTH)

    @staticmethod
    def _compact_named_items(value: Any, limit: int) -> str:
        items = AIOrchestratorService._normalize_metadata_list(value, limit=limit)
        return ", ".join(items) if items else "None"

    @staticmethod
    def _compact_palette_summary(visual_identity: Any) -> str:
        if not isinstance(visual_identity, dict):
            return "Use the validated primary and secondary brand colors."
        resolved_roles = derive_palette_roles(visual_identity)
        if resolved_roles:
            prioritized = [
                f"{role} {value}"
                for role in ("background", "primary", "secondary", "accent")
                if (value := resolved_roles.get(role))
            ]
            if prioritized:
                return ", ".join(prioritized[:5])
        palette_entries = visual_identity.get("brand_color_palette") or visual_identity.get("palette_entries") or []
        if isinstance(palette_entries, dict):
            colors = [
                f"{AIOrchestratorService._normalize_metadata_text(role, limit=18)} {AIOrchestratorService._normalize_metadata_text(value, limit=24)}".strip()
                for role, value in list(palette_entries.items())[:5]
                if AIOrchestratorService._normalize_metadata_text(value, limit=24)
            ]
            return ", ".join(colors) if colors else "Use the validated primary and secondary brand colors."
        if not isinstance(palette_entries, list):
            return "Use the validated primary and secondary brand colors."
        colors: list[str] = []
        for entry in palette_entries[:5]:
            if not isinstance(entry, dict):
                continue
            role = AIOrchestratorService._normalize_metadata_text(entry.get("role"), limit=18)
            code = AIOrchestratorService._normalize_metadata_text(
                entry.get("hex_code") or entry.get("hex") or entry.get("color_code") or entry.get("name"),
                limit=24,
            )
            label = " ".join(part for part in [role, code] if part)
            if label:
                colors.append(label)
        return ", ".join(colors) if colors else "Use the validated primary and secondary brand colors."

    @staticmethod
    def _palette_role_guidance(visual_identity: Any) -> str:
        if not isinstance(visual_identity, dict):
            return (
                "Use the brand background or surface color for the main canvas, keep primary and secondary colors for emphasis, "
                "and maintain strong readable contrast between text and background."
            )
        roles = derive_palette_roles(visual_identity)
        if not roles:
            return (
                "Use the brand background or surface color for the main canvas, keep primary and secondary colors for emphasis, "
                "and maintain strong readable contrast between text and background."
            )
        guidance: list[str] = []
        if roles.get("background") or roles.get("surface"):
            guidance.append(
                f"Base canvas should lean on {roles.get('background') or roles.get('surface')} rather than overpowering accent fills."
            )
        if roles.get("primary"):
            guidance.append(f"Use {roles['primary']} as the main emphasis color.")
        if roles.get("secondary"):
            guidance.append(
                f"Use {roles['secondary']} as a supporting color instead of making it the dominant full-background field unless the layout truly needs it."
            )
        if roles.get("accent"):
            guidance.append(f"Reserve {roles['accent']} for highlights, chart moments, or CTA emphasis.")
        guidance.append("Protect readability with high contrast and avoid white-on-white, pale-on-pale, or dull low-contrast text treatments.")
        return " ".join(guidance)

    @staticmethod
    def _strict_palette_contract(visual_identity: Any) -> str:
        if not isinstance(visual_identity, dict):
            return ""
        roles = derive_palette_roles(visual_identity)
        if not roles:
            return ""
        background = str(roles.get("background") or roles.get("surface") or "").strip()
        primary = str(roles.get("primary") or "").strip()
        secondary = str(roles.get("secondary") or "").strip()
        accent = str(roles.get("accent") or "").strip()
        contract: list[str] = [
            "Strict palette contract: stay inside the validated brand color system and do not introduce unrelated dominant hues."
        ]
        if background:
            contract.append(
                f"Let {background} act as the dominant background or surface tone for most of the canvas."
            )
        if primary:
            contract.append(
                f"Use {primary} as the principal brand emphasis color for major structure, strong contrast, and key framing."
            )
        if secondary:
            contract.append(
                f"Use {secondary} only as a controlled secondary accent or emphasis field, not as a full-canvas wash unless the composition truly demands it."
            )
        if accent:
            contract.append(
                f"Keep {accent} limited to small highlight moments, not broad background coverage."
            )
        contract.append(
            "Avoid drifting into generic blue-gray, random teal, muddy beige, purple, or off-brand pastel systems that are not validated by the brand palette."
        )
        return " ".join(contract)

    @staticmethod
    def _palette_role_execution_contract(visual_identity: Any, *, has_cta: bool, has_legal_footer: bool) -> str:
        if not isinstance(visual_identity, dict):
            return ""
        roles = derive_palette_roles(visual_identity)
        if not roles:
            return ""
        instructions: list[str] = []
        background = str(roles.get("background") or roles.get("surface") or "").strip()
        primary = str(roles.get("primary") or "").strip()
        secondary = str(roles.get("secondary") or "").strip()
        accent = str(roles.get("accent") or "").strip()
        if background:
            instructions.append(f"Canvas and quiet negative space should predominantly use {background}.")
        if primary:
            instructions.append(
                f"Headlines, core body text, key dividers, and the main explanatory structure should primarily use {primary} when strong contrast is needed."
            )
        if secondary:
            instructions.append(
                f"Use {secondary} only for secondary modules, supporting shapes, or restrained depth accents rather than the dominant reading layer."
            )
        if accent:
            accent_targets = ["small stat moments", "highlight chips", "one hero object accent"]
            if has_cta:
                accent_targets.append("the CTA treatment")
            instructions.append(
                f"Use {accent} selectively for " + ", ".join(accent_targets) + " instead of spreading it across the whole slide."
            )
        if has_legal_footer and primary:
            instructions.append(f"Keep the legal footer readable with a calm, low-noise strip and text that can sit cleanly in or near {primary}.")
        return " ".join(instructions)

    @staticmethod
    def _story_role_visual_execution_guidance(story_role: str, *, has_cta: bool = False) -> str:
        normalized = AIOrchestratorService._normalize_metadata_text(story_role, limit=48).casefold().replace(" ", "_")
        if normalized in {"hook", "cover", "opening", "title"}:
            return (
                "Execution guidance for this hook: use one bold focal metaphor with generous spread and clear negative space; let the image lead, not a stack of generic icon badges."
            )
        if normalized in {"structure", "deal_structure", "what_happened", "mechanics", "breakdown"}:
            return (
                "Execution guidance for this structure slide: use a mechanism-led composition such as segmented comparisons, process logic, layered explainer modules, or one strong analytical diagram anchored to the approved facts."
            )
        if normalized in {"undercovered_angle", "missed_angle", "angle"}:
            return (
                "Execution guidance for this undercovered-angle slide: use evidence-led objects, sector-specific symbols, hidden-layer reveals, document fragments, or magnified detail rather than a generic business scene."
            )
        if normalized in {"strategic_meaning", "implications", "implication", "analysis", "what_matters"}:
            return (
                "Execution guidance for this strategic-meaning slide: show systems, networks, balance, ripple effects, or outcome pathways so the visual explains second-order meaning rather than the headline event."
            )
        if normalized in {"takeaway", "close", "closing", "cta", "final"}:
            closing_tail = " and keep the CTA integrated but restrained." if has_cta else "."
            return (
                "Execution guidance for this closing slide: use an action-oriented product or decision-support surface, not a ceremonial or generic symbolic illustration"
                + closing_tail
            )
        return (
            "Execution guidance: choose a distinct explanatory composition that matches the approved slide role and advances the sequence instead of repeating the previous slide's visual grammar."
        )

    @staticmethod
    def _is_non_retryable_image_error(error: Exception) -> bool:
        text = str(error or "").strip().lower()
        return any(
            marker in text
            for marker in (
                "image_generation_user_error",
                "invalid_input_fidelity_model",
                "input_fidelity",
                "not supported for",
                "quality is not supported",
            )
        )

    @staticmethod
    def _compact_typography_summary(visual_identity: Any) -> str:
        if not isinstance(visual_identity, dict):
            return "Follow the validated brand typography."
        typography = visual_identity.get("typography") or visual_identity.get("typography_guide") or {}
        if isinstance(typography, dict):
            families = typography.get("font_families") or typography.get("font_family") or typography.get("families")
            hierarchy = typography.get("hierarchy") or typography.get("usage_patterns")
            family_text = AIOrchestratorService._compact_named_items(families, limit=3)
            hierarchy_text = AIOrchestratorService._compact_named_items(hierarchy, limit=3)
            if family_text != "None" or hierarchy_text != "None":
                return f"{family_text}; hierarchy: {hierarchy_text}"
        return "Follow the validated brand typography."

    @staticmethod
    def _compact_layout_decision(layout_decision: Any) -> str:
        if not isinstance(layout_decision, dict):
            return "Synthesized layout"
        mode = AIOrchestratorService._normalize_metadata_text(layout_decision.get("mode"), limit=32) or "Synthesized layout"
        template_name = AIOrchestratorService._normalize_metadata_text(
            layout_decision.get("template_name") or layout_decision.get("selected_template_name"),
            limit=80,
        )
        reasons = AIOrchestratorService._compact_named_items(layout_decision.get("reasons"), limit=2)
        parts = [mode]
        if template_name:
            parts.append(f"template {template_name}")
        if reasons != "None":
            parts.append(f"because {reasons}")
        return ", ".join(parts)

    @staticmethod
    def _compact_reference_assets(reference_assets: Any) -> str:
        if not isinstance(reference_assets, list):
            return "None"
        labels: list[str] = []
        for asset in reference_assets[:4]:
            if isinstance(asset, dict):
                label = AIOrchestratorService._reference_asset_display_label(asset)
                mime_type = AIOrchestratorService._normalize_metadata_text(asset.get("mime_type"), limit=32)
                if mime_type and mime_type not in label:
                    label = f"{label} ({mime_type})"
            else:
                label = asset
            normalized = AIOrchestratorService._normalize_metadata_text(label, limit=60)
            if normalized:
                labels.append(normalized)
        return ", ".join(labels) if labels else "None"

    @staticmethod
    def _brand_knowledge_visual_grounding(knowledge_brief: Any) -> str:
        brief = ContextCompilerService.coerce_visual_knowledge_brief(knowledge_brief)
        items = brief.get("items") if isinstance(brief.get("items"), list) else []
        grounded_items: list[str] = []
        for item in items[:4]:
            if not isinstance(item, dict):
                continue
            channel = AIOrchestratorService._normalize_metadata_text(item.get("channel"), limit=32).lower()
            content = AIOrchestratorService._normalize_metadata_text(item.get("content"), limit=180)
            if channel and content:
                grounded_items.append(f"{channel}: {content}")
        return " | ".join(grounded_items)

    @staticmethod
    def _trim_prompt(value: str, limit: int) -> str:
        text = " ".join(value.split())
        if len(text) <= limit:
            return text
        trimmed = text[: limit - 3].rstrip(" ,.;:")
        return f"{trimmed}..."

    @staticmethod
    def estimate_token_usage(input_segments: list[str], output_segments: list[str]) -> dict:
        input_tokens = sum(AIOrchestratorService._estimate_tokens(segment) for segment in input_segments)
        output_tokens = sum(AIOrchestratorService._estimate_tokens(segment) for segment in output_segments)
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "estimated": True,
        }

    @staticmethod
    def _estimate_tokens(value: str | None) -> int:
        if not value:
            return 0
        return max(1, (len(value.strip()) + 3) // 4)
