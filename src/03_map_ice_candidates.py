"""
03_map_ice_candidates.py
========================
ISRO Hackathon — Problem Statement 8: Lunar Subsurface Ice Detection
Phase 1: Map ice candidate pixels from slant-range indices to (lat, lon)

PURPOSE:
    Take the CPR and DOP arrays (in slant-range geometry), identify pixels
    that pass the ice detection threshold (CPR > 1 AND DOP < 0.13), and
    map them to geographic (latitude, longitude) coordinates using the
    SLI geometry CSV.

APPROACH:
    The SLI geometry CSV provides ~32,580 control points mapping
    (azimuth_index, range_index) → (lat, lon). We build a 2D interpolator
    from these sparse control points and use it to find the lat/lon
    of each ice candidate pixel.

    Since the CSV is sparse (~1 row per 910 pixels), we need to determine
    the sampling pattern. The SLI XML tells us:
    - Image: 57,880 lines × 512 pixels
    - CSV: 32,580 rows
    - Sampling: ~every 2 lines in azimuth, across the full range swath

    We'll build a regular interpolation grid and query it for ice pixels.

OUTPUTS:
    - ice_candidates.csv: (lat, lon, CPR, DOP) for every ice candidate pixel
    - ice_candidates.npy: boolean mask in slant-range geometry
    - Summary statistics printed to console

AUTHOR: ISRO Hackathon Team
DATE:   2026-06-26
"""

import os
import numpy as np
from scipy.interpolate import RegularGridInterpolator

# =============================================================================
# 1. CONFIGURATION
# =============================================================================

STOKES_DIR = os.path.join(
    "/Users/gauranshtripathi/Documents/ISRO Project/Data",
    "stokes_cpr_dop"
)

SLI_GEO_CSV = os.path.join(
    "/Users/gauranshtripathi/Documents/ISRO Project/Data",
    "ch2_sar_ncxl_20191105t180525404_d_fp_m65",
    "geometry", "calibrated", "20191105",
    "ch2_sar_ncxl_20191105t180525404_g_sli_xx_fp_xx_m65.csv"
)

OUTPUT_DIR = os.path.join(
    "/Users/gauranshtripathi/Documents/ISRO Project/Data",
    "ice_candidates"
)

# Ice detection thresholds (from primary paper, Sinha et al. 2026)
CPR_THRESHOLD = 1.0
DOP_THRESHOLD = 0.13

# SLI image dimensions (from XML)
SLI_LINES = 57880
SLI_PIXELS = 512

# =============================================================================
# 2. LOAD CPR AND DOP
# =============================================================================

print("=" * 60)
print("Ice Candidate Mapping Pipeline")
print("=" * 60)
print()

print("[Step 1/5] Loading CPR and DOP arrays...")
CPR = np.load(os.path.join(STOKES_DIR, "CPR.npy"))
DOP = np.load(os.path.join(STOKES_DIR, "DOP.npy"))
valid_mask = np.load(os.path.join(STOKES_DIR, "valid_mask_slantrange.npy"))

print(f"  CPR shape: {CPR.shape}")
print(f"  DOP shape: {DOP.shape}")
print(f"  Valid pixels: {np.sum(valid_mask):,}")
print()

# =============================================================================
# 3. IDENTIFY ICE CANDIDATES
# =============================================================================

print("[Step 2/5] Applying ice detection thresholds...")
print(f"  CPR > {CPR_THRESHOLD} AND DOP < {DOP_THRESHOLD}")

ice_mask = valid_mask & (CPR > CPR_THRESHOLD) & (DOP < DOP_THRESHOLD)
ice_count = np.sum(ice_mask)

print(f"  Ice candidate pixels: {ice_count:,}")

if ice_count == 0:
    print("  WARNING: No ice candidates found! Check thresholds.")
    exit()

# Get the (row, col) indices of ice pixels in slant-range grid
ice_rows, ice_cols = np.where(ice_mask)
ice_cpr_values = CPR[ice_rows, ice_cols]
ice_dop_values = DOP[ice_rows, ice_cols]

