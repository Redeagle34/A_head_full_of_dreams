"""Group VIIRS detections into fires.

Run:  python pipeline/danger_fires.py     (after pipeline/calendar_table.py)
Output: data/danger/fires.parquet       one row per fire
        data/danger/fire_days.parquet   one row per fire and day

A fire = detections that touch in space and time: same or neighbouring cell of
about 1.6 km, on the same day or up to 2 days later (one missed day, for
example under cloud, does not split a fire).

Size is estimated from the satellite: number of distinct cells of about 440 m
that ever held a detection, times the cell area. It is a rough footprint, not a
surveyed perimeter.
"""
import math
import pathlib

import duckdb
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

ROOT = pathlib.Path(__file__).resolve().parent.parent
DET = f"'{(ROOT / 'data' / 'calendar' / 'detections.parquet').as_posix()}'"
OUT = ROOT / "data" / "danger"

# ponytail: fixed-degree cells (not equal-area); fine for linking neighbours in the
# contiguous U.S., use a projected grid if Alaska is added.
LINK_LAT, LINK_LON = 0.015, 0.02        # linking cell, about 1.7 x 1.6 km
MAX_GAP_DAYS = 2
FINE_LAT, FINE_LON = 0.004, 0.005       # footprint cell, about 445 x 430 m
ACRES_PER_KM2 = 247.105
FINE_ACRES_AT_EQUATOR = FINE_LAT * 111.32 * FINE_LON * 111.32 * ACRES_PER_KM2


def fine_cell_acres(lat):
    return FINE_ACRES_AT_EQUATOR * math.cos(math.radians(lat))


