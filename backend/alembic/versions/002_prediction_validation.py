"""Add prediction_sets and validation_runs tables for the v2 validation loop.

Revision ID: 002_prediction_validation
Revises: 001_initial
Create Date: 2026-03-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_prediction_validation"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prediction_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("twin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("predictions", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("envelope_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("model_version", sa.String(length=64), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prediction_sets_mission_id", "prediction_sets", ["mission_id"])
    op.create_index("ix_prediction_sets_twin_id", "prediction_sets", ["twin_id"])

    op.create_table(
        "validation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prediction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bag_path", sa.String(length=1024), nullable=True),
        sa.Column("actuals", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("deltas", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence_update", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="simulation"),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_validation_runs_prediction_id", "validation_runs", ["prediction_id"])
    op.create_index("ix_validation_runs_mission_id", "validation_runs", ["mission_id"])


def downgrade() -> None:
    op.drop_index("ix_validation_runs_mission_id", table_name="validation_runs")
    op.drop_index("ix_validation_runs_prediction_id", table_name="validation_runs")
    op.drop_table("validation_runs")
    op.drop_index("ix_prediction_sets_twin_id", table_name="prediction_sets")
    op.drop_index("ix_prediction_sets_mission_id", table_name="prediction_sets")
    op.drop_table("prediction_sets")
