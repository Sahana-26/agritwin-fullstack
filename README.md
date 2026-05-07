# AgriTwin Seasonal + Future Analysis Dashboard

This version of the project is updated to support:

- **Local DEM support from `dem.tif` placed beside `aoi.geojson`**
- **Interactive frontend dashboard** with linked map + charts
- **Interactive charts** for analysis outputs using Plotly
- **Leaflet overlay controls** for thematic layers and RGB context
- **Chart API** for histogram, class-share pie, trend line, and theme-comparison bar charts

## Main Outputs

- NDVI
- NDMI
- AWEI
- NDVI anomaly
- Water retention opportunity (WaterLite)
- Coconut suitability
- Pepper suitability
- Eco-stay suitability
- Sandalwood suitability
- Rainwater harvesting suitability
- DEM
- Slope
- All-weather radar composite

## DEM Requirement

This project is now configured to **prioritize a local file named `dem.tif`** in the project root.

Expected structure:

```text
project_root/
  aoi.geojson
  dem.tif
  manage.py
  ...
```

If `dem.tif` is not present, the code can optionally fall back to the Planetary Computer DEM when `DEM_SOURCE_FALLBACK_TO_STAC=True`.

## Dashboard Features

- Historical and future run switching
- Interactive thematic map overlays
- Opacity control for raster overlay
- RGB toggle for optical context
- Map click inspection for parcel diagnostics
- Interactive **line chart** for trend analysis
- Interactive **bar chart** for theme comparison
- Interactive **pie chart** for current layer class share
- Interactive **histogram** for active layer value distribution
- Clicking a **bar** changes the active theme
- Clicking a **trend point** loads that year/run

## API Endpoints

- `/api/dashboard/config/`
- `/api/analysis/select/`
- `/api/analysis/<run_id>/`
- `/api/analysis/<run_id>/charts/?layer_name=ndvi`
- `/api/analysis/<run_id>/inspect/?lat=..&lng=..`
- `/api/analysis/<run_id>/layers/<layer_name>/image.png`
- `/api/trends/?mode=historical&season=Monsoon&layer_name=ndvi`

## Setup

1. Start PostgreSQL + PostGIS

```bash
docker compose up -d
```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Make sure the following files are present in the project root:

- `aoi.geojson`
- `dem.tif`

4. Configure environment values in `.env` if needed.

5. Run migrations

```bash
python manage.py migrate
```

6. Load runs

```bash
python manage.py backfill_historical
python manage.py refresh_future
```

7. Start the app

```bash
python manage.py runserver
```

## Notes

- Rasters are stored in PostgreSQL via PostGIS `RasterField`.
- The dashboard renders raster overlays as PNG images directly from the database.
- Terrain analysis uses the local `dem.tif` when available.
- The charts are driven from stored raster statistics and per-layer raster distributions.




