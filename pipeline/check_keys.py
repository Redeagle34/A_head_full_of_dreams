"""Check that the keys in .env work. Values are never printed.

Run:  python pipeline/check_keys.py
Exit code 0 when every service answers, 1 otherwise.
"""
import json
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server import config      # noqa: E402  (loads .env)


def check_firms():
    """Ask FIRMS for the status of the key, then for one day of detections in a small box."""
    key = config.FIRMS_MAP_KEY
    if not key:
        return False, "FIRMS_MAP_KEY is empty in .env"
    base = "https://firms.modaps.eosdis.nasa.gov"
    try:
        with urllib.request.urlopen(f"{base}/mapserver/mapkey_status/?MAP_KEY={key}", timeout=60) as r:
            status = json.loads(r.read())
        with urllib.request.urlopen(f"{base}/api/area/csv/{key}/VIIRS_NOAA20_NRT/-122,39,-121,40/1", timeout=60) as r:
            lines = r.read().decode().splitlines()
    except Exception as e:                      # the URL holds the key, so only the error type is shown
        return False, f"request failed ({type(e).__name__})"
    if not lines or not lines[0].startswith("latitude"):
        return False, "key rejected: the data request did not return detections"
    return True, (f"key accepted; {status.get('current_transactions')} of {status.get('transaction_limit')} "
                  f"requests used in this window; sample request returned {len(lines) - 1} detections")


def check_earth_engine():
    """Sign in and read one gridMET value (the weather source of the danger model)."""
    if not config.EE_PROJECT:
        return False, "EE_PROJECT is empty in .env"
    try:
        import ee
    except ImportError:
        return False, "package missing: pip install earthengine-api"
    try:
        if config.EE_SERVICE_ACCOUNT_KEY:
            email = json.loads(pathlib.Path(config.EE_SERVICE_ACCOUNT_KEY).read_text())["client_email"]
            ee.Initialize(ee.ServiceAccountCredentials(email, config.EE_SERVICE_ACCOUNT_KEY), project=config.EE_PROJECT)
        else:
            ee.Initialize(project=config.EE_PROJECT)
        image = ee.ImageCollection("IDAHO_EPSCOR/GRIDMET").filterDate("2024-07-24", "2024-07-25").first()
        point = ee.Geometry.Point([-121.8, 39.8])           # Park Fire area
        erc = image.select("erc").reduceRegion(ee.Reducer.first(), point, 4000).get("erc").getInfo()
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:200]}"
    return True, f"signed in; gridMET energy release component at the Park Fire, 24 July 2024 = {erc}"


def main():
    results = {"FIRMS": check_firms(), "Earth Engine": check_earth_engine()}
    for name, (ok, message) in results.items():
        print(f"{'OK  ' if ok else 'FAIL'} {name}: {message}")
    sys.exit(0 if all(ok for ok, _ in results.values()) else 1)


if __name__ == "__main__":
    main()
