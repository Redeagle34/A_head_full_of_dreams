"""The landscape for the critical-node search (server/critical.py), at four cell sizes.

Run:  python pipeline/critical_landscape.py     (after fire_events.py; needs EE_PROJECT in .env)
Output: data/events/landscape_1.parquet    cells of 0.01 x 0.0125 degrees (about 1 km, the grid of fire_events.py)
        data/events/landscape_2.parquet    0.02 x 0.025 degrees (about 2 km)
        data/events/landscape_4.parquet    0.04 x 0.05 degrees (about 4 km, the gridMET grid)
        data/events/landscape_10.parquet   0.1 x 0.1 degrees (about 10 km)
The server uses the finest size that fits the area on screen.

Columns, per cell (row = floor(lat / cell height), col = floor(lon / cell width)):
  ignitions    fires that started here, 2000-2025 (a cell of the fire's first day)
  size_sum     sum of the size of those fires, in cells of this size (to calibrate p_h)
  burned       fires that touched the cell (to check the simulated burn probability)
  elevation    mean SRTM elevation, m                       (p_slope)
  lc           most common MCD12Q1 2019 land cover class    (p_veg)
  treecover    mean MOD44B 2019 tree cover, percent         (p_den)
  wind_ms      mean gridMET wind speed on high fire-danger days, m/s
  wind_from    direction that wind comes from, degrees clockwise from north (vector mean)
High fire-danger days of a place: days when its gridMET energy release component (erc) is at or
above its own 90th percentile of 2012-2025. gridMET covers the contiguous states only: Hawaii
cells have no wind, and the search uses the wind chosen in the panel there.

Land and wind come from Google Earth Engine in tiles of 8 x 8 degrees, kept in
data/raw/ee/critical/ so a stopped run starts again where it was. Cells kept: land inside the
gridMET area (contiguous states) and land in Hawaii.
"""
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import duckdb
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.danger_inputs import connect     # noqa: E402  (Earth Engine sign-in)

EVENTS = ROOT / "data" / "events"
CACHE = ROOT / "data" / "raw" / "ee" / "critical"
BASE = (0.01, 0.0125)           # degrees; the grid of pipeline/fire_events.py
# file suffix -> (rows, columns) of base cells per cell
LEVELS = {1: (1, 1), 2: (2, 2), 4: (4, 4), 10: (10, 8)}
TILE = 8                        # degrees
TILES = [(s, w) for s in (24, 32, 40, 48) for w in range(-128, -64, TILE)] + [(16, -162)]   # contiguous states, Hawaii
HAWAII = (16, -162)
FIRST_YEAR, LAST_YEAR = 2012, 2025
WORKERS = 8
NO_WIND = -9999


def images(ee):
    """(land image at 1 km, wind image at 4 km)."""
    year = lambda name: ee.ImageCollection(name).filterDate("2019-01-01", "2020-01-01").first()   # noqa: E731
    land = ee.Image.cat([
        year("MODIS/061/MCD12Q1").select("LC_Type1").rename("lc"),
        year("MODIS/061/MOD44B").select("Percent_Tree_Cover").rename("treecover"),
        ee.Image("USGS/SRTMGL1_003").select("elevation"),
    ]).unmask(0)
    days = ee.ImageCollection("IDAHO_EPSCOR/GRIDMET").filterDate(f"{FIRST_YEAR}-01-01", f"{LAST_YEAR + 1}-01-01")
    p90 = days.select("erc").reduce(ee.Reducer.percentile([90]))

    def vector(day):            # wind "from" vector: east and north parts, and speed, on high-danger days only
        th, vs = day.select("th").multiply(np.pi / 180), day.select("vs")
        return ee.Image.cat([vs.multiply(th.sin()).rename("u"), vs.multiply(th.cos()).rename("v"), vs.rename("s")]) \
                 .updateMask(day.select("erc").gte(p90))
    wind = days.map(vector).mean().unmask(NO_WIND)
    return land, wind


def pixels(ee, image, south, west, dlat, dlon):
    """One tile of `image` on the grid of cells dlat x dlon, as a structured numpy array (north row first)."""
    return ee.data.computePixels({
        "expression": image, "fileFormat": "NUMPY_NDARRAY",
        "grid": {"dimensions": {"width": round(TILE / dlon), "height": round(TILE / dlat)},
                 "affineTransform": {"scaleX": dlon, "shearX": 0, "translateX": west,
                                     "shearY": 0, "scaleY": -dlat, "translateY": south + TILE},
                 "crsCode": "EPSG:4326"}})


