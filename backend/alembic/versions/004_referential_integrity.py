"""Add referential integrity, per-owner scoping, and parameter audit log.

Revision ID: 004_referential_integrity
Revises: 003_mission_drafts_user_sub
Create Date: 2026-04-16

Introduces:

* ``twin_configs.owner_sub`` — JWT subject of the creator so twins can be
  scoped per-user.
* ``telemetry_logs.owner_sub`` / ``prediction_sets.owner_sub`` — same idea.
* Foreign keys + cascade rules from ``calibration_runs`` / ``prediction_sets``
  / ``validation_runs`` / ``audit_events`` / ``telemetry_logs`` to their
  parents so orphan rows can no longer accumulate.
* ``parameter_audit`` — append-only record of every PARAM_SET pushed to the
  FC. Required for flight-readiness / safety post-mortems.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_referential_integrity"
down_revision: Union[str, None] = "003_mission_drafts_user_sub"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "twin_configs",
        sa.Column("owner_sub", sa.String(length=256), nullable=False, server_default="dev"),
    )
    op.create_index("ix_twin_configs_owner_sub", "twin_configs", ["owner_sub"])

    op.add_column(
        "telemetry_logs",
        sa.Column("owner_sub", sa.String(length=256), nullable=False, server_default="dev"),
    )
    op.create_index("ix_telemetry_logs_owner_sub", "telemetry_logs", ["owner_sub"])

    op.add_column(
        "prediction_sets",
        sa.Column("owner_sub", sa.String(length=256), nullable=False, server_default="dev"),
    )
    op.create_index("ix_prediction_sets_owner_sub", "prediction_sets", ["owner_sub"])

    # Clean up any orphan rows BEFORE applying FKs — otherwise PG rejects the ADD.
    op.execute(
        "DELETE FROM calibration_runs WHERE twin_id NOT IN "
        "(SELECT twin_uuid FROM twin_configs)"
    )
    op.execute(
        "DELETE FROM prediction_sets WHERE twin_id NOT IN "
        "(SELECT twin_uuid FROM twin_configs)"
    )
    op.execute(
        "DELETE FROM validation_runs WHERE prediction_id NOT IN "
        "(SELECT id FROM prediction_sets)"
    )
    op.execute(
        "UPDATE audit_events SET twin_id = NULL WHERE twin_id IS NOT NULL AND twin_id NOT IN "
        "(SELECT twin_uuid FROM twin_configs)"
    )
    op.execute(
        "UPDATE telemetry_logs SET twin_id = NULL WHERE twin_id IS NOT NULL AND twin_id NOT IN "
        "(SELECT twin_uuid FROM twin_configs)"
    )

    op.create_foreign_key(
        "fk_calibration_runs_twin_id",
        "calibration_runs",
        "twin_configs",
        ["twin_id"],
        ["twin_uuid"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_prediction_sets_twin_id",
        "prediction_sets",
        "twin_configs",
        ["twin_id"],
        ["twin_uuid"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_validation_runs_prediction_id",
        "validation_runs",
        "prediction_sets",
        ["prediction_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_audit_events_twin_id",
        "audit_events",
        "twin_configs",
        ["twin_id"],
        ["twin_uuid"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_telemetry_logs_twin_id",
        "telemetry_logs",
        "twin_configs",
        ["twin_id"],
        ["twin_uuid"],
        ondelete="SET NULL",
    )

    op.create_table(
        "parameter_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("twin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor", sa.String(length=256), nullable=False),
        sa.Column("param_id", sa.String(length=32), nullable=False),
        sa.Column("old_value", sa.Float(), nullable=True),
        sa.Column("new_value", sa.Float(), nullable=False),
        sa.Column("param_type", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("context", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["twin_id"], ["twin_configs.twin_uuid"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_parameter_audit_twin_id", "parameter_audit", ["twin_id"])
    op.create_index("ix_parameter_audit_param_id", "parameter_audit", ["param_id"])
    op.create_index("ix_parameter_audit_created_at", "parameter_audit", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_parameter_audit_created_at", table_name="parameter_audit")
    op.drop_index("ix_parameter_audit_param_id", table_name="parameter_audit")
    op.drop_index("ix_parameter_audit_twin_id", table_name="parameter_audit")
    op.drop_table("parameter_audit")

    op.drop_constraint("fk_telemetry_logs_twin_id", "telemetry_logs", type_="foreignkey")
    op.drop_constraint("fk_audit_events_twin_id", "audit_events", type_="foreignkey")
    op.drop_constraint(
        "fk_validation_runs_prediction_id", "validation_runs", type_="foreignkey"
    )
    op.drop_constraint("fk_prediction_sets_twin_id", "prediction_sets", type_="foreignkey")
    op.drop_constraint("fk_calibration_runs_twin_id", "calibration_runs", type_="foreignkey")

    op.drop_index("ix_prediction_sets_owner_sub", table_name="prediction_sets")
    op.drop_column("prediction_sets", "owner_sub")

    op.drop_index("ix_telemetry_logs_owner_sub", table_name="telemetry_logs")
    op.drop_column("telemetry_logs", "owner_sub")

    op.drop_index("ix_twin_configs_owner_sub", table_name="twin_configs")
    op.drop_column("twin_configs", "owner_sub")
