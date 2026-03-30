"""Environment intelligence endpoints: weather, terrain, solar, NIIRS."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from gorzen.api.limiter import limiter
from gorzen.config import settings

from gorzen.models.perception.niirs_tasks import (
    get_all_levels_summary,
    get_niirs_level,
)
from gorzen.services.model_selector import (
    DeploymentMode,
    DefectClass,
    recommend_model,
)
from gorzen.services.solar import compute_solar_position
from gorzen.services.terrain import fetch_elevation, fetch_terrain_profile
from gorzen.services.weather import fetch_weather

router = APIRouter()


def _env_rate_limit() -> str:
    m = settings.rate_limit_per_minute
    return f"{m}/minute" if m and m > 0 else "2000/minute"


# --- Schemas ---


class SolarRequest(BaseModel):
    latitude: float = 35.0
    longitude: float = -106.0
    altitude_m: float = 0.0
    linke_turbidity: float = 3.0


class WeatherRequest(BaseModel):
    latitude: float = 35.0
    longitude: float = -106.0
    elevation_m: float = 0.0


class TerrainRequest(BaseModel):
    latitude: float = 35.0
    longitude: float = -106.0


class TerrainProfileRequest(BaseModel):
    points: list[list[float]]  # [[lat, lon], ...]


class ModelChainPoint(BaseModel):
    speed_ms: float = 15.0
    altitude_m: float = 50.0


# --- Endpoints ---


@router.get("/solar")
@limiter.limit(_env_rate_limit())
async def get_solar_position(
    request: Request,
    latitude: float = Query(35.0, ge=-90.0, le=90.0),
    longitude: float = Query(-106.0, ge=-180.0, le=180.0),
    altitude_m: float = Query(0.0, ge=-500.0, le=9000.0),
) -> dict[str, Any]:
    """Compute current solar position and irradiance for a location."""
    result = compute_solar_position(
        lat=latitude,
        lon=longitude,
        altitude_m=altitude_m,
    )
    return {
        "elevation_deg": result.elevation_deg,
        "azimuth_deg": result.azimuth_deg,
        "zenith_deg": result.zenith_deg,
        "declination_deg": result.declination_deg,
        "sunrise_hour": result.sunrise_hour,
        "sunset_hour": result.sunset_hour,
        "day_length_hr": result.day_length_hr,
        "ghi_w_m2": result.ghi_w_m2,
        "dni_w_m2": result.dni_w_m2,
        "dhi_w_m2": result.dhi_w_m2,
        "illuminance_lux": result.illuminance_lux,
        "solar_noon_utc": result.solar_noon_utc,
        "is_daytime": result.is_daytime,
    }


@router.get("/weather")
@limiter.limit(_env_rate_limit())
async def get_weather(
    request: Request,
    latitude: float = Query(35.0, ge=-90.0, le=90.0),
    longitude: float = Query(-106.0, ge=-180.0, le=180.0),
    elevation_m: float = Query(0.0, ge=-500.0, le=9000.0),
) -> dict[str, Any]:
    """Fetch current weather conditions with multi-altitude wind profiles."""
    try:
        result = await fetch_weather(
            lat=latitude,
            lon=longitude,
            elevation_m=elevation_m,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Weather API error: {e}")

    return {
        "temperature_c": result.temperature_c,
        "pressure_hpa": result.pressure_hpa,
        "humidity_pct": result.humidity_pct,
        "cloud_cover_pct": result.cloud_cover_pct,
        "visibility_m": result.visibility_m,
        "precipitation_mm": result.precipitation_mm,
        "density_altitude_ft": result.density_altitude_ft,
        "air_density_kgm3": result.air_density_kgm3,
        "flight_category": result.flight_category,
        "conditions_summary": result.conditions_summary,
        "timestamp": result.timestamp,
        "wind_layers": [
            {
                "height_m": wl.height_m,
                "speed_ms": round(wl.speed_ms, 1),
                "direction_deg": round(wl.direction_deg, 0),
                "gusts_ms": round(wl.gusts_ms, 1),
            }
            for wl in result.wind_layers
        ],
    }


@router.get("/terrain")
@limiter.limit(_env_rate_limit())
async def get_terrain_elevation(
    request: Request,
    latitude: float = Query(35.0, ge=-90.0, le=90.0),
    longitude: float = Query(-106.0, ge=-180.0, le=180.0),
) -> dict[str, Any]:
    """Fetch ground elevation for a point."""
    try:
        result = await fetch_elevation(lat=latitude, lon=longitude)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Terrain API error: {e}")

    return {
        "latitude": result.latitude,
        "longitude": result.longitude,
        "elevation_m": result.elevation_m,
        "elevation_ft": round(result.elevation_m * 3.281, 0),
    }


@router.post("/terrain/profile")
@limiter.limit(_env_rate_limit())
async def get_terrain_profile(
    http_request: Request, request: TerrainProfileRequest
) -> dict[str, Any]:
    """Fetch terrain elevation profile along a path."""
    points = [(p[0], p[1]) for p in request.points if len(p) >= 2]
    if not points:
        raise HTTPException(status_code=400, detail="No valid points")
    for lat, lon in points:
        if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
            raise HTTPException(
                status_code=400, detail=f"Invalid coordinates: lat={lat}, lon={lon}"
            )

    try:
        result = await fetch_terrain_profile(points)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Terrain API error: {e}")

    return {
        "points": [
            {
                "latitude": p.latitude,
                "longitude": p.longitude,
                "elevation_m": p.elevation_m,
            }
            for p in result.points
        ],
        "min_elevation_m": result.min_elevation_m,
        "max_elevation_m": result.max_elevation_m,
        "mean_elevation_m": round(result.mean_elevation_m, 1),
        "elevation_range_m": result.elevation_range_m,
    }


@router.get("/niirs")
async def get_niirs_table() -> dict[str, Any]:
    """Get the full NIIRS task-level interpretation table."""
    return {"levels": get_all_levels_summary()}


@router.get("/niirs/{level}")
async def get_niirs_level_detail(level: float) -> dict[str, Any]:
    """Get NIIRS level detail and achievable tasks."""
    info = get_niirs_level(level)
    return {
        "level": info.level,
        "category": info.category,
        "description": info.description,
        "tasks": info.tasks,
        "min_gsd_cm": info.min_gsd_cm,
        "typical_altitude_m": info.typical_altitude_m,
    }


@router.post("/model-chain")
async def get_model_chain_point(request: ModelChainPoint) -> dict[str, Any]:
    """Evaluate the full 17-model chain at a single operating point.

    Returns all intermediate values from every model for visualization.
    """
    from gorzen.schemas.twin_graph import VehicleTwin
    from gorzen.solver.envelope_solver import evaluate_point, _extract_params

    twin = VehicleTwin()
    params = _extract_params(twin)

    values = evaluate_point(params, request.speed_ms, request.altitude_m)

    # Group outputs by model stage
    stages = {
        "environment": {
            "headwind_ms": values.get("headwind_ms", 0),
            "crosswind_ms": values.get("crosswind_ms", 0),
            "air_density_kgm3": values.get("air_density_kgm3", 1.225),
            "temperature_at_alt_c": values.get("temperature_at_alt_c", 20),
            "turbulence_intensity": values.get("turbulence_intensity", 0),
        },
        "airframe": {
            "drag_N": round(values.get("drag_N", 0), 1),
            "wing_lift_N": round(values.get("wing_lift_N", 0), 1),
            "rotor_lift_required_N": round(values.get("rotor_lift_required_N", 0), 1),
            "power_parasitic_W": round(values.get("power_parasitic_W", 0), 1),
            "flight_mode_id": values.get("flight_mode_id", 0),
            "aero_feasible": values.get("aero_feasible", 0),
        },
        "ice_engine": {
            "engine_power_available_kw": round(values.get("engine_power_available_kw", 0), 2),
            "engine_power_required_kw": round(values.get("engine_power_required_kw", 0), 2),
            "fuel_flow_rate_g_hr": round(values.get("fuel_flow_rate_g_hr", 0), 1),
            "throttle_pct": round(values.get("throttle_pct", 0), 1),
            "engine_feasible": values.get("engine_feasible", 0),
        },
        "fuel_system": {
            "fuel_endurance_hr": round(values.get("fuel_endurance_hr", 0), 2),
            "fuel_range_nmi": round(values.get("fuel_range_nmi", 0), 1),
            "fuel_remaining_pct": round(values.get("fuel_remaining_pct", 0), 1),
            "fuel_feasible": values.get("fuel_feasible", 0),
        },
        "rotor": {
            "rotor_thrust_total_N": round(values.get("rotor_thrust_total_N", 0), 1),
            "rotor_power_total_W": round(values.get("rotor_power_total_W", 0), 1),
            "rotor_rpm": round(values.get("rotor_rpm", 0), 0),
            "rotor_efficiency": round(values.get("rotor_efficiency", 0), 3),
        },
        "motor": {
            "motor_current_A": round(values.get("motor_current_A", 0), 1),
            "motor_voltage_V": round(values.get("motor_voltage_V", 0), 1),
            "motor_power_elec_W": round(values.get("motor_power_elec_W", 0), 1),
            "motor_efficiency": round(values.get("motor_efficiency", 0), 3),
        },
        "esc": {
            "esc_loss_W": round(values.get("esc_loss_W", 0), 1),
            "total_electrical_power_W": round(values.get("total_electrical_power_W", 0), 1),
        },
        "battery": {
            "pack_voltage_V": round(values.get("pack_voltage_V", 0), 1),
            "terminal_voltage_V": round(values.get("terminal_voltage_V", 0), 1),
            "soc_pct": round(values.get("soc_pct", 0), 1),
            "endurance_min": round(values.get("endurance_min", 0), 1),
            "voltage_sag_V": round(values.get("voltage_sag_V", 0), 2),
            "battery_feasible": values.get("battery_feasible", 0),
        },
        "generator": {
            "generator_power_available_w": round(values.get("generator_power_available_w", 0), 1),
            "generator_charging_w": round(values.get("generator_charging_w", 0), 1),
            "hybrid_boost_active": values.get("hybrid_boost_active", 0),
        },
        "avionics": {
            "position_uncertainty_m": round(values.get("position_uncertainty_m", 0), 3),
            "geotag_error_m": round(values.get("geotag_error_m", 0), 3),
        },
        "compute": {
            "effective_latency_ms": round(values.get("effective_latency_ms", 0), 1),
            "effective_throughput_fps": round(values.get("effective_throughput_fps", 0), 1),
            "compute_power_W": round(values.get("compute_power_W", 0), 1),
        },
        "comms": {
            "link_margin_db": round(values.get("link_margin_db", 0), 1),
            "compression_quality_factor": round(values.get("compression_quality_factor", 0), 1),
            "achievable_bitrate_mbps": round(values.get("achievable_bitrate_mbps", 0), 1),
        },
        "gsd": {
            "gsd_cm_px": round(values.get("gsd_cm_px", 0), 2),
            "pixels_on_target": round(values.get("pixels_on_target", 0), 0),
            "footprint_w_m": round(values.get("footprint_w_m", 0), 1),
        },
        "motion_blur": {
            "smear_pixels": round(values.get("smear_pixels", 0), 2),
            "safe_inspection_speed_ms": round(values.get("safe_inspection_speed_ms", 0), 1),
            "motion_blur_feasible": values.get("motion_blur_feasible", 0),
        },
        "rolling_shutter": {
            "rs_total_distortion_px": round(values.get("rs_total_distortion_px", 0), 2),
            "rs_risk_score": round(values.get("rs_risk_score", 0), 3),
        },
        "image_quality": {
            "system_mtf": round(values.get("system_mtf", 0), 3),
            "snr_db": round(values.get("snr_db", 0), 1),
            "niirs_equivalent": round(values.get("niirs_equivalent", 0), 2),
            "image_utility_score": round(values.get("image_utility_score", 0), 3),
        },
        "identification": {
            "identification_confidence": round(values.get("identification_confidence", 0), 4),
            "blur_penalty": round(values.get("blur_penalty", 0), 3),
            "compression_penalty": round(values.get("compression_penalty", 0), 3),
            "pixel_density_factor": round(values.get("pixel_density_factor", 0), 3),
            "ood_risk": round(values.get("ood_risk", 0), 3),
        },
    }

    # NIIRS interpretation
    niirs = values.get("niirs_equivalent", 0)
    niirs_info = get_niirs_level(niirs)

    return {
        "speed_ms": request.speed_ms,
        "altitude_m": request.altitude_m,
        "stages": stages,
        "niirs_interpretation": {
            "level": niirs_info.level,
            "category": niirs_info.category,
            "description": niirs_info.description,
            "tasks": niirs_info.tasks,
        },
    }


# --- Model Recommendation ---


class ModelRecommendationRequest(BaseModel):
    gsd_cm: float = 1.0
    niirs: float = 6.0
    pixels_on_target: float = 50.0
    deployment_mode: str = "either"
    latency_budget_ms: float = 500.0
    defect_classes: list[str] = ["generic"]
    bandwidth_mbps: float = 10.0


@router.post("/model-recommendation")
async def model_recommendation(request: ModelRecommendationRequest) -> dict[str, Any]:
    """Recommend optimal VLM/CV model based on image quality and operational constraints."""
    mode_map = {
        "onboard": DeploymentMode.ONBOARD,
        "cloud": DeploymentMode.CLOUD,
        "either": DeploymentMode.EITHER,
        "rtn": DeploymentMode.CLOUD,
        "both": DeploymentMode.EITHER,
    }
    deploy_mode = mode_map.get(request.deployment_mode, DeploymentMode.EITHER)

    defect_map = {dc.value: dc for dc in DefectClass}
    defect_classes = [defect_map.get(d, DefectClass.GENERIC) for d in request.defect_classes]

    rec = recommend_model(
        gsd_cm=request.gsd_cm,
        niirs=request.niirs,
        pixels_on_target=request.pixels_on_target,
        deployment_mode=deploy_mode,
        latency_budget_ms=request.latency_budget_ms,
        defect_classes=defect_classes,
        bandwidth_mbps=request.bandwidth_mbps,
    )

    result: dict[str, Any] = {
        "primary_model": {
            "name": rec.primary_model.name,
            "family": rec.primary_model.family,
            "deployment": rec.primary_model.deployment.value,
            "latency_ms": rec.primary_model.latency_ms,
            "accuracy_mAP": rec.primary_model.accuracy_mAP,
            "edge_compatible": rec.primary_model.edge_compatible,
            "description": rec.primary_model.description,
        },
        "estimated_detection_probability": round(rec.estimated_detection_probability, 4),
        "estimated_false_positive_rate": round(rec.estimated_false_positive_rate, 4),
        "deployment_mode": rec.deployment_mode.value,
        "reasoning": rec.reasoning,
        "constraints_met": rec.constraints_met,
        "performance_notes": rec.performance_notes,
    }
    if rec.fallback_model:
        result["fallback_model"] = {
            "name": rec.fallback_model.name,
            "family": rec.fallback_model.family,
            "deployment": rec.fallback_model.deployment.value,
            "latency_ms": rec.fallback_model.latency_ms,
        }

    return result
