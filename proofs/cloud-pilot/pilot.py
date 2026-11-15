"""Cloud-coverage pilot: does knowing where Aqua could see improve the harmonization?

Run:  python proofs/cloud-pilot/pilot.py [earth-engine-project]
Scope: California and Georgia, 2020, Aqua MODIS against S-NPP VIIRS.

1. Observed fraction per 0.1 degree cell and day, from the daily 1 km fire masks
   in Google Earth Engine (MYD14A1 for Aqua, VNP14A1 for S-NPP):
       observed = pixels classed clear land or fire / land pixels
   Cloud, "unknown" and "not processed" pixels count as not observed.
2. The operator of pipeline/harmonize.py (imported, not copied) run three ways:
       none   clear sky assumed (what the pipeline does today)
       cov    probability x Aqua observed fraction of the cell that day
       ratio  probability x min(1, Aqua fraction / VIIRS fraction): VIIRS saw
              the fire, so the sky was clear for VIIRS; only the extra Aqua
              cloud counts
3. Score per state-week against real Aqua active cell-days, same error measure
   as harmonize.py. No fitting anywhere.

Outputs: data/pilot/coverage.parquet (cached), proofs/cloud-pilot/results.json
"""
import calendar
import datetime
import json
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
import calendar_table  # noqa: E402
import harmonize as hz  # noqa: E402
import ingest  # noqa: E402

YEAR = 2020
PILOT = ROOT / "data" / "pilot"
COVERAGE = PILOT / "coverage.parquet"
CELL = hz.CELL
MASKS = {"aqua": "MODIS/061/MYD14A1", "viirs-snpp": "NASA/VIIRS/002/VNP14A1"}
# state -> (west, south, east, north), on 0.1 degree lines
BOXES = {"CA": (-124.5, 32.5, -114.1, 42.1), "GA": (-85.7, 30.3, -80.8, 35.1)}


# ---------------------------------------------------------------- coverage

def month_coverage(sat, state, month):
    """Observed fraction for one satellite, state box and month: rows of
    (sat, date, gy, gx, fraction) as a DataFrame."""
    w, s, e, n = BOXES[state]
    nx, ny = round((e - w) / CELL), round((n - s) / CELL)
    ic = ee.ImageCollection(MASKS[sat]).select("FireMask")
    # Static land map (MODIS land cover, land/water layer: 2 = land).
    land = ee.Image(f"MODIS/061/MCD12Q1/{YEAR}_01_01").select("LW").eq(2)
    last = calendar.monthrange(YEAR, month)[1]
    start = datetime.date(YEAR, month, 1)
    days = ic.filterDate(start.isoformat(), (start + datetime.timedelta(days=last)).isoformat())

    def fraction(img):
        fm = img.unmask(0)                       # no data = not observed
        seen = fm.eq(5).Or(fm.gte(7))            # clear land or fire
        return (seen.updateMask(land)
                .reduceResolution(ee.Reducer.mean(), maxPixels=1024)
                .reproject(crs="EPSG:4326", crsTransform=[CELL, 0, w, 0, -CELL, n])
                .unmask(-1).toFloat())           # -1 = no land in the cell

    arr = ee.data.computePixels({
        "expression": days.map(fraction).toBands(),
        "fileFormat": "NUMPY_NDARRAY",
        "grid": {"dimensions": {"width": nx, "height": ny},
                 "affineTransform": {"scaleX": CELL, "shearX": 0, "translateX": w,
                                     "shearY": 0, "scaleY": -CELL, "translateY": n},
                 "crsCode": "EPSG:4326"}})
    gy0, gx0 = round(s / CELL), round(w / CELL)
    parts = []
    for band in arr.dtype.names:                 # e.g. 2020_08_01_FireMask
        a = arr[band]
        r, c = np.nonzero(a >= 0)
        parts.append(pd.DataFrame({"sat": sat, "acq_date": datetime.date(*map(int, band.split("_")[:3])),
                                   "gy": gy0 + ny - 1 - r, "gx": gx0 + c, "cov": a[r, c].astype(float)}))
    print(f"coverage {sat} {state} {YEAR}-{month:02d} done", flush=True)
    return pd.concat(parts)


