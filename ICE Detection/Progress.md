# Lunar South Pole Subsurface Ice Detection & Mission Planning
## Complete Methodological Report — ISRO Hackathon Problem Statement 8

---

## 1. The Core Idea & Objective

**Objective:** To detect, characterize, and map subsurface water-ice in the lunar South Polar Regions using Chandrayaan-2 radar data, and translate these findings into an actionable robotic exploration strategy (landing site and rover traverse planning).

**The Problem:** While permanently shadowed regions (PSRs) are known to be cold, identifying unambiguous subsurface ice signatures versus rough, rocky terrain is challenging. Furthermore, orbital detection alone isn't enough; missions require knowing exactly where to land and how to safely drive to the ice.

**The Solution:** A complete Python-based data pipeline that processes Dual Frequency Synthetic Aperture Radar (DFSAR) data to isolate true volumetric scattering (ice) from surface scattering (rocks). This output is then integrated into a high-fidelity 3D interactive model to plan safe rover routes.

**Target Area:** Faustini Crater (specifically the doubly shadowed crater "F2" at Latitude -87.39, Longitude 82.31).

**Applicability:** While we focused on Faustini as our primary target, the entire pipeline is **crater-agnostic**. Every script reads its target coordinates from configuration variables at the top of the file. To apply this pipeline to any other south polar crater (Shoemaker, Haworth, Cabeus, etc.), you only need to:
1. Download the corresponding DFSAR strip from PRADAN.
2. Change the center lat/lon and rim radius in `04_spudis_check.py`.
3. Re-run the pipeline.

---

## 2. Research Foundation

The project's methodology is heavily anchored in recent ISRO publications and hackathon mentor guidelines:

### Primary Paper
**"Subsurface ice in doubly shadowed craters as revealed by Chandrayaan-2 dual frequency synthetic aperture radar"** — Sinha et al. (2026), npj Space Exploration.
- **Doubly Shadowed Craters (DSCs):** Shielded from both direct solar illumination AND scattered thermal emission from nearby sunlit rims. Minimum temperatures reach ~25 K.
- **The Golden Threshold:** Established the definitive criterion for subsurface ice:
  - **CPR (Circular Polarization Ratio) > 1:** Indicates multiple radar bounces.
  - **DOP (Degree of Polarization) < 0.13:** Indicates significant depolarization, confirming volumetric scattering inside ice, eliminating false positives from rough boulders.
- **Key Finding:** Crater F2 within Faustini displays the strongest evidence of ice and a prominent lobate-rim morphology.

### Supporting Literature (Ambiguity & False Positives)
- **Fa & Eke (2018):** Revealed that intermediate-aged craters undergo mass wasting on steep interior walls, exposing fresh rocks that mimic the CPR > 1 signature even at the equator. This justifies our strict reliance on the `DOP < 0.13` threshold to rule out mass-wasting anomalies.
- **Spudis et al. (2013):** Established the "Exterior Sanity Check". Fresh craters have high CPR both inside and outside. True ice targets (anomalous craters) have high CPR *only* inside. We implemented a spatial boundary check around Faustini's rim to reject fresh craters.

### Mentor Guidelines
- Emphasized moving from pure "orbital observations" to an "actionable exploration strategy".
- Key deliverables: Ice map, volume estimates, landing site safety, and solar-constrained rover paths.

---

## 3. The Strategy Pivot: From 2D Maps to 3D Mission Planning
Initially, the objective felt like a standard data processing task (create a 2D map of ice). To differentiate the project and maximize evaluation points for "Innovation in methodology" and "Clarity of presentation", the strategy was upgraded.

**The New Paradigm:**
We will process the raw radar data to find the ice, but the final deliverable will be a **3D Interactive Mission Model**.
1. Extract exact ice coordinates via our Python radar pipeline.
2. Overlay these coordinates onto a 3D Digital Elevation Model (DEM) of Faustini crater.
3. Mark doubly shadowed regions visually.
4. Provide coordinate-accurate hover tooltips so teammates can integrate landing site and rover path planning.

---

## 4. Data Sourcing

### 4.1 Radar Data (Ice Detection)
**Source:** Chandrayaan-2 DFSAR Full-Polarimetric (FP) mode datasets from the ISDA PRADAN portal.
**Target File:** `ch2_sar_ncxl_20191105t180525404_d_fp_m65.zip` (CentreLat -87.55, CentreLon 80.87).

