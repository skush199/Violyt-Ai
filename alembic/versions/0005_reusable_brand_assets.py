"""Add reusable extracted brand assets."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0005_reusable_brand_assets"
down_revision = "0004_job_resilience"
branch_labels = None
depends_on = None


UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "reusable_brand_assets"):
        op.create_table(
            "reusable_brand_assets",
            sa.Column("knowledge_asset_id", UUID, sa.ForeignKey("knowledge_assets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("asset_kind", sa.String(length=80), nullable=False),
            sa.Column("label", sa.String(length=200), nullable=True),
            sa.Column("mime_type", sa.String(length=120), nullable=False),
            sa.Column("storage_path", sa.Text(), nullable=False),
            sa.Column("width", sa.Integer(), nullable=True),
            sa.Column("height", sa.Integer(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("source_metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("normalized_metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("id", UUID, primary_key=True, nullable=False),
            sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("brand_space_id", UUID, sa.ForeignKey("brand_spaces.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_reusable_brand_assets_knowledge_asset_id", "reusable_brand_assets", ["knowledge_asset_id"])
        op.create_index("ix_reusable_brand_assets_asset_kind", "reusable_brand_assets", ["asset_kind"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "reusable_brand_assets"):
        index_names = {index["name"] for index in inspector.get_indexes("reusable_brand_assets")}
        if "ix_reusable_brand_assets_asset_kind" in index_names:
            op.drop_index("ix_reusable_brand_assets_asset_kind", table_name="reusable_brand_assets")
        if "ix_reusable_brand_assets_knowledge_asset_id" in index_names:
            op.drop_index("ix_reusable_brand_assets_knowledge_asset_id", table_name="reusable_brand_assets")
        op.drop_table("reusable_brand_assets")
