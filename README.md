# Lunar Subsurface Ice Detection - ISRO Hackathon Project

This project focuses on the detection and characterization of subsurface water-ice in the lunar South Polar Region. By utilizing Chandrayaan-2 Dual Frequency Synthetic Aperture Radar (DFSAR) and Orbiter High Resolution Camera (OHRC) imagery, we aim to identify ice-bearing "doubly shadowed craters," propose viable landing sites, and design optimal rover traverse paths for future ISRO exploration missions.

## Project Overview

The 'doubly shadowed craters' in lunar permanently shadowed regions (PSRs) provide access to extremely cold environments that are ideal candidates for long-term volatile preservation. Our goal is to unambiguously identify subsurface ice and translate these detections into actionable exploration strategies.

### Key Objectives
1. **Identify & Map**: Locate potential subsurface ice-bearing regions in the lunar south polar PSRs (focusing on doubly shadowed craters).
2. **Radar Polarimetry**: Distinguish ice-rich regions from rough, rocky terrains using DFSAR polarimetric signatures (CPR and DOP).
3. **Landing Site Selection**: Propose a scientifically viable and safe landing site near the target crater.
4. **Rover Traverse Planning**: Design an optimal, hazard-free traverse path from the landing site to the target ice.
5. **Volume Estimation**: Estimate the volume of subsurface ice within the top ~5 meters of the lunar regolith.

---

## ⚠️ Important Note About Data

**The `Data/` folder is NOT included in this repository.** 
Due to GitHub file size limits, the large dataset (~2.4 GB) containing DFSAR imagery and generated TIFF files has been excluded via `.gitignore`. 

**For Team Members:**
1. Download the `Data.zip` file shared by the project lead (via Google Drive/USB).
2. Extract the folder and place it directly in the root of this project repository so that the path looks like this: `ISRO Project/Data/`.
3. Do not alter the subdirectories inside `Data/`, as the scripts depend on the specific folder structure.

---

## Code Structure & Workflow

The python scripts in the `src/` folder are designed to be run sequentially to process the radar data, compute metrics, and map the ice candidates.

- **`src/00_preflight_checklist.py`** & **`src/preflight_verify.py`**: Validates that all necessary dependencies (GDAL, rasterio, numpy) and data files are present before starting the analysis.
- **`src/01_ingest_calibrate.py`**: Ingests the raw DFSAR data and performs initial calibration.
- **`src/02_compute_cpr_dop.py`**: Computes radar polarimetric parameters such as Circular Polarization Ratio (CPR) and Degree of Polarization (DOP).
- **`src/03_map_ice_candidates.py`**: Applies specific criteria (e.g., CPR > 1 and DOP < 0.13) to isolate potential volumetric scattering caused by subsurface ice from surface roughness.
- **`src/04_spudis_check.py`**: Validates the detected ice signatures against established scientific literature thresholds (like the Spudis models).
- **`src/peek_sli.py` & `src/peek_tiff.py`**: Utility scripts to inspect `.sli` and `.tiff` output files generated during the pipeline.

## Getting Started

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Qorexx/Lunar-Subsurface-Ice-Detection.git
   cd Lunar-Subsurface-Ice-Detection
   ```
2. **Add the Data folder** (as mentioned above).
3. **Install Dependencies**:
   Ensure you have Python installed along with `numpy`, `scipy`, `gdal`, and `rasterio`.
4. **Run the Preflight Check**:
   ```bash
   python src/00_preflight_checklist.py
   ```
5. **Execute the Pipeline**: Run the numbered scripts `01` through `04` in order.

---
*Built for the ISRO Lunar Ice Detection Hackathon.*
