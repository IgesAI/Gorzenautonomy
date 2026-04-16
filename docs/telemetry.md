# Gorzen Telemetry Layer

This document describes the MAVLink telemetry stack used by the Gorzen
backend for the Cube Black / Cube Orange / Cube Red autopilots running
**PX4 Pro** on the VTOL quad-plane. It is the source of truth for which
messages we request from the FC, which fields we surface to the UI, and
which connection URIs the operator supplies.

> **Heads-up.** The telemetry layer is specifically tuned for PX4 Pro on
> Cube hardware. An experimental ArduPilot-Plane/QuadPlane path exists
> (mode decoding, parameter round-trip) but has not been validated on
> flight hardware; use at your own risk and ensure the FC advertises
> `MAV_AUTOPILOT_ARDUPILOTMEGA` in `HEARTBEAT` so the right decoder is
> selected.

## Connection URIs

| Transport | Example URI | Notes |
|-----------|-------------|-------|
| Cube USB (CDC) | `COM7:115200` (Win) / `/dev/ttyACM0:115200` (Linux) | Baud is cosmetic — USB CDC ignores it, but we pass `115200` for consistency. |
| Holybro SiK telemetry radio | `COM8:57600` | 57 600 baud is the radio default; both ends must match. |
| RFD 900x long-range | `/dev/ttyUSB0:57600` | Use `/serial://...:57600` or `:115200` depending on how you configured the modem. |
| Herelink air unit | `udp://:14552` | Herelink presents a MAVLink router on UDP 14552; supply the IP of the ground station if not local. |
| PX4 SITL | `udp://:14540` | Default for jMAVSim / Gazebo standard_vtol. |

The URI is parsed by `_parse_address` in
[`mavlink_telemetry.py`](../backend/src/gorzen/services/mavlink_telemetry.py).
Unrecognised URIs fall back to serial at 57 600 baud, which is the most
common setting for SiK radios.

## Message rate plan

Every connection requests per-message intervals via
`MAV_CMD_SET_MESSAGE_INTERVAL` (PX4 ≥ 1.13 is the primary path;
`REQUEST_DATA_STREAM` is still sent as a legacy fallback for older
firmware). Two profiles are shipped:

| Message | Default (Hz) | Low-bandwidth (Hz) | Purpose |
|---|---|---|---|
| `HEARTBEAT` | 1 | 1 | Link alive, vehicle type, armed state |
| `SYS_STATUS` | 2 | 1 | Battery V/I, sensor-health bitmask |
| `GPS_RAW_INT` | 2 | 1 | Fix type, sat count, HDOP |
| `ATTITUDE` | 20 | 4 | Roll / pitch / yaw |
| `GLOBAL_POSITION_INT` | 10 | 2 | Lat / lon / MSL & relative altitude, NED velocity |
| `VFR_HUD` | 10 | 2 | Airspeed, ground speed, climb |
| `BATTERY_STATUS` | 2 | 1 | Cell temperatures, coulomb count |
| `EXTENDED_SYS_STATE` | 2 | 1 | **VTOL state** (MC / FW / TRANSITION) + landed state |
| `WIND_COV` | 1 | 0.5 | PX4 wind estimate (m/s NED components) |
| `RC_CHANNELS` | 2 | 1 | RC RSSI (0-254) |
| `STATUSTEXT` | 5 | 2 | Pre-arm failure reasons, warnings |

Switching to the low-bandwidth profile is automatic for serial links and
selectable via the `link_profile` field on `POST /telemetry/connect`.

## PX4 custom-mode decoding

`HEARTBEAT.custom_mode` packs the PX4 main / sub mode into the upper two
bytes:

```
bits 24-31  sub_mode   (AUTO.*, optional)
bits 16-23  main_mode  (MANUAL, POSCTL, AUTO, ...)
bits  0-15  unused
```

Decoded via `decode_px4_custom_mode()`; the full map lives in
`PX4_MAIN_MODES` / `PX4_AUTO_SUBMODES`. VTOL-specific sub-modes in play:

| sub_mode | Label |
|---|---|
| 2  | `AUTO.TAKEOFF` |
| 6  | `AUTO.LAND` |
| 10 | `AUTO.VTOL_TAKEOFF` |
| 11 | `AUTO.VTOL_LAND` |

The ArduPilot branch still exists (driven by `HEARTBEAT.autopilot ==
MAV_AUTOPILOT_ARDUPILOTMEGA`) but is only exercised in bench tests.

## VTOL state tracking

