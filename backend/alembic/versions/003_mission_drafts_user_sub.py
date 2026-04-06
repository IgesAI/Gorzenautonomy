"""mission_drafts keyed by JWT subject (user_sub)

Revision ID: 003_mission_drafts_user_sub
Revises: 002_prediction_validation
Create Date: 2026-04-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "003_mission_drafts_user_sub"
down_revision: Union[str, None] = "002_prediction_validation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mission_drafts", sa.Column("user_sub", sa.String(length=256), nullable=True))
    bind = op.get_bind()
    bind.execute(text("UPDATE mission_drafts SET user_sub = 'dev' WHERE user_sub IS NULL"))
    bind.execute(
        text(
            "INSERT INTO mission_drafts (waypoints_json, user_sub) "
            "SELECT CAST('[]' AS JSON), 'dev' "
            "WHERE NOT EXISTS (SELECT 1 FROM mission_drafts LIMIT 1)"
        )
    )
    op.drop_constraint("mission_drafts_pkey", "mission_drafts", type_="primary")
    op.drop_column("mission_drafts", "id")
    op.alter_column("mission_drafts", "user_sub", nullable=False)
    op.create_primary_key("mission_drafts_pkey", "mission_drafts", ["user_sub"])


def downgrade() -> None:
    op.drop_constraint("mission_drafts_pkey", "mission_drafts", type_="primary")
    op.add_column(
        "mission_drafts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=True),
    )
    op.execute("UPDATE mission_drafts SET id = 1 WHERE id IS NULL")
    op.alter_column("mission_drafts", "id", nullable=False)
    op.create_primary_key("mission_drafts_pkey", "mission_drafts", ["id"])
    op.drop_column("mission_drafts", "user_sub")
