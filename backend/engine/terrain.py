from pathlib import Path

import rasterio
from rasterio.enums import Resampling
from rasterio.windows import from_bounds
from rasterio.warp import transform, transform_bounds
import numpy as np

try:
    from config import DEFAULT_TERRAIN_PATH, ENABLE_ONLINE_ELEVATION, OPEN_TOPO_DATA_URL
except ImportError:
    DEFAULT_TERRAIN_PATH = None
    ENABLE_ONLINE_ELEVATION = False
    OPEN_TOPO_DATA_URL = "https://api.opentopodata.org/v1/srtm30m"

_DTED_LEVELS = {".dt0": 0, ".dt1": 1, ".dt2": 2}
_ELEVATION_EXTENSIONS = set(_DTED_LEVELS) | {".tif", ".tiff"}
_terrain_sources = []
_terrain_status = {
    "path": str(DEFAULT_TERRAIN_PATH) if DEFAULT_TERRAIN_PATH else "",
    "exists": False,
    "source_count": 0,
    "elevation_source_count": 0,
    "imagery_source_count": 0,
    "sources": [],
    "warnings": ["Terrain data has not been scanned yet."],
}


def _source_sort_key(source):
    return (source.get("level", -1), source.get("resolution_score", 0))


def _is_probable_imagery(src):
    return src.count >= 3 and all(dtype == "uint8" for dtype in src.dtypes[:3])


def _scan_raster(path):
    suffix = path.suffix.lower()
    with rasterio.open(path) as src:
        try:
            bounds = transform_bounds(src.crs, "EPSG:4326", *src.bounds) if src.crs else src.bounds
        except Exception:
            bounds = src.bounds

        is_dted = suffix in _DTED_LEVELS
        is_imagery = _is_probable_imagery(src)
        is_elevation = is_dted or (src.count == 1 and not is_imagery)
        level = _DTED_LEVELS.get(suffix, -1)

        source = {
            "path": str(path),
            "name": path.name,
            "kind": "dted" if is_dted else ("imagery" if is_imagery else "raster"),
            "usable_for_elevation": is_elevation,
            "level": level,
            "crs": str(src.crs) if src.crs else None,
            "bounds": {
                "west": float(bounds[0]),
                "south": float(bounds[1]),
                "east": float(bounds[2]),
                "north": float(bounds[3]),
            },
            "width": src.width,
            "height": src.height,
            "bands": src.count,
            "dtypes": list(src.dtypes),
            "warnings": [],
        }
        if is_imagery:
            source["warnings"].append("Looks like RGB imagery; not used for elevation sampling.")
        if not is_elevation and not is_imagery:
            source["warnings"].append("Raster was not recognized as an elevation source.")
        return source


def scan_terrain_path(path):
    global _terrain_sources, _terrain_status

    requested = Path(path).expanduser()
    warnings = []
    sources = []

    if not requested.exists():
        _terrain_sources = []
        _terrain_status = {
            "path": str(requested),
            "exists": False,
            "source_count": 0,
            "elevation_source_count": 0,
            "imagery_source_count": 0,
            "sources": [],
            "warnings": [f"Path does not exist: {requested}"],
        }
        return _terrain_status

    candidates = [requested]
    if requested.is_dir():
        candidates = [
            p for p in requested.rglob("*")
            if p.is_file() and p.suffix.lower() in _ELEVATION_EXTENSIONS
        ]

    for candidate in candidates:
        if candidate.suffix.lower() not in _ELEVATION_EXTENSIONS:
            warnings.append(f"Unsupported file extension: {candidate.name}")
            continue
        try:
            source = _scan_raster(candidate)
            sources.append(source)
            warnings.extend(source["warnings"])
        except Exception as exc:
            warnings.append(f"Could not read {candidate.name}: {exc}")

    elevation_sources = [s for s in sources if s["usable_for_elevation"]]
    elevation_sources.sort(key=_source_sort_key, reverse=True)
    _terrain_sources = elevation_sources
    _terrain_status = {
        "path": str(requested),
        "exists": True,
        "source_count": len(sources),
        "elevation_source_count": len(elevation_sources),
        "imagery_source_count": sum(1 for s in sources if s["kind"] == "imagery"),
        "sources": sources,
        "warnings": warnings if warnings else [],
    }
    if not elevation_sources:
        _terrain_status["warnings"].append("No usable elevation rasters found. Footprints may use online or zero-elevation fallback.")
    return _terrain_status


def get_terrain_status():
    if not _terrain_sources and DEFAULT_TERRAIN_PATH and _terrain_status["source_count"] == 0:
        scan_terrain_path(DEFAULT_TERRAIN_PATH)
    return _terrain_status

