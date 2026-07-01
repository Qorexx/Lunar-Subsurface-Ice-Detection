"""
02_AStar_Pathfinder.py
======================
A* optimal pathfinding for lunar rover traversal.

Start: Landing site on Faustini rim (sunlit, flat, closest to ice cluster)
Goal:  Densest ice candidate cluster inside the crater

Cost function considers: slope × shadow × roughness
The path avoids:
  - Steep slopes (> 20°) — impassable
  - Doubly shadowed crater zones — 8x penalty (no solar power)
  - Rough terrain — up to 6x penalty

Elevation change is penalized: uphill costs more than downhill.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import heapq
import math
from pathlib import Path
from scipy.ndimage import uniform_filter

# ────────────────────────────────────────────────────────────
# PATHS & CONSTANTS
# ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "Rover Path" / "output"
ICE_CSV = BASE_DIR / "ICE Detection" / "Data" / "ice_candidates" / "ice_candidates.csv"

OBJ_LON_MIN, OBJ_LON_MAX = 67.4943, 102.4096
OBJ_LAT_MIN, OBJ_LAT_MAX = -87.7853, -86.4307
GRID_SIZE = 400
R_MOON_KM = 1737.4
FAUSTINI_LAT, FAUSTINI_LON = -87.3, 82.0
FAUSTINI_RIM_KM = 19.0
PIXEL_SIZE_M = 100.0

# ────────────────────────────────────────────────────────────
# HELPERS
# ────────────────────────────────────────────────────────────
def latlon_to_grid(lat, lon):
    gx = (lon - OBJ_LON_MIN) / (OBJ_LON_MAX - OBJ_LON_MIN) * (GRID_SIZE - 1)
    gy = (OBJ_LAT_MAX - lat) / (OBJ_LAT_MAX - OBJ_LAT_MIN) * (GRID_SIZE - 1)
    return int(round(gy)), int(round(gx))  # row, col

def grid_to_latlon(row, col):
    lon = OBJ_LON_MIN + (col / (GRID_SIZE - 1)) * (OBJ_LON_MAX - OBJ_LON_MIN)
    lat = OBJ_LAT_MAX - (row / (GRID_SIZE - 1)) * (OBJ_LAT_MAX - OBJ_LAT_MIN)
    return lat, lon

def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R_MOON_KM * 2 * math.asin(math.sqrt(a))

# ────────────────────────────────────────────────────────────
# LOAD DATA
# ────────────────────────────────────────────────────────────
print("=" * 60)
print("Loading data...")
cost_surface = np.load(OUTPUT_DIR / "cost_surface.npy")
grid_z = np.load(BASE_DIR / "ICE Detection" / "Data" / "dem" / "grid_z.npy")
slope_map = np.load(OUTPUT_DIR / "slope_map.npy")
faustini_mask = np.load(OUTPUT_DIR / "faustini_mask.npy")
ice_df = pd.read_csv(ICE_CSV)

# ────────────────────────────────────────────────────────────
# FIND OPTIMAL GOAL: Densest ice cluster INSIDE the crater
# ────────────────────────────────────────────────────────────
print("\nFinding densest ice cluster inside the crater...")

# Map ice candidates onto grid
ice_grid = np.zeros_like(grid_z)
for _, row in ice_df.iterrows():
    r, c = latlon_to_grid(row['Latitude(deg)'], row['Longitude(deg)'])
    if 0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE:
        ice_grid[r, c] += row['CPR']  # Weight by CPR strength

# Smooth with kernel to find cluster center
ice_density = uniform_filter(ice_grid, size=15)

# Only consider ice inside the crater (below rim elevation)
ice_density_interior = ice_density.copy()
ice_density_interior[grid_z > 5] = 0  # Mask out rim/exterior ice

peak = np.unravel_index(ice_density_interior.argmax(), ice_density_interior.shape)
peak_lat, peak_lon = grid_to_latlon(peak[0], peak[1])

GOAL_POS = peak
print(f"  Goal: grid ({peak[0]}, {peak[1]})")
print(f"  Lat/Lon: {peak_lat:.4f}°, {peak_lon:.4f}°")
print(f"  Elevation: {grid_z[peak]:.2f}m")

# ────────────────────────────────────────────────────────────
# FIND OPTIMAL START: Best landing site on the rim
# ────────────────────────────────────────────────────────────
print("\nFinding optimal landing site on the rim...")

# Criteria: on rim (17-22 km from center), sunlit (elev > 10m),
# flat (slope < 2°), closest to ice cluster
best_score = 999999
best_site = None

for i in range(GRID_SIZE):
    for j in range(GRID_SIZE):
        lon = OBJ_LON_MIN + (j / (GRID_SIZE - 1)) * (OBJ_LON_MAX - OBJ_LON_MIN)
        lat = OBJ_LAT_MAX - (i / (GRID_SIZE - 1)) * (OBJ_LAT_MAX - OBJ_LAT_MIN)
        dist_from_center = haversine(FAUSTINI_LAT, FAUSTINI_LON, lat, lon)
        
        # Must be on the rim, sunlit, and flat
        if 17 <= dist_from_center <= 22 and grid_z[i, j] > 10 and slope_map[i, j] < 2.0:
            # Score: distance to ice cluster + slope penalty
            dist_to_ice = np.sqrt((i - GOAL_POS[0])**2 + (j - GOAL_POS[1])**2)
            score = dist_to_ice + slope_map[i, j] * 20
            if score < best_score:
                best_score = score
                best_site = (i, j, lat, lon)

START_POS = (best_site[0], best_site[1])
start_lat, start_lon = best_site[2], best_site[3]
print(f"  Start: grid ({START_POS[0]}, {START_POS[1]})")
print(f"  Lat/Lon: {start_lat:.4f}°, {start_lon:.4f}°")
print(f"  Elevation: {grid_z[START_POS]:.1f}m")
print(f"  Slope: {slope_map[START_POS]:.3f}°")

# ────────────────────────────────────────────────────────────
# A* PATHFINDING
# ────────────────────────────────────────────────────────────
print(f"\nRunning A* pathfinding...")
print(f"  From: ({START_POS[0]}, {START_POS[1]}) → ({GOAL_POS[0]}, {GOAL_POS[1]})")

def heuristic(a, b):
    """Euclidean distance × minimum possible cost per step."""
    return np.sqrt((b[0] - a[0])**2 + (b[1] - a[1])**2) * 1.0

def astar_path(cost_map, elev_map, start, goal):
    rows, cols = cost_map.shape
    
    frontier = []
    heapq.heappush(frontier, (0.0, start))
    
    came_from = {start: None}
    cost_so_far = {start: 0.0}
    
    # 8-directional movement
    neighbors = [(0, 1), (1, 0), (0, -1), (-1, 0),
                 (1, 1), (-1, 1), (1, -1), (-1, -1)]
    
    MAX_COST = 999990
    explored = 0
    
    while frontier:
        _, current = heapq.heappop(frontier)
        explored += 1
        
        if current == goal:
            break
        
        if explored % 10000 == 0:
            print(f"    Explored {explored} nodes...")
        
        for dr, dc in neighbors:
            nr, nc = current[0] + dr, current[1] + dc
            next_node = (nr, nc)
            
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            
            step_cost = cost_map[nr, nc]
            if step_cost >= MAX_COST:
                continue
            
            # Diagonal movement covers more distance
            dist_factor = 1.414 if (dr != 0 and dc != 0) else 1.0
            
            # Elevation change penalty
            z_diff = elev_map[nr, nc] - elev_map[current[0], current[1]]
            # Uphill: penalize proportionally
            # Downhill: slight penalty (steep descent is also risky)
            if z_diff > 0:
                elev_penalty = z_diff * 3.0   # Uphill is expensive
            else:
                elev_penalty = abs(z_diff) * 1.0  # Downhill is cheaper but not free
            
            new_cost = cost_so_far[current] + (step_cost * dist_factor) + elev_penalty
            
            if next_node not in cost_so_far or new_cost < cost_so_far[next_node]:
                cost_so_far[next_node] = new_cost
                priority = new_cost + heuristic(goal, next_node)
                heapq.heappush(frontier, (priority, next_node))
                came_from[next_node] = current
    
    # Reconstruct
    if goal not in came_from:
        print("  NO PATH FOUND!")
        return None, explored
    
    path = []
    current = goal
    while current != start:
        path.append(current)
        current = came_from[current]
    path.append(start)
    path.reverse()
    
    return path, explored

path, explored = astar_path(cost_surface, grid_z, START_POS, GOAL_POS)

if path:
    path_arr = np.array(path)
    
    # Compute path statistics
    total_distance_m = 0
    max_slope_on_path = 0
    elevation_gain = 0
    elevation_loss = 0
    
    for i in range(1, len(path)):
        r1, c1 = path[i-1]
        r2, c2 = path[i]
        # Grid distance
        step_dist = np.sqrt((r2-r1)**2 + (c2-c1)**2) * PIXEL_SIZE_M
        total_distance_m += step_dist
        # Elevation change
        dz = grid_z[r2, c2] - grid_z[r1, c1]
        if dz > 0:
            elevation_gain += dz
        else:
            elevation_loss += abs(dz)
        # Track max slope
        max_slope_on_path = max(max_slope_on_path, slope_map[r2, c2])
    
    print(f"\n  PATH FOUND!")
    print(f"  Nodes explored: {explored:,}")
    print(f"  Path length: {len(path)} waypoints")
    print(f"  Total distance: {total_distance_m:.0f}m ({total_distance_m/1000:.1f} km)")
    print(f"  Elevation gain: +{elevation_gain:.1f}m")
    print(f"  Elevation loss: -{elevation_loss:.1f}m")
    print(f"  Max slope on path: {max_slope_on_path:.2f}°")
    
    # Save
    np.save(OUTPUT_DIR / "rover_path_pixels.npy", path_arr)
    
    # Save path metadata
    import json
    path_meta = {
        'start_grid': [int(START_POS[0]), int(START_POS[1])],
        'goal_grid': [int(GOAL_POS[0]), int(GOAL_POS[1])],
        'start_latlon': [float(start_lat), float(start_lon)],
        'goal_latlon': [float(peak_lat), float(peak_lon)],
        'total_distance_m': float(total_distance_m),
        'total_distance_km': float(total_distance_m / 1000),
        'waypoints': int(len(path)),
        'nodes_explored': int(explored),
        'elevation_gain_m': float(elevation_gain),
        'elevation_loss_m': float(elevation_loss),
        'max_slope_deg': float(max_slope_on_path),
        'algorithm': 'A* with 8-directional movement',
        'cost_factors': 'slope × shadow_penalty × roughness + elevation_change',
    }
    with open(OUTPUT_DIR / "path_metadata.json", 'w') as f:
        json.dump(path_meta, f, indent=2)
    
    # ────────────────────────────────────────────────────────
    # VISUALIZE
    # ────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(18, 8))
    
    # Left: Path on cost surface
    ax = axes[0]
    vis_cost = np.clip(cost_surface, 0, 50)
    ax.imshow(vis_cost, cmap='gray_r', origin='lower', alpha=0.8)
    ax.plot(path_arr[:, 1], path_arr[:, 0], 'r-', linewidth=2.5, label='Rover Path (A*)')
    ax.plot(START_POS[1], START_POS[0], 'g^', markersize=12, label=f'Landing Site', zorder=5)
    ax.plot(GOAL_POS[1], GOAL_POS[0], 'b*', markersize=15, label=f'Ice Target', zorder=5)
    ax.set_title(f'Optimal Rover Path ({total_distance_m/1000:.1f} km)\nA* on Multi-Factor Cost Surface')
    ax.legend(loc='lower left', fontsize=10)
    
    # Right: Elevation profile along the path
    ax = axes[1]
    path_elevations = [grid_z[r, c] for r, c in path]
    path_slopes = [slope_map[r, c] for r, c in path]
    cumulative_dist = [0]
    for i in range(1, len(path)):
        step = np.sqrt((path[i][0]-path[i-1][0])**2 + (path[i][1]-path[i-1][1])**2) * PIXEL_SIZE_M
        cumulative_dist.append(cumulative_dist[-1] + step)
    
    ax.fill_between(cumulative_dist, path_elevations, alpha=0.3, color='steelblue')
    ax.plot(cumulative_dist, path_elevations, 'steelblue', linewidth=2, label='Elevation')
    ax.set_xlabel('Distance along path (m)')
    ax.set_ylabel('Elevation (m)', color='steelblue')
    ax.tick_params(axis='y', labelcolor='steelblue')
    
    ax2 = ax.twinx()
    ax2.plot(cumulative_dist, path_slopes, 'r-', linewidth=1, alpha=0.7, label='Slope')
    ax2.set_ylabel('Slope (degrees)', color='red')
    ax2.tick_params(axis='y', labelcolor='red')
    
    ax.set_title('Elevation & Slope Profile Along Path')
    ax.legend(loc='upper left')
    ax2.legend(loc='upper right')
    
    fig.suptitle('Faustini Crater — Rover Traverse Plan', fontsize=14, weight='bold')
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "rover_path_vis.png", dpi=150)
    print(f"\nSaved: {OUTPUT_DIR / 'rover_path_vis.png'}")
    print("=" * 60)
