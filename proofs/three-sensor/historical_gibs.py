"""Replay NOAA-20 and Aqua historical detection tiles for fixed locations and dates."""
import gzip
import json
import math
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from urllib.request import urlopen

import mapbox_vector_tile

BASE = "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best"
OUTPUT = Path(__file__).resolve().parent / ".data" / "outputs"
LAYERS = {"MODIS": ("MODIS_Aqua_Thermal_Anomalies_All", "1km", 6),
          "VIIRS": ("VIIRS_NOAA20_Thermal_Anomalies_375m_All", "500m", 7)}
CASES = (
    ("georgia_winter", -82.13, 32.61, date(2024, 2, 15)),
    ("oregon_summer", -119.5, 44.32, date(2024, 7, 23)),
    ("california_summer", -121.76, 39.84, date(2024, 7, 25)),
    ("california_autumn", -120.60, 39.05, date(2022, 9, 7)),
)
RADIUS = 30


def tile(lon, lat, zoom):
    degrees_per_tile = 288 / (1 << zoom)
    return int((lon + 180) / degrees_per_tile), int((90 - lat) / degrees_per_tile)


def distance_km(lon, lat, other_lon, other_lat):
    dlon, dlat = map(math.radians, (other_lon - lon, other_lat - lat))
    h = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat)) * math.cos(
        math.radians(other_lat)) * math.sin(dlon / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def fetch(job):
    name, lon, lat, day, sensor, x, y = job
    layer, matrix, zoom = LAYERS[sensor]
    url = f"{BASE}/{layer}/default/{day}/{matrix}/{zoom}/{y}/{x}.mvt"
    with urlopen(url, timeout=16) as response:
        content = response.read()
    if content.startswith(b"\x1f\x8b"):
        content = gzip.decompress(content)
    rows = {}
    for vector_layer in mapbox_vector_tile.decode(content).values():
        for feature in vector_layer["features"]:
            attrs = {key.upper(): val for key, val in feature["properties"].items()}
            if "LATITUDE" not in attrs or "LONGITUDE" not in attrs:
                raise ValueError(f"Missing original coordinates. Keys: {sorted(attrs)}")
            source_lon, source_lat = float(attrs["LONGITUDE"]), float(attrs["LATITUDE"])
            if distance_km(lon, lat, source_lon, source_lat) <= RADIUS:
                rows[json.dumps(attrs, sort_keys=True)] = attrs
    return (name, str(day), sensor), rows


if __name__ == "__main__":
    jobs = []
    for name, lon, lat, start in CASES:
        for offset in range(3):
            for sensor, (_, _, zoom) in LAYERS.items():
                # 0.45 degrees of margin encloses a 30 km circle at these case latitudes.
                left, top = tile(lon - 0.45, lat + 0.45, zoom)
                right, bottom = tile(lon + 0.45, lat - 0.45, zoom)
                for y in range(top, bottom + 1):
                    for x in range(left, right + 1):
                        jobs.append((name, lon, lat, start + timedelta(days=offset), sensor, x, y))
    grouped = {}
    with ThreadPoolExecutor(max_workers=6) as workers:
        for key, records in workers.map(fetch, jobs):
            grouped.setdefault(key, {}).update(records)
    assert len(grouped) == len(CASES) * 3 * len(LAYERS)
    for sensor in LAYERS:
        assert any(rows for (_, _, family), rows in grouped.items() if family == sensor)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result = {
        "tiles_requested": len(jobs), "radius_km": RADIUS,
        "meaning": "Counts of returned hotspots after spatial filtering. Zero detections leaves coverage unknown.",
        "counts": [{"case": case, "date_utc": day, "sensor": sensor, "observations": len(rows)}
                   for (case, day, sensor), rows in sorted(grouped.items())],
        "observations": [{"case": case, "date_utc": day, "sensor": sensor, **record}
                         for (case, day, sensor), rows in sorted(grouped.items())
                         for record in rows.values()],
    }
    totals = defaultdict(dict)
    for (case, day, sensor), rows in grouped.items():
        totals[case][sensor] = totals[case].get(sensor, 0) + len(rows)
    fit_case = "california_summer"
    fit = totals[fit_case]
    factor = fit["VIIRS"] / fit["MODIS"]
    result["count_scaling_diagnostic"] = {
        "fit_case": fit_case,
        "factor": factor,
        "cases": [{"case": case, **counts,
                   "scaled_modis": round(factor * counts["MODIS"], 2),
                   "raw_absolute_error": abs(counts["VIIRS"] - counts["MODIS"]),
                   "scaled_absolute_error": round(abs(counts["VIIRS"] - factor * counts["MODIS"]), 2)}
                  for case, counts in sorted(totals.items()) if case != fit_case],
        "limits": "Small selected windows with unknown coverage. These comparisons are an illustration, not validation."
    }
    (OUTPUT / "historical-gibs.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "observations"}, indent=2))

