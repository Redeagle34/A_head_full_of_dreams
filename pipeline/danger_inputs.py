"""Pull the inputs of the danger model from Google Earth Engine, for every fire.

Run:  python pipeline/danger_inputs.py            (after pipeline/fire_events.py; needs EE_PROJECT in .env)
      python pipeline/danger_inputs.py --check    compare 200 rows with the reference training table
Output: data/danger/inputs_place.parquet     one row per 0.04 degree cell (about 4 km)
        data/danger/inputs_weather.parquet   one row per cell and first day of a fire

The run can be stopped and started again: finished pieces are kept in data/raw/ee/.

Inputs (same definitions as the reference models in proofs/us-experiments, plus built_5km):
  weather   gridMET, 4 km: erc, bi, fm100, fm1000, vpd, vs, rmin, rmax, tmmx, pr, srad on the first day;
            erc, fm100, vpd, vs the day before (_l1); erc7 mean of the 7 days before;
            pr30 rain and erc_max30 highest erc of the 30 days before
  place     elevation, slope (SRTM); pop_density (GPW v4.11, 2020); frg, mfri (LANDFIRE fire regime);
            lc (MCD12Q1 2019 land cover); treecover (MOD44B 2019);
            built_5km = built-up surface within 5 km, in m2 (GHSL 2020)
"""
import json
import pathlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server import config      # noqa: E402  (loads .env)

FIRES = f"'{(ROOT / 'data' / 'danger' / 'fires.parquet').as_posix()}'"
OUT = ROOT / "data" / "danger"
CACHE = ROOT / "data" / "raw" / "ee"
# Reference models and their training table (branch us-findings, proofs/us-experiments/models). Copy with:
#   git show origin/us-findings:proofs/us-experiments/models/training_table.parquet > data/raw/reference/training_table.parquet
REFERENCE = ROOT / "data" / "raw" / "reference"
CELL = 0.04                     # degrees; gridMET pixels are 1/24 degree
PLACE_BATCH = 4000              # points per request, one image
BUILT_BATCH = 500               # circles per request
WEATHER_BATCH = 500             # points per request, one day
WORKERS = 16
FIRST_YEAR = 2012               # first VIIRS year


def connect():
    import ee
    if config.EE_SERVICE_ACCOUNT_KEY:
        email = json.loads(pathlib.Path(config.EE_SERVICE_ACCOUNT_KEY).read_text())["client_email"]
        ee.Initialize(ee.ServiceAccountCredentials(email, config.EE_SERVICE_ACCOUNT_KEY), project=config.EE_PROJECT)
    else:
        ee.Initialize(project=config.EE_PROJECT)
    return ee


def place_image(ee):
    """The fixed inputs, sampled at 4 km like the reference models."""
    dem = ee.Image("USGS/SRTMGL1_003")
    first = lambda name, a, b: ee.ImageCollection(name).filterDate(a, b).first()      # noqa: E731
    static = ee.Image.cat([
        dem.select("elevation"), ee.Terrain.slope(dem).rename("slope"),
        first("CIESIN/GPWv411/GPW_Population_Density", "2020-01-01", "2021-01-01").rename("pop_density"),
        ee.ImageCollection("LANDFIRE/Fire/FRG/v1_2_0").mosaic().rename("frg"),
        ee.ImageCollection("LANDFIRE/Fire/MFRI/v1_2_0").mosaic().rename("mfri"),
        first("MODIS/061/MCD12Q1", "2019-01-01", "2020-01-01").select("LC_Type1").rename("lc"),
        first("MODIS/061/MOD44B", "2019-01-01", "2020-01-01").select("Percent_Tree_Cover").rename("treecover"),
    ])
    return static


def built_nearby(ee, points):
    """Built-up surface (m2) within 5 km of each point: exact sum of the 100 m GHSL pixels in the circle."""
    built = ee.Image("JRC/GHSL/P2023A/GHS_BUILT_S/2020").select("built_surface")
    circles = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([lon, lat]).buffer(5000), {"key": key})
                                    for key, lat, lon in points])
    result = built.reduceRegions(collection=circles, reducer=ee.Reducer.sum().setOutputs(["built_5km"]),
                                 scale=100, tileScale=4).select(["key", "built_5km"], retainGeometry=False).getInfo()
    return [f["properties"] for f in result["features"]]


def weather_image(ee, day):
    gm = ee.ImageCollection("IDAHO_EPSCOR/GRIDMET")
    d = ee.Date(day)
    now = gm.filterDate(d, d.advance(1, "day")).first().select(
        ["erc", "bi", "fm100", "fm1000", "vpd", "vs", "rmin", "rmax", "tmmx", "pr", "srad"])
    before = gm.filterDate(d.advance(-1, "day"), d).first().select(
        ["erc", "fm100", "vpd", "vs"], ["erc_l1", "fm100_l1", "vpd_l1", "vs_l1"])
    month = gm.filterDate(d.advance(-30, "day"), d)
    return ee.Image.cat([now, before,
                         gm.filterDate(d.advance(-7, "day"), d).select("erc").mean().rename("erc7"),
                         month.select("pr").sum().rename("pr30"),
                         month.select("erc").max().rename("erc_max30")])


