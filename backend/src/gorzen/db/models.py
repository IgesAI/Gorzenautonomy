"""SQLAlchemy ORM models for the digital-twin data layer."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TwinConfigDB(Base):
    """Persisted vehicle twin configuration."""

    __tablename__ = "twin_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    version_major: Mapped[int] = mapped_column(Integer, default=0)
    version_minor: Mapped[int] = mapped_column(Integer, default=1)
    version_patch: Mapped[int] = mapped_column(Integer, default=0)
    build_hash: Mapped[str] = mapped_column(String(32), default="")
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    firmware_compat: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class CatalogEntryDB(Base):
    """Persisted component catalog entry."""

    __tablename__ = "catalog_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subsystem_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    manufacturer: Mapped[str] = mapped_column(String(255), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    datasheet_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CalibrationRunDB(Base):
    """Record of a calibration run."""

    __tablename__ = "calibration_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    twin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    mission_type: Mapped[str] = mapped_column(String(64), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    regime: Mapped[str] = mapped_column(String(64), default="")
    posteriors_json: Mapped[dict] = mapped_column(JSON, default=dict)
    n_observations: Mapped[int] = mapped_column(Integer, default=0)
    log_marginal_likelihood: Mapped[float] = mapped_column(Float, default=0.0)
    log_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditEventDB(Base):
    """Append-only audit trail event."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    twin_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(255), default="system")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class TelemetryLogDB(Base):
    """Metadata record for an uploaded telemetry log file."""

    __tablename__ = "telemetry_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    twin_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    source_format: Mapped[str] = mapped_column(String(32), nullable=False)
    vehicle_id: Mapped[str] = mapped_column(String(255), default="")
    firmware_version: Mapped[str] = mapped_column(String(64), default="")
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    topics: Mapped[list] = mapped_column(JSON, default=list)
    metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
