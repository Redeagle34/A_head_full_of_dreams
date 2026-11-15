"""Orbit data for the fire-watching satellites.

Source: CelesTrak GP data (https://celestrak.org/NORAD/documentation/gp-data-formats.php),
public, no key. One two-line element set (TLE) per satellite; the web page turns it
into positions and overpass times with the SGP4 model (satellite.js).

CelesTrak asks clients not to fetch more often than the data changes, so answers
are cached on disk for six hours. If CelesTrak cannot be reached, the last cache
is used, and failing that the snapshot committed in web/data/tle.json.

Run  python -m server.satellites  to refresh that snapshot.
"""
import datetime
import json
import urllib.request

from .config import ROOT, WEB_DIR

# NORAD catalogue numbers.
SATELLITES = {"terra": 25994, "aqua": 27424, "suomi-npp": 37849,
              "noaa-20": 43013, "noaa-21": 54234, "landsat-8": 39084}
URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR={}&FORMAT=TLE"
CACHE = ROOT / "data" / "tle_cache.json"
SNAPSHOT = WEB_DIR / "data" / "tle.json"
MAX_AGE = datetime.timedelta(hours=6)


def _download():
    out = {}
    for key, number in SATELLITES.items():
        req = urllib.request.Request(URL.format(number), headers={"User-Agent": "burning-calendar"})
        with urllib.request.urlopen(req, timeout=20) as r:
            lines = [ln.rstrip() for ln in r.read().decode().splitlines() if ln.strip()]
        if len(lines) != 3 or not lines[1].startswith("1 ") or not lines[2].startswith("2 "):
            raise ValueError(f"unexpected answer for {key}: {lines[:1]}")
        out[key] = {"name": lines[0].strip(), "line1": lines[1], "line2": lines[2]}
    return {"fetched": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "source": "CelesTrak", "satellites": out}


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def tle():
    """Current element sets, from cache when fresh enough."""
    cached = _read(CACHE)
    now = datetime.datetime.now(datetime.timezone.utc)
    if cached and now - datetime.datetime.fromisoformat(cached["fetched"]) < MAX_AGE:
        return cached
    try:
        fresh = _download()
    except Exception:                       # network down, CelesTrak busy, odd answer
        return cached or _read(SNAPSHOT) or {"fetched": None, "source": "none", "satellites": {}}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(fresh), encoding="utf-8")
    return fresh


if __name__ == "__main__":
    data = _download()
    SNAPSHOT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print("wrote", SNAPSHOT, "with", len(data["satellites"]), "satellites, fetched", data["fetched"])
