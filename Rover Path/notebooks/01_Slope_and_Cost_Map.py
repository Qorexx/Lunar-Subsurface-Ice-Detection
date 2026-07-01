import numpy as np
import matplotlib.pyplot as plt
import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ICE_DIR = BASE_DIR / "ICE Detection" / "Data" / "dem"
OUTPUT_DIR = BASE_DIR / "Rover Path" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("Loading NASA DEM...")
# Load the 400x400 DEM we used for 3D rendering
grid_z = np.load(ICE_DIR / "grid_z.npy")

print(f"DEM shape: {grid_z.shape}")
print(f"Elevation range: {np.nanmin(grid_z):.1f}m to {np.nanmax(grid_z):.1f}m")

# The DEM is ~40km x 40km, grid is 400x400. 
# So each pixel is roughly 100m x 100m.
dx = 100.0
dy = 100.0

print("\nComputing Slope Map...")
# Compute gradients (dz/dx and dz/dy)
dz_dy, dz_dx = np.gradient(grid_z, dy, dx)

# Calculate slope magnitude in radians, then convert to degrees
slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
slope_deg = np.degrees(slope_rad)

print(f"Slope range: {np.nanmin(slope_deg):.1f}° to {np.nanmax(slope_deg):.1f}°")
print(f"Mean slope: {np.nanmean(slope_deg):.1f}°")

print("\nComputing Cost Surface...")
# Base cost is the slope (steeper = more expensive)
# Non-linear penalty: slopes > 15 degrees get exponentially more expensive
cost = slope_deg.copy()
cost[slope_deg > 15] = cost[slope_deg > 15] * (slope_deg[slope_deg > 15] / 5)

# Mask out areas that are completely impassable (slope > 25 degrees)
# We set cost to a very high number (infinity essentially for the pathfinder)
MAX_COST = 999999
cost[slope_deg > 25] = MAX_COST

print("Saving outputs...")
np.save(OUTPUT_DIR / "slope_map.npy", slope_deg)
np.save(OUTPUT_DIR / "cost_surface.npy", cost)

# Visualize
plt.figure(figsize=(12, 5))

plt.subplot(1, 2, 1)
plt.imshow(slope_deg, cmap='inferno', origin='lower')
plt.colorbar(label='Slope (Degrees)')
plt.title('Faustini Crater Slope Map')

plt.subplot(1, 2, 2)
# Clip cost for visualization so the MAX_COST pixels don't blow out the color scale
vis_cost = np.clip(cost, 0, 50) 
plt.imshow(vis_cost, cmap='viridis', origin='lower')
plt.colorbar(label='Cost (Higher = Harder)')
plt.title('Rover Traversability Cost Surface\n(Yellow/capped = Impassable)')

plt.tight_layout()
plt.savefig(OUTPUT_DIR / "slope_and_cost.png", dpi=150)
print(f"Saved visualization to: {OUTPUT_DIR / 'slope_and_cost.png'}")
print("Step 1 & 2 Complete.")
