"""
02_compute_cpr_dop.py
=====================
ISRO Hackathon — Problem Statement 8: Lunar Subsurface Ice Detection
Phase 1: Compute CPR and DOP from SLI (complex) data

PURPOSE:
    Load the SLI (Single Look Complex) GeoTIFF files for HH and VV,
    compute the four Stokes parameters using the complex cross-correlation,
    then derive CPR (Circular Polarization Ratio) and DOP (Degree of
    Polarization) for every pixel.

WHY SLI AND NOT SRI:
    DOP requires the PHASE relationship between HH and VV channels
    (via Re{S_HH · S_VV*} and Im{S_HH · S_VV*}). The SRI files only
    store amplitude (uint16), discarding phase. Using SRI would produce
    a systematically lower DOP, generating false positive ice detections.
    See Progress.md Section 5 for full justification.

VERIFIED FACTS:
    - SLI data type     : ComplexLSB8 = 2 bands of float32 (Real + Imaginary)
    - SLI dimensions    : 57,880 lines × 512 pixels (single-look, slant range)
    - SLI pixel spacing : 0.60 m (azimuth) × 9.59 m (range)
    - SLI CRS           : None (slant range geometry, no map projection)
    - Calibration K_SLI : 80.0 (not needed — CPR and DOP are ratios, K cancels)

STOKES PARAMETERS (Mohan et al. 2011, ref. 55 in primary paper):
    S₁ = <|S_HH|²> + <|S_VV|²>           (total co-pol intensity)
    S₂ = <|S_HH|²> - <|S_VV|²>           (HH vs VV imbalance)
    S₃ =  2 · <Re{S_HH · S_VV*}>         (diagonal polarization component)
    S₄ = -2 · <Im{S_HH · S_VV*}>         (circular polarization component)

    Where <...> denotes spatial averaging (multi-looking).

FORMULAS:
    CPR = (S₁ + S₄) / (S₁ - S₄)
    DOP = √(S₂² + S₃² + S₄²) / S₁

    Physical meaning:
    - CPR > 1  → volumetric scattering (ice candidate)
    - CPR < 1  → surface/single-bounce scattering (regolith)
    - DOP < 0.13 → strong depolarization (confirms ice, rules out rocks)
    - DOP > 0.13 → polarized return (surface scattering, not ice)

MULTI-LOOKING:
    SLI is single-look (very noisy). We apply spatial averaging over a
    window to reduce speckle noise. Window chosen to match approximately
    the SRI product resolution (25m × 25m):
    - Azimuth: 40 pixels × 0.60 m = 24.0 m
    - Range:    3 pixels × 9.59 m = 28.8 m

OUTPUTS:
    Saves CPR, DOP, and Stokes parameter arrays to Data/stokes_cpr_dop/

AUTHOR: ISRO Hackathon Team
DATE:   2026-06-26
"""

import os
import numpy as np
import rasterio
from scipy.ndimage import uniform_filter

# =============================================================================
# 1. CONFIGURATION
# =============================================================================

DATA_DIR = os.path.join(
    "/Users/gauranshtripathi/Documents/ISRO Project/Data",
    "ch2_sar_ncxl_20191105t180525404_d_fp_m65",
    "data", "calibrated", "20191105"
)

# SLI file paths (complex data: Band 1 = Real, Band 2 = Imaginary)
SLI_HH = os.path.join(DATA_DIR, "ch2_sar_ncxl_20191105t180525404_d_sli_xx_fp_hh_m65.tif")
SLI_VV = os.path.join(DATA_DIR, "ch2_sar_ncxl_20191105t180525404_d_sli_xx_fp_vv_m65.tif")

# Multi-looking window (azimuth × range)
# Azimuth: 40 pixels × 0.60 m/pixel ≈ 24 m
# Range:    3 pixels × 9.59 m/pixel ≈ 29 m
ML_AZIMUTH = 40
ML_RANGE = 3

# Output directory
OUTPUT_DIR = os.path.join(
    "/Users/gauranshtripathi/Documents/ISRO Project/Data",
    "stokes_cpr_dop"
)

# =============================================================================
# 2. LOAD SLI COMPLEX DATA
# =============================================================================

print("=" * 60)
print("Stokes Parameter, CPR & DOP Computation Pipeline")
print("=" * 60)
print()

# --- Load HH complex ---
print("[Step 1/6] Loading SLI HH complex data...")
with rasterio.open(SLI_HH) as src:
    hh_real = src.read(1).astype(np.float64)  # Band 1 = Real part
    hh_imag = src.read(2).astype(np.float64)  # Band 2 = Imaginary part
    img_shape = (src.height, src.width)

print(f"  Shape: {img_shape}")
print(f"  Memory: {hh_real.nbytes / 1e6:.1f} MB × 2 bands")
print()

