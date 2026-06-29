"""
Micro-Task 2: Peek at the HH band SRI TIFF file.
Prints data type, dimensions, value range, and coordinate system.
No processing, no modifications — just reading and reporting.
"""
import rasterio
import numpy as np

tiff_path = "/Users/gauranshtripathi/Documents/ISRO Project/Data/ch2_sar_ncxl_20191105t180525404_d_fp_m65/data/calibrated/20191105/ch2_sar_ncxl_20191105t180525404_d_sri_xx_fp_hh_m65.tif"

with rasterio.open(tiff_path) as src:
    data = src.read(1)  # Read band 1
    print("=== DFSAR SRI HH Band — Peek Report ===")
    print(f"Dimensions     : {src.height} lines x {src.width} pixels")
    print(f"Data type      : {src.dtypes[0]}")
    print(f"CRS            : {src.crs}")
    print(f"Pixel min      : {np.min(data)}")
    print(f"Pixel max      : {np.max(data)}")
    print(f"Pixel mean     : {np.mean(data):.2f}")
    print(f"Zero pixels    : {np.sum(data == 0)} out of {data.size}")
    print(f"Bounds         : {src.bounds}")
    print(f"Pixel size     : {src.res}")
    print("========================================")
