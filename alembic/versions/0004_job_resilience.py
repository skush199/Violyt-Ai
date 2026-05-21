"""Add worker lease tracking for resilient job processing."""

from alembic import op
import sqlalchemy as sa


revision = "0004_job_resilience"
down_revision = "0003_brand_asset_architecture"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = [
        ("lease_owner", sa.String(length=255), True),
        ("lease_expires_at", sa.DateTime(timezone=True), True),
        ("heartbeat_at", sa.DateTime(timezone=True), True),
        ("started_at", sa.DateTime(timezone=True), True),
        ("finished_at", sa.DateTime(timezone=True), True),
    ]
    for column_name, column_type, nullable in columns:
        if not _has_column(inspector, "jobs", column_name):
            op.add_column("jobs", sa.Column(column_name, column_type, nullable=nullable))

    if not _has_index(inspector, "jobs", "ix_jobs_lease_owner"):
        op.create_index("ix_jobs_lease_owner", "jobs", ["lease_owner"])
    if not _has_index(inspector, "jobs", "ix_jobs_lease_expires_at"):
        op.create_index("ix_jobs_lease_expires_at", "jobs", ["lease_expires_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_index(inspector, "jobs", "ix_jobs_lease_expires_at"):
        op.drop_index("ix_jobs_lease_expires_at", table_name="jobs")
    if _has_index(inspector, "jobs", "ix_jobs_lease_owner"):
        op.drop_index("ix_jobs_lease_owner", table_name="jobs")
    for column_name in ("finished_at", "started_at", "heartbeat_at", "lease_expires_at", "lease_owner"):
        if _has_column(inspector, "jobs", column_name):
            op.drop_column("jobs", column_name)
