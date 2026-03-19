# Existing Modules & APIs for Gorzen Platform

Research on robust, existing libraries and APIs that can support the autonomous drone mission planning and hardware-performance validation platform.

---

## Already in Use (pyproject.toml)

| Package | Version | Use in Codebase |
|---------|---------|-----------------|
| **casadi** | ≥3.6 | `solver/trajectory.py` – NMPC/trajectory optimization |
| **pymavlink** | ≥2.4 | `calibration/telemetry_ingest.py` – MAVLink log parsing |
| **pyulog** | ≥1.0 | `calibration/telemetry_ingest.py` – PX4 ULog parsing |
| **scipy** | ≥1.14 | Models, UQ distributions |
| **numpy** | ≥1.26 | All numerical computation |

---

## Recommended Additions

### 1. MAVSDK-Python (Mission Planning & Control)

**Purpose:** Mission upload/download, waypoint control, telemetry – higher-level than raw pymavlink.

- **PyPI:** `pip install mavsdk`
- **Docs:** https://mavsdk.mavlink.io/main/en/python/
- **Mission API:** `upload_mission()`, `download_mission()`, `start_mission()`, `mission_progress()`, `set_return_to_launch_after_mission()`

**Integration:** Use for live mission execution and validation. Keep pymavlink for log parsing and low-level MAVLink. MAVSDK uses gRPC and embeds `mavsdk_server`.

```python
from mavsdk import System
drone = System()
await drone.connect()
# Upload validated mission from envelope planner
await drone.mission.upload_mission(mission_plan)
```

---

### 2. ODM GSD Formula (Photogrammetry)

**Purpose:** Standard GSD calculation used in OpenDroneMap.

- **Source:** https://github.com/OpenDroneMap/ODM/blob/master/opendm/gsd.py
- **Formula:** `GSD = (sensor_width × flight_height) / (focal_length × image_width)` (cm/px)

**Current state:** `gorzen/models/perception/gsd.py` already implements the same formula. ODM’s `calculate_gsd()` is a drop-in reference:

```python
# ODM formula (extract, no ODM dependency needed):
def calculate_gsd(sensor_width_mm, flight_height_m, focal_length_mm, image_width_px):
    if sensor_width_mm == 0:
        return None
    focal_ratio = focal_length_mm / sensor_width_mm
    return ((flight_height_m * 100) / image_width_px) / focal_ratio  # cm/px
```

**Recommendation:** Add a small `gorzen/photogrammetry/gsd.py` module that mirrors ODM’s API for consistency and future ODM integration. No new dependency.

---

### 3. Battery Life Estimator (bolddrones)

**Purpose:** Empirical flight-time model from logs: `1/T ≈ b0 + b1*payload + b2*v²`.

- **Repo:** https://github.com/bolddrones/battery-life-estimator
- **Model:** Calibrate from 5–10 flights; estimate total and remaining time from voltage.

**Integration:** Use for calibration of `gorzen/models/fuel_system.py` and `battery.py` from real flight logs. The estimator is a CLI tool; we can:

1. Add it as an optional dev dependency and call it for calibration.
2. Port the linear model into our codebase for runtime use.

```bash
# Calibrate from flight logs
python battery_life_estimator.py calibrate --csv flights.csv --out model.json
# Estimate for given conditions
python battery_life_estimator.py estimate-total --model model.json --payload-kg 0.6 --ground-speed-mps 10 --headwind-mps 2
```

---

### 4. OR-Tools (Routing & Coverage)

**Purpose:** VRP, coverage, and constrained routing (as in the research brief).

- **PyPI:** `pip install ortools`
- **Docs:** https://developers.google.com/optimization

**Use cases:**

- Discrete planner for coverage/corridor routing, time windows, battery swap.
- VRP for multi-drone mission assignment.

**Note:** OR-Tools minimizes distance/cost from a distance matrix. For energy-based costs (e.g., turning), precompute a custom cost matrix.

```python
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
# Standard VRP setup; adapt distance matrix for drone energy/turns
```

---

### 5. PyODM (OpenDroneMap Python SDK)

