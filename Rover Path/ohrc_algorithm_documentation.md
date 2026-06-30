# OHRC Raw Data Processing Algorithm
## Chandrayaan-2 Orbiter High Resolution Camera — From Raw Bundle to Refined Products

**File**: `ohrc_pipeline.py`
**Test command**: `python ohrc_pipeline.py --synthetic --output ./output`
**Real data command**: `python ohrc_pipeline.py --bundle /path/to/ohrc_bundle --output ./output`

---

## Algorithm Overview

The pipeline converts raw OHRC data products (downloaded from ISRO's PRADAN portal) into analysis-ready GeoTIFF products. The processing chain has 9 steps, each documented below with the underlying physics and math.

```
Raw .img (16-bit DN)
      │
      ▼  Step 1-2: Metadata parse + raw read
Raw DN array
      │
      ▼  Step 3: Radiometric calibration
Radiance (W/m²/sr/μm)
      │
      ▼  Step 4: Reflectance conversion (I/F)
Reflectance (0-1, unitless)
      │
      ▼  Step 5: Photoclinometry (Lunar-Lambertian inverse)
Surface slopes (dz/dx, dz/dy in radians)
      │
      ▼  Step 6: Frankot-Chellappa Fourier integration
Relative DEM (meters)
      │
      ▼  Step 7: Derived products
Slope map · Roughness map · Shadow mask
      │
      ▼  Step 8-9: Georeference + save + report
GeoTIFFs + JSON report + visualization PNG
```

---

## Step 1: Metadata Parsing (PVL/XML)

**Input**: `ch2_ohr_ncp_<timestamp>_d_img_d18.xml`
**Format**: PVL (Parameter Value Language), a key=value text format used by PDS3

The metadata file contains everything needed to interpret the raw `.img`:
- `LINES`, `SAMPLES` — image dimensions
- `GAIN`, `OFFSET` — radiometric calibration coefficients
- `EXPOSURE_DURATION` — camera integration time (seconds)
- `SUN_AZIMUTH`, `SUN_ELEVATION` — solar geometry at imaging time
- `SOLAR_INCIDENCE_ANGLE` — 90° − sun elevation
- `MAP_RESOLUTION` — pixel scale (m/pixel)
- `SPACECRAFT_ALTITUDE` — orbital height (km)
- `UL_LATITUDE/LONGITUDE`, `UR_...`, `LL_...`, `LR_...` — four corner coordinates for georeferencing

**Parsing approach**: Regex extraction of `KEY = VALUE` patterns. PVL is line-oriented, so simple regex is sufficient and avoids the overhead of a full PVL parser.

```python
def extract(key, content, default=None, cast=float):
    m = re.search(rf'{key}\s*=\s*([^\n<]+)', content, re.IGNORECASE)
    return cast(m.group(1).strip()) if m else default
```

---

## Step 2: Raw Image Reading

**Input**: `ch2_ohr_ncp_<timestamp>_d_img_d18.img`
**Format**: Binary, 16-bit unsigned integer (`uint16`), row-major order

OHRC `.img` files may have a PVL label prepended (PDS3 convention). The label size is recorded in the metadata as `^IMAGE = <byte_offset>`. If the file size is larger than `lines × samples × 2 bytes`, we search for the image start.

```python
expected_bytes = lines * samples * 2  # uint16
file_size = os.path.getsize(img_path)

if file_size == expected_bytes:
    # Pure binary, no label
    data = np.frombuffer(open(img_path, 'rb').read(), dtype=np.uint16)
elif file_size > expected_bytes:
    # Has PVL label - find offset
    m = re.search(rb'\^IMAGE\s*=\s*(\d+)', content)
    offset = int(m.group(1)) - 1
    data = np.frombuffer(content[offset:offset+expected_bytes], dtype=np.uint16)
```

The result is reshaped to `(lines, samples)` and cast to `float32` for processing.

---

## Step 3: Radiometric Calibration (DN → Radiance)

**Physics**: The camera records Digital Numbers (DN) proportional to the photon flux on the detector. To convert to physical units (radiance), we apply:

$$L = \frac{DN \times \text{gain} + \text{offset}}{t_{\text{exp}}}$$

Where:
- $L$ = radiance (W/m²/sr/μm)
- $DN$ = raw digital number (0–16383, 14-bit ADC)
- $\text{gain}$ = calibration coefficient (W/m²/sr/μm per DN)
- $\text{offset}$ = dark current offset (W/m²/sr/μm)
- $t_{\text{exp}}$ = exposure time (seconds)

The gain and offset are derived from pre-flight calibration and validated on-orbit using stellar observations of known brightness stars.

**Quality masking**: DN = 0 (dead pixels) and DN ≥ 16383 (saturated) are set to NaN.

```python
def radiometric_calibration(dn_image, gain, offset, exposure_time):
    radiance = (dn_image * gain + offset) / exposure_time
    radiance[dn_image == 0] = np.nan          # dead pixels
    radiance[dn_image >= 16383] = np.nan       # saturated
    return radiance
```

---

## Step 4: Reflectance Conversion (Radiance → I/F)

**Physics**: Reflectance $I/F$ normalizes radiance by the incident solar flux, making the measurement independent of Sun-Moon distance and solar spectrum. For a Lambertian surface illuminated at incidence angle $i$:

$$\frac{I}{F} = \frac{\pi \cdot L}{F_{\text{solar}} \cdot \cos(i)}$$

Where:
- $L$ = calibrated radiance (W/m²/sr/μm)
- $F_{\text{solar}}$ = solar spectral flux at the Moon (W/m²/μm), distributed over the OHRC bandpass (450–700 nm, ~0.6 μm effective bandwidth)
- $i$ = solar incidence angle = 90° − sun elevation
- $\pi$ converts between radiant exitance (W/m²) and radiance (W/m²/sr)

For OHRC:
- $F_{\text{solar}} = 1361 / 0.6 ≈ 2268$ W/m²/μm
- At sun elevation 3° (typical polar), $\cos(i) = \cos(87°) ≈ 0.052$

```python
def radiance_to_reflectance(radiance, sun_elevation_deg, ...):
    solar_flux = SOLAR_FLUX_LUNAR / bandwidth_um  # ~2268 W/m²/μm
    cos_i = math.cos(math.radians(90 - sun_elevation_deg))
    i_over_f = (np.pi * radiance) / (solar_flux * cos_i)
    return np.clip(i_over_f, 0, 1)
```

**Output**: $I/F$ ranges from 0 (shadow) to ~0.3 (bright regolith at low sun). Values near 1.0 indicate specular reflection off slopes facing the sun.

---

## Step 5: Photoclinometry (Shape from Shading)

This is the core algorithm — estimating surface topography from a single image using the reflectance model. This is necessary because OHRC is a single-camera pushbroom imager (no stereo), so traditional photogrammetry cannot produce a DEM.

### 5a: Lunar-Lambertian Reflectance Model (Forward)

**Reference**: McEwen, A.S. (1991). "Photometric functions for photoclinometry and morphometric applications." *Icarus* 92(1), 54-76.

The Lunar-Lambertian model combines Lambertian (diffuse) and Lunar (backscatter) terms:

$$I(x,y) = A \cdot \left[ (1 - AL) \cos(i) + AL \cdot \frac{2\cos(i)}{\cos(i) + \cos(e)} \right]$$

Where:
- $I$ = predicted reflectance (I/F)
- $A$ = surface albedo (≈0.12 for mature lunar regolith)
- $AL$ = Lunar-Lambertian weight (≈0.6 for polar regolith; 0 = pure Lambertian, 1 = pure Lunar)
- $i$ = incidence angle (sun to surface normal)
- $e$ = emission angle (surface normal to observer; ≈0 for nadir OHRC)

**Surface normal from slopes**: If the surface has slopes $\partial z/\partial x = p$ and $\partial z/\partial y = q$ (in radians), the surface normal is:

$$\hat{n} = \frac{(-\tan p, -\tan q, 1)}{\sqrt{\tan^2 p + \tan^2 q + 1}}$$

**Incidence angle**: With sun direction $\hat{s} = (s_x, s_y, s_z)$:

$$\cos(i) = \hat{n} \cdot \hat{s} = \frac{-\tan(p) \cdot s_x - \tan(q) \cdot s_y + s_z}{|\hat{n}|}$$

```python
def lunar_lambertian_reflectance(slope_x, slope_y, sun_az, sun_el, albedo=0.12, AL=0.6):
    nx, ny, nz = -np.tan(slope_x), -np.tan(slope_y), 1.0
    n_mag = np.sqrt(nx**2 + ny**2 + nz**2)
    nx, ny, nz = nx/n_mag, ny/n_mag, nz/n_mag
    
    sx = math.sin(az_rad) * math.cos(el_rad)
    sy = math.cos(az_rad) * math.cos(el_rad)
    sz = math.sin(el_rad)
    
    cos_i = np.clip(nx*sx + ny*sy + nz*sz, 0, 1)
    cos_e = np.clip(nz, 0.1, 1)
    
    return albedo * ((1-AL)*cos_i + AL*2*cos_i/(cos_i + cos_e))
```

### 5b: Inverse Problem (Slope Estimation)

**Goal**: Given observed reflectance $I_{\text{obs}}(x,y)$, find slopes $(p, q)$ that produce $I_{\text{pred}}(p, q) ≈ I_{\text{obs}}$.

**Challenge**: Single-image photoclinometry is underdetermined — for each pixel we have one equation (reflectance) but two unknowns (slope_x, slope_y). The standard approach uses a small-slope linearization:

**Linearization around zero slope**: At zero slope, $\cos(i_0) = \sin(\text{el})$ and the reflectance is:

$$I_0 = A \cdot \left[ (1-AL)\cos(\text{el}) + AL \cdot \frac{2\cos(\text{el})}{\cos(\text{el})+1} \right]$$

For small slopes along the sun direction ($s_{\text{sun}}$ = slope component facing the sun):

$$\cos(i) \approx \sin(\text{el}) + \cos(\text{el}) \cdot s_{\text{sun}}$$

So the reflectance becomes approximately linear in $s_{\text{sun}}$:

$$I \approx I_0 + A \cdot \cos(\text{el}) \cdot s_{\text{sun}}$$

Solving for the slope:

$$s_{\text{sun}} = \frac{I - I_0}{A \cdot \cos(\text{el})}$$

**Albedo estimation**: We don't know $A$ a priori, but we can estimate it from the data. The median reflectance of illuminated pixels approximates $I_0$ (since most pixels are near-flat), so:

$$A = \frac{\text{median}(I_{\text{obs}})}{I_0 \text{ per unit albedo}} = \frac{\text{median}(I_{\text{obs}})}{(1-AL)\cos(\text{el}) + AL \cdot 2\cos(\text{el})/(\cos(\text{el})+1)}$$

**Decomposition**: The slope along the sun direction $s_{\text{sun}}$ is decomposed into $x$ and $y$ components using the sun azimuth:

$$p = s_{\text{sun}} \cdot \sin(\text{az}), \quad q = s_{\text{sun}} \cdot \cos(\text{az})$$

**Limitations**: This linear approximation captures the sun-facing slope but misses the cross-sun slope (perpendicular to the sun direction). For full 2D slope recovery, iterative methods (e.g., Horn & Brooks) or multi-image photoclinometry (same area at different sun angles) are needed. The Frankot-Chellappa step enforces integrability, which partially compensates.

```python
def estimate_slopes_from_reflectance(reflectance, sun_az, sun_el, albedo=0.12, AL=0.6):
    # Estimate albedo from median reflectance
    I_0_per_albedo = (1-AL)*cos_el + AL*2*cos_el/(cos_el+1)
    albedo_est = median(reflectance[valid]) / I_0_per_albedo
    
    # Linear slope estimate
    I_0 = albedo_est * I_0_per_albedo
    slope_along_sun = (reflectance - I_0) / (albedo_est * cos_el)
    slope_along_sun = clip(slope_along_sun, -0.5, 0.5)  # cap at ~26°
    
    # Decompose to x, y
    slope_x = slope_along_sun * sin(az_rad)
    slope_y = slope_along_sun * cos(az_rad)
    return slope_x, slope_y
```

---

## Step 6: Frankot-Chellappa DEM Integration

**Reference**: Frankot, R.T., & Chellappa, R. (1988). "A method for enforcing integrability in shape from shading algorithms." *IEEE TPAMI* 10(4), 439-451.

**Problem**: The estimated slopes $(p, q)$ may not be integrable — i.e., there may be no surface $z(x,y)$ whose gradients exactly match $(p, q)$. This happens because:
1. The linear approximation ignores cross-sun slopes
2. Noise in the reflectance propagates to slope estimates
3. Albedo variations (real surface has spatially varying albedo) contaminate slope estimates

**Solution**: Project the slope field onto the nearest integrable surface in the Fourier domain.

**Math**: An integrable surface satisfies $\partial p / \partial y = \partial q / \partial x$. In the Fourier domain, this becomes:

$$\hat{Z}(u,v) = \frac{-j \cdot (u \cdot \hat{P}(u,v) + v \cdot \hat{Q}(u,v))}{u^2 + v^2}$$

Where:
- $\hat{Z}, \hat{P}, \hat{Q}$ = 2D FFTs of $z$, $p$, $q$
- $u, v$ = spatial frequencies (cycles per pixel)
- $j$ = imaginary unit
- The DC component ($u=v=0$) is set to 0 (zero mean elevation)

The inverse FFT gives the integrable DEM:

$$z(x,y) = \mathcal{F}^{-1}\{\hat{Z}(u,v)\}$$

**Scaling**: The slopes are in radians; we convert to $dz/dx = \tan(p)$, then scale the result by pixel size to get meters.

```python
def frankot_chellappa_dem(slope_x, slope_y, pixel_size_m):
    # Handle NaN
    slope_x = np.nan_to_num(slope_x, nan=0.0)
    slope_y = np.nan_to_num(slope_y, nan=0.0)
    
    # Convert angle to gradient
    dz_dx = np.tan(slope_x)
    dz_dy = np.tan(slope_y)
    
    # FFT
    P = np.fft.fft2(dz_dx)
    Q = np.fft.fft2(dz_dy)
    
    # Frequency grids
    u = np.fft.fftfreq(cols).reshape(1, -1)
    v = np.fft.fftfreq(rows).reshape(-1, 1)
    freq_mag = u**2 + v**2
    freq_mag[0, 0] = 1.0  # avoid div by zero
    
    # Frankot-Chellappa
    Z = -1j * (u * P + v * Q) / freq_mag
    Z[0, 0] = 0  # zero mean
    
    # Inverse FFT
    dem = np.real(np.fft.ifft2(Z)) * pixel_size_m
    return dem - dem.mean()  # relative DEM
```

**Output**: A relative DEM (mean-removed) in meters. The absolute elevation requires ground control points (e.g., from LOLA laser altimetry) to tie the relative DEM to the lunar datum.

---

## Step 7: Derived Products

### Slope Map (Horn's Method)
Computes slope in degrees from the DEM using a 3×3 gradient kernel (Horn 1981):

$$\text{slope} = \arctan\left(\sqrt{(\partial z/\partial x)^2 + (\partial z/\partial y)^2}\right)$$

```python
dy, dx = np.gradient(dem, pixel_size_m)
slope_deg = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))
```

### Roughness Map
Local standard deviation in a 5×5 kernel:

$$\sigma(x,y) = \text{std}\left(\{z(x+i, y+j) : i,j \in [-2, 2]\}\right)$$

This captures sub-pixel hazards (boulders, small craters) that the DEM resolves.

### Shadow Mask
Pixels with reflectance below threshold (0.005 I/F) are classified as shadow. At low sun (polar conditions), this approximates the permanently shadowed regions (PSRs):

```python
shadow_mask = (reflectance < 0.005).astype(np.uint8)
```

---

## Step 8: Georeferencing

Saves each product as a GeoTIFF with the corner coordinates from the metadata:

- **CRS**: EPSG:4326 (simple cylindrical lat/lon)
- **Transform**: `from_origin(ul_lon, ul_lat, lon_res, lat_res)` — upper-left corner + pixel size in degrees
- **Nodata**: NaN for float products, 0 for integer products

This allows direct import into QGIS/ArcGIS for overlay with other lunar datasets (LOLA DEM, Mini-RF, Diviner).

---

## Step 9: Quality Report

A JSON file (`processing_report.json`) records:
- Input metadata (gain, offset, sun geometry, resolution)
- Output file paths
- Statistics for each product (min, max, mean)
- Algorithm parameters (AL, albedo, thresholds)
- Mode (synthetic vs real data)

---

## How to Use with Real OHRC Data

### 1. Download from PRADAN

Download an OHRC bundle from ISRO's PRADAN portal. The bundle will have this structure:

```
ch2_ohr_ncp_<timestamp>_d_img_d18_Bundle/
└── ch2_ohr_ncp_<timestamp>_d_img_d18/
    ├── data/calibrated/<YYYYMMDD>/
    │   ├── ch2_ohr_ncp_<timestamp>_d_img_d18.img
    │   └── ch2_ohr_ncp_<timestamp>_d_img_d18.xml
    ├── geometry/calibrated/<YYYYMMDD>/
    │   └── ch2_ohr_ncp_<timestamp>_d_img_d18_geom.csv
    └── miscellaneous/
        ├── ch2_ohr_ncp_<timestamp>_d_img_d18.spm
        └── ch2_ohr_ncp_<timestamp>_d_img_d18.oat
```

### 2. Run the pipeline

```bash
python ohrc_pipeline.py \
    --bundle /path/to/ch2_ohr_ncp_<timestamp>_d_img_d18_Bundle \
    --output /home/z/my-project/download/ohrc_processed
```

### 3. Check outputs

The pipeline produces 8 files in the output directory:
- `calibrated_radiance.tif` — W/m²/sr/μm
- `reflectance_if.tif` — I/F (0-1)
- `dem_photoclinometry.tif` — relative elevation in meters
- `slope_map.tif` — degrees
- `roughness_map.tif` — meters (local std dev)
- `shadow_mask.tif` — binary (0/1)
- `ohrc_processing_results.png` — 6-panel visualization
- `processing_report.json` — all parameters and statistics

### 4. Import to QGIS

Open any `.tif` file in QGIS — they are already georeferenced with EPSG:4326. Overlay with LOLA DEM or Mini-RF for cross-validation.

---

## Algorithm Limitations & Extensions

### Current limitations:
1. **Single-image photoclinometry**: Only recovers sun-facing slope component; cross-sun slope is zero until Frankot-Chellappa enforces integrability.
2. **Constant albedo assumption**: Real regolith has albedo variations (10-20%) that contaminate slope estimates. Multi-image photoclinometry (same area at multiple sun angles) solves this.
3. **No absolute elevation**: The DEM is relative. Tie to LOLA ground control points for absolute heights.
4. **Shadowed regions**: Photoclinometry fails in shadows (no signal). These regions are filled with 0 slope, creating artifacts at shadow boundaries.

### Production-grade extensions:
1. **Multi-image photoclinometry**: Acquire the same area at 2-3 different sun azimuths. Solve the over-determined system for both slope components independently.
2. **Albedo map iteration**: After first DEM pass, compute the residual (I_obs - I_pred). Spatially smooth the residual to estimate an albedo map, then re-run photoclinometry with the corrected albedo.
3. **LOLA ground control**: Sample LOLA elevations within the OHRC footprint. Fit a low-order polynomial (affine transform) from relative DEM to LOLA to add absolute elevation.
4. **Shadow region infill**: Use radar (Mini-RF/DFSAR) or neighboring illuminated pixels to interpolate elevation in shadowed regions.

---

## References

1. **McEwen, A.S.** (1991). "Photometric functions for photoclinometry and morphometric applications." *Icarus*, 92(1), 54-76. — Lunar-Lambertian reflectance model.
2. **Frankot, R.T., & Chellappa, R.** (1988). "A method for enforcing integrability in shape from shading algorithms." *IEEE TPAMI*, 10(4), 439-451. — Fourier-domain slope integration.
3. **Horn, B.K.P.** (1981). "Hill shading and the reflectance map." *Proceedings of the IEEE*, 69(1), 14-47. — Slope computation from DEM.
4. **Kirk, R.L. et al.** (2003). "Radar and photoclinometric studies of lunar polar craters." *ISPRS Archives*, 34, 165-172. — Application to lunar polar PSRs.
5. **Chandrayaan-2 OHRC Data Products User Guide** (ISRO, 2024). — Calibration coefficients, file formats, metadata structure.
6. **Spudis, P.D. et al.** (2013). "Evidence for water ice on the Moon: Results for anomalous polar craters from the Mini-SAR imaging radar." *JGR Planets*, 118(10), 2016-2029. — CPR threshold for ice detection.
