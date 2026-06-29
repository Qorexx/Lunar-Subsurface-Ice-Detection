# 01_ingest_calibrate.py — Pre-Flight Checklist
# ==============================================
# Before writing this script, every item below must be VERIFIED, not assumed.
#
# CONFIRMED (from peek script + XML):
# ✅ File format: GeoTIFF, uint16
# ✅ Dimensions: 1320 x 1239
# ✅ Pixel spacing: 25m x 25m
# ✅ CRS: Polar Stereographic Moon (south pole origin)
# ✅ DN range: 0–11765 (HH band)
# ✅ Zero pixels: ~69% of image is no-data
# ✅ Calibration constant K = 70.308868
#
# UNCERTAIN (must verify before coding):
# ❓ Q1: MASK FILE — What values does sri_ma contain? (0/1? 0/255? Other?)
#         Need to peek at it to know how to apply it.
#
# ❓ Q2: CALIBRATION FORMULA — Is it truly sigma0 = DN^2 / K?
#         Or does ISRO use a different formula (e.g., 10*log10(DN^2/K) for dB)?
#         Must cross-check with the user manual PDF.
#
# ❓ Q3: INCIDENCE ANGLE — Some SAR calibration requires dividing by sin(theta).
#         The dataset includes a per-pixel incidence angle map (sri_in file).
#         Do we need it? The user manual should clarify.
#
# ❓ Q4: GEOMETRY CSV MAPPING — The CSV has 102,943 rows of (lat, lon).
#         The image has 1320 x 1239 = 1,635,480 pixels.
#         How does each CSV row map to image pixels? Row-major? Every pixel?
#         Need to verify the mapping logic.
#
# VERIFICATION PLAN:
# Step 1: Peek at the mask file (sri_ma) — print unique values and shape
# Step 2: Peek at the incidence angle file (sri_in) — print value range
# Step 3: Re-read user manual section on calibration formula
# Step 4: Check geometry CSV row count vs image pixel count
# Step 5: ONLY THEN write the actual ingestion script
