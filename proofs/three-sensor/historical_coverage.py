"""Join historical hotspot cell-days to candidate overpasses and probe fire-mask access."""
import csv
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from pyproj import Transformer

from historical_gibs import CASES, RADIUS, distance_km

OUTPUT = Path(__file__).resolve().parent / ".data" / "outputs"
CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
PRODUCT = {"MODIS": ("MYD14", "061", ".hdf"), "VIIRS": ("VJ114IMG", "002", ".nc")}
GRID = Transformer.from_crs(4326, 5070, always_xy=True)
CENTERS = {name: (lon, lat) for name, lon, lat, _ in CASES}


def catalog(job):
    case, day, sensor = job
    lon, lat = CENTERS[case]
    product, version, suffix = PRODUCT[sensor]
    bounds = (lon - 0.45, lat - 0.45, lon + 0.45, lat + 0.45)
    url = CMR + "?" + urlencode({
        "short_name": product, "version": version, "bounding_box": ",".join(map(str, bounds)),
        "temporal": f"{day}T00:00:00Z,{day}T23:59:59Z", "page_size": 50,
    })
    with urlopen(url, timeout=20) as response:
        entries = json.load(response)["feed"]["entry"]
    links = [link["href"] for entry in entries for link in entry.get("links", [])
             if link.get("href", "").startswith("https://data.lpdaac.earthdatacloud.nasa.gov/")
             and link["href"].endswith(suffix)]
    return job, {"granules": len(entries), "sample": next(iter(links), None)}


def probe(url):
    headers = {"Range": "bytes=0-31"}
    if token := os.environ.get("EARTHDATA_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(url, headers=headers), timeout=20) as response:
            prefix = response.read(16)
            return {"http": response.status, "host": urlsplit(response.url).hostname,
                    "raster_signature": prefix.startswith((b"\x0e\x03\x13\x01", b"\x89HDF", b"CDF"))}
    except HTTPError as error:
        return {"http": error.code, "host": urlsplit(error.url).hostname}


def main():
    archive = json.loads((OUTPUT / "historical-gibs.json").read_text(encoding="utf-8"))
    jobs = {(row["case"], row["date_utc"], row["sensor"]) for row in archive["counts"]}
    with ThreadPoolExecutor(max_workers=6) as executor:
        coverage = dict(executor.map(catalog, sorted(jobs)))
    detections = {}
    for row in archive["observations"]:
        case, day, sensor = row["case"], row["date_utc"], row["sensor"]
        lon, lat = row["LONGITUDE"], row["LATITUDE"]
        assert distance_km(*CENTERS[case], lon, lat) <= RADIUS
        x, y = GRID.transform(lon, lat)
        cell = (case, day, math.floor(x / 375), math.floor(y / 375))
        counts = detections.setdefault(cell, {"MODIS": 0, "VIIRS": 0})
        counts[sensor] += 1

    joined = []
    for (case, day, x, y), counts in sorted(detections.items()):
        row = {"case": case, "date_utc": day, "grid_epsg": 5070, "i": x, "j": y}
        for sensor, count in counts.items():
            granules = coverage[case, day, sensor]["granules"]
            row[sensor + "_detections"] = count
            row[sensor + "_region_candidate_granules"] = granules
            # Catalog granules intersect the search region, which cannot establish
            # whether this cell was observed and clear.
            row[sensor + "_status"] = "detected" if count else "coverage_unknown"
        joined.append(row)
    with (OUTPUT / "historical-cell-days.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(joined[0]))
        writer.writeheader()
        writer.writerows(joined)
    for sensor in PRODUCT:
        assert sum(row[sensor + "_detections"] for row in joined) == sum(
            row["observations"] for row in archive["counts"] if row["sensor"] == sensor)
    probes = {}
    for sensor in PRODUCT:
        sample = next(value["sample"] for key, value in coverage.items() if key[2] == sensor and value["sample"])
        probes[sensor] = {"file": sample.rsplit("/", 1)[1], **probe(sample)}
    result = {
        "coverage_join": "CMR regional granule candidates only; individual fire-mask pixels have not been decoded.",
        "archive_case_days": len({(case, day) for case, day, _ in jobs}),
        "grid_cell_days": len(joined),
        "both_sensors_detected_in_cell_day": sum(
            row["MODIS_detections"] > 0 and row["VIIRS_detections"] > 0 for row in joined),
        "candidate_overpasses": [{"case": case, "date_utc": day, "sensor": sensor, "granules": info["granules"]}
                                 for (case, day, sensor), info in sorted(coverage.items())],
        "raw_mask_access": probes,
    }
    (OUTPUT / "historical-coverage-join.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "candidate_overpasses"}, indent=2))


if __name__ == "__main__":
    main()

