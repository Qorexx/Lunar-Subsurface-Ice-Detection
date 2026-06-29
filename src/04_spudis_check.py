"""
04_spudis_check.py
==================
ISRO Hackathon — Problem Statement 8: Lunar Subsurface Ice Detection
Phase 1: False Positive Mitigation (Spudis Exterior Rim Check)

PURPOSE:
    Differentiate true subsurface ice from young, rocky impact craters.
    High CPR (Circular Polarization Ratio) can be caused by both volumetric
    ice and rough rocky ejecta. However, rocky ejecta typically spills outside
    the crater rim, while subsurface ice in doubly shadowed craters is confined
    to the cold interior.

APPROACH:
    1. Define the Faustini crater rim boundary (Lat: -87.3, Lon: 82.0, R: 19 km).
    2. Calculate the distance from each of our 1,090 ice candidates to this center.
    3. Split candidates into "Interior" (<= 19 km) and "Exterior" (> 19 km).
    4. If candidates exist outside the rim, it suggests rocky ejecta. If they are
       strictly inside, it confirms the ice signal.

AUTHOR: ISRO Hackathon Team
DATE:   2026-06-26
"""

import os
import math
import pandas as pd
import numpy as np

# =============================================================================
# 1. CONFIGURATION
# =============================================================================

# Faustini Crater parameters (Main Crater)
FAUSTINI_LAT = -87.3
FAUSTINI_LON = 82.0
RIM_RADIUS_KM = 19.0

# Moon volumetric mean radius (km)
R_MOON_KM = 1737.4

INPUT_CSV = os.path.join(
    "/Users/gauranshtripathi/Documents/ISRO Project/Data",
    "ice_candidates", "ice_candidates.csv"
)

# =============================================================================
# 2. HELPER FUNCTIONS
# =============================================================================

def haversine_distance(lat1, lon1, lat2, lon2, radius=R_MOON_KM):
    """
    Calculate the great circle distance between two points 
    on a sphere given their longitudes and latitudes.
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1 
    dlon = lon2 - lon1 
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a)) 
    
    return radius * c

# =============================================================================
# 3. MAIN EXECUTION
# =============================================================================

def main():
    print("=" * 60)
    print("Spudis Exterior Rim Check (False Positive Mitigation)")
    print("=" * 60)
    print(f"Target: Faustini Crater (Lat: {FAUSTINI_LAT}, Lon: {FAUSTINI_LON})")
    print(f"Rim Radius: {RIM_RADIUS_KM} km")
    print()

    # Load candidates
    if not os.path.exists(INPUT_CSV):
        print(f"ERROR: Could not find {INPUT_CSV}")
        return

    df = pd.read_csv(INPUT_CSV)
    total_candidates = len(df)
    print(f"Loaded {total_candidates:,} ice candidate pixels.")

    # Calculate distance for each candidate
    distances = []
    for _, row in df.iterrows():
        dist = haversine_distance(
            FAUSTINI_LAT, FAUSTINI_LON, 
            row['Latitude(deg)'], row['Longitude(deg)']
        )
        distances.append(dist)
    
    df['Distance_to_Center_km'] = distances

    # Split into Interior and Exterior
    interior_df = df[df['Distance_to_Center_km'] <= RIM_RADIUS_KM]
    exterior_df = df[df['Distance_to_Center_km'] > RIM_RADIUS_KM]

    n_interior = len(interior_df)
    n_exterior = len(exterior_df)

    # Print results
    print("-" * 60)
    print("RESULTS:")
    print(f"  Interior Candidates (<= {RIM_RADIUS_KM} km): {n_interior:,}")
    print(f"  Exterior Candidates (> {RIM_RADIUS_KM} km) : {n_exterior:,}")
    print("-" * 60)
    print()

    # Scientific Validation Conclusion
    print("CONCLUSION:")
    if n_exterior > 0:
        pct_exterior = (n_exterior / total_candidates) * 100
        print(f"  ⚠️ WARNING: {n_exterior} pixels ({pct_exterior:.1f}%) were found OUTSIDE the crater rim.")
        
        if pct_exterior > 10:
            print("  This suggests the high CPR signal might be heavily influenced by rocky ejecta")
            print("  or a fresh impact crater, casting doubt on the volumetric ice hypothesis.")
        else:
            print("  A small number of exterior pixels may be noise, but requires manual inspection.")
    else:
        print("  ✅ ICE SIGNAL CONFIRMED: 100% of the high-CPR/low-DOP pixels are confined")
        print("  strictly within the Faustini crater interior.")
        print("  This passes the Spudis sanity check, strongly indicating true subsurface")
        print("  volumetric ice rather than surface roughness from rocky ejecta.")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
