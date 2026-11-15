"""The landscape for the critical-node search (server/critical.py): one row per 0.1 degree cell.

Run:  python pipeline/critical_landscape.py     (after fire_events.py and danger_inputs.py)
Output: data/events/landscape.parquet

Columns, per cell of the 0.1 degree grid (row = floor(lat / 0.1), col = floor(lon / 0.1)):
  ignitions    fires that started here, 2000-2025 (the cell of the fire's first day)
  size_sum     sum of the size of those fires, in 0.1 degree cells (to calibrate p_h)
  burned       fires that touched the cell (to check the simulated burn probability)
  elevation    mean SRTM elevation, m            (p_slope: fire climbs uphill faster)
  lc           most common MCD12Q1 land cover    (p_veg)
  treecover    mean MOD44B tree cover, percent   (p_den)
  wind         median gridMET wind speed on the first day of the fires here, m/s

Land cover, tree cover and elevation come from data/danger/inputs_place.parquet, which holds the
0.04 degree cells where VIIRS saw a fire (2012-2025). A cell without any of them has lc NULL; the
search treats it as land the fire cannot cross.
"""
import pathlib

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVENTS = ROOT / "data" / "events"
DANGER = ROOT / "data" / "danger"
OUT = EVENTS / "landscape.parquet"

# event_cells.parquet uses the grid of fire_events.py: 0.01 degree rows, 0.0125 degree columns.
# A 0.1 degree cell holds 10 of its rows and 8 of its columns.
ROW, COL = "floor((gy + 0.5) / 10)::INT", "floor((gx + 0.5) / 8)::INT"
# inputs_place.parquet keys are 'row_col' of 0.04 degree cells.
KEY_ROW = "floor((split_part(key, '_', 1)::INT + 0.5) * 0.04 / 0.1)::INT"
KEY_COL = "floor((split_part(key, '_', 2)::INT + 0.5) * 0.04 / 0.1)::INT"


def main():
    con = duckdb.connect()
    cells, place, weather = (f"'{p.as_posix()}'" for p in (
        EVENTS / "event_cells.parquet", DANGER / "inputs_place.parquet", DANGER / "inputs_weather.parquet"))
    con.execute(f"""
    COPY (
      WITH c AS (SELECT event_id, {ROW} AS row, {COL} AS col, first_day FROM {cells}),
      per_event AS (
        SELECT event_id, arg_min(row, first_day) AS row, arg_min(col, first_day) AS col,
               count(DISTINCT (row, col)) AS size
        FROM c GROUP BY event_id),
      ign AS (SELECT row, col, count(*) AS ignitions, sum(size) AS size_sum FROM per_event GROUP BY ALL),
      touched AS (SELECT row, col, count(DISTINCT event_id) AS burned FROM c GROUP BY ALL),
      wind_key AS (SELECT key, median(vs) AS vs FROM {weather} GROUP BY key),
      pl AS (
        SELECT {KEY_ROW} AS row, {KEY_COL} AS col, avg(p.elevation) AS elevation, mode(p.lc) AS lc,
               avg(p.treecover) AS treecover, median(w.vs) AS wind
        FROM {place} p LEFT JOIN wind_key w USING (key) GROUP BY ALL)
      SELECT row, col, coalesce(ignitions, 0) AS ignitions, coalesce(size_sum, 0) AS size_sum,
             coalesce(burned, 0) AS burned, round(elevation)::INT AS elevation, lc::TINYINT AS lc,
             round(treecover)::TINYINT AS treecover, round(wind, 1)::FLOAT AS wind
      FROM touched FULL JOIN ign USING (row, col) FULL JOIN pl USING (row, col)
      ORDER BY row, col
    ) TO '{OUT.as_posix()}' (FORMAT parquet, COMPRESSION zstd)""")
    n, burnable, ign = con.sql(f"SELECT count(*), count(lc), sum(ignitions) FROM '{OUT.as_posix()}'").fetchall()[0]
    print(f"{OUT}: {n:,} cells, {burnable:,} with land cover, {ign:,} ignitions")


if __name__ == "__main__":
    main()