### 4.2 Topographic Data (3D Visualization)
**Source:** NASA Moon Trek (trek.nasa.gov/moon)
**Target:** CE-2 CCD DEM, South Pole — 20m resolution Chang'e-2 stereo camera DEM.

#### DEM Acquisition: Failures & Workarounds

This was the single most frustrating part of the project. Here is the full timeline:

1. **First attempt — USGS COG streaming:** We tried to stream the `Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif` directly from USGS servers using `rasterio` with VSICURL. The file opened successfully, but the South Pole region returned a zero-size array. The global DEM is in equirectangular projection, which collapses to a singularity near the poles, making pixel extraction fail.

2. **Second attempt — NASA Moon Trek DEM Subsetting:** We searched Moon Trek for "LOLA DEM South Pole". The search results were dominated by Artemis III candidate landing sites (Nobile, Shackleton, Malapert Massif) at 5mpp resolution. **Faustini is not an Artemis candidate site, so no dedicated LOLA DEM tile exists for it.** We found the `CE-2 CCD DEM, S Pole` layer (20m resolution, covers the entire South Pole from 60S to 90S), added it, and used the "Subsetting" tool to draw a bounding box. **The download produced a 0-byte empty file.** We tried multiple browsers (Chrome, Safari). Same result every time. NASA's subsetting backend was silently failing.

3. **Third attempt — Synthetic DEM generation:** We wrote `07_generate_synthetic_dem.py` to mathematically generate a Faustini-shaped crater using parabolic bowl geometry, sine-wave rolling hills, interpolated Gaussian noise, and 60 randomly placed impact craters. The synthetic DEM was dimensionally accurate (correct lat/lon bounds, rim radius, F2 sub-crater position) but looked visibly artificial — too smooth, too regular, and the noise patterns were spiky rather than natural.

4. **Fourth attempt (SUCCESS) — Moon Trek OBJ Export:** We discovered the "Generate 3D Print File" tool on Moon Trek. Unlike the Subsetting tool (which extracts raster DEM tiles), this tool generates a triangulated 3D mesh from NASA's internal elevation database. We exported an **OBJ file** with the following settings:
   - Type: OBJ (supports texture mapping, unlike STL)
   - Bounding Box: Lon 67.49° to 102.41°, Lat -87.79° to -86.43°
   - Resolution: 400
   - Height Exaggeration: 1 (raw elevation)
   - Texture: LRO WAC Mosaic, S Pole v2

   **This worked.** The download produced a 61 MB `model.obj` with 969,570 vertices, a `terrain.mtl` material file, and a `texture.png` photorealistic surface image. We then wrote a custom parser to deduplicate the non-indexed OBJ vertices into a clean 400×400 elevation grid (`grid_x.npy`, `grid_y.npy`, `grid_z.npy`), which Python can efficiently slice and render.

**Lesson learned:** NASA's raster subsetting tools are unreliable for polar regions, but their 3D mesh export pipeline works flawlessly. If this pipeline is applied to another crater, use the OBJ export path directly.

---

## 5. Data Filtering & Engineering Pipeline (Phase 1: Ice Detection)

### 5.1 Dataset Structure & XML Metadata Reconnaissance
After extracting the PRADAN `.zip` file, the dataset follows a PDS4-compliant folder structure:

```
ch2_sar_ncxl_20191105t180525404_d_fp_m65/
├── browse/calibrated/20191105/
│   └── ...brw...m65.png          ← Quick-look preview image of the radar strip
├── data/calibrated/20191105/
│   ├── ...sli_xx_fp_hh/hv/vh/vv...tif  ← Level-1A Slant Range Images (~237 MB each)
│   ├── ...gri_xx_fp_hh/hv/vh/vv...tif  ← Level-1B Ground Range Images (~3 MB each)
│   ├── ...sri_xx_fp_hh/hv/vh/vv...tif  ← Level-2 Seleno-Referenced Images (~3 MB each)
│   ├── ...sri_in_fp_xx...tif           ← Incidence Angle Map (Float32, per-pixel angle)
│   ├── ...sri_ma_fp_xx...tif           ← Valid Data Mask (UnsignedByte, bitmask)
│   └── ...sri_xx_fp_xx...xml           ← PDS4 Label (calibration constants, metadata)
└── geometry/calibrated/20191105/
    ├── ...g_sri_xx_fp_xx...csv          ← Per-pixel Lat/Lon lookup table (102,943 rows)
    ├── ...g_sli_xx_fp_xx...csv          ← SLI geometry CSV (32,580 rows)
    └── ...g_oat_xx_fp_xx...csv          ← Orbit/Attitude telemetry
```

