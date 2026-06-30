import rasterio
from rasterio.windows import from_bounds
import numpy as np

url = "https://planetarymaps.usgs.gov/mosaic/Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif"
print("Attempting to connect to COG...")
try:
    with rasterio.open(url) as src:
        print(f"Success! CRS: {src.crs}, Bounds: {src.bounds}")
        # Faustini approx bounds: lon 70 to 93, lat -87.8 to -87.0
        # Wait, global is usually lon 0-360 or -180 to 180, lat -90 to 90.
        window = from_bounds(70, -87.8, 93, -87.0, src.transform)
        print(f"Calculated Window: {window}")
        data = src.read(1, window=window)
        print(f"Read data shape: {data.shape}, Min elev: {np.nanmin(data)}, Max elev: {np.nanmax(data)}")
except Exception as e:
    print(f"Error: {e}")
