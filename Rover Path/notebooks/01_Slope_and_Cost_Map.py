"""
01_Slope_and_Cost_Map.py
========================
Computes a multi-factor traversability cost surface for Faustini Crater.

Cost factors:
  1. Slope (from DEM gradient) — steep terrain is dangerous
  2. Shadow penalty — DSC zones have no solar power for the rover
  3. Roughness (local elevation variance) — boulder fields
  4. Elevation penalty — deep crater floor is harder to reach/return from

Output: cost_surface.npy, slope_map.npy, roughness_map.npy
"""

import numpy as np
import matplotlib.pyplot as plt
import math
from pathlib import Path
from scipy.ndimage import uniform_filter

# ────────────────────────────────────────────────────────────
# PATHS
# ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ICE_DIR = BASE_DIR / "ICE Detection" / "Data" / "dem"
OUTPUT_DIR = BASE_DIR / "Rover Path" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ────────────────────────────────────────────────────────────
# CONSTANTS
# ────────────────────────────────────────────────────────────
OBJ_LON_MIN, OBJ_LON_MAX = 67.4943, 102.4096
OBJ_LAT_MIN, OBJ_LAT_MAX = -87.7853, -86.4307
GRID_SIZE = 400
R_MOON_KM = 1737.4
FAUSTINI_LAT, FAUSTINI_LON = -87.3, 82.0
FAUSTINI_RIM_KM = 19.0
DSC_Z_THRESHOLD = -5.0  # Elevation below which = doubly shadowed

PIXEL_SIZE_M = 100.0  # Each pixel ≈ 100m (40 km / 400 px)

# ────────────────────────────────────────────────────────────
# LOAD DEM
# ────────────────────────────────────────────────────────────
print("=" * 60)
print("STEP 1: Loading NASA DEM...")
grid_z = np.load(ICE_DIR / "grid_z.npy")
print(f"  Shape: {grid_z.shape}")
print(f"  Elevation range: {np.nanmin(grid_z):.1f}m to {np.nanmax(grid_z):.1f}m")

# ────────────────────────────────────────────────────────────
# STEP 2: SLOPE MAP
# ────────────────────────────────────────────────────────────
print("\nSTEP 2: Computing Slope Map...")
dz_dy, dz_dx = np.gradient(grid_z, PIXEL_SIZE_M, PIXEL_SIZE_M)
slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
slope_deg = np.degrees(slope_rad)

print(f"  Slope range: {slope_deg.min():.3f}° to {slope_deg.max():.1f}°")
print(f"  Mean: {slope_deg.mean():.3f}°, Median: {np.median(slope_deg):.3f}°")
print(f"  Pixels > 5°: {(slope_deg > 5).sum()} ({(slope_deg > 5).sum()/slope_deg.size*100:.1f}%)")
print(f"  Pixels > 15°: {(slope_deg > 15).sum()}")

# ────────────────────────────────────────────────────────────
# STEP 3: ROUGHNESS MAP (local elevation std-dev, 5x5 kernel)
# ────────────────────────────────────────────────────────────
print("\nSTEP 3: Computing Roughness Map...")
local_mean = uniform_filter(grid_z, size=5)
local_sq_mean = uniform_filter(grid_z**2, size=5)
roughness = np.sqrt(np.maximum(local_sq_mean - local_mean**2, 0))

print(f"  Roughness range: {roughness.min():.3f}m to {roughness.max():.2f}m")
print(f"  Mean: {roughness.mean():.3f}m")

# ────────────────────────────────────────────────────────────
# STEP 4: SHADOW / DSC MASK
# ────────────────────────────────────────────────────────────
print("\nSTEP 4: Building Faustini interior + DSC masks...")

def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R_MOON_KM * 2 * math.asin(math.sqrt(a))

faustini_mask = np.zeros((GRID_SIZE, GRID_SIZE), dtype=bool)
for i in range(GRID_SIZE):
    for j in range(GRID_SIZE):
        lon = OBJ_LON_MIN + (j / (GRID_SIZE - 1)) * (OBJ_LON_MAX - OBJ_LON_MIN)
        lat = OBJ_LAT_MAX - (i / (GRID_SIZE - 1)) * (OBJ_LAT_MAX - OBJ_LAT_MIN)
        dist = haversine(FAUSTINI_LAT, FAUSTINI_LON, lat, lon)
        if dist <= FAUSTINI_RIM_KM:
            faustini_mask[i, j] = True