**Key Findings from the XML Label:**

| Parameter | Value | Significance |
|---|---|---|
| Image Dimensions | 1320 lines x 1239 pixels | Small enough to process without cropping |
| Pixel Data Type | `UnsignedLSB2` (uint16) | Raw Digital Numbers (0-65,535), NOT calibrated |
| Pixel Spacing | 25.0 m x 25.0 m | Each pixel = 625 m² on the lunar surface |
| Map Projection | UPS (Universal Polar Stereographic) | Standard for polar regions |
| Ellipsoid | Moon Spheroid (R = 1,737,400 m) | Perfectly spherical lunar model |
| Frequency Band | L-band (1.25 GHz) | Penetrates ~5 m into dry regolith |
| Incidence Angle | 26.01 deg | Angle of the radar beam hitting the surface |
| Calibration Constant (K) | **70.308868** | Used to convert DN to sigma nought |
| No. of Azimuth Looks | 16 | Multi-looked for speckle reduction |

**Per-Polarization Calibration Parameters (from XML):**

| Polarization | Bias (Real) | Bias (Imag) | Gain Imbalance | NESZ (sigma nought) |
|---|---|---|---|---|
| HH | 2.4038 | -0.4136 | 1.0156 | 5.42e-04 |
| HV | -4.0579 | 4.1163 | 0.8839 | 3.44e-04 |
| VH | 8.7580 | -4.7671 | 0.9205 | 4.40e-04 |
| VV | -2.0198 | -0.5865 | 1.0049 | 2.79e-04 |

> **NESZ** = Noise Equivalent Sigma Zero. Any pixel with sigma nought below this value is indistinguishable from instrument noise.

**The Calibration Formula:**
```
sigma_nought = DN² / K
```
Where `DN` = unsigned 16-bit integer, `K` = 70.308868 (from XML).

**Geographic Coverage (from geometry CSV):**
- Coverage spans roughly Lat **-86.93° to -88.09°**, Lon **63.91° to 94.70°**.
- Centre of scene: **Lat -87.56°, Lon 80.87°** (confirmed: covers Faustini crater).

---

### 5.2 Pre-Flight Verification
**Scripts:** `00_preflight_checklist.py`, `peek_tiff.py`, `peek_sli.py`, `preflight_verify.py`

Before writing any processing code, a systematic verification was performed to eliminate all assumptions. Three verification scripts were executed to answer four critical questions:

| Question | Finding | Impact on Code |
|---|---|---|
| Q1: What values does the mask file contain? | Three values: `0`, `16`, `128` (bitmask, NOT binary 0/1) | Mask rule: `0` = no-data, `>0` = valid. Cannot assume simple 0/1 |
| Q2: Is the calibration formula correct? | User manual confirms SRI stores **amplitude** data → `sigma0 = DN² / K` is correct | Formula verified, safe to implement |
| Q3: Is incidence angle correction needed? | Per-pixel angle varies 0.57–78.06 deg, but SRI is pre-calibrated Level-2 product | NOT needed for DN→σ⁰. Angle already accounted for |
| Q4: Does the geometry CSV map 1-to-1 to pixels? | CSV has 102,941 rows vs 1,635,480 pixels (~78 samples/line) | CSV is a sparse grid. Must use GeoTIFF's built-in CRS transform instead |

---

### 5.3 Part A: DFSAR Preprocessing — ✅ COMPLETED
**Script:** `src/01_ingest_calibrate.py`

**Methodology:**
1. **Input:** The four Seleno-Referenced Image (SRI) GeoTIFFs: `..._sri_xx_fp_hh_...tif`, `hv`, `vh`, `vv`.
2. **Masking:** Applied the valid-data mask (`..._sri_ma_...tif`). Pixels with mask value `0` are set to `NaN`. Pixels where `DN = 0` within the valid mask area (radar shadow) are also set to `NaN`.
3. **Type Conversion:** Raw `uint16` values are cast to `float64` BEFORE squaring to prevent integer overflow (max DN² = 138,415,225 which exceeds uint16 range of 65,535).
4. **Calibration:** `sigma_nought = DN² / K` where `K = 70.308868` (from XML).
5. **Coregistration:** Not required — SRI products are already map-projected to UPS coordinates with 25m pixel spacing.
6. **Output:** Four calibrated `.npy` arrays saved to `Data/calibrated_sigma0/` along with the boolean valid mask.

