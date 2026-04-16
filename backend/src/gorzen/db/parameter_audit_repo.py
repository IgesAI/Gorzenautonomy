"""Persistence helpers for the append-only FC parameter audit log."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from gorzen.db.models import Base


class ParameterAuditDB(Base):
    """Append-only audit row for an FC parameter write."""

    __tablename__ = "parameter_audit"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    twin_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("twin_configs.twin_uuid", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor: Mapped[str] = mapped_column(String(256), nullable=False)
    param_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    old_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_value: Mapped[float] = mapped_column(Float, nullable=False)
    param_type: Mapped[int] = mapped_column(Integer, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


async def record_param_write(
    session: AsyncSession,
    *,
    twin_id: UUID | None,
    actor: str,
    param_id: str,
    old_value: float | None,
    new_value: float,
    param_type: int,
    success: bool,
    context: dict[str, Any] | None = None,
) -> ParameterAuditDB:
    row = ParameterAuditDB(
        twin_id=twin_id,
        actor=actor,
        param_id=param_id,
        old_value=old_value,
        new_value=float(new_value),
        param_type=int(param_type),
        success=bool(success),
        context=context or {},
    )
    session.add(row)
    await session.flush()
    return row


async def list_param_writes(
    session: AsyncSession,
    *,
    twin_id: UUID | None = None,
    param_id: str | None = None,
    actor: str | None = None,
    since: datetime | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[ParameterAuditDB]:
    stmt = select(ParameterAuditDB).order_by(ParameterAuditDB.created_at.desc())
    if twin_id is not None:
        stmt = stmt.where(ParameterAuditDB.twin_id == twin_id)
    if param_id is not None:
        stmt = stmt.where(ParameterAuditDB.param_id == param_id)
    if actor is not None:
        stmt = stmt.where(ParameterAuditDB.actor == actor)
    if since is not None:
        stmt = stmt.where(ParameterAuditDB.created_at >= since)
    stmt = stmt.offset(offset).limit(limit)
    return list((await session.scalars(stmt)).all())
