"""
07_3d_visualization.py
======================
ISRO Hackathon — Final 3D Mission Integration

Loads NASA's real OBJ terrain mesh of Faustini Crater,
projects CPR/DOP heatmap onto the surface,
marks doubly shadowed crater regions in red,
plots all ice candidates as glowing markers,
and includes landing site + rover path hooks.
"""

import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import math

# =============================================================================
# 1. CONFIGURATION
# =============================================================================

DATA_DIR = "/Users/gauranshtripathi/Documents/ISRO Project/ICE Detection/Data"
DEM_DIR = os.path.join(DATA_DIR, "dem")
ICE_CSV = os.path.join(DATA_DIR, "ice_candidates", "ice_candidates.csv")
OUTPUT_HTML = os.path.join(DATA_DIR, "interactive_crater.html")

# Bounding box from Moon Trek OBJ export
OBJ_LON_MIN, OBJ_LON_MAX = 67.4943, 102.4096
OBJ_LAT_MIN, OBJ_LAT_MAX = -87.7853, -86.4307

GRID_SIZE = 400
R_MOON_KM = 1737.4

# Faustini Crater center and rim
FAUSTINI_LAT, FAUSTINI_LON = -87.3, 82.0
FAUSTINI_RIM_KM = 19.0

# F2 sub-crater (primary doubly shadowed crater)
F2_LAT, F2_LON = -87.39, 82.31
F2_RADIUS_KM = 5.0

# Doubly shadowed regions are the deepest depressions within Faustini.
# From the elevation data, the crater floor (Z < 0) represents the PSR,
# and the deepest zones (Z < -5) are the doubly shadowed regions.
DSC_Z_THRESHOLD = -5.0  # Elevation units below which = doubly shadowed

# =============================================================================
# 2. COORDINATE TRANSFORMS
# =============================================================================

def latlon_to_grid(lat, lon):
    """Convert lat/lon to OBJ grid XY (0-399)."""
    gx = (lon - OBJ_LON_MIN) / (OBJ_LON_MAX - OBJ_LON_MIN) * (GRID_SIZE - 1)
    gy = (OBJ_LAT_MAX - lat) / (OBJ_LAT_MAX - OBJ_LAT_MIN) * (GRID_SIZE - 1)
    return gx, gy

def grid_to_latlon(gx, gy):
    """Convert OBJ grid XY back to lat/lon for teammates."""
    lon = OBJ_LON_MIN + (gx / (GRID_SIZE - 1)) * (OBJ_LON_MAX - OBJ_LON_MIN)
    lat = OBJ_LAT_MAX - (gy / (GRID_SIZE - 1)) * (OBJ_LAT_MAX - OBJ_LAT_MIN)
    return lat, lon

