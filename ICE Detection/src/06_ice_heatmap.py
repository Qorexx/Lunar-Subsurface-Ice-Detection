"""
06_ice_heatmap.py
=================
ISRO Hackathon — Problem Statement 8: Lunar Subsurface Ice Detection
Phase 1 Final Output: 2D Ice Heatmap (PNG + GeoTIFF)

PURPOSE:
    Generate publication-quality visualizations and a georeferenced raster
    of the confirmed ice candidates within Faustini Crater. This is the
    capstone deliverable for Phase 1 — turning numbers into a visual story.

OUTPUTS:
    1. ice_heatmap_cpr_dop.png   — Side-by-side map: CPR (left) + DOP (right)
    2. ice_heatmap.tif           — 2-band GeoTIFF (Band 1 = CPR, Band 2 = DOP)
                                   in simple geographic CRS for Phase 2 integration.

NOTE ON POLAR GEOMETRY:
    At latitude ~-87.3°, one degree of longitude is only ~1.4 km on the
    Moon (vs ~30.3 km per degree of latitude). Plotting raw lat/lon would
    distort the crater into a horizontal smear. To show the true physical
    shape, we convert all coordinates to local (X km, Y km) offsets from
    the crater center using Haversine-based projections. The crater rim
    then appears as a proper circle.

AUTHOR: ISRO Hackathon Team
DATE:   2026-06-29
"""

import os
import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import Normalize
from matplotlib import cm
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS

# =============================================================================
# 1. CONFIGURATION
# =============================================================================

INPUT_CSV = os.path.join(
    "/Users/gauranshtripathi/Documents/ISRO Project/ICE Detection/Data",
    "ice_candidates", "ice_candidates.csv"
)

OUTPUT_DIR = os.path.join(
    "/Users/gauranshtripathi/Documents/ISRO Project/ICE Detection/Data",
    "ice_candidates"
)

# Faustini Crater parameters
FAUSTINI_LAT = -87.3
FAUSTINI_LON = 82.0
RIM_RADIUS_KM = 19.0
R_MOON_KM = 1737.4

# F2 sub-crater (primary paper target)
F2_LAT = -87.39
F2_LON = 82.31

# =============================================================================
# 2. HELPER FUNCTIONS
# =============================================================================

