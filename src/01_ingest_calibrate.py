"""
01_ingest_calibrate.py
======================
ISRO Hackathon — Problem Statement 8: Lunar Subsurface Ice Detection
Phase 1, Micro-Task 3: Ingest DFSAR SRI data and calibrate DN → σ⁰

PURPOSE:
    Load the four Seleno-Referenced Image (SRI) GeoTIFF files (HH, HV, VH, VV),
    apply the valid-data mask, convert raw Digital Numbers (DN) to radar
    backscatter coefficient (sigma nought), and save the calibrated arrays.

VERIFIED FACTS (from XML metadata + preflight peek):
    - File format    : GeoTIFF, uint16 (unsigned 16-bit integer)
    - Dimensions     : 1320 lines × 1239 pixels
    - Pixel spacing  : 25 m × 25 m (each pixel = 625 m²)
    - CRS            : Polar Stereographic Moon (south pole origin)
    - DN range       : 0–11765 (HH), 0–1931 (HV), 0–2176 (VH), 0–11380 (VV)
    - Mask values    : 0 = no-data, >0 = valid data
    - Calibration    : σ⁰ = DN² / K, where K = 70.308868
    - Valid pixels   : ~510,610 per band (out of 1,635,480 total)

OUTPUTS:
    Saves four .npy files (one per polarization) into Data/calibrated_sigma0/
    Each file contains a float64 array of shape (1320, 1239).
    Masked (no-data) pixels are set to NaN.

AUTHOR: ISRO Hackathon Team
DATE:   2026-06-22
"""

import os
import numpy as np
import rasterio

# =============================================================================
# 1. CONFIGURATION — All paths and constants defined in one place
# =============================================================================

# Base directory for the extracted PRADAN dataset
DATA_DIR = os.path.join(
    "/Users/gauranshtripathi/Documents/ISRO Project/Data",
    "ch2_sar_ncxl_20191105t180525404_d_fp_m65",
    "data", "calibrated", "20191105"
)

# File prefix (everything before the polarization code)
PREFIX = "ch2_sar_ncxl_20191105t180525404_d_sri_xx_fp_"
SUFFIX = "_m65.tif"

# The four polarization bands we need
POLARIZATIONS = ["hh", "hv", "vh", "vv"]

# Mask file path
MASK_FILE = os.path.join(
    DATA_DIR,
    "ch2_sar_ncxl_20191105t180525404_d_sri_ma_fp_xx_m65.tif"
)

# Calibration constant from XML metadata
# Source: <isda:calibration_constant>70.308868</isda:calibration_constant>
CALIBRATION_CONSTANT_K = 70.308868

# Output directory for calibrated arrays
OUTPUT_DIR = os.path.join(
    "/Users/gauranshtripathi/Documents/ISRO Project/Data",
    "calibrated_sigma0"
)

# =============================================================================
# 2. LOAD THE VALID-DATA MASK
# =============================================================================

print("=" * 60)
print("DFSAR SRI Ingestion & Calibration Pipeline")
print("=" * 60)
print()

print("[Step 1/4] Loading valid-data mask...")
with rasterio.open(MASK_FILE) as src:
    mask_raw = src.read(1)  # shape: (1320, 1239), dtype: uint8

# Mask rule (verified via preflight):
#   0   = no-data (pixel outside radar swath)
#   >0  = valid data (values 16 and 128 observed)
valid_mask = mask_raw > 0

valid_count = np.sum(valid_mask)
total_count = valid_mask.size
print(f"  Mask shape    : {mask_raw.shape}")
print(f"  Valid pixels  : {valid_count:,} / {total_count:,} ({100*valid_count/total_count:.1f}%)")
print()

# =============================================================================
# 3. LOAD AND CALIBRATE EACH POLARIZATION BAND
# =============================================================================

print("[Step 2/4] Loading and calibrating polarization bands...")
print(f"  Calibration formula: sigma0 = DN^2 / {CALIBRATION_CONSTANT_K}")
print()

# Dictionary to hold the four calibrated arrays
calibrated = {}

