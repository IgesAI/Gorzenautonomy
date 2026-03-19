# Critical Gaps — Assessment & Remediation

## 1. Physics Validation (Biggest Risk)

### What We Have
| Formula | Implementation | Reference |
|---------|----------------|-----------|
| **Motion blur** | `blur_pixels = (v × t_exposure) / GSD` ✓ | Design doc, Pix4D |
| **+ vibration** | `total_blur = √(smear² + vib²)` ✓ | — |
| **+ rolling shutter** | RS distortion → Identification (1% weight) ✓ | Phase One |
| **+ lens MTF** | ImageQuality model (GIQE) ✓ | GIQE 4.0 |
| **GSD** | `(sensor_width × alt) / (focal_length × pixel_width)` ✓ | DJI, Wikipedia |
| **Rotor thrust** | `T = CT × ρ × n² × D⁴` ✓ | NASA, actuator disk |
| **Drag** | `D = 0.5 × ρ × v² × Cd × A` ✓ | NASA Glenn |
| **Battery OCV** | Polynomial 3+1.2s-0.6s²+0.6s³ ✓ | LiPo typical |

### What's Missing
- **Ground truth comparison**: No validation against real flight logs, PX4/Ardupilot, DJI specs
- **Battery under load**: OCV curve validated; voltage sag / discharge under load not benchmarked
- **Published research**: No comparison to peer-reviewed camera/blur models

### Remediation
- [ ] Add benchmark suite with known reference values (e.g. DJI Mavic GSD table)
- [ ] Integrate real LiPo discharge curves from datasheets
- [ ] Document formula sources in code (docstrings with citations)

---

## 2. Cross-Model Integration Testing

### What We Have
- `test_envelope_feasibility_mask_consistent` — mask matches per-point evaluation
- Per-model unit tests

### What's Missing
- **Explicit failure propagation**: When motion_blur fails → envelope infeasible
- **Constraint coupling**: GSD says OK but blur says no → ident confidence must drop

### Remediation
- [x] Add `test_constraint_failure_propagates_to_envelope`
- [ ] Add `test_identification_degraded_when_blur_exceeds_limit`

---

## 3. Ground Truth Benchmarking

### What We Have
- None

### What's Missing
- Comparison vs real drone flight logs
- Known systems (PX4, Ardupilot, DJI)
- Published research data

### Remediation
- [ ] Create `benchmarks/` with reference datasets
- [ ] Add `test_against_dji_mavic_specs` (if specs available)
- [ ] Document "validation status" per model

---

## 4. Performance Profiling

### What We Have
- `computation_time_s` in envelope response
- No structured benchmarks

### What's Missing
- Latency per solve
- Scaling vs grid size, MC samples
- Worst-case analysis

### Remediation
- [x] Add `benchmarks/benchmark_envelope.py`
- [ ] Add pytest-benchmark or custom timing
- [ ] Document baseline: ~2s for 20×20 grid + 1000 MC

---

## 5. Uncertainty Modeling Validation

### What We Have
- Monte Carlo (1000 samples)
- Sensitivity ranking (correlation with constraints)
- MCP = P(all constraints satisfied)

### What's Missing
- MC propagation validation (e.g. known input → expected output distribution)
- Sensitivity vs Sobol indices
- Confidence interval calibration

### Remediation
- [x] Add `test_mc_propagation_sensible`
- [ ] Compare correlation sensitivity to Sobol (if PCE used)
- [ ] Document UQ assumptions

---

## 6. Data Sources

### What We Have
- `gorzen/data/lipo.py` — reference OCV curve
- `gorzen/data/uiuc_prop.py` — stub
- ISA in environment model

### What's Missing
- UIUC prop data (actual CSV/JSON)
- Motor efficiency curves
- Battery datasheet integration

### Remediation
- [ ] Integrate UIUC prop database
- [ ] Add motor efficiency lookup
- [ ] Load LiPo curves from datasheet format

---

## 7. Model Traceability / Explainability

### What We Have
- Formula audit doc
- No runtime traceability

### What's Missing
- For each output: "Derived from: model X, constraint Y"
- Explainability API

### Remediation
- [x] Add `EnvelopeProvenance` / trace structure
- [ ] API endpoint for "explain this point"

---

## 8. Type Safety

### What We Have
- Pydantic v2 for schemas
- No mypy/pyright
- `pint` added but minimal use

### What's Missing
- mypy strict mode
- Unit annotations on all model I/O
- `pint` for physical quantities

### Remediation
- [x] Add `pyrightconfig.json` / mypy config
- [ ] Gradual typing of model chain
- [ ] Use pint in validation layer

---

## 9. API Contract / Schema Validation

### What We Have
- Pydantic v2 request/response
- No versioning

### What's Missing
- Versioned API (e.g. /v1/)
- Strict schema evolution policy
- OpenAPI with examples

### Remediation
- [ ] Add /v1/ prefix
- [ ] Schema version in response
- [ ] Document breaking change policy

---

## 10. Simulation Layer

### What We Have
- Analytical models only
- No trajectory sim
- No frame-level camera sim

### What's Missing
- Trajectory simulation (time-step)
- Camera frame simulation
- Detection probability from first principles

### Remediation
- [ ] Add `gorzen/simulation/` stub
- [ ] Trajectory integrator
- [ ] Frame generator for validation
