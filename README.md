# Specter-EP

Specter-EP is a 3D EMS footprint prototype for visualizing radio and SATCOM
emissions over terrain.

## Current Baseline

- Flask API backend in `backend/`.
- Static Deck.gl/Mapbox frontend in `frontend/`.
- Default terrain source: `data_store/terrain_cache/Oahu_Tiff.tif`.
- Default map center: Oahu.
- Main analysis endpoint: `POST /api/v1/footprint`.
- Runtime config endpoint: `GET /api/v1/config`.
- Offline terrain endpoints: `GET /api/v1/terrain/status` and `POST /api/v1/terrain/source`.

## Run Locally

```bash
source venv/bin/activate
python backend/app.py
```

Then open the Flask-served app:

```text
http://127.0.0.1:5050/
```

Click the map to place an emitter and select `Calculate Footprint`.

Use the lower-left `Offline Terrain / DTED Path` control to point the app at a
DTED file, DTED folder, or elevation GeoTIFF. `Refresh` scans the path without
restarting Flask. RGB imagery GeoTIFFs are detected and reported, but they are
not used for elevation sampling.

## Verify

```bash
venv/bin/python -m unittest discover -s tests
```

## Configuration

Environment variables:

- `SPECTER_TERRAIN_PATH`: path to a local GeoTIFF/DTED-compatible raster.
- `SPECTER_ONLINE_ELEVATION`: `true` or `false`; enables OpenTopoData fallback.
- `SPECTER_ELEVATION_URL`: alternate OpenTopoData-compatible endpoint.
- `SPECTER_DEFAULT_LAT`, `SPECTER_DEFAULT_LON`, `SPECTER_DEFAULT_ZOOM`: startup map center.
- `SPECTER_VERTICAL_CAP_M`: vertical visualization cap, default `3048` m.
- `SPECTER_EP_HOST`: Flask bind host, default `0.0.0.0`.
- `SPECTER_EP_PORT`: Flask port, default `5050` to avoid Specter-EW's usual `5000`.

## Direction

The first product goal is radio footprint visualization: users should understand
what their EMS signature looks like to ground collectors, with terrain-aware
blocking/diffraction and capped vertical considerations for directional/SATCOM
systems.
