"""Component catalog schema and seed data for metadata-driven UI generation.

Seed data sourced from Cobra AERO engine datasheets and Vertical Autonomy
airframe datasheets. The platform is NOT hardcoded to this hardware — any
engine, airframe, or payload can be added to the catalog.

AUTHORITY: This file is the SINGLE SOURCE OF TRUTH for seeded platform and
propulsion specifications.  No other file may define duplicate fallback
specs.  Every seeded value carries structured provenance metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Parameter classification and provenance
# ---------------------------------------------------------------------------

class ParameterClassification(str, Enum):
    """How a parameter value may be used in computations."""

    DATASHEET_LOCKED = "datasheet_locked"
    OPERATOR_INPUT_REQUIRED = "operator_input_required"
    DERIVED_ONLY = "derived_only"


class CatalogProvenance(BaseModel):
    """Structured traceability for a catalog parameter value."""

    source_file: str | None = None
    source_page: str | None = None
    source_revision: str | None = None
    last_verified: str | None = None
    classification: ParameterClassification = ParameterClassification.DATASHEET_LOCKED
    notes: str | None = None


class CatalogFieldDef(BaseModel):
    """Definition of a single field in a component pack."""

    model_config = {"protected_namespaces": ()}

    name: str
    display_name: str
    units: str
    field_type: str = "float"
    default_value: Any = None
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[Any] | None = None
    group: str = "general"
    advanced: bool = False
    tooltip: str | None = None
    model_binding: str | None = None


class ValidationRule(BaseModel):
    """Cross-field or complex validation rule."""

    rule_id: str
    description: str
    expression: str
    severity: str = "error"


class ComponentPackDef(BaseModel):
    """A 'component pack' ships parameter definitions, constraints, and UI metadata."""

    pack_id: UUID = Field(default_factory=uuid4)
    subsystem_type: str
    name: str
    version: str = "1.0.0"
    fields: list[CatalogFieldDef] = Field(default_factory=list)
    validation_rules: list[ValidationRule] = Field(default_factory=list)


class ComponentCatalogEntry(BaseModel):
    """A concrete component in the catalog.

    Every entry carries structured provenance for audit and validation.
    The ``parameter_provenance`` dict maps parameter names to their
    traceability records so the validation engine can verify that no
    computation depends on unverified data.
    """

    model_config = {"protected_namespaces": ()}

    entry_id: UUID = Field(default_factory=uuid4)
    subsystem_type: str
    manufacturer: str
    model_name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    parameter_provenance: dict[str, CatalogProvenance] = Field(default_factory=dict)
    datasheet_url: str | None = None
    pack_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Provenance helpers for seed data
# ---------------------------------------------------------------------------

def _cobra_prov(page: str = "1", rev: str = "2025-04") -> dict:
    """Provenance record for Cobra AERO engine datasheet values."""
    return {
        "source_file": "Cobra_AERO_Datasheet",
        "source_page": page,
        "source_revision": rev,
        "last_verified": "2025-04",
        "classification": "datasheet_locked",
    }


def _va_prov(model: str, page: str = "1", rev: str = "2025-11") -> dict:
    """Provenance record for Vertical Autonomy airframe datasheet values."""
    return {
        "source_file": f"{model}_Datasheet",
        "source_page": page,
        "source_revision": rev,
        "last_verified": "2025-11",
        "classification": "datasheet_locked",
    }


def _engine_provenance(params: dict, page: str = "1", rev: str = "2025-04") -> dict:
    """Build parameter_provenance dict for an engine, all fields datasheet_locked."""
    return {k: _cobra_prov(page, rev) for k in params}


def _airframe_provenance(params: dict, model: str, page: str = "1", rev: str = "2025-11") -> dict:
    return {k: _va_prov(model, page, rev) for k in params}


def _fuel_provenance(params: dict, model: str = "VA-55") -> dict:
    return {k: _va_prov(model, page="fuel_system", rev="2025-11") for k in params}


# ---------------------------------------------------------------------------
# Seed catalog: Cobra AERO engines (from datasheets)
# ---------------------------------------------------------------------------

_A33N_PARAMS: dict[str, Any] = {
    "engine_type": "2stroke_single",
    "displacement_cc": 33.0,
    "engine_mass_kg": 3.15,
    "max_power_kw": 2.2,
    "max_power_rpm": 8350,
    "bsfc_cruise_g_kwh": 500.0,
    "cooling_type": "air_cooled",
    "efi_system": "intelliject",
    "altitude_compensation": True,
    "cold_start_compensation": True,
    "preheat_required": False,
    "preheat_time_min": 0,
    "preheat_power_w": 0,
    "generator_output_w": 200,
    "generator_output_intermittent_w": 400,
    "hybrid_boost_available": True,
    "engine_can_interface": True,
    "engine_serial_interface": True,
    "onboard_data_logging": True,
    "sensor_cht": True,
    "sensor_mat": True,
    "sensor_fuel_pressure": True,
    "sensor_baro": True,
    "sensor_map": True,
}

SEED_ENGINES: list[dict] = [
    {
        "subsystem_type": "cruise_propulsion",
        "manufacturer": "Cobra AERO",
        "model_name": "A33N",
        "description": "Air-cooled 2-stroke single, 33cc, gasoline. Group 2 UAS standard.",
        "datasheet_url": "https://www.cobra-aero.com",
        "parameters": _A33N_PARAMS,
        "parameter_provenance": _engine_provenance(_A33N_PARAMS, page="A33N_Data_Sheet p1"),
    },
    {
        "subsystem_type": "cruise_propulsion",
        "manufacturer": "Cobra AERO",
        "model_name": "A33HF",
        "description": "Air-cooled 2-stroke single, 33cc, heavy fuel (JP5/JP8/Jet A). Purpose-designed for HF, not a conversion.",
        "datasheet_url": "https://www.cobra-aero.com",
        "parameters": (_A33HF_PARAMS := {
            "engine_type": "2stroke_single",
            "displacement_cc": 33.0,
            "engine_mass_kg": 3.15,
            "max_power_kw": 1.9,
            "max_power_rpm": 8050,
            "bsfc_cruise_g_kwh": 500.0,
            "cooling_type": "air_cooled",
            "efi_system": "intelliject",
            "altitude_compensation": True,
            "cold_start_compensation": True,
            "preheat_required": True,
            "preheat_time_min": 10,
            "preheat_power_w": 110,
            "generator_output_w": 200,
            "generator_output_intermittent_w": 400,
            "hybrid_boost_available": True,
            "engine_can_interface": True,
            "engine_serial_interface": True,
            "onboard_data_logging": True,
            "sensor_cht": True,
            "sensor_mat": True,
            "sensor_fuel_pressure": True,
            "sensor_baro": True,
            "sensor_map": True,
        }),
        "parameter_provenance": {k: _cobra_prov("A33HF_Data_Sheet p1") for k in _A33HF_PARAMS},
    },
    {
        "subsystem_type": "cruise_propulsion",
        "manufacturer": "Cobra AERO",
        "model_name": "A99HF",
        "description": "Liquid-cooled 2-stroke inline triple, 101.4cc, heavy fuel. Low vibration, high power.",
        "datasheet_url": "https://www.cobra-aero.com",
        "parameters": (_A99HF_PARAMS := {
            "engine_type": "2stroke_triple",
            "displacement_cc": 101.4,
            "engine_mass_kg": 8.4,
            "max_power_kw": 6.5,
            "max_power_rpm": 7000,
            "bsfc_cruise_g_kwh": 460.0,
            "cooling_type": "liquid_cooled",
            "efi_system": "intelliject",
            "altitude_compensation": True,
            "cold_start_compensation": True,
            "preheat_required": True,
            "preheat_time_min": 10,
            "preheat_power_w": 110,
            "generator_output_w": 650,
            "generator_output_intermittent_w": 800,
            "hybrid_boost_available": True,
            "engine_can_interface": True,
            "engine_serial_interface": True,
            "onboard_data_logging": True,
            "sensor_cht": True,
            "sensor_mat": True,
            "sensor_fuel_pressure": True,
            "sensor_baro": True,
            "sensor_map": True,
        }),
        "parameter_provenance": {k: _cobra_prov("A99HF_data_sheet p1") for k in _A99HF_PARAMS},
    },
    {
        "subsystem_type": "cruise_propulsion",
        "manufacturer": "Cobra AERO",
        "model_name": "A99S (Series Generator)",
        "description": "Liquid-cooled 2-stroke inline triple, 99cc, series generator. 4.8kW DC rectified output.",
        "datasheet_url": "https://www.cobra-aero.com",
        "parameters": (_A99S_PARAMS := {
            "engine_type": "2stroke_triple",
            "displacement_cc": 99.0,
            "engine_mass_kg": 5.58,
            "max_power_kw": 4.8,
            "max_power_rpm": 7000,
            "bsfc_cruise_g_kwh": 460.0,
            "cooling_type": "liquid_cooled",
            "efi_system": "intelliject",
            "altitude_compensation": True,
            "cold_start_compensation": True,
            "preheat_required": False,
            "preheat_time_min": 0,
            "preheat_power_w": 0,
            "power_architecture": "series_hybrid",
            "generator_output_w": 4800,
            "generator_output_intermittent_w": 4800,
            "generator_voltage_v": 70,
            "engine_can_interface": True,
            "engine_serial_interface": True,
            "onboard_data_logging": True,
            "sensor_cht": True,
            "sensor_mat": True,
            "sensor_fuel_pressure": True,
            "sensor_baro": True,
            "sensor_map": True,
        }),
        "parameter_provenance": {k: _cobra_prov("A99S_data_sheet p1") for k in _A99S_PARAMS},
    },
]

# ---------------------------------------------------------------------------
# Seed catalog: Vertical Autonomy airframes (from datasheets)
# ---------------------------------------------------------------------------

_VA55_PARAMS: dict[str, Any] = {
    "wing_span_m": 3.96,
    "fuselage_length_m": 2.06,
    "height_m": 0.33,
    "mass_empty_kg": 16.78,
    "mass_mtow_kg": 24.95,
    "payload_capacity_nose_kg": 4.54,
    "payload_capacity_boom_kg": 0.91,
    "max_speed_kts": 60.0,
    "cruise_speed_kts": 36.0,
    "max_endurance_hr": 10.0,
    "range_nmi": 360.0,
    "service_ceiling_ft": 12000,
    "vtol_ceiling_ft": 7000,
    "max_crosswind_kts": 30.0,
    "max_operating_temp_c": 49.0,
    "min_operating_temp_c": -29.0,
    "landing_zone_m": 6.1,
}

_VA120_PARAMS: dict[str, Any] = {
    "wing_span_m": 4.88,
    "fuselage_length_m": 2.49,
    "height_m": 0.66,
    "mass_empty_kg": 34.0,
    "mass_mtow_kg": 68.0,
    "payload_capacity_nose_kg": 11.3,
    "payload_capacity_boom_kg": 4.53,
    "max_speed_kts": 65.0,
    "cruise_speed_kts": 42.0,
    "max_endurance_hr": 16.0,
    "range_nmi": 675.0,
    "service_ceiling_ft": 18000,
    "vtol_ceiling_ft": 9000,
    "max_crosswind_kts": 30.0,
    "max_operating_temp_c": 49.0,
    "min_operating_temp_c": -29.0,
    "landing_zone_m": 7.62,
    "crew_size": 2,
}

_VA150_PARAMS: dict[str, Any] = {
    "wing_span_m": 4.88,
    "fuselage_length_m": 2.49,
    "height_m": 0.66,
    "mass_empty_kg": 34.0,
    "mass_mtow_kg": 68.0,
    "payload_capacity_nose_kg": 11.3,
    "payload_capacity_boom_kg": 4.53,
    "max_speed_kts": 65.0,
    "cruise_speed_kts": 42.0,
    "max_endurance_hr": 16.0,
    "range_nmi": 810.0,
    "service_ceiling_ft": 18000,
    "vtol_ceiling_ft": 9000,
    "max_crosswind_kts": 30.0,
    "max_operating_temp_c": 49.0,
    "min_operating_temp_c": -29.0,
    "landing_zone_m": 7.62,
}

SEED_AIRFRAMES: list[dict] = [
    {
        "subsystem_type": "airframe",
        "manufacturer": "Vertical Autonomy",
        "model_name": "VA-55",
        "description": "Expeditionary VTOL UAS for tactical ISR. 2-person deployable, pack-in/pack-out.",
        "datasheet_url": "https://www.verticalautonomy.com",
        "parameters": _VA55_PARAMS,
        "parameter_provenance": {k: _va_prov("VA-55", "VA-55+Datasheet p1") for k in _VA55_PARAMS},
    },
    {
        "subsystem_type": "airframe",
        "manufacturer": "Vertical Autonomy",
        "model_name": "VA-120",
        "description": "Long-endurance VTOL UAS for ISR, comms relay. Moving baseline capable (land/maritime).",
        "datasheet_url": "https://www.verticalautonomy.com",
        "parameters": _VA120_PARAMS,
        "parameter_provenance": {k: _va_prov("VA-120", "VA-120+Datasheet p1") for k in _VA120_PARAMS},
    },
    {
        "subsystem_type": "airframe",
        "manufacturer": "Vertical Autonomy",
        "model_name": "VA-150",
        "description": "Long-endurance heavy-fuel VTOL UAS. Next-gen platform, 8-16hr endurance, SATCOM.",
        "datasheet_url": "https://www.verticalautonomy.com",
        "parameters": _VA150_PARAMS,
        "parameter_provenance": {k: _va_prov("VA-150", "VA-150+Datasheet p1") for k in _VA150_PARAMS},
    },
]

# ---------------------------------------------------------------------------
# Seed catalog: fuel system configurations
# ---------------------------------------------------------------------------

_FUEL_VA55_JP5: dict[str, Any] = {
    "fuel_type": "jp5",
    "fuel_density_kg_l": 0.81,
    "tank_capacity_l": 10.0,
    "tank_capacity_kg": 8.1,
    "usable_fuel_pct": 95.0,
    "fuel_reserve_pct": 15.0,
    "premix_ratio": 50,
    "fuel_pump_self_priming": True,
    "fuel_pump_type": "currawong",
    "fuel_pressure_accumulator": True,
}

_FUEL_VA55_GAS: dict[str, Any] = {
    "fuel_type": "gasoline",
    "fuel_density_kg_l": 0.72,
    "tank_capacity_l": 10.0,
    "tank_capacity_kg": 7.2,
    "usable_fuel_pct": 95.0,
    "fuel_reserve_pct": 15.0,
    "premix_ratio": 50,
    "fuel_pump_self_priming": True,
    "fuel_pump_type": "currawong",
    "fuel_pressure_accumulator": True,
}

_FUEL_VA120_150: dict[str, Any] = {
    "fuel_type": "jp5",
    "fuel_density_kg_l": 0.81,
    "tank_capacity_l": 25.0,
    "tank_capacity_kg": 20.25,
    "usable_fuel_pct": 95.0,
    "fuel_reserve_pct": 15.0,
    "premix_ratio": 50,
    "fuel_pump_self_priming": True,
    "fuel_pump_type": "currawong",
    "fuel_pressure_accumulator": True,
}

SEED_FUEL_SYSTEMS: list[dict] = [
    {
        "subsystem_type": "fuel_system",
        "manufacturer": "Vertical Autonomy",
        "model_name": "VA-55 Fuel System (JP5)",
        "parameters": _FUEL_VA55_JP5,
        "parameter_provenance": {k: _va_prov("VA-55", "fuel_system_spec") for k in _FUEL_VA55_JP5},
    },
    {
        "subsystem_type": "fuel_system",
        "manufacturer": "Vertical Autonomy",
        "model_name": "VA-55 Fuel System (Gasoline)",
        "parameters": _FUEL_VA55_GAS,
        "parameter_provenance": {k: _va_prov("VA-55", "fuel_system_spec") for k in _FUEL_VA55_GAS},
    },
    {
        "subsystem_type": "fuel_system",
        "manufacturer": "Vertical Autonomy",
        "model_name": "VA-120/150 Fuel System",
        "parameters": _FUEL_VA120_150,
        "parameter_provenance": {k: _va_prov("VA-120/150", "fuel_system_spec") for k in _FUEL_VA120_150},
    },
]

# ---------------------------------------------------------------------------
# Seed catalog: known engine-airframe pairings
# ---------------------------------------------------------------------------

SEED_PAIRINGS: list[dict] = [
    {"airframe": "VA-55", "engine_jp5": "A33HF", "engine_gasoline": "A33N"},
    {"airframe": "VA-120", "engine_gasoline": "B100iJ"},
    {"airframe": "VA-150", "engine_jp5": "A99HF", "engine_gasoline": "B100iJ"},
]


def build_seed_catalog() -> list[ComponentCatalogEntry]:
    """Build the full seed catalog from all component types."""
    entries: list[ComponentCatalogEntry] = []
    for items in (SEED_ENGINES, SEED_AIRFRAMES, SEED_FUEL_SYSTEMS):
        for item in items:
            entries.append(ComponentCatalogEntry(**item))
    return entries