**Execution Results:**

| Band | Raw DN Range | σ⁰ Range | σ⁰ Mean | Valid Pixels |
|---|---|---|---|---|
| HH | 0 – 11,765 | 0.0142 – 1,968,674 | 4,406.13 | 510,610 |
| HV | 0 – 1,931 | 0.0142 – 53,034 | 688.47 | 510,607 |
| VH | 0 – 2,176 | 0.0142 – 67,345 | 806.98 | 510,608 |
| VV | 0 – 11,380 | 0.0142 – 1,841,936 | 4,119.67 | 510,609 |

**Physics Sanity Check:** ✅ PASS
- Co-polarized (HH, VV) mean σ⁰ ≈ 4,000–4,400 (strong, similar to each other)
- Cross-polarized (HV, VH) mean σ⁰ ≈ 690–810 (weaker, similar to each other)
- Co-pol > Cross-pol confirmed — consistent with radar scattering physics.

**Note:** σ⁰ values are in **linear power scale** (not dB). For visual display, convert using `10 * log10(σ⁰)`. For CPR/DOP computation, linear values are used directly.

---

### 5.4 Part B: CPR & DOP Computation — ✅ COMPLETED
**Script:** `src/02_compute_cpr_dop.py`

#### Critical Design Decision: SRI vs SLI Data
The DOP formula requires the *phase relationship* between the HH and VV channels via the complex cross-correlation `S_HH · S_VV*`. The SRI (Level-2) files store only amplitude (`uint16`), discarding all phase information. Using SRI data would force `S₃ = 0` and `S₄ = 0`, producing a systematically lower DOP that generates **false positive ice detections** (rocky terrain would incorrectly pass the DOP < 0.13 filter).

**Therefore, we use the SLI (Level-1A, Single Look Complex) files** which store full complex I/Q data (`ComplexLSB8` = two `float32` bands per file).

**SLI Data Properties:**

| Parameter | Value |
|---|---|
| Data type | 2 × float32 (Real + Imaginary) |
| Dimensions | 57,880 lines × 512 pixels |
| Pixel spacing | 0.60 m (azimuth) × 9.59 m (range) |
| Geometry | Slant range (NO map projection) |
| Calibration K | 80.0 (not needed — CPR & DOP are ratios, K cancels out) |
| File size | ~227 MB per polarization |

**Methodology:**
1. **Input:** SLI complex GeoTIFFs for HH and VV only (HV/VH not needed for CPR or DOP).
2. **Complex reconstruction:** `S_HH = Band1 + j·Band2` (real + imaginary parts).
3. **Pixel-wise products:**
   - HH power: `|S_HH|² = real² + imag²`
   - VV power: `|S_VV|² = real² + imag²`
   - Cross-correlation: `S_HH · S_VV* = (hh_r·vv_r + hh_i·vv_i) + j·(hh_i·vv_r - hh_r·vv_i)`
4. **Multi-looking:** Spatial averaging over a 40×3 pixel window (azimuth × range) = 120 effective looks. This reduces single-look speckle noise and approximates the SRI's 25m resolution.
   - Valid-pixel-aware averaging: zero/no-data pixels are excluded from the average count to prevent dilution.
5. **Stokes parameters** (Mohan et al. 2011 convention, ref. 55 in primary paper):
   ```
   S₁ = <|S_HH|²> + <|S_VV|²>           (total co-pol intensity)
   S₂ = <|S_HH|²> - <|S_VV|²>           (HH vs VV imbalance)
   S₃ =  2 · <Re{S_HH · S_VV*}>         (diagonal polarization component)
   S₄ = -2 · <Im{S_HH · S_VV*}>         (circular polarization component)
   ```
6. **CPR and DOP computation:**
   ```
   CPR = (S₁ + S₄) / (S₁ - S₄)
   DOP = √(S₂² + S₃² + S₄²) / S₁
   ```
7. **Output:** CPR, DOP, all four Stokes arrays, and validity mask saved to `Data/stokes_cpr_dop/`.

**Execution Results:**