# --- Load VV complex ---
print("[Step 2/6] Loading SLI VV complex data...")
with rasterio.open(SLI_VV) as src:
    vv_real = src.read(1).astype(np.float64)
    vv_imag = src.read(2).astype(np.float64)

    # Verify dimensions match HH
    assert (src.height, src.width) == img_shape, \
        f"VV dimensions {(src.height, src.width)} != HH dimensions {img_shape}"

print(f"  Shape: {img_shape} (matches HH ✓)")
print()

# =============================================================================
# 3. COMPUTE PIXEL-WISE PRODUCTS (before multi-looking)
# =============================================================================

print("[Step 3/6] Computing pixel-wise products...")

# Create valid mask: both HH and VV must be non-zero
# (zero real AND zero imag = no-data pixel)
valid = ~((hh_real == 0) & (hh_imag == 0))
valid &= ~((vv_real == 0) & (vv_imag == 0))

valid_count = np.sum(valid)
print(f"  Valid pixels: {valid_count:,} / {hh_real.size:,} ({100*valid_count/hh_real.size:.1f}%)")

# HH power: |S_HH|² = real² + imag²
hh_power = hh_real**2 + hh_imag**2

# VV power: |S_VV|² = real² + imag²
vv_power = vv_real**2 + vv_imag**2

# Cross-correlation: S_HH · S_VV* = (hh_r + j·hh_i)(vv_r - j·vv_i)
#   Real part = hh_r·vv_r + hh_i·vv_i
#   Imag part = hh_i·vv_r - hh_r·vv_i
cross_real = hh_real * vv_real + hh_imag * vv_imag
cross_imag = hh_imag * vv_real - hh_real * vv_imag

# Set no-data pixels to 0 in products (they won't contribute to averages)
hh_power[~valid] = 0.0
vv_power[~valid] = 0.0
cross_real[~valid] = 0.0
cross_imag[~valid] = 0.0

# Free the raw complex arrays to save memory (~480 MB freed)
del hh_real, hh_imag, vv_real, vv_imag

print(f"  HH power range: {np.min(hh_power[valid]):.2f} – {np.max(hh_power[valid]):.2f}")
print(f"  VV power range: {np.min(vv_power[valid]):.2f} – {np.max(vv_power[valid]):.2f}")
print()

# =============================================================================
# 4. MULTI-LOOKING (spatial averaging to reduce speckle)
# =============================================================================

print(f"[Step 4/6] Multi-looking with window {ML_AZIMUTH}×{ML_RANGE} "
      f"({ML_AZIMUTH * ML_RANGE} effective looks)...")

# Create a count array for valid-pixel-aware averaging
# Sum of products / count of valid pixels = true average
valid_float = valid.astype(np.float64)

# Uniform filter computes the local mean (sum / window_size).
# To get sum, multiply by window_size. Then divide by valid count.
window = (ML_AZIMUTH, ML_RANGE)
window_size = ML_AZIMUTH * ML_RANGE

# Step 4a: Compute the local SUM of each product
hh_power_sum = uniform_filter(hh_power, size=window) * window_size
vv_power_sum = uniform_filter(vv_power, size=window) * window_size
cross_real_sum = uniform_filter(cross_real, size=window) * window_size
cross_imag_sum = uniform_filter(cross_imag, size=window) * window_size

# Step 4b: Compute the local COUNT of valid pixels
valid_count_local = uniform_filter(valid_float, size=window) * window_size

# Avoid division by zero where there are no valid pixels
valid_count_local[valid_count_local < 1] = np.nan

# Step 4c: Compute the local MEAN (valid-pixel-aware)
hh_power_ml = hh_power_sum / valid_count_local
vv_power_ml = vv_power_sum / valid_count_local
cross_real_ml = cross_real_sum / valid_count_local
cross_imag_ml = cross_imag_sum / valid_count_local

# Free intermediate arrays
del hh_power, vv_power, cross_real, cross_imag
del hh_power_sum, vv_power_sum, cross_real_sum, cross_imag_sum
del valid_float, valid_count_local

print(f"  Multi-looked HH power range: {np.nanmin(hh_power_ml):.2f} – {np.nanmax(hh_power_ml):.2f}")
print(f"  Multi-looked VV power range: {np.nanmin(vv_power_ml):.2f} – {np.nanmax(vv_power_ml):.2f}")
print()

# =============================================================================
# 5. COMPUTE STOKES PARAMETERS, CPR, AND DOP
# =============================================================================

print("[Step 5/6] Computing Stokes parameters, CPR, and DOP...")