def label_nodes(con):
    """Table node_fire(gy, gx, day, fire_id): every linking cell and day with a detection."""
    con.execute(f"""
        CREATE TABLE node AS
        SELECT gy, gx, day, row_number() OVER () - 1 AS id FROM (
            SELECT DISTINCT floor(latitude / {LINK_LAT})::INT AS gy, floor(longitude / {LINK_LON})::INT AS gx,
                   acq_date AS day
            FROM {DET} WHERE sensor LIKE 'viirs%')""")
    n = con.execute("SELECT count(*) FROM node").fetchone()[0]
    # One plain equality join per neighbour offset (a single join over all offsets is planned badly).
    offsets = [(dy, dx, dd) for dd in range(MAX_GAP_DAYS + 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
               if dd > 0 or (dy, dx) > (0, 0)]
    edges = con.execute(" UNION ALL ".join(
        f"SELECT a.id AS a, b.id AS b FROM node a JOIN node b "
        f"ON b.gy = a.gy + {dy} AND b.gx = a.gx + {dx} AND b.day = a.day + {dd}"
        for dy, dx, dd in offsets)).fetchnumpy()
    graph = coo_matrix((np.ones(len(edges["a"]), dtype=np.int8), (edges["a"], edges["b"])), shape=(n, n))
    count, label = connected_components(graph, directed=False)
    label_table = {"id": np.arange(n), "fire_id": label}      # noqa: F841  (read by DuckDB below)
    con.execute("CREATE TABLE node_fire AS SELECT gy, gx, day, fire_id FROM node JOIN label_table USING (id)")
    return n, count


def build(con):
    con.execute(f"""
        CREATE TABLE det AS
        SELECT n.fire_id, d.acq_date AS day, d.latitude AS lat, d.longitude AS lon, coalesce(d.frp, 0) AS frp,
               d.daynight = 'N' AS night, d.state,
               floor(d.latitude / {FINE_LAT})::INT AS fy, floor(d.longitude / {FINE_LON})::INT AS fx
        FROM {DET} d JOIN node_fire n
          ON n.gy = floor(d.latitude / {LINK_LAT})::INT AND n.gx = floor(d.longitude / {LINK_LON})::INT
         AND n.day = d.acq_date
        WHERE d.sensor LIKE 'viirs%'""")
    # Per fire and day: detections, power, and the footprint cells first seen that day.
    con.execute(f"""
        CREATE TABLE fire_days AS
        WITH first_seen AS (SELECT fire_id, fy, fx, min(day) AS day FROM det GROUP BY ALL),
        new_cells AS (SELECT fire_id, day, count(*) AS new_cells FROM first_seen GROUP BY ALL),
        daily AS (SELECT fire_id, day, count(*) AS detections, sum(frp) AS frp, max(frp) AS frp_max,
                         avg(night::INT) AS night_share, avg(lat) AS lat, avg(lon) AS lon
                  FROM det GROUP BY ALL)
        SELECT d.*, coalesce(n.new_cells, 0) AS new_cells,
               coalesce(n.new_cells, 0) * {FINE_ACRES_AT_EQUATOR} * cos(radians(d.lat)) AS new_acres
        FROM daily d LEFT JOIN new_cells n USING (fire_id, day)
        ORDER BY fire_id, day""")
    con.execute("""
        CREATE TABLE fires AS
        WITH f AS (
            SELECT fire_id, mode(state) AS state, min(day) AS first_day, max(day) AS last_day,
                   count(DISTINCT day) AS days_seen, count(*) AS detections,
                   sum(frp) AS frp_sum, max(frp) AS frp_max,
                   sum(lat * (frp + 1)) / sum(frp + 1) AS lat, sum(lon * (frp + 1)) / sum(frp + 1) AS lon,
                   min(lon) AS west, min(lat) AS south, max(lon) AS east, max(lat) AS north
            FROM det GROUP BY ALL),
        early AS (      -- what is known at the end of the second day
            SELECT d.fire_id, sum(d.new_acres) AS acres,
                   arg_min(d.lat, d.day) AS start_lat, arg_min(d.lon, d.day) AS start_lon,
                   sum(d.detections) FILTER (d.day = f.first_day) AS d1_detections,
                   sum(d.frp) FILTER (d.day = f.first_day) AS d1_frp,
                   max(d.frp_max) FILTER (d.day = f.first_day) AS d1_frp_max,
                   sum(d.new_acres) FILTER (d.day = f.first_day) AS d1_acres,
                   max(d.night_share) FILTER (d.day = f.first_day) AS d1_night_share,
                   coalesce(sum(d.detections) FILTER (d.day = f.first_day + 1), 0) AS d2_detections,
                   coalesce(sum(d.frp) FILTER (d.day = f.first_day + 1), 0) AS d2_frp,
                   coalesce(sum(d.new_acres) FILTER (d.day = f.first_day + 1), 0) AS d2_new_acres
            FROM fire_days d JOIN f USING (fire_id) GROUP BY ALL)
        SELECT * FROM f JOIN early USING (fire_id) ORDER BY first_day, fire_id""")


def check(con):
    # Every VIIRS detection belongs to exactly one fire.
    src = con.execute(f"SELECT count(*) FROM {DET} WHERE sensor LIKE 'viirs%'").fetchone()[0]
    got, per_day = con.execute(
        "SELECT (SELECT sum(detections) FROM fires), (SELECT sum(detections) FROM fire_days)").fetchone()
    assert src == got == per_day, (src, got, per_day)
    assert abs(fine_cell_acres(40) - 46.9) < 1, fine_cell_acres(40)
    # Known fires come out as one fire each. The footprint counts only cells where a satellite
    # saw flames, so it is below the surveyed size (Park Fire: 429,603 acres official).
    known = [("Park Fire", 39.95, -121.75, "2024-07-28", 200_000), ("Lahaina", 20.88, -156.67, "2023-08-09", 500)]
    for name, lat, lon, day, min_acres in known:
        rows = con.execute("""SELECT fire_id, first_day, last_day, round(acres) FROM fires
                              WHERE ? BETWEEN south AND north AND ? BETWEEN west AND east
                                AND ?::DATE BETWEEN first_day AND last_day ORDER BY acres DESC""",
                           [lat, lon, day]).fetchall()
        print(f"  {name}: {rows[:2]}")
        assert rows and rows[0][3] >= min_acres, (name, rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    nodes, count = label_nodes(con)
    build(con)
    print(f"{nodes:,} cell-days -> {count:,} fires")
    check(con)
    for table in ("fires", "fire_days"):
        path = (OUT / f"{table}.parquet").as_posix()
        con.execute(f"COPY {table} TO '{path}' (FORMAT parquet, COMPRESSION zstd)")
    print("fires by estimated size, acres (<100, 100-1,000, 1,000-10,000, >10,000):", con.execute("""
        SELECT count(*) FILTER (acres < 100), count(*) FILTER (acres >= 100 AND acres < 1000),
               count(*) FILTER (acres >= 1000 AND acres < 10000), count(*) FILTER (acres >= 10000) FROM fires""").fetchone())
    print("share of fires seen on one day only:",
          con.execute("SELECT round(avg((days_seen = 1)::INT), 3) FROM fires").fetchone()[0])


if __name__ == "__main__":
    main()