`EXTENDED_SYS_STATE.vtol_state` (MAVLink enum `MAV_VTOL_STATE`) drives
the `TelemetryFrame.vtol_state` field:

| Value | Meaning |
|---|---|
| 0 | UNDEFINED |
| 1 | TRANSITION_TO_FW |
| 2 | TRANSITION_TO_MC |
| 3 | MC (multirotor) |
| 4 | FW (fixed-wing) |

`TelemetryFrame.landed_state` (`MAV_LANDED_STATE`) is the authoritative
in-air indicator — we no longer trust an `altitude > 0.5 m` heuristic.

## Parameter protocol

* `read_param(id)` returns `(value, MAV_PARAM_TYPE)` so writes can round-trip
  INT32 / REAL32 parameters correctly. Sending a PX4 INT32 like
  `BAT1_N_CELLS` as REAL32 silently fails on PX4.
* `read_all_params()` pulls the full parameter table via
  `PARAM_REQUEST_LIST` with a polite timeout (~40 s of silence) that
  accommodates slow SiK radios. A MAVFTP bulk fast-path is on the
  roadmap.
* `write_param(id, value)` auto-probes the FC's native parameter type by
  reading once before writing when the caller does not pass `param_type`.
* Every write is recorded in the `parameter_audit` table (see the Phase 3g
  migration): who, when, old value, new value, success.

## Geofence

`upload_geofence_px4(inclusions, exclusions)` uploads a PX4 fence
mission (`MAV_MISSION_TYPE_FENCE`) using `MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION`
(5001) and `MAV_CMD_NAV_FENCE_POLYGON_VERTEX_EXCLUSION` (5002). The FC's
behaviour (warn / rtl / land) is controlled by the `GF_ACTION` parameter;
set it with the normal parameter-sync flow before uploading the fence.

## On-board log download

`list_logs()` enumerates the FC's log store via `LOG_REQUEST_LIST`;
`download_log(id)` pulls the raw uLog bytes via `LOG_REQUEST_DATA` in 90-
byte chunks (the MAVLink payload limit). Useful in the field when the
vehicle hasn't been carried back to a workstation for USB log-dump.

## Pre-flight checklist

`POST /execution/upload` runs the consolidated pre-flight checklist
(`services/preflight.py`) before talking to MAVSDK. Red blocking checks
return HTTP 412 Precondition Failed with a structured list of failures:

| Check | Blocking? |
|---|---|
| `flight_controller_link` | Yes |
| `gps_fix_3d_or_better` | Yes |
| `sensors_healthy` (SYS_STATUS bitmask) | Yes |
| `battery_above_reserve` (≥ 30 %) | Yes |
| `vtol_ready_to_takeoff` (vtol_state == MC) | Yes |
| `no_recent_prearm_failures` | Yes when present |
| `mission_validation` | Yes |
| `airspace_clear` (no controlled / restricted overlap) | Yes |
| `energy_headroom` (reserve ≥ 10 %) | Yes |
| `sora_ground_risk` | Yes when GRC ≥ 5 |
| `notams_clear` | No (yellow only) |
| `autopilot_identified` | No |

Set `bypass_preflight=true` on the upload request only in documented
dev/test scenarios — the bypass is audit-logged.

## Metrics

When `GORZEN_METRICS_ENABLED=true` the backend exposes `/metrics` in
Prometheus text format. Built-in series:

* `gorzen_http_requests_total{method, path, status}`
* `gorzen_http_request_duration_seconds_*{method, path}`
* `gorzen_telemetry_messages_total{type}`
* `gorzen_telemetry_link_connected` (0/1 gauge)
* `gorzen_param_writes_total{outcome}`
* `gorzen_preflight_results_total{status}`

`GORZEN_OTEL_EXPORTER_OTLP_ENDPOINT` turns on OpenTelemetry tracing with
OTLP-HTTP (soft dependency on `opentelemetry-*` packages).

## Remote ID

FAA Part 89 / ASTM F3411 Remote ID is handled by
`services/airspace.OpenDroneIdEmitter`. Broadcasting is gated on
`RemoteIdConfig.enabled=True` — the backend never emits Remote ID
messages automatically. Wire the `sender` callback to
`telemetry_service._conn.mav.open_drone_id_*_send()` when you're ready
to fly under Part 89.

## References

* PX4 `custom_mode` layout: `src/modules/commander/px4_custom_mode.h`.
* MAVLink common message set: https://mavlink.io/en/messages/common.html
* FAA SORA v2: https://jarus-rpas.org/ (annex on ground-risk classes).
* ASTM F3411-19 Remote ID standard.
