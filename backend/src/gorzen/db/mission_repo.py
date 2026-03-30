"""Persist mission draft waypoints (singleton row id=1)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from gorzen.db.models import MissionDraftDB

MISSION_DRAFT_ID = 1


async def load_waypoints_json(session: AsyncSession) -> list[dict[str, Any]]:
    row = await session.get(MissionDraftDB, MISSION_DRAFT_ID)
    if row is None:
        return []
    return list(row.waypoints_json or [])


async def save_waypoints_json(session: AsyncSession, waypoints: list[dict[str, Any]]) -> None:
    row = await session.get(MissionDraftDB, MISSION_DRAFT_ID)
    if row is None:
        row = MissionDraftDB(id=MISSION_DRAFT_ID, waypoints_json=waypoints)
        session.add(row)
    else:
        row.waypoints_json = waypoints
    await session.flush()


async def ensure_mission_draft_row(session: AsyncSession) -> None:
    row = await session.get(MissionDraftDB, MISSION_DRAFT_ID)
    if row is None:
        session.add(MissionDraftDB(id=MISSION_DRAFT_ID, waypoints_json=[]))
        await session.flush()
