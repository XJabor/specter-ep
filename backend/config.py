import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data_store"
TERRAIN_CACHE_DIR = DATA_DIR / "terrain_cache"
LIBRARY_DIR = DATA_DIR / "library"


def load_env_file(path):
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ[key] = value


load_env_file(BASE_DIR / ".env")

DEFAULT_TERRAIN_PATH = Path(
    os.environ.get("SPECTER_TERRAIN_PATH", TERRAIN_CACHE_DIR / "Oahu_Tiff.tif")
).expanduser()

ENABLE_ONLINE_ELEVATION = os.environ.get("SPECTER_ONLINE_ELEVATION", "true").lower() == "true"
OPEN_TOPO_DATA_URL = os.environ.get(
    "SPECTER_ELEVATION_URL",
    "https://api.opentopodata.org/v1/srtm30m",
)

DEFAULT_MAP_CENTER = {
    "lat": float(os.environ.get("SPECTER_DEFAULT_LAT", "21.4765")),
    "lon": float(os.environ.get("SPECTER_DEFAULT_LON", "-157.9647")),
    "zoom": float(os.environ.get("SPECTER_DEFAULT_ZOOM", "10.5")),
}

DEFAULT_VERTICAL_CAP_M = float(os.environ.get("SPECTER_VERTICAL_CAP_M", "3048"))
APP_HOST = os.environ.get("SPECTER_EP_HOST", "0.0.0.0")
APP_PORT = int(os.environ.get("SPECTER_EP_PORT", "5050"))
MAPBOX_TOKEN = os.environ.get("MAPBOX_TOKEN", "")