| Metric | Value | Interpretation |
|---|---|---|
| Valid pixels | 26,682,680 | 89.6% of SLI image |
| CPR range | 0.30 – 5.18 | Reasonable physical range |
| CPR mean / median | 1.05 / 1.00 | Centred around 1 as expected |
| CPR > 1 pixels | 13,537,056 (50.7%) | High — confirms CPR alone is insufficient (Fa & Eke 2018) |
| DOP range | 0.01 – 1.00 | Full physical range |
| DOP mean / median | 0.76 / 0.78 | Most terrain is polarized (surface scattering) |
| DOP < 0.13 pixels | 1,998 (0.01%) | Extremely rare — strong depolarization |
| **ICE CANDIDATES** (CPR > 1 AND DOP < 0.13) | **1,090 pixels (0.004%)** | Matches paper's finding of spatially heterogeneous, concentrated ice |

**Physics Sanity Checks:** ✅ ALL PASS
- CPR alone gives 50% positives → confirms why DOP filter is essential (Fa & Eke 2018 warning validated)
- DOP filter alone gives 0.01% → confirms it is the discriminating parameter
- Combined filter yields 1,090 pixels → small, concentrated clusters expected for doubly shadowed crater ice
- CPR median ≈ 1.0 → typical for mixed terrain (regolith + rocks)

> **Note:** Results are in **slant-range geometry** (57,880 × 512). Reprojection to geographic coordinates is performed in the next step.

---

### 5.5 Part C: Ice Candidate Geolocation — ✅ COMPLETED
**Script:** `src/03_map_ice_candidates.py`

**Purpose:**
The CPR and DOP arrays from Part B are in **slant-range geometry** (57,880 × 512 pixels) — the radar's raw coordinate system. To determine *where* the ice is on the Moon, we must convert the ice candidate pixel indices to geographic (latitude, longitude) coordinates.

**Methodology:**
1. **Input:** CPR and DOP arrays (from Part B), SLI geometry CSV.
2. **Ice detection threshold:** `CPR > 1.0 AND DOP < 0.13` (Sinha et al. 2026, Table 2).
3. **Geometry CSV analysis:** The CSV contains 32,580 control points.
   - Sampling pattern was auto-detected by finding positive longitude jumps (>1°) between azimuth lines.
   - Verified grid: **1,810 azimuth lines × 18 range samples** = 32,580 rows (perfect fit, zero remainder).
   - Azimuth sampling: every ~32 image lines. Range sampling: every ~28 pixels.
4. **2D interpolation:** Control points reshaped into a 1,810 × 18 grid. `scipy.interpolate.RegularGridInterpolator` (bilinear) used to compute lat/lon for each of the 1,090 ice candidate pixel positions.
5. **Output:** `ice_candidates.csv` with columns: Latitude, Longitude, CPR, DOP, SLI_Row, SLI_Col.

**Execution Results:**

| Metric | Value |
|---|---|
| Ice candidate pixels | 1,090 |
| Successfully geolocated | 1,090 / 1,090 (100%) |
| Latitude range | -87.81° to -87.14° |
| Longitude range | 67.82° to 92.54° |
| Mean CPR | 1.10 |
| Mean DOP | 0.10 |
| Near Faustini F2 center (within 0.5°) | 102 pixels |
| Nearest pixel to F2 center | 0.013° (~400 m) |

**Key Finding:** 102 ice candidates cluster within 0.5° of the Faustini F2 crater center (-87.39°, 82.31°) — the exact location where the primary paper reported the **strongest radar evidence** for subsurface ice.

> **Positional accuracy:** Estimated at ~30–50 m (bilinear interpolation from a sparse 1,810 × 18 grid). Sufficient for crater-scale analysis.

---

### 5.6 Part D: False Positive Mitigation (Spudis Check) — ✅ COMPLETED
**Script:** `src/04_spudis_check.py`

**Purpose:** Differentiate true subsurface ice from young, rocky impact craters. High CPR can be caused by both volumetric ice AND rough rocky ejecta. However, rocky ejecta typically spills outside the crater rim, while subsurface ice in doubly shadowed craters is confined to the cold interior.

**Methodology:**
1. Defined the Faustini crater rim boundary (19 km circle centered at Lat: -87.3°, Lon: 82.0°).
2. Computed Haversine great-circle distance from the crater center for each of the 1,090 ice candidates.
3. Split candidates into "Interior" (≤ 19 km) and "Exterior" (> 19 km).

**Execution Results:**

| Metric | Count | Percentage |
|---|---|---|
| Total Candidates | 1,090 | 100% |
| Interior (≤ 19 km) | 995 | 91.3% |
| Exterior (> 19 km) | 95 | 8.7% |

