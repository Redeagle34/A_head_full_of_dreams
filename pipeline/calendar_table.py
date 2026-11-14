"""Step 3: build the state x week x series calendar table.

Run:  python pipeline/calendar_table.py     (after pipeline/ingest.py)
Output: data/calendar/calendar.parquet with one row per state, week and series.

Series: modis (Terra + Aqua together), terra, aqua, viirs-snpp, viirs-jpss1.
Only vegetation-fire detections (FIRMS type 0) are counted.

Measures per row:
  detections        number of detections
  active_cell_days  number of distinct (grid cell, day) pairs with a detection
  frp_sum           summed fire radiative power, MW
"""
import io
import pathlib
import urllib.request
import zipfile

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
PARQUET = ROOT / "data" / "parquet"
STATES = ROOT / "data" / "raw" / "states"
OUT = ROOT / "data" / "calendar"
STATES_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip"
# ponytail: 0.1 degree lat/lon cells (about 11 km north-south, 8-10 km east-west
# in the contiguous U.S.), not equal-area. Fine for per-state comparison between
# sensors; move to an equal-area grid if cell counts are compared across latitudes.
CELL = 0.1


def connect():
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial")
    return con


def load_states(con):
    if not list(STATES.glob("*.shp")):
        STATES.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(STATES_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            zipfile.ZipFile(io.BytesIO(r.read())).extractall(STATES)
    shp = next(STATES.glob("*.shp")).as_posix()
    con.execute(f"CREATE TABLE states AS SELECT STUSPS AS state, geom FROM ST_Read('{shp}')")


def build(con):
    """Create tables `det` (type-0 detections with state) and `calendar`."""
    load_states(con)
    con.execute(f"""
        CREATE TABLE det AS
        SELECT d.sensor, d.satellite, d.acq_date, d.latitude, d.longitude, d.frp, s.state
        FROM read_parquet('{PARQUET.as_posix()}/*/*/*.parquet',
                          hive_partitioning=true, union_by_name=true) d
        LEFT JOIN states s ON ST_Contains(s.geom, ST_Point(d.longitude, d.latitude))
        WHERE d.type = 0
    """)
    con.execute(f"""
        CREATE TABLE calendar AS
        WITH tagged AS (
            SELECT *, unnest(CASE WHEN sensor = 'modis'
                                  THEN ['modis', lower(satellite)]
                                  ELSE [sensor] END) AS series
            FROM det WHERE state IS NOT NULL
        )
        SELECT state, date_trunc('week', acq_date)::DATE AS week_start, series,
               count(*) AS detections,
               count(DISTINCT (floor(latitude / {CELL})::INT, floor(longitude / {CELL})::INT,
                               acq_date)) AS active_cell_days,
               round(sum(frp), 1) AS frp_sum
        FROM tagged GROUP BY ALL ORDER BY ALL
    """)


def check(con):
    """Fails loudly if the table disagrees with the source detections."""
    # 1. Nothing lost or duplicated: calendar totals equal assigned detections.
    for series, where in [("modis", "sensor='modis'"), ("terra", "satellite='Terra'"),
                          ("aqua", "satellite='Aqua'"), ("viirs-snpp", "sensor='viirs-snpp'"),
                          ("viirs-jpss1", "sensor='viirs-jpss1'")]:
        cal = con.execute("SELECT sum(detections) FROM calendar WHERE series=?", [series]).fetchone()[0]
        src = con.execute(f"SELECT count(*) FROM det WHERE state IS NOT NULL AND {where}").fetchone()[0]
        assert cal == src, (series, cal, src)
    # 2. Three boxes that lie fully inside one state: every detection in the box,
    #    counted straight from the Parquet files, must carry that state.
    boxes = {"KS": (38, 39, -99, -98), "GA": (32, 33, -84, -83), "HI": (19.2, 19.9, -155.8, -155.2)}
    for state, (la0, la1, lo0, lo1) in boxes.items():
        box = f"latitude BETWEEN {la0} AND {la1} AND longitude BETWEEN {lo0} AND {lo1}"
        raw = con.execute(f"""SELECT count(*) FROM read_parquet('{PARQUET.as_posix()}/*/*/*.parquet',
                              union_by_name=true) WHERE type = 0 AND {box}""").fetchone()[0]
        got = con.execute(f"SELECT count(*) FROM det WHERE state = ? AND {box}", [state]).fetchone()[0]
        assert raw == got and raw > 0, (state, raw, got)
        print(f"box in {state}: {raw} detections, all assigned to {state}")
    # 3. A cell-day can never hold fewer than one detection.
    assert con.execute("SELECT count(*) FROM calendar WHERE active_cell_days > detections").fetchone()[0] == 0


def main():
    con = connect()
    build(con)
    check(con)
    OUT.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY calendar TO '{(OUT / 'calendar.parquet').as_posix()}' (FORMAT parquet)")
    total, unassigned = con.execute("SELECT count(*), count(*) FILTER (WHERE state IS NULL) FROM det").fetchone()
    print(f"type-0 detections: {total}; outside every state polygon: {unassigned} "
          f"({100 * unassigned / total:.2f}%)")
    print("calendar rows:", con.execute("SELECT count(*) FROM calendar").fetchone()[0],
          "| states:", con.execute("SELECT count(DISTINCT state) FROM calendar").fetchone()[0])
    print("per series:", con.execute("""SELECT series, min(week_start), max(week_start), sum(detections),
          sum(active_cell_days) FROM calendar GROUP BY ALL ORDER BY ALL""").fetchall())


if __name__ == "__main__":
    main()
