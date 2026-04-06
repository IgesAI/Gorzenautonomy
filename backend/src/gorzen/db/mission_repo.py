"""Persist mission draft waypoints (one row per JWT subject)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.db.models import MissionDraftDB


async def load_waypoints_json(session: AsyncSession, user_sub: str) -> list[dict[str, Any]]:
    row = await session.get(MissionDraftDB, user_sub)
    if row is None:
        return []
    return list(row.waypoints_json or [])


async def save_waypoints_json(
    session: AsyncSession, user_sub: str, waypoints: list[dict[str, Any]]
) -> None:
    row = await session.get(MissionDraftDB, user_sub)
    if row is None:
        row = MissionDraftDB(user_sub=user_sub, waypoints_json=waypoints)
        session.add(row)
    else:
        row.waypoints_json = waypoints
    await session.flush()


async def ensure_mission_draft_row(session: AsyncSession, user_sub: str) -> None:
    row = await session.get(MissionDraftDB, user_sub)
    if row is None:
        session.add(MissionDraftDB(user_sub=user_sub, waypoints_json=[]))
        await session.flush()
