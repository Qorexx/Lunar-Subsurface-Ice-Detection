import rasterio
import os
import numpy as np

path = "ICE Detection/Data/dem/faustini_dem.tif"
if not os.path.exists(path):
    print(f"File not found: {path}")
    # let's try to find it in Downloads or elsewhere just in case
else:
    with rasterio.open(path) as src:
        data = src.read(1)
        print(f"Found DEM!")
        print(f"Size: {src.width} x {src.height}")
        print(f"Bounds: {src.bounds}")
        print(f"CRS: {src.crs}")
        print(f"Min Elev: {np.nanmin(data)}")
        print(f"Max Elev: {np.nanmax(data)}")