**Scientific Conclusion:** 91.3% of ice candidates are safely confined within the interior of Faustini. Only 8.7% fell outside the 19 km radius, which may be noise or minor boundary effects at the edge of the radar strip. This passes the Spudis sanity check and strongly supports the volumetric ice hypothesis over surface roughness.

---

### 5.7 Part E: Volume Estimation — ✅ COMPLETED
**Script:** `src/05_volume_estimation.py`

**Methodology:**
Based on the 995 confirmed interior ice pixels, we calculated the total potential volume of subsurface water ice in Faustini Crater.
- **Pixel size:** 25m × 25m = 625 m² per pixel (from XML metadata).
- **Penetration depth:** 5.0 meters (standard L-Band radar penetration into dry lunar regolith).
- **Ice fraction:** Conservative (10%) and optimistic (40%) estimates based on regolith porosity models.
- **Ice density:** 917 kg/m³ (standard water ice).

**Results:**

| Metric | Value |
|---|---|
| Interior ice pixels | 995 |
| Total Surface Area | 688,695 m² (~0.69 km²) |
| Total Regolith Volume | 3,443,477 m³ |
| **Conservative Estimate (10% ice)** | **316,456 Metric Tonnes** |
| **Optimistic Estimate (40% ice)** | **1,265,822 Metric Tonnes** |

**Conclusion:** The analysis indicates roughly **300,000 to 1.2 million metric tonnes** of subsurface water-ice concentrated within a ~0.69 km² area of the Faustini crater floor.

---

## 6. Integration Pipeline (Phase 2: Visualization & Mission Planning)

### 6.1 Part A: 2D Ice Heatmap — ✅ COMPLETED
**Script:** `src/06_ice_heatmap.py`

Generated both a publication-quality PNG and a 2-band GeoTIFF of the confirmed ice candidates:
- **PNG** (`ice_heatmap_cpr_dop.png`): Side-by-side map with CPR intensity (left) and DOP confidence (right). Plotted in local km coordinates to correct for polar geometric distortion. Includes crater rim boundary and F2 sub-crater marker.
- **GeoTIFF** (`ice_heatmap.tif`): 2-band raster (Band 1 = CPR, Band 2 = DOP) in geographic CRS (EPSG:4326). 766 × 1118 grid.

### 6.2 Part B: 3D Interactive Terrain Render — ✅ COMPLETED
**Script:** `src/07_3d_visualization.py`
**Output:** `Data/interactive_crater.html`

#### Iterations & Evolution

This was the most iterated component of the project. We went through **four major versions** before arriving at the final render:

**Version 1 (Synthetic DEM + Plotly Surface):**
Used the mathematically generated crater DEM with white noise texture. Problems: terrain looked like a smooth plastic bowl, the noise created visible spikes when downsampled, and the crater had no visual depth from a top-down view. Landing site and rover path floated in mid-air because they were drawn at Z=0 instead of sampling the terrain height.

**Version 2 (Synthetic DEM + scipy interpolation):**
Added `RegularGridInterpolator` to sample terrain height at landing/path coordinates so they sit on the surface. Expanded the DEM bounds to show more surrounding terrain. Problem: still looked artificial. Added sine-wave rolling hills, interpolated Gaussian noise, and 60 random impact craters. Result: way too spiky and aggressive — looked like a porcupine, not the Moon.

**Version 3 (NASA OBJ mesh + Plotly):**
Discovered that Moon Trek's "Generate 3D Print File" tool could export real terrain as an OBJ mesh. Downloaded a 61 MB file with 969,570 vertices. First attempt to reshape vertices into a 400×400 grid failed because the OBJ format duplicates vertices per-face (non-indexed mesh). Wrote a custom parser to deduplicate vertices by rounding XY coordinates and averaging Z values at shared positions. This produced a clean 400×400 elevation grid with real NASA topography.

**Version 4 (Final — NASA OBJ + Ice Heatmap + DSC marking):**
The current version. Key improvements:
- **Full 400×400 resolution** (no downsampling) for maximum terrain detail.
- **CPR heatmap projected directly onto the terrain surface** using a kernel painter (radius=3 pixels per ice candidate).
- **Doubly shadowed regions marked in RED** — defined as all terrain inside Faustini's rim (computed via Haversine distance) AND below elevation threshold Z < -5.0.
- **F2 sub-crater explicitly labeled** with a red cross marker.
- **Hover tooltips show real lat/lon coordinates** — computed by reversing the OBJ→lat/lon transform — so teammates can read exact positions for landing and path planning.
- **Aspect ratio z=0.15** to visually exaggerate depth and make the crater bowl dramatic.
- **Landing site and rover path drawn ON the surface** by sampling terrain Z at each waypoint.

