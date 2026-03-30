"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2025-03-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "twin_configs",
        sa.Column("twin_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version_major", sa.Integer(), nullable=False),
        sa.Column("version_minor", sa.Integer(), nullable=False),
        sa.Column("version_patch", sa.Integer(), nullable=False),
        sa.Column("build_hash", sa.String(length=32), nullable=False),
        sa.Column("config_json", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("firmware_compat", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("twin_uuid"),
    )
    op.create_table(
        "mission_drafts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("waypoints_json", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "catalog_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subsystem_type", sa.String(length=64), nullable=False),
        sa.Column("manufacturer", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parameters", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("datasheet_url", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_catalog_entries_subsystem_type", "catalog_entries", ["subsystem_type"], unique=False)
    op.create_table(
        "calibration_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("twin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mission_type", sa.String(length=64), nullable=False),
        sa.Column("config_hash", sa.String(length=32), nullable=False),
        sa.Column("regime", sa.String(length=64), nullable=False),
        sa.Column("posteriors_json", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("n_observations", sa.Integer(), nullable=False),
        sa.Column("log_marginal_likelihood", sa.Float(), nullable=False),
        sa.Column("log_ids", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calibration_runs_twin_id", "calibration_runs", ["twin_id"], unique=False)
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("twin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_twin_id", "audit_events", ["twin_id"], unique=False)
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"], unique=False)
    op.create_index("ix_audit_events_timestamp", "audit_events", ["timestamp"], unique=False)
    op.create_table(
        "telemetry_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("twin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_format", sa.String(length=32), nullable=False),
        sa.Column("vehicle_id", sa.String(length=255), nullable=False),
        sa.Column("firmware_version", sa.String(length=64), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("topics", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("log_metadata", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_telemetry_logs_twin_id", "telemetry_logs", ["twin_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_telemetry_logs_twin_id", table_name="telemetry_logs")
    op.drop_table("telemetry_logs")
    op.drop_index("ix_audit_events_timestamp", table_name="audit_events")
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_index("ix_audit_events_twin_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_calibration_runs_twin_id", table_name="calibration_runs")
    op.drop_table("calibration_runs")
    op.drop_index("ix_catalog_entries_subsystem_type", table_name="catalog_entries")
    op.drop_table("catalog_entries")
    op.drop_table("mission_drafts")
    op.drop_table("twin_configs")
