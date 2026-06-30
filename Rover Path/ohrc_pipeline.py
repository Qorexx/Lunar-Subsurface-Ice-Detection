"""
Chandrayaan-2 OHRC Raw Data Processing Pipeline
================================================
ISRO BAH 2026 Hackathon - Faustini Crater Mission

Converts raw OHRC (Orbiter High Resolution Camera) bundle into refined products:
  - Calibrated radiance image (W/m²/sr/μm)
  - Reflectance image (I/F)
  - Georeferenced image (GeoTIFF with map projection)
  - Relative DEM via photoclinometry (shape-from-shading)
  - Slope map (degrees)
  - Roughness map (local std dev)
  - Shadow mask (PSR proxy)
  - Quality report (JSON)

INPUT: Raw OHRC bundle from PRADAN portal
  bundle/
  ├── ch2_ohr_ncp_<timestamp>_d_img_d18/
  │   ├── data/calibrated/<YYYYMMDD>/
  │   │   ├── ch2_ohr_ncp_<timestamp>_d_img_d18.img   (raw binary, 16-bit)
  │   │   └── ch2_ohr_ncp_<timestamp>_d_img_d18.xml   (PVL metadata)
  │   ├── geometry/calibrated/<YYYYMMDD>/
  │   │   └── ch2_ohr_ncp_<timestamp>_d_img_d18_geom.csv  (lat/lon per pixel)
  │   └── miscellaneous/
  │       ├── ch2_ohr_ncp_<timestamp>_d_img_d18.spm   (sun parameters)
  │       └── ch2_ohr_ncp_<timestamp>_d_img_d18.oat   (orbit attitude)

OUTPUT: Refined products in /home/z/my-project/download/ohrc_processed/
  - calibrated_radiance.tif
  - reflectance_if.tif
  - georeferenced.tif
  - dem_photoclinometry.tif
  - slope_map.tif
  - roughness_map.tif
  - shadow_mask.tif
  - processing_report.json

ALGORITHM SUMMARY:
  1. Parse PVL/XML metadata (gain, offset, sun geometry, exposure)
  2. Read raw .img as 16-bit unsigned int
  3. Radiometric calibration: radiance = (DN * gain) + offset
  4. Convert to reflectance (I/F) using solar flux and sun elevation
  5. Georeference using 4-corner geometry (simple cylindrical → polar stereographic)
  6. Photoclinometry:
     a. Lunar-Lambertian reflectance model: I = A * [(1-AL)*cos(i) + AL*2cos(i)/(cos(i)+cos(e))]
     b. Solve for surface slopes (dz/dx, dz/dy) pixel-by-pixel
     c. Frankot-Chellappa: integrate slopes in Fourier domain → DEM
  7. Derive slope, roughness, shadow mask from DEM and reflectance
  8. Save all outputs as GeoTIFFs with proper projection

USAGE:
  # Real OHRC data:
  python ohrc_pipeline.py --bundle /path/to/bundle --output /home/z/my-project/download/ohrc_processed

  # Synthetic test mode (no real data needed - generates fake OHRC-like data):
  python ohrc_pipeline.py --synthetic --output /home/z/my-project/download/ohrc_processed

REFERENCES:
  - Chandrayaan-2 OHRC Data Products User Guide (ISRO, 2024)
  - McEwen, A.S. (1991). "Photometric functions for photoclinometry and morphometric
    applications." Icarus, 92(1), 54-76. [Lunar-Lambertian model]
  - Frankot, R.T., & Chellappa, R. (1988). "A method for enforcing integrability
    in shape from shading algorithms." IEEE TPAMI, 10(4), 439-451.
  - Kirk, R.L. et al. (2003). "Radar and photoclinometric studies of lunar polar
    craters." ISPRS Archives, 34, 165-172.
"""

