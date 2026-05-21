"""Add structured audience evidence grounding fields."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006_audience_evidence_grounding"
down_revision = "0005_reusable_brand_assets"
branch_labels = None
depends_on = None


JSONB = postgresql.JSONB(astext_type=sa.Text())


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "audience_insight_structured_data"):
        return

    for column_name in (
        "objections",
        "desired_outcomes",
        "trust_signals",
        "proof_cues",
        "comparison_points",
    ):
        if _has_column(inspector, "audience_insight_structured_data", column_name):
            continue
        op.add_column(
            "audience_insight_structured_data",
            sa.Column(column_name, JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "audience_insight_structured_data"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("audience_insight_structured_data")}
    for column_name in (
        "comparison_points",
        "proof_cues",
        "trust_signals",
        "desired_outcomes",
        "objections",
    ):
        if column_name in existing_columns:
            op.drop_column("audience_insight_structured_data", column_name)