print(f"  Row range of ice pixels: {ice_rows.min()} – {ice_rows.max()}")
print(f"  Col range of ice pixels: {ice_cols.min()} – {ice_cols.max()}")
print(f"  CPR range of ice pixels: {ice_cpr_values.min():.4f} – {ice_cpr_values.max():.4f}")
print(f"  DOP range of ice pixels: {ice_dop_values.min():.4f} – {ice_dop_values.max():.4f}")
print()

# =============================================================================
# 4. BUILD LAT/LON INTERPOLATOR FROM SLI GEOMETRY CSV
# =============================================================================

print("[Step 3/5] Building lat/lon interpolator from SLI geometry CSV...")

# Read the CSV
lats_csv = []
lons_csv = []
with open(SLI_GEO_CSV, 'r') as f:
    header = f.readline()  # Skip header
    for line in f:
        parts = line.strip().split(',')
        lats_csv.append(float(parts[0]))
        lons_csv.append(float(parts[1]))

lats_csv = np.array(lats_csv)
lons_csv = np.array(lons_csv)

n_csv_rows = len(lats_csv)
print(f"  CSV control points: {n_csv_rows:,}")

# Determine the sampling pattern.
# The CSV has 32,580 rows for a 57,880 × 512 image.
# From the user manual: "Generally, it is kept at a particular sampling
# in both azimuth and range direction."
#
# 32,580 = n_az_samples × n_rg_samples
# If n_rg_samples = 60 (every ~8.5 pixels in range):
#   n_az_samples = 32580 / 60 = 543 (every ~106 lines in azimuth)
# If n_rg_samples = 20:
#   n_az_samples = 32580 / 20 = 1629 (every ~35.5 lines)
#
# Let's detect the pattern by looking at longitude changes.
# Within one azimuth line, longitude should change continuously.
# Between azimuth lines, there should be a jump back.

# Detect range samples by finding where longitude jumps to next azimuth line.
# In this dataset, longitude jumps UP by >1° between the last range sample 
# of one azimuth line and the first range sample of the next line.
lon_diffs = np.diff(lons_csv)
jump_indices = np.where(lon_diffs > 1.0)[0]

if len(jump_indices) > 0:
    n_rg_samples = jump_indices[0] + 1
    n_az_samples = n_csv_rows // n_rg_samples
    remainder = n_csv_rows % n_rg_samples
    print(f"  Detected sampling pattern:")
    print(f"    Range samples per line : {n_rg_samples}")
    print(f"    Azimuth lines sampled  : {n_az_samples}")
    print(f"    Remainder rows         : {remainder}")
    print(f"    Azimuth spacing        : every ~{SLI_LINES / n_az_samples:.1f} lines")
    print(f"    Range spacing          : every ~{SLI_PIXELS / n_rg_samples:.1f} pixels")
else:
    print("  WARNING: Could not detect sampling pattern from longitude jumps.")
    print("  Falling back to nearest-neighbor lookup.")
    n_rg_samples = 0
    n_az_samples = 0

print()

# =============================================================================
# 4b. INTERPOLATE LAT/LON FOR ICE CANDIDATE PIXELS
# =============================================================================

print("[Step 4/5] Interpolating lat/lon for ice candidate pixels...")

if n_rg_samples > 0 and n_az_samples > 0 and remainder == 0:
    # Reshape CSV data into a 2D grid
    lat_grid = lats_csv[:n_az_samples * n_rg_samples].reshape(n_az_samples, n_rg_samples)
    lon_grid = lons_csv[:n_az_samples * n_rg_samples].reshape(n_az_samples, n_rg_samples)

    # Create the azimuth and range index arrays for the CSV grid
    # Assume uniform spacing
    az_indices = np.linspace(0, SLI_LINES - 1, n_az_samples)
    rg_indices = np.linspace(0, SLI_PIXELS - 1, n_rg_samples)

    # Build interpolators
    lat_interp = RegularGridInterpolator(
        (az_indices, rg_indices), lat_grid,
        method='linear', bounds_error=False, fill_value=np.nan
    )
    lon_interp = RegularGridInterpolator(
        (az_indices, rg_indices), lon_grid,
        method='linear', bounds_error=False, fill_value=np.nan
    )

    # Query for ice candidate positions
    query_points = np.column_stack([ice_rows.astype(float), ice_cols.astype(float)])
    ice_lats = lat_interp(query_points)
    ice_lons = lon_interp(query_points)

    # Check for NaN (out of bounds)
    valid_geo = ~np.isnan(ice_lats) & ~np.isnan(ice_lons)
    n_valid_geo = np.sum(valid_geo)
    print(f"  Successfully geolocated: {n_valid_geo:,} / {ice_count:,} ice pixels")

    if n_valid_geo < ice_count:
        print(f"  WARNING: {ice_count - n_valid_geo} ice pixels could not be geolocated (outside CSV bounds)")

    ice_lats = ice_lats[valid_geo]
    ice_lons = ice_lons[valid_geo]
    ice_cpr_final = ice_cpr_values[valid_geo]
    ice_dop_final = ice_dop_values[valid_geo]
    ice_rows_final = ice_rows[valid_geo]
    ice_cols_final = ice_cols[valid_geo]