def haversine_distance(lat1, lon1, lat2, lon2, radius=R_MOON_KM):
    """Great-circle distance between two points on the Moon (km)."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return radius * 2 * math.asin(math.sqrt(a))


def latlon_to_local_km(lat, lon, lat0=FAUSTINI_LAT, lon0=FAUSTINI_LON):
    """
    Convert (lat, lon) to local (x_km, y_km) offsets from a reference point.
    Uses signed Haversine components so direction is preserved.
    x = East-West (positive East), y = North-South (positive North).
    """
    deg2rad = math.pi / 180.0
    km_per_deg_lat = (math.pi * R_MOON_KM) / 180.0  # ~30.32 km/deg

    dy = (lat - lat0) * km_per_deg_lat
    dx = (lon - lon0) * km_per_deg_lat * math.cos(lat * deg2rad)
    return dx, dy

# =============================================================================
# 3. LOAD AND FILTER DATA
# =============================================================================

print("=" * 65)
print("ICE HEATMAP GENERATION (PNG + GeoTIFF)")
print("=" * 65)

df = pd.read_csv(INPUT_CSV)
print(f"Loaded {len(df):,} ice candidates.")

# Apply Spudis interior filter
distances = [haversine_distance(FAUSTINI_LAT, FAUSTINI_LON,
             row['Latitude(deg)'], row['Longitude(deg)'])
             for _, row in df.iterrows()]
df['Distance_km'] = distances
interior = df[df['Distance_km'] <= RIM_RADIUS_KM].copy()
print(f"Interior candidates (Spudis-confirmed): {len(interior):,}")

# Convert to local km coordinates
local_coords = [latlon_to_local_km(row['Latitude(deg)'], row['Longitude(deg)'])
                for _, row in interior.iterrows()]
interior['X_km'] = [c[0] for c in local_coords]
interior['Y_km'] = [c[1] for c in local_coords]

# F2 center in local coords
f2_x, f2_y = latlon_to_local_km(F2_LAT, F2_LON)

# =============================================================================
# 4. GENERATE PNG — Side-by-side CPR + DOP Heatmap
# =============================================================================

print("\n[1/2] Generating PNG heatmap...")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), dpi=200)
fig.patch.set_facecolor('#0a0a1a')

# --- Shared elements for both panels ---
for ax, values, cmap_name, label, vmin, vmax in [
    (ax1, interior['CPR'].values, 'inferno', 'CPR (Circular Polarization Ratio)', 1.0, interior['CPR'].max()),
    (ax2, interior['DOP'].values, 'viridis_r', 'DOP (Degree of Polarization)', 0.0, 0.13),
]:
    ax.set_facecolor('#0a0a1a')

    # Draw crater rim circle
    rim_circle = plt.Circle((0, 0), RIM_RADIUS_KM, fill=False,
                            edgecolor='#00ffcc', linewidth=1.5,
                            linestyle='--', alpha=0.8, label='Faustini Rim (19 km)')
    ax.add_patch(rim_circle)

    # Plot ice candidates
    sc = ax.scatter(interior['X_km'].values, interior['Y_km'].values,
                    c=values, cmap=cmap_name, s=12, alpha=0.85,
                    edgecolors='none', vmin=vmin, vmax=vmax,
                    zorder=3)

    # Mark F2 sub-crater center
    ax.plot(f2_x, f2_y, marker='*', color='#ff3366', markersize=14,
            markeredgecolor='white', markeredgewidth=0.5,
            label=f'F2 Center ({F2_LAT}°, {F2_LON}°)', zorder=5)

    # Mark Faustini center
    ax.plot(0, 0, marker='+', color='#00ffcc', markersize=10,
            markeredgewidth=2, label='Faustini Center', zorder=5)

    # Colorbar
    cbar = fig.colorbar(sc, ax=ax, shrink=0.75, pad=0.02)
    cbar.set_label(label, fontsize=10, color='white', labelpad=10)
    cbar.ax.yaxis.set_tick_params(color='white')
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color='white', fontsize=9)

    # Formatting
    ax.set_xlabel('East–West Distance from Center (km)', fontsize=10, color='white')
    ax.set_ylabel('North–South Distance from Center (km)', fontsize=10, color='white')
    ax.set_aspect('equal')
    ax.set_xlim(-25, 25)
    ax.set_ylim(-25, 25)
    ax.tick_params(colors='white', labelsize=9)
    for spine in ax.spines.values():
        spine.set_color('#333355')
    ax.grid(True, alpha=0.15, color='white')
    ax.legend(loc='upper left', fontsize=8, facecolor='#1a1a2e',
              edgecolor='#333355', labelcolor='white')

ax1.set_title('Ice Candidates — CPR Intensity', fontsize=13, color='white',
              fontweight='bold', pad=12)
ax2.set_title('Ice Candidates — DOP Confidence', fontsize=13, color='white',
              fontweight='bold', pad=12)

fig.suptitle('Faustini Crater Subsurface Ice Detection — Chandrayaan-2 DFSAR',
             fontsize=15, color='white', fontweight='bold', y=0.98)
fig.text(0.5, 0.01,
         f'995 confirmed ice pixels | Area ≈ 0.69 km² | Est. 316,000–1,266,000 tonnes H₂O ice',
         ha='center', fontsize=10, color='#aaaacc', style='italic')

plt.tight_layout(rect=[0, 0.03, 1, 0.95])

png_path = os.path.join(OUTPUT_DIR, "ice_heatmap_cpr_dop.png")
fig.savefig(png_path, facecolor=fig.get_facecolor(), bbox_inches='tight')
plt.close()
print(f"  Saved: {png_path}")

# =============================================================================
# 5. GENERATE GeoTIFF — 2-band raster (CPR + DOP)
# =============================================================================

print("\n[2/2] Generating GeoTIFF...")

# Define the raster grid covering the Faustini area
# Use a lat/lon bounding box with some padding
lat_min = interior['Latitude(deg)'].min() - 0.05
lat_max = interior['Latitude(deg)'].max() + 0.05
lon_min = interior['Longitude(deg)'].min() - 0.5
lon_max = interior['Longitude(deg)'].max() + 0.5

# Grid resolution: ~25m equivalent
# At -87.3° lat, 1° lon ≈ 1.43 km = 1430 m → 25m ≈ 0.0175°
# 1° lat ≈ 30.3 km → 25m ≈ 0.000825°
res_lat = 0.001   # ~30.3 m per pixel in latitude
res_lon = 0.02    # ~28.6 m per pixel in longitude (at -87.3°)

n_rows = int((lat_max - lat_min) / res_lat) + 1
n_cols = int((lon_max - lon_min) / res_lon) + 1

print(f"  Raster dimensions: {n_rows} rows × {n_cols} cols")
print(f"  Lat range: {lat_min:.4f} to {lat_max:.4f}")
print(f"  Lon range: {lon_min:.4f} to {lon_max:.4f}")

# Initialize empty rasters with NaN (no-data)
cpr_raster = np.full((n_rows, n_cols), np.nan, dtype=np.float32)
dop_raster = np.full((n_rows, n_cols), np.nan, dtype=np.float32)

# Rasterize the ice candidates
rasterized_count = 0
for _, row in interior.iterrows():
    r = int((lat_max - row['Latitude(deg)']) / res_lat)
    c = int((row['Longitude(deg)'] - lon_min) / res_lon)
    if 0 <= r < n_rows and 0 <= c < n_cols:
        # If multiple candidates fall in same cell, keep the stronger signal
        if np.isnan(cpr_raster[r, c]) or row['CPR'] > cpr_raster[r, c]:
            cpr_raster[r, c] = row['CPR']
            dop_raster[r, c] = row['DOP']
        rasterized_count += 1

print(f"  Rasterized {rasterized_count} ice pixels into grid.")

# Write GeoTIFF
tif_path = os.path.join(OUTPUT_DIR, "ice_heatmap.tif")
transform = from_bounds(lon_min, lat_min, lon_max, lat_max, n_cols, n_rows)

with rasterio.open(
    tif_path, 'w', driver='GTiff',
    height=n_rows, width=n_cols, count=2,
    dtype='float32', crs=CRS.from_epsg(4326),
    transform=transform, nodata=np.nan,
) as dst:
    dst.write(cpr_raster, 1)
    dst.write(dop_raster, 2)
    dst.set_band_description(1, 'CPR (Circular Polarization Ratio)')
    dst.set_band_description(2, 'DOP (Degree of Polarization)')

tif_size = os.path.getsize(tif_path) / 1024
print(f"  Saved: {tif_path} ({tif_size:.1f} KB)")

# =============================================================================
# 6. SUMMARY
# =============================================================================

print()
print("=" * 65)
print("HEATMAP GENERATION COMPLETE")
print("=" * 65)
print(f"  PNG : {png_path}")
print(f"  TIFF: {tif_path}")
print(f"  Band 1: CPR (ice signal strength)")
print(f"  Band 2: DOP (depolarization confidence)")
print()
print("The PNG is ready for your hackathon presentation.")
print("The GeoTIFF is ready for Phase 2 (3D terrain integration).")
print("=" * 65)