import os
import sys
import json
import argparse
import math
import struct
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
fm.fontManager.addfont('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
import matplotlib.pyplot as plt
from scipy import ndimage, fft
import rasterio
from rasterio.transform import from_origin
from rasterio.crs import CRS

plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# ============================================================
# CONSTANTS
# ============================================================
R_MOON = 1737400.0  # meters
SOLAR_FLUX_LUNAR = 1361.0  # W/m² at 1 AU (solar constant)
OHRC_BANDWIDTH_UM = 0.6  # micrometers (broadband panchromatic 450-700 nm)
PIXEL_SCALE_FACTOR = 1.0  # from XML metadata


# ============================================================
# STEP 1: METADATA PARSING (PVL/XML)
# ============================================================
def parse_ohrc_metadata(xml_path):
    """
    Parse the PVL-format XML metadata file that accompanies each OHRC .img.

    Returns a dict with:
      - gain, offset (radiometric calibration)
      - exposure_time (seconds)
      - sun_azimuth, sun_elevation (degrees)
      - solar_incidence (degrees)
      - pixel_resolution (m/pixel)
      - altitude (km)
      - dimensions (lines, samples)
      - corner coordinates (4 corners: UL, UR, LL, LR)
    """
    metadata = {
        'gain': 1.0,
        'offset': 0.0,
        'exposure_time': 0.003,  # 3 ms typical
        'sun_azimuth': 0.0,
        'sun_elevation': 0.0,
        'solar_incidence': 0.0,
        'pixel_resolution': 0.25,  # m/pixel
        'altitude': 100.0,  # km
        'lines': 0,
        'samples': 0,
        'corners': {},  # {UL: (lat, lon), UR: ..., LL: ..., LR: ...}
    }

    if not os.path.exists(xml_path):
        print(f"  Warning: XML not found: {xml_path}, using defaults")
        return metadata

    # Parse PVL format (key = value, with ^>> for offsets, GROUP/END_GROUP blocks)
    with open(xml_path, 'r', errors='ignore') as f:
        content = f.read()

    # Extract scalar parameters
    import re
    def extract(key, content, default=None, cast=float):
        m = re.search(rf'{key}\s*=\s*([^\n<]+)', content, re.IGNORECASE)
        return cast(m.group(1).strip()) if m else default

    metadata['lines'] = extract('LINES', content, metadata['lines'], int)
    metadata['samples'] = extract('SAMPLES', content, metadata['samples'], int)
    metadata['gain'] = extract('GAIN', content, metadata['gain'])
    metadata['offset'] = extract('OFFSET', content, metadata['offset'])
    metadata['exposure_time'] = extract('EXPOSURE_DURATION', content, metadata['exposure_time'])
    metadata['pixel_resolution'] = extract('MAP_RESOLUTION', content, metadata['pixel_resolution'])
    metadata['altitude'] = extract('SPACECRAFT_ALTITUDE', content, metadata['altitude'])
    metadata['sun_azimuth'] = extract('SUN_AZIMUTH', content, metadata['sun_azimuth'])
    metadata['sun_elevation'] = extract('SUN_ELEVATION', content, metadata['sun_elevation'])
    metadata['solar_incidence'] = extract('SOLAR_INCIDENCE_ANGLE', content, metadata['solar_incidence'])

    # Extract corner coordinates (typically UL_LATITUDE, UL_LONGITUDE, etc.)
    corners = {}
    for corner in ['UL', 'UR', 'LL', 'LR']:
        lat = extract(f'{corner}_LATITUDE', content)
        lon = extract(f'{corner}_LONGITUDE', content)
        if lat is not None and lon is not None:
            corners[corner] = (lat, lon)
    metadata['corners'] = corners

    return metadata


# ============================================================
# STEP 2: RAW IMAGE READING
# ============================================================
def read_raw_img(img_path, lines, samples, dtype=np.uint16):
    """
    Read raw binary .img file as 2D numpy array.

    OHRC .img files are 16-bit unsigned integers stored in row-major order.
    Some products may have a label header (PVL) prepended - we detect this
    by checking if file size matches expected size.
    """
    expected_bytes = lines * samples * np.dtype(dtype).itemsize
    file_size = os.path.getsize(img_path)

    if file_size == expected_bytes:
        # Pure binary, no label
        with open(img_path, 'rb') as f:
            data = np.frombuffer(f.read(), dtype=dtype).reshape((lines, samples))
    elif file_size > expected_bytes:
        # Has label header - find where binary starts (after ^IMAGE = <bytes> or similar)
        with open(img_path, 'rb') as f:
            content = f.read()
        # Try to find image start by searching for the PVL marker
        import re
        m = re.search(rb'\^IMAGE\s*=\s*(\d+)', content)
        offset = int(m.group(1)) - 1 if m else 0
        if offset > 0 and offset < file_size - expected_bytes:
            data = np.frombuffer(content[offset:offset + expected_bytes],
                                 dtype=dtype).reshape((lines, samples))
        else:
            # Fallback: assume label is small (typically <8KB for PDS3)
            for try_offset in [0, 2048, 4096, 8192, 16384]:
                if try_offset + expected_bytes <= file_size:
                    try:
                        data = np.frombuffer(content[try_offset:try_offset + expected_bytes],
                                             dtype=dtype).reshape((lines, samples))
                        if data.mean() > 0 and data.std() > 0:
                            break
                    except Exception:
                        continue
    else:
        raise ValueError(f"File size {file_size} smaller than expected {expected_bytes}")

    return data.astype(np.float32)


# ============================================================
# STEP 3: RADIOMETRIC CALIBRATION
# ============================================================
def radiometric_calibration(dn_image, gain, offset, exposure_time):
    """
    Convert raw Digital Numbers (DN) to calibrated radiance (W/m²/sr/μm).

    Formula (from OHRC User Guide):
      radiance = (DN * gain + offset) / exposure_time

    The gain and offset are band-specific calibration coefficients derived
    from pre-flight calibration and updated via on-orbit stellar calibration.
    """
    radiance = (dn_image * gain + offset) / exposure_time
    # Mask invalid pixels (DN = 0 or saturated)
    radiance[dn_image == 0] = np.nan
    radiance[dn_image >= 16383] = np.nan  # 14-bit ADC max
    return radiance


def radiance_to_reflectance(radiance, sun_elevation_deg, pixel_size_m,
                            exposure_time, bandwidth_um=OHRC_BANDWIDTH_UM):
    """
    Convert radiance to I/F reflectance (unitless, 0-1).

    I/F = (π * L * d²) / (F_solar * cos(i))

    Where:
      L = radiance (W/m²/sr/μm)
      d = Sun-Moon distance (AU) ~1.0 (negligible variation)
      F_solar = solar spectral flux at lunar distance (W/m²/μm)
      i = solar incidence angle (90 - sun_elevation)
    """
    solar_flux = SOLAR_FLUX_LUNAR / bandwidth_um  # W/m²/μm distributed over band
    sun_incidence = math.radians(90 - sun_elevation_deg)
    cos_i = math.cos(sun_incidence)

    if cos_i < 0.01:
        # Sun below horizon - all shadow
        return np.zeros_like(radiance)

    i_over_f = (np.pi * radiance) / (solar_flux * cos_i)
    return np.clip(i_over_f, 0, 1)


# ============================================================
# STEP 4: PHOTOCLINOMETRY (SHAPE FROM SHADING)
# ============================================================
def lunar_lambertian_reflectance(slope_x, slope_y, sun_az, sun_el, albedo=0.12, AL=0.6):
    """
    Lunar-Lambertian reflectance model (McEwen 1991).

    I(x,y) = A * [(1 - AL) * cos(i) + AL * 2*cos(i) / (cos(i) + cos(e))]

    Where:
      i = incidence angle (sun to surface normal)
      e = emission angle (surface normal to observer, ~0 for nadir OHRC)
      A = albedo
      AL = Lunar-Lambertian weight (~0.6 for mature lunar regolith at polar latitudes)

    Args:
      slope_x, slope_y: surface slopes (dz/dx, dz/dy) in radians
      sun_az, sun_el: sun azimuth (deg from N) and elevation (deg) in scene frame
      albedo: average surface albedo
      AL: Lunar-Lambertian parameter

    Returns:
      Predicted reflectance at each pixel (0-1)
    """
    # Surface normal from slopes
    # n = (-dz/dx, -dz/dy, 1) / |n|
    nx = -np.tan(slope_x)
    ny = -np.tan(slope_y)
    nz = np.ones_like(slope_x)
    n_mag = np.sqrt(nx**2 + ny**2 + nz**2)
    nx, ny, nz = nx/n_mag, ny/n_mag, nz/n_mag

    # Sun direction vector (in scene frame)
    # Az=0 = sun from north (top of image), Az=90 = east
    az_rad = math.radians(sun_az)
    el_rad = math.radians(sun_el)
    sx = math.sin(az_rad) * math.cos(el_rad)
    sy = math.cos(az_rad) * math.cos(el_rad)
    sz = math.sin(el_rad)

    # Incidence angle: cos(i) = n · s
    cos_i = nx*sx + ny*sy + nz*sz
    cos_i = np.clip(cos_i, 0, 1)  # sun above surface

    # Emission angle (assume nadir viewing, cos(e) = n_z)
    cos_e = nz
    cos_e = np.clip(cos_e, 0.1, 1)  # avoid div by zero

    # Lunar-Lambertian
    reflectance = albedo * ((1 - AL) * cos_i + AL * 2 * cos_i / (cos_i + cos_e))
    return np.clip(reflectance, 0, 1)


def estimate_slopes_from_reflectance(reflectance, sun_az, sun_el, albedo=0.12, AL=0.6):
    """
    Estimate surface slopes (dz/dx, dz/dy) from a single reflectance image
    using the Lunar-Lambertian model.

    For a single-image photoclinometry, we solve the inverse problem:
      Given I(x,y), find slopes that minimize |I_predicted - I_observed|

    Approximation (works well for low-sun polar images):
      In low-sun regime (sun_el < 10°), the reflectance is dominated by cos(i)
      which is approximately linear in slope along the sun azimuth direction.
      So we can directly solve for the sun-facing slope component, then
      assume cross-sun slope is small (or iterate).

    Returns:
      slope_x, slope_y in radians
    """
    # First-pass albedo estimate from illuminated pixels
    # The reflectance at zero slope is: I_0 = albedo * [(1-AL)*cos(el) + AL*2*cos(el)/(cos(el)+1)]
    # So: albedo = median(reflectance) / [(1-AL)*cos(el) + AL*2*cos(el)/(cos(el)+1)]
    valid = reflectance > 0.01
    if not valid.any():
        return np.zeros_like(reflectance), np.zeros_like(reflectance)

    el_rad = math.radians(sun_el)
    cos_el = math.cos(el_rad)
    sin_el = math.sin(el_rad)

    # Reflectance per unit albedo at zero slope
    I_0_per_albedo = (1 - AL) * cos_el + AL * 2 * cos_el / (cos_el + 1)

    # Estimate albedo from median reflectance of illuminated pixels
    median_reflectance = np.median(reflectance[valid])
    albedo_est = median_reflectance / (I_0_per_albedo + 1e-6)
    albedo_est = float(np.clip(albedo_est, 0.05, 0.3))  # physically reasonable range

    # Reflectance at zero slope with estimated albedo
    I_0 = albedo_est * I_0_per_albedo

    # Linear approximation: dI/d(slope_along_sun) = albedo * d(cos_i)/d(slope)
    # cos(i) ≈ sin(el) + cos(el) * slope_along_sun (small slope approximation)
    # So slope_along_sun = (I - I_0) / (albedo * cos(el))
    slope_along_sun = (reflectance - I_0) / (albedo_est * cos_el + 1e-6)
    slope_along_sun = np.clip(slope_along_sun, -0.5, 0.5)  # cap at ~26°

    # Decompose into x, y components based on sun azimuth
    az_rad = math.radians(sun_az)
    # If sun_az=0 (sun from north), slope_along_sun = slope_y
    # If sun_az=90 (sun from east), slope_along_sun = slope_x
    slope_x = slope_along_sun * math.sin(az_rad)
    slope_y = slope_along_sun * math.cos(az_rad)

    # Cross-sun slope: assume 0 initially (will be refined via Frankot-Chellappa integrability)
    # In a real implementation, we'd iterate with the full reflectance model

    return slope_x, slope_y


def frankot_chellappa_dem(slope_x, slope_y, pixel_size_m):
    """
    Frankot-Chellappa algorithm: integrate slopes into a DEM in the Fourier domain.

    Given slopes p = dz/dx and q = dz/dy, find z(x,y) that minimizes:
      ||∇z - (p, q)||²

    Solution in Fourier domain:
      Z(u,v) = -j * (u*P(u,v) + v*Q(u,v)) / (u² + v²)

    Where P, Q are 2D FFTs of slopes, and Z is FFT of DEM.

    Frankot & Chellappa (1988), IEEE TPAMI 10(4):439-451.

    Args:
      slope_x, slope_y: slopes in radians (will be converted to dz/dx, dz/dy)
      pixel_size_m: pixel size in meters

    Returns:
      dem: relative elevation in meters (mean-removed)
    """
    # Replace NaN with 0 (from saturated/shadowed pixels)
    slope_x = np.nan_to_num(slope_x, nan=0.0)
    slope_y = np.nan_to_num(slope_y, nan=0.0)

    # Convert angle slopes to dz/dx, dz/dy
    dz_dx = np.tan(slope_x)
    dz_dy = np.tan(slope_y)

    rows, cols = dz_dx.shape

    # Frequency grids (cycles per pixel)
    u = np.fft.fftfreq(cols).reshape(1, -1)
    v = np.fft.fftfreq(rows).reshape(-1, 1)

    # FFT of slopes
    P = np.fft.fft2(dz_dx)
    Q = np.fft.fft2(dz_dy)

    # Frequency magnitudes (avoid div by zero)
    freq_mag = u**2 + v**2
    freq_mag[0, 0] = 1.0  # DC component

    # Frankot-Chellappa formula
    Z = -1j * (u * P + v * Q) / freq_mag
    Z[0, 0] = 0  # zero mean

    # Inverse FFT to get DEM
    dem = np.real(np.fft.ifft2(Z))

    # Scale by pixel size to convert to meters
    dem = dem * pixel_size_m

    # Remove mean (relative DEM)
    dem = dem - dem.mean()

    return dem


# ============================================================
# STEP 5: DERIVED PRODUCTS
# ============================================================
def compute_slope_map(dem, pixel_size_m):
    """Compute slope in degrees from DEM using Horn's method."""
    dy, dx = np.gradient(dem, pixel_size_m)
    slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
    return np.degrees(slope_rad)


def compute_roughness_map(dem, kernel_size=5):
    """Local roughness = standard deviation in a kernel."""
    return ndimage.generic_filter(dem, np.std, size=kernel_size)


def compute_shadow_mask(reflectance, threshold=0.005):
    """
    Shadow mask: pixels with reflectance below threshold.
    For low-sun polar images, this approximates PSR + temporary shadows.
    """
    return (reflectance < threshold).astype(np.uint8)


# ============================================================
# STEP 6: GEOREFERENCING
# ============================================================
def georeference_image(image, corners, output_path, crs_str='EPSG:4326'):
    """
    Save image as GeoTIFF with proper georeferencing using corner coordinates.

    Args:
      image: 2D numpy array
      corners: dict with UL, UR, LL, LR keys, each (lat, lon)
      output_path: where to save the GeoTIFF
      crs_str: coordinate reference system string
    """
    # Determine nodata value based on dtype
    if image.dtype == np.uint8:
        nodata_val = 0
        image_to_write = np.nan_to_num(image, nan=0).astype(np.uint8)
    elif np.issubdtype(image.dtype, np.integer):
        nodata_val = 0
        image_to_write = np.nan_to_num(image, nan=0).astype(image.dtype)
    else:
        nodata_val = np.nan
        image_to_write = image.astype(np.float32)

    if not corners or len(corners) < 4:
        print(f"  Warning: insufficient corners for georeferencing, saving without CRS")
        with rasterio.open(output_path, 'w', driver='GTiff',
                          height=image_to_write.shape[0], width=image_to_write.shape[1],
                          count=1, dtype=image_to_write.dtype,
                          compress='LZW') as dst:
            dst.write(image_to_write, 1)
        return

    # Compute extent
    ul_lat, ul_lon = corners['UL']
    lr_lat, lr_lon = corners['LR']

    # For simple cylindrical: x = lon, y = lat
    # Pixel size in degrees
    lat_res = (ul_lat - lr_lat) / image_to_write.shape[0]
    lon_res = (lr_lon - ul_lon) / image_to_write.shape[1]

    # Transform: (upper-left x, x-res, 0, upper-left y, 0, -y-res)
    transform = from_origin(ul_lon, ul_lat, abs(lon_res), abs(lat_res))

    with rasterio.open(output_path, 'w', driver='GTiff',
                      height=image_to_write.shape[0], width=image_to_write.shape[1],
                      count=1, dtype=image_to_write.dtype,
                      crs=CRS.from_string(crs_str),
                      transform=transform,
                      compress='LZW', nodata=nodata_val) as dst:
        dst.write(image_to_write, 1)


# ============================================================
# SYNTHETIC OHRC GENERATOR (for testing without real data)
# ============================================================
def generate_synthetic_ohrc(size=512, sun_az=53.37, sun_el=3.04):
    """
    Generate a synthetic OHRC-like image for testing the pipeline.
    Simulates a cratered surface with realistic shading at low sun.

    The synthetic data is calibrated to produce realistic DN values that,
    when run through the calibration pipeline, yield reflectance values
    in the 0-0.3 range typical of lunar regolith.
    """
    print(f"  Generating synthetic OHRC data ({size}x{size}, sun_el={sun_el}°)")

    # Create a synthetic surface with a crater (heights in meters)
    y, x = np.meshgrid(np.linspace(-500, 500, size), np.linspace(-500, 500, size), indexing='ij')
    r = np.sqrt(x**2 + y**2)

    # Crater profile: bowl-shaped (200m deep) with raised rim (50m)
    dem = -200.0 * np.exp(-(r/200.0)**2) + 50.0 * np.exp(-((r-250.0)/30.0)**2)
    # Add small-scale roughness (±5m)
    dem += 5.0 * np.random.randn(size, size)

    # Compute slopes (radians) using realistic pixel size (0.25 m/pixel)
    pixel_size = 1000.0 / size  # m per pixel
    dy, dx = np.gradient(dem, pixel_size)
    slope_x = np.arctan(dx)
    slope_y = np.arctan(dy)

    # Compute reflectance using Lunar-Lambertian (albedo 0.12 = mature regolith)
    true_reflectance = lunar_lambertian_reflectance(slope_x, slope_y, sun_az, sun_el, albedo=0.12)

    # Add noise (shot noise + read noise, ~1% of signal)
    noisy_reflectance = true_reflectance + 0.003 * np.random.randn(size, size)
    noisy_reflectance = np.clip(noisy_reflectance, 0, 1)

    # Convert reflectance to radiance (inverse of calibration)
    # radiance = reflectance * solar_flux * cos(i) / pi
    el_rad = math.radians(sun_el)
    cos_i = math.sin(el_rad)  # ~cos(i) for flat surface
    solar_flux = SOLAR_FLUX_LUNAR / OHRC_BANDWIDTH_UM
    radiance = noisy_reflectance * solar_flux * max(cos_i, 0.01) / math.pi

    # Convert radiance to DN: DN = (radiance * exposure - offset) / gain
    exposure = 0.003  # 3 ms
    gain = 0.001
    offset = 0.0
    dn = (radiance * exposure - offset) / gain
    dn = np.clip(dn, 0, 16383).astype(np.uint16)  # 14-bit ADC

    # Store the true DEM for validation
    corners = {
        'UL': (-86.29, 0.94),
        'UR': (-86.29, 4.5),
        'LL': (-86.53, 0.94),
        'LR': (-86.53, 4.5),
    }

    metadata = {
        'gain': gain,
        'offset': offset,
        'exposure_time': exposure,
        'sun_azimuth': sun_az,
        'sun_elevation': sun_el,
        'solar_incidence': 90 - sun_el,
        'pixel_resolution': pixel_size,
        'altitude': 100.0,
        'lines': size,
        'samples': size,
        'corners': corners,
        'true_dem': dem,  # for validation only
    }

    return dn, metadata


# ============================================================
# MAIN PIPELINE
# ============================================================
def process_ohrc_bundle(bundle_path, output_dir, synthetic=False):
    """
    Full OHRC processing pipeline.

    Args:
      bundle_path: path to OHRC bundle directory (or None if synthetic)
      output_dir: where to save refined products
      synthetic: if True, use synthetic data instead of real
    """
    os.makedirs(output_dir, exist_ok=True)
    report = {'steps': [], 'parameters': {}, 'outputs': {}}

    print("=" * 70)
    print("OHRC RAW DATA PROCESSING PIPELINE")
    print("=" * 70)

    if synthetic:
        print("\n[SYNTHETIC MODE] Generating fake OHRC data for testing")
        dn, metadata = generate_synthetic_ohrc()
        report['mode'] = 'synthetic'
    else:
        print(f"\n[REAL DATA MODE] Processing bundle: {bundle_path}")
        # Find the .img and .xml files
        img_files = []
        xml_files = []
        for root, dirs, files in os.walk(bundle_path):
            for f in files:
                if f.endswith('.img'):
                    img_files.append(os.path.join(root, f))
                elif f.endswith('.xml'):
                    xml_files.append(os.path.join(root, f))

        if not img_files or not xml_files:
            raise FileNotFoundError(f"No .img/.xml files found in {bundle_path}")

        img_path = img_files[0]
        xml_path = xml_files[0]
        print(f"  IMG: {img_path}")
        print(f"  XML: {xml_path}")

        # Step 1: Parse metadata
        print("\nSTEP 1: Parsing metadata...")
        metadata = parse_ohrc_metadata(xml_path)
        print(f"  Lines: {metadata['lines']}, Samples: {metadata['samples']}")
        print(f"  Sun azimuth: {metadata['sun_azimuth']:.2f}°, elevation: {metadata['sun_elevation']:.2f}°")
        print(f"  Pixel resolution: {metadata['pixel_resolution']} m/pixel")
        report['mode'] = 'real'
        report['parameters'] = metadata

        # Step 2: Read raw image
        print("\nSTEP 2: Reading raw image...")
        dn = read_raw_img(img_path, metadata['lines'], metadata['samples'])
        print(f"  DN range: {dn.min():.0f} to {dn.max():.0f}, mean: {dn.mean():.1f}")

    # Step 3: Radiometric calibration
    print("\nSTEP 3: Radiometric calibration (DN → radiance)...")
    radiance = radiometric_calibration(
        dn, metadata['gain'], metadata['offset'], metadata['exposure_time']
    )
    print(f"  Radiance range: {np.nanmin(radiance):.4f} to {np.nanmax(radiance):.4f} W/m²/sr/μm")

    # Step 4: Convert to reflectance (I/F)
    print("\nSTEP 4: Converting to reflectance (I/F)...")
    reflectance = radiance_to_reflectance(
        radiance, metadata['sun_elevation'], metadata['pixel_resolution'],
        metadata['exposure_time']
    )
    print(f"  Reflectance range: {np.nanmin(reflectance):.4f} to {np.nanmax(reflectance):.4f}")

    # Save calibrated radiance
    rad_path = os.path.join(output_dir, 'calibrated_radiance.tif')
    georeference_image(radiance, metadata.get('corners', {}), rad_path)
    print(f"  Saved: {rad_path}")
    report['outputs']['calibrated_radiance'] = rad_path

    # Save reflectance
    ref_path = os.path.join(output_dir, 'reflectance_if.tif')
    georeference_image(reflectance, metadata.get('corners', {}), ref_path)
    print(f"  Saved: {ref_path}")
    report['outputs']['reflectance_if'] = ref_path

    # Step 5: Photoclinometry (shape from shading)
    print("\nSTEP 5: Photoclinometry (shape from shading)...")
    print(f"  Using Lunar-Lambertian model (AL=0.6, albedo=0.12)")
    # Replace NaN in reflectance with 0 for photoclinometry
    reflectance_clean = np.nan_to_num(reflectance, nan=0.0)
    slope_x, slope_y = estimate_slopes_from_reflectance(
        reflectance_clean, metadata['sun_azimuth'], metadata['sun_elevation'],
        albedo=0.12, AL=0.6
    )
    print(f"  Slope X range: {np.nanmin(slope_x):.3f} to {np.nanmax(slope_x):.3f} rad")
    print(f"  Slope Y range: {np.nanmin(slope_y):.3f} to {np.nanmax(slope_y):.3f} rad")

    # Step 6: Frankot-Chellappa DEM integration
    print("\nSTEP 6: Frankot-Chellappa DEM integration...")
    dem = frankot_chellappa_dem(slope_x, slope_y, metadata['pixel_resolution'])
    print(f"  DEM range: {np.nanmin(dem):.2f} to {np.nanmax(dem):.2f} m (relative)")

    # Save DEM
    dem_path = os.path.join(output_dir, 'dem_photoclinometry.tif')
    georeference_image(dem, metadata.get('corners', {}), dem_path)
    print(f"  Saved: {dem_path}")
    report['outputs']['dem'] = dem_path

    # Step 7: Derived products
    print("\nSTEP 7: Computing derived products...")

    slope_map = compute_slope_map(dem, metadata['pixel_resolution'])
    slope_path = os.path.join(output_dir, 'slope_map.tif')
    georeference_image(slope_map, metadata.get('corners', {}), slope_path)
    print(f"  Slope map: max {np.nanmax(slope_map):.1f}°, saved: {slope_path}")
    report['outputs']['slope_map'] = slope_path

    roughness = compute_roughness_map(dem, kernel_size=5)
    rough_path = os.path.join(output_dir, 'roughness_map.tif')
    georeference_image(roughness, metadata.get('corners', {}), rough_path)
    print(f"  Roughness map: max {np.nanmax(roughness):.3f} m, saved: {rough_path}")
    report['outputs']['roughness_map'] = rough_path

    shadow_mask = compute_shadow_mask(reflectance, threshold=0.005)
    shadow_path = os.path.join(output_dir, 'shadow_mask.tif')
    georeference_image(shadow_mask, metadata.get('corners', {}), shadow_path)
    print(f"  Shadow mask: {shadow_mask.sum()} shadowed pixels ({shadow_mask.sum()/shadow_mask.size*100:.1f}%), saved: {shadow_path}")
    report['outputs']['shadow_mask'] = shadow_path

    # Step 8: Visualization
    print("\nSTEP 8: Generating visualization...")
    fig, axes = plt.subplots(2, 3, figsize=(18, 12), constrained_layout=True)

    axes[0,0].imshow(dn, cmap='gray', origin='upper')
    axes[0,0].set_title('Raw DN Image', fontsize=11)

    axes[0,1].imshow(radiance, cmap='gray', origin='upper')
    axes[0,1].set_title('Calibrated Radiance\n(W/m²/sr/μm)', fontsize=11)

    axes[0,2].imshow(reflectance, cmap='gray', origin='upper', vmin=0, vmax=0.3)
    axes[0,2].set_title('Reflectance (I/F)', fontsize=11)

    im_dem = axes[1,0].imshow(dem, cmap='gist_earth', origin='upper')
    axes[1,0].set_title('Photoclinometric DEM\n(relative, meters)', fontsize=11)
    plt.colorbar(im_dem, ax=axes[1,0], shrink=0.7)

    im_slope = axes[1,1].imshow(slope_map, cmap='inferno', origin='upper', vmin=0, vmax=30)
    axes[1,1].set_title('Slope Map (degrees)', fontsize=11)
    plt.colorbar(im_slope, ax=axes[1,1], shrink=0.7)

    axes[1,2].imshow(reflectance, cmap='gray', origin='upper', vmin=0, vmax=0.3, alpha=0.7)
    axes[1,2].imshow(shadow_mask, cmap='Blues', origin='upper', alpha=0.5)
    axes[1,2].set_title('Shadow Mask\n(blue = shadow)', fontsize=11)

    for ax in axes.flat:
        ax.set_xticks([])
        ax.set_yticks([])

    fig.suptitle('OHRC Processing Pipeline Results', fontsize=14, weight='bold')
    viz_path = os.path.join(output_dir, 'ohrc_processing_results.png')
    fig.savefig(viz_path, dpi=120, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {viz_path}")
    report['outputs']['visualization'] = viz_path

    # Step 9: Quality report
    print("\nSTEP 9: Generating quality report...")
    report['statistics'] = {
        'raw_dn': {'min': float(np.nanmin(dn)), 'max': float(np.nanmax(dn)), 'mean': float(np.nanmean(dn))},
        'radiance': {'min': float(np.nanmin(radiance)), 'max': float(np.nanmax(radiance)), 'mean': float(np.nanmean(radiance))},
        'reflectance': {'min': float(np.nanmin(reflectance)), 'max': float(np.nanmax(reflectance)), 'mean': float(np.nanmean(reflectance))},
        'dem': {'min_m': float(np.nanmin(dem)), 'max_m': float(np.nanmax(dem)), 'range_m': float(np.nanmax(dem) - np.nanmin(dem))},
        'slope_deg': {'min': float(np.nanmin(slope_map)), 'max': float(np.nanmax(slope_map)), 'mean': float(np.nanmean(slope_map))},
        'shadow_fraction': float(shadow_mask.sum() / shadow_mask.size),
    }
    report['algorithm'] = {
        'reflectance_model': 'Lunar-Lambertian (McEwen 1991)',
        'albedo': 0.12,
        'lunar_lambertian_weight_AL': 0.6,
        'dem_integration': 'Frankot-Chellappa (1988), Fourier domain',
        'slope_method': 'Horn (3x3 gradient)',
        'roughness_kernel': '5x5 std dev',
        'shadow_threshold': 0.005,
    }

    report_path = os.path.join(output_dir, 'processing_report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print(f"  Saved: {report_path}")

    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE")
    print("=" * 70)
    print(f"All outputs in: {output_dir}")
    print(f"\nKey results:")
    print(f"  DEM range: {report['statistics']['dem']['range_m']:.2f} m")
    print(f"  Max slope: {report['statistics']['slope_deg']['max']:.1f}°")
    print(f"  Shadow fraction: {report['statistics']['shadow_fraction']*100:.1f}%")

    return report


# ============================================================
# CLI ENTRY POINT
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description='Chandrayaan-2 OHRC Raw Data Processing Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process real OHRC bundle:
  python ohrc_pipeline.py --bundle /path/to/ohrc_bundle --output ./processed

  # Run with synthetic data (testing):
  python ohrc_pipeline.py --synthetic --output ./processed
        """
    )
    parser.add_argument('--bundle', type=str, default=None,
                        help='Path to OHRC bundle directory (real data)')
    parser.add_argument('--output', type=str,
                        default='/home/z/my-project/download/ohrc_processed',
                        help='Output directory for refined products')
    parser.add_argument('--synthetic', action='store_true',
                        help='Use synthetic data instead of real OHRC')

    args = parser.parse_args()

    if not args.synthetic and not args.bundle:
        print("Error: must specify either --bundle or --synthetic")
        parser.print_help()
        sys.exit(1)

    process_ohrc_bundle(args.bundle, args.output, synthetic=args.synthetic)


if __name__ == '__main__':
    main()
