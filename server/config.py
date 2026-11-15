"""Paths and settings. Secrets come from the environment or a local .env file."""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = pathlib.Path(os.environ.get("FIRE_DB_PATH", ROOT / "data" / "fire.duckdb"))
WEB_DIR = ROOT / "web"

MAX_CELLS = 40_000              # most cells sent to the map in one answer
MAX_CSV_ROWS = 200_000          # most rows in one download
CALENDAR_CELL_M = 1500          # the area calendar counts cells of this size


def _load_dotenv():
    """Read KEY=VALUE lines from .env into the environment (existing values win)."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

# pipeline/check_keys.py tests them. The server uses EE_PROJECT for the Landsat pictures of a fire;
# FIRMS_MAP_KEY is not used yet.
FIRMS_MAP_KEY = os.environ.get("FIRMS_MAP_KEY", "")                    # detections after the yearly archive
EE_PROJECT = os.environ.get("EE_PROJECT", "")                          # Google Earth Engine project id
EE_SERVICE_ACCOUNT_KEY = os.environ.get("EE_SERVICE_ACCOUNT_KEY", "")  # optional path to a key file
EE_SERVICE_ACCOUNT_JSON = os.environ.get("EE_SERVICE_ACCOUNT_JSON", "")  # or the text of that file (Vercel)
