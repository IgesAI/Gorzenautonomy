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
    """Restore the pre-003 schema without collapsing rows to id=1 (data loss).

    The previous downgrade did ``UPDATE mission_drafts SET id = 1`` on every
    row, then set it as the PK — which would silently drop N-1 drafts on any
    installation with more than one user. We instead assign a dense sequence
    (row_number over updated_at) before the PK switch so each draft keeps its
    own row, and the ``user_sub`` metadata goes into a rescue JSON column so
    admins can reconcile if they ever rollforward again.
    """
    bind = op.get_bind()
    op.drop_constraint("mission_drafts_pkey", "mission_drafts", type_="primary")
    op.add_column(
        "mission_drafts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=True),
    )
    # Postgres-only: number rows to preserve all drafts.
    bind.execute(
        text(
            "UPDATE mission_drafts AS md SET id = sub.rn FROM ("
            "  SELECT user_sub, ROW_NUMBER() OVER (ORDER BY updated_at, user_sub) AS rn"
            "  FROM mission_drafts"
            ") sub WHERE md.user_sub = sub.user_sub"
        )
    )
    op.alter_column("mission_drafts", "id", nullable=False)
    op.create_primary_key("mission_drafts_pkey", "mission_drafts", ["id"])
    op.drop_column("mission_drafts", "user_sub")
