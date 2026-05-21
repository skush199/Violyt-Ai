from __future__ import annotations

from uuid import UUID

from sqlalchemy import ARRAY, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import BrandScopedMixin, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class BrandLogoAsset(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "brand_logo_assets"

    knowledge_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    variant_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    compatibility: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    usage_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    source_metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class BrandLogoMetadata(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "brand_logo_metadata"

    brand_logo_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("brand_logo_assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    logo_colors: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    size_rules: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    font_details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    tagline: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    inference_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class AudienceInsightAsset(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "audience_insight_assets"

    knowledge_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class AudienceInsightStructuredData(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "audience_insight_structured_data"

    audience_insight_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("audience_insight_assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    audience_segments: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    behaviors: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    motivations: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    pain_points: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    objections: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    desired_outcomes: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    preferences: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    trust_signals: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    proof_cues: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    comparison_points: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    demographics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    psychographics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    research_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    research_evidence: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    research_signal_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    analysis_quality: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    evidence_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_agreement_score: Mapped[float | None] = mapped_column(Float, nullable=True)


class VisualReferenceAsset(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "visual_reference_assets"

    knowledge_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    template_id: Mapped[UUID | None] = mapped_column(ForeignKey("templates.id", ondelete="SET NULL"), nullable=True, index=True)
    layout_structure: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    style_characteristics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    reusable_zones: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    brand_score: Mapped[float | None] = mapped_column(Float, nullable=True)


class MoodBoardAsset(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "mood_board_assets"

    knowledge_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    style_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon_assets: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    micro_design_elements: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    decorative_assets: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    enhancement_components: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)


class ReusableBrandAsset(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "reusable_brand_assets"

    knowledge_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    normalized_metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class ColorPaletteEntry(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "color_palette_entries"

    knowledge_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("knowledge_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    color_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    hex_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    rgb_value: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class TypographyGuide(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "typography_guides"

    knowledge_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    font_families: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    style_hierarchy: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    usage_patterns: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class WordBankUpload(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "word_bank_uploads"

    knowledge_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    bank_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    normalized_terms: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    phrase_map: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class PositiveWord(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "positive_words"

    upload_id: Mapped[UUID] = mapped_column(ForeignKey("word_bank_uploads.id", ondelete="CASCADE"), nullable=False, index=True)
    term: Mapped[str] = mapped_column(String(255), nullable=False, index=True)


class NegativeWord(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "negative_words"

    upload_id: Mapped[UUID] = mapped_column(ForeignKey("word_bank_uploads.id", ondelete="CASCADE"), nullable=False, index=True)
    term: Mapped[str] = mapped_column(String(255), nullable=False, index=True)


class ReplaceableWord(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "replaceable_words"

    upload_id: Mapped[UUID] = mapped_column(ForeignKey("word_bank_uploads.id", ondelete="CASCADE"), nullable=False, index=True)
    term: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    replacements: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)


class AssetProcessingStatus(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "asset_processing_status"

    knowledge_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    field_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    lifecycle_state: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    processor_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    progress_current: Mapped[int] = mapped_column(default=0, nullable=False)
    progress_total: Mapped[int] = mapped_column(default=0, nullable=False)
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    raw_status_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class AssetValidationResult(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "asset_validation_results"

    knowledge_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("knowledge_assets.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    field_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    validation_state: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class AssetCategoryRouting(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "asset_category_routing"

    knowledge_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    requested_field_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    requested_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    routed_category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    classifier: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    routing_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class DataConflict(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "data_conflicts"

    conflict_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    field_keys: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    knowledge_asset_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    details_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    resolved_payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class ResolvedBrandContextSnapshot(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "resolved_brand_context_snapshots"

    snapshot_kind: Mapped[str] = mapped_column(String(40), nullable=False, default="validated", index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    conflict_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    excluded_asset_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    context_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class BrandLegalAsset(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    """Legal disclaimers, copyright notices, terms extracted from brand samples"""
    __tablename__ = "brand_legal_assets"

    asset_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 'disclaimer', 'copyright', 'terms'
    text_template: Mapped[str] = mapped_column(Text, nullable=False)
    applies_to_formats: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)  # ['carousel', 'static', 'infographic']
    position: Mapped[str] = mapped_column(String(20), nullable=False, default="footer")  # 'footer', 'header'
    font_size: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    text_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#666666")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("knowledge_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class BrandCTATemplate(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    """Brand-specific CTA templates for final carousel slides"""
    __tablename__ = "brand_cta_templates"

    template_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    headline_template: Mapped[str | None] = mapped_column(String(300), nullable=True)
    body_template: Mapped[str | None] = mapped_column(String(600), nullable=True)
    button_text: Mapped[str] = mapped_column(String(100), nullable=False)
    button_color: Mapped[str] = mapped_column(String(7), nullable=False)
    button_text_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#FFFFFF")
    button_style: Mapped[str] = mapped_column(String(20), nullable=False, default="rounded")  # 'rounded', 'sharp', 'pill'
    icon_hint: Mapped[str | None] = mapped_column(String(50), nullable=True)
    visual_theme: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