dsc_mask = faustini_mask & (grid_z < DSC_Z_THRESHOLD)
print(f"  Faustini interior: {faustini_mask.sum():,} pixels")
print(f"  Doubly shadowed (Z < {DSC_Z_THRESHOLD}): {dsc_mask.sum():,} pixels")

# ────────────────────────────────────────────────────────────
# STEP 5: MULTI-FACTOR COST SURFACE
# ────────────────────────────────────────────────────────────
print("\nSTEP 5: Building multi-factor cost surface...")

MAX_COST = 999999

# Factor 1: Slope cost (base = 1.0 for flat, non-linear penalty for steep)
slope_cost = 1.0 + slope_deg * 2.0  # Linear base
slope_cost[slope_deg > 10] *= (slope_deg[slope_deg > 10] / 5.0)  # Quadratic above 10°
slope_cost[slope_deg > 20] = MAX_COST  # Impassable above 20°

# Factor 2: Shadow penalty (rover needs solar power)
# PSR interior: moderate penalty (can traverse but inefficient)
# DSC zones: high penalty (completely dark, power-starved)
shadow_cost = np.ones_like(grid_z)
shadow_cost[faustini_mask] = 3.0    # PSR: 3x cost (dark but traversable)
shadow_cost[dsc_mask] = 8.0         # DSC: 8x cost (very expensive, avoid if possible)

# Factor 3: Roughness penalty
roughness_norm = roughness / (roughness.max() + 1e-6)
roughness_cost = 1.0 + roughness_norm * 5.0  # Max 6x penalty for roughest areas

# Combine: multiplicative so ALL factors matter
cost = slope_cost * shadow_cost * roughness_cost

# Ensure impassable zones stay impassable
cost[slope_deg > 20] = MAX_COST

print(f"  Cost range: {cost[cost < MAX_COST].min():.1f} to {cost[cost < MAX_COST].max():.1f}")
print(f"  Mean cost: {cost[cost < MAX_COST].mean():.1f}")
print(f"  Impassable pixels: {(cost >= MAX_COST).sum()}")

# ────────────────────────────────────────────────────────────
# SAVE
# ────────────────────────────────────────────────────────────
print("\nSaving outputs...")
np.save(OUTPUT_DIR / "slope_map.npy", slope_deg)
np.save(OUTPUT_DIR / "roughness_map.npy", roughness)
np.save(OUTPUT_DIR / "cost_surface.npy", cost)
np.save(OUTPUT_DIR / "faustini_mask.npy", faustini_mask)
np.save(OUTPUT_DIR / "dsc_mask.npy", dsc_mask)

# ────────────────────────────────────────────────────────────
# VISUALIZE
# ────────────────────────────────────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(14, 12))

ax = axes[0, 0]
im = ax.imshow(slope_deg, cmap='inferno', origin='lower')
plt.colorbar(im, ax=ax, label='Degrees')
ax.set_title('Slope Map')

ax = axes[0, 1]
im = ax.imshow(roughness, cmap='magma', origin='lower')
plt.colorbar(im, ax=ax, label='Meters (std dev)')
ax.set_title('Surface Roughness')

ax = axes[1, 0]
vis = np.zeros((*grid_z.shape, 3))
vis[~faustini_mask] = [0.5, 0.5, 0.5]     # Rock: gray
vis[faustini_mask] = [0.3, 0.3, 0.4]       # PSR: dark blue-gray
vis[dsc_mask] = [0.8, 0.15, 0.15]          # DSC: red
ax.imshow(vis, origin='lower')
ax.set_title('Hazard Zones\n(Gray=Rock, Blue-gray=PSR, Red=DSC)')

ax = axes[1, 1]
vis_cost = np.clip(cost, 0, 100)
im = ax.imshow(vis_cost, cmap='viridis', origin='lower')
plt.colorbar(im, ax=ax, label='Cost (lower = easier)')
ax.set_title('Multi-Factor Traversability Cost\n(Slope × Shadow × Roughness)')

fig.suptitle('Faustini Crater — Rover Traversability Analysis', fontsize=14, weight='bold')
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "slope_and_cost.png", dpi=150)
print(f"Saved: {OUTPUT_DIR / 'slope_and_cost.png'}")
print("Steps 1-5 Complete.")
