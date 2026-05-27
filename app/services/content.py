from __future__ import annotations

import asyncio
from copy import deepcopy
from io import BytesIO
import json
import logging
from pathlib import Path
import re
from typing import Any
from uuid import UUID, uuid4

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from docx import Document
from docx.shared import Inches
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.blueprint import BlueprintService
from app.ai.brand_intelligence import BrandIntelligenceService
from app.ai.contracts import (
    AIOrchestrationRequest,
    BlueprintPayload,
    CreativeDecisionPayload,
    GeneratedImageAsset,
    GenerationSceneGraph,
    MessageStrategyPayload,
    RendererInput,
    SceneGraphValidationReport,
    StructuredTextPayload,
)
from app.ai.layout_decision import LayoutDecisionEngine
from app.ai.orchestrator import AIOrchestratorService
from app.ai.session_memory import SessionMemoryPlanner
from app.ai.tone_intelligence import ToneIntelligenceService
from app.core.enums import AssetRole, BrandSpaceLifecycle
from app.core.enums import ContentLifecycle, KnowledgeChannel, UsageMetricCode
from app.core.exceptions import GenerationFailureError, LifecycleError, NotFoundError
from app.core.studio import resolve_studio_panel_defaults
from app.integrations.object_storage import LocalObjectStorage
from app.models.content import ContentSession, ContentVersion, GeneratedAsset
from app.repositories.brand import BrandSectionRepository, BrandSpaceRepository, ObjectiveRepository, PersonaRepository
from app.repositories.brand_assets import ReusableBrandAssetRepository
from app.repositories.content import AssetRepository, ChatMessageRepository, ContentRepository, SessionRepository
from app.repositories.knowledge import KnowledgeAssetRepository, TemplateMetadataRepository, TemplateRepository
from app.schemas.content import ContentGenerateRequest, ContentRewriteRequest, ToneCheckRequest
from app.services.artifact_state import ArtifactStateService
from app.services.asset_delivery import AssetDeliveryService
from app.services.content_planning import ContentPlanningService
from app.services.content_format_guide import ContentFormatGuideService
from app.services.knowledge import KnowledgeService
from app.services.data_validation import DataValidatorService
from app.services.format_family_planning import FormatFamilyPlanningService
from app.services.generation_trace import GenerationTraceService
from app.services.live_research import LiveResearchService
from app.services.renderer import RendererService
from app.services.research_editorial_planning import ResearchEditorialPlanningService
from app.services.template import TemplateService
from app.services.usage import UsageLimitService
from app.services.visual_planning import VisualPlanningService
from app.utils.input_access_tracking import InputAccessTracker
from app.utils.image_assets import open_image_asset
from app.utils.palette_roles import derive_palette_roles

logger = logging.getLogger(__name__)


class ContentService:
    AI_FINAL_RENDER_FORMATS = {"static", "story", "poster", "carousel", "infographic"}
    TOPIC_STOPWORDS = {
        "a",
        "an",
        "and",
        "campaign",
        "content",
        "create",
        "creative",
        "design",
        "engaging",
        "file",
        "for",
        "format",
        "generate",
        "goal",
        "image",
        "instagram",
        "layout",
        "media",
        "new",
        "panel",
        "platform",
        "png",
        "post",
        "prompt",
        "share",
        "shares",
        "social",
        "strategy",
        "strategies",
        "that",
        "the",
        "tip",
        "tips",
        "type",
        "using",
        "visual",
        "with",
    }
    GENERIC_REFERENCE_MARKERS = (
        "abstract",
        "asset",
        "background",
        "creative",
        "gradient",
        "hero",
        "img",
        "layout",
        "logo",
        "mood",
        "palette",
        "pattern",
        "reference",
        "shape",
        "style",
        "template",
        "texture",
    )
    REWRITE_REMOVAL_MARKERS = ("remove", "delete", "drop", "omit", "exclude", "strip", "without")
    REWRITE_REPLACEMENT_MARKERS = ("replace", "swap", "substitute", "instead of", "rather than")
    REWRITE_CORE_FIELDS = ("headline", "body", "cta")
    REWRITE_CONTEXT_STOPWORDS = {
        "audience",
        "better",
        "book",
        "body",
        "buyer",
        "buyers",
        "call",
        "content",
        "copy",
        "cta",
        "demo",
        "faster",
        "headline",
        "keep",
        "line",
        "make",
        "move",
        "offer",
        "rest",
        "rewrite",
        "same",
        "see",
        "sharper",
        "stronger",
        "tighter",
        "version",
        "workflow",
    }
    REWRITE_LOW_SIGNAL_MATCH_TOKENS = {
        "audience",
        "brand",
        "budget",
        "business",
        "buyer",
        "client",
        "company",
        "content",
        "customer",
        "finance",
        "leader",
        "market",
        "operation",
        "platform",
        "process",
        "product",
        "report",
        "reporting",
        "service",
        "solution",
        "team",
        "tool",
        "workflow",
    }
    REWRITE_FIELD_HINTS = {
        "headline": ("headline", "opening line"),
        "body": ("body", "body copy", "main copy"),
        "cta": ("cta", "call to action", "button text"),
        "proof_points": ("proof point", "proof points"),
        "stat_highlights": ("stat highlight", "stat highlights", "stats", "statistics"),
        "trust_builders": ("trust builder", "trust builders", "credibility cue", "credibility cues", "social proof"),
        "objection_handling": ("objection handling", "objection", "objections"),
        "claim_evidence_pairs": ("claim/evidence", "claim evidence", "claim evidence pair", "claim evidence pairs"),
        "hook_type": ("hook type", "hook", "opening angle"),
    }

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.sessions = SessionRepository(session)
        self.contents = ContentRepository(session)
        self.assets = AssetRepository(session)
        self.chat_messages = ChatMessageRepository(session)
        self.brands = BrandSpaceRepository(session)
        self.sections = BrandSectionRepository(session)
        self.personas = PersonaRepository(session)
        self.objectives = ObjectiveRepository(session)
        self.templates = TemplateRepository(session)
        self.template_metadata = TemplateMetadataRepository(session)
        self.knowledge_assets = KnowledgeAssetRepository(session)
        self.reusable_assets = ReusableBrandAssetRepository(session)
        self.knowledge = KnowledgeService(session)
        self.renderer = RendererService(session)
        self.orchestrator = AIOrchestratorService()
        self.tone = ToneIntelligenceService()
        self.usage = UsageLimitService(session)
        self.template_service = TemplateService(session)
        self.validator = DataValidatorService(session)
        self.layout_decision = LayoutDecisionEngine()
        self.session_memory = SessionMemoryPlanner()
        self.asset_delivery = AssetDeliveryService()
        self.content_format_guide = ContentFormatGuideService()
        self.live_research = LiveResearchService()
        self.research_editorial = ResearchEditorialPlanningService()
        self.content_planning = ContentPlanningService()
        self.format_family_planning = FormatFamilyPlanningService()
        self.visual_planning = VisualPlanningService()
        self.artifacts = ArtifactStateService()
        self.trace = GenerationTraceService()
        self.storage = LocalObjectStorage()

    @staticmethod
    def _merge_studio_panel(base: dict | None, override: dict | None) -> dict:
        merged = deepcopy(base or {})
        if not override:
            return resolve_studio_panel_defaults(merged)
        for key, value in override.items():
            if key == "size" and isinstance(value, dict):
                merged["size"] = {**merged.get("size", {}), **value}
            elif value is not None:
                merged[key] = value
        return resolve_studio_panel_defaults(merged)

    @staticmethod
    def _knowledge_channels() -> list[str]:
        return [
            KnowledgeChannel.BRAND,
            KnowledgeChannel.STRATEGY,
            KnowledgeChannel.METADATA,
            KnowledgeChannel.CAMPAIGN_HISTORY,
            KnowledgeChannel.TEMPLATE,
            "audience_insights",
            "guardrail_support",
            "visual_identity",
            "reference_creative",
            "mood_board",
            "chat_reference",
        ]

    @classmethod
    def _knowledge_channels_for_panel(cls, studio_panel: dict | None) -> list[str]:
        channels = list(cls._knowledge_channels())
        studio_panel = studio_panel or {}
        format_name = str(studio_panel.get("format") or "").strip().lower()
        file_type = str(studio_panel.get("file_type") or "").strip().lower()
        platform = str(studio_panel.get("platform_preset") or "").strip().lower()
        if (
            file_type == "png"
            and format_name in {"static", "story", "poster"}
            and platform in {"instagram", "linkedin", "x", "youtube_thumbnail", "facebook_post", "twitter_post", "your_story"}
        ):
            channels = [channel for channel in channels if channel != KnowledgeChannel.TEMPLATE]
        return channels

    @classmethod
    def _topic_query_terms(cls, prompt: str, *, limit: int = 6) -> list[str]:
        terms: list[str] = []
        seen: set[str] = set()
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9+#-]*", str(prompt or "").lower()):
            if token in cls.TOPIC_STOPWORDS or len(token) <= 2:
                continue
            if token in seen:
                continue
            seen.add(token)
            terms.append(token)
            if len(terms) >= limit:
                break
        return terms

    @classmethod
    def _sequence_pack_relevance_tokens(cls, value: object) -> set[str]:
        tokens: set[str] = set()
        text = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold())
        high_signal_short_tokens = {
            "aum",
            "cpi",
            "emi",
            "fta",
            "gdp",
            "gst",
            "inr",
            "ipo",
            "irr",
            "mom",
            "npa",
            "nps",
            "rbi",
            "roi",
            "sip",
            "usd",
            "xirr",
            "yoy",
            "ytd",
        }
        generic_tokens = cls.TOPIC_STOPWORDS | {
            "adapted",
            "asset",
            "authority",
            "blueprint",
            "card",
            "carousel",
            "creative",
            "detail",
            "family",
            "finance",
            "financial",
            "flow",
            "guide",
            "headline",
            "hook",
            "image",
            "illustration",
            "investing",
            "investment",
            "investor",
            "layout",
            "logo",
            "mistake",
            "mistakes",
            "page",
            "panel",
            "planning",
            "reference",
            "sequence",
            "slide",
            "slides",
            "story",
            "structure",
            "style",
            "takeaway",
            "template",
            "visual",
        }
        for raw_token in text.split():
            token = raw_token.strip()
            if token.endswith("s") and len(token) > 4:
                token = token[:-1]
            if (
                (len(token) >= 4 or token in high_signal_short_tokens)
                and token not in generic_tokens
                and not token.isdigit()
            ):
                tokens.add(token)
        return tokens

    @classmethod
    def _sequence_pack_is_relevant_to_prompt(
        cls,
        prompt: str | None,
        sequence_pack: dict[str, Any] | None,
    ) -> bool:
        if not isinstance(sequence_pack, dict):
            return False
        prompt_tokens = set(cls._topic_query_terms(str(prompt or ""), limit=8))
        if not prompt_tokens:
            return True
        pack_tokens: set[str] = set()
        pack_tokens.update(cls._sequence_pack_relevance_tokens(sequence_pack.get("family_name")))
        pack_tokens.update(cls._sequence_pack_relevance_tokens(sequence_pack.get("selected_template_name")))
        for slide in [dict(item) for item in sequence_pack.get("slides", []) if isinstance(item, dict)]:
            pack_tokens.update(cls._sequence_pack_relevance_tokens(slide.get("template_name")))
            pack_tokens.update(cls._sequence_pack_relevance_tokens(slide.get("headline_hint")))
            pack_tokens.update(cls._sequence_pack_relevance_tokens(slide.get("reference_asset_path")))
        if not pack_tokens:
            return True
        return bool(prompt_tokens.intersection(pack_tokens))

    @classmethod
    def _selected_template_context_evidence_texts(
        cls,
        *,
        prompt: str | None = None,
        selected_template_name: str | None,
        selected_template_id: str | None,
        template_recommendations: list[dict[str, Any]],
        reference_assets: list[dict[str, Any]],
    ) -> list[str]:
        selected_name_key = str(selected_template_name or "").strip().casefold()
        selected_id = str(selected_template_id or "").strip()
        selected_signature = cls._sequence_pack_signature(selected_template_name)
        evidence: list[str] = [
            str(prompt or "").strip(),
            str(selected_template_name or "").strip(),
        ]

        def _append_metadata_text(source: dict[str, Any]) -> None:
            metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
            for key in (
                "name",
                "display_name",
                "family_display_name",
                "sequence_family",
                "label",
                "headline",
                "headline_hint",
                "summary",
                "sequence_summary",
                "page_pattern",
                "slide_pattern",
                "structural_cues",
                "sequence_cues",
            ):
                value = source.get(key) if key in source else metadata.get(key)
                if isinstance(value, list):
                    evidence.extend(str(item or "").strip() for item in value if str(item or "").strip())
                elif str(value or "").strip():
                    evidence.append(str(value).strip())

        for recommendation in template_recommendations or []:
            candidate_id = str(recommendation.get("template_id") or "").strip()
            candidate_name = str(recommendation.get("name") or "").strip().casefold()
            if (selected_id and candidate_id == selected_id) or (selected_name_key and candidate_name == selected_name_key):
                _append_metadata_text(recommendation)

        for asset in reference_assets or []:
            if not isinstance(asset, dict):
                continue
            metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            asset_label = str(metadata.get("label") or "").strip().casefold()
            asset_signature = cls._sequence_pack_signature(asset.get("storage_path"))
            matches_signature = (
                selected_signature is not None
                and asset_signature is not None
                and asset_signature[0] == selected_signature[0]
            )
            matches_label = bool(selected_name_key and asset_label and selected_name_key in asset_label)
            if not matches_signature and not matches_label:
                continue
            _append_metadata_text(asset)
            storage_path = str(asset.get("storage_path") or "").strip()
            if storage_path.lower().endswith(".pdf") or str(asset.get("mime_type") or "").lower() == "application/pdf":
                evidence.extend(cls._read_reference_pdf_pages(storage_path)[:8])

        return [text for text in evidence if text]

    @classmethod
    def _template_context_layout_semantically_conflicts(
        cls,
        base_context: dict[str, Any] | None,
        evidence_texts: list[str],
    ) -> bool:
        if not isinstance(base_context, dict) or not evidence_texts:
            return False
        context_fragments: list[str] = []
        for key in (
            "editorial_dna",
            "subject_semantics",
            "visual_craft_dna",
            "composition_logic",
            "layout_dna",
            "background_style",
            "zone_map",
        ):
            value = base_context.get(key)
            if value:
                context_fragments.append(json.dumps(value, ensure_ascii=True, default=str))
        if not context_fragments:
            return False
        context_tokens = cls._sequence_pack_relevance_tokens(" ".join(context_fragments))
        evidence_tokens = cls._sequence_pack_relevance_tokens(" ".join(evidence_texts))
        if len(context_tokens) < 4 or len(evidence_tokens) < 4:
            return False
        overlap = context_tokens.intersection(evidence_tokens)
        overlap_ratio = len(overlap) / max(len(context_tokens), 1)
        return overlap_ratio < 0.12

    @classmethod
    def _strip_conflicting_template_layout_context(cls, base_context: dict[str, Any]) -> dict[str, Any]:
        cleaned = deepcopy(base_context or {})
        for key in (
            "icons",
            "zones",
            "layout_dna",
            "layout_type",
            "editorial_dna",
            "background_style",
            "visual_craft_dna",
            "composition_logic",
            "subject_semantics",
            "zone_map",
        ):
            cleaned.pop(key, None)
        cleaned["sample_metadata_status"] = "template_layout_context_ignored_due_to_semantic_mismatch"
        return cleaned

    @classmethod
    def _apply_template_context_surface_policy_to_planning_hints(
        cls,
        planning_hints: dict[str, Any] | None,
        template_context: dict[str, Any] | None,
        studio_panel: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        hints = deepcopy(planning_hints if isinstance(planning_hints, dict) else {})
        context = template_context if isinstance(template_context, dict) else {}
        sequence_pack = context.get("sequence_pack") if isinstance(context.get("sequence_pack"), dict) else {}
        surface_policy = str(sequence_pack.get("surface_policy") or "").strip().lower()
        if not surface_policy:
            return hints
        asset_strategy = deepcopy(hints.get("asset_strategy") if isinstance(hints.get("asset_strategy"), dict) else {})
        asset_strategy["template_surface_policy"] = surface_policy
        format_name = str((studio_panel or {}).get("format") or "").strip().lower()
        if surface_policy == "style_reference_only":
            asset_strategy["use_template_background"] = False
            asset_strategy["use_generated_image"] = True
            asset_strategy["use_brand_reference_assets"] = True
            asset_strategy.setdefault("dominant_visual_system", "generated_image")
            asset_strategy.setdefault("supporting_visual_system", "reference_assets" if format_name == "carousel" else "none")
        elif surface_policy in {"lock_template_surface", "sequence_pack_locked"}:
            asset_strategy["use_template_background"] = True
            asset_strategy["use_generated_image"] = False
            asset_strategy.setdefault("dominant_visual_system", "template_background")
        hints["asset_strategy"] = asset_strategy
        hints["template_surface_policy"] = surface_policy
        return hints

    @classmethod
    def _knowledge_queries_for_channel(cls, prompt: str, channel: str) -> list[str]:
        base_prompt = " ".join(str(prompt or "").split()).strip()
        topic_terms = cls._topic_query_terms(base_prompt)
        topic_suffix = f" relevant to {' '.join(topic_terms)}" if topic_terms else ""
        descriptor_map = {
            KnowledgeChannel.STRATEGY: [
                "brand strategy positioning campaign direction",
            ],
            "audience_insights": [
                "audience motivations pain points behaviors preferences",
            ],
            "guardrail_support": [
                "brand language guardrails dos donts approved blocked words",
            ],
            "visual_identity": [
                "brand visual identity palette typography iconography composition system",
                "brand colors fonts graphic system",
            ],
            "reference_creative": [
                "brand reference creative composition hierarchy layout editorial style",
                "reference creative visual treatment examples",
            ],
            "mood_board": [
                "brand mood board visual language motifs shapes textures atmosphere",
                "mood board aesthetic direction",
            ],
            KnowledgeChannel.TEMPLATE: [
                "brand template layout reusable zones editable sections composition",
            ],
            KnowledgeChannel.METADATA: [
                "brand metadata logo palette typography usage rules",
            ],
        }
        queries: list[str] = [base_prompt] if base_prompt else []
        for descriptor in descriptor_map.get(channel, []):
            queries.append(f"{descriptor}{topic_suffix}".strip())
            queries.append(descriptor)
        deduped: list[str] = []
        seen: set[str] = set()
        for query in queries:
            key = query.casefold()
            if not query or key in seen:
                continue
            seen.add(key)
            deduped.append(query)
        return deduped or ([base_prompt] if base_prompt else [])

    @staticmethod
    def _merge_retrieval_results(result_sets: list[list[dict]], *, limit: int) -> list[dict]:
        merged: dict[str, dict] = {}
        for results in result_sets:
            for item in results:
                if not isinstance(item, dict):
                    continue
                metadata = item.get("metadata")
                metadata = metadata if isinstance(metadata, dict) else {}
                key = (
                    str(metadata.get("chunk_id") or "").strip()
                    or f"{metadata.get('source_id') or 'unknown'}::{str(item.get('content') or '').strip()}"
                )
                try:
                    score = float(item.get("score"))
                except (TypeError, ValueError):
                    score = float("inf")
                existing = merged.get(key)
                if existing is None or score < float(existing.get("score", float("inf"))):
                    merged[key] = item
        return sorted(
            merged.values(),
            key=lambda item: float(item.get("score", float("inf"))),
        )[:limit]

    @staticmethod
    def _is_missing_brand_value(value: object) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (list, tuple, set, dict)):
            return len(value) == 0
        return False

    @classmethod
    def _merge_brand_context_missing(cls, preferred: object, fallback: object) -> object:
        if isinstance(preferred, dict) and isinstance(fallback, dict):
            merged = deepcopy(preferred)
            for key, fallback_value in fallback.items():
                current_value = merged.get(key)
                if key not in merged or cls._is_missing_brand_value(current_value):
                    merged[key] = deepcopy(fallback_value)
                    continue
                if isinstance(current_value, dict) and isinstance(fallback_value, dict):
                    merged[key] = cls._merge_brand_context_missing(current_value, fallback_value)
                    continue
                if isinstance(current_value, list) and isinstance(fallback_value, list) and not current_value:
                    merged[key] = deepcopy(fallback_value)
            return merged
        if cls._is_missing_brand_value(preferred):
            return deepcopy(fallback)
        return deepcopy(preferred)

    @staticmethod
    def _reusable_asset_record(asset: object) -> dict[str, object]:
        source_asset_id = getattr(asset, "source_asset_id", None)
        return {
            "id": str(getattr(asset, "id", "") or ""),
            "asset_kind": str(getattr(asset, "asset_kind", "") or ""),
            "review_class": str(getattr(asset, "review_class", "") or ""),
            "review_status": str(getattr(asset, "review_status", "") or ""),
            "review_reason": getattr(asset, "review_reason", None),
            "mime_type": str(getattr(asset, "mime_type", "image/png") or "image/png"),
            "storage_path": str(getattr(asset, "storage_path", "") or ""),
            "label": str(getattr(asset, "label", "") or ""),
            "source_asset_id": str(source_asset_id) if source_asset_id else None,
            "source_metadata": dict(getattr(asset, "source_metadata_json", {}) or {}),
            "normalized_metadata": dict(getattr(asset, "normalized_metadata_json", {}) or {}),
            "trust_level": str(getattr(asset, "trust_level", "reference_only") or "reference_only"),
            "width": int(getattr(asset, "width", 0) or 0),
            "height": int(getattr(asset, "height", 0) or 0),
        }

    @staticmethod
    def _palette_entries_from_logo_metadata(metadata: dict[str, object] | None) -> list[dict[str, object]]:
        metadata = metadata or {}
        candidate_lists = [
            metadata.get("logo_colors"),
            (metadata.get("normalized_metadata") or {}).get("logo_colors") if isinstance(metadata.get("normalized_metadata"), dict) else None,
            (metadata.get("source_metadata") or {}).get("logo_colors") if isinstance(metadata.get("source_metadata"), dict) else None,
        ]
        entries: list[dict[str, object]] = []
        seen: set[str] = set()
        for candidate_list in candidate_lists:
            if not isinstance(candidate_list, list):
                continue
            for item in candidate_list:
                if not isinstance(item, dict):
                    continue
                hex_code = str(item.get("hex_code") or item.get("hex") or "").strip().upper()
                if hex_code and not hex_code.startswith("#") and re.fullmatch(r"[0-9A-F]{6}", hex_code):
                    hex_code = f"#{hex_code}"
                if not hex_code or not re.fullmatch(r"#[0-9A-F]{6}", hex_code) or hex_code in seen:
                    continue
                seen.add(hex_code)
                entries.append(
                    {
                        "hex_code": hex_code,
                        "role": str(item.get("role") or "").strip().lower(),
                        "color_name": str(item.get("color_name") or item.get("name") or "").strip(),
                    }
                )
        return entries

    @staticmethod
    def _asset_ref(asset: GeneratedAsset) -> GeneratedImageAsset:
        return GeneratedImageAsset(
            asset_id=asset.id,
            mime_type=asset.mime_type,
            storage_path=asset.storage_path,
            width=asset.width or 0,
            height=asset.height or 0,
            asset_role=asset.asset_role,
            metadata=dict(asset.metadata_json or {}),
        )

    @staticmethod
    def _generated_asset_payload(asset: GeneratedAsset) -> dict:
        return {
            "asset_id": str(asset.id),
            "asset_role": asset.asset_role,
            "mime_type": asset.mime_type,
            "storage_path": asset.storage_path,
            "asset_url": AssetDeliveryService().build_signed_url(
                storage_path=asset.storage_path,
                filename=asset.storage_path.rsplit("/", 1)[-1],
            ),
            "metadata": asset.metadata_json,
        }

    @staticmethod
    def _chat_message_payload(message) -> dict:
        return {
            "id": str(message.id),
            "role": message.role,
            "message_text": message.message_text,
            "content_version_id": str(message.content_version_id) if message.content_version_id else None,
            "created_at": message.created_at.isoformat() if getattr(message, "created_at", None) else None,
        }

    @staticmethod
    def _content_prompt_lineage(content: ContentVersion) -> dict[str, object]:
        explainability = content.explainability_metadata if isinstance(content.explainability_metadata, dict) else {}
        prompt_lineage = explainability.get("prompt_lineage") if isinstance(explainability.get("prompt_lineage"), dict) else {}
        source_prompt = str(explainability.get("source_prompt") or "").strip()
        generation_prompt = str(prompt_lineage.get("generation_prompt_effective") or content.prompt or "").strip()
        raw_user_prompt = str(prompt_lineage.get("user_prompt_raw") or source_prompt or generation_prompt).strip()
        rewrite_instruction = str(prompt_lineage.get("rewrite_instruction") or explainability.get("rewrite_instruction") or "").strip()
        source_prompt_snapshot = str(prompt_lineage.get("source_prompt_snapshot") or source_prompt or generation_prompt).strip()
        return {
            "user_prompt_raw": raw_user_prompt,
            "generation_prompt_effective": generation_prompt,
            "rewrite_instruction": rewrite_instruction,
            "source_prompt_snapshot": source_prompt_snapshot,
            "request_mode": str(prompt_lineage.get("request_mode") or explainability.get("rewrite_mode") or "").strip(),
            "source_content_version_id": str(
                prompt_lineage.get("source_content_version_id")
                or explainability.get("rewrite_source_content_version_id")
                or ""
            ).strip(),
        }

    @staticmethod
    def _content_version_memory_payload(content: ContentVersion) -> dict:
        generated_payload = content.generated_payload or {}
        explainability = content.explainability_metadata or {}
        prompt_lineage = ContentService._content_prompt_lineage(content)
        request_lineage = explainability.get("request_lineage") if isinstance(explainability.get("request_lineage"), dict) else {}
        return {
            "id": str(content.id),
            "prompt": str(prompt_lineage.get("generation_prompt_effective") or content.prompt or ""),
            "prompt_lineage": prompt_lineage,
            "request_lineage": request_lineage,
            "title": content.title,
            "headline": generated_payload.get("headline", ""),
            "body": generated_payload.get("body", ""),
            "cta": generated_payload.get("cta", ""),
            "hashtags": generated_payload.get("hashtags", []) or [],
            "persona_id": str(content.selected_persona_id) if content.selected_persona_id else None,
            "objective_id": str(content.objective_id) if content.objective_id else None,
            "template_id": str(content.selected_template_id) if content.selected_template_id else None,
            "generation_decision": explainability.get("creative_decision", {}) or explainability.get("layout_decision", {}),
            "blueprint": content.blueprint_payload or {},
            "scene_graph": explainability.get("scene_graph", {}),
            "message_strategy": explainability.get("message_strategy", {}),
            "created_at": content.created_at.isoformat() if getattr(content, "created_at", None) else None,
        }

    @staticmethod
    def _rewrite_payload_for_prompt(content: ContentVersion) -> dict:
        generated_payload = content.generated_payload if isinstance(content.generated_payload, dict) else {}
        metadata = generated_payload.get("metadata") if isinstance(generated_payload.get("metadata"), dict) else {}
        return {
            "headline": generated_payload.get("headline", ""),
            "body": generated_payload.get("body", ""),
            "cta": generated_payload.get("cta", ""),
            "hashtags": generated_payload.get("hashtags", []) or [],
            "metadata": {
                "section_label": metadata.get("section_label", ""),
                "supporting_line": metadata.get("supporting_line", ""),
                "proof_points": metadata.get("proof_points", []) or [],
                "stat_highlights": metadata.get("stat_highlights", []) or [],
                "hook_type": metadata.get("hook_type", ""),
                "objection_handling": metadata.get("objection_handling", []) or [],
                "trust_builders": metadata.get("trust_builders", []) or [],
                "claim_evidence_pairs": metadata.get("claim_evidence_pairs", []) or [],
            },
        }

    @staticmethod
    def _rewrite_strategy_for_prompt(content: ContentVersion) -> dict:
        explainability = content.explainability_metadata if isinstance(content.explainability_metadata, dict) else {}
        strategy = explainability.get("message_strategy") if isinstance(explainability.get("message_strategy"), dict) else {}
        return {
            "message_strategy": strategy,
            "validation_report": explainability.get("validation_report", {}) or {},
        }

    @staticmethod
    def _rewrite_tone_feedback_for_prompt(content: ContentVersion) -> dict:
        tone_feedback = content.tone_feedback if isinstance(content.tone_feedback, dict) else {}
        return {
            "score": tone_feedback.get("score", content.tone_score),
            "matched_signals": tone_feedback.get("matched_signals", []) or [],
            "deviations": tone_feedback.get("deviations", []) or [],
            "rewrite_suggestions": tone_feedback.get("rewrite_suggestions", []) or [],
            "quality_summary": tone_feedback.get("quality_summary", []) or [],
            "persuasion_dimensions": tone_feedback.get("persuasion_dimensions", {}) or {},
            "field_guidance": tone_feedback.get("field_guidance", {}) or {},
        }

    @classmethod
    def _tone_check_content_string(cls, content_payload: dict[str, object] | None) -> str:
        payload = content_payload if isinstance(content_payload, dict) else {}
        headline = str(payload.get("headline") or "").strip().rstrip(".!? ")
        body = str(payload.get("body") or "").strip().rstrip(".!? ")
        cta = str(payload.get("cta") or "").strip().rstrip(".!? ")
        return ". ".join(part for part in [headline, body, cta] if part)

    @classmethod
    def _rewrite_field_plan_for_prompt(cls, content: ContentVersion) -> dict:
        rewrite_payload = cls._rewrite_payload_for_prompt(content)
        tone_feedback = cls._rewrite_tone_feedback_for_prompt(content)
        metadata = rewrite_payload.get("metadata", {}) if isinstance(rewrite_payload.get("metadata"), dict) else {}
        persuasion_dimensions = tone_feedback.get("persuasion_dimensions", {}) if isinstance(tone_feedback.get("persuasion_dimensions"), dict) else {}
        field_guidance = tone_feedback.get("field_guidance", {}) if isinstance(tone_feedback.get("field_guidance"), dict) else {}

        must_preserve: list[str] = []
        for label, values in (
            ("proof_point", metadata.get("proof_points", []) or []),
            ("stat_highlight", metadata.get("stat_highlights", []) or []),
            ("trust_builder", metadata.get("trust_builders", []) or []),
            ("objection_handling", metadata.get("objection_handling", []) or []),
        ):
            for value in values:
                if not value:
                    continue
                must_preserve.append(f"{label}: {value}")
        for pair in metadata.get("claim_evidence_pairs", []) or []:
            if not isinstance(pair, dict):
                continue
            claim = str(pair.get("claim") or "").strip()
            evidence = str(pair.get("evidence") or "").strip()
            if claim or evidence:
                must_preserve.append(f"claim_evidence: {claim} -> {evidence}".strip())

        priority_fixes: list[str] = []
        if int(persuasion_dimensions.get("proof_strength", 100)) < 72:
            priority_fixes.append("Strengthen claim/evidence support so the copy earns its promise instead of sounding asserted.")
        if int(persuasion_dimensions.get("objection_handling", 100)) < 72:
            priority_fixes.append("Answer the audience's likely skepticism or friction explicitly.")
        if int(persuasion_dimensions.get("distinctiveness", 100)) < 70:
            priority_fixes.append("Replace generic promotional wording with a clearer angle, mechanism, or audience-specific differentiator.")
        if int(persuasion_dimensions.get("cta_strength", 100)) < 72:
            priority_fixes.append("Make the CTA benefit-linked and concrete rather than generic.")

        return {
            "headline": field_guidance.get("headline", []) or [
                "Sharpen the headline so the persuasion angle is explicit rather than implied.",
            ],
            "body": field_guidance.get("body", []) or [
                "Use the body to carry proof, differentiation, and objection resolution instead of repeating the headline.",
            ],
            "cta": field_guidance.get("cta", []) or [
                "Keep the CTA action-oriented and tie it to the audience outcome.",
            ],
            "metadata": field_guidance.get("metadata", []) or [
                "Update persuasion metadata so proof_points, trust_builders, objection_handling, and claim_evidence_pairs stay useful downstream.",
            ],
            "must_preserve": cls._dedupe_preserved_lines(must_preserve)[:10],
            "priority_fixes": cls._dedupe_preserved_lines(priority_fixes)[:6],
        }

    @staticmethod
    def _dedupe_preserved_lines(values: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for value in values:
            normalized = str(value or "").strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            output.append(normalized)
        return output

    @staticmethod
    def _normalized_rewrite_instruction(value: str) -> str:
        return " ".join(str(value or "").casefold().split())

    @classmethod
    def _source_prompt_for_rewrite(cls, content: ContentVersion) -> str:
        prompt_lineage = cls._content_prompt_lineage(content)
        source_prompt = str(prompt_lineage.get("user_prompt_raw") or prompt_lineage.get("source_prompt_snapshot") or "").strip()
        if source_prompt:
            return source_prompt
        explainability = content.explainability_metadata if isinstance(content.explainability_metadata, dict) else {}
        source_prompt = str(explainability.get("source_prompt") or "").strip()
        if source_prompt:
            return source_prompt
        prompt = str(content.prompt or "").strip()
        if not prompt:
            return ""
        match = re.search(r"Original user prompt:\s*(.+)", prompt)
        if match:
            extracted = str(match.group(1) or "").strip()
            if extracted:
                return extracted
        return prompt

    @classmethod
    def _rewrite_instruction_targets_field(cls, field: str, rewrite_instruction: str) -> bool:
        normalized_instruction = cls._normalized_rewrite_instruction(rewrite_instruction)
        if not normalized_instruction:
            return False
        field_hints = cls.REWRITE_FIELD_HINTS.get(field, ())
        if not field_hints:
            return False
        action_markers = cls.REWRITE_REMOVAL_MARKERS + cls.REWRITE_REPLACEMENT_MARKERS
        rewrite_markers = ("tighten", "rewrite", "rework", "refresh", "refine", "sharpen", "improve", "update", "change", "make")
        trailing_actions = (
            "removed",
            "deleted",
            "dropped",
            "omitted",
            "excluded",
            "stripped",
            "replaced",
            "swapped",
            "substituted",
            "tightened",
            "rewritten",
            "reworked",
            "refreshed",
            "refined",
            "sharpened",
            "improved",
            "updated",
            "changed",
        )
        for hint in field_hints:
            escaped_hint = re.escape(hint)
            for marker in action_markers:
                if re.search(rf"{re.escape(marker)}\s+(?:the\s+)?{escaped_hint}\b", normalized_instruction):
                    return True
            for marker in rewrite_markers:
                if re.search(rf"{re.escape(marker)}\s+(?:the\s+)?{escaped_hint}\b", normalized_instruction):
                    return True
            if re.search(
                rf"\b{escaped_hint}\b(?:\s+\w+){{0,4}}\s+(?:should\s+be\s+)?(?:{'|'.join(trailing_actions)})\b",
                normalized_instruction,
            ):
                return True
        return False

    @classmethod
    def _rewrite_instruction_targets_value(cls, value: str, rewrite_instruction: str) -> bool:
        normalized_instruction = cls._normalized_rewrite_instruction(rewrite_instruction)
        normalized_value = cls._normalized_rewrite_instruction(value)
        if not normalized_instruction or not normalized_value or len(normalized_value) < 5:
            return False
        action_markers = cls.REWRITE_REMOVAL_MARKERS + cls.REWRITE_REPLACEMENT_MARKERS
        return normalized_value in normalized_instruction and any(
            marker in normalized_instruction for marker in action_markers
        )

    @classmethod
    def _rewrite_targeted_core_fields(cls, rewrite_instruction: str) -> set[str]:
        targeted_fields = {
            field
            for field in cls.REWRITE_CORE_FIELDS
            if cls._rewrite_instruction_targets_field(field, rewrite_instruction)
        }
        return targeted_fields or set(cls.REWRITE_CORE_FIELDS)

    @classmethod
    def _rewrite_targeted_fields(cls, rewrite_instruction: str) -> list[str]:
        return sorted(
            field
            for field in cls.REWRITE_FIELD_HINTS
            if cls._rewrite_instruction_targets_field(field, rewrite_instruction)
        )

    @classmethod
    def _revision_scope_targeted_fields(cls, revision_scope: dict[str, object] | None) -> set[str]:
        if not isinstance(revision_scope, dict):
            return set()
        return {
            str(field).strip()
            for field in revision_scope.get("targeted_fields", [])
            if str(field).strip()
        }

    @classmethod
    def _revision_scope_targeted_core_fields(cls, revision_scope: dict[str, object] | None) -> set[str]:
        return cls._revision_scope_targeted_fields(revision_scope) & set(cls.REWRITE_CORE_FIELDS)

    @classmethod
    def _revision_scope_targeted_slide_indexes(
        cls,
        revision_scope: dict[str, object] | None,
        *,
        original_slide_specs: list[dict[str, object]],
    ) -> set[int]:
        if not isinstance(revision_scope, dict):
            return set()
        slide_indexes = {
            int(value)
            for value in revision_scope.get("slide_indexes", [])
            if str(value).strip().isdigit() and int(str(value).strip()) > 0
        }
        slide_targets = {
            str(target).strip().casefold()
            for target in revision_scope.get("slide_targets", [])
            if str(target).strip()
        }
        if "cover" in slide_targets:
            slide_indexes.add(1)
        if "last" in slide_targets and original_slide_specs:
            last_index = 0
            for position, slide in enumerate(original_slide_specs, start=1):
                last_index = max(last_index, int(slide.get("slide_index") or position))
            if last_index:
                slide_indexes.add(last_index)
        return slide_indexes

    @classmethod
    def _merge_selective_carousel_slide_specs(
        cls,
        *,
        original_metadata: dict[str, object],
        rewritten_metadata: dict[str, object],
        revision_scope: dict[str, object] | None,
    ) -> tuple[dict[str, object], list[int]]:
        original_specs_raw = original_metadata.get("carousel_slide_specs")
        if not isinstance(original_specs_raw, list) or not original_specs_raw:
            return dict(rewritten_metadata), []
        targeted_slide_indexes = cls._revision_scope_targeted_slide_indexes(
            revision_scope,
            original_slide_specs=[spec for spec in original_specs_raw if isinstance(spec, dict)],
        )
        if not targeted_slide_indexes:
            return dict(rewritten_metadata), []

        rewritten_specs_raw = rewritten_metadata.get("carousel_slide_specs")
        original_specs = [deepcopy(spec) for spec in original_specs_raw if isinstance(spec, dict)]
        rewritten_specs = [deepcopy(spec) for spec in rewritten_specs_raw if isinstance(spec, dict)] if isinstance(rewritten_specs_raw, list) else []
        rewritten_by_index = {
            int(spec.get("slide_index") or position): spec
            for position, spec in enumerate(rewritten_specs, start=1)
        }
        merged_specs: list[dict[str, object]] = []
        updated_indexes: list[int] = []
        for position, original_spec in enumerate(original_specs, start=1):
            slide_index = int(original_spec.get("slide_index") or position)
            if slide_index in targeted_slide_indexes and slide_index in rewritten_by_index:
                merged_specs.append(rewritten_by_index[slide_index])
                updated_indexes.append(slide_index)
            else:
                merged_specs.append(original_spec)
        merged_metadata = dict(rewritten_metadata)
        merged_metadata["carousel_slide_specs"] = merged_specs
        return merged_metadata, updated_indexes

    @classmethod
    def _build_selective_regeneration_plan(
        cls,
        *,
        original: ContentVersion,
        revision_scope: dict[str, object] | None,
    ) -> dict[str, object]:
        if not isinstance(revision_scope, dict):
            return {}
        targeted_fields = sorted(cls._revision_scope_targeted_fields(revision_scope))
        original_metadata = (
            original.generated_payload.get("metadata")
            if isinstance(getattr(original, "generated_payload", None), dict)
            and isinstance(original.generated_payload.get("metadata"), dict)
            else {}
        )
        original_slide_specs = (
            original_metadata.get("carousel_slide_specs")
            if isinstance(original_metadata, dict)
            and isinstance(original_metadata.get("carousel_slide_specs"), list)
            else []
        )
        targeted_slide_indexes = sorted(
            cls._revision_scope_targeted_slide_indexes(
                revision_scope,
                original_slide_specs=[spec for spec in original_slide_specs if isinstance(spec, dict)],
            )
        )
        slide_count = len([spec for spec in original_slide_specs if isinstance(spec, dict)])
        if (
            not targeted_slide_indexes
            and slide_count
            and targeted_fields
            and not bool(revision_scope.get("preserve_visuals"))
        ):
            targeted_slide_indexes = list(range(1, slide_count + 1))
        if not targeted_slide_indexes and bool(revision_scope.get("preserve_visuals")) and slide_count:
            targeted_slide_indexes = list(range(1, slide_count + 1))
        reuse_slide_indexes = [
            index
            for index in range(1, slide_count + 1)
            if index not in set(targeted_slide_indexes)
        ]
        if not targeted_fields and not targeted_slide_indexes:
            return {}
        return {
            "targeted_fields": targeted_fields,
            "targeted_slide_indexes": targeted_slide_indexes,
            "reuse_slide_indexes": reuse_slide_indexes,
            "preserve_visuals": bool(revision_scope.get("preserve_visuals")),
            "preserve_copy": bool(revision_scope.get("preserve_copy")),
            "change_layout": bool(revision_scope.get("change_layout")),
            "change_tone": bool(revision_scope.get("change_tone")),
            "only_targeted": bool(revision_scope.get("only_targeted")),
            "rewrite_source_content_version_id": str(original.id),
        }

    @classmethod
    def _rewrite_context_tokens(cls, *values: object, limit: int = 24) -> set[str]:
        tokens: list[str] = []
        for value in values:
            for word in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", str(value or "")):
                normalized = cls._normalize_topic_token(word)
                if not normalized or normalized in cls.REWRITE_CONTEXT_STOPWORDS or normalized in tokens:
                    continue
                tokens.append(normalized)
                if len(tokens) >= limit:
                    return set(tokens)
        return set(tokens)

    @classmethod
    def _rewrite_has_material_angle_shift(
        cls,
        *,
        original_payload: dict[str, object],
        rewritten_payload: dict[str, object],
        rewrite_instruction: str,
    ) -> bool:
        original_metadata = original_payload.get("metadata") if isinstance(original_payload.get("metadata"), dict) else {}
        rewritten_metadata = rewritten_payload.get("metadata") if isinstance(rewritten_payload.get("metadata"), dict) else {}
        original_tokens = cls._rewrite_context_tokens(
            original_payload.get("headline"),
            original_payload.get("body"),
            original_payload.get("cta"),
            original_metadata.get("supporting_line"),
            original_metadata.get("section_label"),
        )
        rewritten_tokens = cls._rewrite_context_tokens(
            rewrite_instruction,
            rewritten_payload.get("headline"),
            rewritten_payload.get("body"),
            rewritten_payload.get("cta"),
            rewritten_metadata.get("supporting_line"),
            rewritten_metadata.get("section_label"),
        )
        if not original_tokens or not rewritten_tokens:
            return False
        overlap = original_tokens & rewritten_tokens
        return len(overlap) <= 1 and len(rewritten_tokens - original_tokens) >= 2

    @classmethod
    def _rewrite_item_matches_context(cls, value: object, rewrite_context_tokens: set[str]) -> bool:
        text = str(value or "").strip()
        if not text or not rewrite_context_tokens:
            return bool(text)
        item_tokens = cls._rewrite_context_tokens(text, limit=10)
        if not item_tokens:
            return False
        overlap = item_tokens & rewrite_context_tokens
        meaningful_overlap = overlap - cls.REWRITE_LOW_SIGNAL_MATCH_TOKENS
        if meaningful_overlap:
            return True
        if len(overlap) >= 3:
            return True
        if len(overlap) == 1 and len(item_tokens) <= 2 and overlap == meaningful_overlap:
            return True
        return False

    @classmethod
    def _merge_rewrite_text_items(
        cls,
        *,
        field: str,
        original_items: object,
        rewritten_items: object,
        rewrite_instruction: str,
        limit: int,
        rewrite_context_tokens: set[str],
        enforce_context_match: bool,
    ) -> tuple[list[str], bool, list[str]]:
        rewritten = AIOrchestratorService._normalize_metadata_list(rewritten_items, limit=limit)
        if cls._rewrite_instruction_targets_field(field, rewrite_instruction):
            return rewritten, False, []
        original = [
            item for item in AIOrchestratorService._normalize_metadata_list(original_items, limit=limit * 2)
        ]
        preserved_original: list[str] = []
        stale_drops: list[str] = []
        for item in original:
            if cls._rewrite_instruction_targets_value(item, rewrite_instruction):
                continue
            if enforce_context_match and not cls._rewrite_item_matches_context(item, rewrite_context_tokens):
                stale_drops.append(item)
                continue
            preserved_original.append(item)
        merged = AIOrchestratorService._normalize_metadata_list([*original, *rewritten], limit=limit)
        if preserved_original != original:
            merged = AIOrchestratorService._normalize_metadata_list([*preserved_original, *rewritten], limit=limit)
        restored = any(item not in rewritten for item in merged if item in preserved_original)
        return merged, restored, stale_drops

    @classmethod
    def _merge_rewrite_claim_evidence_pairs(
        cls,
        *,
        original_pairs: object,
        rewritten_pairs: object,
        rewrite_instruction: str,
        limit: int,
        rewrite_context_tokens: set[str],
        enforce_context_match: bool,
    ) -> tuple[list[dict[str, str]], bool, list[str]]:
        rewritten = AIOrchestratorService._normalize_claim_evidence_pairs(rewritten_pairs, limit=limit)
        if cls._rewrite_instruction_targets_field("claim_evidence_pairs", rewrite_instruction):
            return rewritten, False, []

        preserved_original: list[dict[str, str]] = []
        stale_drops: list[str] = []
        for pair in AIOrchestratorService._normalize_claim_evidence_pairs(original_pairs, limit=limit * 2):
            claim = str(pair.get("claim") or "").strip()
            evidence = str(pair.get("evidence") or "").strip()
            pair_signature = " ".join(part for part in [claim, evidence] if part).strip()
            if pair_signature and cls._rewrite_instruction_targets_value(pair_signature, rewrite_instruction):
                continue
            if claim and cls._rewrite_instruction_targets_value(claim, rewrite_instruction):
                continue
            if evidence and cls._rewrite_instruction_targets_value(evidence, rewrite_instruction):
                continue
            if enforce_context_match and not cls._rewrite_item_matches_context(pair_signature, rewrite_context_tokens):
                if pair_signature:
                    stale_drops.append(pair_signature)
                continue
            preserved_original.append({"claim": claim, "evidence": evidence})

        merged = AIOrchestratorService._normalize_claim_evidence_pairs(
            [*preserved_original, *rewritten],
            limit=limit,
        )
        rewritten_keys = {
            (str(pair.get("claim") or "").strip().casefold(), str(pair.get("evidence") or "").strip().casefold())
            for pair in rewritten
        }
        restored = any(
            (
                str(pair.get("claim") or "").strip().casefold(),
                str(pair.get("evidence") or "").strip().casefold(),
            )
            not in rewritten_keys
            for pair in merged
            if pair in preserved_original
        )
        return merged, restored, stale_drops

    @classmethod
    def _repair_rewrite_payload(
        cls,
        original: ContentVersion,
        rewritten_payload: dict[str, object] | None,
        rewrite_instruction: str,
        revision_scope: dict[str, object] | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        original_payload = cls._rewrite_payload_for_prompt(original)
        targeted_core_fields = cls._rewrite_targeted_core_fields(rewrite_instruction)
        explicit_targeted_core_fields = cls._revision_scope_targeted_core_fields(revision_scope)
        if explicit_targeted_core_fields:
            targeted_core_fields = explicit_targeted_core_fields
        elif isinstance(revision_scope, dict) and (
            revision_scope.get("slide_indexes")
            or revision_scope.get("slide_targets")
            or revision_scope.get("only_targeted")
        ):
            targeted_core_fields = set()
        fallback_payload = {
            "headline": str(original_payload.get("headline") or "").strip() if "headline" not in targeted_core_fields else "",
            "body": str(original_payload.get("body") or "").strip() if "body" not in targeted_core_fields else "",
            "cta": str(original_payload.get("cta") or "").strip() if "cta" not in targeted_core_fields else "",
            "hashtags": list(original_payload.get("hashtags", []) or []),
            "metadata": {},
        }
        normalized_payload = AIOrchestratorService.normalize_text_payload(
            rewritten_payload if isinstance(rewritten_payload, dict) else {},
            fallback=fallback_payload,
        )
        revision_targeted_fields = cls._revision_scope_targeted_fields(revision_scope)
        preserve_copy = bool((revision_scope or {}).get("preserve_copy")) if isinstance(revision_scope, dict) else False
        if revision_targeted_fields or (isinstance(revision_scope, dict) and revision_scope.get("only_targeted")) or preserve_copy:
            for field in cls.REWRITE_CORE_FIELDS:
                if field in targeted_core_fields and not preserve_copy:
                    continue
                normalized_payload[field] = str(original_payload.get(field) or "").strip()
            if "hashtags" not in revision_targeted_fields or preserve_copy:
                normalized_payload["hashtags"] = list(original_payload.get("hashtags", []) or [])
        raw_original_payload = original.generated_payload if isinstance(original.generated_payload, dict) else {}
        original_metadata = raw_original_payload.get("metadata", {}) if isinstance(raw_original_payload.get("metadata"), dict) else {}
        if not original_metadata:
            original_metadata = original_payload.get("metadata", {}) if isinstance(original_payload.get("metadata"), dict) else {}
        rewritten_metadata = normalized_payload.get("metadata", {}) if isinstance(normalized_payload.get("metadata"), dict) else {}
        repaired_metadata = dict(original_metadata) if preserve_copy else dict(rewritten_metadata)
        restored_fields: list[str] = []
        stale_fields_dropped: dict[str, list[str]] = {}
        angle_shift_detected = cls._rewrite_has_material_angle_shift(
            original_payload=original_payload,
            rewritten_payload=normalized_payload,
            rewrite_instruction=rewrite_instruction,
        )
        rewrite_context_tokens = cls._rewrite_context_tokens(
            rewrite_instruction,
            normalized_payload.get("headline"),
            normalized_payload.get("body"),
            normalized_payload.get("cta"),
            rewritten_metadata.get("supporting_line"),
            rewritten_metadata.get("section_label"),
        )

        for field, limit in (
            ("proof_points", 4),
            ("stat_highlights", 3),
            ("trust_builders", 4),
            ("objection_handling", 3),
        ):
            merged, restored, stale_drops = cls._merge_rewrite_text_items(
                field=field,
                original_items=original_metadata.get(field, []),
                rewritten_items=rewritten_metadata.get(field, []),
                rewrite_instruction=rewrite_instruction,
                limit=limit,
                rewrite_context_tokens=rewrite_context_tokens,
                enforce_context_match=angle_shift_detected,
            )
            repaired_metadata[field] = merged
            if restored:
                restored_fields.append(field)
            if stale_drops:
                stale_fields_dropped[field] = stale_drops

        merged_pairs, restored_pairs, stale_pair_drops = cls._merge_rewrite_claim_evidence_pairs(
            original_pairs=original_metadata.get("claim_evidence_pairs", []),
            rewritten_pairs=rewritten_metadata.get("claim_evidence_pairs", []),
            rewrite_instruction=rewrite_instruction,
            limit=3,
            rewrite_context_tokens=rewrite_context_tokens,
            enforce_context_match=angle_shift_detected,
        )
        repaired_metadata["claim_evidence_pairs"] = merged_pairs
        if restored_pairs:
            restored_fields.append("claim_evidence_pairs")
        if stale_pair_drops:
            stale_fields_dropped["claim_evidence_pairs"] = stale_pair_drops

        original_hook_type = str(original_metadata.get("hook_type") or "").strip()
        rewritten_hook_type = str(rewritten_metadata.get("hook_type") or "").strip()
        if original_hook_type and not rewritten_hook_type and not cls._rewrite_instruction_targets_field("hook_type", rewrite_instruction):
            repaired_metadata["hook_type"] = original_hook_type
            restored_fields.append("hook_type")

        metadata_fallback = dict(original_metadata)
        if angle_shift_detected:
            for field in ("supporting_line", "subheadline", "section_label", "visual_direction", "design_style", "image_prompt"):
                repaired_metadata[field] = str(rewritten_metadata.get(field) or "").strip()
                metadata_fallback[field] = ""

        normalized_payload["metadata"] = AIOrchestratorService.normalize_metadata_payload(
            repaired_metadata,
            fallback=metadata_fallback,
            body=str(normalized_payload.get("body") or ""),
        )
        merged_metadata, updated_slide_indexes = cls._merge_selective_carousel_slide_specs(
            original_metadata=original_metadata,
            rewritten_metadata=normalized_payload["metadata"],
            revision_scope=revision_scope,
        )
        normalized_payload["metadata"] = merged_metadata
        missing_targeted_core_fields = [
            field for field in sorted(targeted_core_fields)
            if not str(normalized_payload.get(field) or "").strip()
        ]
        preserved_core_fields = [
            field for field in cls.REWRITE_CORE_FIELDS
            if field not in targeted_core_fields
            and str(normalized_payload.get(field) or "").strip() == str(original_payload.get(field) or "").strip()
        ]
        diagnostics = {
            "restored_fields": cls._dedupe_preserved_lines(restored_fields),
            "instruction_targets": sorted(
                field
                for field in cls.REWRITE_FIELD_HINTS
                if cls._rewrite_instruction_targets_field(field, rewrite_instruction)
            ),
            "revision_scope_targeted_fields": sorted(revision_targeted_fields),
            "targeted_core_fields": sorted(targeted_core_fields),
            "preserved_core_fields": preserved_core_fields,
            "missing_targeted_core_fields": missing_targeted_core_fields,
            "angle_shift_detected": angle_shift_detected,
            "stale_fields_dropped": sorted(stale_fields_dropped),
        }
        if updated_slide_indexes:
            diagnostics["updated_slide_indexes"] = updated_slide_indexes
        if stale_fields_dropped:
            diagnostics["stale_items_dropped"] = stale_fields_dropped
        return normalized_payload, diagnostics

    @staticmethod
    def _sync_rewrite_scene_graph(explainability_metadata: dict[str, object], payload: dict[str, object]) -> dict[str, object]:
        explainability = deepcopy(explainability_metadata if isinstance(explainability_metadata, dict) else {})
        for key in ("scene_graph", "final_render_scene_graph"):
            scene_graph = explainability.get(key)
            if not isinstance(scene_graph, dict):
                continue
            elements = scene_graph.get("elements")
            if not isinstance(elements, list):
                continue
            updated_scene_graph = dict(scene_graph)
            updated_scene_graph["elements"] = AIOrchestratorService._sync_scene_graph_copy_from_text_payload(
                elements=elements,
                text_payload=payload,
            )
            explainability[key] = updated_scene_graph
        return explainability

    @classmethod
    def _rewrite_fallback_payload(cls, original: ContentVersion, rewrite_instruction: str) -> dict[str, object]:
        original_payload = deepcopy(cls._rewrite_payload_for_prompt(original))
        fallback_payload = deepcopy(original_payload)
        targeted_core_fields = cls._rewrite_targeted_core_fields(rewrite_instruction)
        targeted_fields = set(cls._rewrite_targeted_fields(rewrite_instruction))

        for field in targeted_core_fields:
            fallback_payload[field] = ""

        metadata = dict(fallback_payload.get("metadata", {}) if isinstance(fallback_payload.get("metadata"), dict) else {})
        for field in targeted_fields - set(cls.REWRITE_CORE_FIELDS):
            if field in {"proof_points", "stat_highlights", "trust_builders", "objection_handling", "claim_evidence_pairs"}:
                metadata[field] = []
            elif field == "hook_type":
                metadata[field] = ""
        fallback_payload["metadata"] = metadata
        return fallback_payload

    def _rewrite_compiled_context(
        self,
        *,
        original: ContentVersion,
        source_prompt: str,
        resolved_brand_context: dict[str, object],
        persona_context: dict[str, object],
        objective_context: dict[str, object],
        studio_panel: dict[str, object],
        session: ContentSession | None,
        content_format_guide: dict[str, Any] | None = None,
        research_editorial_brief: dict[str, Any] | None = None,
        format_family_plan: dict[str, Any] | None = None,
        content_plan: dict[str, Any] | None = None,
        visual_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        explainability = original.explainability_metadata if isinstance(original.explainability_metadata, dict) else {}
        stored_compiled_context = explainability.get("compiled_context")
        if isinstance(stored_compiled_context, dict) and stored_compiled_context:
            stored_copy = deepcopy(stored_compiled_context)
            stored_content_format_brief = (
                stored_copy.get("content_format_brief")
                if isinstance(stored_copy.get("content_format_brief"), dict)
                else {}
            )
            stored_research_editorial_brief = (
                stored_copy.get("research_editorial_brief")
                if isinstance(stored_copy.get("research_editorial_brief"), dict)
                else {}
            )
            stored_format_family_plan = (
                stored_copy.get("format_family_plan")
                if isinstance(stored_copy.get("format_family_plan"), dict)
                else {}
            )
            stored_content_plan = (
                stored_copy.get("content_plan")
                if isinstance(stored_copy.get("content_plan"), dict)
                else {}
            )
            stored_visual_plan = (
                stored_copy.get("visual_plan")
                if isinstance(stored_copy.get("visual_plan"), dict)
                else {}
            )
            if (
                stored_content_format_brief
                and (stored_research_editorial_brief or not research_editorial_brief)
                and (stored_format_family_plan or not format_family_plan)
                and (stored_content_plan or not content_plan)
                and (stored_visual_plan or not visual_plan)
            ):
                return stored_copy
            backfilled_content_format_brief = self.orchestrator.compiler._content_format_brief(
                content_format_guide,
                studio_panel,
            )
            if backfilled_content_format_brief:
                stored_copy["content_format_brief"] = backfilled_content_format_brief
            if research_editorial_brief and not stored_research_editorial_brief:
                stored_copy["research_editorial_brief"] = research_editorial_brief
            if format_family_plan and not stored_format_family_plan:
                stored_copy["format_family_plan"] = format_family_plan
            if content_plan and not stored_content_plan:
                stored_copy["content_plan"] = content_plan
            if visual_plan and not stored_visual_plan:
                stored_copy["visual_plan"] = visual_plan
            return stored_copy

        session_memory = explainability.get("session_memory") if isinstance(explainability.get("session_memory"), dict) else {}
        layout_decision = (
            explainability.get("creative_decision")
            if isinstance(explainability.get("creative_decision"), dict)
            else explainability.get("layout_decision")
            if isinstance(explainability.get("layout_decision"), dict)
            else {}
        )
        return self.orchestrator.compiler.compile(
            prompt=source_prompt,
            brand_context=resolved_brand_context,
            persona_context=persona_context,
            objective_context=objective_context,
            ordered_knowledge={},
            studio_panel=studio_panel,
            conversation_context=session.conversational_context if session else {},
            session_memory=session_memory,
            layout_decision=layout_decision,
            content_format_guide=content_format_guide,
            research_editorial_brief=research_editorial_brief,
            format_family_plan=format_family_plan,
            content_plan=content_plan,
            visual_plan=visual_plan,
        )

    async def _generate_rewrite_candidate_payload(
        self,
        *,
        original: ContentVersion,
        rewrite_instruction: str,
        revision_scope: dict[str, object] | None,
        source_prompt: str,
        resolved_brand_context: dict[str, object],
        compiled_context: dict[str, Any],
        message_strategy: dict[str, object],
        studio_panel: dict[str, object],
    ) -> dict[str, object]:
        current_payload = self._rewrite_payload_for_prompt(original)
        tone_feedback = self._rewrite_tone_feedback_for_prompt(original)
        rewrite_field_plan = self._rewrite_field_plan_for_prompt(original)
        targeted_fields = self._rewrite_targeted_fields(rewrite_instruction)
        revision_targeted_fields = [
            str(field).strip()
            for field in (revision_scope or {}).get("targeted_fields", [])
            if str(field).strip()
        ]
        if revision_targeted_fields:
            targeted_fields = sorted(set(targeted_fields) | set(revision_targeted_fields))
        fallback_payload = self._rewrite_fallback_payload(original, rewrite_instruction)
        envelope = self.orchestrator.prompts.compose_rewrite_envelope(
            original_prompt=source_prompt,
            rewrite_instruction=rewrite_instruction,
            current_payload=current_payload,
            compiled_context=compiled_context,
            message_strategy=message_strategy,
            tone_analysis=tone_feedback,
            rewrite_field_plan=rewrite_field_plan,
            studio_panel=studio_panel,
            targeted_fields=targeted_fields,
            revision_scope=revision_scope,
        )
        provider = self.orchestrator.providers.get_text_provider("generation")
        response = provider.generate_structured_json(
            envelope,
            fallback=fallback_payload,
        )
        text_dict = AIOrchestratorService.normalize_text_payload(
            response if isinstance(response, dict) else {},
            fallback_payload,
            brand_name=str(resolved_brand_context.get("brand_name") or ""),
            compiled_context=compiled_context,
        )
        text_payload = StructuredTextPayload.model_validate(text_dict)
        text_payload = self.orchestrator._repair_prompt_echo_text_payload(
            text_payload,
            prompt=rewrite_instruction,
        )
        return text_payload.model_dump(mode="json")

    @classmethod
    def _rewrite_message_strategy(
        cls,
        *,
        original_strategy: dict[str, object] | None,
        rewritten_payload: dict[str, object],
        rewrite_preservation: dict[str, object],
    ) -> dict[str, object]:
        strategy = deepcopy(original_strategy if isinstance(original_strategy, dict) else {})
        metadata = rewritten_payload.get("metadata") if isinstance(rewritten_payload.get("metadata"), dict) else {}
        headline = AIOrchestratorService._normalize_metadata_text(rewritten_payload.get("headline"), limit=160)
        body = AIOrchestratorService._normalize_metadata_text(rewritten_payload.get("body"), limit=220)
        cta = AIOrchestratorService._normalize_metadata_text(rewritten_payload.get("cta"), limit=90)
        supporting_line = AIOrchestratorService._normalize_metadata_text(metadata.get("supporting_line"), limit=180)
        proof_points = AIOrchestratorService._normalize_metadata_list(metadata.get("proof_points"), limit=4)
        claim_evidence_pairs = AIOrchestratorService._normalize_claim_evidence_pairs(metadata.get("claim_evidence_pairs"), limit=3)
        angle_shift_detected = bool(rewrite_preservation.get("angle_shift_detected"))

        if headline:
            strategy["headline_direction"] = headline
        if supporting_line or body:
            strategy["supporting_copy_direction"] = supporting_line or body
        if cta:
            strategy["cta_intent"] = cta

        if angle_shift_detected or not str(strategy.get("primary_campaign_theme") or "").strip():
            strategy["primary_campaign_theme"] = supporting_line or headline or body
        if angle_shift_detected or not str(strategy.get("core_audience_message") or "").strip():
            strategy["core_audience_message"] = body or supporting_line or headline
        if angle_shift_detected or not str(strategy.get("key_value_proposition") or "").strip():
            first_claim = next(
                (
                    AIOrchestratorService._normalize_metadata_text(pair.get("claim"), limit=160)
                    for pair in claim_evidence_pairs
                    if AIOrchestratorService._normalize_metadata_text(pair.get("claim"), limit=160)
                ),
                "",
            )
            strategy["key_value_proposition"] = first_claim or (proof_points[0] if proof_points else (supporting_line or body or headline))

        important_keywords = strategy.get("important_keywords")
        if not isinstance(important_keywords, list) or not important_keywords:
            strategy["important_keywords"] = sorted(
                cls._rewrite_context_tokens(headline, body, supporting_line, cta, limit=10)
            )
        return strategy

    def _rewrite_validation_report(
        self,
        *,
        tenant_id: UUID,
        brand_space_id: UUID,
        user_id: UUID,
        original: ContentVersion,
        studio_panel: dict[str, object],
        resolved_brand_context: dict[str, object],
        persona_context: dict[str, object],
        objective_context: dict[str, object],
        compiled_context: dict[str, Any],
        explainability_metadata: dict[str, object],
        session: ContentSession | None,
    ) -> dict[str, object]:
        scene_graph_payload = explainability_metadata.get("scene_graph")
        if not isinstance(scene_graph_payload, dict):
            return dict(
                explainability_metadata.get("validation_report")
                if isinstance(explainability_metadata.get("validation_report"), dict)
                else {}
            )

        creative_decision_payload = (
            explainability_metadata.get("creative_decision")
            if isinstance(explainability_metadata.get("creative_decision"), dict)
            else explainability_metadata.get("layout_decision")
            if isinstance(explainability_metadata.get("layout_decision"), dict)
            else {}
        )
        try:
            scene_graph = GenerationSceneGraph.model_validate(scene_graph_payload)
            creative_decision = CreativeDecisionPayload.model_validate(creative_decision_payload or {})
        except ValidationError:
            return dict(
                explainability_metadata.get("validation_report")
                if isinstance(explainability_metadata.get("validation_report"), dict)
                else {}
            )

        stored_reference_assets = explainability_metadata.get("selected_reference_images")
        reference_assets = [dict(item) for item in stored_reference_assets if isinstance(item, dict)] if isinstance(stored_reference_assets, list) else []
        logo_selection = explainability_metadata.get("logo_selection") if isinstance(explainability_metadata.get("logo_selection"), dict) else {}
        logo_candidates = explainability_metadata.get("logo_candidates") if isinstance(explainability_metadata.get("logo_candidates"), list) else []
        layout_decision = explainability_metadata.get("planning_hints") if isinstance(explainability_metadata.get("planning_hints"), dict) else {}
        request = AIOrchestrationRequest(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            user_id=user_id,
            prompt=self._source_prompt_for_rewrite(original),
            studio_panel=studio_panel,
            conversation_context=session.conversational_context if session else {},
            session_memory=explainability_metadata.get("session_memory") if isinstance(explainability_metadata.get("session_memory"), dict) else {},
            resolved_brand_context=resolved_brand_context,
            persona_context=persona_context,
            objective_context=objective_context,
            retrieved_knowledge={},
            format_family_plan=compiled_context.get("format_family_plan", {}) if isinstance(compiled_context, dict) else {},
            content_plan=compiled_context.get("content_plan", {}) if isinstance(compiled_context, dict) else {},
            visual_plan=compiled_context.get("visual_plan", {}) if isinstance(compiled_context, dict) else {},
            template_candidates=list((compiled_context.get("template_fit_brief", {}) or {}).get("template_candidates", []) or []),
            layout_decision=layout_decision,
            reference_assets=reference_assets,
            asset_catalog=reference_assets,
            logo_asset_path=str(logo_selection.get("storage_path") or "").strip() or None,
            logo_asset_candidates=[dict(item) for item in logo_candidates if isinstance(item, dict)],
            platform_constraints={
                "platform_preset": studio_panel.get("platform_preset"),
                "format": studio_panel.get("format"),
                "file_type": studio_panel.get("file_type"),
                "size": studio_panel.get("size") or {},
            },
            resolution_policy=resolved_brand_context.get("context_priority", {}) if isinstance(resolved_brand_context, dict) else {},
            generate_image=False,
        )
        report = self.orchestrator.validate_scene_graph(
            scene_graph=scene_graph,
            creative_decision=creative_decision,
            request=request,
            compiled_context=compiled_context,
        )
        return report.model_dump(mode="json")

    @classmethod
    def _rewrite_blueprint_payload(
        cls,
        *,
        original: ContentVersion,
        payload: dict[str, object],
        explainability_metadata: dict[str, object],
        studio_panel: dict[str, object],
        resolved_brand_context: dict[str, object],
    ) -> dict[str, object]:
        scene_graph_payload = explainability_metadata.get("scene_graph")
        if isinstance(scene_graph_payload, dict):
            try:
                scene_graph = GenerationSceneGraph.model_validate(scene_graph_payload)
                blueprint = BlueprintService().from_scene_graph(
                    scene_graph=scene_graph,
                    studio_panel=studio_panel,
                    text_payload=payload,
                    brand_rules_applied=BlueprintService._brand_rules_applied(resolved_brand_context),
                )
                return blueprint.model_dump(mode="json")
            except ValidationError:
                pass

        stored_blueprint = getattr(original, "blueprint_payload", None)
        if isinstance(stored_blueprint, dict) and stored_blueprint:
            blueprint_payload = deepcopy(stored_blueprint)
            blueprint_payload["text_blocks"] = [
                {"role": "headline", "text": str(payload.get("headline") or "")},
                {"role": "body", "text": str(payload.get("body") or "")},
                {"role": "cta", "text": str(payload.get("cta") or "")},
            ]
            return blueprint_payload

        blueprint = BlueprintService().build(
            text_payload=payload,
            studio_panel=studio_panel,
            layout_decision=(
                explainability_metadata.get("creative_decision")
                if isinstance(explainability_metadata.get("creative_decision"), dict)
                else explainability_metadata.get("layout_decision")
                if isinstance(explainability_metadata.get("layout_decision"), dict)
                else {}
            ),
            brand_context=resolved_brand_context,
        )
        return blueprint.model_dump(mode="json")

    async def _refresh_content_tone_feedback(
        self,
        *,
        tenant_id: UUID,
        brand_space_id: UUID,
        content: ContentVersion,
    ) -> None:
        brand = await self.brands.get(brand_space_id)
        if not brand:
            return
        personas = await self.personas.list_by_brand(brand_space_id, tenant_id)
        persona = next((item for item in personas if item.id == content.selected_persona_id), None)
        objectives = await self.objectives.list_by_brand(brand_space_id, tenant_id)
        objective = next((item for item in objectives if item.id == content.objective_id), None)
        explainability = content.explainability_metadata if isinstance(content.explainability_metadata, dict) else {}
        message_strategy = explainability.get("message_strategy") if isinstance(explainability.get("message_strategy"), dict) else {}
        payload = content.generated_payload if isinstance(content.generated_payload, dict) else {}
        tone_feedback = self.tone.evaluate(
            content=self._tone_check_content_string(payload),
            brand_context=brand.resolved_brand_context,
            persona_context=BrandIntelligenceService.persona_to_dict(persona),
            content_payload=payload,
            message_strategy=message_strategy,
            objective_context=BrandIntelligenceService.objective_to_dict(objective),
        )
        content.tone_feedback = tone_feedback
        content.tone_score = int(tone_feedback.get("score") or 0)

    @classmethod
    def _build_rewrite_prompt(cls, content: ContentVersion, rewrite_instruction: str) -> str:
        rewrite_payload = cls._rewrite_payload_for_prompt(content)
        rewrite_strategy = cls._rewrite_strategy_for_prompt(content)
        tone_feedback = cls._rewrite_tone_feedback_for_prompt(content)
        rewrite_field_plan = cls._rewrite_field_plan_for_prompt(content)
        original_prompt = str(content.prompt or "").strip()
        return (
            "Rewrite the existing structured content for the same campaign surface. "
            "This is an edit task, not a fresh campaign brief.\n"
            f"Original user prompt: {original_prompt}\n"
            f"Rewrite instruction: {rewrite_instruction}\n"
            "Current structured content:\n"
            f"{json.dumps(rewrite_payload, ensure_ascii=True)}\n"
            "Current message strategy and QA context:\n"
            f"{json.dumps(rewrite_strategy, ensure_ascii=True)}\n"
            "Current tone QA:\n"
            f"{json.dumps(tone_feedback, ensure_ascii=True)}\n"
            "Field rewrite plan:\n"
            f"{json.dumps(rewrite_field_plan, ensure_ascii=True)}\n"
            "Rewrite requirements:\n"
            "- Keep the same core topic, audience, brand intent, and CTA intent unless the instruction explicitly changes them.\n"
            "- Rewrite the existing content; do not invent a new campaign angle unless the instruction explicitly asks for one.\n"
            "- Apply the field rewrite plan intentionally: treat headline, body, CTA, and persuasion metadata as separate jobs, not as one blur of copy polish.\n"
            "- Improve persuasion, not just wording polish: strengthen the opening hook, clarify the value proposition, tighten objection handling, and keep or upgrade trust builders and claim/evidence support.\n"
            "- Preserve every must_preserve item from the field rewrite plan unless the instruction explicitly removes or replaces it.\n"
            "- If the current copy feels vague, repetitive, or proof-light, make it more concrete and differentiated without inventing unsupported claims.\n"
            "- Return rewritten structured content suitable for the same platform and layout constraints."
        )

    @staticmethod
    def _knowledge_asset_payload(asset) -> dict:
        metadata = dict(asset.metadata_json or {})
        structured = asset.structured_data_json if isinstance(asset.structured_data_json, dict) else {}
        normalized = asset.normalized_data_json if isinstance(asset.normalized_data_json, dict) else {}
        curated_reference_keys = (
            "sequence_kind",
            "narrative_pattern",
            "sequence_summary",
            "sample_usage",
            "structural_cues",
            "sequence_cues",
            "slide_pattern",
            "page_pattern",
            "headline_hint",
            "headline",
            "slide_title",
            "page_title",
            "story_outline",
            "outline",
            "slides",
            "pages",
            "sequence_blueprint",
            "sample_blueprint",
            "carousel_blueprint",
            "reference_blueprint",
            "story_blueprint",
            "summary",
            "label",
            "format_family",
            "editorial_dna",
            "layout_dna",
            "composition_logic",
            "visual_craft",
            "subject_semantics",
            "family_name",
            "sequence_family",
            "slide_index",
            "page_index",
            "page_number",
            "reference_slide_index",
            "reference_slide_count",
        )
        for source in (normalized, structured):
            for key in curated_reference_keys:
                value = source.get(key)
                if value not in (None, "", [], {}):
                    metadata.setdefault(key, value)
        if asset.page_count and not metadata.get("page_count"):
            metadata["page_count"] = asset.page_count
        payload = {
            "asset_id": str(asset.id),
            "asset_role": asset.metadata_json.get("asset_role", asset.channel),
            "mime_type": asset.mime_type,
            "storage_path": asset.storage_path,
            "metadata": metadata,
            "validation_state": asset.validation_state,
            "trust_level": ContentService._trust_level_for_validation_state(asset.validation_state),
        }
        return ContentService._enrich_reference_asset_payload(payload)

    @staticmethod
    def _reusable_asset_payload(asset: dict[str, object]) -> dict[str, object]:
        review_status = str(asset.get("review_status") or "reference_only")
        review_class = str(asset.get("review_class") or asset.get("asset_kind") or "fragment")
        return {
            "asset_id": str(asset.get("id", "")),
            "asset_role": str(asset.get("asset_kind", "decorative_asset")),
            "mime_type": str(asset.get("mime_type", "image/png")),
            "storage_path": str(asset.get("storage_path", "")),
            "asset_url": AssetDeliveryService().build_signed_url(
                storage_path=str(asset.get("storage_path", "")),
                filename=str(asset.get("storage_path", "")).rsplit("/", 1)[-1] if str(asset.get("storage_path", "")).strip() else None,
            ) if str(asset.get("storage_path", "")).strip() else None,
            "metadata": {
                "label": asset.get("label"),
                "source_asset_id": asset.get("source_asset_id"),
                "source_metadata": asset.get("source_metadata", {}),
                "normalized_metadata": asset.get("normalized_metadata", {}),
                "review_class": review_class,
                "review_status": review_status,
                "review_reason": asset.get("review_reason"),
            },
            "validation_state": "clean" if asset.get("trust_level") == "trusted" and review_status == "approved" else "warning",
            "trust_level": asset.get("trust_level", "reference_only"),
        }

    @staticmethod
    def _trust_level_for_validation_state(validation_state: str | None) -> str:
        normalized = str(validation_state or "pending").lower()
        if normalized == "clean":
            return "trusted"
        if normalized == "warning":
            return "usable_with_warning"
        if normalized == "excluded":
            return "excluded"
        return "reference_only"

    def _decorate_asset_reference(self, asset: dict | None) -> dict | None:
        if not isinstance(asset, dict):
            return asset
        storage_path = str(asset.get("storage_path", "")).strip()
        if not storage_path or asset.get("asset_url"):
            return asset
        return {
            **asset,
            "asset_url": self.asset_delivery.build_signed_url(
                storage_path=storage_path,
                filename=storage_path.rsplit("/", 1)[-1],
            ),
        }

    @classmethod
    def _normalize_topic_token(cls, token: str) -> str:
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
        return text if text and text not in cls.TOPIC_STOPWORDS else ""

    @classmethod
    def _topic_tokens(cls, value: object, *, limit: int = 8) -> set[str]:
        words = re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", str(value or ""))
        tokens: list[str] = []
        for word in words:
            normalized = cls._normalize_topic_token(word)
            if not normalized or normalized in tokens:
                continue
            tokens.append(normalized)
            if len(tokens) >= limit:
                break
        return set(tokens)

    @classmethod
    def _asset_topic_label(cls, asset: dict[str, object]) -> str:
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        source_metadata = metadata.get("source_metadata") if isinstance(metadata.get("source_metadata"), dict) else {}
        normalized_metadata = metadata.get("normalized_metadata") if isinstance(metadata.get("normalized_metadata"), dict) else {}
        storage_name = Path(str(asset.get("storage_path") or "")).stem
        parts = [
            asset.get("asset_role"),
            metadata.get("label"),
            metadata.get("review_class"),
            metadata.get("review_reason"),
            source_metadata.get("label"),
            source_metadata.get("name"),
            normalized_metadata.get("label"),
            storage_name,
        ]
        return " ".join(str(part).strip() for part in parts if str(part or "").strip())

    @classmethod
    def _prompt_requests_uploaded_sample_authority(cls, prompt: str) -> bool:
        text = str(prompt or "").casefold()
        if "uploaded sample" not in text and "uploaded retirement sample" not in text:
            return False
        authority_markers = (
            "primary composition reference",
            "primary storytelling reference",
            "match the uploaded sample",
            "same family as the uploaded sample",
            "preserve its premium feel",
            "follow the uploaded sample",
            "use the uploaded",
        )
        return any(marker in text for marker in authority_markers)

    @classmethod
    def _prompt_requests_uploaded_sample_only(cls, prompt: str) -> bool:
        text = str(prompt or "").casefold()
        strict_markers = (
            "uploaded sample only",
            "uploaded retirement sample only",
            "only as a layout/style/composition reference",
            "only as a layout reference",
            "only as a style reference",
            "do not drift into generic",
        )
        return any(marker in text for marker in strict_markers)

    @classmethod
    def _authoritative_request_reference_assets(
        cls,
        request_assets: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        authoritative: list[dict[str, object]] = []
        for asset in request_assets:
            role = str(asset.get("asset_role") or "").strip().casefold()
            if role in {"reference_creative", "template", "template_preview", "image", "photo", "hero_image"}:
                authoritative.append(asset)
                continue
            metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            if any(
                metadata.get(key)
                for key in (
                    "sequence_blueprint",
                    "sample_blueprint",
                    "carousel_blueprint",
                    "reference_blueprint",
                    "story_blueprint",
                    "slides",
                    "pages",
                    "story_outline",
                    "outline",
                )
            ):
                authoritative.append(asset)
        return authoritative or list(request_assets)

    @staticmethod
    def _normalize_recommendation_format_family(value: Any) -> str | None:
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
    def _infer_reference_asset_format_family(cls, asset: dict[str, Any]) -> str | None:
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        editorial_dna = metadata.get("editorial_dna") if isinstance(metadata.get("editorial_dna"), dict) else {}
        normalized_metadata = metadata.get("normalized_metadata") if isinstance(metadata.get("normalized_metadata"), dict) else {}
        normalized_editorial_dna = (
            normalized_metadata.get("editorial_dna")
            if isinstance(normalized_metadata.get("editorial_dna"), dict)
            else {}
        )
        for candidate in (
            asset.get("format_family"),
            metadata.get("format_family"),
            metadata.get("surface_format"),
            metadata.get("content_format"),
            editorial_dna.get("format_family"),
            normalized_metadata.get("format_family"),
            normalized_editorial_dna.get("format_family"),
        ):
            normalized = cls._normalize_recommendation_format_family(candidate)
            if normalized:
                return normalized

        probe = {
            **dict(asset),
            "metadata": metadata,
        }
        if cls._sequence_source_is_carousel_capable(probe):
            return "carousel"

        combined_text = " ".join(
            str(part or "").strip()
            for part in (
                metadata.get("summary"),
                metadata.get("label"),
                metadata.get("sequence_summary"),
                metadata.get("narrative_pattern"),
                metadata.get("sequence_kind"),
                metadata.get("source_filename"),
                asset.get("storage_path"),
            )
            if str(part or "").strip()
        ).casefold()
        if any(token in combined_text for token in ("infographic", "explainer board", "data card", "section stack", "comparison card")):
            return "infographic"
        if any(token in combined_text for token in ("static", "poster", "single post", "single-page", "thumbnail")):
            return "static"
        return None

    @classmethod
    def _enrich_reference_asset_payload(cls, asset: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(asset, dict):
            return {}
        payload = dict(asset)
        metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), dict) else {}
        editorial_dna = dict(metadata.get("editorial_dna") or {}) if isinstance(metadata.get("editorial_dna"), dict) else {}

        signature = cls._sequence_source_signature({**payload, "metadata": metadata})
        if signature is not None:
            family_key, position = signature
            metadata.setdefault("sequence_family", family_key)
            metadata.setdefault("family_name", family_key)
            metadata.setdefault("slide_index", position)
            metadata.setdefault("reference_slide_index", position)

        format_family = cls._infer_reference_asset_format_family({**payload, "metadata": metadata})
        if format_family:
            payload["format_family"] = format_family
            metadata.setdefault("format_family", format_family)
            editorial_dna.setdefault("format_family", format_family)

        if metadata.get("page_count") is None:
            declared_page_count = cls._sequence_pack_declared_page_count({**payload, "metadata": metadata})
            if declared_page_count > 0:
                metadata["page_count"] = declared_page_count

        if editorial_dna:
            metadata["editorial_dna"] = editorial_dna
        payload["metadata"] = metadata
        return payload

    @classmethod
    def _requested_template_format_family(cls, studio_panel: dict[str, Any] | None) -> str | None:
        return cls._normalize_recommendation_format_family((studio_panel or {}).get("format"))

    @classmethod
    def _template_recommendation_format_family(cls, recommendation: object) -> str | None:
        payload = recommendation.model_dump(mode="json") if hasattr(recommendation, "model_dump") else dict(recommendation)
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        explicit = cls._normalize_recommendation_format_family(metadata.get("format_family"))
        if explicit:
            return explicit
        for candidate in (
            metadata.get("layout_type"),
            metadata.get("kind"),
            payload.get("kind"),
        ):
            normalized = cls._normalize_recommendation_format_family(candidate)
            if normalized:
                return normalized
        page_count = metadata.get("page_count")
        try:
            if int(page_count or 0) >= 3:
                return "carousel"
        except (TypeError, ValueError):
            pass
        return None

    @classmethod
    def _template_recommendation_adaptation_score(cls, recommendation: object) -> float:
        payload = recommendation.model_dump(mode="json") if hasattr(recommendation, "model_dump") else dict(recommendation)
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        try:
            return float(metadata.get("adaptation_score") or payload.get("score") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _sort_template_recommendations_for_format(
        cls,
        recommendations: list[object],
        *,
        studio_panel: dict[str, Any] | None,
    ) -> list[object]:
        requested_format_family = cls._requested_template_format_family(studio_panel)
        if not recommendations:
            return []

        def _rank(item: object) -> tuple[int, float, float]:
            payload = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
            try:
                score = float(payload.get("score") or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            family = cls._template_recommendation_format_family(item)
            return (
                1 if requested_format_family and family == requested_format_family else 0,
                cls._template_recommendation_adaptation_score(item),
                score,
            )

        return sorted(recommendations, key=_rank, reverse=True)

    @classmethod
    def _filter_reference_assets_for_studio_format(
        cls,
        assets: list[dict[str, object]],
        *,
        studio_panel: dict[str, Any] | None,
    ) -> list[dict[str, object]]:
        requested_format_family = cls._requested_template_format_family(studio_panel)
        if not requested_format_family:
            return [cls._enrich_reference_asset_payload(dict(asset)) for asset in assets if isinstance(asset, dict)]
        enriched_assets = [
            cls._enrich_reference_asset_payload(dict(asset))
            for asset in assets
            if isinstance(asset, dict)
        ]
        exact_matches = [
            asset
            for asset in enriched_assets
            if cls._normalize_recommendation_format_family(
                asset.get("format_family")
                or ((asset.get("metadata") or {}) if isinstance(asset.get("metadata"), dict) else {}).get("format_family")
            ) == requested_format_family
        ]
        return exact_matches or enriched_assets

    @classmethod
    def _collapse_carousel_template_recommendations(
        cls,
        recommendations: list[object],
        *,
        studio_panel: dict[str, Any] | None,
    ) -> list[object]:
        if cls._requested_template_format_family(studio_panel) != "carousel":
            return recommendations
        normalized: list[dict[str, Any]] = [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
            for item in recommendations
        ]
        family_members: dict[str, list[dict[str, Any]]] = {}
        for item in normalized:
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            family_key = str(
                item.get("recommendation_group_key")
                or metadata.get("sequence_family")
                or metadata.get("recommendation_group_key")
                or ""
            ).strip()
            if not family_key:
                signature = cls._sequence_pack_signature(item.get("name"))
                if signature is not None:
                    family_key = signature[0]
            if str(item.get("format_family") or metadata.get("format_family") or "").strip().lower() == "carousel" and family_key:
                family_members.setdefault(family_key, []).append(item)

        collapsed: list[dict[str, Any]] = []
        seen_families: set[str] = set()
        for item in normalized:
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            format_family = str(item.get("format_family") or metadata.get("format_family") or "").strip().lower()
            family_key = str(
                item.get("recommendation_group_key")
                or metadata.get("sequence_family")
                or metadata.get("recommendation_group_key")
                or ""
            ).strip()
            if not family_key:
                signature = cls._sequence_pack_signature(item.get("name"))
                if signature is not None:
                    family_key = signature[0]
            if format_family != "carousel" or not family_key:
                collapsed.append(item)
                continue
            if family_key in seen_families:
                continue
            seen_families.add(family_key)
            members = family_members.get(family_key, [item])

            def _position(member: dict[str, Any]) -> int:
                member_metadata = member.get("metadata") if isinstance(member.get("metadata"), dict) else {}
                try:
                    return int(member_metadata.get("sequence_position") or 0)
                except (TypeError, ValueError):
                    return 0

            def _adaptation(member: dict[str, Any]) -> float:
                member_metadata = member.get("metadata") if isinstance(member.get("metadata"), dict) else {}
                try:
                    return float(member_metadata.get("adaptation_score") or member.get("score") or 0.0)
                except (TypeError, ValueError):
                    return 0.0

            representative = next((member for member in members if _position(member) == 1), max(members, key=_adaptation))
            representative_metadata = dict(representative.get("metadata") or {})
            family_display_name = str(representative.get("display_name") or representative_metadata.get("family_display_name") or representative.get("name") or "").strip()
            representative_metadata["family_member_count"] = len(members)
            representative_metadata["family_slide_count"] = max(len(members), max((_position(member) for member in members), default=0))
            representative_metadata["group_type"] = "carousel_family"
            representative["display_name"] = family_display_name
            representative["recommendation_group_key"] = family_key
            representative["metadata"] = representative_metadata
            collapsed.append(representative)
        return collapsed

    @classmethod
    def _annotate_template_recommendation_selection(
        cls,
        recommendations: list[object],
        *,
        studio_panel: dict[str, Any] | None,
    ) -> list[object]:
        requested_format_family = cls._requested_template_format_family(studio_panel)
        fallback_reason = {
            "carousel": "Carousel Match",
            "infographic": "Infographic Match",
            "static": "Static Match",
        }.get(requested_format_family, "Suggested Match")
        annotated: list[dict[str, Any]] = []
        for index, recommendation in enumerate(recommendations):
            payload = recommendation.model_dump(mode="json") if hasattr(recommendation, "model_dump") else dict(recommendation)
            payload["is_primary_adaptation"] = index == 0
            payload["selection_reason"] = "Best Adaptation" if index == 0 else str(payload.get("selection_reason") or "").strip() or fallback_reason
            if not payload.get("format_family"):
                metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
                payload["format_family"] = cls._template_recommendation_format_family(payload) or metadata.get("format_family")
            annotated.append(payload)
        return annotated

    @classmethod
    def _filter_template_recommendations_for_studio_format(
        cls,
        recommendations: list[object],
        *,
        studio_panel: dict[str, Any] | None,
    ) -> list[object]:
        requested_format_family = cls._requested_template_format_family(studio_panel)
        if not requested_format_family:
            return recommendations
        exact_matches = [
            recommendation
            for recommendation in recommendations
            if cls._template_recommendation_format_family(recommendation) == requested_format_family
        ]
        return exact_matches or recommendations

    @classmethod
    def _request_asset_template_recommendations(
        cls,
        request_assets: list[dict[str, object]],
        *,
        strict_sample_only: bool,
    ) -> list[dict[str, object]]:
        recommendations: list[dict[str, object]] = []
        for index, asset in enumerate(request_assets):
            if not isinstance(asset, dict):
                continue
            label = cls._asset_topic_label(asset)
            metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            storage_path = str(asset.get("storage_path") or "").strip()
            name = (
                str(metadata.get("label") or "").strip()
                or str(metadata.get("headline") or "").strip()
                or Path(storage_path).stem
                or f"uploaded-reference-{index + 1}"
            )
            page_count = metadata.get("page_count")
            try:
                page_count_value = int(page_count or 0)
            except (TypeError, ValueError):
                page_count_value = 0
            format_family = cls._normalize_recommendation_format_family(
                metadata.get("format_family")
                or metadata.get("layout_type")
                or ("carousel" if page_count_value >= 3 else None)
            ) or ("carousel" if page_count_value >= 3 else "static")
            recommendations.append(
                {
                    "template_id": None,
                    "name": name,
                    "score": 100.0 - float(index),
                    "match_type": "adapted_template",
                    "decision_confidence": 1.0,
                    "reasons": [
                        "explicit uploaded-sample authority request",
                        "using request-supplied reference asset as the primary planning anchor",
                    ],
                    "score_breakdown": {
                        "keyword_overlap": 10.0,
                        "ocr_text_fit": 10.0,
                        "platform_fit": 4.0,
                        "export_fit": 2.0,
                        "format_fit": 2.0,
                        "brand_alignment": 5.0,
                        "asset_coverage": 4.0,
                        "content_structure": 8.0 if page_count_value >= 3 else 4.0,
                        "surface_safety": 2.0 if strict_sample_only else 1.0,
                    },
                    "adaptation_plan": {
                        "expand_headline_or_body": True,
                        "multi_section_flow": page_count_value >= 3,
                        "prefer_distinct_sections": page_count_value >= 3,
                        "use_reference_assets": True,
                        "fit_validation_required": True,
                        "reference_style_only": True,
                        "sample_authority": True,
                    },
                    "metadata": {
                        "kind": "reference_sample",
                        "tags": ["reference_creative", "uploaded_sample", "sample_authority"],
                        "supported_platforms": [],
                        "supported_exports": ["pdf", "png", "jpg", "doc"],
                        "editable_fields": [],
                        "format_family": format_family,
                        "adaptation_score": 200.0 - float(index),
                        "page_count": page_count_value,
                        "layout_type": metadata.get("layout_type"),
                        "surface_kind": metadata.get("surface_kind"),
                        "text_overlay_risk": metadata.get("text_overlay_risk"),
                        "overlay_safe": bool(metadata.get("overlay_safe", True)),
                        "label": label,
                    },
                    "source": "request_reference_asset",
                    "storage_path": storage_path,
                }
            )
        return recommendations

    @classmethod
    def _is_generic_reference_label(cls, label: str) -> bool:
        text = str(label or "").strip().casefold()
        if not text:
            return True
        if re.fullmatch(r"(img|image)[\s_-]*\d+", text):
            return True
        tokens = cls._topic_tokens(text, limit=12)
        if not tokens:
            return True
        return any(marker in text for marker in cls.GENERIC_REFERENCE_MARKERS)

    @classmethod
    def _filter_brand_reference_assets_for_prompt(
        cls,
        assets: list[dict[str, object]],
        *,
        prompt: str,
        follow_up_mode: str,
    ) -> list[dict[str, object]]:
        if str(follow_up_mode or "").strip().casefold() != "new_content":
            return assets
        prompt_tokens = cls._topic_tokens(prompt, limit=8)
        if not prompt_tokens:
            return assets
        filtered: list[dict[str, object]] = []
        for asset in assets:
            role = str(asset.get("asset_role") or "").strip().casefold()
            if role in {"logo", "logo_variant"}:
                filtered.append(asset)
                continue
            label = cls._asset_topic_label(asset)
            if cls._is_generic_reference_label(label):
                filtered.append(asset)
                continue
            if cls._topic_tokens(label, limit=8) & prompt_tokens:
                filtered.append(asset)
        return filtered or assets

    @classmethod
    def _merge_reference_assets_for_prompt(
        cls,
        *,
        prompt: str,
        request_reference_assets: list[dict[str, object]],
        brand_reference_assets: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        authoritative_request_assets = cls._authoritative_request_reference_assets(request_reference_assets)
        if not authoritative_request_assets:
            return [*brand_reference_assets, *request_reference_assets]

        if cls._prompt_requests_uploaded_sample_only(prompt):
            return list(authoritative_request_assets)

        if cls._prompt_requests_uploaded_sample_authority(prompt):
            seen: set[str] = set()
            merged: list[dict[str, object]] = []
            for asset in [*authoritative_request_assets, *brand_reference_assets]:
                storage_path = str(asset.get("storage_path") or "").strip()
                asset_id = str(asset.get("asset_id") or "").strip()
                dedupe_key = storage_path or asset_id
                if dedupe_key and dedupe_key in seen:
                    continue
                if dedupe_key:
                    seen.add(dedupe_key)
                merged.append(asset)
            return merged

        return [*brand_reference_assets, *request_reference_assets]

    @classmethod
    def _merge_template_recommendations_for_prompt(
        cls,
        *,
        prompt: str,
        request_reference_assets: list[dict[str, object]],
        template_recommendations: list[object],
    ) -> list[object]:
        authoritative_request_assets = cls._authoritative_request_reference_assets(request_reference_assets)
        if not authoritative_request_assets or not cls._prompt_requests_uploaded_sample_authority(prompt):
            return template_recommendations

        strict_sample_only = cls._prompt_requests_uploaded_sample_only(prompt)
        synthetic = cls._request_asset_template_recommendations(
            authoritative_request_assets,
            strict_sample_only=strict_sample_only,
        )
        return [*synthetic, *template_recommendations]

    @classmethod
    def _filter_template_recommendations_for_prompt(
        cls,
        recommendations: list[object],
        *,
        prompt: str,
        follow_up_mode: str,
        studio_panel: dict[str, Any] | None = None,
    ) -> list[object]:
        recommendations = cls._filter_template_recommendations_for_studio_format(
            recommendations,
            studio_panel=studio_panel,
        )
        if str(follow_up_mode or "").strip().casefold() != "new_content":
            return cls._sort_template_recommendations_for_format(
                recommendations,
                studio_panel=studio_panel,
            )
        prompt_tokens = cls._topic_tokens(prompt, limit=8)
        if not prompt_tokens:
            return cls._sort_template_recommendations_for_format(
                recommendations,
                studio_panel=studio_panel,
            )
        filtered: list[object] = []
        for recommendation in recommendations:
            payload = recommendation.model_dump(mode="json") if hasattr(recommendation, "model_dump") else dict(recommendation)
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            label = " ".join(
                str(part).strip()
                for part in [
                    payload.get("name"),
                    " ".join(str(tag).strip() for tag in metadata.get("tags", []) or []),
                ]
                if str(part or "").strip()
            )
            if cls._is_generic_reference_label(label):
                filtered.append(recommendation)
                continue
            if cls._topic_tokens(label, limit=10) & prompt_tokens:
                filtered.append(recommendation)
        return cls._sort_template_recommendations_for_format(
            filtered or recommendations,
            studio_panel=studio_panel,
        )

    @staticmethod
    def _parse_uuid_or_none(value: str | UUID | None) -> UUID | None:
        if not value:
            return None
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except ValueError:
            return None

    @classmethod
    def _effective_request_mode(
        cls,
        *,
        payload: ContentGenerateRequest,
        session_memory: dict[str, object] | None,
    ) -> str:
        explicit_mode = str(getattr(payload, "request_mode", "") or "").strip().casefold()
        if explicit_mode:
            return explicit_mode
        memory = session_memory or {}
        return str((memory.get("follow_up_intent") or {}).get("mode") or "").strip().casefold()

    @staticmethod
    def _inheritance_policy_value(payload: ContentGenerateRequest, field_name: str) -> bool | None:
        policy = getattr(payload, "inheritance_policy", None)
        if policy is None:
            return None
        if hasattr(policy, field_name):
            return getattr(policy, field_name)
        if isinstance(policy, dict):
            return policy.get(field_name)
        return None

    @classmethod
    def _should_inherit_generation_selection(
        cls,
        *,
        payload: ContentGenerateRequest,
        session_memory: dict[str, object] | None,
        field_name: str,
    ) -> bool:
        explicit_policy = cls._inheritance_policy_value(payload, field_name)
        if explicit_policy is not None:
            return bool(explicit_policy)
        effective_mode = cls._effective_request_mode(payload=payload, session_memory=session_memory)
        return effective_mode in {"modify_previous", "variant_of_previous"}

    @classmethod
    def _request_lineage_payload(
        cls,
        *,
        payload: ContentGenerateRequest,
        session_memory: dict[str, object] | None,
    ) -> dict[str, object]:
        return {
            "request_mode": cls._effective_request_mode(payload=payload, session_memory=session_memory),
            "source_content_version_id": str(getattr(payload, "source_content_version_id", None) or "").strip() or None,
            "inheritance_policy": {
                "inherit_persona": cls._should_inherit_generation_selection(payload=payload, session_memory=session_memory, field_name="inherit_persona"),
                "inherit_objective": cls._should_inherit_generation_selection(payload=payload, session_memory=session_memory, field_name="inherit_objective"),
                "inherit_template": cls._should_inherit_generation_selection(payload=payload, session_memory=session_memory, field_name="inherit_template"),
                "inherit_reference_assets": cls._should_inherit_generation_selection(payload=payload, session_memory=session_memory, field_name="inherit_reference_assets"),
                "inherit_copy_context": cls._should_inherit_generation_selection(payload=payload, session_memory=session_memory, field_name="inherit_copy_context"),
                "inherit_layout_context": cls._should_inherit_generation_selection(payload=payload, session_memory=session_memory, field_name="inherit_layout_context"),
            },
        }

    @classmethod
    def _request_prompt_lineage_payload(
        cls,
        *,
        payload: ContentGenerateRequest,
        session_memory: dict[str, object] | None,
    ) -> dict[str, object]:
        request_lineage = cls._request_lineage_payload(payload=payload, session_memory=session_memory)
        raw_user_prompt = str(getattr(payload, "raw_user_prompt", None) or payload.prompt or "").strip()
        effective_prompt = str(payload.prompt or "").strip()
        source_prompt_snapshot = str(getattr(payload, "source_prompt_snapshot", None) or raw_user_prompt or effective_prompt).strip()
        rewrite_instruction = str(getattr(payload, "rewrite_instruction", None) or "").strip()
        return {
            "user_prompt_raw": raw_user_prompt,
            "generation_prompt_effective": effective_prompt,
            "rewrite_instruction": rewrite_instruction,
            "source_prompt_snapshot": source_prompt_snapshot,
            "request_mode": request_lineage["request_mode"],
            "source_content_version_id": request_lineage["source_content_version_id"],
        }

    @classmethod
    def _sanitize_latest_content_for_request(
        cls,
        latest_content: dict[str, object],
        *,
        request_lineage: dict[str, object],
    ) -> dict[str, object]:
        sanitized = deepcopy(latest_content)
        inheritance_policy = request_lineage.get("inheritance_policy") if isinstance(request_lineage.get("inheritance_policy"), dict) else {}
        if not inheritance_policy.get("inherit_copy_context", False):
            sanitized["prompt"] = ""
            sanitized["headline"] = ""
            sanitized["body"] = ""
            sanitized["cta"] = ""
            sanitized["prompt_lineage"] = {
                **dict(sanitized.get("prompt_lineage") or {}),
                "user_prompt_raw": "",
                "generation_prompt_effective": "",
                "rewrite_instruction": "",
                "source_prompt_snapshot": "",
            }
        if not inheritance_policy.get("inherit_layout_context", False):
            sanitized["scene_graph"] = {}
            sanitized["generation_decision"] = {}
            sanitized["blueprint"] = {}
            sanitized["message_strategy"] = {}
        return sanitized

    @classmethod
    def _resolve_generation_selection_ids(
        cls,
        *,
        payload: ContentGenerateRequest,
        session_memory: dict[str, object] | None,
    ) -> tuple[str, UUID | None, UUID | None, UUID | None]:
        memory = session_memory or {}
        follow_up_mode = cls._effective_request_mode(payload=payload, session_memory=session_memory)
        inherited_persona_id = memory.get("inherited_persona_id")
        inherited_objective_id = memory.get("inherited_objective_id")
        inherited_template_id = memory.get("inherited_template_id")
        if not cls._should_inherit_generation_selection(
            payload=payload,
            session_memory=session_memory,
            field_name="inherit_persona",
        ):
            inherited_persona_id = None
        if not cls._should_inherit_generation_selection(
            payload=payload,
            session_memory=session_memory,
            field_name="inherit_objective",
        ):
            inherited_objective_id = None
        if not cls._should_inherit_generation_selection(
            payload=payload,
            session_memory=session_memory,
            field_name="inherit_template",
        ):
            inherited_template_id = None
        return (
            follow_up_mode,
            payload.persona_id or cls._parse_uuid_or_none(inherited_persona_id),
            payload.objective_id or cls._parse_uuid_or_none(inherited_objective_id),
            payload.template_id or cls._parse_uuid_or_none(inherited_template_id),
        )

    async def _apply_request_lineage(
        self,
        *,
        tenant_id: UUID,
        brand_space_id: UUID,
        payload: ContentGenerateRequest,
        session_memory: dict[str, object] | None,
    ) -> dict[str, object]:
        memory = deepcopy(session_memory or {})
        request_lineage = self._request_lineage_payload(payload=payload, session_memory=memory)
        follow_up_intent = dict(memory.get("follow_up_intent") or {})
        request_mode = str(request_lineage.get("request_mode") or "").strip()
        if request_mode:
            follow_up_intent["mode"] = request_mode
            follow_up_intent["uses_previous_output"] = request_mode in {"modify_previous", "variant_of_previous"}
        source_content_version_id = getattr(payload, "source_content_version_id", None)
        if source_content_version_id:
            follow_up_intent["source_content_version_id"] = str(source_content_version_id)
        memory["follow_up_intent"] = follow_up_intent
        memory["request_lineage"] = request_lineage

        if not self._should_inherit_generation_selection(
            payload=payload,
            session_memory=memory,
            field_name="inherit_persona",
        ):
            memory["inherited_persona_id"] = None
        if not self._should_inherit_generation_selection(
            payload=payload,
            session_memory=memory,
            field_name="inherit_objective",
        ):
            memory["inherited_objective_id"] = None
        if not self._should_inherit_generation_selection(
            payload=payload,
            session_memory=memory,
            field_name="inherit_template",
        ):
            memory["inherited_template_id"] = None

        if source_content_version_id:
            latest_content = memory.get("latest_content_version") if isinstance(memory.get("latest_content_version"), dict) else {}
            latest_id = self._parse_uuid_or_none(latest_content.get("id")) if latest_content else None
            if latest_id != source_content_version_id:
                source_content = await self.contents.get_scoped(source_content_version_id, tenant_id, brand_space_id)
                if source_content:
                    memory["latest_content_version"] = self._content_version_memory_payload(source_content)

        latest_content = memory.get("latest_content_version") if isinstance(memory.get("latest_content_version"), dict) else {}
        if latest_content:
            memory["latest_content_version"] = self._sanitize_latest_content_for_request(
                latest_content,
                request_lineage=request_lineage,
            )

        return memory

    @classmethod
    def _build_prompt_diagnostics(
        cls,
        *,
        prompt: str,
        session_memory: dict[str, object] | None,
    ) -> dict[str, object]:
        text = str(prompt or "").strip()
        memory = session_memory or {}
        latest_content = memory.get("latest_content_version") if isinstance(memory.get("latest_content_version"), dict) else {}
        recent_messages = memory.get("recent_messages") if isinstance(memory.get("recent_messages"), list) else []
        recent_user_messages = [
            str(message.get("message_text") or "").strip()
            for message in recent_messages
            if isinstance(message, dict) and str(message.get("role") or "").strip().casefold() == "user"
        ]
        latest_user_message = recent_user_messages[-1] if recent_user_messages else ""
        latest_content_prompt = str(
            ((latest_content.get("prompt_lineage") or {}) if isinstance(latest_content.get("prompt_lineage"), dict) else {}).get("user_prompt_raw")
            or latest_content.get("prompt")
            or ""
        ).strip()
        follow_up_intent = memory.get("follow_up_intent") if isinstance(memory.get("follow_up_intent"), dict) else {}
        return {
            "contains_regeneration_wrapper": "Revise the existing creative with this instruction:" in text,
            "wrapper_count": text.count("Revise the existing creative with this instruction:"),
            "starts_with_latest_content_prompt": bool(latest_content_prompt and text.startswith(latest_content_prompt)),
            "matches_latest_user_message": bool(latest_user_message and text == latest_user_message),
            "latest_user_message_excerpt": latest_user_message[:280],
            "latest_content_prompt_excerpt": latest_content_prompt[:280],
            "follow_up_intent": follow_up_intent,
        }

    @classmethod
    def _sanitize_prompt_for_request(
        cls,
        *,
        payload: ContentGenerateRequest,
        session_memory: dict[str, object] | None,
    ) -> tuple[str, dict[str, object]]:
        effective_prompt = str(payload.prompt or "").strip()
        raw_user_prompt = str(getattr(payload, "raw_user_prompt", None) or "").strip()
        request_mode = cls._effective_request_mode(payload=payload, session_memory=session_memory)
        diagnostics = cls._build_prompt_diagnostics(prompt=effective_prompt, session_memory=session_memory)
        contamination_signals: list[str] = []

        if request_mode == "new_content":
            if diagnostics.get("contains_regeneration_wrapper"):
                contamination_signals.append("contains_regeneration_wrapper")
            if diagnostics.get("starts_with_latest_content_prompt") and not diagnostics.get("matches_latest_user_message"):
                contamination_signals.append("starts_with_latest_content_prompt")
            if contamination_signals and raw_user_prompt:
                effective_prompt = raw_user_prompt

        return effective_prompt, {
            "request_mode": request_mode,
            "raw_user_prompt": raw_user_prompt,
            "effective_prompt_original": str(payload.prompt or "").strip(),
            "effective_prompt_sanitized": effective_prompt,
            "contamination_signals": contamination_signals,
            "diagnostics": diagnostics,
        }

    @staticmethod
    def _normalize_hex(value: str | None) -> str | None:
        text = str(value or "").strip().upper()
        if not text:
            return None
        if not text.startswith("#") and re.fullmatch(r"[0-9A-F]{6}", text):
            text = f"#{text}"
        return text if re.fullmatch(r"#[0-9A-F]{6}", text) else None

    @classmethod
    def _hex_to_rgb(cls, value: str | None) -> tuple[int, int, int] | None:
        normalized = cls._normalize_hex(value)
        if not normalized:
            return None
        normalized = normalized.lstrip("#")
        return tuple(int(normalized[index:index + 2], 16) for index in range(0, 6, 2))

    @classmethod
    def _brand_palette_roles(cls, brand_context: dict) -> dict[str, str]:
        visual_identity = brand_context.get("visual_identity", {}) or {}
        return derive_palette_roles(visual_identity)

    @classmethod
    def _desired_logo_variant(cls, brand_context: dict, studio_panel: dict | None) -> dict[str, str]:
        panel = resolve_studio_panel_defaults(deepcopy(studio_panel or {}))
        size = panel.get("size", {}) or {}
        width = int(size.get("width") or 1080)
        height = int(size.get("height") or 1080)
        aspect_ratio = width / max(height, 1)
        if aspect_ratio >= 1.35:
            orientation = "horizontal"
        elif aspect_ratio <= 0.82:
            orientation = "stacked"
        else:
            orientation = "flex"

        palette_roles = cls._brand_palette_roles(brand_context)
        background_hex = (
            palette_roles.get("background")
            or palette_roles.get("surface")
            or palette_roles.get("neutral")
            or "#FFFFFF"
        )
        background_rgb = cls._hex_to_rgb(background_hex) or (255, 255, 255)
        background_tone = "dark" if sum(background_rgb) <= 360 else "light"
        return {
            "orientation": orientation,
            "background_tone": background_tone,
        }

    @staticmethod
    def _logo_traits_from_metadata(storage_path: str, metadata: dict[str, object] | None) -> dict[str, object]:
        metadata = metadata or {}
        normalized_metadata = metadata.get("normalized_metadata") if isinstance(metadata.get("normalized_metadata"), dict) else {}
        normalized_data = metadata.get("normalized_data") if isinstance(metadata.get("normalized_data"), dict) else {}
        usage_hints = normalized_metadata.get("usage_hints") if isinstance(normalized_metadata.get("usage_hints"), dict) else {}
        variants = (
            usage_hints.get("variants")
            if isinstance(usage_hints.get("variants"), list)
            else normalized_data.get("variants")
            if isinstance(normalized_data.get("variants"), list)
            else metadata.get("variants")
        )
        primary_variant = variants[0] if isinstance(variants, list) and variants and isinstance(variants[0], dict) else {}
        text_blob = " ".join(
            str(part).strip().casefold()
            for part in [
                storage_path,
                metadata.get("variant"),
                metadata.get("logo_variant"),
                metadata.get("background_variant"),
                metadata.get("orientation"),
                metadata.get("layout_variant"),
                metadata.get("label"),
                metadata.get("name"),
                primary_variant.get("orientation"),
                primary_variant.get("background_variant"),
                " ".join(primary_variant.get("variant_tags", [])) if isinstance(primary_variant.get("variant_tags"), list) else "",
            ]
            if str(part or "").strip()
        )

        orientation = "flex"
        if any(token in text_blob for token in ("stacked", "vertical", "portrait", "square", "badge", "seal")):
            orientation = "stacked"
        if any(token in text_blob for token in ("horizontal", "wide", "landscape", "lockup", "wordmark")):
            orientation = "horizontal"
        if any(token in text_blob for token in ("icon", "mark", "monogram", "symbol", "emblem")):
            orientation = "icon"

        background_variant = None
        if any(token in text_blob for token in ("light", "white", "reverse", "inverse", "negative")):
            background_variant = "dark"
        elif any(token in text_blob for token in ("dark", "black", "navy", "blue", "color", "colour")):
            background_variant = "light"
        if not background_variant:
            background_variant = str(primary_variant.get("background_variant") or "") or None
        if orientation == "flex":
            orientation = str(primary_variant.get("orientation") or orientation) or "flex"

        return {
            "orientation": orientation,
            "background_variant": background_variant,
            "is_primary": any(token in text_blob for token in ("primary", "main", "default", "official", "master")),
            "is_alternate": any(token in text_blob for token in ("alt", "alternate", "secondary", "temp")),
        }

    @staticmethod
    def _normalize_logo_variant_hint(variant_hint: str | None) -> str:
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
            "wordmark": "horizontal",
            "compact": "icon_only",
            "icon only": "icon_only",
            "brandmark": "icon_only",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return re.sub(r"[^a-z0-9_]+", "_", text).strip("_")

    @classmethod
    def _score_logo_candidate(
        cls,
        candidate: dict[str, object],
        desired: dict[str, str],
        requested_variant: str | None = None,
    ) -> int:
        score = int(candidate.get("source_priority") or 0)
        traits = candidate.get("traits", {}) or {}
        orientation = str(traits.get("orientation") or "flex")
        background_variant = str(traits.get("background_variant") or "")
        background_tone = desired.get("background_tone")
        preferred_orientation = desired.get("orientation")
        trust_level = str(candidate.get("trust_level") or "").strip().lower()
        storage_path = str(candidate.get("storage_path") or "").strip().casefold()

        if trust_level == "excluded":
            return -10_000
        if trust_level == "trusted":
            score += 4
        elif trust_level in {"usable_with_warning", "usable-with-warning"}:
            score += 1

        if background_tone == "light":
            if background_variant == "light":
                score += 18
            elif background_variant == "dark":
                score -= 8
        elif background_tone == "dark":
            if background_variant == "dark":
                score += 18
            elif background_variant == "light":
                score -= 8

        if preferred_orientation == "horizontal":
            if orientation == "horizontal":
                score += 14
            elif orientation == "stacked":
                score -= 4
            elif orientation == "icon":
                score -= 6
        elif preferred_orientation == "stacked":
            if orientation == "stacked":
                score += 12
            elif orientation == "icon":
                score += 7
            elif orientation == "horizontal":
                score -= 5
        else:
            if orientation == "horizontal":
                score += 6
            elif orientation == "stacked":
                score += 4
            elif orientation == "icon":
                score += 2

        if traits.get("is_primary"):
            score += 6
        if traits.get("is_alternate"):
            score -= 2
        looks_logoish = cls._path_looks_like_logo(storage_path)
        if not looks_logoish:
            if orientation == "icon":
                score -= 18
            if str(candidate.get("source") or "").strip().lower() == "storage_discovery":
                score -= 12
        if storage_path.endswith(".svg"):
            score += 2
        elif storage_path.endswith(".png"):
            score += 1

        hint = cls._normalize_logo_variant_hint(requested_variant)
        if hint:
            if "dark_on_light" in hint:
                if background_variant == "light":
                    score += 20
                elif background_variant == "dark":
                    score -= 12
            if "light_on_dark" in hint:
                if background_variant == "dark":
                    score += 20
                elif background_variant == "light":
                    score -= 12
            if "horizontal" in hint:
                score += 16 if orientation == "horizontal" else -8
            if "stacked" in hint:
                score += 16 if orientation == "stacked" else -8
            if "icon_only" in hint:
                score += 14 if orientation == "icon" else -6
            if "wordmark" in hint or "lockup" in hint:
                score += 10 if orientation == "horizontal" else -4
        return score

    @staticmethod
    def _candidate_prefers_exact_logo_overlay(candidate: dict[str, object]) -> bool:
        storage_path = str(candidate.get("storage_path") or "").strip().casefold()
        source = str(candidate.get("source") or "").strip().casefold()
        traits = candidate.get("traits") if isinstance(candidate.get("traits"), dict) else {}
        metadata = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
        orientation = str(traits.get("orientation") or metadata.get("orientation") or "").strip().lower()
        asset_kind = str(metadata.get("asset_kind") or "").strip().lower()
        if orientation == "icon":
            return False
        if asset_kind == "logo_variant":
            return True
        if "/logo/" in storage_path or storage_path.startswith("logo/"):
            return True
        return source in {
            "identity.logo_asset_path",
            "identity.logo_assets",
            "generated_asset",
            "knowledge_asset",
            "knowledge_field_logo",
        }

    @staticmethod
    def _logo_mark_luminance(image: Image.Image) -> float:
        rgba = image.convert("RGBA")
        pixels = rgba.load()
        width, height = rgba.size
        luminance_total = 0.0
        weighted_pixels = 0.0
        step_x = max(width // 96, 1)
        step_y = max(height // 96, 1)
        for y in range(0, height, step_y):
            for x in range(0, width, step_x):
                red, green, blue, alpha = pixels[x, y]
                if alpha <= 16:
                    continue
                luminance_total += (0.2126 * red + 0.7152 * green + 0.0722 * blue) * (alpha / 255.0)
                weighted_pixels += alpha / 255.0
        if weighted_pixels <= 0:
            return 255.0
        return luminance_total / weighted_pixels

    @staticmethod
    def _logo_box_background_luminance(image: Image.Image, box: tuple[int, int, int, int]) -> float:
        x, y, width, height = box
        crop = image.crop((x, y, min(x + width, image.width), min(y + height, image.height))).convert("RGB")
        if crop.width <= 0 or crop.height <= 0:
            return 255.0
        sample = crop.resize((max(min(crop.width, 24), 1), max(min(crop.height, 24), 1)), Image.Resampling.BILINEAR)
        luminance_total = 0.0
        pixel_count = 0
        pixels = sample.load()
        for y in range(sample.height):
            for x in range(sample.width):
                red, green, blue = pixels[x, y]
                luminance_total += 0.2126 * red + 0.7152 * green + 0.0722 * blue
                pixel_count += 1
        if pixel_count <= 0:
            return 255.0
        return luminance_total / pixel_count

    @staticmethod
    def _expanded_logo_clearance_box(
        image: Image.Image,
        box: tuple[int, int, int, int],
        *,
        format_name: str | None = None,
    ) -> tuple[int, int, int, int]:
        x, y, width, height = box
        pad_x = max(int(width * 0.14), 12)
        pad_y = max(int(height * 0.2), 14)
        normalized_format = str(format_name or "").strip().lower()
        if normalized_format in {"carousel", "infographic"}:
            pad_x = max(pad_x, int(width * 0.22))
            pad_y = max(pad_y, int(height * 0.26))
        if y <= int(image.height * 0.12):
            pad_y = max(pad_y, int(height * 0.3))
        if (x + width) >= int(image.width * 0.88):
            pad_x = max(pad_x, int(width * 0.2))
        left_pad = pad_x
        right_pad = pad_x
        if y <= int(image.height * 0.14) and (x + width) >= int(image.width * 0.8):
            left_pad = max(left_pad, int(width * 0.7))
            right_pad = max(right_pad, int(width * 0.1))
            if normalized_format in {"carousel", "infographic"}:
                left_pad = max(left_pad, int(width * 1.75))
                right_pad = max(right_pad, int(width * 0.38))
                pad_y = max(pad_y, int(height * 1.1))
        left = max(int(x) - left_pad, 0)
        top = max(int(y) - pad_y, 0)
        right = min(int(x) + max(int(width), 1) + right_pad, image.width)
        bottom = min(int(y) + max(int(height), 1) + pad_y, image.height)
        return left, top, max(right - left, 1), max(bottom - top, 1)

    @staticmethod
    def _median_channel(values: list[int]) -> int:
        if not values:
            return 255
        ordered = sorted(values)
        return int(ordered[len(ordered) // 2])

    @staticmethod
    def _logo_clearance_anchor(
        image: Image.Image,
        clear_box: tuple[int, int, int, int],
    ) -> str:
        left, top, width, height = clear_box
        right = min(left + width, image.width)
        bottom = min(top + height, image.height)
        center_x = left + ((right - left) / 2.0)
        center_y = top + ((bottom - top) / 2.0)
        vertical = "top" if center_y <= (image.height * 0.34) else ("bottom" if center_y >= (image.height * 0.66) else "middle")
        horizontal = "left" if center_x <= (image.width * 0.34) else ("right" if center_x >= (image.width * 0.66) else "center")
        return f"{vertical}-{horizontal}"

    @classmethod
    def _sample_logo_clearance_color(
        cls,
        image: Image.Image,
        clear_box: tuple[int, int, int, int],
        *,
        anchor_hint: str | None = None,
    ) -> tuple[int, int, int, int]:
        rgba = image.convert("RGBA")
        left, top, width, height = clear_box
        right = min(left + width, rgba.width)
        bottom = min(top + height, rgba.height)
        anchor = str(anchor_hint or cls._logo_clearance_anchor(rgba, clear_box)).strip().lower()
        ring_pad = max(int(max(width, height) * 0.18), 18)
        sample_left = max(left - ring_pad, 0)
        sample_top = max(top - ring_pad, 0)
        sample_right = min(right + ring_pad, rgba.width)
        sample_bottom = min(bottom + ring_pad, rgba.height)
        sample_width = max(sample_right - sample_left, 1)
        sample_height = max(sample_bottom - sample_top, 1)
        step = max(max(sample_width, sample_height) // 56, 1)
        red_values: list[int] = []
        green_values: list[int] = []
        blue_values: list[int] = []
        alpha_values: list[int] = []
        for sample_y in range(sample_top, sample_bottom, step):
            for sample_x in range(sample_left, sample_right, step):
                if left <= sample_x < right and top <= sample_y < bottom:
                    continue
                if anchor == "top-right" and sample_x < left and sample_y >= top:
                    continue
                if anchor == "top-left" and sample_x >= right and sample_y >= top:
                    continue
                if anchor == "bottom-right" and sample_x < left and sample_y < bottom:
                    continue
                if anchor == "bottom-left" and sample_x >= right and sample_y < bottom:
                    continue
                red, green, blue, alpha = rgba.getpixel((sample_x, sample_y))
                if alpha <= 16:
                    continue
                red_values.append(red)
                green_values.append(green)
                blue_values.append(blue)
                alpha_values.append(alpha)
        if not red_values:
            return (255, 255, 255, 255)
        return (
            cls._median_channel(red_values),
            cls._median_channel(green_values),
            cls._median_channel(blue_values),
            255,
        )

    @classmethod
    def _synthesize_logo_clearance_patch(
        cls,
        image: Image.Image,
        clear_box: tuple[int, int, int, int],
        *,
        anchor_hint: str | None = None,
    ) -> Image.Image | None:
        rgba = image.convert("RGBA")
        left, top, width, height = clear_box
        right = min(left + width, rgba.width)
        bottom = min(top + height, rgba.height)
        anchor = str(anchor_hint or cls._logo_clearance_anchor(rgba, clear_box)).strip().lower()
        strip = max(int(min(width, height) * 0.22), 6)
        candidates: list[Image.Image] = []

        # For top-corner logo zones, prefer a stretched sample from the calm top band.
        # Blending in the left/right body strips can reintroduce the exact ghosted text
        # and shapes that the clearance pass is trying to remove.
        if anchor in {"top-right", "top-left", "top-center"} and top > 0:
            sample_top = max(top - strip, 0)
            if sample_top < top:
                return rgba.crop((left, sample_top, right, top)).resize((width, height), Image.Resampling.BILINEAR)

        if top > 0:
            sample_top = max(top - strip, 0)
            if sample_top < top:
                candidates.append(
                    rgba.crop((left, sample_top, right, top)).resize((width, height), Image.Resampling.BILINEAR)
                )
        if bottom < rgba.height:
            sample_bottom = min(bottom + strip, rgba.height)
            if bottom < sample_bottom:
                candidates.append(
                    rgba.crop((left, bottom, right, sample_bottom)).resize((width, height), Image.Resampling.BILINEAR)
                )
        if left > 0 and anchor not in {"top-right", "middle-right", "bottom-right"}:
            sample_left = max(left - strip, 0)
            if sample_left < left:
                candidates.append(
                    rgba.crop((sample_left, top, left, bottom)).resize((width, height), Image.Resampling.BILINEAR)
                )
        if right < rgba.width and anchor not in {"top-left", "middle-left", "bottom-left"}:
            sample_right = min(right + strip, rgba.width)
            if right < sample_right:
                candidates.append(
                    rgba.crop((right, top, sample_right, bottom)).resize((width, height), Image.Resampling.BILINEAR)
                )
        if not candidates:
            return None

        patch = candidates[0]
        for candidate in candidates[1:]:
            patch = Image.blend(patch, candidate, 0.5)
        return patch

    @staticmethod
    def _feathered_clearance_mask(
        width: int,
        height: int,
        *,
        anchor_hint: str | None = None,
    ) -> Image.Image:
        safe_width = max(int(width), 1)
        safe_height = max(int(height), 1)
        anchor = str(anchor_hint or "").strip().lower()
        # Top-corner logo regions need stronger interior cleanup because the AI often
        # paints ghosted wordmarks and text bands underneath. We still feather the
        # edges so the cleanup doesn't look like a hard white tile.
        if anchor.startswith("top-"):
            edge_x = max(int(safe_width * 0.12), 16)
            edge_top = max(int(safe_height * 0.08), 10)
            edge_bottom = max(int(safe_height * 0.22), 24)
        else:
            edge_x = max(int(safe_width * 0.14), 18)
            edge_top = max(int(safe_height * 0.12), 14)
            edge_bottom = max(int(safe_height * 0.16), 18)
        mask = Image.new("L", (safe_width, safe_height), 255)
        draw = ImageDraw.Draw(mask)
        draw.rectangle((0, 0, safe_width - 1, safe_height - 1), fill=255)
        # Blur a contracted inner rectangle back out to create a smooth transition.
        inner_left = min(edge_x, safe_width // 2)
        inner_top = min(edge_top, safe_height // 2)
        inner_right = max(safe_width - edge_x - 1, inner_left)
        inner_bottom = max(safe_height - edge_bottom - 1, inner_top)
        contracted = Image.new("L", (safe_width, safe_height), 0)
        ImageDraw.Draw(contracted).rounded_rectangle(
            (inner_left, inner_top, inner_right, inner_bottom),
            radius=max(min(safe_width, safe_height) // 10, 8),
            fill=255,
        )
        return contracted.filter(ImageFilter.GaussianBlur(radius=max(min(safe_width, safe_height) // 18, 6)))

    @classmethod
    def _clear_ai_logo_overlay_region(
        cls,
        image: Image.Image,
        box: tuple[int, int, int, int],
        *,
        format_name: str | None = None,
    ) -> tuple[Image.Image, bool]:
        if image.width <= 0 or image.height <= 0:
            return image, False
        left, top, width, height = cls._expanded_logo_clearance_box(image, box, format_name=format_name)
        right = min(left + width, image.width)
        bottom = min(top + height, image.height)
        if right <= left or bottom <= top:
            return image, False
        cleared = image.convert("RGBA").copy()
        anchor = cls._logo_clearance_anchor(cleared, (left, top, right - left, bottom - top))
        patch = cls._synthesize_logo_clearance_patch(
            cleared,
            (left, top, right - left, bottom - top),
            anchor_hint=anchor,
        )
        original_region = cleared.crop((left, top, right, bottom))
        if patch is not None:
            mask = cls._feathered_clearance_mask(patch.width, patch.height, anchor_hint=anchor)
            blended = Image.composite(patch, original_region, mask)
            cleared.alpha_composite(blended, (left, top))
        else:
            fill = cls._sample_logo_clearance_color(
                cleared,
                (left, top, right - left, bottom - top),
                anchor_hint=anchor,
            )
            fill_region = Image.new("RGBA", (right - left, bottom - top), fill)
            mask = cls._feathered_clearance_mask(fill_region.width, fill_region.height, anchor_hint=anchor)
            blended = Image.composite(fill_region, original_region, mask)
            cleared.alpha_composite(blended, (left, top))
        return cleared, True

    @classmethod
    def _trim_transparent_logo_margins(cls, image: Image.Image) -> Image.Image:
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        bbox = alpha.getbbox()
        if not bbox:
            return rgba
        left, top, right, bottom = bbox
        if left == 0 and top == 0 and right == rgba.width and bottom == rgba.height:
            return rgba
        return rgba.crop(bbox)

    @staticmethod
    def _logo_footprint_clearance_box(
        *,
        image: Image.Image,
        offset_x: int,
        offset_y: int,
        logo_width: int,
        logo_height: int,
    ) -> tuple[int, int, int, int]:
        safe_logo_width = max(int(logo_width), 1)
        safe_logo_height = max(int(logo_height), 1)
        halo_x = max(int(safe_logo_width * 0.08), 6)
        halo_y = max(int(safe_logo_height * 0.12), 6)
        left = max(int(offset_x) - halo_x, 0)
        top = max(int(offset_y) - halo_y, 0)
        right = min(int(offset_x) + safe_logo_width + halo_x, image.width)
        bottom = min(int(offset_y) + safe_logo_height + halo_y, image.height)
        return left, top, max(right - left, 1), max(bottom - top, 1)

    @classmethod
    def _clear_ai_logo_footprint_region(
        cls,
        image: Image.Image,
        *,
        logo_image: Image.Image,
        offset_x: int,
        offset_y: int,
        clear_box: tuple[int, int, int, int],
    ) -> tuple[Image.Image, bool]:
        left, top, width, height = clear_box
        right = min(left + width, image.width)
        bottom = min(top + height, image.height)
        if right <= left or bottom <= top:
            return image, False

        logo_rgba = logo_image.convert("RGBA")
        alpha = logo_rgba.getchannel("A")
        if alpha.getbbox() is None:
            return image, False

        cleared = image.convert("RGBA").copy()
        anchor = cls._logo_clearance_anchor(cleared, (left, top, right - left, bottom - top))
        patch = cls._synthesize_logo_clearance_patch(
            cleared,
            (left, top, right - left, bottom - top),
            anchor_hint=anchor,
        )
        original_region = cleared.crop((left, top, right, bottom))
        if patch is None:
            fill = cls._sample_logo_clearance_color(
                cleared,
                (left, top, right - left, bottom - top),
                anchor_hint=anchor,
            )
            patch = Image.new("RGBA", (right - left, bottom - top), fill)

        footprint_mask = Image.new("L", (right - left, bottom - top), 0)
        logo_left = max(int(offset_x) - left, 0)
        logo_top = max(int(offset_y) - top, 0)
        binary_alpha = alpha.point(lambda value: 255 if value > 8 else 0)
        footprint_mask.paste(binary_alpha, (logo_left, logo_top))

        halo = max(min(max(logo_rgba.width, logo_rgba.height) // 14, 18), 6)
        max_filter_size = max((halo * 2) - 1, 3)
        if max_filter_size % 2 == 0:
            max_filter_size += 1
        expanded_mask = footprint_mask.filter(ImageFilter.MaxFilter(size=max_filter_size))
        feather_radius = max(min(halo // 2, 8), 3)
        softened_mask = expanded_mask.filter(ImageFilter.GaussianBlur(radius=feather_radius))

        blended = Image.composite(patch, original_region, softened_mask)
        cleared.alpha_composite(blended, (left, top))
        return cleared, True

    def _select_logo_overlay_candidate(
        self,
        *,
        base_image: Image.Image,
        logo_box: tuple[int, int, int, int],
        current_logo_asset_path: str | None,
        logo_asset_candidates: list[dict[str, object]] | None,
        logo_selection: dict[str, object] | None,
    ) -> dict[str, object] | None:
        available_candidates = list(logo_asset_candidates or [])
        if logo_selection and isinstance(logo_selection, dict):
            selected_path = str(logo_selection.get("storage_path") or "").strip()
            if selected_path and not any(str(item.get("storage_path") or "").strip() == selected_path for item in available_candidates):
                available_candidates.append(dict(logo_selection))
        if current_logo_asset_path and not any(
            str(item.get("storage_path") or "").strip() == current_logo_asset_path for item in available_candidates
        ):
            available_candidates.append(
                {
                    "storage_path": current_logo_asset_path,
                    "source": "selected_logo_asset_path",
                    "source_priority": 25,
                    "metadata": {},
                    "traits": {},
                }
            )
        if not available_candidates:
            return None

        background_luminance = self._logo_box_background_luminance(base_image, logo_box)
        preferred_light_mark = background_luminance <= 150
        scored: list[tuple[float, dict[str, object]]] = []
        for candidate in available_candidates:
            storage_path = str(candidate.get("storage_path") or "").strip()
            if not storage_path or not self.storage.exists(storage_path):
                continue
            if not self._candidate_prefers_exact_logo_overlay(candidate):
                continue
            try:
                with open_image_asset(self.storage.absolute_path(storage_path)) as raw_logo:
                    prepared_logo = self._trim_transparent_logo_margins(
                        self._strip_logo_background_if_safe(raw_logo.convert("RGBA"))
                    )
            except OSError:
                continue
            mark_luminance = self._logo_mark_luminance(prepared_logo)
            contrast_score = abs(mark_luminance - background_luminance)
            traits = candidate.get("traits") if isinstance(candidate.get("traits"), dict) else {}
            background_variant = str(traits.get("background_variant") or "").strip().lower()
            overlay_score = float(candidate.get("score") or candidate.get("source_priority") or 0)
            if preferred_light_mark:
                if mark_luminance >= 170:
                    overlay_score += 36
                elif mark_luminance <= 110:
                    overlay_score -= 22
                if background_variant == "dark":
                    overlay_score += 18
                elif background_variant == "light":
                    overlay_score -= 10
            else:
                if mark_luminance <= 120:
                    overlay_score += 36
                elif mark_luminance >= 190:
                    overlay_score -= 18
                if background_variant == "light":
                    overlay_score += 18
                elif background_variant == "dark":
                    overlay_score -= 10
            if storage_path.casefold() == str(current_logo_asset_path or "").strip().casefold():
                overlay_score += 4
            if "/logo/" in storage_path.casefold():
                overlay_score += 4
            if "derived-assets/" in storage_path.casefold():
                overlay_score -= 4
            overlay_score += contrast_score / 6.0
            scored.append((overlay_score, {**candidate, "storage_path": storage_path, "mark_luminance": mark_luminance}))

        if not scored:
            return None
        scored.sort(key=lambda item: (item[0], str(item[1].get("storage_path") or "")), reverse=True)
        return scored[0][1]

    async def _collect_logo_asset_candidates(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        brand_context: dict,
    ) -> list[dict[str, object]]:
        identity = brand_context.get("identity", {}) or {}
        candidate_map: dict[str, dict[str, object]] = {}

        def register_candidate(
            storage_path: str,
            *,
            source: str,
            source_priority: int,
            metadata: dict[str, object] | None = None,
            trust_level: str | None = None,
        ) -> None:
            normalized_path = str(storage_path or "").strip()
            if not normalized_path or not self.storage.exists(normalized_path):
                return
            merged_metadata = dict(metadata or {})
            existing = candidate_map.get(normalized_path)
            if existing:
                existing["source_priority"] = max(int(existing.get("source_priority") or 0), source_priority)
                existing["metadata"] = {
                    **dict(existing.get("metadata") or {}),
                    **merged_metadata,
                }
                if trust_level and not existing.get("trust_level"):
                    existing["trust_level"] = trust_level
                return
            candidate_map[normalized_path] = {
                "storage_path": normalized_path,
                "source": source,
                "source_priority": source_priority,
                "metadata": merged_metadata,
                "trust_level": trust_level,
            }

        logo_path = str(identity.get("logo_asset_path") or "").strip()
        if logo_path and self.storage.exists(logo_path):
            register_candidate(logo_path, source="identity.logo_asset_path", source_priority=26, metadata=identity)
        elif logo_path:
            logger.warning(
                "content.logo_asset_path.stale brand_space_id=%s storage_path=%s",
                brand_space_id,
                logo_path,
            )

        candidate_ids: list[str] = []
        for logo_asset in identity.get("logo_assets") or []:
            if not isinstance(logo_asset, dict):
                continue
            storage_path = str(logo_asset.get("storage_path") or "").strip()
            if storage_path:
                register_candidate(
                    storage_path,
                    source="identity.logo_assets",
                    source_priority=24,
                    metadata=logo_asset,
                    trust_level=str(logo_asset.get("trust_level") or ""),
                )
            asset_id = str(logo_asset.get("asset_id") or "").strip()
            if asset_id:
                candidate_ids.append(asset_id)

        direct_logo_asset_id = str(identity.get("logo_asset_id") or "").strip()
        if direct_logo_asset_id:
            candidate_ids.append(direct_logo_asset_id)
        for asset_id in identity.get("logo_asset_ids") or []:
            text = str(asset_id).strip()
            if text:
                candidate_ids.append(text)

        seen_ids: set[str] = set()
        for candidate_id in candidate_ids:
            if not candidate_id or candidate_id in seen_ids:
                continue
            seen_ids.add(candidate_id)
            try:
                parsed_id = UUID(candidate_id)
            except ValueError:
                continue
            asset = await self.assets.get_scoped(parsed_id, tenant_id, brand_space_id)
            if asset and asset.storage_path:
                register_candidate(
                    asset.storage_path,
                    source="generated_asset",
                    source_priority=22,
                    metadata=dict(asset.metadata_json or {}),
                    trust_level=str((asset.metadata_json or {}).get("trust_level") or ""),
                )
            knowledge_asset = await self.knowledge_assets.get_scoped(parsed_id, tenant_id, brand_space_id)
            if knowledge_asset and knowledge_asset.storage_path:
                register_candidate(
                    knowledge_asset.storage_path,
                    source="knowledge_asset",
                    source_priority=20,
                    metadata=dict(knowledge_asset.metadata_json or {}),
                    trust_level=self._trust_level_for_validation_state(knowledge_asset.validation_state),
                )

        fallback_logo_assets = await self.knowledge_assets.list_by_field(
            brand_space_id,
            "logo",
            tenant_id=tenant_id,
            active_only=True,
        )
        for asset in fallback_logo_assets:
            if asset.storage_path:
                register_candidate(
                    asset.storage_path,
                    source="knowledge_field_logo",
                    source_priority=18,
                    metadata=dict(asset.metadata_json or {}),
                    trust_level=self._trust_level_for_validation_state(asset.validation_state),
                )

        reusable_logo_assets: list[object] = []
        reusable_repo = getattr(self, "reusable_assets", None)
        if reusable_repo is not None and hasattr(reusable_repo, "list_by_brand"):
            try:
                reusable_logo_assets = await reusable_repo.list_by_brand(
                    brand_space_id,
                    tenant_id=tenant_id,
                    active_only=True,
                )
            except Exception:
                reusable_logo_assets = []
        for asset in reusable_logo_assets:
            storage_path = str(getattr(asset, "storage_path", "") or "").strip()
            if not storage_path:
                continue
            normalized_metadata = dict(getattr(asset, "normalized_metadata_json", {}) or {})
            source_metadata = dict(getattr(asset, "source_metadata_json", {}) or {})
            label = str(getattr(asset, "label", "") or "").strip()
            asset_kind = str(getattr(asset, "asset_kind", "") or "").strip().lower()
            if not self._reusable_asset_looks_like_logo(
                asset_kind=asset_kind,
                label=label,
                storage_path=storage_path,
                normalized_metadata=normalized_metadata,
                source_metadata=source_metadata,
            ):
                continue
            review_class = str(normalized_metadata.get("review_class") or "").strip().lower()
            review_status = str(normalized_metadata.get("review_status") or "").strip().lower()
            register_candidate(
                storage_path,
                source="reusable_brand_asset",
                source_priority=17 if review_class == "logo" or asset_kind == "logo_variant" else 13,
                metadata={
                    **normalized_metadata,
                    **source_metadata,
                    "label": label,
                    "asset_kind": asset_kind,
                },
                trust_level="trusted" if review_class == "logo" and review_status == "approved" else (
                    "usable_with_warning" if review_status == "approved" else None
                ),
            )

        for discovered_path in self._discover_logo_storage_paths(tenant_id, brand_space_id):
            register_candidate(
                discovered_path,
                source="storage_discovery",
                source_priority=12,
            )

        candidates: list[dict[str, object]] = []
        for candidate in candidate_map.values():
            candidate["traits"] = self._logo_traits_from_metadata(
                str(candidate.get("storage_path") or ""),
                dict(candidate.get("metadata") or {}),
            )
            candidates.append(candidate)
        return candidates

    async def _resolve_logo_asset_selection(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        brand_context: dict,
        studio_panel: dict | None = None,
        requested_variant: str | None = None,
        candidates: list[dict[str, object]] | None = None,
    ) -> dict[str, object] | None:
        scored_candidates = list(candidates or await self._collect_logo_asset_candidates(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            brand_context=brand_context,
        ))
        if not scored_candidates:
            return None

        desired = self._desired_logo_variant(brand_context, studio_panel)
        normalized_hint = self._normalize_logo_variant_hint(requested_variant)
        for candidate in scored_candidates:
            candidate["score"] = self._score_logo_candidate(candidate, desired, normalized_hint)

        selected = sorted(
            scored_candidates,
            key=lambda item: (
                int(item.get("score") or 0),
                int(item.get("source_priority") or 0),
                str(item.get("storage_path") or ""),
            ),
            reverse=True,
        )[0]
        return selected

    @staticmethod
    def _template_metadata_payload(template_meta) -> dict | None:
        if not template_meta:
            return None
        return {
            "zone_map": template_meta.zone_map or {},
            "sizing_rules": template_meta.sizing_rules or {},
            "platform_rules": template_meta.platform_rules or {},
            "editable_fields": template_meta.editable_fields or [],
            "export_rules": template_meta.export_rules or {},
        }

    @staticmethod
    def _sequence_pack_signature(value: object) -> tuple[str, int] | None:
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

    @classmethod
    def _sequence_signature_looks_like_generic_capture(
        cls,
        signature: tuple[str, int] | None,
    ) -> bool:
        if signature is None:
            return False
        family, _position = signature
        family_text = str(family or "").strip().casefold()
        if not family_text:
            return True
        generic_markers = {"whatsapp", "image", "img", "screenshot", "screen-shot", "scan", "photo", "picture"}
        if any(marker in family_text for marker in generic_markers):
            return True
        if re.search(r"\b20\d{2}\b", family_text):
            return True
        return False

    @classmethod
    def _sequence_source_signature(cls, source: dict[str, Any] | None) -> tuple[str, int] | None:
        if not isinstance(source, dict):
            return None
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}

        slide_index = 0
        for raw_index in (
            metadata.get("reference_slide_index"),
            metadata.get("slide_index"),
            metadata.get("page_index"),
            metadata.get("page_number"),
            source.get("reference_slide_index"),
            source.get("slide_index"),
            source.get("page_index"),
            source.get("page_number"),
        ):
            try:
                slide_index = int(raw_index or 0)
            except (TypeError, ValueError):
                slide_index = 0
            if slide_index > 0:
                break

        if slide_index > 0:
            for family_value in (metadata.get("sequence_family"), metadata.get("family_name")):
                family_text = re.sub(r"[-_\s]+", "-", str(family_value or "")).strip("-").upper()
                if family_text:
                    return (family_text, slide_index)

        for raw_value in (
            metadata.get("sequence_family"),
            metadata.get("family_name"),
            metadata.get("label"),
            metadata.get("source_filename"),
            metadata.get("original_filename"),
            source.get("storage_path"),
        ):
            signature = cls._sequence_pack_signature(raw_value)
            if signature is not None:
                return signature
        return None

    @classmethod
    def _sequence_pack_declared_page_count(cls, source: dict[str, Any] | None) -> int:
        if not isinstance(source, dict):
            return 0
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        for raw_count in (
            source.get("page_count"),
            source.get("slide_count"),
            source.get("preflight_page_count"),
            metadata.get("page_count"),
            metadata.get("slide_count"),
            metadata.get("preflight_page_count"),
        ):
            try:
                parsed = int(raw_count or 0)
            except (TypeError, ValueError):
                parsed = 0
            if parsed > 0:
                return parsed
        return 0

    @classmethod
    def _sequence_pack_has_explicit_blueprint(cls, metadata: dict[str, Any] | None) -> bool:
        if not isinstance(metadata, dict):
            return False
        if any(metadata.get(key) for key in cls._sequence_pack_explicit_blueprint_keys()):
            return True
        return any(
            isinstance(metadata.get(key), list) and any(isinstance(item, dict) for item in metadata.get(key) or [])
            for key in ("slides", "pages", "story_outline", "outline")
        )

    @classmethod
    def _sequence_source_is_carousel_capable(cls, source: dict[str, Any] | None) -> bool:
        if not isinstance(source, dict):
            return False
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        if cls._sequence_pack_has_explicit_blueprint(metadata):
            return True
        signature = cls._sequence_source_signature(source)
        if signature is not None and not cls._sequence_signature_looks_like_generic_capture(signature):
            return True
        page_count = cls._sequence_pack_declared_page_count(source)
        if page_count >= 3:
            return True
        for raw_value in (
            metadata.get("format"),
            metadata.get("layout_type"),
            metadata.get("narrative_pattern"),
            metadata.get("sequence_kind"),
            source.get("kind"),
        ):
            normalized = str(raw_value or "").strip().casefold()
            if normalized in {"carousel", "multi_section", "reference_pdf_blueprint"}:
                return True
        storage_path = str(source.get("storage_path") or "").strip().lower()
        return storage_path.endswith(".pdf")

    @classmethod
    def _sequence_pack_is_visual_summary(cls, value: object) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        lowered = text.casefold()
        if lowered.startswith("layout "):
            return True
        return any(
            token in lowered
            for token in (
                "background flat",
                "background gradient",
                "palette:",
                "editable zones:",
                "typography:",
            )
        )

    @classmethod
    def _repair_encoding_noise(cls, value: object) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if not any(token in text for token in ("Ã", "Â", "â€", "â€™", "â€œ", "â€”", "â€“", "â€¢")):
            return text
        try:
            repaired = text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text
        return repaired or text

    @classmethod
    def _sequence_pack_is_weak_hint(cls, value: object) -> bool:
        text = cls._repair_encoding_noise(value)
        if not text:
            return True
        if cls._sequence_pack_is_visual_summary(text):
            return True
        lowered = text.casefold()
        if lowered in {"template", "sample", "reference", "untitled", "cover", "slide"}:
            return True
        tokens = [token for token in re.split(r"[\s._/-]+", text) if token]
        if tokens and all(token.isdigit() for token in tokens):
            return True
        alnum = re.sub(r"[^a-z0-9]+", "", lowered)
        if len(alnum) <= 4:
            return True
        if re.fullmatch(r"(?:\d{1,4}[.\-_/]?){2,6}", text):
            return True
        return False

    @classmethod
    def _sequence_pack_summary_text(cls, *sources: object) -> str:
        for source in sources:
            if not isinstance(source, dict):
                continue
            for key in ("sequence_summary", "summary", "description", "notes", "sample_usage"):
                text = cls._repair_encoding_noise(source.get(key))
                if text and not cls._sequence_pack_is_visual_summary(text) and not cls._sequence_pack_is_weak_hint(text):
                    return text[:180].rstrip(" ,.;:-")
            editorial_dna = source.get("editorial_dna") if isinstance(source.get("editorial_dna"), dict) else {}
            for value in editorial_dna.get("headline_patterns") or []:
                text = cls._repair_encoding_noise(value)
                if text and not cls._sequence_pack_is_visual_summary(text) and not cls._sequence_pack_is_weak_hint(text):
                    return text[:180].rstrip(" ,.;:-")
            for value in source.get("copy_lines") or []:
                text = cls._repair_encoding_noise(value)
                if text and not cls._sequence_pack_is_visual_summary(text) and not cls._sequence_pack_is_weak_hint(text):
                    return text[:180].rstrip(" ,.;:-")
            for key in ("structural_cues", "sequence_cues", "slide_pattern", "page_pattern"):
                value = source.get(key)
                items = value if isinstance(value, list) else [value]
                for item in items:
                    text = cls._repair_encoding_noise(item)
                    if text and not cls._sequence_pack_is_visual_summary(text) and not cls._sequence_pack_is_weak_hint(text):
                        return text[:180].rstrip(" ,.;:-")
        return ""

    @classmethod
    def _sequence_pack_zone_map(
        cls,
        *,
        recommendation: dict[str, Any] | None = None,
        reference_asset: dict[str, Any] | None = None,
        fallback_zone_map: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fallback = deepcopy(fallback_zone_map or {})
        if isinstance(fallback.get("zones"), list):
            sanitized_fallback_zones: list[dict[str, Any]] = []
            for item in fallback.get("zones") or []:
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role") or item.get("zone_id") or "").strip()
                x = item.get("x")
                y = item.get("y")
                w = item.get("w") if item.get("w") is not None else item.get("width")
                h = item.get("h") if item.get("h") is not None else item.get("height")
                if not role or any(value is None for value in (x, y, w, h)):
                    continue
                try:
                    width = round(float(w), 4)
                    height = round(float(h), 4)
                    if width <= 0.0 or height <= 0.0:
                        continue
                    sanitized_fallback_zones.append(
                        {
                            **dict(item),
                            "role": role,
                            "x": round(float(x), 4),
                            "y": round(float(y), 4),
                            "w": width,
                            "h": height,
                        }
                    )
                except (TypeError, ValueError):
                    continue
            fallback["zones"] = sanitized_fallback_zones
        metadata_sources = [
            recommendation.get("metadata") if isinstance(recommendation, dict) and isinstance(recommendation.get("metadata"), dict) else {},
            reference_asset.get("metadata") if isinstance(reference_asset, dict) and isinstance(reference_asset.get("metadata"), dict) else {},
        ]

        def _normalized_zones(source: dict[str, Any]) -> list[dict[str, Any]]:
            candidates: list[dict[str, Any]] = []
            direct_zone_map = source.get("zone_map") if isinstance(source.get("zone_map"), dict) else {}
            layout_structure = source.get("layout_structure") if isinstance(source.get("layout_structure"), dict) else {}
            style_characteristics = source.get("style_characteristics") if isinstance(source.get("style_characteristics"), dict) else {}
            layout_dna = source.get("layout_dna") if isinstance(source.get("layout_dna"), dict) else (
                style_characteristics.get("layout_dna") if isinstance(style_characteristics.get("layout_dna"), dict) else {}
            )
            canvas_size = layout_dna.get("canvas_size") if isinstance(layout_dna.get("canvas_size"), dict) else {}
            canvas_width = float(canvas_size.get("width") or 0.0)
            canvas_height = float(canvas_size.get("height") or 0.0)

            raw_candidates = []
            if isinstance(direct_zone_map.get("zones"), list):
                raw_candidates.append(direct_zone_map.get("zones") or [])
            if isinstance(layout_structure.get("zones"), list):
                raw_candidates.append(layout_structure.get("zones") or [])
            if isinstance(layout_dna.get("zones"), list):
                raw_candidates.append(layout_dna.get("zones") or [])
            if isinstance(layout_dna.get("zone_instances"), list):
                raw_candidates.append(layout_dna.get("zone_instances") or [])
            if isinstance(layout_dna.get("zones"), dict):
                raw_candidates.append(list((layout_dna.get("zones") or {}).values()))

            for raw_zone_list in raw_candidates:
                for item in raw_zone_list:
                    if not isinstance(item, dict):
                        continue
                    role = str(item.get("role") or item.get("zone_id") or "").strip()
                    normalized = item.get("normalized") if isinstance(item.get("normalized"), dict) else {}
                    x = normalized.get("x", item.get("x"))
                    y = normalized.get("y", item.get("y"))
                    w = normalized.get("w", item.get("w") if item.get("w") is not None else item.get("width"))
                    h = normalized.get("h", item.get("h") if item.get("h") is not None else item.get("height"))
                    if any(value is None for value in (x, y, w, h)):
                        pixels = item.get("pixels") if isinstance(item.get("pixels"), dict) else {}
                        if pixels and canvas_width > 0 and canvas_height > 0:
                            x = x if x is not None else (float(pixels.get("x") or 0.0) / canvas_width)
                            y = y if y is not None else (float(pixels.get("y") or 0.0) / canvas_height)
                            w = w if w is not None else (float(pixels.get("width") or 0.0) / canvas_width)
                            h = h if h is not None else (float(pixels.get("height") or 0.0) / canvas_height)
                    if not role or any(value is None for value in (x, y, w, h)):
                        continue
                    try:
                        width = round(float(w), 4)
                        height = round(float(h), 4)
                        if width <= 0.0 or height <= 0.0:
                            continue
                        candidates.append(
                            {
                                "role": role,
                                "x": round(float(x), 4),
                                "y": round(float(y), 4),
                                "w": width,
                                "h": height,
                                "alignment": str(item.get("alignment") or "").strip() or None,
                            }
                        )
                    except (TypeError, ValueError):
                        continue
                if candidates:
                    break
            return candidates

        for source in metadata_sources:
            if not isinstance(source, dict):
                continue
            zones = _normalized_zones(source)
            if not zones:
                continue
            style_characteristics = source.get("style_characteristics") if isinstance(source.get("style_characteristics"), dict) else {}
            direct_zone_map = source.get("zone_map") if isinstance(source.get("zone_map"), dict) else {}
            layout_structure = source.get("layout_structure") if isinstance(source.get("layout_structure"), dict) else {}
            layout_dna = source.get("layout_dna") if isinstance(source.get("layout_dna"), dict) else (
                style_characteristics.get("layout_dna") if isinstance(style_characteristics.get("layout_dna"), dict) else {}
            )
            resolved = deepcopy(fallback)
            resolved["zones"] = zones
            resolved["layout_type"] = (
                direct_zone_map.get("layout_type")
                or layout_structure.get("layout_type")
                or layout_dna.get("layout_type")
                or resolved.get("layout_type")
                or "template"
            )
            for key in (
                "background_style",
                "visual_hierarchy",
                "content_structure",
                "composition_logic",
                "visual_craft_dna",
                "subject_semantics",
                "editorial_dna",
            ):
                for candidate in (direct_zone_map, layout_structure, source, style_characteristics):
                    if isinstance(candidate.get(key), dict) and candidate.get(key):
                        resolved[key] = deepcopy(candidate.get(key))
                        break
            return resolved
        return fallback

    @classmethod
    def _sequence_pack_source_asset_path(cls, source: dict[str, Any] | None) -> str:
        if not isinstance(source, dict):
            return ""
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        for candidate in (
            source.get("storage_path"),
            source.get("asset_url"),
            metadata.get("storage_path"),
            metadata.get("template_asset_path"),
            metadata.get("reference_asset_path"),
            metadata.get("asset_url"),
        ):
            text = str(candidate or "").strip()
            if text:
                return text
        return ""

    @classmethod
    def _sequence_pack_story_role(
        cls,
        *,
        slide_index: int,
        slide_count: int,
        hints: list[object] | None = None,
    ) -> str:
        hint_text = " ".join(str(item or "").strip().casefold() for item in (hints or []) if str(item or "").strip())
        if any(token in hint_text for token in ("undercovered", "missed", "overlooked", "not tell", "hidden angle")):
            return "undercovered_angle"
        if any(token in hint_text for token in ("why this matters", "strategic", "implication", "second-order", "beyond the headline")):
            return "strategic_meaning"
        if any(token in hint_text for token in ("what changed", "what happened", "deal terms", "how it works", "structure", "mechanics", "breakdown")):
            return "structure"
        if any(token in hint_text for token in ("context", "background", "setup", "what to know first")):
            return "context"
        if any(token in hint_text for token in ("takeaway", "what to watch", "what next", "closing", "cta", "final")):
            return "takeaway"
        if slide_index == 1:
            return "hook"
        if slide_index == slide_count:
            return "takeaway"
        if slide_count == 3 and slide_index == 2:
            return "structure"
        if slide_count >= 4 and slide_index == 2:
            return "structure"
        if slide_count >= 4 and slide_index == slide_count - 1:
            return "strategic_meaning"
        if slide_count >= 4 and slide_index == slide_count - 2:
            return "undercovered_angle"
        return "detail"

    @classmethod
    def _sequence_pack_structural_cues(
        cls,
        *,
        slide_index: int,
        slide_count: int,
        story_role: str,
        recommendation: dict[str, Any],
        reference_asset: dict[str, Any],
    ) -> list[str]:
        cues: list[str] = []
        metadata_sources = [
            recommendation.get("metadata") if isinstance(recommendation.get("metadata"), dict) else {},
            reference_asset.get("metadata") if isinstance(reference_asset.get("metadata"), dict) else {},
        ]
        for source in metadata_sources:
            for key in ("structural_cues", "sequence_cues", "slide_pattern", "page_pattern"):
                value = source.get(key)
                if isinstance(value, list):
                    for item in value:
                        text = str(item or "").strip()
                        if text and text not in cues:
                            cues.append(text)
                elif isinstance(value, str):
                    for chunk in re.split(r"[|;,]\s*|\n+", value):
                        text = chunk.strip()
                        if text and text not in cues:
                            cues.append(text)
        if not cues:
            default_map = {
                "hook": "cover hook",
                "context": "context setup",
                "structure": "what happened",
                "undercovered_angle": "undercovered angle",
                "strategic_meaning": "why it matters",
                "takeaway": "takeaway close",
                "detail": "detail explanation",
            }
            default_cue = default_map.get(story_role, "detail explanation")
            cues.append(default_cue)
        return cues[:4]

    @classmethod
    def _sequence_pack_headline_hint(
        cls,
        *,
        story_role: str,
        slide_index: int,
        template_name: str,
        recommendation: dict[str, Any],
        reference_asset: dict[str, Any],
    ) -> str:
        metadata_sources = [
            recommendation.get("metadata") if isinstance(recommendation.get("metadata"), dict) else {},
            reference_asset.get("metadata") if isinstance(reference_asset.get("metadata"), dict) else {},
        ]
        for source in metadata_sources:
            for key in ("headline_hint", "headline", "heading", "slide_title", "page_title", "label"):
                text = cls._repair_encoding_noise(source.get(key))
                if text and not cls._sequence_pack_is_visual_summary(text) and not cls._sequence_pack_is_weak_hint(text):
                    return text[:120].rstrip(" ,.;:-")
            editorial_dna = source.get("editorial_dna") if isinstance(source.get("editorial_dna"), dict) else {}
            for value in editorial_dna.get("headline_patterns") or []:
                text = cls._repair_encoding_noise(value)
                if text and not cls._sequence_pack_is_visual_summary(text) and not cls._sequence_pack_is_weak_hint(text):
                    return text[:120].rstrip(" ,.;:-")
            for value in source.get("copy_lines") or []:
                text = cls._repair_encoding_noise(value)
                if text and not cls._sequence_pack_is_visual_summary(text) and not cls._sequence_pack_is_weak_hint(text):
                    return text[:120].rstrip(" ,.;:-")
            for entry in source.get("classified_text_lines") or []:
                if not isinstance(entry, dict):
                    continue
                classification = str(entry.get("classification") or "").strip().lower()
                text = cls._repair_encoding_noise(entry.get("line"))
                if classification in {"headline", "template_copy", "supporting_copy"} and text and not cls._sequence_pack_is_visual_summary(text) and not cls._sequence_pack_is_weak_hint(text):
                    return text[:120].rstrip(" ,.;:-")
            for key in ("summary", "description", "notes"):
                text = cls._repair_encoding_noise(source.get(key))
                if text and not cls._sequence_pack_is_visual_summary(text) and not cls._sequence_pack_is_weak_hint(text):
                    return text[:120].rstrip(" ,.;:-")
        role_defaults = {
            "hook": "Why this matters now",
            "context": "What happened",
            "structure": "What actually changed",
            "undercovered_angle": "What most coverage missed",
            "strategic_meaning": "Why it matters beyond the headline",
            "takeaway": "What to do with this insight",
            "detail": f"Key insight {slide_index}",
        }
        if template_name:
            cleaned = cls._repair_encoding_noise(re.sub(r"[-_]+", " ", Path(template_name).stem).strip())
            if cleaned and not cls._sequence_pack_is_weak_hint(cleaned):
                return cleaned[:120].rstrip(" ,.;:-")
        return role_defaults.get(story_role, f"Key insight {slide_index}")

    @classmethod
    def _read_reference_pdf_pages(
        cls,
        storage_path: str,
        *,
        storage: object | None = None,
    ) -> list[str]:
        path_hint = str(storage_path or "").strip()
        if not path_hint:
            return []

        resolved_path: Path | None = None
        candidate_path = Path(path_hint)
        if candidate_path.is_absolute() and candidate_path.exists():
            resolved_path = candidate_path
        else:
            storage_client = storage or LocalObjectStorage()
            exists = getattr(storage_client, "exists", None)
            absolute_path = getattr(storage_client, "absolute_path", None)
            if not callable(exists) or not callable(absolute_path):
                return []
            try:
                if not bool(exists(path_hint)):
                    return []
                resolved_path = Path(str(absolute_path(path_hint)))
            except Exception:
                logger.debug("content.reference_pdf.resolve_failed path=%s", path_hint, exc_info=True)
                return []

        if resolved_path is None or not resolved_path.exists():
            return []

        def _normalize_page_text(value: str | None) -> str:
            lines: list[str] = []
            for raw_line in re.split(r"\n+", str(value or "")):
                line = re.sub(r"\s+", " ", raw_line).strip(" \t-•")
                if line:
                    lines.append(line)
            return "\n".join(lines)

        pages: list[str] = []
        try:
            import pdfplumber

            with pdfplumber.open(str(resolved_path)) as pdf:
                for page in pdf.pages:
                    normalized = _normalize_page_text(page.extract_text())
                    if normalized:
                        pages.append(normalized)
        except Exception:
            logger.debug("content.reference_pdf.pdfplumber_failed path=%s", str(resolved_path), exc_info=True)

        if pages:
            return pages

        try:
            import fitz

            with fitz.open(str(resolved_path)) as pdf:
                for page in pdf:
                    normalized = _normalize_page_text(page.get_text("text"))
                    if normalized:
                        pages.append(normalized)
        except Exception:
            logger.debug("content.reference_pdf.pymupdf_failed path=%s", str(resolved_path), exc_info=True)

        return pages

    @classmethod
    def _build_pdf_reference_sequence_pack(
        cls,
        *,
        source: dict[str, Any],
        metadata: dict[str, Any],
        source_label: str,
        reference_asset_path: str,
        selected_template_name: str | None,
        fallback_editable_fields: list[str],
        storage: object | None = None,
    ) -> dict[str, Any] | None:
        mime_type = str(source.get("mime_type") or metadata.get("mime_type") or "").strip().lower()
        path_hint = str(reference_asset_path or source.get("storage_path") or "").strip()
        if mime_type != "application/pdf" and Path(path_hint).suffix.lower() != ".pdf":
            return None

        page_texts = cls._read_reference_pdf_pages(path_hint, storage=storage)
        if len(page_texts) < 3:
            return None

        family_name = cls._sequence_pack_family_name(
            metadata.get("family_name"),
            source_label,
            reference_asset_path,
            selected_template_name,
        )
        sequence_kind = str(
            metadata.get("sequence_kind")
            or metadata.get("narrative_pattern")
            or "reference_pdf_blueprint"
        ).strip()
        sequence_summary = str(metadata.get("sequence_summary") or metadata.get("summary") or "").strip()
        selected_template_id = str(source.get("template_id") or "").strip()
        selected_template_label = source_label or str(selected_template_name or "").strip()
        slide_count = len(page_texts)
        sequence_cues: list[str] = []
        slides: list[dict[str, Any]] = []

        for slide_index, page_text in enumerate(page_texts, start=1):
            lines = [
                re.sub(r"\s+", " ", line).strip(" \t-•")
                for line in page_text.splitlines()
                if re.sub(r"\s+", " ", line).strip(" \t-•")
            ]
            lead_line = lines[0] if lines else ""
            title_candidate = ""
            for line in lines[:3]:
                word_count = len(line.split())
                if 2 <= word_count <= 14 and len(line) <= 120:
                    title_candidate = line
                    break
            if not title_candidate:
                sentence = re.sub(r"\s+", " ", page_text).strip()
                sentence = re.split(r"(?<=[.!?])\s+", sentence, maxsplit=1)[0]
                if 2 <= len(sentence.split()) <= 16 and len(sentence) <= 120:
                    title_candidate = sentence

            page_summary = re.sub(r"\s+", " ", page_text).strip()[:180]
            hint_pool = [
                title_candidate,
                lead_line,
                metadata.get("narrative_pattern"),
            ]
            story_role = cls._sequence_pack_story_role(
                slide_index=slide_index,
                slide_count=slide_count,
                hints=hint_pool,
            )
            if slide_index == slide_count and story_role == "takeaway":
                closing_text = " ".join(str(item or "").casefold() for item in (title_candidate, lead_line, page_summary))
                if not any(
                    token in closing_text
                    for token in ("cta", "what next", "what to watch", "closing", "final", "learn more", "book", "sign up", "follow")
                ):
                    story_role = "strategic_meaning"
            page_meta = {
                **metadata,
                "headline_hint": title_candidate,
                "summary": page_summary,
                "sequence_summary": page_summary or sequence_summary,
            }
            structural_cues = cls._sequence_pack_structural_cues(
                slide_index=slide_index,
                slide_count=slide_count,
                story_role=story_role,
                recommendation={"metadata": page_meta},
                reference_asset={"metadata": page_meta},
            )
            headline_hint = cls._sequence_pack_headline_hint(
                story_role=story_role,
                slide_index=slide_index,
                template_name=title_candidate or source_label or "",
                recommendation={"metadata": page_meta},
                reference_asset={"metadata": page_meta},
            )
            for cue in structural_cues:
                if cue not in sequence_cues:
                    sequence_cues.append(cue)
            slides.append(
                {
                    "slide_index": slide_index,
                    "template_id": selected_template_id,
                    "template_name": str(title_candidate or source_label or f"{family_name}-{slide_index}").strip(),
                    "template_asset_path": reference_asset_path,
                    "reference_asset_path": reference_asset_path,
                    "zone_map": cls._sequence_pack_zone_map(
                        recommendation={"metadata": page_meta},
                        reference_asset={"metadata": page_meta},
                    ),
                    "editable_fields": list(fallback_editable_fields),
                    "story_role": story_role,
                    "headline_hint": headline_hint,
                    "structural_cues": structural_cues[:4],
                    "sequence_summary": page_summary or sequence_summary,
                }
            )

        return {
            "family_name": family_name or cls._sequence_pack_family_name(selected_template_name, selected_template_label),
            "surface_policy": "style_reference_only",
            "selected_template_id": selected_template_id,
            "selected_template_name": selected_template_label or slides[0].get("template_name") or "",
            "sequence_kind": sequence_kind or "reference_pdf_blueprint",
            "sequence_cues": sequence_cues[:8],
            "slide_count": len(slides),
            "slides": slides,
        }

    @classmethod
    def _sequence_pack_family_name(cls, *values: object) -> str:
        for value in values:
            signature = cls._sequence_pack_signature(value)
            if signature is not None:
                return signature[0]
            raw = str(value or "").strip()
            if not raw:
                continue
            raw = raw.split("?", 1)[0]
            stem = Path(raw).name
            if "." in stem:
                stem = Path(stem).stem
            normalized = re.sub(r"[^A-Za-z0-9]+", "-", stem).strip("-").upper()
            if normalized:
                return normalized[:72]
        return "REFERENCE-SEQUENCE"

    @staticmethod
    def _sequence_pack_explicit_blueprint_keys() -> tuple[str, ...]:
        return (
            "sequence_blueprint",
            "sample_blueprint",
            "carousel_blueprint",
            "reference_blueprint",
            "story_blueprint",
        )

    @classmethod
    def _sequence_pack_slide_items_from_metadata(
        cls,
        metadata: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
        for key in cls._sequence_pack_explicit_blueprint_keys():
            candidate = metadata.get(key)
            if isinstance(candidate, dict):
                for nested_key in ("slides", "pages", "outline", "story_outline"):
                    nested_value = candidate.get(nested_key)
                    if isinstance(nested_value, list):
                        return [dict(item) for item in nested_value if isinstance(item, dict)], candidate, key
            elif isinstance(candidate, list):
                return [dict(item) for item in candidate if isinstance(item, dict)], {}, key

        for inline_key in ("slides", "story_outline", "outline", "pages"):
            inline_value = metadata.get(inline_key)
            if isinstance(inline_value, list) and any(isinstance(item, dict) for item in inline_value):
                return [dict(item) for item in inline_value if isinstance(item, dict)], {}, inline_key

        return [], {}, ""

    @classmethod
    def _build_reference_metadata_sequence_pack(
        cls,
        *,
        selected_template_id: str | None,
        selected_template_name: str | None,
        normalized_recommendations: list[dict[str, Any]],
        reference_assets: list[dict[str, Any]],
        fallback_editable_fields: list[str],
        storage: object | None = None,
    ) -> dict[str, Any] | None:
        source_candidates: list[tuple[dict[str, Any], dict[str, Any], str, str]] = []
        for recommendation in normalized_recommendations:
            metadata = recommendation.get("metadata") if isinstance(recommendation.get("metadata"), dict) else {}
            source_label = str(recommendation.get("name") or metadata.get("label") or "").strip()
            source_candidates.append((recommendation, metadata, source_label, ""))
        for asset in reference_assets or []:
            if not isinstance(asset, dict):
                continue
            metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            source_label = str(metadata.get("label") or asset.get("storage_path") or "").strip()
            source_candidates.append((asset, metadata, source_label, str(asset.get("storage_path") or "").strip()))

        preferred_candidates: list[tuple[dict[str, Any], dict[str, Any], str, str]] = []
        fallback_candidates: list[tuple[dict[str, Any], dict[str, Any], str, str]] = []
        normalized_selected_name = str(selected_template_name or "").strip().casefold()
        normalized_selected_id = str(selected_template_id or "").strip()
        for source, metadata, source_label, reference_asset_path in source_candidates:
            candidate_template_id = str(source.get("template_id") or metadata.get("template_id") or "").strip()
            candidate_name = str(
                source.get("name")
                or metadata.get("template_name")
                or metadata.get("label")
                or source_label
                or ""
            ).strip()
            if (
                normalized_selected_id
                and candidate_template_id
                and candidate_template_id == normalized_selected_id
            ) or (
                normalized_selected_name
                and candidate_name
                and candidate_name.casefold() == normalized_selected_name
            ):
                preferred_candidates.append((source, metadata, source_label, reference_asset_path))
            else:
                fallback_candidates.append((source, metadata, source_label, reference_asset_path))
        source_candidates = preferred_candidates + fallback_candidates

        explicit_slides: list[dict[str, Any]] = []
        family_name = ""
        sequence_cues: list[str] = []
        selected_template_id = ""
        selected_template_label = str(selected_template_name or "").strip()
        sequence_kind = "reference_metadata_blueprint"

        for source, metadata, source_label, reference_asset_path in source_candidates:
            slide_items, blueprint_meta, blueprint_key = cls._sequence_pack_slide_items_from_metadata(metadata)
            if not slide_items:
                continue
            slide_count = len(slide_items)
            if slide_count < 3:
                continue
            family_name = cls._sequence_pack_family_name(
                blueprint_meta.get("family_name") if isinstance(blueprint_meta, dict) else "",
                metadata.get("family_name"),
                source_label,
                reference_asset_path,
                selected_template_name,
            )
            sequence_kind = str(
                (
                    blueprint_meta.get("sequence_kind")
                    if isinstance(blueprint_meta, dict)
                    else ""
                )
                or metadata.get("sequence_kind")
                or metadata.get("narrative_pattern")
                or blueprint_key
                or "reference_metadata_blueprint"
            ).strip()
            selected_template_id = str(source.get("template_id") or "").strip()
            if not selected_template_label:
                selected_template_label = source_label

            for position, item in enumerate(slide_items, start=1):
                try:
                    slide_index = int(item.get("slide_index") or item.get("page_index") or item.get("index") or position)
                except (TypeError, ValueError):
                    slide_index = position
                if slide_index <= 0:
                    slide_index = position
                merged_meta = {
                    **metadata,
                    **({k: v for k, v in blueprint_meta.items() if k not in {"slides", "pages", "outline", "story_outline"}} if isinstance(blueprint_meta, dict) else {}),
                    **item,
                }
                item_specific_hints = [
                    item.get("story_role"),
                    item.get("role"),
                    item.get("headline_hint"),
                    item.get("headline"),
                    item.get("title"),
                    item.get("label"),
                    item.get("summary"),
                    item.get("description"),
                    item.get("notes"),
                ]
                has_item_specific_hints = any(str(value or "").strip() for value in item_specific_hints)
                story_role = cls._sequence_pack_story_role(
                    slide_index=slide_index,
                    slide_count=slide_count,
                    hints=(
                        item_specific_hints
                        if has_item_specific_hints
                        else [
                            merged_meta.get("sequence_summary"),
                            merged_meta.get("narrative_pattern"),
                            source_label,
                        ]
                    ),
                )
                structural_cues = cls._sequence_pack_structural_cues(
                    slide_index=slide_index,
                    slide_count=slide_count,
                    story_role=story_role,
                    recommendation={"metadata": merged_meta},
                    reference_asset={"metadata": merged_meta},
                )
                headline_hint = cls._sequence_pack_headline_hint(
                    story_role=story_role,
                    slide_index=slide_index,
                    template_name=str(item.get("template_name") or source_label or ""),
                    recommendation={"metadata": merged_meta},
                    reference_asset={"metadata": merged_meta},
                )
                for cue in structural_cues:
                    if cue not in sequence_cues:
                        sequence_cues.append(cue)
                slide_reference_path = str(
                    item.get("reference_asset_path")
                    or item.get("template_asset_path")
                    or reference_asset_path
                ).strip()
                slide_summary = cls._sequence_pack_summary_text(
                    item,
                    merged_meta,
                    metadata,
                )
                explicit_slides.append(
                    {
                        "slide_index": slide_index,
                        "template_id": str(item.get("template_id") or source.get("template_id") or "").strip(),
                        "template_name": str(item.get("template_name") or source_label or f"{family_name}-{slide_index}").strip(),
                        "template_asset_path": slide_reference_path,
                        "reference_asset_path": slide_reference_path,
                        "zone_map": cls._sequence_pack_zone_map(
                            recommendation={"metadata": merged_meta},
                            reference_asset={"metadata": metadata},
                        ),
                        "editable_fields": list(item.get("editable_fields") or fallback_editable_fields),
                        "story_role": story_role,
                        "headline_hint": headline_hint,
                        "structural_cues": structural_cues,
                        "sequence_summary": slide_summary,
                    }
                )
            break

        if not explicit_slides:
            for source, metadata, source_label, reference_asset_path in source_candidates:
                pdf_sequence_pack = cls._build_pdf_reference_sequence_pack(
                    source=source,
                    metadata=metadata,
                    source_label=source_label,
                    reference_asset_path=reference_asset_path,
                    selected_template_name=selected_template_name,
                    fallback_editable_fields=fallback_editable_fields,
                    storage=storage,
                )
                if pdf_sequence_pack is not None:
                    return pdf_sequence_pack

        if not explicit_slides:
            for source, metadata, source_label, reference_asset_path in source_candidates:
                slide_count = int(metadata.get("page_count") or 0)
                raw_cues = metadata.get("structural_cues") or metadata.get("sequence_cues") or metadata.get("slide_pattern") or metadata.get("page_pattern")
                cues: list[str] = []
                if isinstance(raw_cues, list):
                    for item in raw_cues:
                        text = str(item or "").strip()
                        if text and text not in cues:
                            cues.append(text)
                elif isinstance(raw_cues, str):
                    for item in re.split(r"[|;,]\s*|\n+", raw_cues):
                        text = str(item or "").strip()
                        if text and text not in cues:
                            cues.append(text)
                if max(slide_count, len(cues)) < 3:
                    continue

                derived_count = max(slide_count, len(cues))
                family_name = cls._sequence_pack_family_name(
                    metadata.get("family_name"),
                    source_label,
                    reference_asset_path,
                    selected_template_name,
                )
                sequence_kind = str(
                    metadata.get("sequence_kind")
                    or metadata.get("narrative_pattern")
                    or "reference_metadata_blueprint"
                ).strip()
                selected_template_id = str(source.get("template_id") or "").strip()
                if not selected_template_label:
                    selected_template_label = source_label

                for slide_index in range(1, derived_count + 1):
                    cue = cues[slide_index - 1] if slide_index - 1 < len(cues) else ""
                    story_role = cls._sequence_pack_story_role(
                        slide_index=slide_index,
                        slide_count=derived_count,
                        hints=[cue] if cue else [metadata.get("narrative_pattern"), metadata.get("sequence_summary"), source_label],
                    )
                    structural_cues = [cue] if cue else cls._sequence_pack_structural_cues(
                        slide_index=slide_index,
                        slide_count=derived_count,
                        story_role=story_role,
                        recommendation={"metadata": metadata},
                        reference_asset={"metadata": metadata},
                    )
                    headline_hint_metadata = {
                        key: value
                        for key, value in metadata.items()
                        if key not in {"label", "summary"}
                    }
                    if cue and (
                        len(cue.split()) >= 4
                        or any(token in cue.casefold() for token in ("what ", "why ", "how ", "missed", "matters", "watch"))
                    ):
                        headline_hint_metadata["headline_hint"] = cue[:1].upper() + cue[1:]
                    headline_hint = cls._sequence_pack_headline_hint(
                        story_role=story_role,
                        slide_index=slide_index,
                        template_name="",
                        recommendation={"metadata": headline_hint_metadata},
                        reference_asset={"metadata": headline_hint_metadata},
                    )
                    for structural_cue in structural_cues:
                        if structural_cue not in sequence_cues:
                            sequence_cues.append(structural_cue)
                    explicit_slides.append(
                        {
                            "slide_index": slide_index,
                            "template_id": str(source.get("template_id") or "").strip(),
                            "template_name": str(source_label or f"{family_name}-{slide_index}").strip(),
                            "template_asset_path": reference_asset_path,
                            "reference_asset_path": reference_asset_path,
                            "zone_map": cls._sequence_pack_zone_map(
                                recommendation={"metadata": headline_hint_metadata},
                                reference_asset={"metadata": metadata},
                            ),
                            "editable_fields": list(fallback_editable_fields),
                            "story_role": story_role,
                            "headline_hint": headline_hint,
                            "structural_cues": structural_cues[:4],
                            "sequence_summary": cls._sequence_pack_summary_text(headline_hint_metadata, metadata),
                        }
                    )
                break

        if len(explicit_slides) < 3:
            return None

        deduped_by_index: dict[int, dict[str, Any]] = {}
        for slide in explicit_slides:
            slide_index = int(slide.get("slide_index") or 0)
            if slide_index <= 0:
                continue
            existing = deduped_by_index.get(slide_index)
            if existing is None or (not existing.get("reference_asset_path") and slide.get("reference_asset_path")):
                deduped_by_index[slide_index] = slide
        slides = cls._rebalance_sequence_pack_story_roles(
            [deduped_by_index[index] for index in sorted(deduped_by_index)]
        )
        if len(slides) < 3:
            return None

        return {
            "family_name": family_name or cls._sequence_pack_family_name(selected_template_name, selected_template_label),
            "surface_policy": "style_reference_only",
            "selected_template_id": selected_template_id,
            "selected_template_name": selected_template_label or slides[0].get("template_name") or "",
            "sequence_kind": sequence_kind or "reference_metadata_blueprint",
            "sequence_cues": sequence_cues[:8],
            "slide_count": len(slides),
            "slides": slides,
        }

    @classmethod
    def _build_selected_template_authority_sequence_pack(
        cls,
        *,
        selected_template_id: str | None,
        selected_template_name: str | None,
        normalized_recommendations: list[dict[str, Any]],
        reference_assets: list[dict[str, Any]],
        fallback_editable_fields: list[str],
        base_zone_map: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        normalized_selected_template_id = str(selected_template_id or "").strip()
        normalized_selected_template_name = str(selected_template_name or "").strip()
        if not normalized_selected_template_id and not normalized_selected_template_name:
            return None

        matched_recommendations: list[dict[str, Any]] = []
        for recommendation in normalized_recommendations:
            candidate_id = str(recommendation.get("template_id") or "").strip()
            candidate_name = str(recommendation.get("name") or "").strip()
            if (
                normalized_selected_template_id
                and candidate_id
                and candidate_id == normalized_selected_template_id
            ) or (
                normalized_selected_template_name
                and candidate_name
                and candidate_name.casefold() == normalized_selected_template_name.casefold()
            ):
                matched_recommendations.append(recommendation)

        selected_signature = cls._sequence_pack_signature(normalized_selected_template_name)
        matched_reference_assets: list[dict[str, Any]] = []
        for asset in reference_assets or []:
            if not isinstance(asset, dict):
                continue
            asset_metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            asset_label = str(asset_metadata.get("label") or asset.get("storage_path") or "").strip()
            asset_signature = cls._sequence_pack_signature(asset.get("storage_path"))
            if (
                selected_signature is not None
                and asset_signature is not None
                and asset_signature[0] == selected_signature[0]
            ) or (
                normalized_selected_template_name
                and asset_label
                and asset_label.casefold() == normalized_selected_template_name.casefold()
            ):
                matched_reference_assets.append(dict(asset))

        if not matched_recommendations and not matched_reference_assets:
            return None

        count_candidates: list[int] = []
        structural_cues: list[str] = []
        family_name = cls._sequence_pack_family_name(normalized_selected_template_name)
        reference_asset_path = ""
        summary_text = ""
        guidance_recommendation = matched_recommendations[0] if matched_recommendations else {}
        guidance_reference_asset = matched_reference_assets[0] if matched_reference_assets else {}

        for source in [*matched_recommendations, *matched_reference_assets]:
            metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
            for raw_count in (
                metadata.get("slide_count"),
                metadata.get("page_count"),
                metadata.get("preflight_page_count"),
                source.get("slide_count"),
                source.get("page_count"),
            ):
                try:
                    parsed = int(raw_count or 0)
                except (TypeError, ValueError):
                    parsed = 0
                if parsed > 0:
                    count_candidates.append(parsed)
            for key in ("structural_cues", "sequence_cues", "slide_pattern", "page_pattern"):
                value = metadata.get(key)
                if isinstance(value, list):
                    for item in value:
                        text = str(item or "").strip()
                        if text and text not in structural_cues:
                            structural_cues.append(text)
                elif isinstance(value, str):
                    for item in re.split(r"[|;,]\s*|\n+", value):
                        text = str(item or "").strip()
                        if text and text not in structural_cues:
                            structural_cues.append(text)
            family_name = cls._sequence_pack_family_name(
                metadata.get("family_name"),
                metadata.get("template_name"),
                metadata.get("label"),
                source.get("name"),
                source.get("storage_path"),
                family_name,
            )
            if not reference_asset_path:
                reference_asset_path = cls._sequence_pack_source_asset_path(source)
            if not summary_text:
                summary_text = cls._sequence_pack_summary_text(
                    metadata,
                    {"copy_lines": metadata.get("copy_lines") or []},
                    {"copy_lines": [metadata.get("slide_title"), metadata.get("heading"), metadata.get("headline"), metadata.get("label")]},
                )

        slide_count = max([count for count in count_candidates if count > 0], default=0)
        if slide_count < 3:
            slide_count = max(len(structural_cues), 5)
        slide_count = max(3, min(slide_count, 10))

        slides: list[dict[str, Any]] = []
        sequence_cues: list[str] = []
        zone_map = deepcopy(base_zone_map or {})
        reference_by_index: dict[int, dict[str, Any]] = {}
        for asset in matched_reference_assets:
            signature = cls._sequence_pack_signature(
                asset.get("storage_path")
                or ((asset.get("metadata") or {}).get("label") if isinstance(asset.get("metadata"), dict) else "")
            )
            if signature is None:
                continue
            reference_by_index[signature[1]] = dict(asset)
        for slide_index in range(1, slide_count + 1):
            current_cue = structural_cues[slide_index - 1] if slide_index - 1 < len(structural_cues) else ""
            slide_reference_asset = reference_by_index.get(slide_index, {})
            template_asset_path = (
                cls._sequence_pack_source_asset_path(slide_reference_asset)
                or cls._sequence_pack_source_asset_path(guidance_recommendation)
                or reference_asset_path
            )
            story_role = cls._sequence_pack_story_role(
                slide_index=slide_index,
                slide_count=slide_count,
                hints=[
                    current_cue,
                    normalized_selected_template_name,
                    summary_text,
                    ((slide_reference_asset.get("metadata") or {}).get("heading") if isinstance(slide_reference_asset, dict) and isinstance(slide_reference_asset.get("metadata"), dict) else ""),
                ],
            )
            per_slide_cues = (
                [current_cue]
                if current_cue
                else cls._sequence_pack_structural_cues(
                    slide_index=slide_index,
                    slide_count=slide_count,
                    story_role=story_role,
                    recommendation=guidance_recommendation,
                    reference_asset=guidance_reference_asset,
                )
            )
            headline_hint = cls._sequence_pack_headline_hint(
                story_role=story_role,
                slide_index=slide_index,
                template_name=normalized_selected_template_name,
                recommendation=guidance_recommendation,
                reference_asset=guidance_reference_asset,
            )
            for cue in per_slide_cues:
                if cue not in sequence_cues:
                    sequence_cues.append(cue)
            slides.append(
                {
                    "slide_index": slide_index,
                    "template_id": normalized_selected_template_id,
                    "template_name": normalized_selected_template_name or f"{family_name}-{slide_index}",
                    "template_asset_path": template_asset_path,
                    "reference_asset_path": cls._sequence_pack_source_asset_path(slide_reference_asset) or template_asset_path,
                    "zone_map": cls._sequence_pack_zone_map(
                        recommendation=guidance_recommendation,
                        reference_asset=slide_reference_asset,
                        fallback_zone_map=zone_map,
                    ),
                    "editable_fields": list(fallback_editable_fields),
                    "story_role": story_role,
                    "headline_hint": headline_hint,
                    "structural_cues": per_slide_cues[:4],
                    "sequence_summary": cls._sequence_pack_summary_text(
                        (slide_reference_asset.get("metadata") if isinstance(slide_reference_asset.get("metadata"), dict) else {}),
                        (guidance_recommendation.get("metadata") if isinstance(guidance_recommendation.get("metadata"), dict) else {}),
                        {"summary": summary_text},
                        {"copy_lines": [headline_hint, *per_slide_cues[:2]]},
                    ),
                }
            )

        return {
            "family_name": family_name or cls._sequence_pack_family_name(normalized_selected_template_name),
            "surface_policy": "style_reference_only",
            "selected_template_id": normalized_selected_template_id,
            "selected_template_name": normalized_selected_template_name or slides[0].get("template_name") or "",
            "sequence_kind": "selected_template_authority_fallback",
            "sequence_cues": sequence_cues[:8],
            "slide_count": len(slides),
            "slides": slides,
        }

    @classmethod
    def _sequence_pack_matches_selected_template(
        cls,
        sequence_pack: dict[str, Any] | None,
        *,
        selected_template_id: str | None,
        selected_template_name: str | None,
    ) -> bool:
        if not isinstance(sequence_pack, dict):
            return False
        normalized_selected_template_id = str(selected_template_id or "").strip()
        normalized_selected_template_name = str(selected_template_name or "").strip().casefold()
        if not normalized_selected_template_id and not normalized_selected_template_name:
            return False
        pack_template_id = str(sequence_pack.get("selected_template_id") or "").strip()
        pack_template_name = str(sequence_pack.get("selected_template_name") or "").strip().casefold()
        slides = [item for item in (sequence_pack.get("slides") or []) if isinstance(item, dict)]
        selected_signature = cls._sequence_pack_signature(selected_template_name)
        if slides:
            if selected_signature is not None:
                matched_slide_families: set[str] = set()
                for slide in slides:
                    slide_signature = cls._sequence_pack_signature(slide.get("template_name"))
                    if slide_signature is None:
                        continue
                    matched_slide_families.add(slide_signature[0])
                if matched_slide_families:
                    return matched_slide_families == {selected_signature[0]}
            if normalized_selected_template_id:
                for slide in slides:
                    if str(slide.get("template_id") or "").strip() == normalized_selected_template_id:
                        return True
            if normalized_selected_template_name:
                for slide in slides:
                    if str(slide.get("template_name") or "").strip().casefold() == normalized_selected_template_name:
                        return True
            return False
        if normalized_selected_template_id and pack_template_id == normalized_selected_template_id:
            return True
        if normalized_selected_template_name and pack_template_name == normalized_selected_template_name:
            return True
        if normalized_selected_template_name:
            for slide in slides:
                if str(slide.get("template_name") or "").strip().casefold() == normalized_selected_template_name:
                    return True
        return False

    @classmethod
    def _resolve_authoritative_sequence_pack(
        cls,
        sequence_pack: dict[str, Any] | None,
        *,
        selected_template_id: str | None,
        selected_template_name: str | None,
        selected_template_authority_pack: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not isinstance(sequence_pack, dict):
            return selected_template_authority_pack if isinstance(selected_template_authority_pack, dict) else None
        if (
            isinstance(selected_template_authority_pack, dict)
            and not cls._sequence_pack_matches_selected_template(
                sequence_pack,
                selected_template_id=selected_template_id,
                selected_template_name=selected_template_name,
            )
        ):
            return deepcopy(selected_template_authority_pack)

        resolved = deepcopy(sequence_pack)
        normalized_selected_template_id = str(selected_template_id or "").strip()
        normalized_selected_template_name = str(selected_template_name or "").strip()
        if normalized_selected_template_id and not str(resolved.get("selected_template_id") or "").strip():
            resolved["selected_template_id"] = normalized_selected_template_id
        if normalized_selected_template_name and not str(resolved.get("selected_template_name") or "").strip():
            resolved["selected_template_name"] = normalized_selected_template_name
        return resolved

    @classmethod
    def _rebalance_sequence_pack_story_roles(
        cls,
        slides: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized_slides = [dict(item) for item in slides if isinstance(item, dict)]
        if len(normalized_slides) < 3:
            return normalized_slides
        existing_roles = [
            str(item.get("story_role") or "").strip().lower()
            for item in normalized_slides
            if str(item.get("story_role") or "").strip()
        ]
        distinct_roles = {role for role in existing_roles if role}
        if distinct_roles and not distinct_roles.issubset({"context", "detail"}):
            return normalized_slides

        slide_count = len(normalized_slides)
        rebalanced: list[dict[str, Any]] = []
        for position, slide in enumerate(normalized_slides, start=1):
            updated = dict(slide)
            updated["story_role"] = cls._sequence_pack_story_role(
                slide_index=position,
                slide_count=slide_count,
                hints=[],
            )
            structural_cues = updated.get("structural_cues")
            if not structural_cues or all(str(item or "").strip().lower() == "context setup" for item in (structural_cues or [])):
                updated["structural_cues"] = cls._sequence_pack_structural_cues(
                    slide_index=position,
                    slide_count=slide_count,
                    story_role=str(updated.get("story_role") or ""),
                    recommendation={"metadata": {}},
                    reference_asset={"metadata": {}},
                )
            rebalanced.append(updated)
        return rebalanced

    @classmethod
    def _build_template_context_payload(
        cls,
        *,
        prompt: str | None,
        template_meta,
        selected_template_id: str | None,
        selected_template_name: str | None,
        template_recommendations: list[object],
        reference_assets: list[dict],
        studio_panel: dict | None,
    ) -> dict | None:
        base_context = deepcopy(template_meta.zone_map or {}) if template_meta else {}
        if template_meta:
            base_context.update(
                {
                    "zone_map": deepcopy(template_meta.zone_map or {}),
                    "sizing_rules": deepcopy(template_meta.sizing_rules or {}),
                    "platform_rules": deepcopy(template_meta.platform_rules or {}),
                    "editable_fields": list(template_meta.editable_fields or []),
                    "export_rules": deepcopy(template_meta.export_rules or {}),
                }
            )

        if str((studio_panel or {}).get("format") or "").strip().lower() != "carousel":
            return base_context or None

        normalized_recommendations: list[dict] = []
        for recommendation in template_recommendations or []:
            if hasattr(recommendation, "model_dump"):
                normalized_recommendations.append(recommendation.model_dump(mode="json"))
            elif isinstance(recommendation, dict):
                normalized_recommendations.append(dict(recommendation))

        normalized_selected_template_id = str(selected_template_id or "").strip()
        normalized_selected_template_name = str(selected_template_name or "").strip()
        normalized_selected_template_name_key = normalized_selected_template_name.casefold()

        def is_selected_template_recommendation(candidate: dict[str, Any]) -> bool:
            candidate_id = str(candidate.get("template_id") or "").strip()
            candidate_name = str(candidate.get("name") or "").strip().casefold()
            return (
                normalized_selected_template_id
                and candidate_id
                and candidate_id == normalized_selected_template_id
            ) or (
                normalized_selected_template_name_key
                and candidate_name
                and candidate_name == normalized_selected_template_name_key
            )

        def is_selected_template_reference_asset(candidate: dict[str, Any]) -> bool:
            if not normalized_selected_template_name_key:
                return False
            metadata = candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
            candidate_values = [
                str(metadata.get("label") or "").strip().casefold(),
                str(metadata.get("family_name") or "").strip().casefold(),
                str(metadata.get("sequence_family") or "").strip().casefold(),
                str(candidate.get("storage_path") or "").replace("\\", "/").rsplit("/", 1)[-1].casefold(),
            ]
            return any(
                value and normalized_selected_template_name_key in value
                for value in candidate_values
            )

        def dedupe_items(
            items: list[dict[str, Any]],
            *,
            key_builder,
        ) -> list[dict[str, Any]]:
            deduped: list[dict[str, Any]] = []
            seen: set[str] = set()
            for item in items:
                key = str(key_builder(item) or "").strip()
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                deduped.append(dict(item))
            return deduped

        carousel_recommendations = [
            dict(recommendation)
            for recommendation in normalized_recommendations
            if cls._sequence_source_is_carousel_capable(recommendation)
        ]
        carousel_reference_assets = [
            dict(asset)
            for asset in reference_assets or []
            if isinstance(asset, dict) and cls._sequence_source_is_carousel_capable(asset)
        ]
        if carousel_recommendations or carousel_reference_assets:
            selected_template_recommendations = [
                dict(recommendation)
                for recommendation in normalized_recommendations
                if is_selected_template_recommendation(recommendation)
            ]
            selected_template_reference_assets = [
                dict(asset)
                for asset in reference_assets or []
                if isinstance(asset, dict) and is_selected_template_reference_asset(asset)
            ]
            normalized_recommendations = dedupe_items(
                [*carousel_recommendations, *selected_template_recommendations]
                if carousel_recommendations
                else normalized_recommendations,
                key_builder=lambda item: (
                    str(item.get("template_id") or "").strip()
                    or str(item.get("name") or "").strip()
                ),
            )
            reference_assets = dedupe_items(
                [*carousel_reference_assets, *selected_template_reference_assets]
                if carousel_reference_assets
                else reference_assets,
                key_builder=lambda item: str(item.get("storage_path") or "").strip(),
            )

        fallback_editable_fields = list(base_context.get("editable_fields") or [])
        selected_context_evidence = cls._selected_template_context_evidence_texts(
            prompt=prompt,
            selected_template_name=normalized_selected_template_name,
            selected_template_id=normalized_selected_template_id,
            template_recommendations=normalized_recommendations,
            reference_assets=reference_assets,
        )
        if cls._template_context_layout_semantically_conflicts(base_context, selected_context_evidence):
            base_context = cls._strip_conflicting_template_layout_context(base_context)
            fallback_editable_fields = list(base_context.get("editable_fields") or fallback_editable_fields)
        explicit_sequence_pack = cls._build_reference_metadata_sequence_pack(
            selected_template_id=selected_template_id,
            selected_template_name=selected_template_name,
            normalized_recommendations=normalized_recommendations,
            reference_assets=reference_assets,
            fallback_editable_fields=fallback_editable_fields,
        )

        pinned_template_id = str((studio_panel or {}).get("pinned_template_id") or "").strip()
        allow_irrelevant_sequence_pack = bool(pinned_template_id)
        def should_keep_sequence_pack(
            sequence_pack: dict[str, Any] | None,
            *,
            selected_template_authority: bool = False,
        ) -> bool:
            if not isinstance(sequence_pack, dict):
                return False
            if selected_template_authority and (normalized_selected_template_id or normalized_selected_template_name):
                return True
            if allow_irrelevant_sequence_pack:
                return True
            return cls._sequence_pack_is_relevant_to_prompt(prompt, sequence_pack)

        explicit_matches_selection = cls._sequence_pack_matches_selected_template(
            explicit_sequence_pack,
            selected_template_id=normalized_selected_template_id,
            selected_template_name=normalized_selected_template_name,
        )
        explicit_selected_template_authority = explicit_matches_selection and bool(
            normalized_selected_template_id or normalized_selected_template_name
        )
        if explicit_sequence_pack and explicit_matches_selection:
            resolved_pack = cls._resolve_authoritative_sequence_pack(
                explicit_sequence_pack,
                selected_template_id=normalized_selected_template_id,
                selected_template_name=normalized_selected_template_name,
            )
            if should_keep_sequence_pack(
                resolved_pack,
                selected_template_authority=explicit_selected_template_authority,
            ):
                base_context["sequence_pack"] = resolved_pack
            return base_context or None
        selected_template_authority_pack = cls._build_selected_template_authority_sequence_pack(
            selected_template_id=normalized_selected_template_id,
            selected_template_name=normalized_selected_template_name,
            normalized_recommendations=normalized_recommendations,
            reference_assets=reference_assets,
            fallback_editable_fields=fallback_editable_fields,
            base_zone_map=base_context.get("zone_map") or base_context,
        )

        family_signature = cls._sequence_pack_signature(selected_template_name)
        if family_signature is None and explicit_sequence_pack and (normalized_selected_template_id or normalized_selected_template_name):
            if selected_template_authority_pack is not None:
                resolved_pack = cls._resolve_authoritative_sequence_pack(
                    selected_template_authority_pack,
                    selected_template_id=normalized_selected_template_id,
                    selected_template_name=normalized_selected_template_name,
                    selected_template_authority_pack=selected_template_authority_pack,
                )
                if should_keep_sequence_pack(resolved_pack, selected_template_authority=True):
                    base_context["sequence_pack"] = resolved_pack
                return base_context or None
            resolved_pack = cls._resolve_authoritative_sequence_pack(
                explicit_sequence_pack,
                selected_template_id=normalized_selected_template_id,
                selected_template_name=normalized_selected_template_name,
                selected_template_authority_pack=selected_template_authority_pack,
            )
            if should_keep_sequence_pack(
                resolved_pack,
                selected_template_authority=explicit_selected_template_authority,
            ):
                base_context["sequence_pack"] = resolved_pack
            return base_context or None
        if family_signature is None:
            for recommendation in normalized_recommendations:
                family_signature = cls._sequence_pack_signature(recommendation.get("name"))
                if family_signature is not None:
                    break
        if family_signature is None:
            for asset in reference_assets or []:
                family_signature = cls._sequence_pack_signature(asset.get("storage_path"))
                if family_signature is not None:
                    break
        if family_signature is None:
            if explicit_sequence_pack:
                resolved_pack = cls._resolve_authoritative_sequence_pack(
                    explicit_sequence_pack,
                    selected_template_id=normalized_selected_template_id,
                    selected_template_name=normalized_selected_template_name,
                    selected_template_authority_pack=selected_template_authority_pack,
                )
                if should_keep_sequence_pack(
                    resolved_pack,
                    selected_template_authority=explicit_selected_template_authority,
                ):
                    base_context["sequence_pack"] = resolved_pack
                return base_context or None
            return base_context or None

        family_name = family_signature[0]
        recommendation_by_index: dict[int, dict] = {}
        for recommendation in normalized_recommendations:
            signature = cls._sequence_pack_signature(recommendation.get("name"))
            if not signature or signature[0] != family_name:
                continue
            recommendation_by_index[signature[1]] = recommendation

        reference_by_index: dict[int, dict] = {}
        for asset in reference_assets or []:
            if not isinstance(asset, dict):
                continue
            signature = cls._sequence_pack_signature(asset.get("storage_path"))
            if not signature or signature[0] != family_name:
                continue
            reference_by_index[signature[1]] = dict(asset)

        slide_indexes = sorted(set(recommendation_by_index) | set(reference_by_index))
        if len(slide_indexes) < 3:
            if selected_template_authority_pack is not None:
                resolved_pack = cls._resolve_authoritative_sequence_pack(
                    selected_template_authority_pack,
                    selected_template_id=normalized_selected_template_id,
                    selected_template_name=normalized_selected_template_name,
                    selected_template_authority_pack=selected_template_authority_pack,
                )
                if should_keep_sequence_pack(resolved_pack, selected_template_authority=True):
                    base_context["sequence_pack"] = resolved_pack
                return base_context or None
            if explicit_sequence_pack:
                resolved_pack = cls._resolve_authoritative_sequence_pack(
                    explicit_sequence_pack,
                    selected_template_id=normalized_selected_template_id,
                    selected_template_name=normalized_selected_template_name,
                    selected_template_authority_pack=selected_template_authority_pack,
                )
                if should_keep_sequence_pack(
                    resolved_pack,
                    selected_template_authority=explicit_selected_template_authority,
                ):
                    base_context["sequence_pack"] = resolved_pack
                return base_context or None
            return base_context or None

        sequence_pack_template_id = ""
        selected_template_label = str(selected_template_name or "").strip()
        slides: list[dict[str, object]] = []
        sequence_cues: list[str] = []
        for slide_index in slide_indexes:
            recommendation = recommendation_by_index.get(slide_index, {})
            reference_asset = reference_by_index.get(slide_index, {})
            metadata = recommendation.get("metadata") if isinstance(recommendation.get("metadata"), dict) else {}
            template_id = str(recommendation.get("template_id") or "").strip()
            template_name = str(recommendation.get("name") or f"{family_name}-{slide_index}").strip()
            reference_asset_path = str(reference_asset.get("storage_path") or "").strip()
            reference_metadata = reference_asset.get("metadata") if isinstance(reference_asset.get("metadata"), dict) else {}
            story_role = cls._sequence_pack_story_role(
                slide_index=slide_index,
                slide_count=len(slide_indexes),
                hints=[
                    template_name,
                    metadata.get("label"),
                    metadata.get("summary"),
                    metadata.get("slide_title"),
                    reference_metadata.get("label"),
                    reference_metadata.get("summary"),
                    reference_metadata.get("sequence_summary"),
                    reference_metadata.get("narrative_pattern"),
                ],
            )
            structural_cues = cls._sequence_pack_structural_cues(
                slide_index=slide_index,
                slide_count=len(slide_indexes),
                story_role=story_role,
                recommendation=recommendation,
                reference_asset=reference_asset,
            )
            headline_hint = cls._sequence_pack_headline_hint(
                story_role=story_role,
                slide_index=slide_index,
                template_name=template_name,
                recommendation=recommendation,
                reference_asset=reference_asset,
            )
            if not sequence_pack_template_id and template_id:
                sequence_pack_template_id = template_id
            if not selected_template_label and template_name:
                selected_template_label = template_name
            for cue in structural_cues:
                if cue not in sequence_cues:
                    sequence_cues.append(cue)
            slides.append(
                {
                    "slide_index": slide_index,
                    "template_id": template_id,
                    "template_name": template_name,
                    "template_asset_path": reference_asset_path,
                    "reference_asset_path": reference_asset_path,
                    "zone_map": cls._sequence_pack_zone_map(
                        recommendation=recommendation,
                        reference_asset=reference_asset,
                        fallback_zone_map=base_context.get("zone_map") or base_context,
                    ),
                    "editable_fields": list(metadata.get("editable_fields") or fallback_editable_fields),
                    "story_role": story_role,
                    "headline_hint": headline_hint,
                    "structural_cues": structural_cues,
                    "sequence_summary": cls._sequence_pack_summary_text(
                        reference_metadata,
                        metadata,
                    ),
                }
            )

        if not slides:
            return base_context or None

        slides = cls._rebalance_sequence_pack_story_roles(slides)
        sequence_cues = []
        for slide in slides:
            for cue in slide.get("structural_cues") or []:
                text = str(cue or "").strip()
                if text and text not in sequence_cues:
                    sequence_cues.append(text)

        sequence_pack = {
            "family_name": family_name,
            "surface_policy": "style_reference_only",
            "selected_template_id": normalized_selected_template_id or sequence_pack_template_id,
            "selected_template_name": normalized_selected_template_name or selected_template_label or slides[0].get("template_name") or "",
            "sequence_kind": "reference_driven_structural_blueprint",
            "sequence_cues": sequence_cues[:8],
            "slide_count": len(slides),
            "slides": slides,
        }
        if not cls._sequence_pack_matches_selected_template(
            sequence_pack,
            selected_template_id=normalized_selected_template_id,
            selected_template_name=normalized_selected_template_name,
        ) and selected_template_authority_pack is not None:
            resolved_pack = cls._resolve_authoritative_sequence_pack(
                selected_template_authority_pack,
                selected_template_id=normalized_selected_template_id,
                selected_template_name=normalized_selected_template_name,
                selected_template_authority_pack=selected_template_authority_pack,
            )
            if should_keep_sequence_pack(resolved_pack, selected_template_authority=True):
                base_context["sequence_pack"] = resolved_pack
            return base_context or None
        resolved_pack = cls._resolve_authoritative_sequence_pack(
            sequence_pack,
            selected_template_id=normalized_selected_template_id,
            selected_template_name=normalized_selected_template_name,
            selected_template_authority_pack=selected_template_authority_pack,
        )
        if should_keep_sequence_pack(resolved_pack):
            base_context["sequence_pack"] = resolved_pack
        return base_context or None

    async def _get_or_create_session(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        user_id: UUID,
        session_id: UUID | None,
        studio_panel: dict,
    ) -> ContentSession:
        if session_id:
            existing = await self.sessions.get(session_id)
            if existing and existing.tenant_id == tenant_id and existing.brand_space_id == brand_space_id:
                existing.studio_panel = studio_panel or existing.studio_panel
                return existing
        session = ContentSession(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            user_id=user_id,
            title="Brand Workspace Session",
            studio_panel=studio_panel,
            conversational_context={},
        )
        await self.sessions.add(session)
        await self.session.flush()
        return session

    async def _record_session_context(
        self,
        session: ContentSession,
        payload: ContentGenerateRequest,
        content_version: ContentVersion,
    ) -> None:
        artifact_service = getattr(self, "artifacts", ArtifactStateService())
        session.studio_panel = payload.studio_panel.model_dump()
        context = dict(session.conversational_context or {})
        context["last_user_prompt"] = str(getattr(payload, "raw_user_prompt", None) or payload.prompt or "").strip()
        context["last_content_version_id"] = str(content_version.id)
        context["last_persona_id"] = str(content_version.selected_persona_id) if content_version.selected_persona_id else None
        context["last_objective_id"] = str(content_version.objective_id) if content_version.objective_id else None
        context["last_template_id"] = str(content_version.selected_template_id) if content_version.selected_template_id else None
        decision_payload = (
            (content_version.explainability_metadata or {}).get("creative_decision", {})
            or (content_version.explainability_metadata or {}).get("layout_decision", {})
            or {}
        )
        context["last_generation_mode"] = decision_payload.get("layout_mode") or decision_payload.get("mode")
        context["message_count"] = int(context.get("message_count", 0)) + 1
        artifact_state = (
            (content_version.explainability_metadata or {}).get("artifact_state")
            if isinstance(content_version.explainability_metadata, dict)
            else {}
        )
        if isinstance(artifact_state, dict) and artifact_state:
            context["artifact_state"] = artifact_service.build_session_state(
                context,
                content_artifact_state=artifact_state,
            )
        session.conversational_context = context

    async def _build_session_memory(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        session: ContentSession,
        current_prompt: str,
    ) -> dict:
        recent_messages = await self.chat_messages.list_recent_by_session(session.id, limit=8)
        serialized_messages = [self._chat_message_payload(message) for message in recent_messages]
        if serialized_messages:
            last_message = serialized_messages[-1]
            if (
                last_message.get("role") == "user"
                and str(last_message.get("message_text", "")).strip() == current_prompt.strip()
            ):
                serialized_messages = serialized_messages[:-1]

        recent_contents = await self.contents.list_by_session(session.id, tenant_id=tenant_id, limit=3)
        serialized_contents = [
            self._content_version_memory_payload(content)
            for content in recent_contents
            if content.brand_space_id == brand_space_id
        ]
        return self.session_memory.build(
            current_prompt=current_prompt,
            recent_messages=serialized_messages,
            recent_content_versions=serialized_contents,
            session_context=session.conversational_context,
        )

    async def _gather_context(self, brand_space_id: UUID) -> dict:
        brand = await self.brands.get(brand_space_id)
        if not brand:
            raise NotFoundError("Brand Space not found")
        sections = await self.sections.list_current_sections(brand_space_id, brand.tenant_id)
        personas = await self.personas.list_by_brand(brand_space_id, brand.tenant_id)
        objectives = await self.objectives.list_by_brand(brand_space_id, brand.tenant_id)
        return {
            "brand": brand,
            "sections": sections,
            "personas": personas,
            "objectives": objectives,
        }

    async def _get_content_scoped(
        self,
        tenant_id: UUID,
        brand_space_id: UUID | None,
        content_version_id: UUID,
    ) -> ContentVersion:
        content = await self.contents.get_scoped(content_version_id, tenant_id, brand_space_id)
        if not content:
            raise NotFoundError("Content version not found")
        return content

    async def _resolve_logo_asset_path(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        brand_context: dict,
        studio_panel: dict | None = None,
    ) -> str | None:
        selection = await self._resolve_logo_asset_selection(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            brand_context=brand_context,
            studio_panel=studio_panel,
        )
        if not selection:
            fallback_context = await self._brand_context_with_identity_logo_fallback(
                tenant_id=tenant_id,
                brand_space_id=brand_space_id,
                brand_context=brand_context,
            )
            if fallback_context is not None:
                selection = await self._resolve_logo_asset_selection(
                    tenant_id=tenant_id,
                    brand_space_id=brand_space_id,
                    brand_context=fallback_context,
                    studio_panel=studio_panel,
                )
        if not selection:
            return None
        return str(selection.get("storage_path") or "").strip() or None

    async def _brand_context_with_identity_logo_fallback(
        self,
        *,
        tenant_id: UUID,
        brand_space_id: UUID,
        brand_context: dict,
    ) -> dict | None:
        identity = brand_context.get("identity", {}) or {}
        if any(
            identity.get(key)
            for key in ("logo_asset_path", "logo_asset_id", "logo_asset_ids", "logo_assets")
        ):
            return None
        sections = await self.sections.list_current_sections(brand_space_id, tenant_id)
        identity_section = next(
            (
                section.payload
                for section in sections
                if getattr(section, "section_code", None) == "identity" and isinstance(getattr(section, "payload", None), dict)
            ),
            None,
        )
        if not isinstance(identity_section, dict):
            return None
        fallback_identity: dict[str, object] = {}
        for key in ("logo_asset_path", "logo_asset_id", "logo_asset_ids", "logo_assets"):
            value = identity_section.get(key)
            if value:
                fallback_identity[key] = deepcopy(value)
        if not fallback_identity:
            return None
        resolved_context = deepcopy(brand_context)
        resolved_context["identity"] = {
            **dict(identity),
            **fallback_identity,
        }
        return resolved_context

    async def _prepare_runtime_brand_context(
        self,
        *,
        tenant_id: UUID,
        brand_space_id: UUID,
        brand_context: dict,
        studio_panel: dict | None = None,
        sections: list[object] | None = None,
    ) -> tuple[dict, list[dict[str, object]], dict[str, object] | None]:
        resolved_context = deepcopy(brand_context or {})

        section_payloads: dict[str, dict] = {}
        for section in sections or []:
            section_code = str(getattr(section, "section_code", "") or "").strip()
            payload = getattr(section, "payload", None)
            if section_code and isinstance(payload, dict):
                section_payloads[section_code] = payload

        for section_code in (
            "identity",
            "foundations",
            "voice_tone",
            "visual_identity",
            "prompt_intelligence",
            "knowledge",
            "objectives",
            "review",
        ):
            fallback_payload = section_payloads.get(section_code)
            if not isinstance(fallback_payload, dict):
                continue
            resolved_context[section_code] = self._merge_brand_context_missing(
                resolved_context.get(section_code, {}),
                fallback_payload,
            )

        fallback_context = await self._brand_context_with_identity_logo_fallback(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            brand_context=resolved_context,
        )
        if fallback_context is not None:
            resolved_context = self._merge_brand_context_missing(resolved_context, fallback_context)

        identity = dict(resolved_context.get("identity", {}) or {})
        visual_identity = dict(resolved_context.get("visual_identity", {}) or {})

        if not visual_identity.get("reusable_design_assets"):
            reusable_assets: list[dict[str, object]] = []
            reusable_repo = getattr(self, "reusable_assets", None)
            if reusable_repo is not None and hasattr(reusable_repo, "list_by_brand"):
                try:
                    reusable_assets = [
                        self._reusable_asset_record(asset)
                        for asset in await reusable_repo.list_by_brand(
                            brand_space_id,
                            tenant_id=tenant_id,
                            active_only=True,
                        )
                    ]
                except Exception:
                    reusable_assets = []
            if reusable_assets:
                visual_identity["reusable_design_assets"] = reusable_assets
                visual_identity["reusable_design_asset_ids"] = [
                    asset["id"] for asset in reusable_assets if str(asset.get("id") or "").strip()
                ]
                visual_identity["icon_asset_ids"] = [
                    asset["id"]
                    for asset in reusable_assets
                    if str(asset.get("asset_kind") or "").strip().lower() == "icon" and str(asset.get("id") or "").strip()
                ]
                visual_identity["decorative_asset_ids"] = [
                    asset["id"]
                    for asset in reusable_assets
                    if str(asset.get("asset_kind") or "").strip().lower() in {"decorative_asset", "enhancement_component", "micro_design_element"}
                    and str(asset.get("id") or "").strip()
                ]
                visual_identity["logo_variant_asset_ids"] = [
                    asset["id"]
                    for asset in reusable_assets
                    if str(asset.get("asset_kind") or "").strip().lower() == "logo_variant" and str(asset.get("id") or "").strip()
                ]

        resolved_context["identity"] = identity
        resolved_context["visual_identity"] = visual_identity

        logo_candidates = await self._collect_logo_asset_candidates(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            brand_context=resolved_context,
        )
        logo_selection = await self._resolve_logo_asset_selection(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            brand_context=resolved_context,
            studio_panel=studio_panel,
            candidates=logo_candidates,
        )
        if logo_selection:
            logo_storage_path = str(logo_selection.get("storage_path") or "").strip()
            logo_metadata = dict(logo_selection.get("metadata") or {})
            logo_traits = dict(logo_selection.get("traits") or {})
            if logo_storage_path and not str(identity.get("logo_asset_path") or "").strip():
                identity["logo_asset_path"] = logo_storage_path
            logo_assets = list(identity.get("logo_assets") or [])
            if logo_storage_path and not any(
                str(item.get("storage_path") or "").strip() == logo_storage_path
                for item in logo_assets
                if isinstance(item, dict)
            ):
                logo_assets.insert(
                    0,
                    {
                        "storage_path": logo_storage_path,
                        "trust_level": logo_selection.get("trust_level"),
                        "variant": logo_metadata.get("variant") or logo_metadata.get("logo_variant"),
                        "background_variant": logo_traits.get("background_variant") or logo_metadata.get("background_variant"),
                        "orientation": logo_traits.get("orientation") or logo_metadata.get("orientation"),
                    },
                )
            if logo_assets:
                identity["logo_assets"] = logo_assets

            if not visual_identity.get("palette_entries"):
                logo_palette_entries = self._palette_entries_from_logo_metadata(logo_metadata)
                if logo_palette_entries:
                    visual_identity["palette_entries"] = logo_palette_entries

        if not visual_identity.get("brand_color_palette"):
            derived_palette_roles = derive_palette_roles(visual_identity)
            if derived_palette_roles:
                visual_identity["brand_color_palette"] = derived_palette_roles

        resolved_context["identity"] = identity
        resolved_context["visual_identity"] = visual_identity
        return resolved_context, logo_candidates, logo_selection

    def _discover_logo_storage_paths(self, tenant_id: UUID, brand_space_id: UUID) -> list[str]:
        base_path = getattr(self.storage, "base_path", None)
        if not base_path:
            return []
        base_path = Path(base_path).resolve()
        try:
            brand_root = Path(self.storage.absolute_path(f"{tenant_id}/{brand_space_id}"))
        except Exception:
            return []
        if not brand_root.exists():
            return []

        search_roots = [
            brand_root / "logo",
            brand_root / "brand",
            brand_root / "uploads",
            brand_root / "derived-assets",
        ]
        image_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
        keyword_hits: list[Path] = []
        fallback_hits: list[Path] = []

        for root in search_roots:
            if not root.exists():
                continue
            for candidate in root.rglob("*"):
                if not candidate.is_file() or candidate.suffix.lower() not in image_suffixes:
                    continue
                lowered_name = candidate.name.casefold()
                if self._path_looks_like_logo(lowered_name):
                    keyword_hits.append(candidate)
                elif candidate.is_relative_to(brand_root / "derived-assets"):
                    continue
                else:
                    fallback_hits.append(candidate)

        ordered_candidates = sorted(keyword_hits) + sorted(fallback_hits)
        resolved_paths: list[str] = []
        seen: set[str] = set()
        for candidate in ordered_candidates:
            try:
                relative = str(candidate.relative_to(base_path)).replace("\\", "/")
            except ValueError:
                continue
            if relative in seen:
                continue
            seen.add(relative)
            resolved_paths.append(relative)
        return resolved_paths

    @staticmethod
    def _reusable_asset_looks_like_logo(
        *,
        asset_kind: str,
        label: str,
        storage_path: str,
        normalized_metadata: dict[str, object] | None = None,
        source_metadata: dict[str, object] | None = None,
    ) -> bool:
        if asset_kind == "logo_variant":
            return True
        normalized_metadata = normalized_metadata or {}
        source_metadata = source_metadata or {}
        if str(normalized_metadata.get("review_class") or "").strip().lower() == "logo":
            return True
        combined = " ".join(
            part.casefold()
            for part in [
                label,
                storage_path,
                str(source_metadata.get("source_filename") or ""),
                str(source_metadata.get("origin_category") or ""),
            ]
            if str(part or "").strip()
        )
        return ContentService._path_looks_like_logo(combined)

    @staticmethod
    def _path_looks_like_logo(value: str) -> bool:
        text = str(value or "").casefold()
        return any(token in text for token in ("logo", "wordmark", "brandmark", "lockup", "emblem", "monogram"))

    async def _resolve_request_reference_assets(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        reference_asset_ids: list[UUID],
    ) -> list[dict]:
        assets: list[dict] = []
        seen: set[str] = set()
        for asset_id in reference_asset_ids:
            generated_asset = await self.assets.get_scoped(asset_id, tenant_id, brand_space_id)
            if generated_asset:
                if str(generated_asset.id) not in seen:
                    payload = self._generated_asset_payload(generated_asset)
                    payload["trust_level"] = "trusted"
                    assets.append(payload)
                    seen.add(str(generated_asset.id))
                continue

            knowledge_asset = await self.knowledge_assets.get_scoped(asset_id, tenant_id, brand_space_id)
            if knowledge_asset and str(knowledge_asset.id) not in seen:
                payload = self._knowledge_asset_payload(knowledge_asset)
                if payload["trust_level"] in {"trusted", "usable_with_warning"}:
                    assets.append(payload)
                seen.add(str(knowledge_asset.id))
        return assets

    async def _resolve_brand_reference_assets(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        brand_context: dict,
    ) -> list[dict]:
        visual_identity = brand_context.get("visual_identity", {}) or {}
        asset_ids = [
            *(visual_identity.get("reference_creative_asset_ids", []) or []),
            *(visual_identity.get("mood_board_asset_ids", []) or []),
        ]
        asset_ids.extend(item.get("asset_id") for item in (visual_identity.get("reference_creatives", []) or []) if item.get("asset_id"))
        asset_ids.extend(item.get("asset_id") for item in (visual_identity.get("mood_boards", []) or []) if item.get("asset_id"))
        seen: set[str] = set()
        assets: list[dict] = []
        for reusable_asset in visual_identity.get("reusable_design_assets", []) or []:
            asset_id = str(reusable_asset.get("id", "")).strip()
            if not asset_id or asset_id in seen:
                continue
            payload = self._reusable_asset_payload(reusable_asset)
            if payload["trust_level"] in {"trusted", "usable_with_warning"}:
                assets.append(payload)
            seen.add(asset_id)
        for raw_id in asset_ids:
            try:
                asset_id = UUID(str(raw_id))
            except ValueError:
                continue
            if str(asset_id) in seen:
                continue
            asset = await self.knowledge_assets.get_scoped(asset_id, tenant_id, brand_space_id)
            if not asset:
                continue
            payload = self._knowledge_asset_payload(asset)
            if payload["trust_level"] in {"trusted", "usable_with_warning"}:
                assets.append(payload)
            seen.add(str(asset_id))
        return assets

    def _resolve_render_decorative_assets(self, brand_context: dict) -> list[GeneratedImageAsset]:
        decorative_assets: list[GeneratedImageAsset] = []
        visual_identity = brand_context.get("visual_identity", {}) or {}
        for asset in visual_identity.get("reusable_design_assets", []) or []:
            if asset.get("trust_level") not in {"trusted", "usable_with_warning"}:
                continue
            if asset.get("review_status") != "approved":
                continue
            if asset.get("asset_kind") not in {"icon", "micro_design_element", "decorative_asset", "enhancement_component"}:
                continue
            normalized_metadata = asset.get("normalized_metadata", {}) or {}
            if not normalized_metadata.get("render_eligible", False):
                continue
            storage_path = str(asset.get("storage_path", "")).strip()
            asset_id = self._parse_uuid_or_none(asset.get("id"))
            if not storage_path or not asset_id:
                continue
            decorative_assets.append(
                GeneratedImageAsset(
                    asset_id=asset_id,
                    mime_type=str(asset.get("mime_type", "image/png")),
                    storage_path=storage_path,
                    width=int(asset.get("width") or 0),
                    height=int(asset.get("height") or 0),
                    asset_role=str(asset.get("asset_kind", "decorative_asset")),
                )
            )
            if len(decorative_assets) >= 4:
                break
        return decorative_assets

    @staticmethod
    def _resolve_render_font_assets(brand_context: dict) -> list[str]:
        visual_identity = brand_context.get("visual_identity", {}) or {}
        typography = visual_identity.get("typography", {}) or {}
        font_paths: list[str] = []
        seen: set[str] = set()
        for asset in typography.get("uploaded_font_assets", []) or []:
            if asset.get("trust_level") == "excluded":
                continue
            storage_path = str(asset.get("storage_path", "")).strip()
            if not storage_path or storage_path in seen:
                continue
            seen.add(storage_path)
            font_paths.append(storage_path)
        return font_paths

    @staticmethod
    def _resolve_blueprint_payload(
        stored_blueprint: dict,
        template_zone_map: dict | None,
        override_blueprint: dict | None,
        studio_panel: dict,
    ) -> dict:
        if override_blueprint:
            blueprint = deepcopy(override_blueprint)
        else:
            blueprint = deepcopy(stored_blueprint or {})
        if template_zone_map and template_zone_map.get("zones") and not override_blueprint:
            blueprint["zones"] = template_zone_map["zones"]
            blueprint["layout_type"] = template_zone_map.get("layout_type", blueprint.get("layout_type", "template"))
        if studio_panel.get("platform_preset"):
            blueprint["platform_preset"] = studio_panel["platform_preset"]
        if studio_panel.get("file_type"):
            blueprint["export_format"] = studio_panel["file_type"]
        blueprint.setdefault(
            "source_mode",
            "exact_template" if template_zone_map and template_zone_map.get("zones") else "synthesized_layout",
        )
        blueprint.setdefault("source_template_id", None)
        blueprint.setdefault("layout_archetype", None)
        blueprint.setdefault("adaptation_plan", {})
        adaptation_plan = blueprint.get("adaptation_plan") if isinstance(blueprint.get("adaptation_plan"), dict) else {}
        if (
            str(blueprint.get("source_mode") or "").strip().lower() == "synthesized_layout"
            or adaptation_plan.get("reference_style_only")
            or adaptation_plan.get("topic_fit_too_weak")
        ):
            blueprint["source_mode"] = "synthesized_layout"
            blueprint["source_template_id"] = None
        blueprint.setdefault("brand_rules_applied", {})
        blueprint.setdefault("composition_plan", {})
        default_blueprint = BlueprintService().build(
            text_payload={
                "headline": "",
                "body": "",
                "cta": "",
            },
            studio_panel=studio_panel,
            template_metadata=None,
            layout_decision={
                "mode": blueprint.get("source_mode", "synthesized_layout"),
                "template_id": blueprint.get("source_template_id"),
                "adaptation_plan": blueprint.get("adaptation_plan", {}),
            },
            brand_context={},
        )
        resolved_canvas_size = studio_panel.get("size") or {
            "width": max((zone.x + zone.width for zone in default_blueprint.zones), default=0),
            "height": max((zone.y + zone.height for zone in default_blueprint.zones), default=0),
        }
        blueprint["zones"] = BlueprintService.resolve_zone_payloads(
            blueprint.get("zones"),
            default_blueprint.zones,
            canvas_size=resolved_canvas_size,
        )
        return blueprint

    @staticmethod
    def _resolve_scene_graph_payload(
        stored_scene_graph: dict | None,
        studio_panel: dict,
    ) -> dict | None:
        if not stored_scene_graph:
            return None
        scene_graph = deepcopy(stored_scene_graph)
        canvas = dict(scene_graph.get("canvas") or {})
        size = studio_panel.get("size") or {}
        canvas["width"] = int(size.get("width") or canvas.get("width") or 1080)
        canvas["height"] = int(size.get("height") or canvas.get("height") or 1080)
        if studio_panel.get("platform_preset"):
            canvas["platform"] = studio_panel["platform_preset"]
        if studio_panel.get("file_type"):
            canvas["file_type"] = studio_panel["file_type"]
        canvas.setdefault("safe_margin", 48)
        scene_graph["canvas"] = canvas
        scene_graph.setdefault("layout_mode", "synthesized_layout")
        scene_graph.setdefault("layers", ["background", "decorative", "primary_visual", "content", "brand", "footer"])
        scene_graph.setdefault("elements", [])
        scene_graph.setdefault("styles", {})
        scene_graph.setdefault("assets", [])
        scene_graph.setdefault("template_adaptation", {})
        scene_graph.setdefault("validation_hints", {})
        return scene_graph

    @staticmethod
    def _supports_ai_final_render_export(studio_panel: dict | None, explainability: dict | None) -> bool:
        if not isinstance(studio_panel, dict):
            return False
        if not isinstance(explainability, dict):
            return False
        if str(explainability.get("render_authority") or "").strip().lower() != "ai":
            return False
        if not ContentService._requires_ai_final_render_for_panel(studio_panel):
            return False
        return True

    @staticmethod
    def _requires_ai_final_render_for_panel(studio_panel: dict | None) -> bool:
        if not isinstance(studio_panel, dict):
            return False
        format_name = str(studio_panel.get("format") or "").strip().lower()
        file_type = str(studio_panel.get("file_type") or "").strip().lower()
        return format_name in ContentService.AI_FINAL_RENDER_FORMATS and file_type in {"png", "jpg", "pdf", "doc"}

    @classmethod
    def _effective_generate_image_requested(
        cls,
        *,
        studio_panel: dict | None,
        generate_image: bool | None,
    ) -> bool:
        if cls._requires_ai_final_render_for_panel(studio_panel):
            return True
        return bool(generate_image)

    @staticmethod
    def _assert_research_guard(*, prompt: str, brief: dict[str, Any], stage: str) -> None:
        guard = brief.get("research_guard") if isinstance(brief.get("research_guard"), dict) else {}
        if not guard or not bool(guard.get("hard_fail")):
            return
        raise GenerationFailureError(
            str(guard.get("reason") or "Research-backed generation requirements were not met."),
            failure_type="missing_research",
            reason_code="research_backing_required",
            user_safe_message=(
                "I couldn't generate this visual safely because the prompt needs externally verified research, "
                "but live source verification was unavailable. Please try again or attach a supporting source."
            ),
            retryable=True,
            rule_source="system",
            suggested_next_action="Retry with live research available or upload a supporting source.",
            details={"stage": stage, "prompt_excerpt": str(prompt or "")[:180]},
        )

    @staticmethod
    def _sort_ai_final_render_assets(assets: list[GeneratedAsset]) -> list[GeneratedAsset]:
        return sorted(
            assets,
            key=lambda asset: (
                int((asset.metadata_json or {}).get("slide_index") or 999),
                str(asset.asset_role or ""),
                str(asset.storage_path or ""),
            ),
        )

    @staticmethod
    def _find_ai_final_render_assets(
        assets: list[GeneratedAsset],
        explainability: dict | None,
        studio_panel: dict | None,
    ) -> list[GeneratedAsset]:
        if not ContentService._supports_ai_final_render_export(studio_panel, explainability):
            return []
        explainability = explainability or {}
        preferred_assets = explainability.get("final_render_assets") or []
        preferred_paths = [
            str(item.get("storage_path") or "").strip()
            for item in preferred_assets
            if isinstance(item, dict) and str(item.get("storage_path") or "").strip()
        ]
        if not preferred_paths:
            final_render_asset = explainability.get("final_render_asset") or {}
            preferred_path = str(final_render_asset.get("storage_path") or "").strip()
            if preferred_path:
                preferred_paths = [preferred_path]
        matching_assets = [
            asset
            for asset in assets
            if (asset.metadata_json or {}).get("render_source") == "ai"
            and (asset.metadata_json or {}).get("generation_stage") == "final_render"
        ]
        if preferred_paths:
            ordered_assets: list[GeneratedAsset] = []
            seen_paths: set[str] = set()
            for preferred_path in preferred_paths:
                for asset in matching_assets:
                    if asset.storage_path == preferred_path and asset.storage_path not in seen_paths:
                        ordered_assets.append(asset)
                        seen_paths.add(asset.storage_path)
                        break
            for asset in ContentService._sort_ai_final_render_assets(matching_assets):
                if asset.storage_path not in seen_paths:
                    ordered_assets.append(asset)
            if ordered_assets:
                return ordered_assets
        if matching_assets:
            return ContentService._sort_ai_final_render_assets(matching_assets)
        if preferred_paths:
            ordered_assets = []
            seen_paths: set[str] = set()
            for preferred_path in preferred_paths:
                for asset in assets:
                    if asset.storage_path == preferred_path and asset.storage_path not in seen_paths:
                        ordered_assets.append(asset)
                        seen_paths.add(asset.storage_path)
                        break
            if ordered_assets:
                return ContentService._sort_ai_final_render_assets(ordered_assets)
        return []

    @staticmethod
    def _should_render_missing_ai_final_assets_for_rewrite(
        *,
        content: ContentVersion,
        ai_final_render_assets: list[GeneratedAsset],
        explainability: dict | None,
        selective_regeneration_plan: dict[str, object] | None,
    ) -> bool:
        if ai_final_render_assets:
            return False
        explainability = explainability or {}
        if str(explainability.get("render_authority") or "").strip().lower() != "ai":
            return False
        plan = selective_regeneration_plan or {}
        targeted_slide_indexes = [
            value
            for value in (plan.get("targeted_slide_indexes") or [])
            if str(value).strip()
        ]
        if not targeted_slide_indexes:
            return False
        rewrite_source_content_version_id = (
            str(plan.get("rewrite_source_content_version_id") or "").strip()
            or str(explainability.get("rewrite_source_content_version_id") or "").strip()
            or str(content.parent_version_id or "").strip()
        )
        return bool(rewrite_source_content_version_id)

    async def _regenerate_ai_final_render_assets_for_rewrite(
        self,
        *,
        tenant_id: UUID,
        brand_space_id: UUID,
        content: ContentVersion,
        brand,
        explainability: dict[str, Any],
        studio_panel: dict[str, Any],
        trace_id: str | None,
        logo_asset_path: str | None,
        logo_candidates: list[dict[str, object]] | None = None,
    ) -> list[GeneratedAsset]:
        session = await self.sessions.get(content.session_id)
        if not session:
            raise NotFoundError("Session not found for AI final render regeneration.")

        request = AIOrchestrationRequest(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            user_id=content.created_by,
            prompt=content.prompt,
            studio_panel=studio_panel,
            conversation_context=session.conversational_context or {},
            session_memory=deepcopy(explainability.get("session_memory") or {}),
            resolved_brand_context=dict(getattr(brand, "resolved_brand_context", {}) or explainability.get("brand_context_snapshot") or {}),
            persona_context=dict(explainability.get("selected_persona") or {}),
            objective_context=dict(explainability.get("selected_objective") or {}),
            retrieved_knowledge={},
            template_context=None,
            content_format_guide=self.content_format_guide.load(),
            live_research=deepcopy(explainability.get("live_research") or {}),
            research_editorial_brief=deepcopy(explainability.get("research_editorial_brief") or {}),
            format_family_plan=deepcopy(explainability.get("format_family_plan") or {}),
            content_plan=deepcopy(explainability.get("content_plan") or {}),
            visual_plan=deepcopy(explainability.get("visual_plan") or {}),
            template_candidates=list(((explainability.get("planning_hints") or {}) if isinstance(explainability.get("planning_hints"), dict) else {}).get("template_recommendations") or []),
            layout_decision=deepcopy(explainability.get("planning_hints") or explainability.get("layout_decision") or {}),
            reference_assets=[],
            asset_catalog=[],
            logo_asset_path=logo_asset_path,
            logo_asset_candidates=[dict(item) for item in (logo_candidates or []) if isinstance(item, dict)],
            platform_constraints={
                "platform_preset": studio_panel.get("platform_preset"),
                "format": studio_panel.get("format"),
                "file_type": studio_panel.get("file_type"),
                "size": studio_panel.get("size") or {},
            },
            resolution_policy=dict((getattr(brand, "resolved_brand_context", {}) or {}).get("context_priority", {}) or {}),
            validation_report=deepcopy(explainability.get("validation_report") or {}),
            generation_trace_id=trace_id,
            generate_image=True,
        )
        text_payload = StructuredTextPayload.model_validate(content.generated_payload or {})
        creative_decision = CreativeDecisionPayload.model_validate(
            explainability.get("creative_decision") or explainability.get("layout_decision") or {}
        )
        scene_graph = GenerationSceneGraph.model_validate(
            self._resolve_scene_graph_payload(
                stored_scene_graph=explainability.get("scene_graph"),
                studio_panel=studio_panel,
            )
        )
        message_strategy = MessageStrategyPayload.model_validate(explainability.get("message_strategy") or {})
        validation_report = SceneGraphValidationReport.model_validate(explainability.get("validation_report") or {})
        selected_reference_images = [
            dict(item)
            for item in (explainability.get("selected_reference_images") or [])
            if isinstance(item, dict)
        ]
        conditioning_reference_images = [
            dict(item)
            for item in (explainability.get("conditioning_reference_images") or [])
            if isinstance(item, dict)
        ]
        final_render_assets, final_render_asset, _text_payload, final_render_scene_graph = self.orchestrator.render_final_assets_only(
            request=request,
            text_payload=text_payload,
            creative_decision=creative_decision,
            scene_graph=scene_graph,
            message_strategy=message_strategy,
            validation_report=validation_report,
            generation_path=str(explainability.get("generation_path") or "image_led_social"),
            selected_reference_images=selected_reference_images,
            conditioning_reference_images=conditioning_reference_images,
            compiled_context=deepcopy(explainability.get("compiled_context") or {}),
            quality_assessment=deepcopy(explainability.get("quality_assessment") or {}),
            quality_retry_attempts=int(explainability.get("quality_retry_attempts") or 0),
            fresh_replan_attempted=bool(explainability.get("fresh_replan_attempted")),
        )

        existing_assets = await self.assets.list_by_content(content.id)
        for asset in existing_assets:
            metadata = asset.metadata_json or {}
            if metadata.get("render_source") == "ai" and metadata.get("generation_stage") == "final_render":
                await self.assets.delete(asset)

        persisted_assets: list[GeneratedAsset] = []
        for index, asset in enumerate(final_render_assets, start=1):
            persisted_assets.append(
                await self.assets.add(
                    GeneratedAsset(
                        tenant_id=tenant_id,
                        brand_space_id=brand_space_id,
                        content_version_id=content.id,
                        template_id=content.selected_template_id,
                        asset_role=AssetRole.RENDER_PREVIEW if index == 1 else AssetRole.RENDER_EXPORT,
                        mime_type=asset.mime_type,
                        storage_path=asset.storage_path,
                        width=asset.width,
                        height=asset.height,
                        metadata_json={
                            **(asset.metadata or {}),
                            "render_source": "ai",
                            "generation_stage": "final_render",
                            "slide_index": int((asset.metadata or {}).get("slide_index") or index),
                            "slide_count": int((asset.metadata or {}).get("slide_count") or len(final_render_assets)),
                        },
                    )
                )
            )

        content.explainability_metadata = {
            **dict(explainability or {}),
            "render_authority": "ai",
            "scene_graph": final_render_scene_graph.model_dump(mode="json"),
            "final_render_assets": [asset.model_dump(mode="json") for asset in final_render_assets],
            "final_render_asset": final_render_asset.model_dump(mode="json") if final_render_asset else None,
        }
        await self.session.flush()
        self.trace.write_payload(
            trace_id,
            "rewritten_ai_final_render_regenerated",
            {
                "content_version_id": str(content.id),
                "asset_count": len(persisted_assets),
                "storage_paths": [asset.storage_path for asset in persisted_assets],
            },
        )
        return persisted_assets

    @staticmethod
    def _find_ai_final_render_asset(
        assets: list[GeneratedAsset],
        explainability: dict | None,
        studio_panel: dict | None,
    ) -> GeneratedAsset | None:
        resolved = ContentService._find_ai_final_render_assets(assets, explainability, studio_panel)
        return resolved[0] if resolved else None

    @staticmethod
    def _selected_reference_visual_assets(
        explainability: dict | None,
        *,
        allow_literal_reference_surfaces: bool = True,
    ) -> list[GeneratedImageAsset]:
        explainability = explainability or {}
        selected_assets = explainability.get("selected_reference_images") or []
        results: list[GeneratedImageAsset] = []
        seen: set[str] = set()
        for asset in selected_assets:
            if not isinstance(asset, dict):
                continue
            if (
                not allow_literal_reference_surfaces
                and ContentService._is_literal_reference_surface_asset(asset)
                and not ContentService._asset_allows_literal_render(asset)
            ):
                continue
            storage_path = str(asset.get("storage_path") or "").strip()
            if not storage_path or storage_path in seen:
                continue
            seen.add(storage_path)
            try:
                results.append(
                    GeneratedImageAsset(
                        asset_id=UUID(str(asset.get("asset_id"))) if str(asset.get("asset_id") or "").strip() else uuid4(),
                        mime_type=str(asset.get("mime_type") or "image/png"),
                        storage_path=storage_path,
                        width=int(asset.get("width") or 0),
                        height=int(asset.get("height") or 0),
                        asset_role=str(asset.get("asset_role") or AssetRole.REFERENCE_CREATIVE),
                        metadata={
                            "source": "selected_reference_asset",
                            "label": str(((asset.get("metadata") or {}) if isinstance(asset.get("metadata"), dict) else {}).get("label") or ""),
                            "trust_level": str(asset.get("trust_level") or ""),
                        },
                    )
                )
            except ValueError:
                continue
        return results

    @staticmethod
    def _asset_role_value(asset: GeneratedImageAsset | dict[str, object]) -> str:
        if isinstance(asset, GeneratedImageAsset):
            return str(asset.asset_role or "").strip().casefold()
        if isinstance(asset, dict):
            return str(asset.get("asset_role") or "").strip().casefold()
        return ""

    @staticmethod
    def _asset_metadata_value(asset: GeneratedImageAsset | dict[str, object]) -> dict[str, object]:
        if isinstance(asset, GeneratedImageAsset):
            return dict(asset.metadata or {})
        if isinstance(asset, dict):
            metadata = asset.get("metadata")
            if isinstance(metadata, dict):
                return dict(metadata)
        return {}

    @classmethod
    def _is_literal_reference_surface_asset(cls, asset: GeneratedImageAsset | dict[str, object]) -> bool:
        role = cls._asset_role_value(asset)
        return role in {
            str(AssetRole.REFERENCE_CREATIVE),
            str(AssetRole.TEMPLATE_PREVIEW),
            "template",
        }

    @classmethod
    def _asset_allows_literal_render(cls, asset: GeneratedImageAsset | dict[str, object]) -> bool:
        metadata = cls._asset_metadata_value(asset)
        return bool(
            metadata.get("literal_render_allowed")
            or metadata.get("renderer_safe_reference")
            or metadata.get("use_as_content_image")
        )

    @classmethod
    def _should_filter_literal_reference_surfaces_for_render(
        cls,
        *,
        creative_decision: dict | None,
        scene_graph: dict | None,
        blueprint: dict | None,
    ) -> bool:
        decision = creative_decision or {}
        graph = scene_graph or {}
        resolved_blueprint = blueprint or {}
        layout_mode = str(
            decision.get("layout_mode")
            or graph.get("layout_mode")
            or resolved_blueprint.get("source_mode")
            or ""
        ).strip().lower()
        graph_adaptation = graph.get("template_adaptation") if isinstance(graph.get("template_adaptation"), dict) else {}
        blueprint_adaptation = resolved_blueprint.get("adaptation_plan") if isinstance(resolved_blueprint.get("adaptation_plan"), dict) else {}
        review_flags = {
            str(flag).strip()
            for flag in (
                list(decision.get("review_flags") or [])
                + list(graph_adaptation.get("review_flags") or [])
                + list(blueprint_adaptation.get("review_flags") or [])
            )
            if str(flag).strip()
        }
        return bool(
            layout_mode == "synthesized_layout"
            or graph_adaptation.get("reference_style_only")
            or blueprint_adaptation.get("reference_style_only")
            or graph_adaptation.get("topic_fit_too_weak")
            or blueprint_adaptation.get("topic_fit_too_weak")
            or "template_topic_mismatch" in review_flags
            or "template_text_overlay_risk" in review_flags
        )

    @classmethod
    def _filter_literal_reference_surface_assets(
        cls,
        assets: list[GeneratedImageAsset],
    ) -> list[GeneratedImageAsset]:
        return [
            asset
            for asset in assets
            if not cls._is_literal_reference_surface_asset(asset) or cls._asset_allows_literal_render(asset)
        ]

    @classmethod
    def _sanitize_scene_graph_for_structured_render(
        cls,
        scene_graph: dict | None,
        *,
        filter_literal_reference_surfaces: bool,
    ) -> dict | None:
        if not scene_graph or not filter_literal_reference_surfaces:
            return scene_graph
        sanitized = deepcopy(scene_graph)
        assets = sanitized.get("assets")
        if isinstance(assets, list):
            sanitized["assets"] = [
                asset
                for asset in assets
                if not cls._is_literal_reference_surface_asset(asset) or cls._asset_allows_literal_render(asset)
            ]
        for element in sanitized.get("elements", []) or []:
            if not isinstance(element, dict):
                continue
            asset_payload = element.get("asset")
            if cls._is_literal_reference_surface_asset(asset_payload) and not cls._asset_allows_literal_render(asset_payload):
                element.pop("asset", None)
        return sanitized

    @staticmethod
    def _ai_export_file_type(studio_panel: dict | None) -> str:
        file_type = str((studio_panel or {}).get("file_type") or "").strip().lower()
        return file_type if file_type in {"png", "jpg", "pdf", "doc"} else "png"

    def _read_ai_final_render_image(self, storage_path: str) -> Image.Image:
        with open_image_asset(self.storage.absolute_path(storage_path)) as raw_image:
            return raw_image.convert("RGBA")

    @staticmethod
    def _edge_background_should_strip(image: Image.Image, threshold: int = 245) -> bool:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        if width <= 0 or height <= 0:
            return False
        edge_pixels: list[tuple[int, int, int, int]] = []
        pixels = rgba.load()
        for x in range(width):
            edge_pixels.append(pixels[x, 0])
            edge_pixels.append(pixels[x, height - 1])
        for y in range(1, max(height - 1, 1)):
            edge_pixels.append(pixels[0, y])
            edge_pixels.append(pixels[width - 1, y])
        opaque_edges = [pixel for pixel in edge_pixels if pixel[3] > 0]
        if not opaque_edges:
            return False
        light_edges = [
            pixel
            for pixel in opaque_edges
            if pixel[0] >= threshold and pixel[1] >= threshold and pixel[2] >= threshold
        ]
        return (len(light_edges) / len(opaque_edges)) >= 0.75

    @staticmethod
    def _edge_matte_color(image: Image.Image) -> tuple[int, int, int] | None:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        if width <= 2 or height <= 2:
            return None
        pixels = rgba.load()
        edge_pixels: list[tuple[int, int, int, int]] = []
        for x in range(width):
            edge_pixels.append(pixels[x, 0])
            edge_pixels.append(pixels[x, height - 1])
        for y in range(1, max(height - 1, 1)):
            edge_pixels.append(pixels[0, y])
            edge_pixels.append(pixels[width - 1, y])
        opaque_edges = [pixel for pixel in edge_pixels if pixel[3] > 220]
        if not opaque_edges:
            return None
        reds = sorted(pixel[0] for pixel in opaque_edges)
        greens = sorted(pixel[1] for pixel in opaque_edges)
        blues = sorted(pixel[2] for pixel in opaque_edges)
        matte = (
            int(reds[len(reds) // 2]),
            int(greens[len(greens) // 2]),
            int(blues[len(blues) // 2]),
        )
        tolerance = 22
        matched = [
            pixel
            for pixel in opaque_edges
            if abs(pixel[0] - matte[0]) <= tolerance
            and abs(pixel[1] - matte[1]) <= tolerance
            and abs(pixel[2] - matte[2]) <= tolerance
        ]
        return matte if (len(matched) / len(opaque_edges)) >= 0.82 else None

    @classmethod
    def _strip_logo_background_if_safe(cls, image: Image.Image) -> Image.Image:
        rgba = image.convert("RGBA")
        matte = cls._edge_matte_color(rgba)
        if matte is None and not cls._edge_background_should_strip(rgba):
            return rgba
        width, height = rgba.size
        pixels = rgba.load()
        keep = [[True for _ in range(width)] for _ in range(height)]
        queue: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()

        def is_background(px: tuple[int, int, int, int]) -> bool:
            red, green, blue, alpha = px
            if alpha <= 0:
                return False
            if matte is not None:
                return (
                    abs(red - matte[0]) <= 26
                    and abs(green - matte[1]) <= 26
                    and abs(blue - matte[2]) <= 26
                )
            return red >= 245 and green >= 245 and blue >= 245

        for x in range(width):
            queue.append((x, 0))
            queue.append((x, height - 1))
        for y in range(height):
            queue.append((0, y))
            queue.append((width - 1, y))

        while queue:
            x, y = queue.pop()
            if (x, y) in seen or x < 0 or y < 0 or x >= width or y >= height:
                continue
            seen.add((x, y))
            if not is_background(pixels[x, y]):
                continue
            keep[y][x] = False
            queue.extend(((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))

        cleaned = rgba.copy()
        cleaned_pixels = cleaned.load()
        for y in range(height):
            for x in range(width):
                if not keep[y][x]:
                    red, green, blue, _alpha = cleaned_pixels[x, y]
                    cleaned_pixels[x, y] = (red, green, blue, 0)
        return cleaned

    @staticmethod
    def _flatten_image_for_jpg(image: Image.Image) -> Image.Image:
        if image.mode != "RGBA":
            return image.convert("RGB")
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.getchannel("A"))
        return background

    def _store_ai_final_render_image(
        self,
        *,
        content: ContentVersion,
        image: Image.Image,
        filename_prefix: str,
        suffix: str = "png",
        quality: int = 92,
    ) -> dict:
        buffer = BytesIO()
        if suffix == "jpg":
            self._flatten_image_for_jpg(image).save(buffer, format="JPEG", quality=quality, optimize=True)
            mime_type = "image/jpeg"
        else:
            image.save(buffer, format="PNG")
            mime_type = "image/png"
        stored = self.storage.save_bytes(
            content.tenant_id,
            content.brand_space_id,
            "generated",
            f"{filename_prefix}-{content.brand_space_id}-{uuid4().hex}.{suffix}",
            buffer.getvalue(),
        )
        return {
            "asset_id": str(uuid4()),
            "asset_role": str(AssetRole.RENDER_EXPORT),
            "mime_type": mime_type,
            "storage_path": stored.storage_path,
            "width": image.width,
            "height": image.height,
        }

    def _build_ai_final_render_pdf_export(
        self,
        *,
        content: ContentVersion,
        source_assets: list[dict[str, object]],
    ) -> dict | None:
        if not source_assets:
            return None
        buffer = BytesIO()
        pdf = pdf_canvas.Canvas(buffer)
        for asset in source_assets:
            with open_image_asset(self.storage.absolute_path(str(asset.get("storage_path") or ""))) as raw_image:
                image = raw_image.convert("RGB")
            width, height = image.size
            pdf.setPageSize((width, height))
            pdf.drawImage(ImageReader(image), 0, 0, width=width, height=height, preserveAspectRatio=True, mask="auto")
            pdf.showPage()
        pdf.save()
        stored = self.storage.save_bytes(
            content.tenant_id,
            content.brand_space_id,
            "generated",
            f"export-{content.brand_space_id}-{uuid4().hex}.pdf",
            buffer.getvalue(),
        )
        return {
            "asset_id": str(uuid4()),
            "asset_role": str(AssetRole.RENDER_EXPORT),
            "mime_type": "application/pdf",
            "storage_path": stored.storage_path,
            "width": None,
            "height": None,
        }

    def _build_ai_final_render_doc_export(
        self,
        *,
        content: ContentVersion,
        source_assets: list[dict[str, object]],
    ) -> dict | None:
        if not source_assets:
            return None
        document = Document()
        for index, asset in enumerate(source_assets):
            with open_image_asset(self.storage.absolute_path(str(asset.get("storage_path") or ""))) as raw_image:
                image = raw_image.convert("RGB")
            image_buffer = BytesIO()
            image.save(image_buffer, format="PNG")
            image_buffer.seek(0)
            document.add_picture(image_buffer, width=Inches(6.5))
            if index < len(source_assets) - 1:
                document.add_page_break()
        buffer = BytesIO()
        document.save(buffer)
        stored = self.storage.save_bytes(
            content.tenant_id,
            content.brand_space_id,
            "generated",
            f"export-{content.brand_space_id}-{uuid4().hex}.docx",
            buffer.getvalue(),
        )
        return {
            "asset_id": str(uuid4()),
            "asset_role": str(AssetRole.RENDER_EXPORT),
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "storage_path": stored.storage_path,
            "width": None,
            "height": None,
        }

    def _build_ai_final_render_export_assets(
        self,
        *,
        content: ContentVersion,
        source_assets: list[dict[str, object]],
        file_type: str,
    ) -> list[dict]:
        if file_type == "png":
            return [
                self._decorate_asset_reference({**asset, "asset_role": str(AssetRole.RENDER_EXPORT)})
                for asset in source_assets
            ]
        if file_type == "jpg":
            converted: list[dict] = []
            for asset in source_assets:
                with open_image_asset(self.storage.absolute_path(str(asset.get("storage_path") or ""))) as raw_image:
                    image = raw_image.convert("RGBA")
                jpg_asset = self._store_ai_final_render_image(
                    content=content,
                    image=image,
                    filename_prefix="export",
                    suffix="jpg",
                )
                converted.append(self._decorate_asset_reference(jpg_asset))
            return converted
        if file_type == "pdf":
            pdf_asset = self._build_ai_final_render_pdf_export(content=content, source_assets=source_assets)
            return [self._decorate_asset_reference(pdf_asset)] if pdf_asset else []
        if file_type == "doc":
            doc_asset = self._build_ai_final_render_doc_export(content=content, source_assets=source_assets)
            return [self._decorate_asset_reference(doc_asset)] if doc_asset else []
        return [
            self._decorate_asset_reference({**asset, "asset_role": str(AssetRole.RENDER_EXPORT)})
            for asset in source_assets
        ]

    def _build_ai_final_render_export_payload(
        self,
        *,
        content: ContentVersion,
        asset: GeneratedAsset,
        explainability: dict,
        studio_panel: dict,
        selected_template_id: UUID | None,
        logo_asset_path: str | None,
        logo_asset_candidates: list[dict[str, object]] | None = None,
        logo_selection: dict[str, object] | None = None,
    ) -> dict:
        return self._build_ai_final_render_export_payloads(
            content=content,
            assets=[asset],
            explainability=explainability,
            studio_panel=studio_panel,
            selected_template_id=selected_template_id,
            logo_asset_path=logo_asset_path,
            logo_asset_candidates=logo_asset_candidates,
            logo_selection=logo_selection,
        )

    def _build_ai_final_render_export_payloads(
        self,
        *,
        content: ContentVersion,
        assets: list[GeneratedAsset],
        explainability: dict,
        studio_panel: dict,
        selected_template_id: UUID | None,
        logo_asset_path: str | None,
        logo_asset_candidates: list[dict[str, object]] | None = None,
        logo_selection: dict[str, object] | None = None,
    ) -> dict:
        if not assets:
            return {"preview_asset": None, "export_assets": [], "renderer_metadata": {}}

        ordered_assets = self._sort_ai_final_render_assets(assets)
        source_assets: list[dict[str, object]] = []
        render_manifest_assets: list[dict[str, object]] = []
        any_logo_rendered = False
        any_footer_rendered = False

        for index, asset in enumerate(ordered_assets, start=1):
            composited_asset = self._build_ai_logo_fallback_asset(
                content=content,
                asset=asset,
                explainability=explainability,
                studio_panel=studio_panel,
                logo_asset_path=logo_asset_path,
                logo_asset_candidates=logo_asset_candidates,
                logo_selection=logo_selection,
            )
            footer_source_asset = self._payload_to_generated_image_asset(
                composited_asset,
                fallback_asset=asset,
            ) if composited_asset else asset
            footer_asset = self._build_ai_footer_fallback_asset(
                content=content,
                asset=footer_source_asset,
                explainability=explainability,
                studio_panel=studio_panel,
            )
            source_asset_payload = footer_asset or composited_asset or self._generated_asset_payload(asset)
            source_assets.append(source_asset_payload)
            render_manifest_assets.append(
                {
                    "slide_index": int((asset.metadata_json or {}).get("slide_index") or index),
                    "slide_count": int((asset.metadata_json or {}).get("slide_count") or len(ordered_assets)),
                    "storage_path": source_asset_payload.get("storage_path"),
                    "source_storage_path": asset.storage_path,
                    "carousel_role": (asset.metadata_json or {}).get("carousel_role"),
                    "logo_fallback_composited": bool(composited_asset),
                    "legal_footer_fallback_composited": bool(footer_asset),
                    "logo_overlay_strategy": (source_asset_payload.get("metadata") or {}).get("logo_overlay_strategy"),
                }
            )
            any_logo_rendered = any_logo_rendered or bool((asset.metadata_json or {}).get("logo_composited_by_ai")) or bool(composited_asset)
            any_footer_rendered = any_footer_rendered or bool(footer_asset)

        preview_asset = self._decorate_asset_reference(
            {
                **source_assets[0],
                "asset_role": str(AssetRole.RENDER_PREVIEW),
            }
        )
        file_type = self._ai_export_file_type(studio_panel)
        export_assets = self._build_ai_final_render_export_assets(
            content=content,
            source_assets=source_assets,
            file_type=file_type,
        )

        render_metadata = {
            "layout_variant": "ai_final_render_carousel" if len(ordered_assets) > 1 else "ai_final_render",
            "render_authority": "ai",
            "template_rendered": False,
            "logo_rendered": any_logo_rendered,
            "image_rendered": True,
            "decorative_rendered": False,
            "scene_graph_used": bool(explainability.get("scene_graph")),
            "template_id": str(selected_template_id) if selected_template_id else None,
            "logo_asset_path": logo_asset_path,
            "page_count": len(ordered_assets),
            "output_file_type": file_type,
            "render_manifest": {
                "scene_graph": explainability.get("scene_graph"),
                "direct_asset_export": True,
                "generation_path": explainability.get("generation_path"),
                "carousel_slide_count": len(ordered_assets),
                "logo_fallback_composited": any(item.get("logo_fallback_composited") for item in render_manifest_assets),
                "legal_footer_fallback_composited": any(item.get("legal_footer_fallback_composited") for item in render_manifest_assets),
                "assets": render_manifest_assets,
            },
            "legal_footer_rendered": any_footer_rendered,
        }
        return {
            "preview_asset": preview_asset,
            "export_assets": export_assets,
            "renderer_metadata": render_metadata,
        }

    @staticmethod
    def _coerce_ai_logo_box(
        candidate: dict | None,
        *,
        canvas_width: int,
        canvas_height: int,
        units: str | None = None,
    ) -> tuple[int, int, int, int] | None:
        if not isinstance(candidate, dict):
            return None
        geometry = candidate.get("geometry") if isinstance(candidate.get("geometry"), dict) else candidate
        try:
            raw_x = float(geometry.get("x", 0))
            raw_y = float(geometry.get("y", 0))
            raw_width = float(geometry.get("width", 0))
            raw_height = float(geometry.get("height", 0))
        except (TypeError, ValueError):
            return None
        resolved_units = str(units or geometry.get("units") or candidate.get("units") or "").strip().lower()
        looks_normalized = max(abs(raw_x), abs(raw_y), abs(raw_width), abs(raw_height)) <= 1.5
        if resolved_units == "normalized" or (not resolved_units and looks_normalized):
            x = int(round(raw_x * canvas_width))
            y = int(round(raw_y * canvas_height))
            width = int(round(raw_width * canvas_width))
            height = int(round(raw_height * canvas_height))
        else:
            x = int(round(raw_x))
            y = int(round(raw_y))
            width = int(round(raw_width))
            height = int(round(raw_height))
        if width <= 0 or height <= 0:
            return None
        x = max(0, min(x, max(canvas_width - 1, 0)))
        y = max(0, min(y, max(canvas_height - 1, 0)))
        width = max(1, min(width, max(canvas_width - x, 1)))
        height = max(1, min(height, max(canvas_height - y, 1)))
        return (x, y, width, height)

    @classmethod
    def _logo_anchor_from_hint(cls, hint: str | None) -> tuple[str, str] | None:
        text = str(hint or "").strip().lower()
        if not text:
            return None
        vertical = "top" if "top" in text else ("bottom" if "bottom" in text else "middle")
        horizontal = "right" if "right" in text else ("left" if "left" in text else "center")
        if vertical == "middle" and horizontal == "center":
            return None
        return (vertical, horizontal)

    @staticmethod
    def _logo_anchor_from_box(
        box: tuple[int, int, int, int],
        *,
        canvas_width: int,
        canvas_height: int,
    ) -> tuple[str, str]:
        x, y, width, height = box
        center_x = x + (width / 2.0)
        center_y = y + (height / 2.0)
        vertical = "top" if center_y <= (canvas_height * 0.35) else ("bottom" if center_y >= (canvas_height * 0.65) else "middle")
        horizontal = "left" if center_x <= (canvas_width * 0.35) else ("right" if center_x >= (canvas_width * 0.65) else "center")
        return (vertical, horizontal)

    @staticmethod
    def _logo_box_profile_for_format(
        *,
        canvas_width: int,
        canvas_height: int,
        format_name: str,
    ) -> tuple[int, int]:
        normalized_format = str(format_name or "").strip().lower()
        if normalized_format == "carousel":
            width = max(int(canvas_width * 0.24), 200)
            height = max(int(canvas_height * 0.1), 72)
        elif normalized_format == "infographic":
            width = max(int(canvas_width * 0.22), 190)
            height = max(int(canvas_height * 0.095), 68)
        else:
            aspect_ratio = canvas_width / max(canvas_height, 1)
            if aspect_ratio >= 1.3:
                width = max(int(canvas_width * 0.18), 180)
                height = max(int(canvas_height * 0.09), 60)
            else:
                width = max(int(canvas_width * 0.19), 180)
                height = max(int(canvas_height * 0.085), 60)
        return (min(width, canvas_width), min(height, canvas_height))

    @classmethod
    def _default_ai_logo_box(
        cls,
        *,
        canvas_width: int,
        canvas_height: int,
        format_name: str,
        anchor: tuple[str, str] | None,
        reference_box: tuple[int, int, int, int] | None = None,
    ) -> tuple[int, int, int, int]:
        margin_x = max(int(canvas_width * 0.04), 24)
        margin_y = max(int(canvas_height * 0.04), 24)
        width, height = cls._logo_box_profile_for_format(
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            format_name=format_name,
        )
        if reference_box is not None:
            ref_x, ref_y, ref_width, ref_height = reference_box
            width = max(width, ref_width)
            height = max(height, ref_height)
            margin_x = max(min(ref_x, max(int(canvas_width * 0.08), 48)), 16)
            margin_y = max(min(ref_y, max(int(canvas_height * 0.08), 64)), 16)
        vertical, horizontal = anchor or ("top", "right")
        if horizontal == "left":
            x = margin_x
        elif horizontal == "center":
            x = max((canvas_width - width) // 2, 0)
        else:
            x = max(canvas_width - width - margin_x, 0)
        if vertical == "bottom":
            y = max(canvas_height - height - margin_y, 0)
        elif vertical == "middle":
            y = max((canvas_height - height) // 2, 0)
        else:
            y = margin_y
        width = min(width, max(canvas_width - x, 1))
        height = min(height, max(canvas_height - y, 1))
        return (x, y, width, height)

    @classmethod
    def _reference_ai_logo_box(
        cls,
        *,
        content: ContentVersion,
        explainability: dict,
        canvas_width: int,
        canvas_height: int,
        anchor: tuple[str, str] | None,
    ) -> tuple[int, int, int, int] | None:
        if anchor is None:
            return None
        visual_identity = {}
        if isinstance(explainability, dict):
            snapshot = explainability.get("brand_context_snapshot")
            if isinstance(snapshot, dict):
                visual_identity = snapshot.get("visual_identity") if isinstance(snapshot.get("visual_identity"), dict) else {}
        if not visual_identity and isinstance(content.explainability_metadata, dict):
            snapshot = content.explainability_metadata.get("brand_context_snapshot")
            if isinstance(snapshot, dict):
                visual_identity = snapshot.get("visual_identity") if isinstance(snapshot.get("visual_identity"), dict) else {}
        if not isinstance(visual_identity, dict):
            return None

        candidates: list[tuple[float, float, float, float]] = []

        def _collect(zones: object) -> None:
            for zone in zones if isinstance(zones, list) else []:
                if not isinstance(zone, dict):
                    continue
                if str(zone.get("role") or "").strip().lower() != "logo":
                    continue
                try:
                    x = float(zone.get("x"))
                    y = float(zone.get("y"))
                    width = float(zone.get("width") if zone.get("width") is not None else zone.get("w"))
                    height = float(zone.get("height") if zone.get("height") is not None else zone.get("h"))
                except (TypeError, ValueError):
                    continue
                if min(x, y, width, height) < 0 or width <= 0 or height <= 0:
                    continue
                if max(x, y, width, height) > 1.5:
                    continue
                candidate_box = (
                    int(round(x * canvas_width)),
                    int(round(y * canvas_height)),
                    int(round(width * canvas_width)),
                    int(round(height * canvas_height)),
                )
                if cls._logo_anchor_from_box(candidate_box, canvas_width=canvas_width, canvas_height=canvas_height) == anchor:
                    candidates.append((x, y, width, height))

        for reference in visual_identity.get("reference_creatives") or []:
            if not isinstance(reference, dict):
                continue
            _collect(reference.get("reusable_zones"))
            layout_structure = reference.get("layout_structure") if isinstance(reference.get("layout_structure"), dict) else {}
            _collect(layout_structure.get("zones"))
        for template_info in visual_identity.get("template_intelligence") or []:
            if not isinstance(template_info, dict):
                continue
            analysis = template_info.get("analysis") if isinstance(template_info.get("analysis"), dict) else {}
            _collect(analysis.get("reusable_zones"))
            _collect(analysis.get("editable_zones"))
        if not candidates:
            return None

        def _median(values: list[float]) -> float:
            ordered = sorted(values)
            return ordered[len(ordered) // 2]

        return (
            int(round(_median([item[0] for item in candidates]) * canvas_width)),
            int(round(_median([item[1] for item in candidates]) * canvas_height)),
            int(round(_median([item[2] for item in candidates]) * canvas_width)),
            int(round(_median([item[3] for item in candidates]) * canvas_height)),
        )

    @staticmethod
    def _extract_logo_position_hint(
        content: ContentVersion,
        explainability: dict,
    ) -> str | None:
        generated_payload = content.generated_payload if isinstance(content.generated_payload, dict) else {}
        metadata = generated_payload.get("metadata") if isinstance(generated_payload.get("metadata"), dict) else {}
        blueprint = content.blueprint_payload if isinstance(content.blueprint_payload, dict) else {}
        blueprint_zones = blueprint.get("zones") if isinstance(blueprint.get("zones"), list) else []
        scene_graph = explainability.get("scene_graph") if isinstance(explainability, dict) else {}
        if isinstance(scene_graph, dict):
            styles = scene_graph.get("styles") if isinstance(scene_graph.get("styles"), dict) else {}
            brand_visual_brief = styles.get("brand_visual_brief") if isinstance(styles.get("brand_visual_brief"), dict) else {}
            validation_hints = scene_graph.get("validation_hints") if isinstance(scene_graph.get("validation_hints"), dict) else {}
        else:
            styles = {}
            brand_visual_brief = {}
            validation_hints = {}
        layout_constraints = explainability.get("layout_constraints") if isinstance(explainability, dict) and isinstance(explainability.get("layout_constraints"), dict) else {}
        logo_usage_plan = layout_constraints.get("logo_usage_plan") if isinstance(layout_constraints.get("logo_usage_plan"), dict) else {}
        candidates = [
            validation_hints.get("logo_position"),
            styles.get("logo_position"),
            logo_usage_plan.get("preferred_anchor"),
            explainability.get("logo_position") if isinstance(explainability, dict) else None,
            brand_visual_brief.get("logo_position"),
            metadata.get("logo_position"),
        ]
        for zone in blueprint_zones:
            if not isinstance(zone, dict):
                continue
            zone_role = str(zone.get("role") or "").strip().lower()
            zone_id = str(zone.get("zone_id") or zone.get("id") or zone.get("name") or "").strip().lower()
            if zone_role == "logo" or "logo" in zone_id:
                candidates.append(zone_id.replace("_", "-"))
        for candidate in candidates:
            text = str(candidate or "").strip()
            if text:
                return text
        return None

    @staticmethod
    def _is_style_reference_only_logo_policy(
        content: ContentVersion,
        explainability: dict,
    ) -> bool:
        blueprint = content.blueprint_payload if isinstance(content.blueprint_payload, dict) else {}
        adaptation_plan = blueprint.get("adaptation_plan") if isinstance(blueprint.get("adaptation_plan"), dict) else {}
        if bool(adaptation_plan.get("reference_style_only")):
            return True
        scene_graph = explainability.get("scene_graph") if isinstance(explainability, dict) else {}
        if isinstance(scene_graph, dict):
            validation_hints = scene_graph.get("validation_hints") if isinstance(scene_graph.get("validation_hints"), dict) else {}
            if str(validation_hints.get("template_surface_policy") or "").strip().lower() == "style_reference_only":
                return True
        return False

    @classmethod
    def _normalize_ai_logo_box(
        cls,
        *,
        box: tuple[int, int, int, int] | None,
        canvas_width: int,
        canvas_height: int,
        format_name: str,
        hint: str | None,
        content: ContentVersion,
        explainability: dict,
    ) -> tuple[int, int, int, int]:
        hint_anchor = cls._logo_anchor_from_hint(hint)
        reference_box = cls._reference_ai_logo_box(
            content=content,
            explainability=explainability,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            anchor=hint_anchor,
        )
        min_width, min_height = cls._logo_box_profile_for_format(
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            format_name=format_name,
        )
        if box is None:
            return cls._default_ai_logo_box(
                canvas_width=canvas_width,
                canvas_height=canvas_height,
                format_name=format_name,
                anchor=hint_anchor,
                reference_box=reference_box,
            )
        current_anchor = cls._logo_anchor_from_box(
            box,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
        )
        anchor = hint_anchor or current_anchor
        x, y, width, height = box
        anchor_mismatch = bool(hint_anchor and hint_anchor != current_anchor)
        too_small = width < int(min_width * 0.65) or height < int(min_height * 0.65)
        if anchor_mismatch or too_small:
            return cls._default_ai_logo_box(
                canvas_width=canvas_width,
                canvas_height=canvas_height,
                format_name=format_name,
                anchor=anchor,
                reference_box=reference_box,
            )
        if reference_box is not None:
            _ref_x, _ref_y, ref_width, ref_height = reference_box
            if abs(width - ref_width) >= max(int(canvas_width * 0.035), 28) or abs(height - ref_height) >= max(int(canvas_height * 0.025), 22):
                return cls._default_ai_logo_box(
                    canvas_width=canvas_width,
                    canvas_height=canvas_height,
                    format_name=format_name,
                    anchor=anchor,
                    reference_box=reference_box,
                )
        return box

    @classmethod
    def _resolve_ai_logo_box(
        cls,
        *,
        content: ContentVersion,
        explainability: dict,
        studio_panel: dict,
        asset: GeneratedAsset,
    ) -> tuple[int, int, int, int]:
        canvas_width = int(asset.width or (studio_panel.get("size") or {}).get("width") or 1080)
        canvas_height = int(asset.height or (studio_panel.get("size") or {}).get("height") or 1080)
        format_name = str((studio_panel or {}).get("format") or "").strip().lower()
        logo_position_hint = cls._extract_logo_position_hint(content, explainability)
        style_reference_only = cls._is_style_reference_only_logo_policy(content, explainability)

        scene_graph = explainability.get("scene_graph") if isinstance(explainability, dict) else {}
        if not style_reference_only:
            for element in (scene_graph.get("elements") or []) if isinstance(scene_graph, dict) else []:
                role = str((element or {}).get("role") or (element or {}).get("element_type") or "").strip().lower()
                if role != "logo":
                    continue
                placement = (
                    (element or {}).get("placement")
                    if isinstance((element or {}).get("placement"), dict)
                    else (element or {}).get("bounds")
                )
                geometry = (element or {}).get("geometry") if isinstance((element or {}).get("geometry"), dict) else None
                resolved = cls._coerce_ai_logo_box(
                    placement if isinstance(placement, dict) else (geometry if isinstance(geometry, dict) else element),
                    canvas_width=canvas_width,
                    canvas_height=canvas_height,
                    units=str(
                        (placement or {}).get("units")
                        or (geometry or {}).get("units")
                        or (element or {}).get("units")
                        or ""
                    ),
                )
                if resolved:
                    return cls._normalize_ai_logo_box(
                        box=resolved,
                        canvas_width=canvas_width,
                        canvas_height=canvas_height,
                        format_name=format_name,
                        hint=logo_position_hint,
                        content=content,
                        explainability=explainability,
                    )

        blueprint = content.blueprint_payload if isinstance(content.blueprint_payload, dict) else {}
        if not style_reference_only:
            for zone in blueprint.get("zones") or []:
                zone_role = str((zone or {}).get("role") or "").strip().lower()
                zone_id = str((zone or {}).get("zone_id") or (zone or {}).get("id") or (zone or {}).get("name") or "").strip().lower()
                if zone_role != "logo" and "logo" not in zone_id:
                    continue
                resolved = cls._coerce_ai_logo_box(
                    zone,
                    canvas_width=canvas_width,
                    canvas_height=canvas_height,
                    units=str((zone or {}).get("units") or ""),
                )
                if resolved:
                    return cls._normalize_ai_logo_box(
                        box=resolved,
                        canvas_width=canvas_width,
                        canvas_height=canvas_height,
                        format_name=format_name,
                        hint=logo_position_hint,
                        content=content,
                        explainability=explainability,
                    )

        return cls._normalize_ai_logo_box(
            box=None,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            format_name=format_name,
            hint=logo_position_hint,
            content=content,
            explainability=explainability,
        )

    @staticmethod
    def _should_use_ai_final_render_overlay_for_panel(
        studio_panel: dict | None,
        assets: list[GeneratedAsset],
    ) -> bool:
        format_name = str((studio_panel or {}).get("format") or "").strip().lower()
        if format_name != "carousel":
            return False
        return any(
            isinstance((asset.metadata_json or {}).get("render_overlay_scene_graph"), dict)
            and isinstance((asset.metadata_json or {}).get("render_overlay_text"), dict)
            for asset in assets
        )

    @staticmethod
    def _ai_final_render_asset_has_overlay_contract(asset: GeneratedAsset) -> bool:
        metadata = asset.metadata_json or {}
        return isinstance(metadata.get("render_overlay_text"), dict)

    @staticmethod
    def _ai_final_render_overlay_scene_graph_is_usable(
        payload: dict | None,
    ) -> bool:
        if not isinstance(payload, dict):
            return False
        elements = payload.get("elements")
        return isinstance(elements, list) and bool(elements)

    @staticmethod
    def _ai_final_render_overlay_text_is_usable(
        payload: dict | None,
    ) -> bool:
        if not isinstance(payload, dict):
            return False
        return any(
            str(payload.get(key) or "").strip()
            for key in ("headline", "body", "cta")
        )

    @staticmethod
    def _ai_final_render_overlay_scene_graph_payload(
        asset: GeneratedAsset,
        explainability: dict | None,
    ) -> dict | None:
        metadata = asset.metadata_json or {}
        candidate = metadata.get("render_overlay_scene_graph")
        if isinstance(candidate, dict):
            return deepcopy(candidate)
        explainability = explainability or {}
        fallback = explainability.get("final_render_scene_graph") or explainability.get("scene_graph")
        return deepcopy(fallback) if isinstance(fallback, dict) else None

    @staticmethod
    def _ai_final_render_overlay_text_payload(
        asset: GeneratedAsset,
        content: ContentVersion,
    ) -> dict:
        metadata = asset.metadata_json or {}
        slide_index = metadata.get("slide_index")
        slide_count = metadata.get("slide_count")
        if str(slide_index or "").strip().isdigit():
            structured_payload = ContentService._selective_overlay_text_payload(
                content,
                slide_index=int(slide_index),
                slide_count=int(slide_count or 0) or 1,
            )
            structured_source = (
                structured_payload.get("metadata", {})
                if isinstance(structured_payload.get("metadata"), dict)
                else {}
            ).get("source")
            if structured_source == "structured_slide_spec":
                return structured_payload
        candidate = metadata.get("render_overlay_text")
        if isinstance(candidate, dict):
            candidate_copy = deepcopy(candidate)
            candidate_meta = candidate_copy.get("metadata")
            if not isinstance(candidate_meta, dict):
                candidate_meta = {}
                candidate_copy["metadata"] = candidate_meta
            candidate_meta.setdefault("source", "render_overlay_text")
            return candidate_copy
        return deepcopy(content.generated_payload or {})

    @staticmethod
    def _ai_final_render_overlay_element_slide_index(element: dict | None) -> int | None:
        if not isinstance(element, dict):
            return None
        candidates = [
            element.get("slide_index"),
            (element.get("metadata") or {}).get("slide_index") if isinstance(element.get("metadata"), dict) else None,
            (element.get("validation_hints") or {}).get("slide_index") if isinstance(element.get("validation_hints"), dict) else None,
        ]
        for candidate in candidates:
            if str(candidate or "").strip().isdigit():
                value = int(str(candidate).strip())
                return value if value > 0 else None
        element_id = str(element.get("element_id") or "").strip()
        match = re.search(r"(?:^|[_-])(?:slide[_-]?)?(\d{1,2})$", element_id, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            return value if value > 0 else None
        return None

    @staticmethod
    def _ai_final_render_select_overlay_text_element(
        elements: list[dict],
        *,
        role: str,
        slide_index: int,
    ) -> dict | None:
        normalized_role = str(role or "").strip().lower()
        role_aliases = {
            "headline": {
                "headline",
                "heading",
                "title",
                "main_headline",
                "hook",
            },
            "body": {
                "body",
                "body_text",
                "body_points",
                "detail",
                "details",
                "paragraph",
                "proof",
                "proof_point",
                "proof_points",
                "stat",
                "stat_highlight",
                "stat_highlights",
                "subheadline",
                "subtitle",
                "support",
                "supporting_copy",
                "supporting_line",
            },
            "cta": {
                "button",
                "call_to_action",
                "cta",
            },
        }
        accepted_roles = role_aliases.get(normalized_role, {normalized_role})
        candidates = [
            dict(element)
            for element in elements
            if isinstance(element, dict)
            and str(element.get("element_type") or "").strip().lower() == "text"
            and str(element.get("role") or "").strip().lower() in accepted_roles
        ]
        if not candidates:
            return None
        exact = [
            element
            for element in candidates
            if ContentService._ai_final_render_overlay_element_slide_index(element) == slide_index
        ]
        if exact:
            return deepcopy(exact[0])
        unscoped = [
            element
            for element in candidates
            if ContentService._ai_final_render_overlay_element_slide_index(element) is None
        ]
        return deepcopy(unscoped[0] if unscoped else candidates[0])

    @staticmethod
    def _ai_final_render_sanitize_overlay_scene_graph_for_asset(
        scene_graph: dict | None,
        *,
        asset: GeneratedAsset,
        overlay_text: dict,
    ) -> dict | None:
        if not isinstance(scene_graph, dict):
            return None
        sanitized = deepcopy(scene_graph)
        source_elements = [
            dict(element)
            for element in (sanitized.get("elements") or [])
            if isinstance(element, dict)
        ]
        if not source_elements:
            return sanitized

        metadata = asset.metadata_json or {}
        try:
            slide_index = int(metadata.get("slide_index") or 1)
        except (TypeError, ValueError):
            slide_index = 1
        if slide_index <= 0:
            slide_index = 1

        overlay_values = {
            "headline": str(overlay_text.get("headline") or "").strip(),
            "body": str(overlay_text.get("body") or "").strip(),
            "cta": str(overlay_text.get("cta") or "").strip(),
        }
        selected_elements: list[dict] = []
        seen_ids: set[str] = set()

        def _append(element: dict | None) -> None:
            if not isinstance(element, dict):
                return
            element_id = str(element.get("element_id") or "").strip()
            if not element_id:
                element_id = f"overlay_element_{len(selected_elements) + 1}"
                element["element_id"] = element_id
            if element_id in seen_ids:
                element = {**element, "element_id": f"{element_id}_{len(selected_elements) + 1}"}
                element_id = str(element["element_id"])
            seen_ids.add(element_id)
            selected_elements.append(element)

        for element in source_elements:
            role = str(element.get("role") or "").strip().lower()
            if role == "logo":
                _append(deepcopy(element))

        for role in ("headline", "body", "cta"):
            value = overlay_values.get(role) or ""
            if not value:
                continue
            element = ContentService._ai_final_render_select_overlay_text_element(
                source_elements,
                role=role,
                slide_index=slide_index,
            )
            if element is None:
                continue
            element["text"] = value
            element["role"] = role
            element["element_type"] = "text"
            element["element_id"] = f"{role}_text_slide_{slide_index}"
            _append(element)

        for element in source_elements:
            role = str(element.get("role") or "").strip().lower()
            element_id = str(element.get("element_id") or "").strip().lower()
            if role in {"legal", "footer", "disclaimer"} or "footer" in element_id or "legal" in element_id:
                _append(deepcopy(element))
                break

        sanitized["elements"] = selected_elements
        existing_layers = [str(layer) for layer in (sanitized.get("layers") or []) if str(layer).strip()]
        used_layers = [str(element.get("layer") or "content") for element in selected_elements]
        sanitized["layers"] = list(dict.fromkeys([*existing_layers, *used_layers]))
        validation_hints = sanitized.get("validation_hints")
        if not isinstance(validation_hints, dict):
            validation_hints = {}
        validation_hints["ai_final_overlay_sanitized"] = True
        validation_hints["overlay_slide_index"] = slide_index
        sanitized["validation_hints"] = validation_hints
        return sanitized

    @staticmethod
    def _selective_overlay_text_payload(
        content: ContentVersion,
        *,
        slide_index: int,
        slide_count: int,
    ) -> dict:
        generated_payload = content.generated_payload if isinstance(content.generated_payload, dict) else {}
        metadata = generated_payload.get("metadata") if isinstance(generated_payload.get("metadata"), dict) else {}
        slide_specs = metadata.get("carousel_slide_specs") if isinstance(metadata.get("carousel_slide_specs"), list) else []
        slide_spec = next(
            (
                dict(spec)
                for spec in slide_specs
                if isinstance(spec, dict) and int(spec.get("slide_index") or 0) == slide_index
            ),
            None,
        )
        if not slide_spec:
            return deepcopy(generated_payload)
        slide_metadata = slide_spec.get("metadata") if isinstance(slide_spec.get("metadata"), dict) else {}
        slide_body = AIOrchestratorService._carousel_slide_body_text(
            slide_spec,
            fallback_text=str(slide_spec.get("supporting_line") or generated_payload.get("body") or ""),
        )
        slide_cta = slide_spec.get("cta")
        return StructuredTextPayload(
            headline=str(slide_spec.get("headline") or generated_payload.get("headline") or ""),
            body=slide_body,
            cta=str(slide_cta if slide_cta is not None else (generated_payload.get("cta") or "")),
            hashtags=list(generated_payload.get("hashtags") or []),
            metadata={
                **metadata,
                **slide_metadata,
                "source": "structured_slide_spec",
                "supporting_line": str(slide_spec.get("supporting_line") or generated_payload.get("body") or ""),
                "proof_points": list(slide_spec.get("proof_points") or []),
                "body_points": list(slide_spec.get("body_points") or []),
                "stat_highlights": list(slide_spec.get("stat_highlights") or []),
                "visual_focus": str(slide_spec.get("visual_focus") or ""),
                "transition_note": str(slide_spec.get("transition_note") or ""),
                "slide_role": str(slide_spec.get("role") or ""),
                "slide_index": slide_index,
                "slide_count": slide_count,
            },
        ).model_dump(mode="json")

    @staticmethod
    def _selective_regeneration_plan(explainability: dict | None) -> dict[str, object]:
        explainability = explainability or {}
        plan = explainability.get("selective_regeneration_plan")
        return dict(plan) if isinstance(plan, dict) else {}

    async def _render_ai_final_overlay_source_asset(
        self,
        *,
        content: ContentVersion,
        asset: GeneratedAsset,
        explainability: dict,
        studio_panel: dict,
        resolved_blueprint: dict,
        creative_decision: dict,
        font_asset_paths: list[str],
        brand_visual_rules: dict,
        logo_asset_path: str | None,
        overlay_content: ContentVersion | None = None,
    ) -> dict[str, object] | None:
        overlay_scene_graph = self._ai_final_render_overlay_scene_graph_payload(
            asset,
            explainability,
        )
        overlay_text = self._ai_final_render_overlay_text_payload(
            asset,
            overlay_content or content,
        )
        overlay_scene_graph = self._ai_final_render_sanitize_overlay_scene_graph_for_asset(
            overlay_scene_graph,
            asset=asset,
            overlay_text=overlay_text,
        )
        if not self._ai_final_render_overlay_scene_graph_is_usable(overlay_scene_graph) or not self._ai_final_render_overlay_text_is_usable(overlay_text):
            return None

        overlay_response = await self.renderer.render(
            RendererInput(
                tenant_id=content.tenant_id,
                brand_space_id=content.brand_space_id,
                content_version_id=uuid4(),
                studio_panel=studio_panel,
                blueprint=BlueprintPayload(**resolved_blueprint),
                scene_graph=GenerationSceneGraph.model_validate(
                    self._resolve_scene_graph_payload(overlay_scene_graph, studio_panel)
                ),
                text=StructuredTextPayload(**overlay_text),
                template_metadata=None,
                template_asset_path=None,
                base_canvas_asset_path=asset.storage_path,
                logo_asset_path=logo_asset_path,
                image_assets=[],
                decorative_assets=[],
                font_asset_paths=font_asset_paths,
                brand_visual_rules=brand_visual_rules,
                layout_decision=explainability.get("layout_decision", {}),
                creative_decision=creative_decision,
                validation_report=explainability.get("validation_report", {}),
            )
        )
        response_payload = overlay_response.model_dump(mode="json")
        exported_assets = [
            dict(item)
            for item in (response_payload.get("export_assets") or [])
            if isinstance(item, dict)
        ]
        if not exported_assets:
            return None
        preview_asset = response_payload.get("preview_asset")
        preview_payload = (
            self._decorate_asset_reference(preview_asset)
            if isinstance(preview_asset, dict)
            else None
        )
        return {
            "source_asset": exported_assets[0],
            "preview_asset": preview_payload,
            "text_overlay_source": (
                ((overlay_text.get("metadata") or {}).get("source"))
                if isinstance(overlay_text.get("metadata"), dict)
                else None
            ),
            "renderer_metadata": (
                response_payload.get("renderer_metadata")
                if isinstance(response_payload.get("renderer_metadata"), dict)
                else {}
            ),
        }

    async def _build_ai_final_render_delivery_payloads(
        self,
        *,
        content: ContentVersion,
        assets: list[GeneratedAsset],
        explainability: dict,
        studio_panel: dict,
        selected_template_id: UUID | None,
        logo_asset_path: str | None,
        logo_asset_candidates: list[dict[str, object]] | None = None,
        logo_selection: dict[str, object] | None = None,
        blueprint_payload: dict,
        creative_decision: dict,
        font_asset_paths: list[str],
        brand_visual_rules: dict,
    ) -> dict:
        if self._should_use_ai_final_render_overlay_for_panel(studio_panel, assets):
            return await self._build_ai_final_render_overlay_payloads(
                content=content,
                assets=assets,
                explainability=explainability,
                studio_panel=studio_panel,
                selected_template_id=selected_template_id,
                logo_asset_path=logo_asset_path,
                logo_asset_candidates=logo_asset_candidates,
                logo_selection=logo_selection,
                blueprint_payload=blueprint_payload,
                creative_decision=creative_decision,
                font_asset_paths=font_asset_paths,
                brand_visual_rules=brand_visual_rules,
            )
        return self._build_ai_final_render_export_payloads(
            content=content,
            assets=assets,
            explainability=explainability,
            studio_panel=studio_panel,
            selected_template_id=selected_template_id,
            logo_asset_path=logo_asset_path,
            logo_asset_candidates=logo_asset_candidates,
            logo_selection=logo_selection,
        )

    async def _build_selective_ai_final_render_export_payloads(
        self,
        *,
        content: ContentVersion,
        current_assets: list[GeneratedAsset] | None = None,
        parent_assets: list[GeneratedAsset],
        parent_content: ContentVersion | None = None,
        explainability: dict,
        studio_panel: dict,
        selected_template_id: UUID | None,
        logo_asset_path: str | None,
        logo_asset_candidates: list[dict[str, object]] | None = None,
        logo_selection: dict[str, object] | None = None,
        blueprint_payload: dict,
        creative_decision: dict,
        font_asset_paths: list[str],
        brand_visual_rules: dict,
        regeneration_plan: dict[str, object],
    ) -> dict | None:
        ordered_parent_assets = self._sort_ai_final_render_assets(parent_assets)
        if not ordered_parent_assets:
            return None
        targeted_slide_indexes = {
            int(value)
            for value in regeneration_plan.get("targeted_slide_indexes", [])
            if str(value).strip().isdigit()
        }
        if not targeted_slide_indexes:
            return None

        ordered_current_assets = self._sort_ai_final_render_assets(current_assets or [])
        current_assets_by_index = {
            int((asset.metadata_json or {}).get("slide_index") or position): asset
            for position, asset in enumerate(ordered_current_assets, start=1)
        }
        if any(slide_index not in current_assets_by_index for slide_index in targeted_slide_indexes):
            return None

        parent_assets_by_index = {
            int((asset.metadata_json or {}).get("slide_index") or position): asset
            for position, asset in enumerate(ordered_parent_assets, start=1)
        }
        ordered_slide_indexes: list[int] = []
        seen_slide_indexes: set[int] = set()
        for position, asset in enumerate(ordered_parent_assets, start=1):
            slide_index = int((asset.metadata_json or {}).get("slide_index") or position)
            if slide_index in seen_slide_indexes:
                continue
            seen_slide_indexes.add(slide_index)
            ordered_slide_indexes.append(slide_index)
        for slide_index in sorted(targeted_slide_indexes):
            if slide_index not in seen_slide_indexes:
                ordered_slide_indexes.append(slide_index)

        source_assets: list[dict[str, object]] = []
        render_manifest_assets: list[dict[str, object]] = []
        preview_asset: dict | None = None
        any_logo_rendered = False
        page_count = len(ordered_slide_indexes)
        per_slide_panel = {**dict(studio_panel or {}), "file_type": "png"}
        resolved_blueprint = self._resolve_blueprint_payload(
            blueprint_payload if isinstance(blueprint_payload, dict) else {},
            None,
            None,
            studio_panel,
        )

        for position, slide_index in enumerate(ordered_slide_indexes, start=1):
            reused_parent_render = slide_index not in targeted_slide_indexes
            asset = (
                parent_assets_by_index.get(slide_index)
                if reused_parent_render
                else current_assets_by_index.get(slide_index)
            )
            if asset is None:
                return None
            overlay_payload = await self._render_ai_final_overlay_source_asset(
                content=content,
                asset=asset,
                explainability=explainability,
                studio_panel=per_slide_panel,
                resolved_blueprint=resolved_blueprint,
                creative_decision=creative_decision,
                font_asset_paths=font_asset_paths,
                brand_visual_rules=brand_visual_rules,
                logo_asset_path=logo_asset_path,
                overlay_content=(
                    parent_content
                    if reused_parent_render and parent_content is not None
                    else content
                ),
            )
            overlay_renderer_metadata = (
                overlay_payload.get("renderer_metadata")
                if overlay_payload and isinstance(overlay_payload.get("renderer_metadata"), dict)
                else {}
            )
            overlay_logo_rendered = (
                bool(overlay_renderer_metadata.get("logo_rendered"))
                if "logo_rendered" in overlay_renderer_metadata
                else bool(overlay_payload)
            )
            source_asset_payload = (
                dict(overlay_payload.get("source_asset") or {})
                if overlay_payload
                else (
                    self._build_ai_logo_fallback_asset(
                        content=content,
                        asset=asset,
                        explainability=explainability,
                        studio_panel=studio_panel,
                        logo_asset_path=logo_asset_path,
                        logo_asset_candidates=logo_asset_candidates,
                        logo_selection=logo_selection,
                    )
                    or self._generated_asset_payload(asset)
                )
            )
            decorated = self._decorate_asset_reference(
                {
                    **source_asset_payload,
                    "asset_role": str(AssetRole.RENDER_EXPORT),
                }
            )
            if preview_asset is None:
                preview_asset = (
                    dict(overlay_payload.get("preview_asset"))
                    if overlay_payload and isinstance(overlay_payload.get("preview_asset"), dict)
                    else self._decorate_asset_reference(
                        {
                            **source_asset_payload,
                            "asset_role": str(AssetRole.RENDER_PREVIEW),
                        }
                    )
                )
            source_assets.append(dict(decorated or source_asset_payload))
            render_manifest_assets.append(
                {
                    "slide_index": slide_index,
                    "slide_count": int((asset.metadata_json or {}).get("slide_count") or page_count),
                    "source_storage_path": asset.storage_path,
                    "output_storage_paths": [str(source_asset_payload.get("storage_path") or "")],
                    "carousel_role": (asset.metadata_json or {}).get("carousel_role"),
                    "base_canvas_overlay": bool(overlay_payload),
                    "text_overlay_source": (
                        overlay_payload.get("text_overlay_source")
                        if overlay_payload
                        else None
                    ),
                    "selective_regeneration": not reused_parent_render,
                    "reused_parent_render": reused_parent_render,
                }
            )
            any_logo_rendered = (
                any_logo_rendered
                or bool((asset.metadata_json or {}).get("logo_composited_by_ai"))
                or bool(source_asset_payload.get("metadata"))
                or overlay_logo_rendered
            )

        if preview_asset is None:
            return None

        file_type = self._ai_export_file_type(studio_panel)
        export_assets = self._build_ai_final_render_export_assets(
            content=content,
            source_assets=source_assets,
            file_type=file_type,
        )
        return {
            "preview_asset": preview_asset,
            "export_assets": export_assets,
            "renderer_metadata": {
                "layout_variant": "selective_ai_final_render_merge_carousel",
                "render_authority": "ai",
                "template_rendered": False,
                "logo_rendered": any_logo_rendered,
                "image_rendered": True,
                "decorative_rendered": False,
                "scene_graph_used": True,
                "template_id": str(selected_template_id) if selected_template_id else None,
                "logo_asset_path": logo_asset_path,
                "page_count": page_count,
                "output_file_type": file_type,
                "render_manifest": {
                    "scene_graph": explainability.get("scene_graph"),
                    "final_render_scene_graph": explainability.get("final_render_scene_graph"),
                    "selective_regeneration": True,
                    "generation_path": explainability.get("generation_path"),
                    "targeted_slide_indexes": sorted(targeted_slide_indexes),
                    "reuse_slide_indexes": [
                        int(value)
                        for value in regeneration_plan.get("reuse_slide_indexes", [])
                        if str(value).strip().isdigit()
                    ],
                    "assets": render_manifest_assets,
                },
            },
        }

    async def _build_ai_final_render_overlay_payloads(
        self,
        *,
        content: ContentVersion,
        assets: list[GeneratedAsset],
        explainability: dict,
        studio_panel: dict,
        selected_template_id: UUID | None,
        logo_asset_path: str | None,
        logo_asset_candidates: list[dict[str, object]] | None = None,
        logo_selection: dict[str, object] | None = None,
        blueprint_payload: dict,
        creative_decision: dict,
        font_asset_paths: list[str],
        brand_visual_rules: dict,
    ) -> dict:
        if not assets:
            return self._build_ai_final_render_export_payloads(
                content=content,
                assets=assets,
                explainability=explainability,
                studio_panel=studio_panel,
                selected_template_id=selected_template_id,
                logo_asset_path=logo_asset_path,
                logo_asset_candidates=logo_asset_candidates,
                logo_selection=logo_selection,
            )

        ordered_assets = self._sort_ai_final_render_assets(assets)
        resolved_blueprint = self._resolve_blueprint_payload(
            blueprint_payload if isinstance(blueprint_payload, dict) else {},
            None,
            None,
            studio_panel,
        )
        requested_file_type = self._ai_export_file_type(studio_panel)
        per_slide_panel = {**dict(studio_panel or {}), "file_type": "png"}

        rendered_source_assets: list[dict[str, object]] = []
        render_manifest_assets: list[dict[str, object]] = []
        preview_asset: dict | None = None
        any_logo_rendered = False
        overlay_quality_assessments: list[dict[str, object]] = []

        for position, asset in enumerate(ordered_assets, start=1):
            overlay_payload = await self._render_ai_final_overlay_source_asset(
                content=content,
                asset=asset,
                explainability=explainability,
                studio_panel=per_slide_panel,
                resolved_blueprint=resolved_blueprint,
                creative_decision=creative_decision,
                font_asset_paths=font_asset_paths,
                brand_visual_rules=brand_visual_rules,
                logo_asset_path=logo_asset_path,
            )
            if not overlay_payload:
                return self._build_ai_final_render_export_payloads(
                    content=content,
                    assets=assets,
                    explainability=explainability,
                    studio_panel=studio_panel,
                    selected_template_id=selected_template_id,
                    logo_asset_path=logo_asset_path,
                    logo_asset_candidates=logo_asset_candidates,
                    logo_selection=logo_selection,
                )

            overlay_renderer_metadata = (
                overlay_payload.get("renderer_metadata")
                if isinstance(overlay_payload.get("renderer_metadata"), dict)
                else {}
            )
            overlay_logo_rendered = (
                bool(overlay_renderer_metadata.get("logo_rendered"))
                if "logo_rendered" in overlay_renderer_metadata
                else bool(logo_asset_path)
            )
            rendered_asset = dict(overlay_payload.get("source_asset") or {})
            if logo_asset_path and not overlay_logo_rendered and rendered_asset.get("storage_path"):
                fallback_asset = self._build_ai_logo_fallback_asset(
                    content=content,
                    asset=GeneratedImageAsset(
                        asset_id=uuid4(),
                        mime_type=str(rendered_asset.get("mime_type") or asset.mime_type or "image/png"),
                        storage_path=str(rendered_asset.get("storage_path") or ""),
                        width=int(rendered_asset.get("width") or asset.width or 0),
                        height=int(rendered_asset.get("height") or asset.height or 0),
                        asset_role=str(rendered_asset.get("asset_role") or asset.asset_role or AssetRole.RENDER_EXPORT),
                        metadata=dict(asset.metadata_json or {}),
                    ),
                    explainability=explainability,
                    studio_panel=per_slide_panel,
                    logo_asset_path=logo_asset_path,
                    logo_asset_candidates=logo_asset_candidates,
                    logo_selection=logo_selection,
                )
                if fallback_asset:
                    rendered_asset = fallback_asset
                    overlay_logo_rendered = True
            rendered_source_assets.append(rendered_asset)
            any_logo_rendered = any_logo_rendered or overlay_logo_rendered
            if isinstance(overlay_renderer_metadata.get("quality_assessment"), dict):
                overlay_quality_assessments.append(dict(overlay_renderer_metadata["quality_assessment"]))
            if preview_asset is None and isinstance(overlay_payload.get("preview_asset"), dict):
                preview_asset = dict(overlay_payload.get("preview_asset"))
            render_manifest_assets.append(
                {
                    "slide_index": int((asset.metadata_json or {}).get("slide_index") or position),
                    "slide_count": int((asset.metadata_json or {}).get("slide_count") or len(ordered_assets)),
                    "storage_path": rendered_asset.get("storage_path"),
                    "source_storage_path": asset.storage_path,
                    "carousel_role": (asset.metadata_json or {}).get("carousel_role"),
                    "base_canvas_overlay": True,
                    "text_overlay_source": overlay_payload.get("text_overlay_source"),
                    "logo_rendered": overlay_logo_rendered,
                    "renderer_metadata": overlay_renderer_metadata,
                }
            )

        if preview_asset is None:
            preview_asset = self._decorate_asset_reference({**rendered_source_assets[0], "asset_role": str(AssetRole.RENDER_PREVIEW)})

        export_assets = self._build_ai_final_render_export_assets(
            content=content,
            source_assets=rendered_source_assets,
            file_type=requested_file_type,
        )
        return {
            "preview_asset": preview_asset,
            "export_assets": export_assets,
            "renderer_metadata": {
                "layout_variant": (
                    "ai_final_render_text_overlay_carousel"
                    if len(rendered_source_assets) > 1
                    else "ai_final_render_text_overlay"
                ),
                "render_authority": "ai",
                "template_rendered": False,
                "logo_rendered": any_logo_rendered,
                "image_rendered": True,
                "decorative_rendered": False,
                "scene_graph_used": True,
                "template_id": str(selected_template_id) if selected_template_id else None,
                "logo_asset_path": logo_asset_path,
                "overlay_quality_assessments": overlay_quality_assessments,
                "page_count": len(rendered_source_assets),
                "output_file_type": requested_file_type,
                "render_manifest": {
                    "scene_graph": explainability.get("scene_graph"),
                    "final_render_scene_graph": explainability.get("final_render_scene_graph"),
                    "generation_path": explainability.get("generation_path"),
                    "base_canvas_overlay": True,
                    "direct_asset_export": False,
                    "assets": render_manifest_assets,
                },
            },
        }

    @staticmethod
    def _payload_to_generated_image_asset(
        payload: dict[str, object] | None,
        *,
        fallback_asset: GeneratedAsset | GeneratedImageAsset,
    ) -> GeneratedImageAsset:
        metadata = {}
        if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict):
            metadata = dict(payload.get("metadata") or {})
        else:
            metadata = dict(getattr(fallback_asset, "metadata_json", None) or getattr(fallback_asset, "metadata", {}) or {})
        raw_asset_id = (payload or {}).get("asset_id") if isinstance(payload, dict) else None
        try:
            asset_id = UUID(str(raw_asset_id)) if raw_asset_id else uuid4()
        except (TypeError, ValueError):
            asset_id = uuid4()
        return GeneratedImageAsset(
            asset_id=asset_id,
            mime_type=str((payload or {}).get("mime_type") or getattr(fallback_asset, "mime_type", None) or "image/png"),
            storage_path=str((payload or {}).get("storage_path") or getattr(fallback_asset, "storage_path", "")),
            width=int((payload or {}).get("width") or getattr(fallback_asset, "width", 0) or 0),
            height=int((payload or {}).get("height") or getattr(fallback_asset, "height", 0) or 0),
            asset_role=str((payload or {}).get("asset_role") or getattr(fallback_asset, "asset_role", AssetRole.RENDER_EXPORT)),
            metadata=metadata,
        )

    @staticmethod
    def _asset_metadata_payload(asset: GeneratedAsset | GeneratedImageAsset) -> dict[str, object]:
        return dict(getattr(asset, "metadata_json", None) or getattr(asset, "metadata", {}) or {})

    @staticmethod
    def _ai_final_render_legal_footer_text(
        *,
        content: ContentVersion,
        explainability: dict,
    ) -> str:
        for graph_key in ("final_render_scene_graph", "scene_graph"):
            graph = explainability.get(graph_key) if isinstance(explainability, dict) else None
            if not isinstance(graph, dict):
                continue
            for element in graph.get("elements") or []:
                if not isinstance(element, dict):
                    continue
                role = str(element.get("role") or element.get("element_type") or "").strip().lower()
                element_id = str(element.get("element_id") or "").strip().lower()
                if role in {"legal", "footer", "disclaimer"} or "legal" in element_id or "footer" in element_id:
                    text = str(element.get("text") or "").strip()
                    if text:
                        return " ".join(text.split())
        generated_payload = content.generated_payload if isinstance(content.generated_payload, dict) else {}
        metadata = generated_payload.get("metadata") if isinstance(generated_payload.get("metadata"), dict) else {}
        for candidate in (
            metadata.get("footer"),
            metadata.get("legal_footer"),
            generated_payload.get("footer"),
        ):
            text = str(candidate or "").strip()
            if text:
                return " ".join(text.split())
        return ""

    @staticmethod
    def _load_footer_font(size: int) -> ImageFont.ImageFont:
        for font_name in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
            try:
                return ImageFont.truetype(font_name, size=size)
            except OSError:
                continue
        return ImageFont.load_default()

    @staticmethod
    def _wrap_footer_lines(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.ImageFont,
        *,
        max_width: int,
    ) -> list[str]:
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            left, _top, right, _bottom = draw.textbbox((0, 0), candidate, font=font)
            if current and (right - left) > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    def _build_ai_footer_fallback_asset(
        self,
        *,
        content: ContentVersion,
        asset: GeneratedAsset | GeneratedImageAsset,
        explainability: dict,
        studio_panel: dict,
    ) -> dict | None:
        footer_text = self._ai_final_render_legal_footer_text(content=content, explainability=explainability)
        if not footer_text or not str(getattr(asset, "mime_type", "") or "").startswith("image/"):
            return None
        storage_path = str(getattr(asset, "storage_path", "") or "")
        if not storage_path or not self.storage.exists(storage_path):
            return None
        try:
            with open_image_asset(self.storage.absolute_path(storage_path)) as raw_base:
                base = raw_base.convert("RGBA")
        except OSError:
            logger.warning(
                "content.ai_final_render.footer_overlay_failed content_version_id=%s asset_storage_path=%s",
                content.id,
                storage_path,
            )
            return None

        width, height = base.size
        strip_height = max(int(height * 0.052), 56)
        strip_top = max(height - strip_height, 0)
        sample_y = min(max(strip_top + strip_height // 2, 0), height - 1)
        sample_points = [base.getpixel((x, sample_y))[:3] for x in (int(width * 0.12), int(width * 0.5), int(width * 0.88))]
        avg_luma = sum((0.2126 * r + 0.7152 * g + 0.0722 * b) for r, g, b in sample_points) / max(len(sample_points), 1)
        if avg_luma >= 145:
            strip_fill = (255, 255, 255, 226)
            text_fill = (0, 57, 117, 255)
        else:
            strip_fill = (0, 57, 117, 232)
            text_fill = (255, 255, 255, 255)

        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.rectangle((0, strip_top, width, height), fill=strip_fill)
        horizontal_padding = max(int(width * 0.04), 28)
        vertical_padding = max(int(strip_height * 0.16), 8)
        max_text_width = max(width - horizontal_padding * 2, 10)
        max_text_height = max(strip_height - vertical_padding * 2, 10)

        chosen_font = self._load_footer_font(max(int(height * 0.009), 9))
        chosen_lines = self._wrap_footer_lines(draw, footer_text, chosen_font, max_width=max_text_width)
        for size in range(max(int(height * 0.0095), 11), 6, -1):
            font = self._load_footer_font(size)
            lines = self._wrap_footer_lines(draw, footer_text, font, max_width=max_text_width)
            line_heights = [draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1] for line in lines]
            total_height = sum(line_heights) + max(len(lines) - 1, 0) * max(size // 3, 2)
            chosen_font = font
            chosen_lines = lines
            if total_height <= max_text_height:
                break

        spacing = max(getattr(chosen_font, "size", 9) // 3, 2)
        line_boxes = [draw.textbbox((0, 0), line, font=chosen_font) for line in chosen_lines]
        total_height = sum(box[3] - box[1] for box in line_boxes) + max(len(chosen_lines) - 1, 0) * spacing
        cursor_y = strip_top + max((strip_height - total_height) // 2, vertical_padding // 2)
        for line, box in zip(chosen_lines, line_boxes):
            line_height = box[3] - box[1]
            draw.text((horizontal_padding, cursor_y - box[1]), line, fill=text_fill, font=chosen_font)
            cursor_y += line_height + spacing

        base = Image.alpha_composite(base, overlay)
        stored = self._store_ai_final_render_image(
            content=content,
            image=base,
            filename_prefix="exact-footer",
        )
        metadata = {
            **self._asset_metadata_payload(asset),
            "render_source": "ai",
            "generation_stage": "final_render",
            "legal_footer_composited_by_service": True,
            "legal_footer_overlay_strategy": "exact_footer_strip",
            "source_storage_path": storage_path,
            "legal_footer_text_length": len(footer_text),
            "legal_footer_line_count": len(chosen_lines),
            "legal_footer_strip_box": {
                "x": 0,
                "y": strip_top,
                "width": width,
                "height": strip_height,
            },
        }
        return {
            "asset_id": stored["asset_id"],
            "asset_role": str(AssetRole.RENDER_EXPORT),
            "mime_type": stored["mime_type"],
            "storage_path": stored["storage_path"],
            "width": stored["width"],
            "height": stored["height"],
            "metadata": metadata,
        }

    def _build_ai_logo_fallback_asset(
        self,
        *,
        content: ContentVersion,
        asset: GeneratedAsset,
        explainability: dict,
        studio_panel: dict,
        logo_asset_path: str | None,
        logo_asset_candidates: list[dict[str, object]] | None = None,
        logo_selection: dict[str, object] | None = None,
    ) -> dict | None:
        if not logo_asset_path or not str(asset.mime_type or "").startswith("image/"):
            return None
        if (asset.metadata_json or {}).get("logo_composited_by_ai"):
            return None
        if not self.storage.exists(asset.storage_path) or not self.storage.exists(logo_asset_path):
            return None

        try:
            with open_image_asset(self.storage.absolute_path(asset.storage_path)) as raw_base:
                base = raw_base.convert("RGBA")
        except OSError:
            logger.warning(
                "content.ai_final_render.logo_overlay_failed content_version_id=%s asset_storage_path=%s logo_storage_path=%s",
                content.id,
                asset.storage_path,
                logo_asset_path,
            )
            return None

        logo_box = self._resolve_ai_logo_box(
            content=content,
            explainability=explainability,
            studio_panel=studio_panel,
            asset=asset,
        )
        logo_clearance_anchor = self._logo_clearance_anchor(base, logo_box)
        # Resolve the best logo candidate using the unmodified base image so that
        # background-luminance scoring is not corrupted by any clearance fill.
        overlay_candidate = self._select_logo_overlay_candidate(
            base_image=base,
            logo_box=logo_box,
            current_logo_asset_path=logo_asset_path,
            logo_asset_candidates=logo_asset_candidates,
            logo_selection=logo_selection,
        )
        resolved_logo_asset_path = (
            str((overlay_candidate or {}).get("storage_path") or "").strip() or logo_asset_path
        )
        if not self.storage.exists(resolved_logo_asset_path):
            resolved_logo_asset_path = logo_asset_path
        try:
            with open_image_asset(self.storage.absolute_path(resolved_logo_asset_path)) as raw_logo:
                raw_logo_rgba = raw_logo.convert("RGBA")
                # Strip the logo background first, then decide whether clearance is needed.
                # Checking the RAW logo was wrong: even if the raw file had a solid white
                # background, _strip_logo_background_if_safe removes it, leaving a
                # transparent logo.  Calling clearance afterward samples dark brand colors
                # from the surrounding base image and fills the entire zone with an opaque
                # dark rectangle — destroying headlines and charts.
                logo = self._trim_transparent_logo_margins(
                    self._strip_logo_background_if_safe(raw_logo_rgba)
                )
                # Determine if the logo is effectively transparent AFTER stripping.
                logo_pixels = list(logo.getdata())
                total_pixels = len(logo_pixels)
                transparent_pixels = sum(1 for p in logo_pixels if p[3] < 30)
                logo_is_transparent_after_strip = total_pixels > 0 and (transparent_pixels / total_pixels) >= 0.25
        except OSError:
            logger.warning(
                "content.ai_final_render.logo_overlay_failed content_version_id=%s asset_storage_path=%s logo_storage_path=%s",
                content.id,
                asset.storage_path,
                resolved_logo_asset_path,
            )
            return None

        x, y, width, height = logo_box
        inner_width = max(width - max(int(width * 0.01), 2), 1)
        inner_height = max(height - max(int(height * 0.015), 2), 1)
        contained = ImageOps.contain(logo, (inner_width, inner_height), method=Image.Resampling.LANCZOS)
        offset_x = x + max((width - contained.width) // 2, 0)
        offset_y = y + max((height - contained.height) // 2, 0)
        compact_clearance_box = self._logo_footprint_clearance_box(
            image=base,
            offset_x=offset_x,
            offset_y=offset_y,
            logo_width=contained.width,
            logo_height=contained.height,
        )
        # Clear only the true transparent logo footprint plus a tiny feathered halo.
        # This removes AI-painted noise beneath the logo without creating a visible
        # rectangular background plate.
        base, logo_clearance_zone_applied = self._clear_ai_logo_footprint_region(
            base,
            logo_image=contained,
            offset_x=offset_x,
            offset_y=offset_y,
            clear_box=compact_clearance_box,
        )
        background_luminance = self._logo_box_background_luminance(base, logo_box)
        base.paste(contained, (offset_x, offset_y), contained)

        stored = self._store_ai_final_render_image(
            content=content,
            image=base,
            filename_prefix="exact-logo",
        )
        return {
            "asset_id": stored["asset_id"],
            "asset_role": str(AssetRole.RENDER_EXPORT),
            "mime_type": stored["mime_type"],
            "storage_path": stored["storage_path"],
            "width": stored["width"],
            "height": stored["height"],
            "metadata": {
                **dict(asset.metadata_json or {}),
                "render_source": "ai",
                "generation_stage": "final_render",
                "logo_composited_by_service": True,
                "logo_overlay_strategy": "exact_asset_overlay",
                "logo_asset_path": resolved_logo_asset_path,
                "logo_selection_source": (overlay_candidate or {}).get("source"),
                "logo_variant_background_tone": "dark" if background_luminance <= 150 else "light",
                "source_storage_path": asset.storage_path,
                "logo_clearance_zone_applied": logo_clearance_zone_applied,
                "logo_clearance_anchor": logo_clearance_anchor,
                "logo_clearance_strategy": "footprint_masked_top_band_patch" if logo_clearance_anchor.startswith("top-") else "footprint_masked_context_patch_or_fill",
                "logo_clearance_box": {
                    "x": compact_clearance_box[0],
                    "y": compact_clearance_box[1],
                    "width": compact_clearance_box[2],
                    "height": compact_clearance_box[3],
                },
            },
        }

    async def _resolve_generation_decision(
        self,
        *,
        prompt: str,
        studio_panel: dict,
        brand_context: dict,
        persona_context: dict,
        objective_context: dict,
        template_recommendations,
        selected_template_id: UUID | None,
        selected_template_name: str | None,
        reference_assets: list[dict],
    ) -> dict:
        recommendations = [
            recommendation.model_dump(mode="json") if hasattr(recommendation, "model_dump") else dict(recommendation)
            for recommendation in template_recommendations
        ]
        decision = self.layout_decision.decide(
            prompt=prompt,
            studio_panel=studio_panel,
            brand_context=brand_context,
            persona_context=persona_context,
            objective_context=objective_context,
            template_recommendations=recommendations,
            selected_template_id=str(selected_template_id) if selected_template_id else None,
            selected_template_name=selected_template_name,
            reference_assets=reference_assets,
        )
        primary_recommendation = recommendations[0] if recommendations else {}
        selected_template_value = str(decision.template_id or selected_template_id or "").strip()
        selected_template_name_value = str(decision.template_name or selected_template_name or "").strip()
        primary_template_id = str(primary_recommendation.get("template_id") or "").strip()
        primary_template_name = str(primary_recommendation.get("name") or "").strip()
        primary_matches_selected = bool(
            primary_recommendation
            and (
                (primary_template_id and primary_template_id == selected_template_value)
                or (primary_template_name and primary_template_name == selected_template_name_value)
            )
        )
        return {
            **decision.to_payload(),
            "source": "backend_planning_hints",
            "authoritative": False,
            "primary_adaptation_template_id": primary_template_id or None,
            "primary_adaptation_template_name": primary_template_name or None,
            "primary_adaptation_selection_reason": primary_recommendation.get("selection_reason"),
            "primary_adaptation_matches_selected_template": primary_matches_selected,
            "template_recommendations": recommendations[:5],
        }

    async def _persist_render_assets(
        self,
        content: ContentVersion,
        selected_template_id: UUID | None,
        response: dict,
    ) -> None:
        preview_asset = response.get("preview_asset")
        export_assets = response.get("export_assets", [])
        for asset in [preview_asset, *export_assets]:
            if not asset:
                continue
            existing = await self.assets.get_by_content_storage_role(
                content.id,
                asset["storage_path"],
                asset["asset_role"],
            )
            if existing:
                existing.mime_type = asset["mime_type"]
                existing.width = asset.get("width")
                existing.height = asset.get("height")
                existing.template_id = selected_template_id
                existing.metadata_json = {
                    **existing.metadata_json,
                    "renderer_output": True,
                }
                continue
            await self.assets.add(
                GeneratedAsset(
                    tenant_id=content.tenant_id,
                    brand_space_id=content.brand_space_id,
                    content_version_id=content.id,
                    template_id=selected_template_id,
                    asset_role=asset["asset_role"],
                    mime_type=asset["mime_type"],
                    storage_path=asset["storage_path"],
                    width=asset.get("width"),
                    height=asset.get("height"),
                    metadata_json={"renderer_output": True},
                )
            )

    async def _build_retrieved_knowledge(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        prompt: str,
        studio_panel: dict | None = None,
    ) -> tuple[dict[str, list[dict]], dict[str, dict]]:
        assets = await self.knowledge.list(tenant_id, brand_space_id)
        channel_state: dict[str, dict] = {}
        retrieved_knowledge: dict[str, list[dict]] = {}
        for channel in self._knowledge_channels_for_panel(studio_panel):
            channel_assets = [asset for asset in assets if asset.channel == channel and asset.lifecycle_state != "deleted"]
            query_variants = self._knowledge_queries_for_channel(prompt, channel)
            result_sets = [
                self.knowledge.retrieval.search(
                    str(tenant_id),
                    str(brand_space_id),
                    channel,
                    query,
                    k=4,
                )
                for query in query_variants
            ]
            retrieved_knowledge[channel] = self._merge_retrieval_results(
                result_sets,
                limit=4,
            )
            channel_state[channel] = {
                "assets_present": len(channel_assets),
                "indexed_assets": len([asset for asset in channel_assets if asset.lifecycle_state == "indexed"]),
                "processing_assets": len([asset for asset in channel_assets if asset.lifecycle_state == "processing"]),
                "match_count": len(retrieved_knowledge[channel]),
                "query_count": len(query_variants),
            }
        return retrieved_knowledge, channel_state

    def _write_brand_usage_trace(
        self,
        *,
        trace_id: str | None,
        context_sections: list[Any],
        effective_prompt: str,
        tenant_id: UUID,
        brand_space_id: UUID,
        studio_panel: dict[str, Any],
        runtime_brand_context: dict[str, Any],
        persona: Any,
        objective: Any,
        reference_assets: list[dict[str, Any]],
        template_recommendations: list[Any],
        template_context: dict[str, Any],
        retrieved_knowledge: dict[str, list[dict[str, Any]]],
        planning_hints: dict[str, Any],
        explainability: dict[str, Any],
        template: Any,
        logo_candidates: list[dict[str, Any]],
        logo_selection: dict[str, Any] | None,
    ) -> None:
        brand_usage_writer = getattr(self.trace, "write_brand_usage_report", None)
        brand_usage_builder = getattr(self.trace, "build_brand_usage_report", None)
        if not (callable(brand_usage_writer) and callable(brand_usage_builder) and trace_id):
            return
        section_payloads = {
            str(getattr(section, "section_code", "")).strip(): dict(getattr(section, "payload", {}) or {})
            for section in context_sections
            if str(getattr(section, "section_code", "")).strip() and isinstance(getattr(section, "payload", None), dict)
        }
        brand_usage_report = brand_usage_builder(
            trace_id=trace_id,
            mode="content.generate",
            prompt=effective_prompt,
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            studio_panel=studio_panel,
            section_payloads=section_payloads,
            runtime_brand_context=runtime_brand_context,
            persona_context=BrandIntelligenceService.persona_to_dict(persona),
            objective_context=BrandIntelligenceService.objective_to_dict(objective),
            reference_assets=reference_assets,
            template_candidates=[
                recommendation.model_dump(mode="json") if hasattr(recommendation, "model_dump") else dict(recommendation)
                for recommendation in template_recommendations
            ],
            template_context=template_context,
            retrieved_knowledge=retrieved_knowledge,
            planning_hints=planning_hints,
            explainability=explainability,
            selected_template={
                "template_id": str(template.id) if template else "",
                "template_name": getattr(template, "name", "") if template else "",
            },
            logo_candidates=logo_candidates,
            logo_selection=logo_selection,
        )
        brand_usage_writer(trace_id, brand_usage_report)

    async def generate(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        user_id: UUID,
        payload: ContentGenerateRequest,
    ) -> ContentVersion:
        context = await self._gather_context(brand_space_id)
        brand = context["brand"]
        if brand.lifecycle_state != BrandSpaceLifecycle.ACTIVE:
            raise LifecycleError("Brand Space must be Active for generation")
        brand, _snapshot = await self.validator.refresh_brand_context(brand_space_id)
        session = await self._get_or_create_session(
            tenant_id,
            brand_space_id,
            user_id,
            payload.session_id,
            payload.studio_panel.model_dump(),
        )
        session_memory = await self._build_session_memory(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            session=session,
            current_prompt=str(getattr(payload, "raw_user_prompt", None) or payload.prompt or "").strip(),
        )
        session_memory = await self._apply_request_lineage(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            payload=payload,
            session_memory=session_memory,
        )
        effective_prompt, prompt_sanitization = self._sanitize_prompt_for_request(
            payload=payload,
            session_memory=session_memory,
        )
        payload.prompt = effective_prompt
        request_lineage = self._request_lineage_payload(payload=payload, session_memory=session_memory)
        prompt_lineage = self._request_prompt_lineage_payload(payload=payload, session_memory=session_memory)
        follow_up_mode, persona_lookup_id, objective_lookup_id, selected_template_id = self._resolve_generation_selection_ids(
            payload=payload,
            session_memory=session_memory,
        )
        trace = self.trace.start_trace(
            prompt=effective_prompt,
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            session_id=session.id,
            metadata={
                "platform_preset": payload.studio_panel.platform_preset,
                "format": payload.studio_panel.format,
                "file_type": payload.studio_panel.file_type,
            },
        )
        trace_id = (trace or {}).get("trace_id")
        self.trace.write_debug_event(
            "content.generate.trace_start_result",
            {
                "session_id": str(session.id),
                "trace_id": trace_id,
                "trace_dir": (trace or {}).get("trace_dir"),
                "format": payload.studio_panel.format,
                "file_type": payload.studio_panel.file_type,
                "request_mode": payload.request_mode,
                "prompt_preview": str(effective_prompt or "")[:160],
            },
        )
        logger.info(
            "content.generate.start session_id=%s trace_id=%s format=%s file_type=%s generate_image=%s prompt_length=%s",
            session.id,
            trace_id,
            payload.studio_panel.format,
            payload.studio_panel.file_type,
            payload.generate_image,
            len(effective_prompt or ""),
        )

        persona = next((item for item in context["personas"] if item.id == persona_lookup_id), None) or next((item for item in context["personas"] if item.is_default), None)
        objective = next((item for item in context["objectives"] if item.id == objective_lookup_id), None) or next((item for item in context["objectives"] if item.is_default), None)
        persona_context = BrandIntelligenceService.persona_to_dict(persona)
        objective_context = BrandIntelligenceService.objective_to_dict(objective)
        runtime_brand_context, logo_candidates, logo_selection = await self._prepare_runtime_brand_context(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            brand_context=brand.resolved_brand_context,
            studio_panel=payload.studio_panel.model_dump(),
            sections=context["sections"],
        )
        input_access_tracker = InputAccessTracker()
        tracked_runtime_brand_context = input_access_tracker.wrap_source("brand_context", runtime_brand_context)
        tracked_persona_context = input_access_tracker.wrap_source("persona_context", persona_context)
        tracked_objective_context = input_access_tracker.wrap_source("objective_context", objective_context)
        tracked_logo_candidates = input_access_tracker.wrap_source("logo_candidates", logo_candidates)
        tracked_logo_selection = input_access_tracker.wrap_source("logo_selection", logo_selection or {})
        template_recommendations = await self.template_service.recommend(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            prompt=effective_prompt,
            studio_panel=payload.studio_panel.model_dump(),
            brand_context=tracked_runtime_brand_context,
            limit=5,
        )
        preselected_template = (
            await self.templates.get_scoped(selected_template_id, tenant_id, brand_space_id)
            if selected_template_id
            else None
        )
        if selected_template_id and not preselected_template:
            logger.warning(
                "content.generate.requested_template_missing brand_space_id=%s session_id=%s requested_template_id=%s",
                brand_space_id,
                session.id,
                selected_template_id,
            )
        request_reference_assets = await self._resolve_request_reference_assets(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            reference_asset_ids=payload.reference_asset_ids,
        )
        request_reference_assets = self._filter_reference_assets_for_studio_format(
            request_reference_assets,
            studio_panel=payload.studio_panel.model_dump(),
        )
        brand_reference_assets = await self._resolve_brand_reference_assets(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            brand_context=tracked_runtime_brand_context,
        )
        brand_reference_assets = self._filter_brand_reference_assets_for_prompt(
            brand_reference_assets,
            prompt=effective_prompt,
            follow_up_mode=follow_up_mode,
        )
        brand_reference_assets = self._filter_reference_assets_for_studio_format(
            brand_reference_assets,
            studio_panel=payload.studio_panel.model_dump(),
        )
        template_recommendations = self._filter_template_recommendations_for_prompt(
            list(template_recommendations),
            prompt=effective_prompt,
            follow_up_mode=follow_up_mode,
            studio_panel=payload.studio_panel.model_dump(),
        )
        template_recommendations = self._merge_template_recommendations_for_prompt(
            prompt=effective_prompt,
            request_reference_assets=request_reference_assets,
            template_recommendations=list(template_recommendations),
        )
        template_recommendations = self._sort_template_recommendations_for_format(
            list(template_recommendations),
            studio_panel=payload.studio_panel.model_dump(),
        )
        template_recommendations = self._collapse_carousel_template_recommendations(
            list(template_recommendations),
            studio_panel=payload.studio_panel.model_dump(),
        )
        template_recommendations = self._annotate_template_recommendation_selection(
            list(template_recommendations),
            studio_panel=payload.studio_panel.model_dump(),
        )
        reference_assets = self._merge_reference_assets_for_prompt(
            prompt=effective_prompt,
            request_reference_assets=request_reference_assets,
            brand_reference_assets=brand_reference_assets,
        )
        reference_assets = self._filter_reference_assets_for_studio_format(
            reference_assets,
            studio_panel=payload.studio_panel.model_dump(),
        )
        tracked_reference_assets = input_access_tracker.wrap_source("reference_assets", reference_assets)
        template_recommendation_payloads = [
            recommendation.model_dump(mode="json") if hasattr(recommendation, "model_dump") else dict(recommendation)
            for recommendation in template_recommendations
        ]
        tracked_template_candidates = input_access_tracker.wrap_source(
            "template_candidates",
            template_recommendation_payloads,
        )
        planning_hints = await self._resolve_generation_decision(
            prompt=effective_prompt,
            studio_panel=payload.studio_panel.model_dump(),
            brand_context=tracked_runtime_brand_context,
            persona_context=tracked_persona_context,
            objective_context=tracked_objective_context,
            template_recommendations=tracked_template_candidates,
            selected_template_id=selected_template_id,
            selected_template_name=preselected_template.name if preselected_template else None,
            reference_assets=tracked_reference_assets,
        )
        logo_asset_path = (
            str(tracked_logo_selection.get("storage_path") or "").strip() or None
            if tracked_logo_selection
            else None
        )
        self.trace.write_payload(
            trace_id,
            "content_request_pre_template_context",
            {
                "prompt": effective_prompt,
                "studio_panel": payload.studio_panel.model_dump(),
                "planning_hints": planning_hints,
                "template_recommendations": tracked_template_candidates,
                "reference_assets": reference_assets,
                "logo_asset_path": logo_asset_path,
                "logo_candidates": logo_candidates,
                "logo_selection": logo_selection,
                "session_memory": session_memory,
                "request_lineage": request_lineage,
                "prompt_lineage": prompt_lineage,
                "prompt_sanitization": prompt_sanitization,
                "prompt_diagnostics": self._build_prompt_diagnostics(
                    prompt=effective_prompt,
                    session_memory=session_memory,
                ),
                "brand_context": tracked_runtime_brand_context,
                "persona_context": tracked_persona_context,
                "objective_context": tracked_objective_context,
            },
        )
        template = preselected_template
        template_meta = await self.template_metadata.get_by_template(template.id) if template else None
        selected_template_name = preselected_template.name if preselected_template else None
        planned_template_id = None
        # When no template is pre-pinned, fall back to the AI-planned template's zone_map
        # so that layout coordinates and design DNA reach the orchestrator even in auto-select mode.
        if template_meta is None and isinstance(planning_hints, dict):
            planned_template_id = self._parse_uuid_or_none(planning_hints.get("template_id"))
            if planned_template_id:
                planned_tmpl = await self.templates.get_scoped(planned_template_id, tenant_id, brand_space_id)
                if planned_tmpl:
                    template_meta = await self.template_metadata.get_by_template(planned_tmpl.id)
                    selected_template_name = selected_template_name or planned_tmpl.name
        if not selected_template_name and isinstance(planning_hints, dict):
            selected_template_name = str(planning_hints.get("template_name") or "").strip() or None
        selected_template_context_id = (
            str(preselected_template.id)
            if preselected_template
            else str(planned_template_id)
            if planned_template_id
            else None
        )
        template_context = self._build_template_context_payload(
            prompt=effective_prompt,
            template_meta=template_meta,
            selected_template_id=selected_template_context_id,
            selected_template_name=selected_template_name,
            template_recommendations=tracked_template_candidates,
            reference_assets=tracked_reference_assets,
            studio_panel=payload.studio_panel.model_dump(),
        )
        planning_hints = self._apply_template_context_surface_policy_to_planning_hints(
            planning_hints,
            template_context,
            payload.studio_panel.model_dump(),
        )
        tracked_template_context = input_access_tracker.wrap_source("template_context", template_context)
        self.trace.write_payload(
            trace_id,
            "content_request",
            {
                "prompt": effective_prompt,
                "studio_panel": payload.studio_panel.model_dump(),
                "planning_hints": planning_hints,
                "template_context": template_context,
                "template_recommendations": tracked_template_candidates,
                "reference_assets": reference_assets,
                "logo_asset_path": logo_asset_path,
                "logo_candidates": logo_candidates,
                "logo_selection": logo_selection,
                "session_memory": session_memory,
                "request_lineage": request_lineage,
                "prompt_lineage": prompt_lineage,
                "prompt_sanitization": prompt_sanitization,
                "prompt_diagnostics": self._build_prompt_diagnostics(
                    prompt=effective_prompt,
                    session_memory=session_memory,
                ),
                "brand_context": tracked_runtime_brand_context,
                "persona_context": tracked_persona_context,
                "objective_context": tracked_objective_context,
            },
        )

        await self.usage.enforce(tenant_id, UsageMetricCode.CONTENT_GENERATIONS)
        retrieved_knowledge, knowledge_state = await self._build_retrieved_knowledge(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            prompt=effective_prompt,
            studio_panel=payload.studio_panel.model_dump(),
        )
        content_format_guide = self.content_format_guide.load()
        tracked_content_format_guide = input_access_tracker.wrap_source(
            "content_format_guide",
            content_format_guide,
        )
        tracked_retrieved_knowledge = input_access_tracker.wrap_source("retrieved_knowledge", retrieved_knowledge)
        knowledge_brief = self.research_editorial.knowledge_brief_from_retrieved(tracked_retrieved_knowledge)
        live_research = self.live_research.gather_sync(
            prompt=effective_prompt,
            studio_panel=payload.studio_panel.model_dump(),
            compiled_context={"knowledge_brief": knowledge_brief},
        )
        tracked_live_research = input_access_tracker.wrap_source("live_research", live_research)
        planning_bundle = self.visual_planning.build_visual_plan(
            prompt=effective_prompt,
            studio_panel=payload.studio_panel.model_dump(),
            brand_context=tracked_runtime_brand_context,
            persona_context=tracked_persona_context,
            objective_context=tracked_objective_context,
            knowledge_brief=knowledge_brief,
            live_research=tracked_live_research,
            content_format_guide=tracked_content_format_guide,
            deliverable_type="visual_generation",
            template_context=tracked_template_context,
        )
        research_editorial_brief = planning_bundle["research_editorial_brief"]
        self._assert_research_guard(prompt=effective_prompt, brief=research_editorial_brief, stage="content.generate")
        format_family_plan = planning_bundle["format_family_plan"]
        content_plan = planning_bundle["content_plan"]
        visual_plan = planning_bundle["visual_plan"]
        self._write_brand_usage_trace(
            trace_id=trace_id,
            context_sections=context["sections"],
            effective_prompt=effective_prompt,
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            studio_panel=payload.studio_panel.model_dump(),
            runtime_brand_context=runtime_brand_context,
            persona=persona,
            objective=objective,
            reference_assets=reference_assets,
            template_recommendations=template_recommendations,
            template_context=template_context,
            retrieved_knowledge=retrieved_knowledge,
            planning_hints=planning_hints,
            explainability={
                "report_stage": "pre_orchestration",
                "generation_trace": "Brand usage snapshot captured before orchestration completed.",
            },
            template=template,
            logo_candidates=logo_candidates,
            logo_selection=logo_selection,
        )
        effective_generate_image = self._effective_generate_image_requested(
            studio_panel=payload.studio_panel.model_dump(),
            generate_image=payload.generate_image,
        )
        response = await asyncio.to_thread(
            self.orchestrator.generate,
            AIOrchestrationRequest(
                tenant_id=tenant_id,
                brand_space_id=brand_space_id,
                user_id=user_id,
                prompt=effective_prompt,
                studio_panel=payload.studio_panel.model_dump(),
                conversation_context=session.conversational_context,
                resolved_brand_context=tracked_runtime_brand_context,
                persona_context=tracked_persona_context,
                objective_context=tracked_objective_context,
                retrieved_knowledge=tracked_retrieved_knowledge,
                template_context=tracked_template_context,
                content_format_guide=tracked_content_format_guide,
                live_research=tracked_live_research,
                research_editorial_brief=research_editorial_brief,
                format_family_plan=format_family_plan,
                content_plan=content_plan,
                visual_plan=visual_plan,
                template_candidates=tracked_template_candidates,
                layout_decision=planning_hints,
                session_memory=session_memory,
                reference_assets=tracked_reference_assets,
                asset_catalog=tracked_reference_assets,
                logo_asset_path=logo_asset_path,
                logo_asset_candidates=tracked_logo_candidates,
                platform_constraints={
                    "platform_preset": payload.studio_panel.platform_preset,
                    "format": payload.studio_panel.format,
                    "file_type": payload.studio_panel.file_type,
                    "size": payload.studio_panel.size or {},
                },
                resolution_policy=tracked_runtime_brand_context.get("context_priority", {}),
                generation_trace_id=trace_id,
                generate_image=effective_generate_image,
                input_access_tracker=input_access_tracker,
            ),
        )
        logger.info(
            "content.generate.response trace_id=%s render_authority=%s final_render_assets=%s final_render_asset=%s image_assets=%s repair_attempts=%s",
            trace_id,
            response.render_authority,
            len(response.final_render_assets or []),
            bool(response.final_render_asset),
            len(response.image_assets or []),
            response.repair_attempts,
        )
        if (
            self._requires_ai_final_render_for_panel(payload.studio_panel.model_dump())
            and effective_generate_image
        ):
            if str(response.render_authority or "").strip().lower() != "ai":
                logger.error(
                    "content.generate.ai_required_wrong_authority trace_id=%s response_render_authority=%s format=%s file_type=%s",
                    trace_id,
                    response.render_authority,
                    payload.studio_panel.format,
                    payload.studio_panel.file_type,
                )
                raise GenerationFailureError(
                    "AI final render is required for this format and backend rendering is disabled.",
                    failure_type="missing_asset",
                    reason_code="ai_final_render_required",
                    user_safe_message="I couldn't prepare the final visual this time because the AI-only render path did not complete. Please regenerate.",
                    retryable=True,
                    rule_source="system",
                    suggested_next_action="Regenerate the creative.",
                    details={"stage": "content.generate", "response_render_authority": response.render_authority},
                )
            if not response.final_render_assets and response.final_render_asset is None:
                logger.error(
                    "content.generate.ai_required_missing_final_render trace_id=%s response_render_authority=%s format=%s file_type=%s",
                    trace_id,
                    response.render_authority,
                    payload.studio_panel.format,
                    payload.studio_panel.file_type,
                )
                raise GenerationFailureError(
                    "AI final render asset is missing and backend fallback rendering is disabled for this format.",
                    failure_type="missing_asset",
                    reason_code="ai_final_render_asset_missing",
                    user_safe_message="I couldn't generate the visual this time because the final AI render asset is missing. Please regenerate.",
                    retryable=True,
                    rule_source="system",
                    suggested_next_action="Regenerate the creative.",
                    details={"stage": "content.generate", "response_render_authority": response.render_authority},
                )
        creative_decision = response.creative_decision.model_dump(mode="json")
        selected_template_id = self._parse_uuid_or_none(response.creative_decision.selected_template_id)
        if response.creative_decision.layout_mode == "synthesized_layout" and not payload.template_id:
            selected_template_id = None
        template = await self.templates.get_scoped(selected_template_id, tenant_id, brand_space_id) if selected_template_id else None
        template_meta = await self.template_metadata.get_by_template(template.id) if template else None
        artifact_state = self.artifacts.build_content_state(
            mode="visual_generation",
            prompt=effective_prompt,
            studio_panel=payload.studio_panel.model_dump(),
            research_objects={
                "knowledge_state": knowledge_state,
                "live_research": live_research,
                "research_editorial_brief": research_editorial_brief,
                "retrieval_channels": list(retrieved_knowledge.keys()),
            },
            planning_objects={
                "format_family_plan": format_family_plan,
                "content_plan": content_plan,
                "visual_plan": visual_plan,
                "message_strategy": response.message_strategy.model_dump(mode="json"),
                "creative_decision": creative_decision,
                "validation_report": response.validation_report.model_dump(mode="json"),
                "render_authority": response.render_authority,
            },
            revision_lineage=self.artifacts.build_revision_lineage(
                parent_version_id=str(payload.source_content_version_id) if payload.source_content_version_id else (session_memory.get("latest_content_version") or {}).get("id"),
                rewrite_mode=follow_up_mode or "fresh_generation",
            ),
            source_linked_artifacts={
                "reference_asset_ids": [asset["asset_id"] for asset in reference_assets],
                "selected_template_id": str(template.id) if template else None,
                "final_render_assets": [asset.storage_path for asset in response.final_render_assets],
            },
        )

        content_version = ContentVersion(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            session_id=session.id,
            created_by=user_id,
            lifecycle_state=ContentLifecycle.GENERATED,
            content_type="content",
            title=response.text.headline,
            prompt=effective_prompt,
            selected_persona_id=persona.id if persona else None,
            selected_template_id=template.id if template else None,
            objective_id=objective.id if objective else None,
            studio_panel=payload.studio_panel.model_dump(),
            generated_payload=response.text.model_dump(),
            blueprint_payload=response.blueprint.model_dump(),
            explainability_metadata={
                **response.explainability,
                "knowledge_state": knowledge_state,
                "live_research": live_research,
                "research_editorial_brief": research_editorial_brief,
                "format_family_plan": format_family_plan,
                "content_plan": content_plan,
                "visual_plan": visual_plan,
                "reference_asset_ids": [asset["asset_id"] for asset in reference_assets],
                "message_strategy": response.message_strategy.model_dump(mode="json"),
                "layout_decision": creative_decision,
                "creative_decision": creative_decision,
                "scene_graph": response.scene_graph.model_dump(mode="json"),
                "validation_report": response.validation_report.model_dump(mode="json"),
                "repair_attempts": response.repair_attempts,
                "render_authority": response.render_authority,
                "final_render_assets": [
                    asset.model_dump(mode="json") for asset in response.final_render_assets
                ],
                "final_render_asset": response.final_render_asset.model_dump(mode="json") if response.final_render_asset else None,
                "logo_candidates": logo_candidates,
                "logo_selection": logo_selection,
                "planning_hints": planning_hints,
                "session_memory": session_memory,
                "request_lineage": request_lineage,
                "prompt_lineage": prompt_lineage,
                "generation_trace_id": trace_id,
                "artifact_state": artifact_state,
            },
            tone_score=response.tone_analysis["score"],
            tone_feedback=response.tone_analysis,
        )
        await self.contents.add(content_version)

        follow_up_intent = (session_memory.get("follow_up_intent") or {})
        latest_content = session_memory.get("latest_content_version") or {}
        parent_content_version_id = payload.source_content_version_id or self._parse_uuid_or_none(latest_content.get("id"))
        if follow_up_intent.get("uses_previous_output") and parent_content_version_id:
            try:
                content_version.parent_version_id = UUID(str(parent_content_version_id))
            except ValueError:
                content_version.parent_version_id = None
            if follow_up_intent.get("mode") == "modify_previous":
                content_version.lifecycle_state = ContentLifecycle.EDITED

        for asset in response.image_assets:
            await self.assets.add(
                GeneratedAsset(
                    tenant_id=tenant_id,
                    brand_space_id=brand_space_id,
                    content_version_id=content_version.id,
                    template_id=template.id if template else None,
                    asset_role=asset.asset_role,
                    mime_type=asset.mime_type,
                    storage_path=asset.storage_path,
                    width=asset.width,
                    height=asset.height,
                    metadata_json=asset.metadata or {},
                )
            )
        persisted_final_render_assets = response.final_render_assets or (
            [response.final_render_asset] if response.final_render_asset else []
        )
        logger.info(
            "content.generate.persist trace_id=%s content_version_id=%s persisted_final_render_assets=%s selected_template_id=%s",
            trace_id,
            content_version.id,
            len(persisted_final_render_assets),
            content_version.selected_template_id,
        )
        for index, asset in enumerate(persisted_final_render_assets, start=1):
            asset_role = AssetRole.RENDER_PREVIEW if index == 1 else AssetRole.RENDER_EXPORT
            await self.assets.add(
                GeneratedAsset(
                    tenant_id=tenant_id,
                    brand_space_id=brand_space_id,
                    content_version_id=content_version.id,
                    template_id=template.id if template else None,
                    asset_role=asset_role,
                    mime_type=asset.mime_type,
                    storage_path=asset.storage_path,
                    width=asset.width,
                    height=asset.height,
                    metadata_json={
                        **(asset.metadata or {}),
                        "render_source": "ai",
                        "generation_stage": "final_render",
                        "slide_index": int((asset.metadata or {}).get("slide_index") or index),
                        "slide_count": int((asset.metadata or {}).get("slide_count") or len(persisted_final_render_assets)),
                    },
                )
            )

        await self._record_session_context(session, payload, content_version)
        await self.usage.increment(tenant_id, UsageMetricCode.CONTENT_GENERATIONS)
        if response.image_assets:
            await self.usage.increment(tenant_id, UsageMetricCode.IMAGE_GENERATIONS, len(response.image_assets))
        elif persisted_final_render_assets:
            await self.usage.increment(tenant_id, UsageMetricCode.IMAGE_GENERATIONS, len(persisted_final_render_assets))
        await self.session.commit()
        self.trace.write_payload(
            trace_id,
            "content_persisted",
            {
                "content_version_id": str(content_version.id),
                "selected_template_id": str(content_version.selected_template_id) if content_version.selected_template_id else None,
                "explainability_metadata": content_version.explainability_metadata,
            },
        )
        self._write_brand_usage_trace(
            trace_id=trace_id,
            context_sections=context["sections"],
            effective_prompt=effective_prompt,
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            studio_panel=payload.studio_panel.model_dump(),
            runtime_brand_context=runtime_brand_context,
            persona=persona,
            objective=objective,
            reference_assets=reference_assets,
            template_recommendations=template_recommendations,
            template_context=template_context,
            retrieved_knowledge=retrieved_knowledge,
            planning_hints=planning_hints,
            explainability=content_version.explainability_metadata,
            template=template,
            logo_candidates=logo_candidates,
            logo_selection=logo_selection,
        )
        return content_version

    async def rewrite(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        user_id: UUID,
        payload: ContentRewriteRequest,
    ) -> ContentVersion:
        original = await self._get_content_scoped(tenant_id, brand_space_id, payload.content_version_id)
        logger.info(
            "content.rewrite.start original_content_version_id=%s revision_scope=%s rewrite_length=%s",
            original.id,
            payload.revision_scope or {},
            len(payload.rewrite_instruction or ""),
        )
        brand = await self.brands.get(brand_space_id)
        if not brand:
            raise NotFoundError("Brand Space not found")
        if str(getattr(brand, "lifecycle_state", BrandSpaceLifecycle.ACTIVE)) != BrandSpaceLifecycle.ACTIVE:
            raise LifecycleError("Brand Space must be Active for rewrite")

        personas = await self.personas.list_by_brand(brand_space_id, tenant_id)
        persona = next((item for item in personas if item.id == original.selected_persona_id), None)
        objectives = await self.objectives.list_by_brand(brand_space_id, tenant_id)
        objective = next((item for item in objectives if item.id == original.objective_id), None)
        original_explainability = original.explainability_metadata if isinstance(original.explainability_metadata, dict) else {}
        stored_persona = original_explainability.get("selected_persona") if isinstance(original_explainability.get("selected_persona"), dict) else {}
        stored_objective = original_explainability.get("selected_objective") if isinstance(original_explainability.get("selected_objective"), dict) else {}
        persona_context = BrandIntelligenceService.persona_to_dict(persona) if persona else dict(stored_persona or {})
        objective_context = BrandIntelligenceService.objective_to_dict(objective) if objective else dict(stored_objective or {})
        resolved_brand_context = (
            dict(getattr(brand, "resolved_brand_context", {}) or {})
            or dict(original_explainability.get("brand_context_snapshot") or {})
        )
        source_prompt = self._source_prompt_for_rewrite(original)
        studio_panel = self._merge_studio_panel(
            original.studio_panel if isinstance(getattr(original, "studio_panel", None), dict) else {},
            payload.studio_panel.model_dump(),
        )
        content_format_guide = self.content_format_guide.load()
        research_editorial_brief = (
            original_explainability.get("research_editorial_brief")
            if isinstance(original_explainability.get("research_editorial_brief"), dict)
            else {}
        )
        template_context = (
            original_explainability.get("template_context")
            if isinstance(original_explainability.get("template_context"), dict)
            else {}
        )
        self._assert_research_guard(prompt=payload.rewrite_instruction, brief=research_editorial_brief, stage="content.rewrite")
        planning_bundle = self.visual_planning.build_visual_plan(
            prompt=payload.rewrite_instruction,
            studio_panel=studio_panel,
            brand_context=resolved_brand_context,
            persona_context=persona_context,
            objective_context=objective_context,
            knowledge_brief=[],
            live_research=(
                original_explainability.get("live_research")
                if isinstance(original_explainability.get("live_research"), dict)
                else {}
            ),
            template_context=template_context,
            content_format_guide=content_format_guide,
            deliverable_type="visual_generation",
        )
        format_family_plan = (
            original_explainability.get("format_family_plan")
            if isinstance(original_explainability.get("format_family_plan"), dict)
            else {}
        ) or planning_bundle["format_family_plan"]
        content_plan = (
            original_explainability.get("content_plan")
            if isinstance(original_explainability.get("content_plan"), dict)
            else {}
        ) or planning_bundle["content_plan"]
        visual_plan = (
            original_explainability.get("visual_plan")
            if isinstance(original_explainability.get("visual_plan"), dict)
            else {}
        ) or planning_bundle["visual_plan"]
        session = await self.sessions.get(original.session_id)
        rewrite_trace = self.trace.start_trace(
            prompt=str(payload.rewrite_instruction or "").strip(),
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            session_id=original.session_id,
            metadata={
                "source_content_version_id": str(original.id),
                "format": studio_panel.get("format") if isinstance(studio_panel, dict) else None,
                "rewrite_mode": "rewrite",
            },
        )
        rewrite_trace_id = (rewrite_trace or {}).get("trace_id")
        compiled_context = self._rewrite_compiled_context(
            original=original,
            source_prompt=source_prompt,
            resolved_brand_context=resolved_brand_context,
            persona_context=persona_context,
            objective_context=objective_context,
            studio_panel=studio_panel,
            session=session,
            content_format_guide=content_format_guide,
            research_editorial_brief=research_editorial_brief,
            format_family_plan=format_family_plan,
            content_plan=content_plan,
            visual_plan=visual_plan,
        )
        self.trace.write_payload(rewrite_trace_id, "compiled_context", compiled_context)
        message_strategy = (
            deepcopy(original_explainability.get("message_strategy"))
            if isinstance(original_explainability.get("message_strategy"), dict)
            else {}
        )
        await self.usage.enforce(tenant_id, UsageMetricCode.CONTENT_GENERATIONS)
        candidate_payload = await self._generate_rewrite_candidate_payload(
            original=original,
            rewrite_instruction=payload.rewrite_instruction,
            revision_scope=payload.revision_scope,
            source_prompt=source_prompt,
            resolved_brand_context=resolved_brand_context,
            compiled_context=compiled_context,
            message_strategy=message_strategy,
            studio_panel=studio_panel,
        )
        self.trace.write_payload(rewrite_trace_id, "rewrite_candidate", candidate_payload)
        repaired_payload, rewrite_preservation = self._repair_rewrite_payload(
            original,
            candidate_payload if isinstance(candidate_payload, dict) else {},
            payload.rewrite_instruction,
            payload.revision_scope,
        )
        missing_targeted_core_fields = rewrite_preservation.get("missing_targeted_core_fields", [])
        if isinstance(missing_targeted_core_fields, list) and missing_targeted_core_fields:
            raise GenerationFailureError(
                "Rewrite output is missing required structured fields.",
                failure_type="invalid_payload",
                reason_code="rewrite_missing_structured_fields",
                user_safe_message="I couldn't finish the rewrite because the revised copy came back incomplete. Please try the rewrite again.",
                retryable=True,
                rule_source="system",
                suggested_next_action="Retry the rewrite.",
                details={
                    "stage": "content.rewrite",
                    "content_version_id": str(original.id),
                    "missing_targeted_core_fields": missing_targeted_core_fields,
                    "instruction_targets": rewrite_preservation.get("instruction_targets", []),
                },
            )

        updated_message_strategy = self._rewrite_message_strategy(
            original_strategy=message_strategy,
            rewritten_payload=repaired_payload,
            rewrite_preservation=rewrite_preservation,
        )
        source_prompt_snapshot = self._source_prompt_for_rewrite(original)
        rewritten_prompt_lineage = {
            "user_prompt_raw": str(payload.rewrite_instruction or "").strip(),
            "generation_prompt_effective": str(payload.rewrite_instruction or "").strip(),
            "rewrite_instruction": str(payload.rewrite_instruction or "").strip(),
            "source_prompt_snapshot": source_prompt_snapshot,
            "request_mode": "modify_previous",
            "source_content_version_id": str(original.id),
        }
        rewritten_request_lineage = {
            "request_mode": "modify_previous",
            "source_content_version_id": str(original.id),
            "inheritance_policy": {
                "inherit_persona": True,
                "inherit_objective": True,
                "inherit_template": True,
                "inherit_reference_assets": True,
                "inherit_copy_context": True,
                "inherit_layout_context": True,
            },
        }
        rewritten_explainability = self._sync_rewrite_scene_graph(
            original_explainability,
            repaired_payload,
        )
        rewritten_explainability["compiled_context"] = compiled_context
        rewritten_explainability["message_strategy"] = updated_message_strategy
        rewritten_explainability["brand_context_snapshot"] = resolved_brand_context
        rewritten_explainability["selected_persona"] = persona_context
        rewritten_explainability["selected_objective"] = objective_context
        rewritten_explainability["rewrite_preservation"] = rewrite_preservation
        rewritten_explainability["rewrite_mode"] = "dedicated_rewrite"
        rewritten_explainability["rewrite_instruction"] = payload.rewrite_instruction
        rewritten_explainability["rewrite_source_content_version_id"] = str(original.id)
        rewritten_explainability["revision_scope"] = payload.revision_scope or {}
        rewritten_explainability["selective_regeneration_plan"] = self._build_selective_regeneration_plan(
            original=original,
            revision_scope=payload.revision_scope,
        )
        logger.info(
            "content.rewrite.plan original_content_version_id=%s selective_regeneration_plan=%s",
            original.id,
            rewritten_explainability["selective_regeneration_plan"],
        )
        rewritten_explainability["format_family_plan"] = format_family_plan
        rewritten_explainability["content_plan"] = content_plan
        rewritten_explainability["visual_plan"] = visual_plan
        rewritten_explainability["source_prompt"] = source_prompt
        rewritten_explainability["prompt_lineage"] = rewritten_prompt_lineage
        rewritten_explainability["request_lineage"] = rewritten_request_lineage
        rewritten_explainability["generation_trace_id"] = rewrite_trace_id
        rewritten_explainability["final_render_assets"] = []
        rewritten_explainability["final_render_asset"] = None
        rewritten_explainability["render_authority"] = "ai"
        rewritten_explainability["validation_report"] = self._rewrite_validation_report(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            user_id=user_id,
            original=original,
            studio_panel=studio_panel,
            resolved_brand_context=resolved_brand_context,
            persona_context=persona_context,
            objective_context=objective_context,
            compiled_context=compiled_context,
            explainability_metadata=rewritten_explainability,
            session=session,
        )
        prior_artifact_state = (
            original_explainability.get("artifact_state")
            if isinstance(original_explainability.get("artifact_state"), dict)
            else {}
        )
        rewritten_explainability["artifact_state"] = self.artifacts.build_content_state(
            mode="visual_generation",
            prompt=payload.rewrite_instruction,
            studio_panel=studio_panel,
            research_objects={
                "live_research": original_explainability.get("live_research"),
                "research_editorial_brief": research_editorial_brief,
                "knowledge_state": original_explainability.get("knowledge_state"),
                "retrieval_channels": list(original_explainability.get("retrieval_channels") or []),
            },
            planning_objects={
                "format_family_plan": format_family_plan,
                "content_plan": content_plan,
                "visual_plan": visual_plan,
                "message_strategy": updated_message_strategy,
                "creative_decision": rewritten_explainability.get("creative_decision"),
                "validation_report": rewritten_explainability.get("validation_report"),
                "selective_regeneration_plan": rewritten_explainability.get("selective_regeneration_plan"),
            },
            revision_lineage=self.artifacts.build_revision_lineage(
                parent_version_id=original.id,
                source_content_version_id=original.id,
                rewrite_mode="dedicated_rewrite",
                rewrite_instruction=payload.rewrite_instruction,
                revision_scope=payload.revision_scope,
                prior_lineage=prior_artifact_state.get("revision_lineage"),
            ),
            source_linked_artifacts={
                "source_content_version_id": str(original.id),
                "reference_asset_ids": original_explainability.get("reference_asset_ids") or [],
            },
        )
        rewritten_blueprint = self._rewrite_blueprint_payload(
            original=original,
            payload=repaired_payload,
            explainability_metadata=rewritten_explainability,
            studio_panel=studio_panel,
            resolved_brand_context=resolved_brand_context,
        )
        initial_tone_feedback = self._rewrite_tone_feedback_for_prompt(original)
        rewritten = ContentVersion(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            session_id=original.session_id,
            folder_id=getattr(original, "folder_id", None),
            parent_version_id=original.id,
            created_by=user_id,
            lifecycle_state=ContentLifecycle.EDITED,
            content_type=str(getattr(original, "content_type", "content") or "content"),
            title=str(repaired_payload.get("headline") or getattr(original, "title", "") or "").strip(),
            prompt=payload.rewrite_instruction,
            selected_persona_id=original.selected_persona_id,
            selected_template_id=original.selected_template_id,
            objective_id=original.objective_id,
            studio_panel=studio_panel,
            generated_payload=repaired_payload,
            blueprint_payload=rewritten_blueprint,
            explainability_metadata=rewritten_explainability,
            tone_score=int(initial_tone_feedback.get("score") or getattr(original, "tone_score", 0) or 0),
            tone_feedback=initial_tone_feedback,
        )
        await self.contents.add(rewritten)
        if session:
            await self._record_session_context(
                session,
                ContentGenerateRequest(
                    prompt=payload.rewrite_instruction,
                    session_id=original.session_id,
                    persona_id=original.selected_persona_id,
                    objective_id=original.objective_id,
                    template_id=original.selected_template_id,
                    studio_panel=payload.studio_panel,
                    generate_image=False,
                ),
                rewritten,
            )
        await self._refresh_content_tone_feedback(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            content=rewritten,
        )
        await self.usage.increment(tenant_id, UsageMetricCode.CONTENT_GENERATIONS)
        await self.session.commit()
        await self.session.refresh(rewritten)
        logger.info(
            "content.rewrite.persist new_content_version_id=%s parent_version_id=%s render_authority=%s final_render_assets=%s",
            rewritten.id,
            original.id,
            rewritten.explainability_metadata.get("render_authority"),
            len((rewritten.explainability_metadata.get("final_render_assets") or [])),
        )
        return rewritten

    async def tone_check(self, brand_space_id: UUID, payload: ToneCheckRequest) -> dict:
        brand = await self.brands.get(brand_space_id)
        if not brand:
            raise NotFoundError("Brand Space not found")
        content_version = (
            await self._get_content_scoped(brand.tenant_id, brand_space_id, payload.content_version_id)
            if payload.content_version_id
            else None
        )
        personas = await self.personas.list_by_brand(brand_space_id, brand.tenant_id)
        persona_id = payload.persona_id or getattr(content_version, "selected_persona_id", None)
        persona = next((item for item in personas if item.id == persona_id), None)
        objectives = await self.objectives.list_by_brand(brand_space_id, brand.tenant_id)
        objective_id = payload.objective_id or getattr(content_version, "objective_id", None)
        objective = next((item for item in objectives if item.id == objective_id), None)
        stored_payload = content_version.generated_payload if content_version and isinstance(content_version.generated_payload, dict) else {}
        stored_explainability = (
            content_version.explainability_metadata
            if content_version and isinstance(content_version.explainability_metadata, dict)
            else {}
        )
        content_payload = payload.content_payload if isinstance(payload.content_payload, dict) else stored_payload
        message_strategy = (
            payload.message_strategy
            if isinstance(payload.message_strategy, dict)
            else stored_explainability.get("message_strategy", {})
        )
        objective_context = (
            payload.objective_context
            if isinstance(payload.objective_context, dict)
            else BrandIntelligenceService.objective_to_dict(objective)
        )
        content_text = str(payload.content or "").strip() or self._tone_check_content_string(content_payload)
        return self.tone.evaluate(
            content=content_text,
            brand_context=brand.resolved_brand_context,
            persona_context=BrandIntelligenceService.persona_to_dict(persona),
            content_payload=content_payload,
            message_strategy=message_strategy,
            objective_context=objective_context,
        )

    async def history(self, tenant_id: UUID, brand_space_id: UUID) -> list[ContentVersion]:
        return await self.contents.list_by_brand(brand_space_id, tenant_id)

    async def detail(self, tenant_id: UUID, brand_space_id: UUID, content_version_id: UUID) -> ContentVersion:
        return await self._get_content_scoped(tenant_id, brand_space_id, content_version_id)

    async def export(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        content_version_id: UUID,
        studio_panel: dict | None,
        blueprint_payload: dict | None = None,
        template_id: UUID | None = None,
    ) -> dict:
        content = await self._get_content_scoped(tenant_id, brand_space_id, content_version_id)
        brand = await self.brands.get_scoped(tenant_id, brand_space_id)
        if not brand:
            raise NotFoundError("Brand Space not found")
        assets = await self.assets.list_by_content(content_version_id)
        visual_assets = [
            asset for asset in assets
            if asset.asset_role in {AssetRole.AI_IMAGE, AssetRole.REFERENCE_CREATIVE, AssetRole.TEMPLATE_PREVIEW}
        ]
        merged_panel = self._merge_studio_panel(content.studio_panel, studio_panel)
        explainability = content.explainability_metadata or {}
        visual_generation_mode = str(explainability.get("mode") or "").strip().lower() == "visual_generation"
        trace_id = str(explainability.get("generation_trace_id") or "").strip() or None
        creative_decision = explainability.get("creative_decision", {}) or explainability.get("layout_decision", {}) or {}
        selected_template_id = template_id or self._parse_uuid_or_none(creative_decision.get("selected_template_id")) or content.selected_template_id
        template = await self.templates.get_scoped(selected_template_id, tenant_id, brand_space_id) if selected_template_id else None
        template_meta = await self.template_metadata.get_by_template(template.id) if template else None
        logo_candidates = await self._collect_logo_asset_candidates(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            brand_context=brand.resolved_brand_context,
        )
        logo_selection = await self._resolve_logo_asset_selection(
            tenant_id=tenant_id,
            brand_space_id=brand_space_id,
            brand_context=brand.resolved_brand_context,
            studio_panel=merged_panel,
            candidates=logo_candidates,
        )
        if not logo_selection and isinstance(explainability.get("logo_selection"), dict):
            logo_selection = dict(explainability.get("logo_selection") or {})
        if not logo_candidates and isinstance(explainability.get("logo_candidates"), list):
            logo_candidates = [
                dict(item)
                for item in explainability.get("logo_candidates") or []
                if isinstance(item, dict)
            ]
        logo_asset_path = (
            str((logo_selection or {}).get("storage_path") or "").strip()
            or await self._resolve_logo_asset_path(
                tenant_id,
                brand_space_id,
                brand.resolved_brand_context,
                studio_panel=merged_panel,
            )
        )
        ai_final_render_assets = self._find_ai_final_render_assets(
            assets,
            explainability=explainability,
            studio_panel=merged_panel,
        )
        selective_regeneration_plan = self._selective_regeneration_plan(explainability)
        logger.info(
            "content.export.start content_version_id=%s trace_id=%s format=%s file_type=%s visual_generation_mode=%s ai_final_render_assets=%s selective_targeted=%s parent_version_id=%s legacy_renderer_allowed=%s",
            content.id,
            trace_id,
            merged_panel.get("format"),
            merged_panel.get("file_type"),
            visual_generation_mode,
            len(ai_final_render_assets),
            list(selective_regeneration_plan.get("targeted_slide_indexes", []) or []),
            content.parent_version_id,
            bool(explainability.get("allow_legacy_renderer_export")),
        )
        resolved_scene_graph = self._resolve_scene_graph_payload(
            stored_scene_graph=explainability.get("scene_graph"),
            studio_panel=merged_panel,
        )
        resolved_blueprint = self._resolve_blueprint_payload(
            stored_blueprint=content.blueprint_payload,
            template_zone_map=template_meta.zone_map if template_meta else None,
            override_blueprint=blueprint_payload,
            studio_panel=merged_panel,
        )
        if str(creative_decision.get("layout_mode") or "").strip().lower() == "synthesized_layout":
            resolved_blueprint["source_mode"] = "synthesized_layout"
            resolved_blueprint["source_template_id"] = None
        font_asset_paths = self._resolve_render_font_assets(brand.resolved_brand_context)
        brand_visual_rules = {
            **brand.resolved_brand_context.get("visual_identity", {}),
            "brand_name": brand.name,
            "identity": brand.resolved_brand_context.get("identity", {}),
        }
        if ai_final_render_assets and not (
            selective_regeneration_plan
            and selective_regeneration_plan.get("targeted_slide_indexes")
        ):
            self.trace.write_payload(
                trace_id,
                "render_input",
                {
                    "content_version_id": str(content.id),
                    "studio_panel": merged_panel,
                    "creative_decision": creative_decision,
                    "scene_graph": explainability.get("scene_graph"),
                    "blueprint": content.blueprint_payload,
                    "template_id": str(template.id) if template else None,
                    "logo_asset_path": logo_asset_path,
                    "logo_selection": logo_selection,
                    "image_asset_paths": [asset.storage_path for asset in visual_assets],
                    "ai_final_render_storage_paths": [asset.storage_path for asset in ai_final_render_assets],
                    "render_authority": "ai",
                },
            )
            payload = await self._build_ai_final_render_delivery_payloads(
                content=content,
                assets=ai_final_render_assets,
                explainability=explainability,
                studio_panel=merged_panel,
                selected_template_id=selected_template_id,
                logo_asset_path=logo_asset_path,
                logo_asset_candidates=logo_candidates,
                logo_selection=logo_selection,
                blueprint_payload=resolved_blueprint,
                creative_decision=creative_decision,
                font_asset_paths=font_asset_paths,
                brand_visual_rules=brand_visual_rules,
            )
            self.trace.write_payload(
                trace_id,
                "render_output",
                {
                    **payload,
                    "render_short_circuit": "ai_final_render",
                },
            )
            return payload
        filter_literal_reference_surfaces = self._should_filter_literal_reference_surfaces_for_render(
            creative_decision=creative_decision,
            scene_graph=resolved_scene_graph,
            blueprint=resolved_blueprint,
        )
        resolved_scene_graph = self._sanitize_scene_graph_for_structured_render(
            resolved_scene_graph,
            filter_literal_reference_surfaces=filter_literal_reference_surfaces,
        )
        render_template = template if (creative_decision.get("layout_mode") or resolved_blueprint.get("source_mode")) != "synthesized_layout" else None
        render_template_metadata = template_meta if render_template else None
        decorative_assets = self._resolve_render_decorative_assets(brand.resolved_brand_context)
        selected_reference_visual_assets = self._selected_reference_visual_assets(
            explainability,
            allow_literal_reference_surfaces=not filter_literal_reference_surfaces,
        )
        persisted_render_assets = [
            self._asset_ref(asset)
            for asset in visual_assets
        ]
        if filter_literal_reference_surfaces:
            persisted_render_assets = self._filter_literal_reference_surface_assets(persisted_render_assets)
        persisted_paths = {asset.storage_path for asset in persisted_render_assets}
        render_image_assets = persisted_render_assets + [
            asset
            for asset in selected_reference_visual_assets
            if asset.storage_path not in persisted_paths
        ]
        if (
            selective_regeneration_plan
            and selective_regeneration_plan.get("targeted_slide_indexes")
        ):
            rewrite_source_content_version_id = (
                str(selective_regeneration_plan.get("rewrite_source_content_version_id") or "").strip()
                or str(explainability.get("rewrite_source_content_version_id") or "").strip()
                or str(content.parent_version_id or "").strip()
            )
            parent_content: ContentVersion | None = None
            parent_assets: list[GeneratedAsset] = []
            if rewrite_source_content_version_id:
                try:
                    parent_content = await self._get_content_scoped(
                        tenant_id,
                        brand_space_id,
                        UUID(rewrite_source_content_version_id),
                    )
                    parent_assets = await self.assets.list_by_content(parent_content.id)
                except (ValueError, NotFoundError):
                    parent_content = None
                    parent_assets = []
            parent_ai_final_render_assets = self._find_ai_final_render_assets(
                parent_assets,
                explainability=(
                    parent_content.explainability_metadata
                    if parent_content and isinstance(parent_content.explainability_metadata, dict)
                    else {}
                ),
                studio_panel=merged_panel,
            )
            if parent_ai_final_render_assets:
                payload = await self._build_selective_ai_final_render_export_payloads(
                    content=content,
                    current_assets=ai_final_render_assets,
                    parent_assets=parent_ai_final_render_assets,
                    parent_content=parent_content,
                    explainability=explainability,
                    studio_panel=merged_panel,
                    selected_template_id=selected_template_id,
                    logo_asset_path=logo_asset_path,
                    logo_asset_candidates=logo_candidates,
                    logo_selection=logo_selection,
                    blueprint_payload=resolved_blueprint,
                    creative_decision=creative_decision,
                    font_asset_paths=font_asset_paths,
                    brand_visual_rules=brand_visual_rules,
                    regeneration_plan=selective_regeneration_plan,
                )
                if payload:
                    logger.info(
                        "content.export.selective_ai_final_render content_version_id=%s parent_content_version_id=%s parent_ai_assets=%s current_ai_assets=%s targeted_slide_indexes=%s",
                        content.id,
                        parent_content.id if parent_content else None,
                        len(parent_ai_final_render_assets),
                        len(ai_final_render_assets),
                        list(selective_regeneration_plan.get('targeted_slide_indexes', []) or []),
                    )
                    self.trace.write_payload(
                        trace_id,
                        "render_input",
                        {
                            "content_version_id": str(content.id),
                            "studio_panel": merged_panel,
                            "creative_decision": creative_decision,
                            "scene_graph": resolved_scene_graph,
                            "blueprint": resolved_blueprint,
                            "template_id": str(render_template.id) if render_template else None,
                            "logo_asset_path": logo_asset_path,
                            "font_asset_paths": font_asset_paths,
                            "image_asset_paths": [asset.storage_path for asset in render_image_assets],
                            "decorative_asset_paths": [asset.storage_path for asset in decorative_assets],
                            "selective_regeneration_plan": selective_regeneration_plan,
                            "parent_ai_final_render_storage_paths": [
                                asset.storage_path for asset in parent_ai_final_render_assets
                            ],
                        },
                    )
                    self.trace.write_payload(
                        trace_id,
                        "render_output",
                        {
                            **payload,
                            "render_short_circuit": "selective_ai_final_render",
                        },
                    )
                    return payload
        if ai_final_render_assets:
            logger.info(
                "content.export.ai_final_render_passthrough content_version_id=%s ai_final_render_assets=%s",
                content.id,
                len(ai_final_render_assets),
            )
            self.trace.write_payload(
                trace_id,
                "render_input",
                {
                    "content_version_id": str(content.id),
                    "studio_panel": merged_panel,
                    "creative_decision": creative_decision,
                    "scene_graph": explainability.get("scene_graph"),
                    "blueprint": content.blueprint_payload,
                    "template_id": str(template.id) if template else None,
                    "logo_asset_path": logo_asset_path,
                    "logo_selection": logo_selection,
                    "image_asset_paths": [asset.storage_path for asset in visual_assets],
                    "ai_final_render_storage_paths": [asset.storage_path for asset in ai_final_render_assets],
                    "render_authority": "ai",
                    "selective_regeneration_plan": selective_regeneration_plan,
                },
            )
            payload = await self._build_ai_final_render_delivery_payloads(
                content=content,
                assets=ai_final_render_assets,
                explainability=explainability,
                studio_panel=merged_panel,
                selected_template_id=selected_template_id,
                logo_asset_path=logo_asset_path,
                logo_asset_candidates=logo_candidates,
                logo_selection=logo_selection,
                blueprint_payload=resolved_blueprint,
                creative_decision=creative_decision,
                font_asset_paths=font_asset_paths,
                brand_visual_rules=brand_visual_rules,
            )
            self.trace.write_payload(
                trace_id,
                "render_output",
                {
                    **payload,
                    "render_short_circuit": "ai_final_render",
                },
            )
            return payload
        should_render_missing_ai_assets_for_rewrite = self._should_render_missing_ai_final_assets_for_rewrite(
            content=content,
            ai_final_render_assets=ai_final_render_assets,
            explainability=explainability,
            selective_regeneration_plan=selective_regeneration_plan,
        )
        if should_render_missing_ai_assets_for_rewrite:
            logger.info(
                "content.export.ai_final_render_rewrite_render_fallback content_version_id=%s trace_id=%s rewrite_source_content_version_id=%s targeted_slide_indexes=%s",
                content.id,
                trace_id,
                str(selective_regeneration_plan.get("rewrite_source_content_version_id") or "").strip()
                or str(explainability.get("rewrite_source_content_version_id") or "").strip()
                or str(content.parent_version_id or ""),
                list(selective_regeneration_plan.get("targeted_slide_indexes", []) or []),
            )
            ai_final_render_assets = await self._regenerate_ai_final_render_assets_for_rewrite(
                tenant_id=tenant_id,
                brand_space_id=brand_space_id,
                content=content,
                brand=brand,
                explainability=explainability,
                studio_panel=merged_panel,
                trace_id=trace_id,
                logo_asset_path=logo_asset_path,
                logo_candidates=logo_candidates,
            )
            if ai_final_render_assets:
                payload = await self._build_ai_final_render_delivery_payloads(
                    content=content,
                    assets=ai_final_render_assets,
                    explainability=content.explainability_metadata or explainability,
                    studio_panel=merged_panel,
                    selected_template_id=selected_template_id,
                    logo_asset_path=logo_asset_path,
                    logo_asset_candidates=logo_candidates,
                    logo_selection=logo_selection,
                    blueprint_payload=resolved_blueprint,
                    creative_decision=creative_decision,
                    font_asset_paths=font_asset_paths,
                    brand_visual_rules=brand_visual_rules,
                )
                self.trace.write_payload(
                    trace_id,
                    "render_output",
                    {
                        **payload,
                        "render_short_circuit": "ai_final_render_regenerated_for_rewrite",
                    },
                )
                return payload
        legacy_renderer_allowed = bool(explainability.get("allow_legacy_renderer_export"))
        if (
            visual_generation_mode
            or self._requires_ai_final_render_for_panel(merged_panel)
            or (
                str(merged_panel.get("format") or "").strip()
                and not legacy_renderer_allowed
            )
        ) and not should_render_missing_ai_assets_for_rewrite:
            logger.error(
                "content.export.ai_final_render_missing content_version_id=%s trace_id=%s render_authority=%s asset_count=%s final_render_assets_meta=%s parent_version_id=%s selective_regeneration_plan=%s",
                content.id,
                trace_id,
                explainability.get("render_authority"),
                len(assets),
                len(explainability.get("final_render_assets") or []),
                content.parent_version_id,
                selective_regeneration_plan,
            )
            raise GenerationFailureError(
                "AI final render asset is missing and legacy renderer export is disabled for this format.",
                failure_type="missing_asset",
                reason_code="ai_final_render_asset_missing",
                user_safe_message="I couldn't prepare the final visual because the AI-rendered asset is missing. Please regenerate.",
                retryable=True,
                rule_source="system",
                suggested_next_action="Regenerate the creative.",
                details={
                    "stage": "content.export",
                    "content_version_id": str(content.id),
                    "legacy_renderer_allowed": legacy_renderer_allowed,
                },
            )
        self.trace.write_payload(
            trace_id,
            "render_input",
            {
                "content_version_id": str(content.id),
                "studio_panel": merged_panel,
                "creative_decision": creative_decision,
                "scene_graph": resolved_scene_graph,
                "blueprint": resolved_blueprint,
                "template_id": str(render_template.id) if render_template else None,
                "logo_asset_path": logo_asset_path,
                "font_asset_paths": font_asset_paths,
                "image_asset_paths": [asset.storage_path for asset in render_image_assets],
                "decorative_asset_paths": [asset.storage_path for asset in decorative_assets],
            },
        )
        response = await self.renderer.render(
            RendererInput(
                tenant_id=content.tenant_id,
                brand_space_id=content.brand_space_id,
                content_version_id=content.id,
                studio_panel=merged_panel,
                blueprint=BlueprintPayload(**resolved_blueprint),
                scene_graph=GenerationSceneGraph.model_validate(resolved_scene_graph) if resolved_scene_graph else None,
                text=StructuredTextPayload(**content.generated_payload),
                template_metadata=self._template_metadata_payload(render_template_metadata),
                template_asset_path=render_template.storage_path if render_template else None,
                logo_asset_path=logo_asset_path,
                image_assets=render_image_assets,
                decorative_assets=decorative_assets,
                font_asset_paths=font_asset_paths,
                brand_visual_rules=brand_visual_rules,
                layout_decision=explainability.get("layout_decision", {}),
                creative_decision=creative_decision,
                validation_report=explainability.get("validation_report", {}),
            )
        )
        payload = response.model_dump(mode="json")
        payload["preview_asset"] = self._decorate_asset_reference(payload.get("preview_asset"))
        payload["export_assets"] = [
            self._decorate_asset_reference(asset)
            for asset in payload.get("export_assets", [])
        ]
        payload["renderer_metadata"]["template_id"] = str(render_template.id) if render_template else None
        payload["renderer_metadata"]["logo_asset_path"] = logo_asset_path
        payload["renderer_metadata"]["scene_graph_used"] = bool(resolved_scene_graph)
        existing_manifest = payload["renderer_metadata"].get("render_manifest") or {}
        payload["renderer_metadata"]["render_manifest"] = {
            "zones_used": existing_manifest.get("zones_used", resolved_blueprint.get("zones", [])),
            "text_blocks_used": existing_manifest.get("text_blocks_used", resolved_blueprint.get("text_blocks", [])),
            "template_zone_map": render_template_metadata.zone_map if render_template_metadata else None,
            "image_asset_paths": [asset.storage_path for asset in visual_assets],
            "decorative_asset_paths": [asset.storage_path for asset in decorative_assets],
            "scene_graph": resolved_scene_graph,
        }
        self.trace.write_payload(trace_id, "render_output", payload)
        await self._persist_render_assets(content, render_template.id if render_template else None, payload)
        await self.session.commit()
        return payload

    async def copy(self, tenant_id: UUID, brand_space_id: UUID, content_version_id: UUID) -> dict:
        content = await self._get_content_scoped(tenant_id, brand_space_id, content_version_id)
        return {
            "headline": content.generated_payload.get("headline", ""),
            "body": content.generated_payload.get("body", ""),
            "cta": content.generated_payload.get("cta", ""),
            "hashtags": content.generated_payload.get("hashtags", []),
        }
