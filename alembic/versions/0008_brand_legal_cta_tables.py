"""Add brand_legal_assets and brand_cta_templates tables

Revision ID: 0008_brand_legal_cta_tables
Revises: 0007_audience_quality_meta
Create Date: 2026-05-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0008_brand_legal_cta_tables"
down_revision = "0007_audience_quality_meta"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def _has_unique_constraint(inspector, table_name: str, constraint_name: str) -> bool:
    return constraint_name in {
        constraint["name"] for constraint in inspector.get_unique_constraints(table_name) if constraint.get("name")
    }


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Create brand_legal_assets table
    if not _has_table(inspector, "brand_legal_assets"):
        op.create_table(
            "brand_legal_assets",
            sa.Column("id", postgresql.UUID(), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(), nullable=False),
            sa.Column("brand_space_id", postgresql.UUID(), nullable=False),
            sa.Column("asset_type", sa.String(50), nullable=False),
            sa.Column("text_template", sa.Text(), nullable=False),
            sa.Column(
                "applies_to_formats",
                postgresql.ARRAY(sa.Text()),
                server_default='{"carousel","static","infographic"}',
                nullable=False,
            ),
            sa.Column("position", sa.String(20), nullable=False, server_default="footer"),
            sa.Column("font_size", sa.Integer(), nullable=False, server_default="8"),
            sa.Column("text_color", sa.String(7), nullable=False, server_default="#666666"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
            sa.Column("source_asset_id", postgresql.UUID(), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["brand_space_id"], ["brand_spaces.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["source_asset_id"], ["knowledge_assets.id"], ondelete="SET NULL"),
        )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "brand_legal_assets", "ix_brand_legal_assets_brand_space_id"):
        op.create_index("ix_brand_legal_assets_brand_space_id", "brand_legal_assets", ["brand_space_id"])
    if not _has_index(inspector, "brand_legal_assets", "ix_brand_legal_assets_asset_type"):
        op.create_index("ix_brand_legal_assets_asset_type", "brand_legal_assets", ["asset_type"])

    # Create brand_cta_templates table
    if not _has_table(inspector, "brand_cta_templates"):
        op.create_table(
            "brand_cta_templates",
            sa.Column("id", postgresql.UUID(), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(), nullable=False),
            sa.Column("brand_space_id", postgresql.UUID(), nullable=False),
            sa.Column("template_name", sa.String(100), nullable=False),
            sa.Column("headline_template", sa.String(300), nullable=True),
            sa.Column("body_template", sa.String(600), nullable=True),
            sa.Column("button_text", sa.String(100), nullable=False),
            sa.Column("button_color", sa.String(7), nullable=False),
            sa.Column("button_text_color", sa.String(7), nullable=False, server_default="#FFFFFF"),
            sa.Column("button_style", sa.String(20), nullable=False, server_default="rounded"),
            sa.Column("icon_hint", sa.String(50), nullable=True),
            sa.Column("visual_theme", sa.String(50), nullable=True),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["brand_space_id"], ["brand_spaces.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("brand_space_id", "template_name", name="uq_brand_cta_template_name"),
        )

    inspector = sa.inspect(bind)
    if not _has_unique_constraint(inspector, "brand_cta_templates", "uq_brand_cta_template_name"):
        op.create_unique_constraint(
            "uq_brand_cta_template_name",
            "brand_cta_templates",
            ["brand_space_id", "template_name"],
        )
    if not _has_index(inspector, "brand_cta_templates", "ix_brand_cta_templates_brand_space_id"):
        op.create_index("ix_brand_cta_templates_brand_space_id", "brand_cta_templates", ["brand_space_id"])
    if not _has_index(inspector, "brand_cta_templates", "ix_brand_cta_templates_template_name"):
        op.create_index("ix_brand_cta_templates_template_name", "brand_cta_templates", ["template_name"])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "brand_cta_templates"):
        if _has_index(inspector, "brand_cta_templates", "ix_brand_cta_templates_template_name"):
            op.drop_index("ix_brand_cta_templates_template_name", table_name="brand_cta_templates")
        if _has_index(inspector, "brand_cta_templates", "ix_brand_cta_templates_brand_space_id"):
            op.drop_index("ix_brand_cta_templates_brand_space_id", table_name="brand_cta_templates")
        if _has_unique_constraint(inspector, "brand_cta_templates", "uq_brand_cta_template_name"):
            op.drop_constraint("uq_brand_cta_template_name", "brand_cta_templates", type_="unique")
        op.drop_table("brand_cta_templates")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "brand_legal_assets"):
        if _has_index(inspector, "brand_legal_assets", "ix_brand_legal_assets_asset_type"):
            op.drop_index("ix_brand_legal_assets_asset_type", table_name="brand_legal_assets")
        if _has_index(inspector, "brand_legal_assets", "ix_brand_legal_assets_brand_space_id"):
            op.drop_index("ix_brand_legal_assets_brand_space_id", table_name="brand_legal_assets")
        op.drop_table("brand_legal_assets")
