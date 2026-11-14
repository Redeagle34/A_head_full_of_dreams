"""Check Landsat optical coverage and cloud flags at fixed incident locations."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

import rasterio
from rasterio.windows import Window
from pyproj import Transformer
from shapely import transform
from shapely.geometry import Polygon, box, shape

DATA = Path(__file__).resolve().parent / ".data"
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/token"
CASES = {
    "park_fire": (-121.76, 39.84, "2024-07-24", "2024-08-01"),
    "oregon": (-119.5, 44.32, "2024-07-23", "2024-08-01"),
    "georgia_live_selection": (-82.13371, 32.6085, "2026-11-09", "2026-11-10"),
}
REFERENCE = {"georgia_live_selection": "2026-11-09T14:56:00+00:00"}
WINDOWS_MINUTES = (30, 90, 180)
FLAGS = {0: "fill", 1: "dilated_cloud", 2: "cirrus", 3: "cloud",
         4: "cloud_shadow", 5: "snow", 7: "water"}


def get_json(url):
    with urlopen(url, timeout=20) as response:
        return json.load(response)


def status(value):
    if value is None or value & 1:
        return "unobserved"
    if any(value & (1 << bit) for bit in (1, 2, 3, 4)):
        return "cloud_or_shadow"
    if value & ((1 << 5) | (1 << 7)):
        return "snow_or_water"
    return "clear_land"


def inspect(case, footprint=None):
    lon, lat, start, end = case
    bounds = footprint.bounds if footprint is not None else (lon-0.002, lat-0.002, lon+0.002, lat+0.002)
    params = urlencode({
        "collections": "landsat-c2-l2",
        "bbox": ",".join(map(str, bounds)),
        "datetime": f"{start}T00:00:00Z/{end}T00:00:00Z",
        "limit": 10,
    })
    scenes = get_json(f"{STAC}/search?{params}")["features"]
    samples = []
    for scene in scenes:
        href = scene["assets"]["qa_pixel"]["href"]
        account = urlsplit(href).hostname.split(".")[0]
        container = urlsplit(href).path.split("/")[1]
        token = get_json(f"{SAS}/{account}/{container}")["token"]
        with rasterio.open(f"{href}?{token}") as qa:
            project = Transformer.from_crs(4326, qa.crs, always_xy=True).transform
            x, y = project(lon, lat)
            row, column = qa.index(x, y)
            value = (int(next(qa.sample([(x, y)]))[0])
                     if 0 <= row < qa.height and 0 <= column < qa.width else None)
            area = footprint_qa(qa, transform(footprint, project, interleaved=False)) if footprint is not None else None
        samples.append({"scene": scene["id"], "acquired_utc": scene["properties"]["datetime"],
                        "qa_pixel": value, "flags": [flag for bit, flag in FLAGS.items()
                                                    if value is not None and value & (1 << bit)],
                        "coverage": status(value), "footprint_fractions": area})
    return {"catalog_scenes": len(scenes), "samples": samples}


def footprint_qa(qa, footprint):
    from collections import defaultdict
    inverse = ~qa.transform
    pixels = Polygon([inverse * (x, y) for x, y in footprint.exterior.coords])
    x0, y0, x1, y1 = pixels.bounds
    from math import ceil, floor, isclose
    left, top = max(0, floor(x0)), max(0, floor(y0))
    right, bottom = min(qa.width, ceil(x1)), min(qa.height, ceil(y1))
    fractions = defaultdict(float)
    if left < right and top < bottom:
        values = qa.read(1, window=Window(left, top, right - left, bottom - top))
        for dy, row in enumerate(values):
            for dx, value in enumerate(row):
                x, y = left + dx, top + dy
                fraction = pixels.intersection(box(x, y, x + 1, y + 1)).area / pixels.area
                if fraction > 0:
                    fractions[status(int(value))] += fraction
    total = sum(fractions.values())
    if not isclose(total, 1, abs_tol=1e-8):
        fractions["unobserved"] += max(0, 1 - total)
    assert isclose(sum(fractions.values()), 1, abs_tol=1e-8)
    return {key: round(value, 6) for key, value in fractions.items()}


if __name__ == "__main__":
    assert [status(v) for v in (None, 1, 8, 16, 32, 64, 128)] == [
        "unobserved", "unobserved", "cloud_or_shadow", "cloud_or_shadow",
        "snow_or_water", "clear_land", "snow_or_water"]
    assert status(64 | 16) == "cloud_or_shadow"
    from numpy import array
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin
    with MemoryFile() as memory:
        with memory.open(driver="GTiff", width=2, height=1, count=1, dtype="uint16",
                         transform=from_origin(10, 10, 1, 1)) as grid:
            grid.write(array([[64, 8]], dtype="uint16"), 1)
            assert footprint_qa(grid, box(9.5, 9, 11.5, 10)) == {
                "clear_land": 0.5, "cloud_or_shadow": 0.25, "unobserved": 0.25}
    live = json.loads((DATA / "outputs" / "nearby.geojson").read_text(encoding="utf-8"))
    footprint = shape(next(feature["geometry"] for feature in live["features"]
                           if feature["id"] == "d233165e9bd836730e9ae3d8"))
    results = {}
    for name, case in CASES.items():
        try:
            results[name] = inspect(case, footprint if name in REFERENCE else None)
        except Exception as exc:
            # Transport exceptions can contain a signed asset URL.
            results[name] = {"error": type(exc).__name__}
    for name, timestamp in REFERENCE.items():
        result = results[name]
        if "samples" not in result:
            continue
        reference = datetime.fromisoformat(timestamp)
        for sample in result["samples"]:
            acquired = datetime.fromisoformat(sample["acquired_utc"])
            sample["minutes_from_modis"] = round(abs(acquired - reference) / timedelta(minutes=1), 2)
        result["modis_time_utc"] = timestamp
        result["coverage_by_window"] = {
            str(minutes): (
                "at_least_90_percent_clear" if any(
                    sample["minutes_from_modis"] <= minutes and (sample["footprint_fractions"].get("clear_land", 0) >= 0.9)
                    for sample in result["samples"]
                ) else "no_scene_with_90_percent_clear_within_window"
            )
            for minutes in WINDOWS_MINUTES
        }
    output = DATA / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    result = json.dumps(results, indent=2)
    (output / "landsat-coverage.json").write_text(result + "\n", encoding="utf-8")
    print(result)
    if any("error" in case or not case["samples"] for case in results.values()):
        raise SystemExit(1)