def haversine_distance(lat1, lon1, lat2, lon2):
    """Great circle distance on the Moon in km."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return R_MOON_KM * 2 * math.asin(math.sqrt(a))

def get_surface_z(gx, gy):
    """Get terrain Z at a grid coordinate."""
    ix = max(0, min(int(round(gx)), GRID_SIZE - 1))
    iy = max(0, min(int(round(gy)), GRID_SIZE - 1))
    return grid_z[iy, ix]

# =============================================================================
# 3. LOAD DATA
# =============================================================================
print("=" * 60)
print("Loading terrain grid...")
grid_x = np.load(os.path.join(DEM_DIR, "grid_x.npy"))
grid_y = np.load(os.path.join(DEM_DIR, "grid_y.npy"))
grid_z = np.load(os.path.join(DEM_DIR, "grid_z.npy"))

# Use FULL resolution (no downsampling) for maximum detail
x_mesh, y_mesh = np.meshgrid(grid_x, grid_y)
print(f"  Grid: {grid_z.shape[0]}x{grid_z.shape[1]} = {grid_z.size:,} points")
print(f"  Z range: {grid_z.min():.1f} to {grid_z.max():.1f}")

print("Loading ice candidates...")
ice_df = pd.read_csv(ICE_CSV)
print(f"  Total in CSV: {len(ice_df)}")

# =============================================================================
# 4. IDENTIFY DOUBLY SHADOWED REGIONS
# =============================================================================
print("Identifying doubly shadowed crater regions...")

# Build a mask of which grid cells are inside Faustini's rim
faustini_mask = np.zeros_like(grid_z, dtype=bool)
for i in range(GRID_SIZE):
    for j in range(GRID_SIZE):
        lat, lon = grid_to_latlon(grid_x[j], grid_y[i])
        dist = haversine_distance(FAUSTINI_LAT, FAUSTINI_LON, lat, lon)
        if dist <= FAUSTINI_RIM_KM:
            faustini_mask[i, j] = True

# Doubly shadowed = inside Faustini AND below the depth threshold
dsc_mask = faustini_mask & (grid_z < DSC_Z_THRESHOLD)
print(f"  Faustini interior pixels: {faustini_mask.sum():,}")
print(f"  Doubly shadowed pixels (Z < {DSC_Z_THRESHOLD}): {dsc_mask.sum():,}")

# =============================================================================
# 5. MAP ICE CANDIDATES TO GRID
# =============================================================================
print("Mapping ice candidates to terrain...")

ice_gx, ice_gy, ice_gz, ice_cpr_vals, ice_dop_vals = [], [], [], [], []
ice_lats, ice_lons = [], []

for _, row in ice_df.iterrows():
    gx, gy = latlon_to_grid(row['Latitude(deg)'], row['Longitude(deg)'])
    if 0 <= gx < GRID_SIZE and 0 <= gy < GRID_SIZE:
        gz = get_surface_z(gx, gy) + 0.3
        ice_gx.append(gx)
        ice_gy.append(gy)
        ice_gz.append(gz)
        ice_cpr_vals.append(row['CPR'])
        ice_dop_vals.append(row['DOP'])
        ice_lats.append(row['Latitude(deg)'])
        ice_lons.append(row['Longitude(deg)'])

print(f"  Mapped: {len(ice_gx)} / {len(ice_df)} candidates")

# =============================================================================
# 6. BUILD SURFACE COLOR ARRAY
# =============================================================================
print("Building surface colors...")

# Color encoding:
#   0.0       = Gray lunar rock (outside crater)
#   0.01-0.14 = Dark gray (crater interior, not doubly shadowed)
#   0.15-0.29 = RED (doubly shadowed regions)
#   0.30-1.00 = Blue→Cyan (ice CPR heatmap)

color_grid = np.zeros_like(grid_z)

# Mark crater interior as slightly different shade
color_grid[faustini_mask] = 0.07

# Mark doubly shadowed regions
color_grid[dsc_mask] = 0.22

# Paint ice CPR heatmap (overrides DSC red where ice exists)
cpr_min = min(ice_cpr_vals) if ice_cpr_vals else 1.0
cpr_max = max(ice_cpr_vals) if ice_cpr_vals else 1.3

for gx, gy, cpr_val in zip(ice_gx, ice_gy, ice_cpr_vals):
    si, sj = int(round(gy)), int(round(gx))
    radius = 3
    for di in range(-radius, radius + 1):
        for dj in range(-radius, radius + 1):
            ni, nj = si + di, sj + dj
            if 0 <= ni < GRID_SIZE and 0 <= nj < GRID_SIZE:
                norm_cpr = 0.4 + 0.6 * ((cpr_val - cpr_min) / (cpr_max - cpr_min + 1e-6))
                if norm_cpr > color_grid[ni, nj]:
                    color_grid[ni, nj] = norm_cpr

# Custom colorscale with distinct regions
terrain_colorscale = [
    [0.00, 'rgb(90, 90, 100)'],      # Outside: gray rock
    [0.06, 'rgb(90, 90, 100)'],      
    [0.07, 'rgb(60, 60, 75)'],       # Crater interior: darker gray
    [0.14, 'rgb(60, 60, 75)'],       
    [0.15, 'rgb(120, 20, 20)'],      # DSC start: dark red
    [0.29, 'rgb(200, 40, 40)'],      # DSC strong: bright red
    [0.30, 'rgb(200, 40, 40)'],      # Transition
    [0.40, 'rgb(0, 60, 160)'],       # Weak ice: dark blue
    [0.65, 'rgb(0, 160, 255)'],      # Medium ice: blue
    [1.00, 'rgb(0, 255, 255)'],      # Strong ice: bright cyan
]

# =============================================================================
# 7. BUILD PLOTLY FIGURE
# =============================================================================
print("Building 3D scene...")
fig = go.Figure()

# --- Terrain surface with DSC + Ice heatmap ---
# Build hover text with lat/lon for teammates
hover_text = np.empty(grid_z.shape, dtype=object)
for i in range(GRID_SIZE):
    for j in range(GRID_SIZE):
        lat, lon = grid_to_latlon(grid_x[j], grid_y[i])
        region = "Rock"
        if dsc_mask[i, j]:
            region = "DOUBLY SHADOWED"
        elif faustini_mask[i, j]:
            region = "Crater Interior (PSR)"
        hover_text[i, j] = (
            f"Lat: {lat:.4f}°<br>"
            f"Lon: {lon:.4f}°<br>"
            f"Elev: {grid_z[i,j]:.1f}<br>"
            f"Region: {region}"
        )

fig.add_trace(go.Surface(
    x=x_mesh, y=y_mesh, z=grid_z,
    surfacecolor=color_grid,
    colorscale=terrain_colorscale,
    cmin=0, cmax=1,
    showscale=False,
    name="Terrain",
    lighting=dict(ambient=0.5, diffuse=0.7, roughness=0.8, specular=0.15, fresnel=0.1),
    lightposition=dict(x=500, y=500, z=1000),
    text=hover_text,
    hoverinfo='text',
))

# --- Ice Candidates (glowing scatter) ---
if ice_gx:
    ice_hover = [
        f"Lat: {lat:.4f}°<br>Lon: {lon:.4f}°<br>CPR: {cpr:.3f}<br>DOP: {dop:.4f}"
        for lat, lon, cpr, dop in zip(ice_lats, ice_lons, ice_cpr_vals, ice_dop_vals)
    ]
    fig.add_trace(go.Scatter3d(
        x=ice_gx, y=ice_gy, z=ice_gz,
        mode='markers',
        marker=dict(
            size=3,
            color=ice_cpr_vals,
            colorscale='ice',
            cmin=cpr_min, cmax=cpr_max,
            colorbar=dict(
                title=dict(text="CPR", font=dict(color='white', size=12)),
                x=1.02, len=0.35, y=0.75,
                tickfont=dict(color='white', size=10)
            ),
            opacity=0.9,
            line=dict(width=0)
        ),
        text=ice_hover,
        hoverinfo='text',
        name=f"Ice Candidates ({len(ice_gx)})",
    ))

# --- F2 Sub-crater Marker ---
f2_gx, f2_gy = latlon_to_grid(F2_LAT, F2_LON)
f2_gz = get_surface_z(f2_gx, f2_gy) + 0.8
fig.add_trace(go.Scatter3d(
    x=[f2_gx], y=[f2_gy], z=[f2_gz],
    mode='markers+text',
    marker=dict(size=8, color='red', symbol='cross'),
    text=["F2 (Primary DSC)"],
    textposition="top center",
    textfont=dict(size=12, color='red'),
    name="F2 Sub-crater"
))

# --- TEAMMATE HOOKS ---
def add_landing_site(lat, lon, label="Landing Site"):
    gx, gy = latlon_to_grid(lat, lon)
    gz = get_surface_z(gx, gy) + 0.5
    fig.add_trace(go.Scatter3d(
        x=[gx], y=[gy], z=[gz],
        mode='markers+text',
        marker=dict(size=10, color='yellow', symbol='diamond'),
        text=[label], textposition="top center",
        textfont=dict(size=14, color='yellow'),
        name="Lander"
    ))

def add_rover_path(path_arr):
    # path_arr contains grid coordinates (row, col) = (y, x)
    xs, ys, zs = [], [], []
    for row, col in path_arr:
        gz = get_surface_z(col, row) + 0.2
        xs.append(col); ys.append(row); zs.append(gz)
    fig.add_trace(go.Scatter3d(
        x=xs, y=ys, z=zs,
        mode='lines+markers',
        line=dict(color='#ff00ff', width=6),
        marker=dict(size=3, color='#ff00ff'),
        name="Rover Path (A* Optimal)"
    ))

# Load the A* computed path
try:
    rover_path_pixels = np.load(os.path.join(DATA_DIR, "..", "..", "Rover Path", "output", "rover_path_pixels.npy"))
    start_row, start_col = rover_path_pixels[0]
    landing_lat, landing_lon = grid_to_latlon(start_col, start_row)
    
    add_landing_site(landing_lat, landing_lon, label="Landing Site (Temp)")
    add_rover_path(rover_path_pixels)
except Exception as e:
    print(f"Warning: Could not load A* path ({e}), using fallback.")
    # Placeholder (teammates replace these)
    add_landing_site(-87.15, 82.0)
    add_rover_path([(200, 200)]) # Fallback to F2


# =============================================================================
# 8. LAYOUT
# =============================================================================
fig.update_layout(
    title=dict(
        text="ISRO Hackathon: Faustini Crater — Subsurface Ice & Doubly Shadowed Regions",
        font=dict(size=16, color='white')
    ),
    scene=dict(
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        zaxis=dict(visible=False),
        aspectmode='manual',
        aspectratio=dict(x=1, y=1, z=0.15),
        bgcolor='rgb(5, 5, 15)',
        camera=dict(
            eye=dict(x=0.8, y=-1.2, z=0.6),
            up=dict(x=0, y=0, z=1)
        )
    ),
    paper_bgcolor='rgb(5, 5, 15)',
    font=dict(color='white'),
    margin=dict(l=0, r=0, b=0, t=50),
    legend=dict(x=0.78, y=0.95, bgcolor='rgba(0,0,0,0.6)',
                bordercolor='rgba(255,255,255,0.2)', borderwidth=1,
                font=dict(size=11))
)

# Add annotation explaining the color legend
fig.add_annotation(
    text=(
        "<b>Color Legend:</b><br>"
        "<span style='color:rgb(90,90,100)'>■</span> Lunar Rock<br>"
        "<span style='color:rgb(60,60,75)'>■</span> Crater Interior (PSR)<br>"
        "<span style='color:rgb(200,40,40)'>■</span> Doubly Shadowed (DSC)<br>"
        "<span style='color:rgb(0,255,255)'>■</span> Ice Detection (CPR)"
    ),
    x=0.02, y=0.15,
    xref='paper', yref='paper',
    showarrow=False,
    font=dict(size=12, color='white'),
    bgcolor='rgba(0,0,0,0.6)',
    bordercolor='rgba(255,255,255,0.2)',
    borderwidth=1,
    align='left'
)

print(f"Exporting to {OUTPUT_HTML}...")
fig.write_html(OUTPUT_HTML, include_plotlyjs='cdn')
print("=" * 60)
print("Done! Open interactive_crater.html in your browser.")
print(f"  Ice candidates plotted: {len(ice_gx)} / {len(ice_df)}")
print(f"  Doubly shadowed pixels: {dsc_mask.sum():,}")
print(f"  Missing (out of OBJ bounds): {len(ice_df) - len(ice_gx)}")
print("=" * 60)