def tile(ee, land, wind, south, west):
    """Base cells of one tile: dict of 1-D arrays. Cached."""
    path = CACHE / f"{south}_{west}.npz"
    if not path.exists():
        a = pixels(ee, land, south, west, *BASE)
        w = pixels(ee, wind, south, west, BASE[0] * 4, BASE[1] * 4)
        np.savez_compressed(path, lc=a["lc"], treecover=a["treecover"], elevation=a["elevation"],
                            u=w["u"], v=w["v"], s=w["s"])
    t = np.load(path)
    rows, cols = t["lc"].shape
    i, j = np.indices((rows, cols))
    u, v, s = (np.repeat(np.repeat(t[k], 4, axis=0), 4, axis=1) for k in ("u", "v", "s"))   # 4 km -> 1 km
    has_wind = s > NO_WIND / 2
    keep = (t["lc"] > 0) & (has_wind | ((south, west) == HAWAII))
    return {"gy": (round((south + TILE) / BASE[0]) - 1 - i)[keep], "gx": (round(west / BASE[1]) + j)[keep],
            "lc": t["lc"][keep], "treecover": t["treecover"][keep], "elevation": t["elevation"][keep],
            "u": np.where(has_wind, u, np.nan)[keep], "v": np.where(has_wind, v, np.nan)[keep],
            "s": np.where(has_wind, s, np.nan)[keep]}


def base_cells():
    CACHE.mkdir(parents=True, exist_ok=True)
    ee = connect()
    land, wind = images(ee)
    parts = []
    with ThreadPoolExecutor(WORKERS) as pool:
        jobs = {pool.submit(tile, ee, land, wind, s, w): (s, w) for s, w in TILES}
        for n, job in enumerate(as_completed(jobs), 1):
            parts.append(job.result())
            print(f"  tile {jobs[job]} done ({n}/{len(TILES)})", flush=True)
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}


def main():
    import pyarrow as pa
    cells = base_cells()
    con = duckdb.connect()
    con.register("base", pa.table({k: pa.array(v, from_pandas=True) for k, v in cells.items()}))   # NaN -> NULL
    events = f"'{(EVENTS / 'event_cells.parquet').as_posix()}'"
    for name, (fy, fx) in LEVELS.items():
        out = EVENTS / f"landscape_{name}.parquet"
        row, col = f"floor(gy / {fy})::INT", f"floor(gx / {fx})::INT"
        con.execute(f"""
        COPY (
          WITH c AS (SELECT event_id, {row} AS row, {col} AS col, first_day FROM {events}),
          per_event AS (
            SELECT event_id, arg_min(row, first_day) AS row, arg_min(col, first_day) AS col,
                   count(DISTINCT (row, col)) AS size
            FROM c GROUP BY event_id),
          ign AS (SELECT row, col, count(*) AS ignitions, sum(size) AS size_sum FROM per_event GROUP BY ALL),
          touched AS (SELECT row, col, count(DISTINCT event_id) AS burned FROM c GROUP BY ALL),
          land AS (
            SELECT {row} AS row, {col} AS col, avg(elevation) AS elevation, mode(lc) AS lc,
                   avg(treecover) AS treecover, avg(u) AS u, avg(v) AS v, avg(s) AS s
            FROM base GROUP BY ALL)
          SELECT row, col, coalesce(ignitions, 0)::INT AS ignitions, coalesce(size_sum, 0)::INT AS size_sum,
                 coalesce(burned, 0)::INT AS burned, round(elevation)::SMALLINT AS elevation, lc::TINYINT AS lc,
                 round(treecover)::TINYINT AS treecover, round(s, 1)::FLOAT AS wind_ms,
                 ((round(degrees(atan2(u, v)))::INT + 360) % 360)::SMALLINT AS wind_from
          FROM land LEFT JOIN touched USING (row, col) LEFT JOIN ign USING (row, col)
          WHERE lc IN (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14) OR ignitions > 0 OR burned > 0
          ORDER BY row, col
        ) TO '{out.as_posix()}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 50000)""")
        n, wind, ign = con.sql(f"SELECT count(*), count(wind_ms), sum(ignitions) FROM '{out.as_posix()}'").fetchall()[0]
        print(f"{out.name}: {n:,} cells, {wind:,} with wind, {ign:,} ignitions, {out.stat().st_size / 2**20:.1f} MB")


if __name__ == "__main__":
    main()
