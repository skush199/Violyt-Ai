from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import (
    BrandScopedMixin,
    SoftDeleteMixin,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class KnowledgeAsset(
    UUIDPrimaryKeyMixin,
    TenantScopedMixin,
    BrandScopedMixin,
    TimestampMixin,
    SoftDeleteMixin,
    Base,
):
    __tablename__ = "knowledge_assets"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(50), nullable=False, default="uploaded", index=True)
    channel: Mapped[str] = mapped_column(String(100), nullable=False, default="brand", index=True)
    field_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    asset_category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    source_intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    page_count: Mapped[int] = mapped_column(default=0, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    structured_data_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    normalized_data_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    validation_state: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    validation_summary_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_indexed_at: Mapped[str | None] = mapped_column(String(50), nullable=True)


class Template(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "templates"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, default="hybrid")
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_knowledge_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("knowledge_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    origin_field_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    analysis_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    matcher_features_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)


class TemplateMetadata(UUIDPrimaryKeyMixin, TenantScopedMixin, BrandScopedMixin, TimestampMixin, Base):
    __tablename__ = "template_metadata"

    template_id: Mapped[UUID] = mapped_column(ForeignKey("templates.id", ondelete="CASCADE"), index=True)
    zone_map: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    sizing_rules: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    platform_rules: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    editable_fields: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    export_rules: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
