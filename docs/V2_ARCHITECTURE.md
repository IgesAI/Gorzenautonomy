# Gorzenautonomy v2 Architecture

Concrete service topology, message flow, and module ownership for the
self-validating autonomy planning system.

## Design Thesis

v1 is a **smart calculator**: twin config in → feasibility report out.
v2 closes the loop: predict → fly/simulate → record → compare → update confidence.

The stack: **PX4 · ROS 2 · uXRCE-DDS · MAVSDK · Gazebo Harmonic · rosbag2**.
Isaac Sim added later for perception/HIL. Aerostack2 behavior concepts borrowed
for mission behavior abstraction, not adopted as a framework dependency.

---

## Repository Layout

```
gorzenautonomy/
├── backend/                    # gorzen-planner  (EXISTING — enhanced)
│   └── src/gorzen/
│       ├── api/                # FastAPI REST + WS (unchanged)
│       ├── calibration/        # Bayesian calibration (unchanged)
│       ├── db/                 # SQLAlchemy models (new: validation_runs table)
│       ├── models/             # 17-model physics chain (unchanged)
│       ├── schemas/            # Pydantic (new: prediction + validation schemas)
│       ├── services/           # MAVLink, MAVSDK, flight log (refined)
│       ├── solver/             # Envelope, mission planner (unchanged)
│       ├── uq/                 # Monte Carlo, PCE (unchanged)
│       └── validation/         # Parameter audits + NEW prediction export
│
├── ros/                        # NEW — all ROS 2 packages
│   ├── gorzen_msgs/            # Custom .msg / .srv definitions
│   ├── gorzen_bridge/          # Gorzen ↔ ROS 2 bridge node
│   ├── gorzen_executor/        # MAVSDK mission + offboard node
│   ├── gorzen_validator/       # Post-flight prediction-vs-actual
│   ├── gorzen_recorder/        # rosbag2 recording orchestration
│   └── gorzen_bringup/         # Launch files + configs
│
├── sim/                        # NEW — simulation configs
│   ├── gazebo/                 # Gazebo Harmonic worlds + models
│   └── isaac/                  # Future: Isaac Sim configs
│
├── frontend/                   # React UI (EXISTING — enhanced)
│   └── src/
│       ├── components/
│       │   ├── validation/     # NEW: predicted-vs-actual views
│       │   ├── simulation/     # NEW: sim launch + monitor
│       │   └── ...             # existing components unchanged
│       └── ...
│
├── docker-compose.yml          # Updated with ROS 2 services
├── docker-compose.sim.yml      # Simulation-specific overlay
└── docs/
    └── V2_ARCHITECTURE.md      # This file
```

---

## Services

### 1. gorzen-planner (backend/) — Decision Engine

**Owner:** Existing FastAPI backend. No ROS 2 dependency in this process.

**Responsibilities:**
- Twin configuration CRUD and versioning
- 17-model physics chain evaluation
- Envelope solver + UQ propagation
- Mission feasibility, coverage optimization
- Prediction export (new): before each flight/sim, persist expected outcomes
- Validation ingestion (new): accept post-flight comparison reports
- Calibration update: use validation deltas to refine Bayesian posteriors
- REST + WebSocket API for frontend

**New endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/predictions/{mission_id}` | Store pre-flight predicted outcomes |
| GET | `/predictions/{mission_id}` | Retrieve predictions for validator |
| POST | `/validations/{mission_id}` | Ingest post-flight validation report |
| GET | `/validations/{mission_id}` | Retrieve validation comparison |
| GET | `/validations/{mission_id}/drift` | Model drift analysis |
| POST | `/simulations/launch` | Trigger Gazebo SITL session |
| GET | `/simulations/status` | Running simulation state |

**New DB tables:**

```sql
CREATE TABLE prediction_sets (
    id            UUID PRIMARY KEY,
    mission_id    UUID NOT NULL,
    twin_id       UUID NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now(),
    predictions   JSONB NOT NULL,  -- endurance, blur, MCP, per-waypoint
    envelope_hash TEXT,            -- hash of envelope config used
    model_version TEXT
);