def extract_elevation_grid(tif_path, center_lat, center_lon, radius_km, max_size=220):
    """
    Extracts a grid of elevation data around a center point.
    """
    # Rough approximation: 1 degree latitude is ~111 km
    # This creates a bounding box to clip the raster window
    lat_offset = radius_km / 111.0
    lon_offset = radius_km / (111.0 * np.cos(np.radians(center_lat)))
    
    min_lon = center_lon - lon_offset
    max_lon = center_lon + lon_offset
    min_lat = center_lat - lat_offset
    max_lat = center_lat + lat_offset

    with rasterio.open(tif_path) as src:
        # Convert lat/lon bounds to the raster's coordinate system (assuming WGS84)
        window = from_bounds(min_lon, min_lat, max_lon, max_lat, src.transform)
        
        window = window.round_offsets().round_lengths()
        out_rows = max(1, min(max_size, int(window.height)))
        out_cols = max(1, min(max_size, int(window.width)))

        elevation_matrix = src.read(
            1,
            window=window,
            out_shape=(out_rows, out_cols),
            resampling=Resampling.bilinear,
        )
        scale_x = window.width / out_cols
        scale_y = window.height / out_rows
        window_transform = src.window_transform(window) * src.transform.scale(scale_x, scale_y)
        
        # Generate coordinates for every pixel in the matrix
        rows, cols = elevation_matrix.shape
        col_indices, row_indices = np.meshgrid(np.arange(cols), np.arange(rows))
        
        # Vectorized conversion of pixel indices to Longitude / Latitude
        lons, lats = rasterio.transform.xy(window_transform, row_indices, col_indices)

        lats = np.array(lats).reshape(rows, cols)
        lons = np.array(lons).reshape(rows, cols)
        
        return lats, lons, elevation_matrix


def _sample_raster_source(points, source):
    path = source["path"]
    try:
        with rasterio.open(path) as src:
            lons = [p["lon"] for p in points]
            lats = [p["lat"] for p in points]
            if src.crs and str(src.crs).upper() not in ("EPSG:4326", "OGC:CRS84"):
                xs, ys = transform("EPSG:4326", src.crs, lons, lats)
            else:
                xs, ys = lons, lats

            results = []
            for x, y, sample in zip(xs, ys, src.sample(zip(xs, ys), indexes=1)):
                if not (src.bounds.left <= x <= src.bounds.right and src.bounds.bottom <= y <= src.bounds.top):
                    results.append(None)
                    continue
                val = float(sample[0])
                results.append(0.0 if val < -32000 else val)
            return results
    except Exception:
        return [None] * len(points)


def _sample_local_tif(points, tif_path=None):
    """
    Sample a local GeoTIFF for [{lat, lon}, ...].
    Returns list[float | None]; None means outside coverage or unavailable.
    """
    if tif_path:
        status = scan_terrain_path(tif_path)
        sources = [s for s in status["sources"] if s["usable_for_elevation"]]
    else:
        if not _terrain_sources:
            get_terrain_status()
        sources = _terrain_sources

    if not sources:
        return [None] * len(points)

    results = [None] * len(points)
    missing = list(range(len(points)))
    for source in sources:
        if not missing:
            break
        sampled = _sample_raster_source([points[i] for i in missing], source)
        next_missing = []
        for point_idx, val in zip(missing, sampled):
            if val is None:
                next_missing.append(point_idx)
            else:
                results[point_idx] = val
        missing = next_missing
    return results


def _sample_online(points):
    if not ENABLE_ONLINE_ELEVATION:
        return [None] * len(points)

    try:
        import requests
    except ImportError:
        return [None] * len(points)

    results = []
    for i in range(0, len(points), 100):
        chunk = points[i:i + 100]
        loc_string = "|".join(f"{p['lat']},{p['lon']}" for p in chunk)
        try:
            response = requests.post(
                OPEN_TOPO_DATA_URL,
                json={"locations": loc_string},
                timeout=20,
            )
            response.raise_for_status()
            body = response.json()
            if body.get("status") != "OK":
                results.extend([None] * len(chunk))
                continue
            results.extend(r.get("elevation") for r in body.get("results", []))
        except Exception:
            results.extend([None] * len(chunk))
    return results[:len(points)]


def sample_elevations_with_sources(points, tif_path=None, allow_online=True):
    local = _sample_local_tif(points, tif_path)
    sources = ["local" if v is not None else None for v in local]
    if not allow_online or all(v is not None for v in local):
        return [0.0 if v is None else v for v in local], [
            source or "fallback_zero" for source in sources
        ]

    missing = [i for i, val in enumerate(local) if val is None]
    online = _sample_online([points[i] for i in missing])
    for idx, val in zip(missing, online):
        if val is None or val < -32000:
            local[idx] = 0.0
            sources[idx] = "fallback_zero"
        else:
            local[idx] = float(val)
            sources[idx] = "online"
    return [0.0 if v is None else v for v in local], sources


def sample_elevations(points, tif_path=None, allow_online=True):
    elevations, _sources = sample_elevations_with_sources(points, tif_path, allow_online)
    return elevations


