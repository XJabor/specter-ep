# Repository Guidelines

## Project Structure & Module Organization

`backend/` contains the Flask app, API routes, propagation engine, terrain handling, and pipeline utilities. `frontend/` contains the Flask-served UI: `index.html`, `js/`, and `css/`. `tests/` contains the Python `unittest` suite. `data_store/` holds system library JSON and terrain assets such as GeoTIFF or DTED inputs. Treat `venv/` and `__pycache__/` as local environment artifacts, not source.

## Build, Test, and Development Commands

Use the project virtualenv:

```bash
source venv/bin/activate
python backend/app.py
```

This starts the app on `http://127.0.0.1:5050/` by default.

Key verification commands:

```bash
venv/bin/python -m unittest discover -s tests
venv/bin/python -m compileall backend tests
node --check frontend/js/map_deckgl.js
```

The first runs the API and RF-engine tests, the second catches Python syntax issues, and the third checks frontend JavaScript syntax.

## Coding Style & Naming Conventions

Use 4-space indentation in Python and keep functions/modules in `snake_case`. Preserve the current plain-JS frontend style; use clear function names such as `fetchFootprint` and `refreshTerrainSource`. Keep comments sparse and only where logic is not obvious. Prefer ASCII unless a file already requires other characters. Use `apply_patch` for manual edits.

## Testing Guidelines

Tests use Python’s built-in `unittest`. Add new tests in `tests/test_*.py` and name test methods `test_<behavior>`. Cover propagation math, terrain-source selection, and API contract changes whenever backend behavior changes. For frontend-only edits, at minimum run `node --check` on the touched JS file.

## Commit & Pull Request Guidelines

This workspace is not a Git checkout, so no local commit history is available to infer conventions. Use short, imperative commit subjects such as `Add terrain source status endpoint`. Keep PRs focused. Include a concise description, the commands used for verification, linked issues if applicable, and screenshots for visible UI changes.

## Configuration & Data Notes

Runtime configuration is controlled with environment variables such as `SPECTER_EP_PORT`, `SPECTER_TERRAIN_PATH`, and `SPECTER_ONLINE_ELEVATION`. RGB imagery GeoTIFFs may be valid visual assets but are not valid elevation sources; prefer DTED or single-band elevation rasters for propagation work.
