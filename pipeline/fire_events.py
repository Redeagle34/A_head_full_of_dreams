"""Group satellite detections into fire events: one row per fire.

Run:  python pipeline/fire_events.py     (after pipeline/calendar_table.py)
Output: data/events/events.parquet       one row per fire
        data/events/event_cells.parquet  the ground cells of each fire, with first and last day

Method (the idea of FIRED, Balch et al. 2020, applied to active-fire detections):
detections are placed on a grid of about 1 km. Two burning cells belong to the
same fire when they touch (same cell or one of its 8 neighbours) and are at most
GAP_DAYS days apart. A fire is everything connected that way.

Per fire
  start, end        first and last day with a detection
  duration_days     end - start + 1
  active_days       days with at least one detection
  area_km2          ground area of all cells that ever burned (an estimate from
                    hotspots: it misses what burned under cloud or between passes,
                    and it rounds up to whole cells)
  frp_max, frp_sum  fire radiative power, MW
  detections_modis, detections_viirs

Limits: before 2012 only MODIS exists, so early fires look smaller and shorter.
Fires closer than one cell merge into one. Compare with burned-area maps and
reported perimeters (pipeline/event_enrich.py) before trusting a single number.
"""
import math
import pathlib

import duckdb
import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

ROOT = pathlib.Path(__file__).resolve().parent.parent
DET = f"'{(ROOT / 'data' / 'calendar' / 'detections.parquet').as_posix()}'"
OUT = ROOT / "data" / "events"
DLAT, DLON = 0.01, 0.0125       # cell: 1.11 km north-south, 0.9 to 1.3 km east-west in the U.S.
GAP_DAYS = 5
KM_PER_DEG = 111.32


def cell_area_km2(gy):
    """Ground area of a cell in row gy."""
    return DLAT * KM_PER_DEG * DLON * KM_PER_DEG * np.cos(np.radians((gy + 0.5) * DLAT))


