from __future__ import annotations

from collections import Counter, defaultdict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.brand_intelligence import BrandIntelligenceService
from app.core.config import get_settings
from app.core.enums import AssetValidationState, ConflictSeverity
from app.core.exceptions import NotFoundError
from app.models.brand import BrandSpace
from app.models.brand_assets import AssetValidationResult, DataConflict, ResolvedBrandContextSnapshot
from app.models.knowledge import KnowledgeAsset, Template
from app.repositories.brand import (
    BrandSectionRepository,
    BrandSpaceRepository,
    GuardrailRepository,
    ObjectiveRepository,
    PersonaRepository,
)
from app.repositories.brand_assets import (
    AssetValidationResultRepository,
    AudienceInsightAssetRepository,
    AudienceInsightStructuredDataRepository,
    BrandLogoAssetRepository,
    BrandLogoMetadataRepository,
    ColorPaletteEntryRepository,
    DataConflictRepository,
    MoodBoardAssetRepository,
    PositiveWordRepository,
    NegativeWordRepository,
    ReplaceableWordRepository,
    ReusableBrandAssetRepository,
    ResolvedBrandContextSnapshotRepository,
    TypographyGuideRepository,
    VisualReferenceAssetRepository,
    WordBankUploadRepository,
)
from app.repositories.knowledge import KnowledgeAssetRepository, TemplateMetadataRepository, TemplateRepository
from app.utils.palette_roles import derive_palette_roles, is_soft_neutral_color, normalize_hex


