"""Layer 3: Twin graph, versioning, and configuration management."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from gorzen.schemas.subsystems import (
    AIModelConfig,
    AirframeConfig,
    AvionicsConfig,
    CommsConfig,
    ComputeConfig,
    CruisePropulsionConfig,
    EnergyConfig,
    FuelSystemConfig,
    LiftPropulsionConfig,
    MissionProfileConfig,
    PayloadConfig,
)


class SemanticVersion(BaseModel):
    major: int = 0
    minor: int = 1
    patch: int = 0

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class FirmwareCompat(BaseModel):
    autopilot: str = "px4"
    min_version: str = "1.14.0"
    max_version: str | None = None


class CalibrationState(BaseModel):
    last_calibrated: datetime | None = None
    calibration_run_ids: list[str] = Field(default_factory=list)
    posterior_version: str | None = None
    data_coverage_pct: float = 0.0
    quality_score: float | None = None


class RelationshipType(str, Enum):
    POWERS = "powers"
    MOUNTS_ON = "mounts_on"
    SENSES_FOR = "senses_for"
    CONTROLS = "controls"
    FEEDS_DATA = "feeds_data"


class Relationship(BaseModel):
    source_subsystem: str
    target_subsystem: str
    rel_type: RelationshipType
    metadata: dict[str, Any] = Field(default_factory=dict)


class SubsystemNode(BaseModel):
    subsystem_type: str
    config: Any
    catalog_entry_id: str | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)


class VehicleTwin(BaseModel):
    """Top-level digital-twin entity representing a fully configured VTOL vehicle."""

    twin_id: UUID = Field(default_factory=uuid4)
    name: str = "Unnamed Twin"
    description: str = ""
    version: SemanticVersion = Field(default_factory=SemanticVersion)
    build_hash: str = ""
    firmware_compat: FirmwareCompat = Field(default_factory=FirmwareCompat)

    airframe: AirframeConfig = Field(default_factory=AirframeConfig)
    lift_propulsion: LiftPropulsionConfig = Field(default_factory=LiftPropulsionConfig)
    cruise_propulsion: CruisePropulsionConfig = Field(default_factory=CruisePropulsionConfig)
    fuel_system: FuelSystemConfig = Field(default_factory=FuelSystemConfig)
    energy: EnergyConfig = Field(default_factory=EnergyConfig)
    avionics: AvionicsConfig = Field(default_factory=AvionicsConfig)
    compute: ComputeConfig = Field(default_factory=ComputeConfig)
    comms: CommsConfig = Field(default_factory=CommsConfig)
    payload: PayloadConfig = Field(default_factory=PayloadConfig)
    ai_model: AIModelConfig = Field(default_factory=AIModelConfig)
    mission_profile: MissionProfileConfig = Field(default_factory=MissionProfileConfig)

    relationships: list[Relationship] = Field(default_factory=list)
    calibration_state: CalibrationState | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def compute_build_hash(self) -> str:
        payload = self.model_dump(exclude={"twin_id", "build_hash", "created_at", "updated_at"})
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def with_hash(self) -> "VehicleTwin":
        self.build_hash = self.compute_build_hash()
        return self
