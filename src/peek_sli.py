"""
Step 2: Peek at the SLI (complex) HH file.
Verify data type, dimensions, and value ranges of the complex I/Q data.
"""
import rasterio
import numpy as np

sli_path = "/Users/gauranshtripathi/Documents/ISRO Project/Data/ch2_sar_ncxl_20191105t180525404_d_fp_m65/data/calibrated/20191105/ch2_sar_ncxl_20191105t180525404_d_sli_xx_fp_hh_m65.tif"

with rasterio.open(sli_path) as src:
    print("=== SLI HH Band — Peek Report ===")
    print(f"Band count     : {src.count}")
    print(f"Dimensions     : {src.height} lines x {src.width} pixels")
    print(f"Data types     : {src.dtypes}")
    print(f"CRS            : {src.crs}")
    print(f"Bounds         : {src.bounds}")
    print(f"Pixel size     : {src.res}")
    print()

    # Read all bands to understand the complex structure
    for band_idx in range(1, src.count + 1):
        data = src.read(band_idx)
        print(f"  Band {band_idx}:")
        print(f"    Shape      : {data.shape}")
        print(f"    Dtype      : {data.dtype}")
        print(f"    Min        : {np.min(data):.6f}")
        print(f"    Max        : {np.max(data):.6f}")
        print(f"    Mean       : {np.mean(data):.6f}")
        print(f"    Zeros      : {np.sum(data == 0)} / {data.size}")
        print()

print("=== File size check ===")
import os
file_size_mb = os.path.getsize(sli_path) / (1024 * 1024)
print(f"File size: {file_size_mb:.1f} MB")
expected_complex_size = 57880 * 512 * 8  # 8 bytes per complex pixel
print(f"Expected data size (57880 x 512 x 8 bytes): {expected_complex_size / (1024*1024):.1f} MB")
print("========================================")
