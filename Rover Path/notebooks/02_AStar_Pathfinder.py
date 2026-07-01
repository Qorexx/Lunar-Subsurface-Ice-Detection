import numpy as np
import matplotlib.pyplot as plt
import heapq
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "Rover Path" / "output"

print("Loading Cost Surface...")
cost_surface = np.load(OUTPUT_DIR / "cost_surface.npy")
grid_z = np.load(BASE_DIR / "ICE Detection" / "Data" / "dem" / "grid_z.npy")

def heuristic(a, b):
    # Euclidean distance
    return np.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)

def astar_path(cost_map, start, goal):
    """
    A* pathfinding algorithm
    start and goal are tuples of (row, col)
    """
    rows, cols = cost_map.shape
    
    # Priority queue
    frontier = []
    heapq.heappush(frontier, (0, start))
    
    # Track paths
    came_from = {}
    came_from[start] = None
    
    # Track costs
    cost_so_far = {}
    cost_so_far[start] = 0
    
    # 8-way movement: (dr, dc)
    neighbors = [(0, 1), (1, 0), (0, -1), (-1, 0), 
                 (1, 1), (-1, 1), (1, -1), (-1, -1)]
                 
    MAX_COST = 999990
                 
    while len(frontier) > 0:
        current = heapq.heappop(frontier)[1]
        
        if current == goal:
            break
            
        for dr, dc in neighbors:
            next_node = (current[0] + dr, current[1] + dc)
            
            # Check bounds
            if 0 <= next_node[0] < rows and 0 <= next_node[1] < cols:
                
                # Check if impassable
                step_cost = cost_map[next_node]
                if step_cost >= MAX_COST:
                    continue
                
                # Diagonal movement costs more distance
                dist_factor = 1.414 if (dr != 0 and dc != 0) else 1.0
                
                # We penalize uphill movement slightly more than downhill or flat
                z_diff = grid_z[next_node] - grid_z[current]
                elevation_penalty = max(0, z_diff) * 2.0 
                
                new_cost = cost_so_far[current] + (step_cost * dist_factor) + elevation_penalty
                
                if next_node not in cost_so_far or new_cost < cost_so_far[next_node]:
                    cost_so_far[next_node] = new_cost
                    priority = new_cost + heuristic(goal, next_node)
                    heapq.heappush(frontier, (priority, next_node))
                    came_from[next_node] = current
                    
    # Reconstruct path
    path = []
    current = goal
    
    if current not in came_from:
        print("NO PATH FOUND!")
        return None
        
    while current != start:
        path.append(current)
        current = came_from[current]
    path.append(start)
    path.reverse()
    
    return path

# Define Start and End Points
# F2 Ice Target (from our ICE Detection phase)
F2_LAT, F2_LON = -87.39, 82.31

OBJ_LON_MIN, OBJ_LON_MAX = 67.4943, 102.4096
OBJ_LAT_MIN, OBJ_LAT_MAX = -87.7853, -86.4307
GRID_SIZE = 400

def latlon_to_grid(lat, lon):
    gx = (lon - OBJ_LON_MIN) / (OBJ_LON_MAX - OBJ_LON_MIN) * (GRID_SIZE - 1)
    gy = (OBJ_LAT_MAX - lat) / (OBJ_LAT_MAX - OBJ_LAT_MIN) * (GRID_SIZE - 1)
    return int(round(gy)), int(round(gx)) # row, col

GOAL_POS = latlon_to_grid(F2_LAT, F2_LON)

# Temporary Landing Site: Somewhere on the rim (let's pick top right rim)
# We look for a flat spot near the top right corner
rim_zone = cost_surface[300:380, 300:380]
flat_idx = np.unravel_index(np.argmin(rim_zone), rim_zone.shape)
START_POS = (300 + flat_idx[0], 300 + flat_idx[1])

print(f"Goal (F2 Ice): {GOAL_POS}")
print(f"Start (Temp Landing Site): {START_POS}")

print("\nRunning A* Pathfinding (this might take a few seconds)...")
path = astar_path(cost_surface, START_POS, GOAL_POS)

if path:
    print(f"Path found! Length: {len(path)} steps.")
    
    # Convert path list to numpy array for easy slicing
    path_arr = np.array(path)
    np.save(OUTPUT_DIR / "rover_path_pixels.npy", path_arr)
    
    # Visualize
    plt.figure(figsize=(10, 10))
    plt.imshow(np.clip(cost_surface, 0, 30), cmap='gray', origin='lower')
    
    # Plot path
    plt.plot(path_arr[:, 1], path_arr[:, 0], 'r-', linewidth=2, label='Rover Path')
    
    # Plot start and end
    plt.plot(START_POS[1], START_POS[0], 'go', markersize=10, label='Landing Site (Start)')
    plt.plot(GOAL_POS[1], GOAL_POS[0], 'bo', markersize=10, label='F2 Ice Target (Goal)')
    
    plt.title('Optimal Rover Path via A* Algorithm')
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "rover_path_vis.png", dpi=150)
    print(f"Saved visualization to: {OUTPUT_DIR / 'rover_path_vis.png'}")
    print("Step 4 & 5 Complete.")
