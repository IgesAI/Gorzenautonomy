# Implementation Roadmap

Priority-ordered plan from audit and physics validation.

## Phase 1 — Make Models Physically Correct ✅

- [x] Rotor thrust: T = CT×ρ×n²×D⁴ (validated)
- [x] Drag: D = 0.5×ρ×v²×Cd×A (validated)
- [x] GSD: (sensor_width×altitude)/(focal_length×image_width) (validated)
- [x] Motion blur: max_velocity = (blur_pixels×GSD)/exposure_time (validated)
- [x] Reference validation tests in `test_formulas_reference.py`

## Phase 2 — Real Data Sources (Stubs Added)

- [x] `gorzen/data/lipo.py` — LiPo OCV reference curve
- [x] `gorzen/data/uiuc_prop.py` — UIUC prop database stub
- [ ] Integrate UIUC prop CSV/JSON for CT(μ), CP(μ)
- [ ] NASA airfoil data (if needed for wing model)

## Phase 3 — System-Level Testing ✅

- [x] `test_inspection_mission_constraints()` — all constraints satisfied
- [x] Envelope feasibility mask consistent with per-point evaluation
- [x] MCP constraints defined

## Phase 4 — Monte Carlo / Uncertainty ✅

- [x] Default MC samples: 500 → 1000
- [x] UQ inputs: wind, bsfc, mass, cd0, soh, temperature, **encoding_bitrate**
- [x] Output: confidence intervals (P5/P50/P95), MCP

## Phase 5 — Performance Optimization

- [ ] Vectorize grid evaluation (NumPy)
- [ ] Cache invariant results (e.g. ISA density by altitude)
- [ ] Optional: numba for hot paths

## Phase 6 — Observability

- [ ] Logging of every constraint decision
- [ ] Debug mode for engineers

## Tools Added

| Tool | Purpose |
|------|---------|
| **pint** | Unit handling, validation, conversion |
| **hypothesis** | Property-based testing |
| **numpy, scipy** | Already present |
| **pydantic v2** | Already present |
| **numba** | Optional, for performance |