for pol in POLARIZATIONS:
    # Build the full file path
    filename = PREFIX + pol + SUFFIX
    filepath = os.path.join(DATA_DIR, filename)

    # Verify the file exists before opening
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Missing file: {filepath}")

    # Read the raw DN values
    with rasterio.open(filepath) as src:
        dn_raw = src.read(1)  # shape: (1320, 1239), dtype: uint16

        # On the first band, also save the CRS and transform for later use
        if pol == "hh":
            crs = src.crs
            transform = src.transform
            bounds = src.bounds

    # Convert to float64 BEFORE squaring to prevent integer overflow
    # (max DN = 11765, DN² = 138,415,225 — overflows uint16 but fits float64)
    dn_float = dn_raw.astype(np.float64)

    # Apply calibration: σ⁰ = DN² / K
    sigma0 = (dn_float ** 2) / CALIBRATION_CONSTANT_K

    # Apply the mask: set no-data pixels to NaN
    # This ensures they propagate correctly through all future computations
    sigma0[~valid_mask] = np.nan

    # Also set pixels where DN=0 (but mask says valid) to NaN
    # These are radar shadow pixels with no return signal
    sigma0[dn_raw == 0] = np.nan

    # Store the calibrated array
    calibrated[pol.upper()] = sigma0

    # Print verification stats for this band
    valid_sigma0 = sigma0[~np.isnan(sigma0)]
    print(f"  {pol.upper()} band:")
    print(f"    Raw DN range     : {np.min(dn_raw[valid_mask]):,} – {np.max(dn_raw[valid_mask]):,}")
    print(f"    σ⁰ range         : {np.min(valid_sigma0):.6f} – {np.max(valid_sigma0):.6f}")
    print(f"    σ⁰ mean          : {np.mean(valid_sigma0):.6f}")
    print(f"    Valid pixels     : {len(valid_sigma0):,}")
    print()

# =============================================================================
# 4. SAVE CALIBRATED ARRAYS TO DISK
# =============================================================================

print("[Step 3/4] Saving calibrated arrays...")

os.makedirs(OUTPUT_DIR, exist_ok=True)

for pol in POLARIZATIONS:
    out_path = os.path.join(OUTPUT_DIR, f"sigma0_{pol}.npy")
    np.save(out_path, calibrated[pol.upper()])
    file_size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"  Saved: {out_path} ({file_size_mb:.1f} MB)")

# Also save the mask for downstream scripts
mask_path = os.path.join(OUTPUT_DIR, "valid_mask.npy")
np.save(mask_path, valid_mask)
print(f"  Saved: {mask_path}")
print()

# =============================================================================
# 5. FINAL VERIFICATION REPORT
# =============================================================================

print("[Step 4/4] Final verification report")
print("-" * 60)
print(f"  Image dimensions   : {calibrated['HH'].shape[0]} x {calibrated['HH'].shape[1]}")
print(f"  Pixel spacing      : 25.0 m x 25.0 m")
print(f"  CRS                : {crs}")
print(f"  Bounds (UPS meters): left={bounds.left:.2f}, bottom={bounds.bottom:.2f}")
print(f"                       right={bounds.right:.2f}, top={bounds.top:.2f}")
print(f"  Calibration K      : {CALIBRATION_CONSTANT_K}")
print(f"  Valid pixel count  : {valid_count:,}")
print()

# Cross-check: HH and VV should be similar strength (co-pol),
# HV and VH should be similar but weaker (cross-pol)
hh_mean = np.nanmean(calibrated['HH'])
vv_mean = np.nanmean(calibrated['VV'])
hv_mean = np.nanmean(calibrated['HV'])
vh_mean = np.nanmean(calibrated['VH'])

print("  Physics sanity check:")
print(f"    HH mean σ⁰ = {hh_mean:.4f}  |  VV mean σ⁰ = {vv_mean:.4f}  (co-pol, should be similar)")
print(f"    HV mean σ⁰ = {hv_mean:.4f}  |  VH mean σ⁰ = {vh_mean:.4f}  (cross-pol, should be similar & weaker)")

if hh_mean > hv_mean and vv_mean > vh_mean:
    print("    ✅ PASS: Co-pol > Cross-pol (consistent with radar physics)")
else:
    print("    ⚠️  WARNING: Unexpected relationship between co-pol and cross-pol")

print()
print("=" * 60)
print("Ingestion & calibration complete. Ready for CPR/DOP computation.")
print("=" * 60)
