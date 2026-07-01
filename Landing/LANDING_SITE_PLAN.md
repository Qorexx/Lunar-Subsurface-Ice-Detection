Lunar Landing Site Selection Pipeline using Chandrayaan-2 OHRC
Overview

This project presents an automated pipeline for identifying safe lunar landing sites from Chandrayaan-2 Orbiter High Resolution Camera (OHRC) imagery. The pipeline processes raw orbital images, evaluates terrain safety using image-based features, ranks candidate landing regions, and converts the selected landing site's pixel coordinates into lunar latitude and longitude.

The implementation is designed to be dataset-independent, allowing it to be reused for any OHRC image strip, including scientifically important regions such as Faustini Crater, simply by providing the corresponding OHRC dataset.

Pipeline
OHRC Image + XML
        │
        ▼
Load & Parse Metadata
        │
        ▼
Detect Useful Illuminated Region
        │
        ▼
Tile Image (1000 × 1000 px)
        │
        ▼
Filter Useful Terrain Crops
        │
        ▼
Extract Terrain Features
        │
        ▼
Landing Safety Scoring
        │
        ▼
Rank Candidate Landing Sites
        │
        ▼
Pixel → Latitude/Longitude Conversion
        │
        ▼
Final Landing Site
Terrain Features Extracted
Mean Brightness
Brightness Standard Deviation
Shadow Percentage
Surface Roughness (Entropy)
Maximum Slope Proxy (Gradient)

These features are combined into a composite Landing Safety Score, prioritizing:

Low shadow coverage
Smooth terrain
Low surface slope
Results
Metric	Value
OHRC Image Size	101,074 × 12,000 pixels
Resolution	0.2 m/pixel
Initial Tiles	192
Valid Terrain Crops	89
Safe Landing Candidates	65
Final Landing Latitude	-85.800759°
Final Landing Longitude	33.428759°
Output Files
crop_features.csv – Terrain features for every crop
landing_candidates_ranked.csv – Ranked landing site candidates
landing_site_final.json – Final landing site coordinates and metadata
Future Scope

The current implementation demonstrates the methodology on an available OHRC south-polar image strip. The pipeline is fully reusable and can be directly applied to Faustini Crater or any other lunar region by replacing the input OHRC image and XML metadata, enabling future integration with DFSAR-based subsurface ice detection and rover traverse planning.