def build_coverage(con):
    if not COVERAGE.exists():
        jobs = [(sat, st, m) for sat in MASKS for st in BOXES for m in range(1, 13)]
        with ThreadPoolExecutor(4) as pool:
            parts = list(pool.map(lambda j: month_coverage(*j), jobs))
        cov_raw = pd.concat(parts)  # noqa: F841  (read by DuckDB below)
        PILOT.mkdir(parents=True, exist_ok=True)
        # The two state boxes do not overlap, so (sat, date, gy, gx) is unique.
        con.execute(f"COPY (SELECT sat, acq_date::DATE AS acq_date, gy::INT AS gy, gx::INT AS gx, cov "
                    f"FROM cov_raw) TO '{COVERAGE.as_posix()}' (FORMAT parquet)")
    con.execute(f"CREATE TABLE cov AS SELECT * FROM '{COVERAGE.as_posix()}'")
    n, dup = con.execute("SELECT count(*), count(*) - count(DISTINCT (sat, acq_date, gy, gx)) FROM cov").fetchone()
    assert n > 0 and dup == 0, (n, dup)
    assert con.execute("SELECT min(cov) >= 0 AND max(cov) <= 1 FROM cov").fetchone()[0]


# -------------------------------------------------------------- detections

def build_detections(con):
    """Tables `det` (type-0 detections in the pilot states) and `seen` (days on
    which each satellite reported anything in the whole country)."""
    calendar_table.load_states(con)
    files = {s: ingest.download(s, YEAR) for s in ("modis", "viirs-snpp")}
    union = " UNION ALL BY NAME ".join(
        f"""SELECT '{s}' AS sensor, * FROM read_csv('{p.as_posix()}', header=true,
            types={{'acq_time': 'VARCHAR', 'confidence': 'VARCHAR', 'satellite': 'VARCHAR',
                    'version': 'VARCHAR'}})""" for s, p in files.items())
    con.execute(f"CREATE TABLE us AS SELECT *, {hz.SAT} AS sat FROM ({union}) WHERE type = 0")
    con.execute("CREATE TABLE seen AS SELECT DISTINCT sat, acq_date FROM us")
    box = " OR ".join(f"(longitude BETWEEN {w} AND {e} AND latitude BETWEEN {s} AND {n})"
                      for w, s, e, n in BOXES.values())
    con.execute(f"""
        CREATE TABLE det AS
        SELECT d.sensor, d.sat, d.acq_date, d.acq_time, d.daynight, d.latitude, d.longitude, d.frp, s.state
        FROM (SELECT * FROM us WHERE {box}) d
        JOIN states s ON ST_Contains(s.geom, ST_Point(d.longitude, d.latitude))
        WHERE s.state IN ({", ".join(f"'{k}'" for k in BOXES)})
    """)


# ---------------------------------------------------------------- operator

def build_weekly(con):
    """Table `weekly`: state, week, pixel-size variant, real Aqua cell-days and the
    operator prediction under each cloud treatment. Days seen by both satellites only."""
    con.execute("CREATE TABLE areas (variant VARCHAR, area DOUBLE)")
    con.executemany("INSERT INTO areas VALUES (?, ?)",
                    [("swath", a) for a in hz.modis_pixel_areas()] + [("mean", hz.MEAN_PIXEL_KM2)])
    # Same clustering as harmonize.build_daily.
    con.execute(f"""
        CREATE TABLE clusters AS
        WITH looks AS (
            SELECT state, acq_date, daynight, acq_time,
                   floor(latitude / {hz.CLUSTER_LAT})::INT AS cy,
                   floor(longitude / {hz.CLUSTER_LON})::INT AS cx, sum(frp) AS frp
            FROM det WHERE sensor = 'viirs-snpp' GROUP BY ALL)
        SELECT state, acq_date, daynight, cy, cx, round(max(frp), 1) AS frp,
               floor((cy + 0.5) * {hz.CLUSTER_LAT} / {CELL})::INT AS gy,
               floor((cx + 0.5) * {hz.CLUSTER_LON} / {CELL})::INT AS gx
        FROM looks GROUP BY ALL
    """)
    con.execute("""
        CREATE TABLE prob AS
        WITH p AS (SELECT d.frp, d.daynight, a.variant,
                          avg(detect_probability(d.frp, a.area, d.daynight)) AS p
                   FROM (SELECT DISTINCT frp, daynight FROM clusters) d, areas a GROUP BY ALL)
        SELECT c.*, p.variant, p.p,
               coalesce(a.cov, 1) AS cov_aqua, coalesce(v.cov, 1) AS cov_viirs
        FROM clusters c JOIN p USING (frp, daynight)
        LEFT JOIN cov a ON a.sat = 'aqua' AND a.acq_date = c.acq_date AND a.gy = c.gy AND a.gx = c.gx
        LEFT JOIN cov v ON v.sat = 'viirs-snpp' AND v.acq_date = c.acq_date AND v.gy = c.gy AND v.gx = c.gx
    """)
    union = lambda xs: "1 - exp(sum(ln(greatest(1 - " + xs + ", 1e-12))))"
    con.execute(f"""
        CREATE TABLE weekly AS
        WITH both_seen AS (SELECT acq_date FROM seen WHERE sat = 'aqua'
                      INTERSECT SELECT acq_date FROM seen WHERE sat = 'viirs-snpp'),
        cell_day AS (
            SELECT state, acq_date, variant, gy, gx,
                   {union("p")} AS q_none,
                   {union("p * cov_aqua")} AS q_cov,
                   {union("p * least(1, cov_aqua / greatest(cov_viirs, 1e-6))")} AS q_ratio
            FROM prob WHERE acq_date IN (SELECT acq_date FROM both_seen) GROUP BY ALL),
        op AS (SELECT state, date_trunc('week', acq_date)::DATE AS week_start, variant,
                      sum(q_none) AS none, sum(q_cov) AS cov, sum(q_ratio) AS ratio
               FROM cell_day GROUP BY ALL),
        aqua AS (SELECT state, date_trunc('week', acq_date)::DATE AS week_start,
                        count(DISTINCT (floor(latitude / {CELL})::INT, floor(longitude / {CELL})::INT,
                                        acq_date)) AS aqua
                 FROM det WHERE sat = 'aqua' AND acq_date IN (SELECT acq_date FROM both_seen) GROUP BY ALL),
        keys AS (SELECT DISTINCT state, week_start, variant FROM op
                 UNION SELECT state, week_start, variant FROM aqua, (SELECT DISTINCT variant FROM areas))
        SELECT k.*, coalesce(a.aqua, 0) AS aqua, coalesce(o.none, 0) AS none,
               coalesce(o.cov, 0) AS cov, coalesce(o.ratio, 0) AS ratio
        FROM keys k LEFT JOIN op o USING (state, week_start, variant)
        LEFT JOIN aqua a USING (state, week_start)
    """)