else:
    # Fallback: nearest-neighbor from CSV
    print("  Using nearest-neighbor fallback (less accurate)")
    # Simple approach: map row index to nearest CSV row
    csv_az_step = SLI_LINES / n_csv_rows
    csv_indices = (ice_rows / csv_az_step).astype(int)
    csv_indices = np.clip(csv_indices, 0, n_csv_rows - 1)
    ice_lats = lats_csv[csv_indices]
    ice_lons = lons_csv[csv_indices]
    ice_cpr_final = ice_cpr_values
    ice_dop_final = ice_dop_values
    ice_rows_final = ice_rows
    ice_cols_final = ice_cols
    n_valid_geo = ice_count

print()
print(f"  Ice candidate locations:")
print(f"    Lat range: {np.min(ice_lats):.4f} to {np.max(ice_lats):.4f}")
print(f"    Lon range: {np.min(ice_lons):.4f} to {np.max(ice_lons):.4f}")
print(f"    CPR range: {np.min(ice_cpr_final):.4f} to {np.max(ice_cpr_final):.4f}")
print(f"    DOP range: {np.min(ice_dop_final):.4f} to {np.max(ice_dop_final):.4f}")
print()

# =============================================================================
# 5. SAVE OUTPUTS
# =============================================================================

print("[Step 5/5] Saving outputs...")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Save as CSV (human-readable)
csv_path = os.path.join(OUTPUT_DIR, "ice_candidates.csv")
with open(csv_path, 'w') as f:
    f.write("Latitude(deg),Longitude(deg),CPR,DOP,SLI_Row,SLI_Col\n")
    for i in range(len(ice_lats)):
        f.write(f"{ice_lats[i]:.6f},{ice_lons[i]:.6f},"
                f"{ice_cpr_final[i]:.6f},{ice_dop_final[i]:.6f},"
                f"{ice_rows_final[i]},{ice_cols_final[i]}\n")

print(f"  Saved: {csv_path} ({n_valid_geo} rows)")

# Save ice mask in slant-range geometry
np.save(os.path.join(OUTPUT_DIR, "ice_mask_slantrange.npy"), ice_mask)
print(f"  Saved: ice_mask_slantrange.npy")

# Print summary
print()
print("=" * 60)
print("ICE CANDIDATE SUMMARY")
print("=" * 60)
print(f"  Total ice candidates     : {n_valid_geo:,} pixels")
print(f"  Latitude range           : {np.min(ice_lats):.4f} to {np.max(ice_lats):.4f}")
print(f"  Longitude range          : {np.min(ice_lons):.4f} to {np.max(ice_lons):.4f}")
print(f"  Mean CPR                 : {np.mean(ice_cpr_final):.4f}")
print(f"  Mean DOP                 : {np.mean(ice_dop_final):.4f}")
print()

# Faustini crater F2 is at Lat -87.39, Lon 82.31
# Check how many candidates are near F2
f2_lat, f2_lon = -87.39, 82.31
dist_to_f2 = np.sqrt((ice_lats - f2_lat)**2 + (ice_lons - f2_lon)**2)
near_f2 = np.sum(dist_to_f2 < 0.5)  # within 0.5 degrees
print(f"  Near Faustini F2 (within 0.5°): {near_f2} pixels")
print(f"  Nearest pixel to F2: {np.min(dist_to_f2):.4f} degrees away")
print("=" * 60)