**Purpose:** Aerial image processing via NodeODM (orthophotos, DEMs, 3D models).

- **PyPI:** `pip install pyodm`
- **Docs:** https://pyodm.readthedocs.io/

**Use case:** Post-mission validation – run ODM on captured imagery to check GSD and quality. Not needed for real-time envelope computation.

---

### 6. Pint (Units)

**Purpose:** Physical units and conversions.

- **PyPI:** `pip install pint`
- **Already in dev deps:** `pint>=0.23`

**Use case:** Use in schemas and models for unit-safe calculations (m, m/s, kg, etc.) and to avoid unit mix-ups.

---

### 7. drone-flightplan (HOT OSM)

**Purpose:** Aerial mapping and inspection mission planning with GSD, overlap, and waypoint generation.

- **PyPI:** `pip install drone-flightplan` (Python ≥3.10)
- **Repo:** https://github.com/hotosm/drone-flightplan

**Features:**

- Waypoint generation from project area, altitude (AGL), GSD, overlap
- Parameter calculation (forward/side overlap, altitude, image intervals)
- DEM integration for terrain
- No-fly zone avoidance
- DJI WPML (.kmz) export

**Use case:** Coverage mission generation from our validated envelope (speed, altitude, GSD). Can feed waypoints into MAVSDK/pymavlink.

---

### 8. ORBIT (Bridge Inspection Toolkit)

**Purpose:** Constraint-aware routing for infrastructure inspection.

- **Repo:** https://github.com/ErToBar2/ORBIT

**Features:** Coverage planning, safety zones, GNSS-denied awareness, DJI Mavic 3E workflow.

**Use case:** Reference for inspection-specific routing; may be too specialized for general VTOL use.

---

## Summary: Integration Priorities

| Priority | Module | Action | Status |
|----------|--------|--------|--------|
| **High** | MAVSDK | Add for mission execution; keep pymavlink for logs | ✅ Integrated |
| **High** | drone-flightplan | Add for coverage waypoint generation from envelope (GSD, overlap) | ✅ Optional `[coverage]` |
| **High** | ODM GSD | Align `gsd.py` with ODM formula; optional thin wrapper | ✅ `gorzen.photogrammetry.gsd` |
| **Medium** | Battery-life-estimator | Use for calibration from flight logs | ✅ Ported to `gorzen.calibration.battery_life` |
| **Medium** | OR-Tools | Add for coverage/VRP planning | ✅ Integrated |
| **Low** | PyODM | Optional for post-flight validation | ✅ Optional `[odm]` |
| **Low** | Pint | Use in new code for unit safety | ✅ Main dependency |

---

## Implemented Integrations

- **MAVSDK** (`/execution`): `POST /upload`, `POST /start`, `GET /progress` for mission upload/start/progress
- **drone-flightplan** (`pip install gorzen[coverage]`): Coverage waypoints via `solver/coverage.py`; fallback to internal lawnmower when not installed
- **OR-Tools**: TSP route optimization in `solver/coverage.py` for waypoint ordering
- **Battery-life-estimator**: Ported to `calibration/battery_life.py`; endpoints `POST /calibration/battery/calibrate`, `POST /calibration/battery/estimate`
- **ODM GSD**: `gorzen.photogrammetry.gsd.calculate_gsd_odm()`
- **Pint**: `gorzen.units` for unit conversions
- **PyODM** (`pip install gorzen[odm]`): `POST /validation/odm/task` for post-flight orthophoto

---

## References

- MAVSDK Python: https://mavsdk.mavlink.io/main/en/python/
- MAVLink Mission Protocol: https://mavlink.io/en/services/mission.html
- ODM GSD: https://github.com/OpenDroneMap/ODM/blob/master/opendm/gsd.py
- Battery Life Estimator: https://github.com/bolddrones/battery-life-estimator
- OR-Tools: https://developers.google.com/optimization
- CasADi: https://web.casadi.org/
- Pix4D GSD guidance: https://support.pix4d.com/hc/en-us/articles/202560249
- drone-flightplan: https://github.com/hotosm/drone-flightplan
