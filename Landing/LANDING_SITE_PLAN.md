# Landing Site Selection — Implementation Plan for Teammate A

## Current Status: What You've Done

✅ **Notebook 01** — OHRC data loaded (101,074 × 12,000 @ 0.2m/px), useful illuminated region identified (rows 76,039–92,483), shadow detection (71.4%), surface roughness via entropy.

✅ **Notebook 02** — Image tiled into 192 crops (1000×1000 px), filtered to 89 useful crops with actual terrain.

⚠️ **Notebook 03** — `extract_features()` function is **defined but never called**. No feature table exists yet.

---

## What's Missing (4 Steps)

### Step 1: Run Feature Extraction on All 89 Crops (~20 min)

Your `extract_features()` function in Notebook 03 is ready. You just need to loop it over the filtered crops and build a table.

```python
import numpy as np
import pandas as pd

# Load your data
filtered_crops = np.load(PROCESSED_DATA / "filtered_crops.npy")
filtered_locations = np.load(PROCESSED_DATA / "filtered_locations.npy")

# Run feature extraction on all crops
results = []
for i, (crop, loc) in enumerate(zip(filtered_crops, filtered_locations)):
    features = extract_features(crop)
    features['crop_id'] = i
    features['pixel_row'] = loc[0]    # top-left row of the crop in the full image
    features['pixel_col'] = loc[1]    # top-left col of the crop in the full image
    results.append(features)

df = pd.DataFrame(results)
print(df.describe())
df.to_csv(PROCESSED_DATA / "crop_features.csv", index=False)
```

**Expected output:** A CSV with 89 rows, each having: `mean_brightness`, `std_brightness`, `shadow_percentage`, `roughness`, `max_slope_proxy`, `pixel_row`, `pixel_col`.

---

### Step 2: Score & Rank Landing Site Candidates (~30 min)

Create a composite **Landing Safety Score** for each crop. A good landing site needs:
- **Low shadow** (solar power for the lander)
- **Low roughness** (fewer boulders)
- **Low slope** (safe touchdown)
- **Moderate brightness** (not too dark = not permanently shadowed)

```python
# Normalize each feature to 0-1 range
df['shadow_norm'] = df['shadow_percentage'] / 100
df['roughness_norm'] = df['roughness'] / df['roughness'].max()
df['slope_norm'] = df['max_slope_proxy'] / df['max_slope_proxy'].max()

# Landing Safety Score (higher = safer)
# We WANT: low shadow, low roughness, low slope
df['landing_score'] = (
    0.40 * (1 - df['shadow_norm']) +      # 40% weight: needs sunlight
    0.30 * (1 - df['roughness_norm']) +    # 30% weight: smooth surface
    0.30 * (1 - df['slope_norm'])          # 30% weight: flat terrain
)

# Rank
df_ranked = df.sort_values('landing_score', ascending=False)
print("\nTop 10 Landing Candidates:")
print(df_ranked[['crop_id', 'shadow_percentage', 'roughness', 'max_slope_proxy', 'landing_score']].head(10))

# Save
df_ranked.to_csv(PROCESSED_DATA / "landing_candidates_ranked.csv", index=False)
```

**Hard filter** — eliminate any crop with:
- `shadow_percentage > 80%` (too dark for solar power)
- `max_slope_proxy > 0.3` (too steep for safe landing, roughly > 15°)

```python
safe = df_ranked[
    (df_ranked['shadow_percentage'] < 80) &
    (df_ranked['max_slope_proxy'] < 0.3)
]
print(f"\nSafe candidates: {len(safe)} out of {len(df_ranked)}")
```

---

### Step 3: Geolocate Best Candidate to Lat/Lon (~30 min)

This is the critical step. Your crops are pixel indices in the OHRC image. You need to convert the best crop's position to actual lunar coordinates.

**Option A: If your OHRC XML has corner coordinates**

```python
# From your XML metadata (you already parsed these in Notebook 01)
# Check for UL_LATITUDE, UL_LONGITUDE, LR_LATITUDE, LR_LONGITUDE
# These give you the bounding box of the OHRC strip

# Example (replace with your actual values from the XML):
ul_lat = -86.5   # upper-left latitude
ul_lon = 75.0    # upper-left longitude
lr_lat = -88.0   # lower-right latitude
lr_lon = 90.0    # lower-right longitude

total_lines = 101074
total_samples = 12000

# For the best candidate crop:
best = safe.iloc[0]
crop_center_row = best['pixel_row'] + 500   # center of 1000px crop
crop_center_col = best['pixel_col'] + 500

# Linear interpolation (simple cylindrical approximation)
landing_lat = ul_lat + (crop_center_row / total_lines) * (lr_lat - ul_lat)
landing_lon = ul_lon + (crop_center_col / total_samples) * (lr_lon - ul_lon)

print(f"Landing Site: Lat {landing_lat:.4f}°, Lon {landing_lon:.4f}°")
```

**Option B: If you have the geometry CSV**

Check if there's a `*_geom.csv` in your OHRC bundle. If so, it maps pixel positions to lat/lon directly (same approach we used for the DFSAR data).

---

### Step 4: Output Final Coordinates (~10 min)

Once you have the landing site lat/lon, save it and **send the coordinates to Gauransh** so he can plot it on the 3D render.

```python
landing_site = {
    'latitude': landing_lat,
    'longitude': landing_lon,
    'crop_id': int(best['crop_id']),
    'landing_score': float(best['landing_score']),
    'shadow_percentage': float(best['shadow_percentage']),
    'roughness': float(best['roughness']),
    'max_slope_proxy': float(best['max_slope_proxy']),
    'justification': 'Lowest shadow + roughness + slope composite score among 89 OHRC crops'
}

import json
with open(PROCESSED_DATA / "landing_site_final.json", 'w') as f:
    json.dump(landing_site, f, indent=2)

print(f"\n{'='*50}")
print(f"FINAL LANDING SITE")
print(f"{'='*50}")
print(f"Latitude:  {landing_lat:.4f}°")
print(f"Longitude: {landing_lon:.4f}°")
print(f"Score:     {best['landing_score']:.3f}")
print(f"\nSEND THESE COORDINATES TO GAURANSH")
```

---

## Constraints to Keep in Mind

1. **Must be on or near the Faustini crater rim** — the lander needs sunlight, so it can't land inside the permanently shadowed crater floor.
2. **Faustini center:** Lat -87.3°, Lon 82.0°, Rim radius ~19 km.
3. **The landing site should face the crater interior** — the rover needs to descend from the rim into the crater to reach the ice at F2 (Lat -87.39°, Lon 82.31°).
4. **Earth visibility** — for communication, the landing site ideally has line-of-sight to Earth. Near the south pole this is intermittent, so don't over-optimize for this.

## What Gauransh Needs From You

> **Just two numbers: `latitude` and `longitude` of the final landing site.**
> 
> Text/WhatsApp them as soon as you have them.
> He'll plug them into the 3D render and run the rover path from your landing site to the F2 ice target.

## Estimated Time: ~1.5 hours total
