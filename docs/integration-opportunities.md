# Integration Opportunities: Models, APIs & Datasets

Research compilation for enhancing the Gorzen VTOL digital twin platform.
Organized by pipeline phase, ranked by impact-to-effort ratio.

---

## Tier 1: High Impact, Low Effort (Do First)

### pvlib — Physics-Based Lighting
- **Replaces:** Static `ambient_light_lux` pass-through in Environment model
- **What:** Computes solar position, clear-sky irradiance, and lux from lat/lon/time. Models overcast vs clear sky. No external API calls needed.
- **License:** BSD (free, offline)
- **Install:** `pip install pvlib`
- **Impact:** Camera exposure and SNR model become time-of-day and weather aware

### UIUC Propeller Database — Real CT/CP Data
- **Replaces:** Hardcoded CT/CP stub in `data/uiuc_prop.py` (already a stub in the codebase)
- **What:** Wind-tunnel-measured CT, CP, efficiency vs advance ratio for 200+ small propellers (9"-22"). Plain text files, trivially parsed with numpy.
- **License:** Public (cite Prof. Selig)
- **URL:** m-selig.ae.illinois.edu/props/propDB.html
- **Impact:** Rotor model gets real advance-ratio-dependent performance instead of `Ct0*(1-0.3*mu^2)` approximation

### Open-Meteo — Multi-Altitude Wind & Weather
- **Replaces:** Single `wind_speed_ms` scalar in Environment model
- **What:** Free global weather API. Wind speed/direction at 10m, 80m, 120m, 180m heights. Temperature, pressure, cloud cover. No API key required.
- **License:** Free (non-commercial), no key needed
- **Install:** `pip install openmeteo-requests`
- **Impact:** Altitude-dependent wind profiles feed realistic data into Dryden turbulence and drag calculations

### GIQE 5 Upgrade — Better Image Quality Equation
- **Replaces:** GIQE 4.0 coefficients in `image_quality.py`
- **What:** Updated coefficients (c0=9.57, c1=-3.32, c2=3.32, c3=-1.9, c4=-2.0). Removes the RER>=0.9 bifurcation. Single equation valid across all quality levels.
- **License:** Public formula (NGA/SPIE publications)
- **Ref:** Griffith, D., "Updated GIQE," ASPRS/JACIE, 2012-2014
- **Impact:** More accurate NIIRS at degraded conditions (blur, low SNR) — exactly where envelope edges matter most

### Open-Elevation (SRTM) — Terrain Awareness
- **Replaces:** No terrain model currently exists
- **What:** Elevation lookups from NASA SRTM 30m data. Self-hostable Docker container or free REST API.
- **License:** MIT (open source), public domain data
- **URL:** github.com/Jorl17/open-elevation
- **Impact:** Convert AGL to MSL, terrain-following constraints, obstacle clearance layer on envelope grid

### pyulog — Flight Log Ingestion
- **Replaces:** No model calibration pipeline exists
- **What:** Parse PX4 ULog flight logs to extract actual airspeed, altitude, battery voltage, motor RPM, fuel flow. Compare predicted vs actual.
- **License:** BSD-3
- **Install:** `pip install pyulog`
- **Impact:** Empirical validation and calibration of every model in the chain

---

## Tier 2: High Impact, Medium Effort

### PyBaMM — Physics-Based Battery Modeling
- **Replaces/Enhances:** 1RC Thevenin model in `battery.py`
- **What:** Comprehensive battery framework. SPM, DFN electrochemical models, equivalent circuits with temperature/SoC-dependent parameters. Built-in cell parameterizations (LGM50, Chen2020). Uses CasADi internally (already a project dependency).
- **License:** BSD-3
- **Install:** `pip install pybamm`
- **Impact:** Temperature/SoC-dependent R0, R1, C1. Physics-based aging (SEI growth, lithium plating) replaces empirical `alpha*cycles^beta`. Validated OCV curves per cell chemistry.

### CCBlade — Blade Element Momentum Rotor Analysis
- **Replaces:** Simplified CT/CP dimensional analysis in `RotorModel`
- **What:** NREL's validated BEM solver. Takes blade chord/twist distributions and airfoil polars, outputs CT(J), CP(J) with Prandtl tip-loss corrections.
- **License:** Apache 2.0
- **Install:** `pip install ccblade`
- **Impact:** Physics-based rotor performance replacing fixed coefficients. Critical for transition corridor where advance ratio changes significantly.

