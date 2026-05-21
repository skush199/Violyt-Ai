"""Add categorized brand asset architecture."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003_brand_asset_architecture"
down_revision = "0002_user_metadata_json"
branch_labels = None
depends_on = None


UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    knowledge_columns = [
        ("field_key", sa.String(length=100), True, None),
        ("asset_category", sa.String(length=100), True, None),
        ("source_intent", sa.String(length=100), True, None),
        ("classification_confidence", sa.Float(), True, None),
        ("structured_data_json", JSONB, False, sa.text("'{}'::jsonb")),
        ("normalized_data_json", JSONB, False, sa.text("'{}'::jsonb")),
        ("validation_state", sa.String(length=50), False, sa.text("'pending'")),
        ("validation_summary_json", JSONB, False, sa.text("'{}'::jsonb")),
        ("is_active", sa.Boolean(), False, sa.text("true")),
    ]
    for column_name, column_type, nullable, server_default in knowledge_columns:
        if not _has_column(inspector, "knowledge_assets", column_name):
            op.add_column(
                "knowledge_assets",
                sa.Column(column_name, column_type, nullable=nullable, server_default=server_default),
            )

    template_columns = [
        ("source_knowledge_asset_id", UUID, True, None),
        ("origin_field_key", sa.String(length=100), True, None),
        ("matcher_features_json", JSONB, False, sa.text("'{}'::jsonb")),
    ]
    for column_name, column_type, nullable, server_default in template_columns:
        if not _has_column(inspector, "templates", column_name):
            op.add_column(
                "templates",
                sa.Column(column_name, column_type, nullable=nullable, server_default=server_default),
            )

    if _has_column(inspector, "templates", "source_knowledge_asset_id"):
        foreign_keys = {fk["constrained_columns"][0] for fk in inspector.get_foreign_keys("templates") if fk["constrained_columns"]}
        if "source_knowledge_asset_id" not in foreign_keys:
            op.create_foreign_key(
                "fk_templates_source_knowledge_asset_id",
                "templates",
                "knowledge_assets",
                ["source_knowledge_asset_id"],
                ["id"],
                ondelete="SET NULL",
            )

    tables = inspector.get_table_names()
    if "brand_logo_assets" not in tables:
        op.create_table(
            "brand_logo_assets",
            sa.Column("knowledge_asset_id", UUID, sa.ForeignKey("knowledge_assets.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("variant_label", sa.String(length=120), nullable=True),
            sa.Column("compatibility", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("usage_metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("source_metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("id", UUID, primary_key=True, nullable=False),
            sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_space_id", UUID, sa.ForeignKey("brand_spaces.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "brand_logo_metadata" not in tables:
        op.create_table(
            "brand_logo_metadata",
            sa.Column("brand_logo_asset_id", UUID, sa.ForeignKey("brand_logo_assets.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("logo_colors", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("size_rules", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("font_details", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("tagline", sa.Text(), nullable=True),
            sa.Column("extracted_text", sa.Text(), nullable=True),
            sa.Column("inference_metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("id", UUID, primary_key=True, nullable=False),
            sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_space_id", UUID, sa.ForeignKey("brand_spaces.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "audience_insight_assets" not in tables:
        op.create_table(
            "audience_insight_assets",
            sa.Column("knowledge_asset_id", UUID, sa.ForeignKey("knowledge_assets.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("source_metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("id", UUID, primary_key=True, nullable=False),
            sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_space_id", UUID, sa.ForeignKey("brand_spaces.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "audience_insight_structured_data" not in tables:
        op.create_table(
            "audience_insight_structured_data",
            sa.Column("audience_insight_asset_id", UUID, sa.ForeignKey("audience_insight_assets.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("audience_segments", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("behaviors", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("motivations", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("pain_points", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("preferences", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("demographics", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("psychographics", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("research_summary", sa.Text(), nullable=True),
            sa.Column("id", UUID, primary_key=True, nullable=False),
            sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_space_id", UUID, sa.ForeignKey("brand_spaces.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "visual_reference_assets" not in tables:
        op.create_table(
            "visual_reference_assets",
            sa.Column("knowledge_asset_id", UUID, sa.ForeignKey("knowledge_assets.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("template_id", UUID, sa.ForeignKey("templates.id", ondelete="SET NULL"), nullable=True),
            sa.Column("layout_structure", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("style_characteristics", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("reusable_zones", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("brand_score", sa.Float(), nullable=True),
            sa.Column("id", UUID, primary_key=True, nullable=False),
            sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_space_id", UUID, sa.ForeignKey("brand_spaces.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "mood_board_assets" not in tables:
        op.create_table(
            "mood_board_assets",
            sa.Column("knowledge_asset_id", UUID, sa.ForeignKey("knowledge_assets.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("style_summary", sa.Text(), nullable=True),
            sa.Column("icon_assets", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("micro_design_elements", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("decorative_assets", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("enhancement_components", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("id", UUID, primary_key=True, nullable=False),
            sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_space_id", UUID, sa.ForeignKey("brand_spaces.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "color_palette_entries" not in tables:
        op.create_table(
            "color_palette_entries",
            sa.Column("knowledge_asset_id", UUID, sa.ForeignKey("knowledge_assets.id", ondelete="SET NULL"), nullable=True),
            sa.Column("role", sa.String(length=40), nullable=False),
            sa.Column("color_name", sa.String(length=120), nullable=True),
            sa.Column("hex_code", sa.String(length=32), nullable=False),
            sa.Column("rgb_value", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("source_metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("id", UUID, primary_key=True, nullable=False),
            sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_space_id", UUID, sa.ForeignKey("brand_spaces.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "typography_guides" not in tables:
        op.create_table(
            "typography_guides",
            sa.Column("knowledge_asset_id", UUID, sa.ForeignKey("knowledge_assets.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("font_families", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("style_hierarchy", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("usage_patterns", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("id", UUID, primary_key=True, nullable=False),
            sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_space_id", UUID, sa.ForeignKey("brand_spaces.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "word_bank_uploads" not in tables:
        op.create_table(
            "word_bank_uploads",
            sa.Column("knowledge_asset_id", UUID, sa.ForeignKey("knowledge_assets.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("bank_type", sa.String(length=40), nullable=False),
            sa.Column("normalized_terms", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("phrase_map", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("id", UUID, primary_key=True, nullable=False),
            sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_space_id", UUID, sa.ForeignKey("brand_spaces.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    for table_name in ("positive_words", "negative_words", "replaceable_words"):
        if table_name in tables:
            continue
        columns = [
            sa.Column("upload_id", UUID, sa.ForeignKey("word_bank_uploads.id", ondelete="CASCADE"), nullable=False),
            sa.Column("term", sa.String(length=255), nullable=False),
        ]
        if table_name == "replaceable_words":
            columns.append(sa.Column("replacements", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))
        columns.extend(
            [
                sa.Column("id", UUID, primary_key=True, nullable=False),
                sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
                sa.Column("brand_space_id", UUID, sa.ForeignKey("brand_spaces.id", ondelete="CASCADE"), nullable=True),
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            ]
        )
        op.create_table(table_name, *columns)

    if "asset_processing_status" not in tables:
        op.create_table(
            "asset_processing_status",
            sa.Column("knowledge_asset_id", UUID, sa.ForeignKey("knowledge_assets.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("field_key", sa.String(length=100), nullable=False),
            sa.Column("lifecycle_state", sa.String(length=50), nullable=False),
            sa.Column("processor_name", sa.String(length=120), nullable=True),
            sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status_message", sa.Text(), nullable=True),
            sa.Column("last_job_id", UUID, sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("raw_status_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("id", UUID, primary_key=True, nullable=False),
            sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_space_id", UUID, sa.ForeignKey("brand_spaces.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "asset_validation_results" not in tables:
        op.create_table(
            "asset_validation_results",
            sa.Column("knowledge_asset_id", UUID, sa.ForeignKey("knowledge_assets.id", ondelete="CASCADE"), nullable=True),
            sa.Column("field_key", sa.String(length=100), nullable=False),
            sa.Column("validation_state", sa.String(length=50), nullable=False),
            sa.Column("warnings", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("exclusion_reason", sa.Text(), nullable=True),
            sa.Column("resolved_payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("id", UUID, primary_key=True, nullable=False),
            sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_space_id", UUID, sa.ForeignKey("brand_spaces.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "asset_category_routing" not in tables:
        op.create_table(
            "asset_category_routing",
            sa.Column("knowledge_asset_id", UUID, sa.ForeignKey("knowledge_assets.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("requested_field_key", sa.String(length=100), nullable=False),
            sa.Column("requested_category", sa.String(length=100), nullable=True),
            sa.Column("routed_category", sa.String(length=100), nullable=False),
            sa.Column("classifier", sa.String(length=120), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("routing_reason", sa.Text(), nullable=True),
            sa.Column("decision_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("id", UUID, primary_key=True, nullable=False),
            sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_space_id", UUID, sa.ForeignKey("brand_spaces.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "data_conflicts" not in tables:
        op.create_table(
            "data_conflicts",
            sa.Column("conflict_type", sa.String(length=100), nullable=False),
            sa.Column("severity", sa.String(length=40), nullable=False),
            sa.Column("field_keys", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("knowledge_asset_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("details_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("resolution_status", sa.String(length=40), nullable=False, server_default="open"),
            sa.Column("resolved_payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("id", UUID, primary_key=True, nullable=False),
            sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_space_id", UUID, sa.ForeignKey("brand_spaces.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "resolved_brand_context_snapshots" not in tables:
        op.create_table(
            "resolved_brand_context_snapshots",
            sa.Column("snapshot_kind", sa.String(length=40), nullable=False, server_default="validated"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
            sa.Column("warnings", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("conflict_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("excluded_asset_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("context_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("id", UUID, primary_key=True, nullable=False),
            sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_space_id", UUID, sa.ForeignKey("brand_spaces.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name in [
        "resolved_brand_context_snapshots",
        "data_conflicts",
        "asset_category_routing",
        "asset_validation_results",
        "asset_processing_status",
        "replaceable_words",
        "negative_words",
        "positive_words",
        "word_bank_uploads",
        "typography_guides",
        "color_palette_entries",
        "mood_board_assets",
        "visual_reference_assets",
        "audience_insight_structured_data",
        "audience_insight_assets",
        "brand_logo_metadata",
        "brand_logo_assets",
    ]:
        if _has_table(inspector, table_name):
            op.drop_table(table_name)

    if _has_column(inspector, "templates", "source_knowledge_asset_id"):
        for foreign_key in inspector.get_foreign_keys("templates"):
            if foreign_key["constrained_columns"] == ["source_knowledge_asset_id"]:
                op.drop_constraint(foreign_key["name"], "templates", type_="foreignkey")
                break
        for column_name in ("matcher_features_json", "origin_field_key", "source_knowledge_asset_id"):
            if _has_column(inspector, "templates", column_name):
                op.drop_column("templates", column_name)

    for column_name in (
        "is_active",
        "validation_summary_json",
        "validation_state",
        "normalized_data_json",
        "structured_data_json",
        "classification_confidence",
        "source_intent",
        "asset_category",
        "field_key",
    ):
        if _has_column(inspector, "knowledge_assets", column_name):
            op.drop_column("knowledge_assets", column_name)
