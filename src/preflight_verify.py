"""
Pre-flight verification: Peek at the MASK and INCIDENCE ANGLE files,
and check the geometry CSV row count.
"""
import rasterio
import numpy as np

base = "/Users/gauranshtripathi/Documents/ISRO Project/Data/ch2_sar_ncxl_20191105t180525404_d_fp_m65/data/calibrated/20191105/"
geo_csv = "/Users/gauranshtripathi/Documents/ISRO Project/Data/ch2_sar_ncxl_20191105t180525404_d_fp_m65/geometry/calibrated/20191105/ch2_sar_ncxl_20191105t180525404_g_sri_xx_fp_xx_m65.csv"

# Q1: What does the mask file contain?
print("=== Q1: MASK FILE (sri_ma) ===")
with rasterio.open(base + "ch2_sar_ncxl_20191105t180525404_d_sri_ma_fp_xx_m65.tif") as src:
    mask = src.read(1)
    print(f"Shape       : {mask.shape}")
    print(f"Data type   : {src.dtypes[0]}")
    print(f"Unique vals : {np.unique(mask)}")
    print(f"Count of 0  : {np.sum(mask == 0)}")
    print(f"Count of 1  : {np.sum(mask == 1)}")
    print(f"Count other : {np.sum((mask != 0) & (mask != 1))}")
    print()

# Q2: What does the incidence angle file contain?
print("=== Q2: INCIDENCE ANGLE FILE (sri_in) ===")
with rasterio.open(base + "ch2_sar_ncxl_20191105t180525404_d_sri_in_fp_xx_m65.tif") as src:
    inc = src.read(1)
    print(f"Shape       : {inc.shape}")
    print(f"Data type   : {src.dtypes[0]}")
    valid_inc = inc[inc > 0]  # Exclude no-data
    if len(valid_inc) > 0:
        print(f"Min (valid) : {np.min(valid_inc):.4f}")
        print(f"Max (valid) : {np.max(valid_inc):.4f}")
        print(f"Mean(valid) : {np.mean(valid_inc):.4f}")
    print(f"Zero pixels : {np.sum(inc == 0)}")
    print()

# Q3: How many rows in geometry CSV vs pixels in image?
print("=== Q3: GEOMETRY CSV ROW COUNT ===")
with open(geo_csv, 'r') as f:
    lines = f.readlines()
    print(f"Total rows (inc header): {len(lines)}")
    print(f"Data rows              : {len(lines) - 1}")
    print(f"Image pixels           : 1320 x 1239 = {1320 * 1239}")
    print(f"Rows per image line    : {(len(lines) - 1) / 1320:.2f}")
    print(f"Header                 : {lines[0].strip()}")
    print()

# Q4: Also peek at ALL four polarization bands to compare ranges
print("=== Q4: ALL FOUR POLARIZATION BANDS ===")
for pol in ["hh", "hv", "vh", "vv"]:
    fname = f"ch2_sar_ncxl_20191105t180525404_d_sri_xx_fp_{pol}_m65.tif"
    with rasterio.open(base + fname) as src:
        data = src.read(1)
        nonzero = data[data > 0]
        print(f"{pol.upper()}: min={np.min(nonzero):5d}, max={np.max(nonzero):5d}, mean={np.mean(nonzero):8.2f}, nonzero_count={len(nonzero)}")