### HRRR via herbie — 3km Turbulence Forecasts
- **Replaces:** Coarse light/moderate/severe gust categories in Environment model
- **What:** NOAA's High-Resolution Rapid Refresh. 3km grid, hourly updates. Provides EDR (eddy dissipation rate) fields — a direct physical measure of turbulence.
- **License:** Free (public domain, AWS Open Data)
- **Install:** `pip install herbie-data`
- **Impact:** EDR-calibrated Dryden sigma values instead of `0.1 * wind_speed` scaling. Captures terrain-induced and convective turbulence.

### ITM/Longley-Rice — Terrain-Aware RF Propagation
- **Replaces:** Free-space path loss (FSPL) in Comms model
- **What:** Irregular Terrain Model for radio propagation. Considers terrain profile, atmospheric refractivity, ground conductivity. 20 MHz - 20 GHz.
- **License:** Public domain (US Government)
- **Install:** `pip install itmlogic` or community `pyitm`
- **Impact:** Comms feasibility layer on envelope grid. Mountains, buildings, and terrain between drone and GCS cause real link margin degradation the current FSPL model ignores.

### PX4/ArduPilot SITL (QuadPlane) — Simulation Validation
- **Replaces:** No validation loop currently exists
- **What:** Full flight stack simulation. ArduPilot's QuadPlane mode is specifically lift+cruise VTOL — directly matches Gorzen's target platform. Connect via MAVSDK-Python.
- **License:** BSD-3 (PX4), GPLv3 (ArduPilot)
- **Install:** `pip install mavsdk` + PX4/ArduPilot build
- **Impact:** Run predicted mission profiles through SITL, compare outcomes. Validate speed-altitude envelopes match simulated vehicle behavior.

### prysm — Physical Optics MTF
- **Replaces:** Fixed `sampling_mtf = 0.64` in Image Quality model
- **What:** Diffraction-limited MTF/PSF computation from pupil functions and Zernike aberrations. Models defocus, astigmatism, coma. No commercial dependencies.
- **License:** MIT
- **Install:** `pip install prysm`
- **Impact:** Aperture/wavelength/aberration-based MTF replaces magic constants. Models how MTF degrades with defocus at different altitudes.

### ImageNet-C / VisDrone — Degradation Calibration Data
- **Replaces:** Linear degradation assumptions in `identification.py`
- **What:** ImageNet-C has 15 corruption types at 5 severities (blur, JPEG, noise). VisDrone has 263 drone video clips at varying altitudes/GSD with object detection annotations.
- **License:** Research use
- **Impact:** Empirically calibrate `accuracy_degradation_per_blur_px` and `accuracy_degradation_per_jpeg_q10` instead of guessing linear coefficients. Validate pixel_density_factor curve.

---

## Tier 3: Medium Impact, Medium-High Effort

### OpenMDAO + Dymos — MDO Framework
- **Replaces:** Manual model chaining in `envelope_solver.py`
- **What:** NASA's multidisciplinary optimization framework. Automatic coupling, gradient-based optimization, built-in UQ drivers. Dymos adds optimal trajectory generation via direct collocation.
- **License:** Apache 2.0
- **Install:** `pip install openmdao dymos`
- **Impact:** Architecture-level upgrade. Automatic differentiation through the model chain. Optimal mission profiles (energy-optimal climb/descent). Would be a significant refactor.

### Cantera — Thermodynamic Engine Modeling
- **Replaces:** Linear BSFC part-throttle correction in ICE Engine model
- **What:** Chemical kinetics and thermodynamics library. Model actual Otto/2-stroke cycle to produce BSFC maps as function of RPM and torque. Altitude derating from first principles.
- **License:** BSD-3
- **Install:** `pip install cantera`
- **Impact:** BSFC "island" maps replacing `bsfc * (1 + 0.15*(1-throttle))`. Physics-based altitude derating instead of empirical 3%/1000ft rule.