def sample(ee, image, scale, points):
    """points: [(key, lat, lon)] -> [{key, band: value, ...}]"""
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([lon, lat]), {"key": key}) for key, lat, lon in points])
    result = image.sampleRegions(collection=fc, scale=scale, geometries=False).getInfo()
    return [f["properties"] for f in result["features"]]


def run(name, jobs, work):
    """Run every job not yet in the cache. jobs: {piece name: argument}. Returns the cached rows."""
    folder = CACHE / name
    folder.mkdir(parents=True, exist_ok=True)

    def one(piece, argument):
        path = folder / f"{piece}.json"
        for attempt in range(6):
            try:
                path.write_text(json.dumps(work(argument)))
                return None
            except Exception as e:      # Earth Engine is busy or the piece is too large: wait and retry
                error = str(e)[:150]
                time.sleep(min(120, 5 * 2 ** attempt))
        return f"{piece}: {error}"

    todo = {p: a for p, a in jobs.items() if not (folder / f"{p}.json").exists()}
    print(f"{name}: {len(jobs)} pieces, {len(todo)} to do", flush=True)
    start, failed = time.time(), []
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(one, p, a) for p, a in todo.items()]
        for n, future in enumerate(as_completed(futures), 1):
            if future.result():
                failed.append(future.result())
            if n % 100 == 0 or n == len(futures):
                print(f"  {n}/{len(futures)}  {time.time() - start:.0f}s  failed {len(failed)}", flush=True)
    for line in failed[:5]:
        print("  FAILED", line)
    return [row for p in jobs if (folder / f"{p}.json").exists() for row in json.loads((folder / f"{p}.json").read_text())]


def cells_and_days(con):
    cell = f"floor(start_lat / {CELL})::INT AS cy, floor(start_lon / {CELL})::INT AS cx"
    where = f"WHERE year(first_day) >= {FIRST_YEAR} AND state <> 'HI'"
    cells = con.execute(f"SELECT DISTINCT {cell} FROM {FIRES} {where} ORDER BY ALL").fetchall()
    days = con.execute(f"SELECT DISTINCT first_day, {cell} FROM {FIRES} {where} ORDER BY ALL").fetchall()
    return cells, days


def centre(cy, cx):
    return (cy + 0.5) * CELL, (cx + 0.5) * CELL


def write(con, rows, name):
    path = CACHE / f"{name}.json"
    path.write_text("\n".join(json.dumps(r) for r in rows))
    out = (OUT / f"inputs_{name}.parquet").as_posix()
    con.execute(f"COPY (SELECT * FROM read_json_auto('{path.as_posix()}')) TO '{out}' (FORMAT parquet, COMPRESSION zstd)")
    path.unlink()
    print(f"inputs_{name}.parquet: {len(rows):,} rows")


def build():
    ee = connect()
    con = duckdb.connect()
    cells, days = cells_and_days(con)
    print(f"{len(cells):,} cells, {len(days):,} cell-days")

    place = {}
    batches = lambda size: {f"{i:06d}": [(f"{cy}_{cx}", *centre(cy, cx)) for cy, cx in cells[i:i + size]]      # noqa: E731
                            for i in range(0, len(cells), size)}
    image = place_image(ee)
    for row in run("place", batches(PLACE_BATCH), lambda points: sample(ee, image, 4000, points)) +             run("built", batches(BUILT_BATCH), lambda points: built_nearby(ee, points)):
        place.setdefault(row["key"], {}).update(row)
    write(con, list(place.values()), "place")

    jobs = {}
    by_day = {}
    for day, cy, cx in days:
        by_day.setdefault(day.isoformat(), []).append((f"{cy}_{cx}", *centre(cy, cx)))
    for day, points in by_day.items():
        for i in range(0, len(points), WEATHER_BATCH):
            jobs[f"{day}_{i // WEATHER_BATCH}"] = (day, points[i:i + WEATHER_BATCH])
    rows = run("weather", jobs, lambda job: [dict(r, day=job[0]) for r in sample(ee, weather_image(ee, job[0]), 4000, job[1])])
    write(con, rows, "weather")


def check():
    """The same code must give the reference training table's values for its own rows."""
    ee = connect()
    table = REFERENCE / "training_table.parquet"
    rows = duckdb.connect().execute(
        f"SELECT lat, lon, date::DATE::VARCHAR, erc, fm1000, pr30, elevation, treecover, lc FROM '{table.as_posix()}' "
        "WHERE year = 2023 AND erc IS NOT NULL USING SAMPLE 200 (reservoir, 1)").fetchall()
    worst = {}
    by_day = {}
    for i, r in enumerate(rows):
        by_day.setdefault(r[2], []).append((i, r[0], r[1]))
    static = place_image(ee)
    for day, points in list(by_day.items()):
        got = {g["key"]: g for g in sample(ee, ee.Image.cat([weather_image(ee, day), static]), 4000, points)}
        for i, _, _ in points:
            for j, band in enumerate(["erc", "fm1000", "pr30", "elevation", "treecover", "lc"], 3):
                if i in got and rows[i][j] is not None:
                    worst[band] = max(worst.get(band, 0), abs(got[i][band] - rows[i][j]))
    print("largest difference from the reference table, 200 rows:", {k: round(v, 3) for k, v in worst.items()})
    assert all(v < 0.01 for v in worst.values()), worst


if __name__ == "__main__":
    check() if "--check" in sys.argv else build()
