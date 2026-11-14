"""Run the three-sensor proof against downloaded NASA FIRMS footprint bundles."""
import argparse
import csv
import hashlib
import json
import math
import re
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile

import shapefile
from pyproj import Geod, Transformer
from shapely import STRtree, transform
from shapely.geometry import Point, Polygon, box, mapping, shape

ROOT = Path(__file__).resolve().parent
DATA = ROOT / ".data"
FIRMS = "https://firms.modaps.eosdis.nasa.gov/api/kml_fire_footprints"
STATES_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_20m.zip"
REGION = "usa_contiguous_and_hawaii"
PRODUCTS = {"c6.1": "MODIS", "noaa-20-viirs-c2": "VIIRS",
            "noaa-21-viirs-c2": "VIIRS", "landsat": "Landsat"}
CELL = 375
GEOD = Geod(ellps="WGS84")
GRID_PROJECTION = Transformer.from_crs(4326, 5070, always_xy=True)


def sources():
    for product in PRODUCTS:
        yield DATA / f"{REGION}_{product}.kmz", f"{FIRMS}/{REGION}/7d/{product}", product


def download(path, url):
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = response.read()
    temporary = path.with_suffix(".part")
    temporary.write_bytes(payload)
    temporary.replace(path)


def parse(path, product):
    with ZipFile(path) as archive:
        with archive.open(next(name for name in archive.namelist() if name.endswith(".kml"))) as file:
            for _, mark in ET.iterparse(file, events=("end",)):
                if not mark.tag.endswith("}Placemark"):
                    continue
                ring = mark.findtext(".//{*}outerBoundaryIs/{*}LinearRing/{*}coordinates")
                if ring:
                    attrs = dict(re.findall(r"<b>([^:]+):\s*</b>\s*([^<\r\n]+)", mark.findtext("{*}description", "")))
                    lat, lon = float(attrs["Latitude"]), float(attrs["Longitude"])
                    observed = datetime.strptime(attrs["Detection Time"].strip(), "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
                    platform = attrs["Sensor"].strip()
                    native_id = hashlib.sha256(f"{platform}|{observed.isoformat()}|{lon}|{lat}".encode()).hexdigest()[:24]
                    polygon = Polygon([tuple(map(float, coord.split(",")[:2])) for coord in ring.split()])
                    if not polygon.is_valid or polygon.area <= 0:
                        raise ValueError(f"Invalid footprint in {path.name}: {native_id}")
                    yield {
                        "id": native_id, "sensor": PRODUCTS[product], "platform": platform,
                        "product": product, "batch": path.name, "time": observed, "lon": lon, "lat": lat,
                        "confidence": next(value.strip() for key, value in attrs.items() if key.startswith("Confidence")),
                        "footprint": polygon,
                    }
                mark.clear()


def boundary_index():
    with shapefile.Reader(str(DATA / "states.zip")) as reader:
        states = [(item.record["STUSPS"], shape(item.shape.__geo_interface__))
                  for item in reader.iterShapeRecords() if int(item.record["STATEFP"]) < 60
                  and item.record["STUSPS"] not in ("AK", "DC", "HI")]
    assert len(states) == 48
    return states, STRtree([item[1] for item in states])


def load():
    states, tree = boundary_index()
    observations = {}
    counts = Counter({path.name: 0 for path, _, _ in sources()})
    outside = Counter({path.name: 0 for path, _, _ in sources()})
    for path, _, product in sources():
        for row in parse(path, product):
            counts[path.name] += 1
            candidates = tree.query(Point(row["lon"], row["lat"]), predicate="intersects")
            if len(candidates):
                row["state"] = states[candidates[0]][0]
                observations.setdefault(row["id"], row)
            else:
                outside[path.name] += 1
    return observations, counts, outside


def match(observations, minutes):
    by_sensor = defaultdict(list)
    for row in observations.values():
        by_sensor[row["sensor"]].append(row)
    result = []
    for name in ("VIIRS", "Landsat"):
        candidates = by_sensor[name]
        tree = STRtree([row["footprint"] for row in candidates])
        for modis in by_sensor["MODIS"]:
            for index in tree.query(modis["footprint"], predicate="intersects"):
                other = candidates[index]
                delta = abs((modis["time"] - other["time"]).total_seconds()) / 60
                if delta <= minutes and modis["footprint"].intersection(other["footprint"]).area > 0:
                    result.append((modis["id"], other["id"], name, delta))
    return result


def nearby(rows, lon, lat, radius_km, start, end):
    return [row for row in rows if start <= row["time"] < end
            and abs(GEOD.inv(lon, lat, row["lon"], row["lat"])[2]) <= radius_km * 1000]


def grid_rows(rows):
    for row in rows:
        crs = 5070
        polygon = transform(row["footprint"], GRID_PROJECTION.transform, interleaved=False)
        x0, y0, x1, y1 = polygon.bounds
        for x in range(math.floor(x0 / CELL), math.ceil(x1 / CELL)):
            for y in range(math.floor(y0 / CELL), math.ceil(y1 / CELL)):
                cell = box(x * CELL, y * CELL, (x + 1) * CELL, (y + 1) * CELL)
                fraction = polygon.intersection(cell).area / polygon.area
                if fraction > 0:
                    yield {"observation_id": row["id"], "grid_crs": crs, "i": x, "j": y,
                           "fraction_of_footprint": fraction}


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Replace local inputs with the current rolling bundles")
    args = parser.parse_args()
    DATA.mkdir(exist_ok=True)
    for path, url in [(DATA / "states.zip", STATES_URL),
                      *((path, url) for path, url, _ in sources())]:
        if args.refresh or not path.exists():
            download(path, url)

    observations, counts, outside = load()
    assert set(row["sensor"] for row in observations.values()) == set(PRODUCTS.values())
    # Replay the same identifiers as a second batch and assert distinct row count.
    repeated, _, _ = load()
    assert set(observations | repeated) == set(observations) == set(repeated)

    thresholds = (30, 90, 180)
    comparisons = {minutes: match(observations, minutes) for minutes in thresholds}
    accepted = comparisons[180]
    by_parent = defaultdict(set)
    for parent, _, sensor, _ in accepted:
        by_parent[parent].add(sensor)
    if not by_parent:
        raise RuntimeError("This rolling sample has no intersecting MODIS comparisons within 180 minutes. Preserve it and select a different seven-day batch for the overlap proof.")
    # Pick a live overlapping example for the local query-and-export check.
    center_id = max(by_parent, key=lambda key: (len(by_parent[key]), key))
    center = observations[center_id]
    start = min(row["time"] for row in observations.values())
    end = max(row["time"] for row in observations.values())
    end += timedelta(seconds=1)
    selected = nearby(observations.values(), center["lon"], center["lat"], 20, start, end)
    ids = {row["id"] for row in selected}

    output = DATA / "outputs"
    output.mkdir(exist_ok=True)
    with (output / "national.ndjson").open("w", encoding="utf-8") as file:
        for row in observations.values():
            record = {key: value for key, value in row.items() if key not in ("time", "footprint")}
            record.update(time_utc=row["time"].isoformat(), footprint=mapping(row["footprint"]))
            print(json.dumps(record), file=file)
    native = [{key: value for key, value in row.items() if key not in ("footprint", "time")}
              | {"time_utc": row["time"].isoformat()} for row in selected]
    write_csv(output / "observations.csv", list(native[0]), native)
    features = [{"type": "Feature", "id": row["id"], "properties": attrs,
                 "geometry": mapping(row["footprint"])} for row, attrs in zip(selected, native)]
    (output / "nearby.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")

    grid = list(grid_rows(selected))
    write_csv(output / "grid-evidence.csv", list(grid[0]), grid)
    fractions = defaultdict(float)
    grid_counts = Counter()
    for item in grid:
        key = item["observation_id"]
        fractions[key] += item["fraction_of_footprint"]
        grid_counts[key] += 1
    assert set(fractions) == ids and all(math.isclose(value, 1, abs_tol=1e-8) for value in fractions.values())
    assert any(grid_counts[row["id"]] > 1 for row in selected if row["sensor"] == "MODIS")
    with (output / "observations.csv").open(encoding="utf-8", newline="") as file:
        assert {row["id"] for row in csv.DictReader(file)} == ids == {item["id"] for item in features}
    assert not nearby(selected, center["lon"], center["lat"], 20, end, end)

    local_matches = [{"modis_id": parent, "comparison_id": other, "comparison_sensor": sensor, "minutes_apart": delta}
                     for parent, other, sensor, delta in accepted if parent in ids and other in ids]
    write_csv(output / "candidate-matches.csv", ["modis_id", "comparison_id", "comparison_sensor", "minutes_apart"], local_matches)
    summary = {
        "input_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path, _, _ in sources()},
        "boundary_sha256": hashlib.sha256((DATA / "states.zip").read_bytes()).hexdigest(),
        "raw_footprints": dict(counts), "outside_state_mask": dict(outside),
        "distinct_us_native_observations": len(observations),
        "observations_by_sensor": dict(Counter(row["sensor"] for row in observations.values())),
        "states_with_detections": sorted({row["state"] for row in observations.values()}),
        "observed_interval_utc": [start.isoformat(), end.isoformat()],
        "candidate_match_pairs_by_minutes": {
            str(minutes): {name: sum(pair[2] == name for pair in pairs) for name in ("VIIRS", "Landsat")}
            for minutes, pairs in comparisons.items()
        },
        "modis_parents_with_both_comparisons_at_180_minutes": sum(len(sensors) == 2 for sensors in by_parent.values()),
        "selection": {"state": center["state"], "longitude": center["lon"], "latitude": center["lat"], "radius_km": 20,
                      "native_observations": len(ids), "grid_evidence_rows": len(grid), "candidate_pairs": len(local_matches),
                      "center_candidate_sensors": sorted(by_parent[center_id])},
        "coverage": "Unknown for unmatched detections. MVP scope is the contiguous 48 states.",
        "limits": "Pair counts describe overlapping estimated detection footprints, not accuracy, confirmed wildfire, or event counts.",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    calendar = Counter((row["time"].date().isoformat(), row["sensor"]) for row in selected)
    write_csv(output / "observed-activity.csv", ["date_utc", "sensor", "native_detections"],
              [{"date_utc": date, "sensor": sensor, "native_detections": count}
               for (date, sensor), count in sorted(calendar.items())])
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

