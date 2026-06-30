import os
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS

OUTPUT_DIR = "/Users/gauranshtripathi/Documents/ISRO Project/ICE Detection/Data/dem"
os.makedirs(OUTPUT_DIR, exist_ok=True)
DEM_PATH = os.path.join(OUTPUT_DIR, "faustini_dem.tif")

# Expanded Grid dimensions to show more surrounding area
lat_min, lat_max = -88.2, -86.5
lon_min, lon_max = 60.0, 100.0
n_rows, n_cols = 1000, 1400

print("Generating Synthetic Faustini DEM...")
# Create a coordinate grid
lats = np.linspace(lat_max, lat_min, n_rows)
lons = np.linspace(lon_min, lon_max, n_cols)
lon_grid, lat_grid = np.meshgrid(lons, lats)

# Faustini center
center_lat, center_lon = -87.3, 82.0
rim_radius_deg_lat = 19.0 / 30.32  # approx radius in degrees lat
rim_radius_deg_lon = 19.0 / 1.43   # approx radius in degrees lon at -87.3

# Calculate distance from center (normalized to 1.0 at rim)
dist = np.sqrt(((lat_grid - center_lat) / rim_radius_deg_lat)**2 + 
               ((lon_grid - center_lon) / rim_radius_deg_lon)**2)

# Generate elevation (bowl shape)
# Crater floor is deep (-2000m), rim is high (+500m), outside is rough plain (0m)
dem = np.zeros((n_rows, n_cols), dtype=np.float32)

# Inside crater
inside = dist <= 1.0
dem[inside] = -2000 + (dist[inside] ** 2) * 2500  # -2000m at center, up to +500m at rim

# Outside crater (drop off slightly from rim, then flat)
outside = dist > 1.0
dem[outside] = 500 * np.exp(-(dist[outside] - 1.0) * 3)

# 1. Macro Terrain (Rolling Hills)
# Combine a few sine waves based on lat/lon to create large ridges and valleys
dem += 150 * np.sin(lon_grid * 5) * np.cos(lat_grid * 10)
dem += 100 * np.sin(lon_grid * 15 + lat_grid * 5)
dem += 50 * np.sin(lat_grid * 30)

# 2. Micro Terrain (Regolith Roughness)
np.random.seed(42)
# White noise gets smoothed out by downsampling, so we use a coarse grid and interpolate
from scipy.ndimage import zoom
coarse_noise = np.random.normal(0, 150, (n_rows//4, n_cols//4))
smooth_noise = zoom(coarse_noise, 4)[:n_rows, :n_cols]
dem += smooth_noise

# 3. Add random impact craters (to make it look like the moon)
for _ in range(60):
    c_lat = np.random.uniform(lat_max, lat_min)
    c_lon = np.random.uniform(lon_min, lon_max)
    c_rad = np.random.uniform(0.05, 0.4) # radius in degrees
    c_depth = np.random.uniform(100, 500)
    
    c_dist = np.sqrt(((lat_grid - c_lat) / c_rad)**2 + ((lon_grid - c_lon) / c_rad)**2)
    c_mask = c_dist <= 1.0
    # Bowl shape for small craters
    dem[c_mask] -= c_depth * (1 - c_dist[c_mask]**2)
    # Add crater rim
    rim_mask = (c_dist > 1.0) & (c_dist < 1.2)
    dem[rim_mask] += (c_depth * 0.2) * (1.2 - c_dist[rim_mask])

# F2 sub-crater depression
f2_lat, f2_lon = -87.39, 82.31
f2_dist = np.sqrt(((lat_grid - f2_lat) / (5.0/30.32))**2 + ((lon_grid - f2_lon) / (5.0/1.43))**2)
f2_mask = f2_dist <= 1.0
dem[f2_mask] -= 300 * (1 - f2_dist[f2_mask]**2)
rim_f2 = (f2_dist > 1.0) & (f2_dist < 1.1)
dem[rim_f2] += 100 * (1.1 - f2_dist[rim_f2])

# Save as GeoTIFF
transform = from_bounds(lon_min, lat_min, lon_max, lat_max, n_cols, n_rows)
with rasterio.open(
    DEM_PATH, 'w', driver='GTiff',
    height=n_rows, width=n_cols, count=1,
    dtype='float32', crs=CRS.from_epsg(4326),
    transform=transform, nodata=np.nan
) as dst:
    dst.write(dem, 1)

print(f"Success! Saved synthetic DEM to {DEM_PATH}")
