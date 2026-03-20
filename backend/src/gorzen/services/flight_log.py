"""Flight log parser service.

Parses PX4 uLog files and extracts telemetry topics for comparison
against digital twin model predictions (calibration workflow).
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

try:
    from pyulog import ULog

    PYULOG_AVAILABLE = True
except ImportError:
    PYULOG_AVAILABLE = False
    ULog = None  # type: ignore


@dataclass
class LogSummary:
    """Summary of a parsed flight log."""

    filename: str
    duration_s: float
    start_timestamp: float
    topics: list[str]
    parameters: dict[str, Any]
    vehicle_uuid: str
    software_version: str
    hardware_version: str
    message_count: int


@dataclass
class TimeseriesData:
    """Time-indexed array of a single field."""

    topic: str
    field: str
    timestamps_s: list[float]
    values: list[float]
    unit: str
    min_val: float
    max_val: float
    mean_val: float


# Topics and fields most relevant for twin calibration
CALIBRATION_TOPICS = {
    "vehicle_attitude": {
        "fields": ["rollspeed", "pitchspeed", "yawspeed", "q[0]", "q[1]", "q[2]", "q[3]"],
        "unit": "rad/s",
    },
    "vehicle_local_position": {
        "fields": ["x", "y", "z", "vx", "vy", "vz"],
        "unit": "m",
    },
    "vehicle_global_position": {
        "fields": ["lat", "lon", "alt"],
        "unit": "deg/m",
    },
    "battery_status": {
        "fields": ["voltage_v", "current_a", "remaining", "temperature", "discharged_mah"],
        "unit": "V/A/%/°C/mAh",
    },
    "sensor_combined": {
        "fields": [
            "gyro_rad[0]", "gyro_rad[1]", "gyro_rad[2]",
            "accelerometer_m_s2[0]", "accelerometer_m_s2[1]", "accelerometer_m_s2[2]",
        ],
        "unit": "rad_s/m_s2",
    },
    "vehicle_air_data": {
        "fields": ["baro_alt_meter", "baro_temp_celcius", "baro_pressure_pa"],
        "unit": "m/°C/Pa",
    },
    "airspeed_validated": {
        "fields": ["true_airspeed_m_s", "indicated_airspeed_m_s"],
        "unit": "m/s",
    },
    "actuator_outputs": {
        "fields": ["output[0]", "output[1]", "output[2]", "output[3]"],
        "unit": "us",
    },
    "wind_estimate": {
        "fields": ["windspeed_north", "windspeed_east", "variance_north", "variance_east"],
        "unit": "m/s",
    },
    "estimator_status": {
        "fields": ["pos_horiz_accuracy", "pos_vert_accuracy"],
        "unit": "m",
    },
}


def parse_ulog(data: bytes, filename: str = "upload.ulg") -> LogSummary:
    """Parse a uLog file and return a summary."""
    if not PYULOG_AVAILABLE:
        raise RuntimeError("pyulog not installed")

    ulog = ULog(io.BytesIO(data))

    # Extract parameters
    params: dict[str, Any] = {}
    if hasattr(ulog, "initial_parameters") and ulog.initial_parameters:
        for p_name, p_val in ulog.initial_parameters.items():
            params[p_name] = p_val
    elif hasattr(ulog, "params"):
        params = dict(ulog.params)

    # Duration
    start = ulog.start_timestamp / 1e6 if ulog.start_timestamp else 0
    last = ulog.last_timestamp / 1e6 if ulog.last_timestamp else 0
    duration = last - start

    # Available topics
    topics = [d.name for d in ulog.data_list]

    # Vehicle info from messages
    vehicle_uuid = ""
    sw_version = ""
    hw_version = ""
    for msg in ulog.msg_info_dict.items() if hasattr(ulog, "msg_info_dict") else []:
        key, val = msg
        if "uuid" in key.lower():
            vehicle_uuid = str(val)
        elif "ver_sw" in key.lower():
            sw_version = str(val)
        elif "ver_hw" in key.lower():
            hw_version = str(val)

    return LogSummary(
        filename=filename,
        duration_s=round(duration, 1),
        start_timestamp=start,
        topics=topics,
        parameters=params,
        vehicle_uuid=vehicle_uuid,
        software_version=sw_version,
        hardware_version=hw_version,
        message_count=sum(len(d.data["timestamp"]) for d in ulog.data_list if "timestamp" in d.data),
    )


def extract_timeseries(
    data: bytes,
    topic: str,
    field: str,
    downsample: int = 500,
) -> TimeseriesData:
    """Extract a single timeseries from a uLog file."""
    if not PYULOG_AVAILABLE:
        raise RuntimeError("pyulog not installed")

    ulog = ULog(io.BytesIO(data))

    # Find the topic
    matched = [d for d in ulog.data_list if d.name == topic]
    if not matched:
        raise ValueError(f"Topic '{topic}' not found. Available: {[d.name for d in ulog.data_list]}")

    d = matched[0]
    if field not in d.data:
        raise ValueError(f"Field '{field}' not in topic '{topic}'. Available: {list(d.data.keys())}")

    timestamps = d.data["timestamp"] / 1e6  # microseconds to seconds
    values = np.array(d.data[field], dtype=float)

    # Normalize timestamps to start at 0
    t0 = timestamps[0]
    timestamps = timestamps - t0

    # Downsample for frontend display
    n = len(values)
    if n > downsample:
        step = n // downsample
        timestamps = timestamps[::step]
        values = values[::step]

    unit = CALIBRATION_TOPICS.get(topic, {}).get("unit", "")

    return TimeseriesData(
        topic=topic,
        field=field,
        timestamps_s=[round(float(t), 3) for t in timestamps],
        values=[round(float(v), 4) for v in values],
        unit=unit,
        min_val=round(float(np.min(values)), 4),
        max_val=round(float(np.max(values)), 4),
        mean_val=round(float(np.mean(values)), 4),
    )


def extract_calibration_data(data: bytes) -> dict[str, Any]:
    """Extract all calibration-relevant data from a uLog for twin comparison.

    Returns a structured dict with battery, airspeed, wind, position data
    ready for overlay against twin model predictions.
    """
    if not PYULOG_AVAILABLE:
        raise RuntimeError("pyulog not installed")

    ulog = ULog(io.BytesIO(data))
    result: dict[str, Any] = {"topics_found": [], "data": {}}

    for d in ulog.data_list:
        if d.name not in CALIBRATION_TOPICS:
            continue

        result["topics_found"].append(d.name)
        topic_data: dict[str, Any] = {}

        timestamps = d.data["timestamp"] / 1e6
        t0 = timestamps[0]
        timestamps = timestamps - t0

        # Downsample to 500 points max
        n = len(timestamps)
        step = max(1, n // 500)

        topic_data["timestamps_s"] = [round(float(t), 3) for t in timestamps[::step]]

        for field_name in CALIBRATION_TOPICS[d.name]["fields"]:
            if field_name in d.data:
                vals = np.array(d.data[field_name], dtype=float)[::step]
                topic_data[field_name] = [round(float(v), 4) for v in vals]

        result["data"][d.name] = topic_data

    # Extract PX4 parameters for twin mapping
    params: dict[str, Any] = {}
    if hasattr(ulog, "initial_parameters") and ulog.initial_parameters:
        for p_name, p_val in ulog.initial_parameters.items():
            params[p_name] = p_val
    result["px4_parameters"] = params

    # Compute flight statistics
    if "battery_status" in result["data"]:
        batt = result["data"]["battery_status"]
        if "voltage_v" in batt:
            voltages = batt["voltage_v"]
            result["stats"] = {
                "battery_start_v": voltages[0] if voltages else 0,
                "battery_end_v": voltages[-1] if voltages else 0,
                "battery_min_v": min(voltages) if voltages else 0,
                "flight_duration_s": round(batt["timestamps_s"][-1], 1) if batt["timestamps_s"] else 0,
            }

    return result


def get_available_topics() -> dict[str, Any]:
    """Return the list of calibration topics and their fields."""
    return {
        topic: {
            "fields": info["fields"],
            "unit": info["unit"],
            "description": f"PX4 {topic} telemetry data",
        }
        for topic, info in CALIBRATION_TOPICS.items()
    }