### OpenVSP / AVL — Geometry-Based Aerodynamics
- **Replaces:** Flat-plate drag polar in Airframe model (`cd0 + CL^2/(pi*AR*e)`)
- **What:** OpenVSP: NASA parametric geometry + vortex-lattice aero. AVL: Athena Vortex Lattice for stability derivatives and trim.
- **License:** NASA Open Source (OpenVSP), GPL (AVL)
- **Impact:** Real CL, CD vs alpha for the actual vehicle shape. Important for transition corridor where fuselage/wing/rotor interactions matter.

### AirMap / Aloft — Airspace Intelligence
- **Replaces:** No airspace/regulatory constraints currently
- **What:** Airspace rules, LAANC authorization, NOTAMs, TFRs, geofencing polygons. Weather at altitude layers.
- **License:** Commercial (enterprise API pricing)
- **Impact:** Filter envelope grid to legally flyable altitudes at a given location before running physics models.

### SUAVE / RCAIDE — eVTOL Design Framework
- **Replaces/Supplements:** Multiple models (airframe, propulsion, battery)
- **What:** Stanford's aircraft conceptual design framework. Energy network models for hybrid-electric, weight estimation, mission segment analysis. RCAIDE (successor) explicitly handles lift+cruise VTOL.
- **License:** BSD
- **Impact:** Validated sizing correlations and mission analysis. Weight breakdown methods. Thermal models for batteries in eVTOL profiles.

---

## Tier 4: Supplementary / Future

| Tool | Purpose | License | Notes |
|------|---------|---------|-------|
| **pyiqa** | 30+ image quality metrics (BRISQUE, NIQE, MUSIQ, CLIPIQA) | MIT | Cross-validate GIQE predictions on real imagery |
| **lensfunpy** | Lens distortion database (2000+ camera/lens combos) | LGPL | GSD non-uniformity across FOV |
| **motulator** | PMSM motor simulation (iron losses, saturation) | MIT | Replace simplified Kv/Kt motor model |
| **liionpack** | Pack-level battery sim (cell-to-cell variation) | BSD-3 | Extends PyBaMM for series/parallel packs |
| **impedance.py** | EIS fitting for Thevenin R0/R1/C1 | MIT | Calibrate battery params from real impedance data |
| **ERA5 via cdsapi** | Gold-standard atmospheric reanalysis (137 pressure levels) | Free | Full 3D atmosphere including humidity effects on density |
| **Meteomatics** | Wind at arbitrary altitudes, density altitude | Commercial (~EUR 100/mo) | Best commercial weather-at-altitude option |
| **AWC METAR/TAF** | Real aviation weather observations | Free | Via `avwx` Python package |
| **NASA Battery Dataset** | Run-to-failure Li-ion cycling data | Public domain | Gold standard for aging model validation |
| **Battery Archive** | Thousands of cell cycling datasets (Sandia) | Public domain | OCV curves, aging params per chemistry |
| **InterUSS DSS** | UTM strategic deconfliction (ASTM F3548) | Apache 2.0 | Future-proof UTM-compatible operation volumes |
| **CloudRF** | Hosted RF propagation modeling | Commercial (~$50/mo) | Turnkey alternative to ITM if self-hosting is too complex |
| **Gazebo** | Physics simulation + sensor sim | Apache 2.0 | Free alternative to Omniverse for SITL validation |
| **NVIDIA Omniverse** | High-fidelity 3D sensor simulation | Free (individual) | Validate perception pipeline with rendered camera feeds |

---

## Quick-Start Integration Path

If starting today, this sequence maximizes value with minimal coupling risk:

```
Week 1:  pvlib (lighting) + GIQE 5 (coefficients) + Open-Elevation (terrain)
         └── Pure formula/data upgrades, no architecture changes

Week 2:  UIUC propeller data + Open-Meteo weather
         └── Replace stubs with real data, add altitude-dependent wind

Week 3:  PyBaMM battery + prysm optics
         └── Higher-fidelity subsystem models, drop-in replacements

Week 4:  ITM RF propagation + HRRR turbulence
         └── New feasibility layers on the envelope grid

Week 5+: PX4 SITL validation loop + ImageNet-C calibration
         └── Close the loop: predict → simulate → compare → calibrate
```

Each tier builds on the previous without requiring architectural changes to the existing 17-model chain.