def report(con):
    out = {"year": YEAR, "states": list(BOXES), "scores": [], "coverage": []}
    print(f"\nState-week active cell-days against real Aqua, {YEAR}, no fitting")
    print(f"{'state':6s}{'pixels':7s}{'treatment':10s}{'error':>7s}{'total/Aqua':>12s}")
    for state, variant in con.execute(
            "SELECT * FROM (SELECT DISTINCT state FROM weekly UNION SELECT 'both'), "
            "(SELECT DISTINCT variant FROM weekly) ORDER BY ALL").fetchall():
        where = "variant = ?" + ("" if state == "both" else f" AND state = '{state}'")
        for t in ("none", "cov", "ratio"):
            err, tot, aqua = con.execute(
                f"SELECT sum(abs({t} - aqua)) / sum(aqua), sum({t}) / sum(aqua), sum(aqua) "
                f"FROM weekly WHERE {where}", [variant]).fetchone()
            print(f"{state:6s}{variant:7s}{t:10s}{err:7.3f}{tot:12.3f}")
            out["scores"].append(dict(state=state, pixels=variant, treatment=t, error=round(err, 3),
                                      total_over_aqua=round(tot, 3), aqua_cell_days=int(aqua)))
    # Coverage itself: plain mean, and weighted to the cells where VIIRS saw fire.
    print("\nMean observed fraction (all land cells | at VIIRS fire clusters)")
    for sat, state, plain in con.execute("""
            SELECT c.sat, s.state, avg(c.cov) FROM cov c
            JOIN (SELECT DISTINCT state, gy, gx FROM clusters) s USING (gy, gx) GROUP BY ALL ORDER BY ALL""").fetchall():
        col = "cov_aqua" if sat == "aqua" else "cov_viirs"
        at_fire = con.execute(f"SELECT avg({col}) FROM prob WHERE state = ? AND variant = 'mean'", [state]).fetchone()[0]
        print(f"{sat:11s}{state:4s}{plain:6.3f} | {at_fire:6.3f}")
        out["coverage"].append(dict(sat=sat, state=state, mean_burnable_cells=round(plain, 3),
                                    mean_at_viirs_fires=round(at_fire, 3)))
    for sat in ("aqua", "viirs-snpp"):
        n = con.execute("SELECT count(*) FROM seen WHERE sat = ?", [sat]).fetchone()[0]
        print(f"{sat}: {n} days with any U.S. detection in {YEAR}")
        out[f"{sat}_days_seen"] = n
    (pathlib.Path(__file__).parent / "results.json").write_text(json.dumps(out, indent=1))


def self_check(con):
    # A fully clouded Aqua cell must remove the fire; a clear one must change nothing.
    q = lambda cov: con.execute("SELECT detect_probability(500.0, 1.0, 'D') * ?", [cov]).fetchone()[0]
    assert q(0.0) == 0 and q(1.0) > 0.99


def main():
    ee.Initialize(project=sys.argv[1] if len(sys.argv) > 1 else None)
    con = calendar_table.connect()
    hz.define_operator(con)
    self_check(con)
    build_coverage(con)
    build_detections(con)
    build_weekly(con)
    report(con)


if __name__ == "__main__":
    main()
