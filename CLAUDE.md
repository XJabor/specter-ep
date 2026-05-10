# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the app (activate venv first)
source venv/bin/activate
python backend/app.py          # serves at http://127.0.0.1:5050/

# Run all tests
venv/bin/python -m unittest discover -s tests

# Run a single test class or method
venv/bin/python -m unittest tests.test_rf_engine.PropagationTests
venv/bin/python -m unittest tests.test_rf_engine.PropagationTests.test_path_loss_model_selection

# Syntax checks
venv/bin/python -m compileall backend tests
node --check frontend/js/map_deckgl.js
```

## Architecture

**Request flow for a footprint calculation:**

1. Frontend `ui_controls.js` collects emitter parameters and calls `fetchFootprint` in `map_deckgl.js`
2. `POST /api/v1/footprint` is handled by `backend/api/routes_model.py:calculate_footprint`
3. For each bearing (default 72), it calls `get_elevation_profiles_batch` → `sample_elevations_with_sources` → local raster → online fallback → zero fallback
4. `_walk_profile_to_range` steps along each elevation profile, calls `check_line_of_sight` (Deygout knife-edge diffraction) and `calculate_path_loss_details` at each sample, and finds the distance where path loss exceeds the link budget
5. Response is polygon vertices + per-sector metadata; Deck.gl renders these as a `PolygonLayer`

**Path loss model selection** (`backend/engine/propagation.py:classify_path_loss_model`):

| Condition | LOS model | NLOS model |
|---|---|---|
| >2000 MHz | SHF FSPL + clutter | SHF FSPL + clutter |
| Free space or air terrain | FSPL | FSPL |
| 1000–2000 MHz, tx_height <30 m | Upper-UHF FSPL + terrain correction | Upper-UHF FSPL + terrain correction |
| ≥150 MHz and tx_height ≥30 m (COST-231 valid) | Two-Ray Ground Reflection | COST-231 Hata |
| Otherwise (VHF, low antenna) | Egli | Egli |

**Terrain stack** (`backend/engine/terrain.py`):

- `scan_terrain_path` populates the module-level `_terrain_sources` list from a file or directory of GeoTIFF/DTED files; RGB multi-band rasters are flagged as imagery and excluded from elevation use
- `extract_elevation_grid` clips a raster window around the Tx and resamples to a `max_size×max_size` matrix (default 220) for the legacy FSPL heatmap (`POST /api/v1/calculate`)
- `sample_elevations_with_sources` tries local sources first, falls back to OpenTopoData in 100-point batches, then zero
- Viewshed masking in `calculate_fspl_grid` uses Bresenham ray casting; shadow cells take a hard −40 dB penalty (Deygout replaces this in the footprint path)

**Frontend state** (`frontend/js/app.js`):

`window.specterApp` is a single global state object. All mutations go through its methods (`armPlacement`, `placeArmedSystem`, `updateSelectedInstanceField`, etc.). Rendering is triggered by `specterApp.refreshUi()`, which calls `renderLibraryPanel`, `renderInstancePanel`, `renderMapLayers`, and `renderProgressPanel` if they are defined on `window`.

**Systems library** (`data_store/library/core_systems.json`):

JSON with `tactical_radios` and `satcom_terminals` arrays. Each entry becomes an instance via `createInstanceFromSystem` in `app.js`. `custom_systems` are session-only (not persisted). `backend/api/routes_systems.py` exposes them via `GET /api/v1/systems`.

**Pipeline utilities** (`backend/pipeline/`):

- `jf12_parser.py` — regex extraction of power/frequency/nomenclature from JF12 or vendor spec text; normalizes Watts → dBm
- `system_builder.py` — placeholder (currently empty)

**Config** (`backend/config.py`):

Loads `.env` from the repo root (env vars take precedence over the file). Key vars: `SPECTER_TERRAIN_PATH`, `SPECTER_ONLINE_ELEVATION`, `SPECTER_ELEVATION_URL`, `MAPBOX_TOKEN`, `SPECTER_EP_PORT` (default 5050).

## Notes

- `backend/` is the Flask working directory; imports within it use bare module names (`from config import …`, `from engine.terrain import …`). Tests prepend `backend/` to `sys.path`.
- The `Oahu_Tiff.tif` bundled in `data_store/terrain_cache/` is an RGB imagery raster (3-band uint8), so `elevation_source_count` will be 0 and `imagery_source_count` will be 1 when it is the only source. Footprints over Oahu rely on the online fallback or zero elevation unless a real DTED/single-band GeoTIFF is provided.
- `utils_rf.py` has its own `calculate_eirp_dbm(tx_power_dbm, cable_loss_db, antenna_gain_dbi)` with argument order different from `propagation.py`'s `calculate_eirp_dbm(tx_power_dbm, antenna_gain_dbi, cable_loss_db)`. Do not mix them.