class DataValidatorService:
    TEMPLATE_PALETTE_DISTANCE_TOLERANCE = 36.0

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()
        self.brands = BrandSpaceRepository(session)
        self.sections = BrandSectionRepository(session)
        self.personas = PersonaRepository(session)
        self.guardrails = GuardrailRepository(session)
        self.objectives = ObjectiveRepository(session)
        self.assets = KnowledgeAssetRepository(session)
        self.logo_assets = BrandLogoAssetRepository(session)
        self.logo_metadata = BrandLogoMetadataRepository(session)
        self.audience_assets = AudienceInsightAssetRepository(session)
        self.audience_structured = AudienceInsightStructuredDataRepository(session)
        self.visual_references = VisualReferenceAssetRepository(session)
        self.mood_boards = MoodBoardAssetRepository(session)
        self.reusable_assets = ReusableBrandAssetRepository(session)
        self.palette_entries = ColorPaletteEntryRepository(session)
        self.typography_guides = TypographyGuideRepository(session)
        self.word_bank_uploads = WordBankUploadRepository(session)
        self.positive_words = PositiveWordRepository(session)
        self.negative_words = NegativeWordRepository(session)
        self.replaceable_words = ReplaceableWordRepository(session)
        self.validation_results = AssetValidationResultRepository(session)
        self.conflicts = DataConflictRepository(session)
        self.snapshots = ResolvedBrandContextSnapshotRepository(session)
        self.templates = TemplateRepository(session)
        self.template_metadata = TemplateMetadataRepository(session)
        self.intelligence = BrandIntelligenceService()

    async def refresh_brand_context(self, brand_space_id: UUID) -> tuple[BrandSpace, ResolvedBrandContextSnapshot]:
        brand = await self.brands.get(brand_space_id)
        if not brand:
            raise NotFoundError("Brand Space not found")

        base_context = await self._build_base_context(brand)
        assets = [
            asset
            for asset in await self.assets.list_by_brand(brand_space_id, brand.tenant_id)
            if asset.lifecycle_state != "deleted"
        ]
        active_assets = [asset for asset in assets if asset.is_active and asset.lifecycle_state != "failed"]

        warnings: list[str] = []
        excluded_asset_ids: list[str] = []
        await self.conflicts.delete_open_for_brand(brand.tenant_id, brand_space_id)
        conflict_records: list[DataConflict] = []

        palette_summary, palette_warnings, palette_conflicts, palette_assets = await self._resolve_palette(
            brand.tenant_id,
            brand_space_id,
        )
        warnings.extend(palette_warnings)
        conflict_records.extend(palette_conflicts)

        typography_summary = await self._resolve_typography(brand.tenant_id, brand_space_id)
        logo_summary = await self._resolve_logos(brand.tenant_id, brand_space_id)
        audience_summary = await self._resolve_audience(brand.tenant_id, brand_space_id)
        reference_summary, template_conflicts = await self._resolve_references_and_templates(
            brand.tenant_id,
            brand_space_id,
            palette_summary,
            typography_summary,
        )
        conflict_records.extend(template_conflicts)
        mood_board_summary = await self._resolve_mood_boards(brand.tenant_id, brand_space_id)
        reusable_asset_summary = await self._resolve_reusable_assets(brand.tenant_id, brand_space_id)
        word_bank_summary = await self._resolve_word_banks(brand.tenant_id, brand_space_id)
        legal_disclaimers_summary = await self._resolve_legal_disclaimers(brand.tenant_id, brand_space_id)
        cta_templates_summary = await self._resolve_cta_templates(brand.tenant_id, brand_space_id)

        for conflict in conflict_records:
            self.session.add(conflict)
            warnings.append(conflict.details_json.get("summary") or conflict.conflict_type.replace("_", " ").title())

        for asset in assets:
            result = await self._upsert_validation_result_for_asset(
                asset=asset,
                palette_asset_ids=palette_assets,
                conflict_records=conflict_records,
            )
            if result.validation_state == AssetValidationState.EXCLUDED:
                excluded_asset_ids.append(str(asset.id))

        identity = dict(base_context.get("identity", {}))
        if logo_summary["logos"]:
            identity["logo_assets"] = logo_summary["logos"]
            identity["logo_asset_ids"] = [logo["asset_id"] for logo in logo_summary["logos"]]
            if not identity.get("logo_asset_id"):
                identity["logo_asset_id"] = logo_summary["logos"][0]["asset_id"]
            if not identity.get("logo_asset_path") and logo_summary.get("primary_storage_path"):
                identity["logo_asset_path"] = logo_summary["primary_storage_path"]
            identity["logo_rules"] = logo_summary["logo_rules"]

        visual_identity = dict(base_context.get("visual_identity", {}))
        explicit_palette_roles = dict(visual_identity.get("brand_color_palette", {}) or {})
        if palette_summary["entries"]:
            visual_identity["palette_entries"] = palette_summary["entries"]
        if typography_summary:
            visual_identity["typography"] = typography_summary
        if reference_summary["templates"]:
            visual_identity["template_intelligence"] = reference_summary["templates"]
        if reference_summary.get("synthesis"):
            visual_identity["design_system"] = reference_summary["synthesis"]
            if reference_summary["synthesis"].get("component_motifs"):
                visual_identity["component_motifs"] = reference_summary["synthesis"]["component_motifs"]
            if reference_summary["synthesis"].get("gradient_preferences"):
                visual_identity["gradient_preferences"] = reference_summary["synthesis"]["gradient_preferences"]
            if reference_summary["synthesis"].get("background_style") and not visual_identity.get("background_style"):
                visual_identity["background_style"] = reference_summary["synthesis"]["background_style"]
            if reference_summary["synthesis"].get("logo_anchor") and not visual_identity.get("logo_position"):
                visual_identity["logo_position"] = reference_summary["synthesis"]["logo_anchor"]
        if palette_summary["entries"]:
            visual_identity["brand_color_palette"] = derive_palette_roles(
                {
                    "brand_color_palette": explicit_palette_roles or palette_summary["role_map"],
                    "palette_entries": palette_summary["entries"],
                    "template_intelligence": reference_summary["templates"],
                }
            )
        if reference_summary["references"]:
            visual_identity["reference_creatives"] = reference_summary["references"]
            visual_identity["reference_creative_asset_ids"] = [
                reference["asset_id"] for reference in reference_summary["references"]
            ]
        if mood_board_summary:
            visual_identity["mood_boards"] = mood_board_summary
            visual_identity["mood_board_asset_ids"] = [
                board["asset_id"] for board in mood_board_summary if board.get("asset_id")
            ]
        if reusable_asset_summary["all"]:
            visual_identity["reusable_design_assets"] = reusable_asset_summary["all"]
            visual_identity["reusable_design_asset_ids"] = [
                item["id"] for item in reusable_asset_summary["all"] if item.get("id")
            ]
            visual_identity["icon_asset_ids"] = reusable_asset_summary["icon_asset_ids"]
            visual_identity["decorative_asset_ids"] = reusable_asset_summary["decorative_asset_ids"]
            visual_identity["logo_variant_asset_ids"] = reusable_asset_summary["logo_variant_asset_ids"]
        if (
            reusable_asset_summary["approved"]
            or reusable_asset_summary["reference_only"]
            or reusable_asset_summary["excluded"]
        ):
            visual_identity["reusable_design_asset_review"] = {
                "approved": reusable_asset_summary["approved"],
                "reference_only": reusable_asset_summary["reference_only"],
                "excluded": reusable_asset_summary["excluded"],
            }

        guardrails = dict(base_context.get("guardrails", {}))
        if word_bank_summary:
            guardrails["positive_word_bank"] = word_bank_summary["positive_words"]
            guardrails["negative_word_bank"] = word_bank_summary["negative_words"]
            guardrails["replaceable_words"] = word_bank_summary["replaceable_words"]
            guardrails["replaceable_word_map"] = word_bank_summary["replaceable_map"]

        brand_assets_summary = {}
        if legal_disclaimers_summary:
            brand_assets_summary["legal_disclaimers"] = legal_disclaimers_summary
        if cta_templates_summary:
            brand_assets_summary["cta_templates"] = cta_templates_summary

        context_json = {
            **base_context,
            "identity": identity,
            "visual_identity": visual_identity,
            "guardrails": guardrails,
            "audience_insights": audience_summary,
            "brand_assets": brand_assets_summary,
            "validation": {
                "warnings": list(dict.fromkeys(warnings)),
                "excluded_asset_ids": excluded_asset_ids,
                "conflict_count": len(conflict_records),
            },
            "context_priority": {
                "highest": [
                    "guardrails",
                    "identity",
                    "foundations",
                    "voice_tone",
                    "visual_identity",
                    "audience_insights",
                    "prompt_intelligence",
                ],
                "supplemental": [
                    "strategy",
                    "brand",
                    "campaign_history",
                    "template",
                    "metadata",
                    "reference_creative",
                    "mood_board",
                ],
            },
        }

        brand.resolved_brand_context = context_json
        snapshot = ResolvedBrandContextSnapshot(
            tenant_id=brand.tenant_id,
            brand_space_id=brand.id,
            snapshot_kind="validated",
            status="active",
            warnings=list(dict.fromkeys(warnings)),
            conflict_ids=[str(conflict.id) for conflict in conflict_records],
            excluded_asset_ids=excluded_asset_ids,
            context_json=context_json,
        )
        self.session.add(snapshot)
        await self.session.flush()
        await self.snapshots.trim_for_brand(
            brand.tenant_id,
            brand.id,
            keep_latest=self.settings.validation_snapshot_retention_count,
        )
        await self.session.commit()
        await self.session.refresh(snapshot)
        await self.session.refresh(brand)
        return brand, snapshot

    async def get_validation_summary(self, tenant_id: UUID, brand_space_id: UUID) -> dict:
        snapshot = await self.snapshots.latest_for_brand(tenant_id, brand_space_id)
        conflicts = await self.conflicts.list_for_brand(tenant_id, brand_space_id)
        assets = await self.assets.list_by_brand(brand_space_id, tenant_id)
        validations = await self.validation_results.list_by_asset_ids([asset.id for asset in assets])
        return {
            "warnings": snapshot.warnings if snapshot else [],
            "conflicts": conflicts,
            "excluded_assets": snapshot.excluded_asset_ids if snapshot else [],
            "validation_results": validations,
            "snapshot": snapshot,
        }

    async def get_latest_snapshot(self, tenant_id: UUID, brand_space_id: UUID) -> ResolvedBrandContextSnapshot | None:
        return await self.snapshots.latest_for_brand(tenant_id, brand_space_id)

    @staticmethod
    def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
        normalized = normalize_hex(value)
        if not normalized:
            return None
        text = normalized.lstrip("#")
        return tuple(int(text[index:index + 2], 16) for index in range(0, 6, 2))

    @staticmethod
    def _rgb_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> float:
        return sum((left[index] - right[index]) ** 2 for index in range(3)) ** 0.5

    @classmethod
    def _template_color_matches_palette(
        cls,
        color: str,
        palette_hexes: set[str],
        palette_rgbs: list[tuple[int, int, int]],
    ) -> bool:
        normalized = normalize_hex(color)
        if not normalized:
            return False
        if normalized in palette_hexes:
            return True
        rgb = cls._hex_to_rgb(normalized)
        if not rgb:
            return False
        if is_soft_neutral_color(rgb):
            return True
        return any(
            cls._rgb_distance(rgb, palette_rgb) <= cls.TEMPLATE_PALETTE_DISTANCE_TOLERANCE
            for palette_rgb in palette_rgbs
        )

    @classmethod
    def _normalized_palette_role_map(cls, entries: list[dict[str, str]]) -> dict[str, str]:
        return derive_palette_roles({"palette_entries": entries})

    async def _build_base_context(self, brand: BrandSpace) -> dict:
        sections = await self.sections.list_current_sections(brand.id, brand.tenant_id)
        personas = await self.personas.list_by_brand(brand.id, brand.tenant_id)
        guardrails = await self.guardrails.list_by_brand(brand.id, brand.tenant_id)
        objectives = await self.objectives.list_by_brand(brand.id, brand.tenant_id)
        return self.intelligence.build_context(
            brand_space=brand,
            sections=[{"section_code": item.section_code, "payload": item.payload} for item in sections],
            personas=personas,
            guardrails=guardrails,
            objectives=objectives,
        )

    async def _resolve_logos(self, tenant_id: UUID, brand_space_id: UUID) -> dict:
        logos = await self.logo_assets.list_for_brand(tenant_id, brand_space_id)
        payload: list[dict] = []
        aggregated_rules = {"compatibility": [], "size_rules": [], "fonts": [], "taglines": []}
        primary_storage_path: str | None = None
        seen_asset_ids: set[str] = set()
        for logo in logos:
            metadata = await self.logo_metadata.get_by_logo_asset(logo.id)
            source_asset = await self.assets.get_scoped(logo.knowledge_asset_id, tenant_id, brand_space_id)
            storage_path = source_asset.storage_path if source_asset else None
            asset_id = str(logo.knowledge_asset_id)
            if storage_path and not primary_storage_path:
                primary_storage_path = storage_path
            seen_asset_ids.add(asset_id)
            payload.append(
                {
                    "asset_id": asset_id,
                    "variant_label": logo.variant_label,
                    "compatibility": logo.compatibility,
                    "usage_metadata": logo.usage_metadata,
                    "storage_path": storage_path,
                    "mime_type": source_asset.mime_type if source_asset else None,
                    "logo_colors": metadata.logo_colors if metadata else [],
                    "size_rules": metadata.size_rules if metadata else {},
                    "font_details": metadata.font_details if metadata else {},
                    "tagline": metadata.tagline if metadata else None,
                }
            )
            aggregated_rules["compatibility"].extend(logo.compatibility)
            if metadata:
                if metadata.size_rules:
                    aggregated_rules["size_rules"].append(metadata.size_rules)
                if metadata.font_details:
                    aggregated_rules["fonts"].append(metadata.font_details)
                if metadata.tagline:
                    aggregated_rules["taglines"].append(metadata.tagline)

        # Fall back to direct logo attachments when specialized logo records are
        # missing or stale, so validated brand context can still recover a real
        # stored logo from uploads.
        fallback_assets = await self.assets.list_by_field(
            brand_space_id,
            "logo",
            tenant_id=tenant_id,
            active_only=True,
        )
        for source_asset in fallback_assets:
            asset_id = str(source_asset.id)
            if asset_id in seen_asset_ids:
                continue
            if source_asset.lifecycle_state in {"deleted", "failed"}:
                continue
            if source_asset.storage_path and not primary_storage_path:
                primary_storage_path = source_asset.storage_path
            usage_metadata = {}
            if isinstance(source_asset.normalized_data_json, dict):
                usage_metadata = source_asset.normalized_data_json.get("usage_metadata", {}) or {}
            structured_data = source_asset.structured_data_json if isinstance(source_asset.structured_data_json, dict) else {}
            variant_label = None
            if isinstance(source_asset.metadata_json, dict):
                variant_label = source_asset.metadata_json.get("variant_label")
            payload.append(
                {
                    "asset_id": asset_id,
                    "variant_label": variant_label,
                    "compatibility": usage_metadata.get("compatible_backgrounds", []),
                    "usage_metadata": usage_metadata,
                    "storage_path": source_asset.storage_path,
                    "mime_type": source_asset.mime_type,
                    "logo_colors": structured_data.get("logo_colors", []),
                    "size_rules": structured_data.get("size_rules", {}),
                    "font_details": structured_data.get("font_details", {}),
                    "tagline": structured_data.get("tagline"),
                }
            )
            compatible_backgrounds = usage_metadata.get("compatible_backgrounds", [])
            if compatible_backgrounds:
                aggregated_rules["compatibility"].extend(compatible_backgrounds)
            if structured_data.get("size_rules"):
                aggregated_rules["size_rules"].append(structured_data["size_rules"])
            if structured_data.get("font_details"):
                aggregated_rules["fonts"].append(structured_data["font_details"])
            if structured_data.get("tagline"):
                aggregated_rules["taglines"].append(structured_data["tagline"])
        return {
            "logos": payload,
            "logo_rules": aggregated_rules,
            "primary_storage_path": primary_storage_path,
        }

    async def _resolve_audience(self, tenant_id: UUID, brand_space_id: UUID) -> dict:
        assets = await self.audience_assets.list_for_brand(tenant_id, brand_space_id)
        segments: list[dict] = []
        behaviors: list[str] = []
        motivations: list[str] = []
        pain_points: list[str] = []
        objections: list[str] = []
        desired_outcomes: list[str] = []
        preferences: list[str] = []
        trust_signals: list[str] = []
        proof_cues: list[str] = []
        comparison_points: list[str] = []
        demographics: dict[str, str] = {}
        psychographics: dict[str, str] = {}
        summaries: list[str] = []
        research_evidence: list[dict] = []
        quality_snapshots: list[dict[str, float]] = []
        for asset in assets:
            structured = await self.audience_structured.get_by_audience_asset(asset.id)
            if not structured:
                continue
            segments.extend(structured.audience_segments)
            behaviors.extend(structured.behaviors)
            motivations.extend(structured.motivations)
            pain_points.extend(structured.pain_points)
            objections.extend(getattr(structured, "objections", []) or [])
            desired_outcomes.extend(getattr(structured, "desired_outcomes", []) or [])
            preferences.extend(structured.preferences)
            trust_signals.extend(getattr(structured, "trust_signals", []) or [])
            proof_cues.extend(getattr(structured, "proof_cues", []) or [])
            comparison_points.extend(getattr(structured, "comparison_points", []) or [])
            demographics.update(structured.demographics)
            psychographics.update(structured.psychographics)
            if structured.research_summary:
                summaries.append(structured.research_summary)
            analysis_metadata = (
                asset.source_metadata_json.get("analysis_metadata", {})
                if isinstance(getattr(asset, "source_metadata_json", None), dict)
                else {}
            )
            structured_analysis_quality = getattr(structured, "analysis_quality", {})
            if not isinstance(structured_analysis_quality, dict) or not structured_analysis_quality:
                structured_analysis_quality = (
                    analysis_metadata.get("analysis_quality", {})
                    if isinstance(analysis_metadata, dict)
                    else {}
                )
            raw_evidence = getattr(structured, "research_evidence", {})
            if not isinstance(raw_evidence, dict) or not raw_evidence:
                raw_evidence = analysis_metadata.get("audience_evidence", {}) if isinstance(analysis_metadata, dict) else {}
            evidence_confidence = self._coerce_float(
                getattr(structured, "evidence_confidence", None),
                fallback=self._coerce_float(getattr(asset, "confidence", None)),
            )
            source_agreement_score = self._coerce_float(
                getattr(structured, "source_agreement_score", None),
                fallback=self._coerce_float(structured_analysis_quality.get("source_agreement_score")),
            )
            analysis_quality_score = self._coerce_float(structured_analysis_quality.get("analysis_quality_score"))
            research_signal_count = self._coerce_int(
                getattr(structured, "research_signal_count", None),
                fallback=self._coerce_int(
                    analysis_metadata.get("research_signal_count") if isinstance(analysis_metadata, dict) else None
                ),
            )
            if any(value > 0.0 for value in (evidence_confidence, source_agreement_score, analysis_quality_score)):
                quality_snapshots.append(
                    {
                        "evidence_confidence": evidence_confidence,
                        "source_agreement_score": source_agreement_score,
                        "analysis_quality_score": analysis_quality_score,
                    }
                )
            if isinstance(raw_evidence, dict):
                for field, items in raw_evidence.items():
                    for item in items or []:
                        if not isinstance(item, dict):
                            continue
                        value = str(item.get("value") or "").strip()
                        snippet = str(item.get("source_snippet") or value).strip()
                        confidence = item.get("confidence")
                        if not value:
                            continue
                        research_evidence.append(
                            {
                                "field": str(field or "").strip(),
                                "value": value,
                                "source_snippet": snippet,
                                "confidence": float(confidence) if confidence is not None else None,
                                "evidence_confidence": evidence_confidence,
                                "source_agreement_score": source_agreement_score,
                                "analysis_quality_score": analysis_quality_score,
                                "research_signal_count": research_signal_count,
                            }
                        )
                        research_evidence[-1]["ranking_score"] = self._research_evidence_rank(research_evidence[-1])
        deduped_research_evidence: list[dict] = []
        seen_research_keys: set[tuple[str, str, str]] = set()
        for item in sorted(
            research_evidence,
            key=lambda entry: (
                -float(entry.get("ranking_score") or 0.0),
                str(entry.get("field") or ""),
                str(entry.get("value") or ""),
            ),
        ):
            key = (
                str(item.get("field") or "").casefold(),
                str(item.get("value") or "").casefold(),
                str(item.get("source_snippet") or "").casefold(),
            )
            if key in seen_research_keys:
                continue
            seen_research_keys.add(key)
            deduped_research_evidence.append(item)
        deduped_summaries = self._dedupe_list(summaries)
        research_highlights = self._ranked_research_highlights(
            summaries=deduped_summaries,
            research_evidence=deduped_research_evidence,
            proof_cues=proof_cues,
            trust_signals=trust_signals,
            comparison_points=comparison_points,
            objections=objections,
            desired_outcomes=desired_outcomes,
        )
        research_summary = " ".join(deduped_summaries[:4]).strip()
        if not research_summary:
            research_summary = " ".join(research_highlights[:4]).strip()
        research_quality = {
            "analysis_quality_score": max((item["analysis_quality_score"] for item in quality_snapshots), default=0.0),
            "source_agreement_score": max((item["source_agreement_score"] for item in quality_snapshots), default=0.0),
            "evidence_confidence": max((item["evidence_confidence"] for item in quality_snapshots), default=0.0),
        }
        return {
            "segments": self._dedupe_dict_list(segments, key="label"),
            "behaviors": self._dedupe_list(behaviors),
            "motivations": self._dedupe_list(motivations),
            "pain_points": self._dedupe_list(pain_points),
            "objections": self._dedupe_list(objections),
            "desired_outcomes": self._dedupe_list(desired_outcomes),
            "preferences": self._dedupe_list(preferences),
            "trust_signals": self._dedupe_list(trust_signals),
            "proof_cues": self._dedupe_list(proof_cues),
            "comparison_points": self._dedupe_list(comparison_points),
            "demographics": demographics,
            "psychographics": psychographics,
            "research_summary": research_summary,
            "research_highlights": research_highlights,
            "research_summaries": deduped_summaries[:6],
            "research_signal_count": len(deduped_research_evidence) if deduped_research_evidence else len(deduped_summaries) if deduped_summaries else len(research_highlights),
            "research_evidence": deduped_research_evidence[:24],
            "research_quality": research_quality,
        }

    @staticmethod
    def _template_analysis_records(
        references: list[dict],
        templates: list[dict],
    ) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        for reference in references:
            if not isinstance(reference, dict):
                continue
            style_characteristics = (
                reference.get("style_characteristics")
                if isinstance(reference.get("style_characteristics"), dict)
                else {}
            )
            layout_structure = (
                reference.get("layout_structure")
                if isinstance(reference.get("layout_structure"), dict)
                else {}
            )
            records.append(
                {
                    "source": "reference",
                    "layout_type": style_characteristics.get("layout_type") or layout_structure.get("layout_type"),
                    "background_style": style_characteristics.get("background_style", {}),
                    "editable_zones": reference.get("reusable_zones") or layout_structure.get("zones") or [],
                    "component_motifs": style_characteristics.get("component_motifs", {}),
                    "typography_dna": style_characteristics.get("typography_dna", {}),
                    "infographic_elements": style_characteristics.get("infographic_elements", {}),
                    "visual_mood": style_characteristics.get("visual_mood"),
                    "design_style": style_characteristics.get("design_style"),
                    "visual_hierarchy": style_characteristics.get("visual_hierarchy", {}),
                    "content_structure": style_characteristics.get("content_structure", {}),
                    "image_treatment": style_characteristics.get("image_treatment", {}),
                    "layout_dna": style_characteristics.get("layout_dna", {}),
                    "composition_logic": style_characteristics.get("composition_logic", {}),
                    "visual_craft_dna": style_characteristics.get("visual_craft_dna", {}),
                    "subject_semantics": style_characteristics.get("subject_semantics", {}),
                    "brand_cues": style_characteristics.get("brand_cues", {}),
                    "design_tokens": style_characteristics.get("design_tokens", {}),
                    "editorial_dna": style_characteristics.get("editorial_dna", {}),
                    "brand_score": reference.get("brand_score"),
                }
            )
        for template in templates:
            if not isinstance(template, dict):
                continue
            analysis = template.get("analysis") if isinstance(template.get("analysis"), dict) else {}
            if not analysis:
                continue
            records.append(
                {
                    "source": "template",
                    "layout_type": analysis.get("layout_type"),
                    "background_style": analysis.get("background_style", {}),
                    "editable_zones": analysis.get("editable_zones") or analysis.get("reusable_zones") or [],
                    "component_motifs": analysis.get("component_motifs", {}),
                    "typography_dna": analysis.get("typography_dna", {}),
                    "infographic_elements": analysis.get("infographic_elements", {}),
                    "visual_mood": analysis.get("visual_mood"),
                    "design_style": analysis.get("design_style"),
                    "visual_hierarchy": analysis.get("visual_hierarchy", {}),
                    "content_structure": analysis.get("content_structure", {}),
                    "image_treatment": analysis.get("image_treatment", {}),
                    "layout_dna": analysis.get("layout_dna", {}),
                    "composition_logic": analysis.get("composition_logic", {}),
                    "visual_craft_dna": analysis.get("visual_craft_dna", {}),
                    "subject_semantics": analysis.get("subject_semantics", {}),
                    "brand_cues": analysis.get("brand_cues", {}),
                    "design_tokens": analysis.get("design_tokens", {}),
                    "editorial_dna": analysis.get("editorial_dna", {}),
                    "gradients": analysis.get("gradients", []),
                    "logo_anchor": analysis.get("logo_anchor"),
                    "font_size_hints": analysis.get("font_size_hints", []),
                    "brand_score": analysis.get("brand_score"),
                }
            )
        return records

    @staticmethod
    def _most_common_values(values: list[str], *, limit: int = 3) -> list[str]:
        cleaned = [str(value).strip() for value in values if str(value).strip()]
        if not cleaned:
            return []
        counts = Counter(item.casefold() for item in cleaned)
        first_seen: dict[str, str] = {}
        for item in cleaned:
            first_seen.setdefault(item.casefold(), item)
        ordered = sorted(counts.items(), key=lambda item: (-item[1], first_seen[item[0]]))
        return [first_seen[key] for key, _ in ordered[:limit]]

    @classmethod
    def _synthesize_component_motifs(cls, records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
        total = max(len(records), 1)
        support: dict[str, int] = {}
        chosen: dict[str, dict[str, object]] = {}
        for record in records:
            motifs = record.get("component_motifs") if isinstance(record.get("component_motifs"), dict) else {}
            for key, value in motifs.items():
                if isinstance(value, dict):
                    detected = value.get("detected")
                    if detected is False:
                        continue
                    if not value and detected is None:
                        continue
                    support[key] = support.get(key, 0) + 1
                    existing = chosen.get(key, {})
                    if len(value) >= len(existing):
                        chosen[key] = dict(value)
                elif value:
                    support[key] = support.get(key, 0) + 1
                    chosen[key] = {"value": value}
        return {
            key: {
                **value,
                "sample_support": support.get(key, 0),
                "sample_support_ratio": round(support.get(key, 0) / total, 4),
            }
            for key, value in chosen.items()
            if support.get(key, 0) > 0
        }

    @classmethod
    def _synthesize_editorial_patterns(cls, records: list[dict[str, object]]) -> dict[str, object]:
        story_arc_counter: Counter[tuple[str, ...]] = Counter()
        headline_patterns: list[str] = []
        sample_summaries: list[str] = []
        seen_headlines: set[str] = set()
        seen_summaries: set[str] = set()
        slide_count_candidates: list[str] = []
        explanation_styles = cls._most_common_values(
            [
                str((item.get("editorial_dna") or {}).get("explanation_style") or "")
                for item in records
                if isinstance(item.get("editorial_dna"), dict)
            ],
            limit=4,
        )
        closing_styles = cls._most_common_values(
            [
                str((item.get("editorial_dna") or {}).get("closing_style") or "")
                for item in records
                if isinstance(item.get("editorial_dna"), dict)
            ],
            limit=3,
        )
        copy_densities = cls._most_common_values(
            [
                str((item.get("editorial_dna") or {}).get("copy_density") or "")
                for item in records
                if isinstance(item.get("editorial_dna"), dict)
            ],
            limit=3,
        )
        disclaimer_support = 0
        for item in records:
            editorial_dna = item.get("editorial_dna") if isinstance(item.get("editorial_dna"), dict) else {}
            story_arc = tuple(
                str(role).strip()
                for role in (editorial_dna.get("story_arc_roles") or [])
                if str(role).strip()
            )
            if story_arc:
                story_arc_counter[story_arc] += 1
            slide_count = editorial_dna.get("page_count_hint")
            if slide_count not in (None, "", 0):
                slide_count_candidates.append(str(slide_count))
            if editorial_dna.get("disclaimer_present"):
                disclaimer_support += 1
            for pattern in (editorial_dna.get("headline_patterns") or [])[:4]:
                normalized = str(pattern).strip()
                if normalized and normalized.casefold() not in seen_headlines:
                    seen_headlines.add(normalized.casefold())
                    headline_patterns.append(normalized)
            for pattern in (editorial_dna.get("supporting_patterns") or [])[:4]:
                normalized = str(pattern).strip()
                if normalized and normalized.casefold() not in seen_summaries:
                    seen_summaries.add(normalized.casefold())
                    sample_summaries.append(normalized)
        dominant_story_arc = list(story_arc_counter.most_common(1)[0][0]) if story_arc_counter else []
        story_arc_options = [list(arc) for arc, _count in story_arc_counter.most_common(3)]
        preferred_slide_counts = [
            int(value)
            for value in cls._most_common_values(slide_count_candidates, limit=3)
            if str(value).strip().isdigit()
        ]
        return {
            "dominant_story_arc": dominant_story_arc,
            "story_arc_options": story_arc_options,
            "preferred_slide_count": preferred_slide_counts[0] if preferred_slide_counts else 0,
            "slide_count_options": preferred_slide_counts,
            "explanation_styles": explanation_styles,
            "closing_styles": closing_styles,
            "copy_densities": copy_densities,
            "headline_patterns": headline_patterns[:6],
            "sample_summaries": sample_summaries[:6],
            "disclaimer_support_ratio": round(disclaimer_support / max(len(records), 1), 4),
        }

    @classmethod
    def _synthesize_reference_system(cls, references: list[dict], templates: list[dict]) -> dict[str, object]:
        records = cls._template_analysis_records(references, templates)
        if not records:
            return {}

        layout_types = cls._most_common_values([str(item.get("layout_type") or "") for item in records], limit=4)
        visual_moods = cls._most_common_values([str(item.get("visual_mood") or "") for item in records], limit=4)
        design_styles = cls._most_common_values([str(item.get("design_style") or "") for item in records], limit=4)
        logo_anchors = cls._most_common_values([str(item.get("logo_anchor") or "") for item in records], limit=2)

        zone_counter: Counter[str] = Counter()
        for record in records:
            for zone in record.get("editable_zones") or []:
                if not isinstance(zone, dict):
                    continue
                role = str(zone.get("role") or zone.get("zone_id") or "").strip().lower()
                if role:
                    zone_counter[role] += 1

        background_types = cls._most_common_values(
            [
                str((item.get("background_style") or {}).get("type") or (item.get("background_style") or {}).get("dominant_mode") or "")
                for item in records
                if isinstance(item.get("background_style"), dict)
            ],
            limit=2,
        )
        background_primary_hexes = cls._most_common_values(
            [
                str((item.get("background_style") or {}).get("primary_hex") or "")
                for item in records
                if isinstance(item.get("background_style"), dict)
            ],
            limit=2,
        )
        background_style = {
            "type": background_types[0],
            "dominant_mode": background_types[0],
            "primary_hex": background_primary_hexes[0] if background_primary_hexes else None,
        } if background_types else {}

        gradient_preferences: list[dict[str, object]] = []
        seen_gradients: set[tuple[str, str, str, str]] = set()
        for record in records:
            for gradient in record.get("gradients") or []:
                if not isinstance(gradient, dict):
                    continue
                signature = (
                    str(gradient.get("type") or ""),
                    str(gradient.get("direction") or ""),
                    str(gradient.get("start_color") or ""),
                    str(gradient.get("end_color") or ""),
                )
                if not signature[2] or not signature[3] or signature in seen_gradients:
                    continue
                seen_gradients.add(signature)
                gradient_preferences.append(dict(gradient))
                if len(gradient_preferences) >= 3:
                    break
            if len(gradient_preferences) >= 3:
                break

        heading_styles = cls._most_common_values(
            [
                str((item.get("typography_dna") or {}).get("heading_style") or "")
                for item in records
                if isinstance(item.get("typography_dna"), dict)
            ],
            limit=3,
        )
        text_alignments = cls._most_common_values(
            [
                str((item.get("typography_dna") or {}).get("text_alignment") or "")
                for item in records
                if isinstance(item.get("typography_dna"), dict)
            ],
            limit=2,
        )
        dominant_cases = cls._most_common_values(
            [
                str((item.get("typography_dna") or {}).get("dominant_case") or "")
                for item in records
                if isinstance(item.get("typography_dna"), dict)
            ],
            limit=2,
        )
        emphasis_patterns = cls._most_common_values(
            [
                str((item.get("typography_dna") or {}).get("emphasis_pattern") or (item.get("visual_hierarchy") or {}).get("emphasis") or "")
                for item in records
                if isinstance(item.get("typography_dna"), dict) or isinstance(item.get("visual_hierarchy"), dict)
            ],
            limit=2,
        )

        focal_roles = cls._most_common_values(
            [
                str((item.get("visual_hierarchy") or {}).get("focal_role") or "")
                for item in records
                if isinstance(item.get("visual_hierarchy"), dict)
            ],
            limit=3,
        )
        densities = cls._most_common_values(
            [
                str((item.get("visual_hierarchy") or {}).get("density") or "")
                for item in records
                if isinstance(item.get("visual_hierarchy"), dict)
            ],
            limit=2,
        )
        whitespace_modes = cls._most_common_values(
            [
                str((item.get("visual_hierarchy") or {}).get("whitespace") or "")
                for item in records
                if isinstance(item.get("visual_hierarchy"), dict)
            ],
            limit=2,
        )

        storytelling_modes = cls._most_common_values(
            [
                str((item.get("content_structure") or {}).get("storytelling") or "")
                for item in records
                if isinstance(item.get("content_structure"), dict)
            ],
            limit=3,
        )
        cta_prominence = cls._most_common_values(
            [
                str((item.get("content_structure") or {}).get("cta_prominence") or "")
                for item in records
                if isinstance(item.get("content_structure"), dict)
            ],
            limit=2,
        )
        legal_footer_support = sum(
            1
            for item in records
            if isinstance(item.get("content_structure"), dict)
            and bool((item.get("content_structure") or {}).get("legal_footer_present"))
        )
        proof_modules = [
            int((item.get("content_structure") or {}).get("proof_modules") or 0)
            for item in records
            if isinstance(item.get("content_structure"), dict)
        ]

        image_styles = cls._most_common_values(
            [
                str((item.get("image_treatment") or {}).get("style") or "")
                for item in records
                if isinstance(item.get("image_treatment"), dict)
            ],
            limit=3,
        )
        image_crops = cls._most_common_values(
            [
                str((item.get("image_treatment") or {}).get("crop") or "")
                for item in records
                if isinstance(item.get("image_treatment"), dict)
            ],
            limit=3,
        )
        subject_focus_modes = cls._most_common_values(
            [
                str((item.get("image_treatment") or {}).get("subject_focus") or "")
                for item in records
                if isinstance(item.get("image_treatment"), dict)
            ],
            limit=3,
        )
        depth_styles = cls._most_common_values(
            [
                str((item.get("visual_craft_dna") or {}).get("depth_style") or "")
                for item in records
                if isinstance(item.get("visual_craft_dna"), dict)
            ],
            limit=3,
        )
        rendering_styles = cls._most_common_values(
            [
                str((item.get("visual_craft_dna") or {}).get("rendering_style") or "")
                for item in records
                if isinstance(item.get("visual_craft_dna"), dict)
            ],
            limit=3,
        )
        lighting_modes = cls._most_common_values(
            [
                str((item.get("visual_craft_dna") or {}).get("lighting") or "")
                for item in records
                if isinstance(item.get("visual_craft_dna"), dict)
            ],
            limit=3,
        )
        polish_levels = cls._most_common_values(
            [
                str((item.get("visual_craft_dna") or {}).get("polish_level") or "")
                for item in records
                if isinstance(item.get("visual_craft_dna"), dict)
            ],
            limit=3,
        )
        material_cues = cls._most_common_values(
            [
                str(keyword)
                for item in records
                if isinstance(item.get("visual_craft_dna"), dict)
                for keyword in ((item.get("visual_craft_dna") or {}).get("material_cues") or [])
            ],
            limit=8,
        )
        dimensionality_cues = cls._most_common_values(
            [
                str(keyword)
                for item in records
                if isinstance(item.get("visual_craft_dna"), dict)
                for keyword in ((item.get("visual_craft_dna") or {}).get("dimensionality_cues") or [])
            ],
            limit=8,
        )
        composition_balances = cls._most_common_values(
            [
                str((item.get("composition_logic") or {}).get("balance") or "")
                for item in records
                if isinstance(item.get("composition_logic"), dict)
            ],
            limit=3,
        )
        composition_framings = cls._most_common_values(
            [
                str((item.get("composition_logic") or {}).get("framing") or "")
                for item in records
                if isinstance(item.get("composition_logic"), dict)
            ],
            limit=3,
        )
        composition_layerings = cls._most_common_values(
            [
                str((item.get("composition_logic") or {}).get("layering") or "")
                for item in records
                if isinstance(item.get("composition_logic"), dict)
            ],
            limit=3,
        )
        scene_types = cls._most_common_values(
            [
                str((item.get("subject_semantics") or {}).get("scene_type") or "")
                for item in records
                if isinstance(item.get("subject_semantics"), dict)
            ],
            limit=3,
        )
        primary_subjects = cls._most_common_values(
            [
                str(keyword)
                for item in records
                if isinstance(item.get("subject_semantics"), dict)
                for keyword in ((item.get("subject_semantics") or {}).get("primary_subjects") or [])
            ],
            limit=8,
        )
        domain_cues = cls._most_common_values(
            [
                str(keyword)
                for item in records
                if isinstance(item.get("subject_semantics"), dict)
                for keyword in ((item.get("subject_semantics") or {}).get("domain_cues") or [])
            ],
            limit=8,
        )
        financial_objects = cls._most_common_values(
            [
                str(keyword)
                for item in records
                if isinstance(item.get("subject_semantics"), dict)
                for keyword in ((item.get("subject_semantics") or {}).get("financial_objects") or [])
            ],
            limit=8,
        )
        human_presence_modes = cls._most_common_values(
            [
                str((item.get("subject_semantics") or {}).get("human_presence") or "")
                for item in records
                if isinstance(item.get("subject_semantics"), dict)
            ],
            limit=3,
        )
        environments = cls._most_common_values(
            [
                str((item.get("subject_semantics") or {}).get("environment") or "")
                for item in records
                if isinstance(item.get("subject_semantics"), dict)
            ],
            limit=3,
        )
        abstraction_levels = cls._most_common_values(
            [
                str((item.get("subject_semantics") or {}).get("abstraction_level") or "")
                for item in records
                if isinstance(item.get("subject_semantics"), dict)
            ],
            limit=3,
        )
        tone_keywords = cls._most_common_values(
            [
                str(keyword)
                for item in records
                if isinstance(item.get("brand_cues"), dict)
                for keyword in ((item.get("brand_cues") or {}).get("tone_keywords") or [])
            ],
            limit=6,
        )
        trust_markers = cls._most_common_values(
            [
                str(keyword)
                for item in records
                if isinstance(item.get("brand_cues"), dict)
                for keyword in ((item.get("brand_cues") or {}).get("trust_markers") or [])
            ],
            limit=6,
        )
        editorial_patterns = cls._synthesize_editorial_patterns(records)
        format_specific_patterns: dict[str, dict[str, object]] = {}
        for family in ("static", "carousel", "infographic"):
            family_records = [
                item
                for item in records
                if str(((item.get("editorial_dna") or {}) if isinstance(item.get("editorial_dna"), dict) else {}).get("format_family") or "").strip().casefold() == family
            ]
            if family_records:
                format_specific_patterns[family] = cls._synthesize_editorial_patterns(family_records)

        brand_scores = [
            self_score
            for item in records
            if (self_score := cls._coerce_float(item.get("brand_score"))) > 0
        ]

        return {
            "sample_count": len(records),
            "layout_preferences": {
                "dominant": layout_types[0] if layout_types else None,
                "common": layout_types,
                "zone_role_frequency": dict(zone_counter),
                "preferred_zone_roles": [role for role, _count in zone_counter.most_common(8)],
            },
            "background_style": background_style,
            "gradient_preferences": gradient_preferences,
            "component_motifs": cls._synthesize_component_motifs(records),
            "typography_preferences": {
                "heading_styles": heading_styles,
                "text_alignments": text_alignments,
                "dominant_cases": dominant_cases,
                "emphasis_patterns": emphasis_patterns,
            },
            "visual_hierarchy": {
                "focal_roles": focal_roles,
                "density_preferences": densities,
                "whitespace_preferences": whitespace_modes,
            },
            "content_structure": {
                "storytelling_modes": storytelling_modes,
                "cta_prominence": cta_prominence[0] if cta_prominence else None,
                "legal_footer_support_ratio": round(legal_footer_support / max(len(records), 1), 4),
                "average_proof_modules": round(sum(proof_modules) / len(proof_modules), 2) if proof_modules else 0.0,
            },
            "image_treatment": {
                "styles": image_styles,
                "crops": image_crops,
                "subject_focus_modes": subject_focus_modes,
            },
            "visual_craft": {
                "depth_styles": depth_styles,
                "rendering_styles": rendering_styles,
                "lighting_modes": lighting_modes,
                "polish_levels": polish_levels,
                "material_cues": material_cues,
                "dimensionality_cues": dimensionality_cues,
            },
            "composition_logic": {
                "balances": composition_balances,
                "framings": composition_framings,
                "layerings": composition_layerings,
            },
            "subject_semantics": {
                "scene_types": scene_types,
                "primary_subjects": primary_subjects,
                "domain_cues": domain_cues,
                "financial_objects": financial_objects,
                "human_presence_modes": human_presence_modes,
                "environments": environments,
                "abstraction_levels": abstraction_levels,
            },
            "brand_cues": {
                "tone_keywords": tone_keywords,
                "trust_markers": trust_markers,
            },
            "editorial_patterns": {
                **editorial_patterns,
                "static": format_specific_patterns.get("static", {}),
                "carousel": format_specific_patterns.get("carousel", {}),
                "infographic": format_specific_patterns.get("infographic", {}),
            },
            "visual_moods": visual_moods,
            "design_styles": design_styles,
            "logo_anchor": logo_anchors[0] if logo_anchors else None,
            "brand_score_range": {
                "min": round(min(brand_scores), 2) if brand_scores else 0.0,
                "max": round(max(brand_scores), 2) if brand_scores else 0.0,
            },
        }

    async def _resolve_references_and_templates(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
        palette_summary: dict,
        typography_summary: dict,
    ) -> tuple[dict, list[DataConflict]]:
        templates = await self.templates.list_by_brand(brand_space_id, tenant_id)
        all_references = await self.visual_references.list_for_brand(tenant_id, brand_space_id)

        # Filter out references with inactive or deleted knowledge assets
        references = []
        for ref in all_references:
            asset = await self.assets.get(ref.knowledge_asset_id)
            if asset and asset.is_active and asset.lifecycle_state not in ("deleted", "failed"):
                references.append(ref)
        palette_hexes = {
            normalized
            for entry in palette_summary.get("entries", [])
            if isinstance(entry, dict)
            if (normalized := normalize_hex(entry.get("hex_code")))
        }
        role_map = palette_summary.get("role_map", {})
        if isinstance(role_map, dict):
            palette_hexes.update(
                normalized
                for value in role_map.values()
                if (normalized := normalize_hex(value))
            )
        palette_rgbs = [
            rgb
            for color in palette_hexes
            if (rgb := self._hex_to_rgb(color))
        ]
        type_names = {
            family.get("name")
            for family in typography_summary.get("font_families", [])
            if family.get("name")
        }
        conflicts: list[DataConflict] = []
        reference_payload = []
        template_payload = []
        for reference in references:
            reference_payload.append(
                {
                    "asset_id": str(reference.knowledge_asset_id),
                    "layout_structure": reference.layout_structure,
                    "style_characteristics": reference.style_characteristics,
                    "reusable_zones": reference.reusable_zones,
                    "brand_score": reference.brand_score,
                    "template_id": str(reference.template_id) if reference.template_id else None,
                }
            )
        for template in templates:
            analysis = template.analysis_json or {}
            template_payload.append(
                {
                    "template_id": str(template.id),
                    "source_asset_id": str(template.source_knowledge_asset_id) if template.source_knowledge_asset_id else None,
                    "origin_field_key": template.origin_field_key,
                    "analysis": analysis,
                    "matcher_features": template.matcher_features_json or {},
                }
            )
            template_colors = {
                normalized
                for item in analysis.get("color_usage", [])
                if isinstance(item, dict)
                if (normalized := normalize_hex(item.get("hex_code") or item.get("value")))
            }
            off_palette = sorted(
                color
                for color in template_colors
                if palette_hexes and not self._template_color_matches_palette(color, palette_hexes, palette_rgbs)
            )
            if off_palette:
                conflicts.append(
                    DataConflict(
                        tenant_id=tenant_id,
                        brand_space_id=brand_space_id,
                        conflict_type="template_palette_mismatch",
                        severity=ConflictSeverity.WARNING,
                        field_keys=["color_palette", template.origin_field_key or "template"],
                        knowledge_asset_ids=[
                            str(template.source_knowledge_asset_id)
                        ]
                        if template.source_knowledge_asset_id
                        else [],
                        details_json={
                            "summary": f"Template '{template.name}' uses colors outside the validated palette.",
                            "template_id": str(template.id),
                            "off_palette_colors": off_palette,
                        },
                    )
                )
            template_fonts = {
                font.get("name")
                for font in analysis.get("font_families", [])
                if isinstance(font, dict) and font.get("name")
            }
            font_mismatches = sorted(font for font in template_fonts if type_names and font not in type_names)
            if font_mismatches:
                conflicts.append(
                    DataConflict(
                        tenant_id=tenant_id,
                        brand_space_id=brand_space_id,
                        conflict_type="template_typography_mismatch",
                        severity=ConflictSeverity.INFO,
                        field_keys=["font_guide", template.origin_field_key or "template"],
                        knowledge_asset_ids=[
                            str(template.source_knowledge_asset_id)
                        ]
                        if template.source_knowledge_asset_id
                        else [],
                        details_json={
                            "summary": f"Template '{template.name}' uses fonts outside the validated typography guide.",
                            "template_id": str(template.id),
                            "fonts": font_mismatches,
                        },
                    )
                )
        synthesis = self._synthesize_reference_system(reference_payload, template_payload)
        return {"references": reference_payload, "templates": template_payload, "synthesis": synthesis}, conflicts

    async def _resolve_mood_boards(self, tenant_id: UUID, brand_space_id: UUID) -> list[dict]:
        boards = await self.mood_boards.list_for_brand(tenant_id, brand_space_id)
        return [
            {
                "asset_id": str(board.knowledge_asset_id),
                "style_summary": board.style_summary,
                "icon_assets": board.icon_assets,
                "micro_design_elements": board.micro_design_elements,
                "decorative_assets": board.decorative_assets,
                "enhancement_components": board.enhancement_components,
            }
            for board in boards
        ]

    async def _resolve_reusable_assets(self, tenant_id: UUID, brand_space_id: UUID) -> dict:
        assets = await self.reusable_assets.list_for_brand(tenant_id, brand_space_id)
        approved: list[dict] = []
        reference_only: list[dict] = []
        excluded: list[dict] = []
        icon_asset_ids: list[str] = []
        decorative_asset_ids: list[str] = []
        logo_variant_asset_ids: list[str] = []
        for asset in assets:
            if not asset.is_active:
                continue
            source_asset = await self.assets.get(asset.knowledge_asset_id)
            if not source_asset or not source_asset.is_active or source_asset.lifecycle_state in {"failed", "deleted"}:
                continue
            trust_level = self._trust_level_for_validation_state(source_asset.validation_state)
            normalized_metadata = asset.normalized_metadata_json or {}
            review_status = str(normalized_metadata.get("review_status") or "reference_only")
            review_class = str(normalized_metadata.get("review_class") or asset.asset_kind or "fragment")
            review_reason = str(normalized_metadata.get("review_reason") or "").strip()
            render_eligible = bool(normalized_metadata.get("render_eligible"))
            confidence = asset.confidence or 0.0
            payload = {
                "id": str(asset.id),
                "source_asset_id": str(asset.knowledge_asset_id),
                "asset_kind": asset.asset_kind,
                "review_class": review_class,
                "review_status": review_status,
                "review_reason": review_reason,
                "label": asset.label,
                "storage_path": asset.storage_path,
                "mime_type": asset.mime_type,
                "width": asset.width,
                "height": asset.height,
                "confidence": asset.confidence,
                "trust_level": trust_level,
                "source_metadata": asset.source_metadata_json,
                "normalized_metadata": normalized_metadata,
            }

            if asset.asset_kind != "logo_variant" and review_status == "approved" and (not render_eligible or confidence < 0.58):
                payload["review_status"] = "reference_only"
                payload["review_reason"] = review_reason or "Confidence below render threshold."
                payload["normalized_metadata"] = {
                    **normalized_metadata,
                    "review_status": "reference_only",
                    "review_reason": payload["review_reason"],
                    "render_eligible": False,
                }
                review_status = "reference_only"

            if review_status == "approved":
                approved.append(payload)
            elif review_status == "reference_only":
                reference_only.append(payload)
            else:
                excluded.append(payload)

            if review_status != "approved":
                continue

            if asset.asset_kind == "logo_variant":
                logo_variant_asset_ids.append(str(asset.id))
            elif asset.asset_kind in {"icon", "micro_design_element"}:
                icon_asset_ids.append(str(asset.id))
            elif asset.asset_kind in {"decorative_asset", "enhancement_component"}:
                decorative_asset_ids.append(str(asset.id))
        return {
            "all": approved,
            "approved": approved,
            "reference_only": reference_only,
            "excluded": excluded,
            "icon_asset_ids": icon_asset_ids,
            "decorative_asset_ids": decorative_asset_ids,
            "logo_variant_asset_ids": logo_variant_asset_ids,
        }

    async def _resolve_palette(
        self,
        tenant_id: UUID,
        brand_space_id: UUID,
    ) -> tuple[dict, list[str], list[DataConflict], set[str]]:
        entries = await self.palette_entries.list_for_brand(tenant_id, brand_space_id)
        warnings: list[str] = []
        conflicts: list[DataConflict] = []
        role_map_entries: list[dict[str, str]] = []
        duplicate_roles: dict[str, set[str]] = defaultdict(set)
        involved_asset_ids: set[str] = set()
        payload = []
        for entry in entries:
            payload.append(
                {
                    "asset_id": str(entry.knowledge_asset_id) if entry.knowledge_asset_id else None,
                    "role": entry.role,
                    "color_name": entry.color_name,
                    "hex_code": entry.hex_code,
                    "rgb_value": entry.rgb_value,
                    "confidence": entry.confidence,
                }
            )
            role_map_entries.append(
                {
                    "role": entry.role,
                    "color_name": entry.color_name or "",
                    "hex_code": entry.hex_code,
                }
            )
            duplicate_roles[entry.hex_code].add(entry.role)
            if entry.knowledge_asset_id:
                involved_asset_ids.add(str(entry.knowledge_asset_id))
        for hex_code, roles in duplicate_roles.items():
            if len(roles) < 2:
                continue
            warnings.append(f"Color {hex_code} appears in multiple palette roles: {', '.join(sorted(roles))}.")
            conflicts.append(
                DataConflict(
                    tenant_id=tenant_id,
                    brand_space_id=brand_space_id,
                    conflict_type="palette_role_conflict",
                    severity=ConflictSeverity.WARNING,
                    field_keys=["color_palette"],
                    knowledge_asset_ids=sorted(involved_asset_ids),
                    details_json={
                        "summary": f"Color {hex_code} is assigned to multiple roles.",
                        "hex_code": hex_code,
                        "roles": sorted(roles),
                    },
                )
            )
        role_map = self._normalized_palette_role_map(role_map_entries)
        return {"entries": payload, "role_map": role_map}, warnings, conflicts, involved_asset_ids

    async def _resolve_typography(self, tenant_id: UUID, brand_space_id: UUID) -> dict:
        guides = await self.typography_guides.list_for_brand(tenant_id, brand_space_id)
        font_families = []
        hierarchy = {}
        usage_patterns = {}
        uploaded_font_assets: list[dict] = []
        for guide in guides:
            font_families.extend(guide.font_families)
            hierarchy.update(guide.style_hierarchy)
            usage_patterns.update(guide.usage_patterns)
            source_asset = await self.assets.get(guide.knowledge_asset_id)
            if not source_asset:
                continue
            suffix = source_asset.original_filename.rsplit(".", 1)[-1].lower() if "." in source_asset.original_filename else ""
            if suffix not in {"ttf", "otf"} and source_asset.mime_type not in {
                "font/ttf",
                "font/otf",
                "application/x-font-ttf",
                "application/x-font-otf",
                "application/font-sfnt",
            }:
                continue
            family = next(
                (
                    family
                    for family in guide.font_families
                    if isinstance(family, dict) and family.get("name")
                ),
                {},
            )
            uploaded_font_assets.append(
                {
                    "asset_id": str(source_asset.id),
                    "storage_path": source_asset.storage_path,
                    "mime_type": source_asset.mime_type,
                    "filename": source_asset.original_filename,
                    "family_name": family.get("name"),
                    "style_name": family.get("style"),
                    "confidence": family.get("confidence", guide.confidence),
                    "trust_level": self._trust_level_for_validation_state(source_asset.validation_state),
                }
            )
        return {
            "font_families": self._dedupe_dict_list(font_families, key="name"),
            "style_hierarchy": hierarchy,
            "usage_patterns": usage_patterns,
            "uploaded_font_assets": uploaded_font_assets,
        }

    async def _resolve_word_banks(self, tenant_id: UUID, brand_space_id: UUID) -> dict:
        uploads = await self.word_bank_uploads.list_for_brand(tenant_id, brand_space_id)
        upload_ids = [upload.id for upload in uploads]
        positive = await self.positive_words.list_for_brand(tenant_id, brand_space_id) if upload_ids else []
        negative = await self.negative_words.list_for_brand(tenant_id, brand_space_id) if upload_ids else []
        replaceable = await self.replaceable_words.list_for_brand(tenant_id, brand_space_id) if upload_ids else []
        replace_map = {
            word.term: word.replacements
            for word in replaceable
            if word.replacements
        }
        return {
            "positive_words": self._dedupe_list([word.term for word in positive]),
            "negative_words": self._dedupe_list([word.term for word in negative]),
            "replaceable_words": self._dedupe_list([word.term for word in replaceable]),
            "replaceable_map": replace_map,
        }

    async def _resolve_legal_disclaimers(self, tenant_id: UUID, brand_space_id: UUID) -> list[dict]:
        """Resolve legal disclaimers for the brand"""
        from app.repositories.brand_assets import BrandLegalAssetRepository

        legal_repo = BrandLegalAssetRepository(self.session)
        legal_assets = await legal_repo.get_by_brand_space(brand_space_id)

        if not legal_assets:
            return []

        disclaimers = []
        for asset in legal_assets:
            disclaimers.append({
                "id": str(asset.id),
                "asset_type": asset.asset_type,
                "text_template": asset.text_template,
                "applies_to_formats": asset.applies_to_formats or [],
                "position": asset.position,
                "font_size": asset.font_size,
                "text_color": asset.text_color,
                "confidence": asset.confidence,
                "source_asset_id": str(asset.source_asset_id) if asset.source_asset_id else None,
            })

        return disclaimers

    async def _resolve_cta_templates(self, tenant_id: UUID, brand_space_id: UUID) -> list[dict]:
        """Resolve CTA templates for the brand"""
        from app.repositories.brand_assets import BrandCTATemplateRepository

        cta_repo = BrandCTATemplateRepository(self.session)
        cta_templates = await cta_repo.get_by_brand_space(brand_space_id)

        if not cta_templates:
            return []

        templates = []
        for template in cta_templates:
            templates.append({
                "id": str(template.id),
                "template_name": template.template_name,
                "headline_template": template.headline_template,
                "body_template": template.body_template,
                "button_text": template.button_text,
                "button_color": template.button_color,
                "button_text_color": template.button_text_color,
                "button_style": template.button_style,
                "icon_hint": template.icon_hint,
                "visual_theme": template.visual_theme,
                "is_default": template.is_default,
            })

        return templates

    async def _upsert_validation_result_for_asset(
        self,
        asset: KnowledgeAsset,
        palette_asset_ids: set[str],
        conflict_records: list[DataConflict],
    ) -> AssetValidationResult:
        conflict_hits = [
            conflict
            for conflict in conflict_records
            if str(asset.id) in set(conflict.knowledge_asset_ids)
        ]
        warnings = list(asset.validation_summary_json.get("warnings", []))
        warnings.extend(conflict.details_json.get("summary", "") for conflict in conflict_hits if conflict.details_json.get("summary"))
        warnings = [warning for warning in warnings if warning]
        validation_state = asset.validation_state or AssetValidationState.PENDING
        exclusion_reason = None
        if asset.lifecycle_state == "failed" or not asset.is_active:
            validation_state = AssetValidationState.EXCLUDED
            exclusion_reason = asset.processing_error or "Asset is inactive and excluded from generation."
        elif conflict_hits:
            validation_state = AssetValidationState.WARNING
        elif asset.field_key == "color_palette" and str(asset.id) in palette_asset_ids:
            validation_state = AssetValidationState.CLEAN
        elif asset.normalized_data_json and validation_state != AssetValidationState.WARNING:
            validation_state = AssetValidationState.CLEAN

        existing = next(
            (
                item
                for item in await self.validation_results.list_by_asset_ids([asset.id])
                if item.knowledge_asset_id == asset.id
            ),
            None,
        )
        payload = {
            "tenant_id": asset.tenant_id,
            "brand_space_id": asset.brand_space_id,
            "knowledge_asset_id": asset.id,
            "field_key": asset.field_key or asset.channel,
            "validation_state": validation_state,
            "warnings": list(dict.fromkeys(warnings)),
            "exclusion_reason": exclusion_reason,
            "resolved_payload": asset.normalized_data_json or asset.structured_data_json,
            "confidence": asset.classification_confidence,
        }
        if existing:
            existing.validation_state = payload["validation_state"]
            existing.warnings = payload["warnings"]
            existing.exclusion_reason = payload["exclusion_reason"]
            existing.resolved_payload = payload["resolved_payload"]
            existing.confidence = payload["confidence"]
            return existing
        created = AssetValidationResult(**payload)
        self.session.add(created)
        await self.session.flush()
        return created

    @staticmethod
    def _dedupe_list(values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            clean = " ".join(str(value).split()).strip()
            if not clean:
                continue
            key = clean.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(clean)
        return deduped

    @classmethod
    def _ranked_research_highlights(
        cls,
        *,
        summaries: list[str],
        research_evidence: list[dict],
        proof_cues: list[str],
        trust_signals: list[str],
        comparison_points: list[str],
        objections: list[str],
        desired_outcomes: list[str],
        limit: int = 6,
    ) -> list[str]:
        lanes: dict[str, list[str]] = {
            "proof_cues": [],
            "trust_signals": [],
            "comparison_points": [],
            "objections": [],
            "desired_outcomes": [],
            "summaries": cls._dedupe_list(summaries),
            "general": [],
        }
        for item in research_evidence:
            field = str(item.get("field") or "").strip().casefold()
            value = str(item.get("value") or "").strip()
            if not value:
                continue
            lane_name = field if field in lanes else "general"
            lanes[lane_name].append(value)
        for field, values in (
            ("proof_cues", proof_cues),
            ("trust_signals", trust_signals),
            ("comparison_points", comparison_points),
            ("objections", objections),
            ("desired_outcomes", desired_outcomes),
        ):
            lanes[field].extend(values or [])
        for lane_name, values in tuple(lanes.items()):
            lanes[lane_name] = cls._dedupe_list(values)

        merged: list[str] = []
        seen: set[str] = set()
        positions = {lane_name: 0 for lane_name in lanes}

        def _append_from_lane(lane_name: str) -> bool:
            lane = lanes.get(lane_name, [])
            index = positions[lane_name]
            while index < len(lane):
                candidate = lane[index]
                index += 1
                key = candidate.casefold()
                if key in seen:
                    continue
                positions[lane_name] = index
                seen.add(key)
                merged.append(candidate)
                return True
            positions[lane_name] = index
            return False

        first_pass_order = (
            "proof_cues",
            "summaries",
            "trust_signals",
            "summaries",
            "comparison_points",
            "objections",
            "desired_outcomes",
            "general",
        )
        fill_order = (
            "proof_cues",
            "trust_signals",
            "comparison_points",
            "objections",
            "desired_outcomes",
            "summaries",
            "general",
        )

        for lane_name in first_pass_order:
            if len(merged) >= limit:
                break
            _append_from_lane(lane_name)

        while len(merged) < limit:
            progressed = False
            for lane_name in fill_order:
                if len(merged) >= limit:
                    break
                progressed = _append_from_lane(lane_name) or progressed
            if not progressed:
                break

        return merged[:limit]

    @staticmethod
    def _dedupe_dict_list(values: list[dict], key: str) -> list[dict]:
        seen: set[str] = set()
        deduped: list[dict] = []
        for value in values:
            identifier = str(value.get(key, "")).strip()
            if not identifier:
                continue
            normalized = identifier.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(value)
        return deduped

    @staticmethod
    def _coerce_float(value: object, fallback: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _coerce_int(value: object, fallback: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    @classmethod
    def _research_evidence_rank(cls, entry: dict[str, object]) -> float:
        item_confidence = cls._coerce_float(entry.get("confidence"))
        evidence_confidence = cls._coerce_float(entry.get("evidence_confidence"))
        source_agreement_score = cls._coerce_float(entry.get("source_agreement_score"))
        analysis_quality_score = min(cls._coerce_float(entry.get("analysis_quality_score")) / 10.0, 1.0)
        signal_density = min(cls._coerce_float(entry.get("research_signal_count")) / 8.0, 1.0)
        return round(
            (source_agreement_score * 0.32)
            + (analysis_quality_score * 0.24)
            + (item_confidence * 0.22)
            + (evidence_confidence * 0.14)
            + (signal_density * 0.08),
            6,
        )

    @staticmethod
    def _trust_level_for_validation_state(validation_state: str | None) -> str:
        normalized = str(validation_state or AssetValidationState.PENDING).lower()
        if normalized == AssetValidationState.CLEAN:
            return "trusted"
        if normalized == AssetValidationState.WARNING:
            return "usable_with_warning"
        if normalized == AssetValidationState.EXCLUDED:
            return "excluded"
        return "reference_only"