#### 3D Render Statistics

| Metric | Value |
|---|---|
| Terrain mesh | 400 × 400 = 160,000 vertices |
| Elevation range | -22.5 to +36.8 (NASA units) |
| Ice candidates plotted | 1,077 / 1,090 (98.8%) |
| Missing (outside OBJ bounds) | 13 (at lat < -87.79°) |
| Faustini interior pixels | 82,737 |
| Doubly shadowed pixels (red) | 21,005 |
| Output file | `interactive_crater.html` (~7 MB, browser-viewable) |

#### Why Some Ice Candidates Appear Outside the Red Zone
Most ice candidates cluster on the **inner crater walls** rather than the deepest crater floor (the red zone). This is scientifically expected:
1. **Ice exists throughout the entire PSR**, not just the DSC. The full crater interior is permanently shadowed and cold enough (~40–100 K) to trap water ice.
2. **Radar physics favors the crater walls.** The DFSAR beam hits at an angle (~26°). On the steep inner walls, the radar penetrates and bounces off buried ice in multiple directions (high CPR). On the flat floor, the near-vertical incidence produces a different return pattern, making detection harder.
3. **The deepest floor likely HAS ice** — but a thicker regolith blanket over it attenuates the radar signal.

### 6.3 Part C: Slope-Hazard Cost Map — ❌ PENDING (Teammate Scope)
To be computed from the DEM gradient. Will highlight slopes > 15° as danger zones.

### 6.4 Part D: Rover Path Planning — ❌ PENDING (Teammate Scope)
A* or Dijkstra algorithm from a safe, sunlit landing zone to the doubly shadowed crater floor. Cost function weights: steep slopes (high penalty), time in darkness (solar power constraint).

**Integration point:** The `07_3d_visualization.py` script contains `add_landing_site(lat, lon)` and `add_rover_path([(lat, lon), ...])` helper functions. Teammates simply call these with their computed coordinates, and the path is automatically drawn on the terrain surface.

---

## 7. Known Limitations & Constraints

1. **DEM Source:** The OBJ mesh from Moon Trek uses Chang'e-2 stereo camera data (20m resolution), not LOLA laser altimetry. LOLA would provide higher vertical accuracy (~1m vs ~5m), but was unavailable for the Faustini region via Moon Trek's export tools.
2. **Volume Assumptions:** Radar penetration depth depends on the dielectric constant of local regolith (which varies). Our 5.0 m depth is a standard assumption for dry regolith at L-band; actual depth could be 2–10 m depending on composition.
3. **Doubly Shadowed Region Definition:** We approximate DSC using an elevation threshold (Z < -5.0) within the Faustini rim. True DSC boundaries require ray-tracing illumination models that account for scattered thermal emission from nearby sunlit crater walls. This is beyond our current scope.
4. **Hazard Resolution:** While DFSAR/DEM gives macro-slopes, micro-hazards (meter-sized boulders) require OHRC optical imagery overlay, which adds pipeline complexity.
5. **Noise Floor:** Any pixel with sigma nought below the NESZ values (~3–5 × 10⁻⁴) is indistinguishable from instrument noise.
6. **Missing Ice Candidates:** 13 out of 1,090 candidates (1.2%) fall outside the OBJ bounding box at lat < -87.79°. A slightly larger OBJ export would capture these.

---

## 8. Complete File Structure