# Stokes parameters (Mohan et al. 2011 convention)
S1 = hh_power_ml + vv_power_ml          # Total co-pol intensity
S2 = hh_power_ml - vv_power_ml          # HH vs VV imbalance
S3 = 2.0 * cross_real_ml                # Diagonal component
S4 = -2.0 * cross_imag_ml               # Circular component

# Free intermediate arrays
del hh_power_ml, vv_power_ml, cross_real_ml, cross_imag_ml

# --- CPR ---
# CPR = (S1 + S4) / (S1 - S4)
# Guard against division by zero
denominator_cpr = S1 - S4
denominator_cpr[denominator_cpr == 0] = np.nan
CPR = (S1 + S4) / denominator_cpr

# --- DOP ---
# DOP = sqrt(S2² + S3² + S4²) / S1
# Guard against division by zero
S1_safe = S1.copy()
S1_safe[S1_safe == 0] = np.nan
DOP = np.sqrt(S2**2 + S3**2 + S4**2) / S1_safe

# Create a final validity mask (pixels that had valid data after multi-looking)
final_valid = ~np.isnan(CPR) & ~np.isnan(DOP) & np.isfinite(CPR) & np.isfinite(DOP)

print(f"  Valid CPR/DOP pixels: {np.sum(final_valid):,}")
print()

# --- Statistics ---
cpr_valid = CPR[final_valid]
dop_valid = DOP[final_valid]

print("  CPR statistics:")
print(f"    Min    : {np.min(cpr_valid):.4f}")
print(f"    Max    : {np.max(cpr_valid):.4f}")
print(f"    Mean   : {np.mean(cpr_valid):.4f}")
print(f"    Median : {np.median(cpr_valid):.4f}")
print(f"    Pixels with CPR > 1: {np.sum(cpr_valid > 1):,} ({100*np.sum(cpr_valid > 1)/len(cpr_valid):.2f}%)")
print()

print("  DOP statistics:")
print(f"    Min    : {np.min(dop_valid):.4f}")
print(f"    Max    : {np.max(dop_valid):.4f}")
print(f"    Mean   : {np.mean(dop_valid):.4f}")
print(f"    Median : {np.median(dop_valid):.4f}")
print(f"    Pixels with DOP < 0.13: {np.sum(dop_valid < 0.13):,} ({100*np.sum(dop_valid < 0.13)/len(dop_valid):.2f}%)")
print()

# --- ICE CANDIDATES ---
ice_mask = (cpr_valid > 1.0) & (dop_valid < 0.13)
print(f"  *** ICE CANDIDATES (CPR > 1 AND DOP < 0.13): {np.sum(ice_mask):,} pixels "
      f"({100*np.sum(ice_mask)/len(cpr_valid):.2f}%) ***")
print()

# =============================================================================
# 6. SAVE OUTPUTS
# =============================================================================

print("[Step 6/6] Saving outputs...")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Save CPR and DOP arrays
np.save(os.path.join(OUTPUT_DIR, "CPR.npy"), CPR)
np.save(os.path.join(OUTPUT_DIR, "DOP.npy"), DOP)

# Save Stokes parameters for traceability
np.save(os.path.join(OUTPUT_DIR, "S1.npy"), S1)
np.save(os.path.join(OUTPUT_DIR, "S2.npy"), S2)
np.save(os.path.join(OUTPUT_DIR, "S3.npy"), S3)
np.save(os.path.join(OUTPUT_DIR, "S4.npy"), S4)

# Save validity mask
np.save(os.path.join(OUTPUT_DIR, "valid_mask_slantrange.npy"), final_valid)

# Save multi-looking config for reproducibility
config_path = os.path.join(OUTPUT_DIR, "config.txt")
with open(config_path, 'w') as f:
    f.write(f"ml_azimuth_pixels={ML_AZIMUTH}\n")
    f.write(f"ml_range_pixels={ML_RANGE}\n")
    f.write(f"ml_azimuth_meters={ML_AZIMUTH * 0.601246:.2f}\n")
    f.write(f"ml_range_meters={ML_RANGE * 9.593359:.2f}\n")
    f.write(f"effective_looks={ML_AZIMUTH * ML_RANGE}\n")
    f.write(f"image_shape={img_shape}\n")
    f.write(f"valid_pixels={np.sum(final_valid)}\n")

for fname in os.listdir(OUTPUT_DIR):
    fpath = os.path.join(OUTPUT_DIR, fname)
    fsize = os.path.getsize(fpath) / (1024 * 1024)
    print(f"  Saved: {fname} ({fsize:.1f} MB)")

print()
print("=" * 60)
print("CPR & DOP computation complete.")
print("Next step: Reproject from slant-range to map-projected (SRI) geometry,")
print("then apply ice thresholding (CPR > 1 AND DOP < 0.13).")
print("=" * 60)
