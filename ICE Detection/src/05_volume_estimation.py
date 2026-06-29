"""
05_volume_estimation.py
=======================
ISRO Hackathon — Problem Statement 8: Lunar Subsurface Ice Detection
Phase 1: Volume Estimation

PURPOSE:
    Estimate the total potential volume and mass of subsurface water-ice
    within the Faustini Crater.

APPROACH:
    1. Load the 1,090 ice candidates from Phase 1.
    2. Filter to the 995 candidates mathematically confirmed to be inside 
       the crater (Spudis Exterior Rim Check - Distance <= 19 km).
    3. Calculate total surface area based on the multi-looked pixel resolution
       (~24.05 m x 28.78 m = ~692.16 m^2 per pixel).
    4. Calculate total volume using the standard L-band radar penetration depth 
       of 5.0 meters.
    5. Apply conservative (10%) and optimistic (40%) ice fraction/porosity 
       factors to estimate the actual water-ice volume.
    6. Convert volume to Metric Tonnes (assuming ice density of 919 kg/m^3).

AUTHOR: ISRO Hackathon Team
DATE:   2026-06-29
"""

import os
import math
import pandas as pd

# =============================================================================
# 1. CONFIGURATION & CONSTANTS
# =============================================================================

INPUT_CSV = os.path.join(
    "/Users/gauranshtripathi/Documents/ISRO Project/ICE Detection/Data",
    "ice_candidates", "ice_candidates.csv"
)

# Faustini Crater parameters for Spudis Check
FAUSTINI_LAT = -87.3
FAUSTINI_LON = 82.0
RIM_RADIUS_KM = 19.0
R_MOON_KM = 1737.4

# Multi-looked pixel dimensions (from 02_compute_cpr_dop.py config)
PIXEL_AZIMUTH_M = 24.04984
PIXEL_RANGE_M = 28.780077
AREA_PER_PIXEL_M2 = PIXEL_AZIMUTH_M * PIXEL_RANGE_M  # ~692.16 m^2

# Scientific Assumptions
PENETRATION_DEPTH_M = 5.0
ICE_FRACTION_LOWER = 0.10  # 10%
ICE_FRACTION_UPPER = 0.40  # 40%
ICE_DENSITY_KG_M3 = 919.0  # Density of ice at very low temperatures

# =============================================================================
# 2. HELPER FUNCTIONS
# =============================================================================

def haversine_distance(lat1, lon1, lat2, lon2, radius=R_MOON_KM):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1 
    dlon = lon2 - lon1 
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a)) 
    return radius * c

# =============================================================================
# 3. MAIN EXECUTION
# =============================================================================

def main():
    print("=" * 65)
    print("LUNAR SUBSURFACE ICE VOLUME ESTIMATION (Faustini Crater)")
    print("=" * 65)

    if not os.path.exists(INPUT_CSV):
        print(f"ERROR: Could not find {INPUT_CSV}")
        return

    df = pd.read_csv(INPUT_CSV)
    
    # Re-apply Spudis Check to strictly use confirmed interior pixels
    distances = [haversine_distance(FAUSTINI_LAT, FAUSTINI_LON, row['Latitude(deg)'], row['Longitude(deg)']) for _, row in df.iterrows()]
    df['Distance_km'] = distances
    interior_df = df[df['Distance_km'] <= RIM_RADIUS_KM]
    
    pixel_count = len(interior_df)
    print(f"\n[1] DATA INPUT")
    print(f"  Confirmed Interior Ice Pixels : {pixel_count:,}")
    print(f"  Pixel Resolution (Multi-look) : ~24.0 m x ~28.8 m")
    print(f"  Area per Pixel                : {AREA_PER_PIXEL_M2:.2f} m²")

    # Step 1: Area
    total_area_m2 = pixel_count * AREA_PER_PIXEL_M2
    total_area_km2 = total_area_m2 / 1_000_000
    print(f"\n[2] SURFACE AREA")
    print(f"  Total Ice-bearing Area        : {total_area_m2:,.0f} m² ({total_area_km2:.3f} km²)")

    # Step 2: Total Regolith Volume
    total_regolith_vol_m3 = total_area_m2 * PENETRATION_DEPTH_M
    print(f"\n[3] REGOLITH VOLUME")
    print(f"  Assumed Radar Depth (L-Band)  : {PENETRATION_DEPTH_M} m")
    print(f"  Total Ice-bearing Regolith    : {total_regolith_vol_m3:,.0f} m³")

    # Step 3: Pure Water Ice Volume & Mass
    vol_lower = total_regolith_vol_m3 * ICE_FRACTION_LOWER
    vol_upper = total_regolith_vol_m3 * ICE_FRACTION_UPPER
    
    mass_lower_tonnes = (vol_lower * ICE_DENSITY_KG_M3) / 1000
    mass_upper_tonnes = (vol_upper * ICE_DENSITY_KG_M3) / 1000

    print(f"\n[4] FINAL WATER-ICE ESTIMATES")
    print(f"  Ice Density Used              : {ICE_DENSITY_KG_M3} kg/m³")
    print("-" * 65)
    print(f"  CONSERVATIVE ESTIMATE (10% Ice Fraction):")
    print(f"    Ice Volume : {vol_lower:,.0f} m³")
    print(f"    Ice Mass   : {mass_lower_tonnes:,.0f} Metric Tonnes")
    print()
    print(f"  OPTIMISTIC ESTIMATE (40% Ice Fraction):")
    print(f"    Ice Volume : {vol_upper:,.0f} m³")
    print(f"    Ice Mass   : {mass_upper_tonnes:,.0f} Metric Tonnes")
    print("-" * 65)
    
    print("\nCONCLUSION FOR JUDGES:")
    print(f"The analysis of Chandrayaan-2 DFSAR data strongly indicates the presence")
    print(f"of roughly {mass_lower_tonnes:,.0f} to {mass_upper_tonnes:,.0f} metric tonnes of subsurface")
    print(f"water-ice concentrated within a ~{total_area_km2:.2f} km² area of the Faustini crater.")
    print("=" * 65)

if __name__ == "__main__":
    main()