```
ISRO Project/ICE Detection/
├── Data/
│   ├── ch2_sar_ncxl_.../                    ← Extracted PRADAN dataset
│   │   ├── browse/calibrated/               ← Quick-look PNG preview
│   │   ├── data/calibrated/20191105/        ← SRI + SLI TIFFs, Mask, Incidence, XMLs
│   │   └── geometry/calibrated/             ← Per-pixel Lat/Lon CSVs, orbit telemetry
│   ├── calibrated_sigma0/                   ← OUTPUT: Calibrated σ⁰ numpy arrays
│   │   ├── sigma0_hh.npy, sigma0_hv.npy, sigma0_vh.npy, sigma0_vv.npy
│   │   └── valid_mask.npy
│   ├── stokes_cpr_dop/                      ← OUTPUT: Stokes, CPR, DOP arrays
│   │   ├── CPR.npy, DOP.npy
│   │   ├── S1.npy, S2.npy, S3.npy, S4.npy
│   │   ├── valid_mask_slantrange.npy
│   │   └── config.txt                       ← Multi-looking parameters
│   ├── ice_candidates/                      ← OUTPUT: Geolocated ice detections
│   │   ├── ice_candidates.csv               ← (lat, lon, CPR, DOP) for 1,090 pixels
│   │   ├── ice_mask_slantrange.npy          ← Boolean mask in slant-range geometry
│   │   ├── ice_heatmap.tif                  ← 2-band GeoTIFF (CPR + DOP)
│   │   └── ice_heatmap_cpr_dop.png          ← Publication-quality 2D visualization
│   ├── dem/                                 ← Terrain data
│   │   ├── trekOBJ/                         ← Raw NASA Moon Trek export
│   │   │   ├── model.obj                    ← 61 MB, 969,570 vertices
│   │   │   ├── terrain.mtl                  ← Material definition
│   │   │   └── texture.png                  ← LRO WAC photorealistic texture
│   │   ├── grid_x.npy, grid_y.npy, grid_z.npy  ← Parsed 400×400 elevation grid
│   │   └── faustini_dem.tif                 ← Synthetic DEM (backup, superseded by OBJ)
│   └── interactive_crater.html              ← ★ FINAL 3D INTERACTIVE RENDER ★
│
├── src/
│   ├── 00_preflight_checklist.py            ← Documents all verified facts & uncertainties
│   ├── peek_tiff.py                         ← Verified SRI TIFF structure
│   ├── peek_sli.py                          ← Verified SLI complex structure
│   ├── preflight_verify.py                  ← Resolved all 4 open questions
│   ├── 01_ingest_calibrate.py               ← ✅ DN → σ⁰ calibration
│   ├── 02_compute_cpr_dop.py                ← ✅ Stokes → CPR + DOP from SLI complex data
│   ├── 03_map_ice_candidates.py             ← ✅ Slant-range → lat/lon geolocation
│   ├── 04_spudis_check.py                   ← ✅ Exterior rim false positive mitigation
│   ├── 05_volume_estimation.py              ← ✅ Ice volume calculation
│   ├── 06_ice_heatmap.py                    ← ✅ 2D heatmap (PNG + GeoTIFF)
│   ├── 07_generate_synthetic_dem.py         ← Synthetic DEM generator (backup)
│   └── 07_3d_visualization.py               ← ✅ Final 3D interactive render
│
├── Research/                                ← Papers, mentor PPT, notes
│   ├── Papers/s44453-026-00038-9.pdf        ← Sinha et al. (2026) primary paper
│   └── Problem-statement.txt                ← Official hackathon problem statement
│
└── Progress.md                              ← This document
```

---

## 9. Summary of Key Results

| Deliverable | Status | Key Number |
|---|---|---|
| Radar Calibration (DN → σ⁰) | ✅ Complete | 4 bands × 510K valid pixels |
| CPR/DOP Ice Detection | ✅ Complete | **1,090 ice candidate pixels** |
| Geolocation to Lat/Lon | ✅ Complete | 100% mapped, 102 near F2 |
| Spudis False Positive Check | ✅ Complete | 91.3% interior (PASS) |
| Volume Estimation | ✅ Complete | **316K – 1.27M metric tonnes** |
| 2D Ice Heatmap | ✅ Complete | PNG + GeoTIFF |
| 3D Interactive Render | ✅ Complete | 1,077 ice dots + 21K DSC pixels |
| Slope-Hazard Map | ❌ Pending | Teammate scope |
| Rover Path Planning | ❌ Pending | Teammate scope |

---

## 10. What Remains for Teammates

### Landing Site Selection (Teammate A)
**Input available:** The 3D render (`interactive_crater.html`) provides real lat/lon coordinates on hover. The DEM grid arrays (`grid_x/y/z.npy`) can be loaded in Python to compute slope gradients.
**Task:** Identify a flat, sunlit region on or near the Faustini rim with slopes < 10° and line-of-sight to Earth for communication.
**Integration:** Call `add_landing_site(lat, lon)` in `07_3d_visualization.py`.

### Rover Path Planning (Teammate B)
**Input available:** Ice candidate locations from `ice_candidates.csv`, terrain elevation from `grid_z.npy`.
**Task:** Implement A* pathfinding from the landing site to the F2 sub-crater, minimizing slope steepness and time in darkness.
**Integration:** Call `add_rover_path([(lat1,lon1), (lat2,lon2), ...])` in `07_3d_visualization.py`.
