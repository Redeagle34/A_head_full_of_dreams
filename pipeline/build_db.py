"""Build data/fire.duckdb, the database the map server reads.

Run:  python pipeline/build_db.py     (after pipeline/calendar_table.py)

Tables
  obs    one row per fire observation, for each of the three map layers:
           layer 'viirs'  every VIIRS detection (375 m)
           layer 'modis'  every MODIS detection (1 km)
           layer 'both'   the harmonized layer in MODIS-equivalent units:
                          Aqua detections as observed, plus VIIRS fires merged
                          into 1.5 km clusters, each with the probability `p`
                          that MODIS would have detected it
  day_w  for each layer, satellite and day: the weight of that satellite.
         A satellite with no detection anywhere that day has no row (not observed).
           'viirs', 'modis'  1 / number of satellites observing (averages intensity)
           'both'            Aqua 0.5 and VIIRS 0.5 (split between its satellites);
                             if one side is missing the other gets everything
  meta   first and last day of each layer
"""
import pathlib
import sys

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harmonize import MEAN_PIXEL_KM2, define_operator      # noqa: E402
from server.grid import BASE_SIZE_M, cell_sql               # noqa: E402

DET = f"'{(ROOT / 'data' / 'calendar' / 'detections.parquet').as_posix()}'"
DB = ROOT / "data" / "fire.duckdb"
MIN_PROBABILITY = 0.001         # VIIRS clusters MODIS would essentially never see are dropped


def build(con):
    define_operator(con)
    row, col = cell_sql(BASE_SIZE_M["both"], "latitude", "longitude")
    con.execute(f"""
        CREATE TABLE obs AS
        WITH native AS (
            SELECT CASE WHEN sensor = 'modis' THEN 'modis' ELSE 'viirs' END AS layer,
                   CASE WHEN sensor = 'modis' THEN lower(satellite) ELSE sensor END AS source,
                   acq_date, latitude AS lat, longitude AS lon, coalesce(frp, 0) AS frp, 1.0 AS p
            FROM {DET}),
        -- VIIRS -> MODIS-equivalent: sum power per 1.5 km cell and overpass, keep the
        -- strongest overpass per day part, then apply the observation operator.
        looks AS (
            SELECT sensor, acq_date, daynight, acq_time, {row} AS r, {col} AS c,
                   sum(frp) AS frp, avg(latitude) AS lat, avg(longitude) AS lon
            FROM {DET} WHERE sensor LIKE 'viirs%' GROUP BY ALL),
        clusters AS (
            SELECT sensor, acq_date, daynight, r, c, max(frp) AS frp,
                   arg_max(lat, frp) AS lat, arg_max(lon, frp) AS lon
            FROM looks GROUP BY ALL),
        equivalent AS (
            SELECT 'both' AS layer, sensor AS source, acq_date, lat, lon, frp,
                   detect_probability(frp, {MEAN_PIXEL_KM2}, daynight) AS p
            FROM clusters)
        SELECT * FROM native
        UNION ALL SELECT 'both', source, acq_date, lat, lon, frp, p FROM native WHERE source = 'aqua'
        UNION ALL SELECT * FROM equivalent WHERE p >= {MIN_PROBABILITY}
        ORDER BY layer, acq_date
    """)
    con.execute("""
        CREATE TABLE day_w AS
        WITH seen AS (SELECT DISTINCT source, acq_date FROM obs WHERE layer IN ('modis', 'viirs')),
        d AS (SELECT acq_date,
                     bool_or(source = 'terra') AS terra, bool_or(source = 'aqua') AS aqua,
                     bool_or(source = 'viirs-snpp') AS snpp, bool_or(source = 'viirs-jpss1') AS jpss1
              FROM seen GROUP BY ALL)
        SELECT 'modis' AS layer, 'terra' AS source, acq_date, 1.0 / (1 + aqua::INT) AS w FROM d WHERE terra
        UNION ALL SELECT 'modis', 'aqua', acq_date, 1.0 / (1 + terra::INT) FROM d WHERE aqua
        UNION ALL SELECT 'viirs', 'viirs-snpp', acq_date, 1.0 / (1 + jpss1::INT) FROM d WHERE snpp
        UNION ALL SELECT 'viirs', 'viirs-jpss1', acq_date, 1.0 / (1 + snpp::INT) FROM d WHERE jpss1
        UNION ALL SELECT 'both', 'aqua', acq_date, CASE WHEN snpp OR jpss1 THEN 0.5 ELSE 1.0 END FROM d WHERE aqua
        UNION ALL SELECT 'both', 'viirs-snpp', acq_date,
                         (CASE WHEN aqua THEN 0.5 ELSE 1.0 END) / (1 + jpss1::INT) FROM d WHERE snpp
        UNION ALL SELECT 'both', 'viirs-jpss1', acq_date,
                         (CASE WHEN aqua THEN 0.5 ELSE 1.0 END) / (1 + snpp::INT) FROM d WHERE jpss1
    """)
    # The harmonized layer starts when Aqua starts.
    con.execute("DELETE FROM obs WHERE layer = 'both' AND acq_date < (SELECT min(acq_date) FROM obs WHERE source = 'aqua')")
    con.execute("CREATE TABLE meta AS SELECT layer, min(acq_date) AS first_day, max(acq_date) AS last_day, "
                "count(*) AS n_rows FROM obs GROUP BY ALL ORDER BY ALL")


def check(con):
    # Weights of a layer add up to 1 on every day it has any.
    bad = con.execute("SELECT count(*) FROM (SELECT layer, acq_date, sum(w) s FROM day_w GROUP BY ALL) "
                      "WHERE abs(s - 1) > 1e-9").fetchone()[0]
    assert bad == 0, bad
    # Every observation has a weight row.
    orphan = con.execute("SELECT count(*) FROM obs o ANTI JOIN day_w w USING (layer, source, acq_date)").fetchone()[0]
    assert orphan == 0, orphan
    # Native layers hold exactly the source detections.
    src = con.execute(f"SELECT count(*) FROM {DET}").fetchone()[0]
    got = con.execute("SELECT count(*) FROM obs WHERE layer IN ('modis', 'viirs')").fetchone()[0]
    assert src == got, (src, got)
    assert con.execute("SELECT min(p) >= 0 AND max(p) <= 1 FROM obs").fetchone()[0]


def main():
    DB.unlink(missing_ok=True)
    con = duckdb.connect(str(DB))
    build(con)
    check(con)
    for r in con.execute("SELECT * FROM meta").fetchall():
        print(*r)
    con.close()
    print(f"{DB.relative_to(ROOT)}: {DB.stat().st_size / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