def label_events(gy, gx, day):
    """Event number for every (cell, day). Arrays of equal length, one entry per distinct cell-day."""
    n = len(day)
    gy = gy - gy.min() + 1; gx = gx - gx.min() + 1; day = day - day.min()      # all >= 0, room for -1 offsets
    width, span = int(gx.max()) + 2, int(day.max()) + GAP_DAYS + 2
    key = (gy.astype(np.int64) * width + gx) * span + day                      # sorted by cell, then day
    order = np.argsort(key); key_sorted = key[order]
    rows, cols = [], []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            # First later appearance of the neighbouring cell (same day counts for neighbours).
            first_day = day + (1 if dy == 0 and dx == 0 else 0)
            cell = ((gy + dy).astype(np.int64) * width + (gx + dx)) * span
            at = np.searchsorted(key_sorted, cell + first_day)
            at_safe = np.minimum(at, n - 1)
            found = key_sorted[at_safe]
            ok = (at < n) & (found // span == cell // span) & (found % span <= day + GAP_DAYS)
            rows.append(np.nonzero(ok)[0]); cols.append(order[at_safe[ok]])
    rows, cols = np.concatenate(rows), np.concatenate(cols)
    graph = coo_matrix((np.ones(len(rows), np.int8), (rows, cols)), shape=(n, n))
    return connected_components(graph, directed=False)[1]


def build(con):
    con.execute(f"""
        CREATE TABLE node AS
        SELECT floor(latitude / {DLAT})::INT AS gy, floor(longitude / {DLON})::INT AS gx, acq_date,
               count(*) FILTER (WHERE sensor = 'modis') AS n_modis,
               count(*) FILTER (WHERE sensor <> 'modis') AS n_viirs,
               sum(coalesce(frp, 0)) AS frp_sum, max(coalesce(frp, 0)) AS frp_max,
               mode(state) AS state
        FROM {DET} GROUP BY ALL
    """)
    node = con.execute("SELECT gy, gx, (acq_date - DATE '2000-01-01')::INT AS day FROM node ORDER BY ALL").df()
    labels = label_events(node.gy.to_numpy(), node.gx.to_numpy(), node.day.to_numpy())
    node["event_id"] = labels
    node["cell_km2"] = cell_area_km2(node.gy.to_numpy())
    con.register("node_df", node)
    con.execute("""
        CREATE TABLE cell AS
        SELECT l.event_id, n.gy, n.gx, min(n.acq_date) AS first_day, max(n.acq_date) AS last_day,
               count(*) AS days, sum(n.n_modis) AS n_modis, sum(n.n_viirs) AS n_viirs,
               sum(n.frp_sum) AS frp_sum, max(n.frp_max) AS frp_max, any_value(l.cell_km2) AS cell_km2,
               mode(n.state) AS state
        FROM node n JOIN node_df l
          ON l.gy = n.gy AND l.gx = n.gx AND l.day = (n.acq_date - DATE '2000-01-01')::INT
        GROUP BY ALL
    """)
    con.execute(f"""
        CREATE TABLE event AS
        WITH days AS (SELECT l.event_id, count(DISTINCT l.day) AS active_days FROM node_df l GROUP BY ALL)
        SELECT c.event_id, mode(c.state) AS state,
               min(c.first_day) AS start, max(c.last_day) AS "end",
               (max(c.last_day) - min(c.first_day) + 1)::INT AS duration_days,
               any_value(d.active_days)::INT AS active_days,
               count(*)::INT AS cells, round(sum(c.cell_km2), 2) AS area_km2,
               sum(c.n_modis)::INT AS detections_modis, sum(c.n_viirs)::INT AS detections_viirs,
               round(sum(c.frp_sum), 1) AS frp_sum, round(max(c.frp_max), 1) AS frp_max,
               round(avg((c.gy + 0.5) * {DLAT}), 4) AS lat, round(avg((c.gx + 0.5) * {DLON}), 4) AS lon,
               round(min(c.gx) * {DLON}, 4) AS west, round(min(c.gy) * {DLAT}, 4) AS south,
               round((max(c.gx) + 1) * {DLON}, 4) AS east, round((max(c.gy) + 1) * {DLAT}, 4) AS north
        FROM cell c JOIN days d USING (event_id) GROUP BY c.event_id
    """)


def check(con):
    # Every detection belongs to exactly one fire, and nothing is lost.
    src = con.execute(f"SELECT count(*) FROM {DET}").fetchone()[0]
    got = con.execute("SELECT sum(detections_modis + detections_viirs) FROM event").fetchone()[0]
    assert src == got, (src, got)
    assert con.execute("SELECT count(*) FROM (SELECT gy, gx, first_day FROM cell GROUP BY ALL HAVING count(*) > 1)").fetchone()[0] == 0
    assert con.execute("SELECT min(duration_days) >= 1 AND min(active_days) >= 1 AND min(area_km2) > 0 FROM event").fetchone()[0]
    assert con.execute("SELECT count(*) FROM event WHERE active_days > duration_days").fetchone()[0] == 0


def self_check():
    # Two touching cells one day apart are one fire; a cell far away, or too late, is another.
    gy = np.array([10, 10, 11, 50, 10]); gx = np.array([10, 11, 12, 50, 10]); day = np.array([0, 1, 3, 0, 20])
    lab = label_events(gy, gx, day)
    assert lab[0] == lab[1] == lab[2] and lab[3] != lab[0] and lab[4] != lab[0], lab
    assert abs(cell_area_km2(np.array([3700])) - 1.11 * 1.39 * math.cos(math.radians(37)) ) < 0.03


def main():
    self_check()
    con = duckdb.connect()
    build(con)
    check(con)
    OUT.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY (SELECT * FROM event ORDER BY area_km2 DESC) TO '{(OUT / 'events.parquet').as_posix()}' (FORMAT parquet)")
    con.execute(f"COPY (SELECT event_id, gy, gx, first_day, last_day, days FROM cell ORDER BY event_id) "
                f"TO '{(OUT / 'event_cells.parquet').as_posix()}' (FORMAT parquet)")
    print("fires:", con.execute("SELECT count(*) FROM event").fetchone()[0])
    print("by size (km2): fires, share of all burned cells")
    for r in con.execute("""SELECT CASE WHEN area_km2 < 2 THEN 'a <2' WHEN area_km2 < 10 THEN 'b 2-10'
                                        WHEN area_km2 < 100 THEN 'c 10-100' ELSE 'd >=100' END AS size,
                                   count(*), round(sum(area_km2) / (SELECT sum(area_km2) FROM event), 3)
                            FROM event GROUP BY ALL ORDER BY ALL""").fetchall():
        print(" ", *r)
    print("largest:", con.execute('SELECT state, start, "end", duration_days, area_km2 FROM event ORDER BY area_km2 DESC LIMIT 5').fetchall())


if __name__ == "__main__":
    main()