def get_elevation_profile(lat1, lon1, lat2, lon2, num_samples=25, tif_path=None):
    from engine.propagation import haversine_km

    total_km = haversine_km(lat1, lon1, lat2, lon2)
    samples = max(2, int(num_samples))
    points = []
    for i in range(samples):
        t = i / (samples - 1)
        points.append({
            "lat": lat1 + t * (lat2 - lat1),
            "lon": lon1 + t * (lon2 - lon1),
        })

    elevations, sources = sample_elevations_with_sources(points, tif_path=tif_path)
    profile = []
    for i, (point, elevation, source) in enumerate(zip(points, elevations, sources)):
        profile.append({
            "lat": point["lat"],
            "lon": point["lon"],
            "elevation_m": elevation,
            "distance_km": (i / (samples - 1)) * total_km,
            "elevation_source": source,
        })
    return profile


def get_elevation_profiles_batch(paths, num_samples=25, tif_path=None):
    return [
        get_elevation_profile(lat1, lon1, lat2, lon2, num_samples, tif_path)
        for lat1, lon1, lat2, lon2 in paths
    ]


def _knife_edge_loss_db(nu):
    if nu <= -0.78:
        return 0.0
    if nu <= 0:
        val = 0.5 - 0.62 * nu
    elif nu <= 1:
        val = 0.5 * np.exp(-0.95 * nu)
    elif nu <= 2.4:
        val = 0.4 - np.sqrt(max(0.1184 - (0.38 - 0.1 * nu) ** 2, 0.0))
    else:
        val = 0.225 / nu
    return 60.0 if val <= 0 else max(0.0, -20.0 * np.log10(val))


def _deygout_loss_db(profile, freq_mhz, h_tx_abs, h_rx_abs):
    if len(profile) < 3:
        return 0.0

    earth_effective_radius_km = 8500.0
    d0 = profile[0]["distance_km"]
    total_km = profile[-1]["distance_km"] - d0
    if total_km <= 0:
        return 0.0

    wavelength_m = 3e8 / (freq_mhz * 1e6)
    best_nu = -float("inf")
    best_idx = -1

    for i in range(1, len(profile) - 1):
        d1 = profile[i]["distance_km"] - d0
        d2 = profile[-1]["distance_km"] - profile[i]["distance_km"]
        if d1 <= 0 or d2 <= 0:
            continue
        bulge_m = (d1 * d2 / (2.0 * earth_effective_radius_km)) * 1000.0
        los_h = h_tx_abs + (h_rx_abs - h_tx_abs) * (d1 / total_km)
        obstruction = (profile[i]["elevation_m"] + bulge_m) - los_h
        d1_m = d1 * 1000.0
        d2_m = d2 * 1000.0
        denom = wavelength_m * d1_m * d2_m
        if denom <= 0:
            continue
        nu = obstruction * np.sqrt(2.0 * (d1_m + d2_m) / denom)
        if nu > best_nu:
            best_nu = nu
            best_idx = i

    if best_idx < 0 or best_nu <= -0.78:
        return 0.0

    main_loss = _knife_edge_loss_db(best_nu)
    h_main = profile[best_idx]["elevation_m"]
    left_loss = _deygout_loss_db(profile[:best_idx + 1], freq_mhz, h_tx_abs, h_main)
    right_loss = _deygout_loss_db(profile[best_idx:], freq_mhz, h_main, h_rx_abs)
    return main_loss + left_loss + right_loss


def check_line_of_sight(profile, freq_mhz, tx_height_agl_m=0.0, rx_height_agl_m=0.0):
    clear = {
        "is_los": True,
        "max_obstruction_m": 0.0,
        "obstruction_distance_km": 0.0,
        "diffraction_loss_db": 0.0,
    }
    if len(profile) < 2:
        return clear

    earth_effective_radius_km = 8500.0
    h1 = profile[0]["elevation_m"] + tx_height_agl_m
    h2 = profile[-1]["elevation_m"] + rx_height_agl_m
    total_km = profile[-1]["distance_km"]
    if total_km <= 0:
        return clear

    max_obstruction = -float("inf")
    worst_d1 = 0.0
    for sample in profile[1:-1]:
        d1 = sample["distance_km"]
        d2 = total_km - d1
        bulge_m = (d1 * d2 / (2.0 * earth_effective_radius_km)) * 1000.0
        los_h = h1 + (h2 - h1) * (d1 / total_km)
        obstruction = (sample["elevation_m"] + bulge_m) - los_h
        if obstruction > max_obstruction:
            max_obstruction = obstruction
            worst_d1 = d1

    is_los = max_obstruction <= 1.0
    diffraction_db = 0.0 if is_los else _deygout_loss_db(profile, freq_mhz, h1, h2)
    return {
        "is_los": is_los,
        "max_obstruction_m": round(max_obstruction, 1),
        "obstruction_distance_km": round(worst_d1, 3),
        "diffraction_loss_db": round(diffraction_db, 1),
    }

if __name__ == "__main__":
    # Quick Test - Replace with a real path to a DTED/TIF file
    # lats, lons, elev = extract_elevation_grid("../data_store/terrain_cache/sample.tif", 34.05, -118.24, 5)
    # print(f"Extracted Grid Shape: {elev.shape}")
    pass
