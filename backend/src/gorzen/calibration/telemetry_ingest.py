"""Telemetry ingest: ULog, DataFlash, DroneCAN parsers, canonical schema.

Normalizes heterogeneous UAV log formats into a unified time-synced schema.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class TelemetryRecord:
    """A single time-synced telemetry record in canonical form."""

    timestamp_us: int
    topic: str
    fields: dict[str, float | int | str] = field(default_factory=dict)


@dataclass
class TelemetryDataset:
    """A collection of telemetry records from a single flight."""

    source_format: str  # "ulog", "dataflash", "dronecan"
    vehicle_id: str = ""
    firmware_version: str = ""
    records: list[TelemetryRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    topics: set[str] = field(default_factory=set)

    def get_topic_series(self, topic: str, field_name: str) -> tuple[np.ndarray, np.ndarray]:
        """Extract a time series for a specific topic/field."""
        times = []
        values = []
        for r in self.records:
            if r.topic == topic and field_name in r.fields:
                times.append(r.timestamp_us / 1e6)
                values.append(float(r.fields[field_name]))
        return np.array(times), np.array(values)


class ULogParser:
    """Parser for PX4 ULog format.

    ULog is self-describing: it includes message format definitions alongside data,
    enabling automated schema extraction.
    """

    HEADER_MAGIC = b"ULog\x01\x12\x35"

    def parse(self, filepath: str | Path) -> TelemetryDataset:
        dataset = TelemetryDataset(source_format="ulog")
        path = Path(filepath)

        if not path.exists():
            return dataset

        try:
            import pyulog
            ulog = pyulog.ULog(str(path))

            dataset.metadata = {
                "start_timestamp": ulog.start_timestamp,
                "msg_info_dict": {k: str(v) for k, v in ulog.msg_info_dict.items()},
            }

            if "sys_name" in ulog.msg_info_dict:
                dataset.vehicle_id = str(ulog.msg_info_dict["sys_name"])
            if "ver_sw" in ulog.msg_info_dict:
                dataset.firmware_version = str(ulog.msg_info_dict["ver_sw"])

            for d in ulog.data_list:
                topic = d.name
                dataset.topics.add(topic)

                timestamps = d.data.get("timestamp", [])
                field_names = [k for k in d.data.keys() if k != "timestamp"]

                for i in range(len(timestamps)):
                    fields = {}
                    for fn in field_names:
                        val = d.data[fn][i]
                        fields[fn] = float(val) if isinstance(val, (int, float, np.number)) else str(val)
                    dataset.records.append(TelemetryRecord(
                        timestamp_us=int(timestamps[i]),
                        topic=topic,
                        fields=fields,
                    ))
        except ImportError:
            dataset.metadata["error"] = "pyulog not installed"
        except Exception as e:
            dataset.metadata["error"] = str(e)

        return dataset


class DataFlashParser:
    """Parser for ArduPilot DataFlash/BIN logs."""

    def parse(self, filepath: str | Path) -> TelemetryDataset:
        dataset = TelemetryDataset(source_format="dataflash")
        path = Path(filepath)

        if not path.exists():
            return dataset

        try:
            from pymavlink import mavutil
            mlog = mavutil.mavlink_connection(str(path))

            while True:
                msg = mlog.recv_match(blocking=False)
                if msg is None:
                    break
                msg_type = msg.get_type()
                if msg_type == "BAD_DATA":
                    continue

                dataset.topics.add(msg_type)
                fields = {}
                if hasattr(msg, "_fieldnames"):
                    for fname in msg._fieldnames:
                        val = getattr(msg, fname, None)
                        if val is not None:
                            fields[fname] = float(val) if isinstance(val, (int, float)) else str(val)

                timestamp = getattr(msg, "TimeUS", 0) or getattr(msg, "time_usec", 0) or 0
                dataset.records.append(TelemetryRecord(
                    timestamp_us=int(timestamp),
                    topic=msg_type,
                    fields=fields,
                ))
        except ImportError:
            dataset.metadata["error"] = "pymavlink not installed"
        except Exception as e:
            dataset.metadata["error"] = str(e)

        return dataset


class DroneCAN_ESC_Parser:
    """Parser for DroneCAN ESC telemetry data.

    Extracts voltage, current, temperature, RPM, and error counters.
    """

    CANONICAL_FIELDS = [
        "voltage_v", "current_a", "temperature_c",
        "rpm", "power_rating_pct", "error_count",
    ]

    def parse_from_ulog(self, dataset: TelemetryDataset) -> list[TelemetryRecord]:
        """Extract ESC telemetry records from a ULog dataset."""
        esc_records: list[TelemetryRecord] = []

        for r in dataset.records:
            if "esc_status" in r.topic.lower() or "actuator_outputs" in r.topic.lower():
                canonical = {}
                for orig, canon in [
                    ("esc_voltage", "voltage_v"),
                    ("esc_current", "current_a"),
                    ("esc_temperature", "temperature_c"),
                    ("esc_rpm", "rpm"),
                    ("voltage", "voltage_v"),
                    ("current", "current_a"),
                ]:
                    if orig in r.fields:
                        canonical[canon] = r.fields[orig]

                if canonical:
                    esc_records.append(TelemetryRecord(
                        timestamp_us=r.timestamp_us,
                        topic="esc_telemetry",
                        fields=canonical,
                    ))

        return esc_records


def ingest_log(filepath: str | Path) -> TelemetryDataset:
    """Auto-detect log format and parse."""
    path = Path(filepath)
    suffix = path.suffix.lower()

    if suffix == ".ulg":
        return ULogParser().parse(path)
    elif suffix in (".bin", ".log"):
        return DataFlashParser().parse(path)
    else:
        # Try ULog first, then DataFlash
        try:
            ds = ULogParser().parse(path)
            if ds.records:
                return ds
        except Exception:
            pass
        return DataFlashParser().parse(path)