CREATE TABLE validation_runs (
    id              UUID PRIMARY KEY,
    prediction_id   UUID REFERENCES prediction_sets(id),
    mission_id      UUID NOT NULL,
    completed_at    TIMESTAMPTZ DEFAULT now(),
    bag_path        TEXT,                    -- rosbag2 file path
    actuals         JSONB NOT NULL,          -- measured outcomes
    deltas          JSONB NOT NULL,          -- predicted − actual
    confidence_update JSONB,                 -- posterior adjustments
    source          TEXT CHECK (source IN ('flight','simulation'))
);
```

**What stays the same:** Every existing API route, the full model chain, UQ,
calibration, catalog, audit. The planner does not import `rclpy`. It talks to
the ROS layer exclusively through REST calls and shared PostgreSQL.

---

### 2. gorzen-bridge (ros/gorzen_bridge/) — ROS 2 ↔ Planner Bridge

**Owner:** New ROS 2 Python package. The only service that speaks both REST
and ROS 2.

**Responsibilities:**
- Poll gorzen-planner REST for new missions/predictions
- Publish mission plans and predictions to ROS 2 topics
- Subscribe to PX4 telemetry topics (from uXRCE-DDS) and forward frames
  to gorzen-planner via HTTP POST or WebSocket
- Translate between Gorzen schemas and ROS 2 message types
- Manage lifecycle (connect, arm checks, mission handoff to executor)

**ROS 2 interface:**

| Direction | Topic | Type | QoS | Purpose |
|-----------|-------|------|-----|---------|
| PUB | `/gorzen/mission/plan` | `gorzen_msgs/MissionPlan` | Reliable | Planned waypoints + constraints |
| PUB | `/gorzen/mission/predictions` | `gorzen_msgs/MissionPredictions` | Reliable | Expected outcomes per leg |
| PUB | `/gorzen/telemetry/frame` | `gorzen_msgs/TelemetryFrame` | BestEffort | Bridged to frontend WS |
| SUB | `/fmu/out/vehicle_odometry` | `px4_msgs/VehicleOdometry` | BestEffort* | Position + velocity |
| SUB | `/fmu/out/battery_status` | `px4_msgs/BatteryStatus` | BestEffort* | SoC, voltage, current |
| SUB | `/fmu/out/vehicle_status` | `px4_msgs/VehicleStatus` | BestEffort* | Arming, nav state |
| SUB | `/fmu/out/vehicle_gps_position` | `px4_msgs/SensorGps` | BestEffort* | GPS fix + coords |
| SUB | `/gorzen/validation/result` | `gorzen_msgs/ValidationResult` | Reliable | From validator node |

*PX4's Micro XRCE-DDS QoS: `BEST_EFFORT` reliability, `VOLATILE` durability,
depth = 1 for high-rate topics. Subscribers **must** match this — using ROS 2
defaults (`RELIABLE` / `TRANSIENT_LOCAL`) will cause silent drops.

**Key implementation detail:** Uses `CompatibleQoSProfile` helper that mirrors
PX4's QoS for all `/fmu/*` subscriptions:

```python
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

PX4_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)
```

---

### 3. gorzen-executor (ros/gorzen_executor/) — Vehicle Command Layer

**Owner:** New ROS 2 Python package. Wraps MAVSDK as a ROS 2 node.

**Responsibilities:**
- Mission upload/download via `mavsdk.MissionRaw` (for QGC-compatible items)
- Mission start/pause/resume/cancel
- Offboard control with automatic 20 Hz setpoint streaming
  (MAVSDK's Offboard API handles the heartbeat; PX4 requires ≥2 Hz)
- Arm/disarm, takeoff/land, RTL commands
- Forward mission progress to ROS 2 topics
- Health/pre-arm check publication

**ROS 2 interface:**

| Direction | Topic/Service | Type | Purpose |
|-----------|--------------|------|---------|
| SUB | `/gorzen/mission/plan` | `gorzen_msgs/MissionPlan` | Receive mission to upload |
| PUB | `/gorzen/mission/progress` | `gorzen_msgs/MissionProgress` | Current waypoint index, ETA |
| PUB | `/gorzen/mission/status` | `gorzen_msgs/MissionStatus` | State machine: uploading/running/paused/done/failed |
| PUB | `/gorzen/health/preflight` | `gorzen_msgs/PreflightHealth` | GPS, gyro, mag, battery checks |
| SRV | `/gorzen/cmd/upload_mission` | `gorzen_msgs/UploadMission` | Trigger MAVSDK MissionRaw upload |
| SRV | `/gorzen/cmd/start_mission` | `gorzen_msgs/Trigger` | Arm + start |
| SRV | `/gorzen/cmd/offboard_setpoint` | `gorzen_msgs/OffboardSetpoint` | Push position/velocity/attitude setpoint |
| SRV | `/gorzen/cmd/rtl` | `std_srvs/Trigger` | Return to launch |

**MAVSDK version constraint:** MAVSDK Python ≥ 2.0, connecting to
`mavsdk_server` on the companion or via gRPC to `localhost:50051`.
Does **not** conflict with uXRCE-DDS because MAVSDK uses MAVLink (UDP 14540)
while uXRCE-DDS uses its own serial/UDP transport (typically UDP 8888).

---

### 4. gorzen-recorder (ros/gorzen_recorder/) — Canonical Truth Recorder

**Owner:** New ROS 2 Python package (thin wrapper around rosbag2 API).

**Responsibilities:**
- Start/stop recording on command (ROS 2 service calls)
- Record all `/fmu/out/*`, `/gorzen/*` topics by default
- Tag recordings with mission_id and prediction_id
- Store bags to `GORZEN_OBJECT_STORE_PATH/bags/`
- Notify gorzen-validator when a recording is finalized

**ROS 2 interface:**

| Direction | Topic/Service | Type | Purpose |
|-----------|--------------|------|---------|
| SRV | `/gorzen/recording/start` | `gorzen_msgs/StartRecording` | Begin bag with mission metadata |
| SRV | `/gorzen/recording/stop` | `gorzen_msgs/StopRecording` | Finalize bag, return path |
| PUB | `/gorzen/recording/status` | `gorzen_msgs/RecordingStatus` | Active, bag size, duration |

**Storage format:** SQLite3 storage plugin (rosbag2 default), ZSTD compression.
One bag per mission execution. Naming: `{mission_id}_{timestamp}.db3`.

---

### 5. gorzen-validator (ros/gorzen_validator/) — Prediction vs Observation

**Owner:** New ROS 2 Python package (or standalone Python script that reads bags).

This is the **highest-value new component** — it closes the decision-to-reality
loop.

**Responsibilities:**
- Read a completed rosbag2 recording
- Extract actual outcomes from recorded topics
- Fetch predicted outcomes from gorzen-planner REST
- Compute deltas across all prediction dimensions
- Publish validation result to ROS 2 topic
- POST validation report to gorzen-planner for persistence and calibration update

**Validation dimensions:**

| Predicted (from planner) | Actual (from bag) | Source topic |
|--------------------------|-------------------|-------------|
| Endurance (minutes) | Time to battery threshold | `/fmu/out/battery_status` |
| Energy consumed (Wh) | Integrated V×I over flight | `/fmu/out/battery_status` |
| Ground speed profile | Actual speed per leg | `/fmu/out/vehicle_odometry` |
| Motion blur (pixels) | Measured blur metric* | `/gorzen/perception/blur` |
| GSD achieved (cm/px) | Computed from altitude + camera | `/fmu/out/vehicle_odometry` |
| Mission completion prob | Binary: completed all WPs? | `/gorzen/mission/status` |
| Per-waypoint arrival time | Actual timestamps at WPs | `/gorzen/mission/progress` |
| Altitude hold accuracy | Std dev of altitude error | `/fmu/out/vehicle_odometry` |

*Blur metric from onboard or post-processed imagery — available when perception
pipeline is active. Gracefully skipped otherwise.

**Output schema (posted to planner):**

```json
{
  "mission_id": "uuid",
  "prediction_id": "uuid",
  "source": "simulation",
  "actuals": {
    "endurance_min": 22.3,
    "energy_wh": 187.4,
    "completion": true,
    "waypoints_reached": 12,
    "waypoints_total": 12,
    "mean_groundspeed_ms": 8.7,
    "altitude_std_m": 0.42,
    "max_blur_px": 1.8,
    "mean_gsd_cm": 2.1
  },
  "deltas": {
    "endurance_min": -1.7,
    "energy_wh": +12.4,
    "mean_groundspeed_ms": -0.3,
    "max_blur_px": +0.4
  },
  "confidence_update": {
    "drag_coefficient_bias": +0.03,
    "battery_capacity_effective_pct": -2.1,
    "wind_model_rmse_ms": 0.8
  }
}
```

---

### 6. gorzen-bringup (ros/gorzen_bringup/) — Launch Orchestration

**Owner:** New ROS 2 package (launch files only, no nodes).

**Launch configurations:**

| Launch file | What it starts |
|-------------|---------------|
| `sitl.launch.py` | PX4 SITL + Gazebo Harmonic + uXRCE-DDS agent + all gorzen nodes |
| `hardware.launch.py` | uXRCE-DDS agent + all gorzen nodes (PX4 on real FCU) |
| `replay.launch.py` | rosbag2 play + gorzen-validator (no vehicle) |
| `bridge_only.launch.py` | gorzen-bridge only (for gradual migration) |

---

## Message Flow

### A. Mission Planning → Execution

```
┌────────────┐    REST     ┌────────────────┐   ROS 2 topic    ┌─────────────────┐
│  Frontend   │ ─────────► │ gorzen-planner  │ ───(via bridge)─► │ gorzen-executor  │
│  (React)    │            │ (FastAPI)       │                   │ (MAVSDK node)    │
└────────────┘            └────────────────┘                   └────────┬────────┘
                                │                                       │
                          POST /predictions                      MAVSDK gRPC
                                │                                       │
                                ▼                                       ▼
                          ┌──────────┐                           ┌──────────┐
                          │ Postgres │                           │   PX4    │
                          └──────────┘                           │ (SITL/HW)│
                                                                 └──────────┘
```

**Step-by-step:**

1. User plans mission in frontend → `POST /mission-plan/validate` + `POST /mission-plan/drone/upload`
2. gorzen-planner computes feasibility, stores prediction set → `POST /predictions/{mission_id}`
3. gorzen-bridge polls or receives webhook, publishes `MissionPlan` + `MissionPredictions` to ROS 2
4. gorzen-executor subscribes, calls `mavsdk.MissionRaw.upload_mission()`
5. User triggers start → gorzen-executor arms + starts mission via MAVSDK
6. gorzen-recorder begins rosbag2 recording

### B. In-Flight Telemetry

```
┌──────────┐  uXRCE-DDS  ┌──────────────┐  ROS 2 topics  ┌───────────────┐  REST/WS  ┌────────────┐
│   PX4    │ ───────────► │ XRCE-DDS     │ ──────────────► │ gorzen-bridge │ ────────► │  gorzen-   │
│          │              │ Agent (v2.x)  │                │               │           │  planner   │
└──────────┘              └──────────────┘                └───────────────┘           └─────┬──────┘
                                                                 │                          │
                                                           rosbag2 record              WebSocket
                                                                 │                          │
                                                                 ▼                          ▼
                                                          ┌──────────────┐          ┌────────────┐
                                                          │ gorzen-      │          │  Frontend   │
                                                          │ recorder     │          │  (React)    │
                                                          └──────────────┘          └────────────┘
```

**QoS chain:** PX4 XRCE-DDS client → Agent (v2.4.x, NOT v3.x) → ROS 2 DDS →
gorzen-bridge (matching `BEST_EFFORT` / `VOLATILE` / depth 1). The bridge
aggregates into `TelemetryFrame` and POSTs or streams to the planner, which
forwards to the frontend via existing WebSocket at `/telemetry/ws`.

### C. Post-Flight Validation

```
┌──────────────┐  read bag  ┌─────────────────┐  GET /predictions  ┌────────────────┐
│ gorzen-      │ ──────────► │ gorzen-validator │ ─────────────────► │ gorzen-planner  │
│ recorder     │             │                 │                    │                │
│ (bag file)   │             │                 │ POST /validations  │                │
└──────────────┘             │  compare        │ ─────────────────► │  update        │
                             │  predicted vs   │                    │  calibration   │
                             │  actual         │                    │  posteriors    │
                             └─────────────────┘                    └────────────────┘
```

**Step-by-step:**

1. gorzen-recorder finalizes bag, publishes path on `/gorzen/recording/status`
2. gorzen-validator opens bag, extracts actual telemetry timeseries
3. Validator fetches predictions from `GET /predictions/{mission_id}`
4. Computes per-dimension deltas (endurance, energy, blur, GSD, completion)
5. Posts validation report to `POST /validations/{mission_id}`
6. gorzen-planner uses deltas to update Bayesian calibration posteriors
7. Frontend can display predicted-vs-actual comparison charts

### D. Simulation Loop

```
┌────────────────┐  POST /simulations/launch  ┌────────────────┐
│   Frontend     │ ──────────────────────────► │ gorzen-planner  │
└────────────────┘                             └───────┬────────┘
                                                       │
                                               subprocess / docker
                                                       │
                                                       ▼
                                               ┌──────────────────────────┐
                                               │  sitl.launch.py          │
                                               │  ├─ PX4 SITL             │
                                               │  ├─ Gazebo Harmonic      │
                                               │  ├─ XRCE-DDS Agent v2.x │
                                               │  ├─ gorzen-bridge        │
                                               │  ├─ gorzen-executor      │
                                               │  ├─ gorzen-recorder      │
                                               │  └─ gorzen-validator     │
                                               └──────────────────────────┘
```

The simulation loop is identical to the hardware loop from the bridge's
perspective — the only difference is PX4 runs as SITL with Gazebo instead of on
an FCU. This is by design: same code path, same validation, same bag format.

---

## Custom ROS 2 Messages (gorzen_msgs/)

```
# MissionPlan.msg
std_msgs/Header header
string mission_id
string twin_id
gorzen_msgs/Waypoint[] waypoints
float64 max_wind_ms
float64 min_battery_pct

# Waypoint.msg
float64 latitude_deg
float64 longitude_deg
float64 altitude_amsl_m
float64 speed_ms
uint8 action          # 0=navigate, 1=loiter, 2=photo, 3=survey
float32 loiter_time_s
float32 gimbal_pitch_deg

# MissionPredictions.msg
string mission_id
string prediction_id
float64 predicted_endurance_min
float64 predicted_energy_wh
float64 predicted_max_blur_px
float64 predicted_mean_gsd_cm
float64 mission_completion_probability
gorzen_msgs/LegPrediction[] legs

# LegPrediction.msg
uint32 from_wp
uint32 to_wp
float64 time_s
float64 energy_wh
float64 groundspeed_ms
float64 blur_px

# MissionProgress.msg
std_msgs/Header header
string mission_id
uint32 current_waypoint
uint32 total_waypoints
float64 elapsed_s
float64 eta_s

# MissionStatus.msg
std_msgs/Header header
string mission_id
uint8 state  # 0=idle, 1=uploading, 2=ready, 3=running, 4=paused, 5=done, 6=failed
string detail

# ValidationResult.msg
std_msgs/Header header
string mission_id
string prediction_id
string source  # "flight" or "simulation"
float64 actual_endurance_min
float64 actual_energy_wh
float64 delta_endurance_min
float64 delta_energy_wh
bool mission_completed
uint32 waypoints_reached
uint32 waypoints_total

# TelemetryFrame.msg
std_msgs/Header header
float64 latitude_deg
float64 longitude_deg
float64 altitude_amsl_m
float64 altitude_agl_m
float64 roll_deg
float64 pitch_deg
float64 yaw_deg
float64 vn_ms
float64 ve_ms
float64 vd_ms
float64 groundspeed_ms
float64 airspeed_ms
float64 battery_voltage_v
float64 battery_current_a
float64 battery_remaining_pct
uint8 gps_fix
uint8 satellites
bool armed
string flight_mode

# PreflightHealth.msg
std_msgs/Header header
bool gps_ok
bool gyro_ok
bool mag_ok
bool battery_ok
bool global_position_ok
string[] warnings
```

**Service definitions:**

```
# UploadMission.srv
string mission_id
---
bool success
string message

# StartRecording.srv
string mission_id
string prediction_id
---
bool success
string bag_path

# StopRecording.srv
---
bool success
string bag_path
float64 duration_s
uint64 size_bytes
```

---

## Docker Compose (v2 additions)

```yaml
# docker-compose.yml additions

  xrce-dds-agent:
    image: eprosima/micro-xrce-dds-agent:v2.4.3
    network_mode: host
    command: udp4 -p 8888
    restart: unless-stopped

  gorzen-bridge:
    build:
      context: .
      dockerfile: ros/Dockerfile
      target: gorzen-bridge
    network_mode: host
    environment:
      GORZEN_API_URL: http://localhost:8000
      ROS_DOMAIN_ID: "0"
      RMW_IMPLEMENTATION: rmw_fastrtps_cpp
    depends_on:
      - api
      - xrce-dds-agent

  gorzen-executor:
    build:
      context: .
      dockerfile: ros/Dockerfile
      target: gorzen-executor
    network_mode: host
    environment:
      MAVSDK_SERVER_ADDRESS: localhost
      MAVSDK_SYSTEM_ADDRESS: udp://:14540
    depends_on:
      - xrce-dds-agent

  gorzen-recorder:
    build:
      context: .
      dockerfile: ros/Dockerfile
      target: gorzen-recorder
    network_mode: host
    volumes:
      - gorzen_bags:/bags
    depends_on:
      - xrce-dds-agent

  gorzen-validator:
    build:
      context: .
      dockerfile: ros/Dockerfile
      target: gorzen-validator
    network_mode: host
    environment:
      GORZEN_API_URL: http://localhost:8000
    volumes:
      - gorzen_bags:/bags
    depends_on:
      - api
      - gorzen-recorder
```

```yaml
# docker-compose.sim.yml (overlay for simulation)

  px4-sitl:
    image: px4io/px4-dev-simulation-jammy:latest
    network_mode: host
    command: make px4_sitl gz_x500
    environment:
      PX4_GZ_MODEL: x500
      PX4_SIM_SPEED_FACTOR: "1"
    volumes:
      - ./sim/gazebo/worlds:/worlds

  gazebo:
    image: osrf/gazebo:harmonic
    network_mode: host
    environment:
      GZ_SIM_RESOURCE_PATH: /worlds
    volumes:
      - ./sim/gazebo/worlds:/worlds
```

---

## Port / Transport Map

| Transport | Port / Address | Source → Sink |
|-----------|---------------|---------------|
| MAVLink UDP | `udp://:14540` | PX4 SITL ↔ MAVSDK (gorzen-executor) |
| MAVLink UDP | `udp://:14550` | PX4 ↔ QGroundControl (optional) |
| uXRCE-DDS UDP | `udp://8888` | PX4 XRCE client ↔ XRCE-DDS Agent |
| ROS 2 DDS | multicast / SHM | All gorzen ROS 2 nodes (same host) |
| HTTP REST | `localhost:8000` | gorzen-bridge/validator → gorzen-planner |
| WebSocket | `ws://localhost:8000/telemetry/ws` | gorzen-planner → frontend |
| PostgreSQL | `localhost:5432` | gorzen-planner ↔ Postgres |
| Vite dev | `localhost:5173` | Browser ↔ frontend |
| MAVSDK gRPC | `localhost:50051` | gorzen-executor ↔ mavsdk_server |

---

## Migration Path: v1 → v2

The migration is **additive**. Nothing in v1 breaks.

### Phase 1: ROS 2 Bridge (Week 1–2)

Create `ros/gorzen_bridge/` as a standalone ROS 2 node that:
- Subscribes to PX4 telemetry via uXRCE-DDS with correct QoS
- Aggregates into TelemetryFrame
- POSTs to existing gorzen-planner telemetry endpoints

At this point you have **two telemetry paths**: the existing pymavlink path and
the new ROS 2 path. The frontend doesn't change — it still reads from the same
WebSocket. You can A/B compare them.

**Deliverable:** `bridge_only.launch.py` that runs gorzen-bridge alongside
existing backend.

### Phase 2: MAVSDK Executor Node (Week 2–3)

Extract mission upload/download logic from `backend/src/gorzen/services/mission_planner.py`
and `api/routers/execution.py` into `ros/gorzen_executor/`.

The existing REST endpoints remain but delegate to the executor node
via the bridge (or directly via REST → service call proxy).

**Deliverable:** Upload a QGC-format mission through the frontend, have it
execute on PX4 SITL via the executor node.

### Phase 3: Recording + Prediction Export (Week 3–4)

- Add `prediction_sets` and `validation_runs` tables (Alembic migration)
- Add prediction export endpoints to gorzen-planner
- Implement `gorzen-recorder` with start/stop services
- Wire the bridge to trigger recording on mission start

**Deliverable:** Every simulated mission produces a rosbag2 with full
telemetry + mission progress.

### Phase 4: Validator + Feedback Loop (Week 4–6)

- Implement `gorzen-validator`
- Post-flight: read bag → extract actuals → fetch predictions → compute deltas
- POST validation report to planner
- Planner uses deltas to update calibration posteriors
- Frontend shows predicted-vs-actual comparison

**Deliverable:** Run a simulated inspection mission. See a dashboard comparing
predicted endurance, blur, GSD vs actual values. See confidence intervals
tighten after multiple runs.

### Phase 5: Simulation Integration (Week 5–7)

- Gazebo Harmonic world files for test environments
- `sitl.launch.py` that brings up the full stack
- Frontend button: "Simulate this mission" → launches SITL → records → validates
- CI: automated simulation smoke tests

**Deliverable:** One-click simulation from the frontend with automatic
validation report.

### Phase 6: Isaac Sim + Perception (Future)

- Isaac Sim for high-fidelity visual environments
- Synthetic image generation for perception model validation
- GSD/blur validation against rendered imagery
- Isaac ROS bridge for camera topics

Only pursue this when the core loop (phases 1–5) is solid.

---

## What Does NOT Change

- **Frontend architecture**: React + Vite + TanStack Query. New components added,
  existing ones untouched.
- **Backend framework**: FastAPI + SQLAlchemy + Pydantic. No ROS dependency
  in the backend process.
- **Model chain**: All 17 physics models, envelope solver, UQ propagation.
- **API contract**: All existing REST endpoints. New ones added alongside.
- **Database**: Postgres 16. New tables added via Alembic.
- **Authentication**: JWT flow unchanged.
- **CI**: Existing ruff/pyright/bandit/pytest. ROS 2 packages get their own
  colcon test stage.

---

## Key Constraints and Gotchas

1. **uXRCE-DDS v2.x only.** PX4's Micro XRCE-DDS client is built against
   v2.x agent API. Do not use eProsima Micro XRCE-DDS Agent v3.x — it will
   not connect.

2. **PX4 ROS 2 QoS mismatch.** All PX4 topic subscribers must use
   `BEST_EFFORT` reliability + `VOLATILE` durability. Using ROS 2 defaults
   silently drops messages.

3. **MAVSDK + uXRCE-DDS coexistence.** They use different transports:
   MAVSDK uses MAVLink over UDP:14540, uXRCE-DDS uses its own protocol
   on UDP:8888. They do not conflict on the same vehicle.

4. **Single vehicle first.** gorzen_msgs assumes single-vehicle. Multi-vehicle
   adds namespace prefixes (`/drone_01/fmu/out/*`) and fleet registration.
   Design for it, implement later.

5. **rosbag2 storage.** Default SQLite3 plugin. For long missions (>1hr),
   consider MCAP format for better random-access performance. Both are
   supported by rosbag2.

6. **Offboard heartbeat.** MAVSDK's Offboard API auto-sends setpoints at
   20 Hz. PX4 drops out of offboard mode if it doesn't receive setpoints
   for ~500ms (requires ≥2 Hz). Do not implement your own heartbeat on top
   of MAVSDK's — it already handles this.

7. **Gazebo Harmonic version.** PX4 officially supports Gazebo Harmonic on
   Ubuntu 22.04+. The `gz-sim` package, not the old `gazebo` (Gazebo Classic).
   Docker images from `osrf/gazebo:harmonic` or build from PX4's Dockerfile.
