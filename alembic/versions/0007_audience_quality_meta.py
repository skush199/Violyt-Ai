"""Persist audience evidence quality metadata on structured rows."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0007_audience_quality_meta"
down_revision = "0006_audience_evidence_grounding"
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

    additions = (
        ("research_evidence", sa.Column("research_evidence", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))),
        ("research_signal_count", sa.Column("research_signal_count", sa.Integer(), nullable=False, server_default=sa.text("0"))),
        ("analysis_quality", sa.Column("analysis_quality", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))),
        ("evidence_confidence", sa.Column("evidence_confidence", sa.Float(), nullable=True)),
        ("source_agreement_score", sa.Column("source_agreement_score", sa.Float(), nullable=True)),
    )
    for column_name, column in additions:
        if _has_column(inspector, "audience_insight_structured_data", column_name):
            continue
        op.add_column("audience_insight_structured_data", column)

    if not _has_table(inspector, "audience_insight_assets"):
        return

    op.execute(
        sa.text(
            """
            UPDATE audience_insight_structured_data AS structured
            SET
                research_evidence = COALESCE(
                    asset.source_metadata_json->'analysis_metadata'->'audience_evidence',
                    '{}'::jsonb
                ),
                research_signal_count = COALESCE(
                    CASE
                        WHEN COALESCE(asset.source_metadata_json->'analysis_metadata'->>'research_signal_count', '') ~ '^[0-9]+$'
                            THEN (asset.source_metadata_json->'analysis_metadata'->>'research_signal_count')::integer
                        ELSE 0
                    END,
                    0
                ),
                analysis_quality = COALESCE(
                    asset.source_metadata_json->'analysis_metadata'->'analysis_quality',
                    '{}'::jsonb
                ),
                evidence_confidence = COALESCE(asset.confidence, structured.evidence_confidence),
                source_agreement_score = COALESCE(
                    CASE
                        WHEN COALESCE(asset.source_metadata_json->'analysis_metadata'->'analysis_quality'->>'source_agreement_score', '') ~ '^-?[0-9]+(?:\\.[0-9]+)?$'
                            THEN (asset.source_metadata_json->'analysis_metadata'->'analysis_quality'->>'source_agreement_score')::double precision
                        ELSE NULL
                    END,
                    structured.source_agreement_score
                )
            FROM audience_insight_assets AS asset
            WHERE structured.audience_insight_asset_id = asset.id
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "audience_insight_structured_data"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("audience_insight_structured_data")}
    for column_name in (
        "source_agreement_score",
        "evidence_confidence",
        "analysis_quality",
        "research_signal_count",
        "research_evidence",
    ):
        if column_name in existing_columns:
            op.drop_column("audience_insight_structured_data", column_name)
