# Output Pipeline Audit: Accuracy, Efficiency, and Value

Audit of how the digital twin produces final outputs (MCP, fuel endurance, battery reserve, sensitivity) and whether they are accurate, efficient, and provide valuable, usable, correct information.

---

## 1. Output Flow Summary

| Output | Source | Method | Scope |
|--------|--------|--------|-------|
| **Feasibility surface** | Deterministic grid | 17-model chain per (speed, alt) | Full envelope |
| **Identification surface** | Deterministic grid | Same | Full envelope |
| **Endurance surface** | Deterministic grid | Same | Full envelope |
| **MCP** | Monte Carlo | 500 samples at midpoint | Single operating point |
| **Fuel endurance (P5/P50/P95)** | Monte Carlo | Same 500 samples | Single operating point |
| **Battery reserve (P5/P50/P95)** | Monte Carlo | Same 500 samples | Single operating point |
| **Sensitivity** | Pearson correlation | Input vs fuel_endurance_hr | Single operating point |

---

## 2. Accuracy Assessment

### 2.1 Mission Completion Probability (MCP)

**Definition:** P(fuel_endurance_hr ≥ 1.0 ∧ identification_confidence ≥ min_ident)

**Correctness:** ✓ The joint constraint logic is correct. MCP = mean(all_satisfied) over MC samples.

**Scope:** ⚠ **Critical** — MCP is computed at **one** operating point (mid_speed, mid_alt), not over the full envelope. Users may assume it applies everywhere.

**Precision:** With 500 samples, SE ≈ √[p(1−p)/500]. For p=0.9, SE≈0.013 (±1.3%). Adequate for screening per [Eracons, RStudio analysis].

**Benchmark:** NASA guidance on MC for aerospace reliability — 500 samples is reasonable for initial screening; higher (1000–5000) for certification.

### 2.2 Fuel Endurance & Battery Reserve (EnvelopeOutput)

**Correctness:** ✓ Mean, std, P5/P25/P50/P75/P95 from MC samples are statistically valid.

**Scope:** Same single-point caveat as MCP.

### 2.3 Sensitivity Ranking

**Method:** Pearson correlation between each input and fuel_endurance_hr.

**Limitations:**
- Correlation captures **linear** association; Sobol indices are preferred for nonlinear models [EPA, SciDirect].
- Ranked by **fuel_endurance only** — identification_confidence drivers (GSD, encoding_bitrate, blur) are not in UQ inputs, so sensitivity misses perception-side contributors to MCP.
- wind_speed_ms is in UQ but may not affect fuel chain in current model — low/no correlation expected.

**Benchmark:** Correlation is acceptable as a fast screening step; Sobol would be more rigorous for final analysis.

### 2.4 Surface Confidence Bands (z_p5, z_p95)

**Current implementation:**
- ident_surface: z_p5 = z_mean × 0.85, z_p95 = z_mean × 1.1
- endurance_surface: z_p5 = z_mean × 0.85, z_p95 = z_mean × 1.15

**Issue:** ⚠ These are **synthetic** scaling factors, not from actual UQ. They suggest uncertainty bands but do not represent real confidence intervals. Misleading if interpreted as such.

---

## 3. Efficiency Assessment

| Step | Cost | Notes |
|------|------|-------|
| Grid evaluation | 20×20 = 400 points × 17 models | ~6.8k model evals |
| UQ propagation | 500 samples × 17 models | ~8.5k model evals |
| **Total** | ~15.3k model evals | ~1–3 s typical |

**Verdict:** ✓ Efficient for interactive use. Full UQ at every grid point would be 400×500 = 200k evals — not practical without parallelization.

---

## 4. Value & Usability

### Strengths
- MCP gives a single, interpretable risk metric.
- P5/P50/P95 for fuel and battery support reserve planning.
- Sensitivity highlights which parameters to calibrate or tighten.
- Feasibility heatmap is actionable for mission planning.

### Gaps
1. **Operating point ambiguity** — MCP/fuel/battery/sensitivity apply to midpoint; UI does not state this.
2. **Synthetic bands** — Surface P5/P95 are not real UQ; risk of misinterpretation.
3. **Failed MC samples** — Silently dropped; can cause input/output length mismatch and wrong sensitivity.
4. **Perception drivers** — UQ inputs don’t include encoding_bitrate, GSD-related params; sensitivity underrepresents identification_confidence drivers.

---

## 5. Corrections Applied

1. **UI:** Clarify that MCP, fuel endurance, battery reserve, and sensitivity are for the nominal operating point (midpoint of speed/altitude range).
2. **UI:** Remove or relabel synthetic P5/P95 on surfaces to avoid implying real confidence bands.
3. **Backend:** Align input/output samples when MC runs fail — only use successful runs for sensitivity and MCP.
4. **Sensitivity:** Rank by correlation with a proxy for MCP (e.g., min of normalized fuel and ident margins) when both constraints matter, or document that ranking is fuel_endurance-only.

---

## 6. References

- NASA NTRS: Monte Carlo for launch vehicle design
- Eracons: Statistical uncertainty in MC proportion estimates
- EPA/SciDirect: Pearson vs Sobol for sensitivity
- RStudio: Sample size for proportion estimation (N≥500 adequate)
