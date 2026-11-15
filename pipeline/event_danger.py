"""Give each fire event its danger rating.

Run:  python pipeline/event_danger.py     (after fire_events.py and danger_model.py)
Output: data/events/event_danger.parquet   one row per fire event that has VIIRS detections

The page lists one kind of fire: the events of pipeline/fire_events.py (MODIS and VIIRS,
cells of about 1 km, gaps of up to 5 days). The danger model was trained on another
grouping, pipeline/danger_fires.py (VIIRS only, cells of about 1.6 km, gaps of up to
2 days), and its inputs and scores belong to that grouping. Until the model is trained
again on events, this script carries each rating over to its event.

How: every VIIRS detection lies in exactly one event and in exactly one rated fire, so
the two are matched by the detections they share, not by boxes. An event takes the
rating of the rated fire that holds most of its VIIRS detections (its main part).

Per event
  fire_id      the rated fire it takes the rating from (number in table `fires` of fire.duckdb)
  parts        how many rated fires have detections in the event
  share        share of the event's VIIRS detections that are in the main part
  fire_share   share of the main part's detections that are in this event (below 1 when the
               rated fire reaches into a neighbouring event)
  the rating   level, chances, exposure and first-day facts, copied from table `fires`;
               the dates and footprint of the rated fire are kept as rated_first_day,
               rated_last_day, acres, acres_day2

Limits: events with MODIS detections only (all fires before 2012) have no row. A rated
fire that is never the main part of an event is not shown; the script prints how many.
"""
import pathlib

import duckdb

import danger_fires
from danger_fires import LINK_LAT, LINK_LON
from fire_events import DLAT, DLON

ROOT = pathlib.Path(__file__).resolve().parent.parent
DET = danger_fires.DET
EVENTS = ROOT / "data" / "events"
DB = ROOT / "data" / "fire.duckdb"
RATING = ("first_day AS rated_first_day, last_day AS rated_last_day, days_seen, acres, acres_day2, growth, "
          "d1_night_share, level, p100, p1000, built_5km, vs, rmin, fm1000, pr30, tmmx, lc")


def build(con, rated="rated.fires"):
    """Table `link` from the detections, table `event_cell` and the rated fires in table `rated`."""
    # The grouping of danger_fires.py again. Its numbers change from run to run, so each group is
    # matched to the stored fire by what cannot change: dates, corners and number of detections.
    danger_fires.label_nodes(con)
    con.execute(f"""
        CREATE TABLE piece AS
        WITH d AS (
            SELECT floor(latitude / {LINK_LAT})::INT AS ly, floor(longitude / {LINK_LON})::INT AS lx,
                   floor(latitude / {DLAT})::INT AS gy, floor(longitude / {DLON})::INT AS gx, acq_date AS day,
                   count(*) AS n, min(longitude) AS west, min(latitude) AS south,
                   max(longitude) AS east, max(latitude) AS north
            FROM {DET} WHERE sensor LIKE 'viirs%' GROUP BY ALL)
        SELECT n.fire_id AS label, c.event_id, d.day, d.n, d.west, d.south, d.east, d.north
        FROM d JOIN node_fire n ON n.gy = d.ly AND n.gx = d.lx AND n.day = d.day
               JOIN event_cell c ON c.gy = d.gy AND c.gx = d.gx AND d.day BETWEEN c.first_day AND c.last_day""")
    con.execute(f"""
        CREATE TABLE label_fire AS
        WITH l AS (SELECT label, min(day) AS first_day, max(day) AS last_day, min(west) AS west, min(south) AS south,
                          max(east) AS east, max(north) AS north, sum(n) AS detections FROM piece GROUP BY label)
        SELECT l.label, f.fire_id
        FROM l LEFT JOIN {rated} f ON f.first_day = l.first_day AND f.last_day = l.last_day AND f.west = l.west
             AND f.south = l.south AND f.east = l.east AND f.north = l.north AND f.detections = l.detections""")
    con.execute(f"""
        CREATE TABLE link AS
        WITH pair AS (SELECT p.event_id, l.fire_id, sum(p.n) AS shared
                      FROM piece p JOIN label_fire l USING (label) GROUP BY ALL),
        sized AS (SELECT *, count(*) OVER (PARTITION BY event_id) AS parts,
                         sum(shared) OVER (PARTITION BY event_id) AS in_event,
                         sum(shared) OVER (PARTITION BY fire_id) AS in_fire FROM pair)
        SELECT s.event_id, s.fire_id, s.parts::INT AS parts, s.shared / s.in_event AS share,
               s.shared / s.in_fire AS fire_share, {RATING}
        FROM sized s JOIN {rated} f USING (fire_id)
        QUALIFY row_number() OVER (PARTITION BY s.event_id ORDER BY s.shared DESC, s.fire_id) = 1
        ORDER BY s.event_id""")


def check(con, events, rated="rated.fires"):
    # Nothing lost: every VIIRS detection is in one event and one group.
    src = con.execute(f"SELECT count(*) FROM {DET} WHERE sensor LIKE 'viirs%'").fetchone()[0]
    got = con.execute("SELECT sum(n) FROM piece").fetchone()[0]
    assert src == got, (src, got)
    # Every group is one stored fire and every stored fire is one group. If not, table `fires` was
    # built from other detections: run danger_fires.py and danger_model.py again.
    groups, matched, distinct = con.execute("SELECT count(*), count(fire_id), count(DISTINCT fire_id) FROM label_fire").fetchone()
    stored = con.execute(f"SELECT count(*) FROM {rated}").fetchone()[0]
    assert groups == matched == distinct == stored, (groups, matched, distinct, stored)
    # Every event with VIIRS detections has exactly one row, and no other event has one.
    want, linked, distinct = con.execute(f"""
        SELECT (SELECT count(*) FROM {events} WHERE detections_viirs > 0), count(*), count(DISTINCT event_id) FROM link""").fetchone()
    assert want == linked == distinct, (want, linked, distinct)
    assert con.execute("SELECT min(share) > 0 AND max(share) <= 1 AND min(fire_share) > 0 AND max(fire_share) <= 1 FROM link").fetchone()[0]


def report(con, events, rated="rated.fires"):
    total, viirs = con.execute(f"SELECT count(*), count(*) FILTER (detections_viirs > 0) FROM {events}").fetchone()
    print(f"fire events: {total:,} | with VIIRS detections, so with a row here: {viirs:,} | with a level:",
          f"{con.execute('SELECT count(level) FROM link').fetchone()[0]:,}")
    print("events whose rated fire holds all their VIIRS detections, and those that also hold all of it:",
          con.execute("SELECT round(avg((share = 1)::INT), 3), round(avg((share = 1 AND fire_share = 1)::INT), 3) FROM link").fetchone())
    print("the same for events of 2 km2 or more:", con.execute(f"""
        SELECT round(avg((share = 1)::INT), 3), round(avg((share = 1 AND fire_share = 1)::INT), 3)
        FROM link JOIN {events} USING (event_id) WHERE area_km2 >= 2""").fetchone())
    print("rated fires by level (empty = not rated): all, shown as the main part of an event, not shown")
    for level, n, shown in con.execute(f"""
            SELECT f.level, count(*), count(*) FILTER (f.fire_id IN (SELECT fire_id FROM link))
            FROM {rated} f GROUP BY ALL ORDER BY ALL""").fetchall():
        print(f"  {'' if level is None else int(level)!s:>2} {n:>10,} {shown:>10,} {n - shown:>10,}")


def self_check():
    """Three VIIRS days in one place: days 0-1 and day 5 are two rated fires (gap over 2 days) but one event."""
    con = duckdb.connect()
    con.execute("""CREATE TABLE src AS SELECT 'viirs-snpp' AS sensor, 40.0005 AS latitude, -120.0005 AS longitude,
                          DATE '2024-07-01' + d AS acq_date FROM (VALUES (0), (0), (1), (5)) t(d)""")
    con.execute("CREATE TABLE fires AS SELECT 7 AS fire_id, DATE '2024-07-01' AS first_day, DATE '2024-07-02' AS last_day, "
                "-120.0005 AS west, 40.0005 AS south, -120.0005 AS east, 40.0005 AS north, 3 AS detections, 3 AS level "
                "UNION ALL SELECT 9, DATE '2024-07-06', DATE '2024-07-06', -120.0005, 40.0005, -120.0005, 40.0005, 1, 0")
    for column in RATING.split(", ")[2:]:
        if column != "level":
            con.execute(f"ALTER TABLE fires ADD COLUMN {column} DOUBLE")
    con.execute(f"""CREATE TABLE event_cell AS SELECT 1 AS event_id, floor(40.0005 / {DLAT})::INT AS gy,
                    floor(-120.0005 / {DLON})::INT AS gx, DATE '2024-07-01' AS first_day, DATE '2024-07-06' AS last_day""")
    con.execute("CREATE TABLE events AS SELECT 1 AS event_id, 4 AS detections_viirs, 1.0 AS area_km2")
    global DET
    saved, DET = DET, "src"
    danger_fires.DET = "src"
    try:
        build(con, "fires")
        check(con, "events", "fires")
    finally:
        DET = danger_fires.DET = saved
    row = con.execute("SELECT event_id, fire_id, parts, share, fire_share, level FROM link").fetchall()
    assert row == [(1, 7, 2, 0.75, 1.0, 3)], row


def main():
    self_check()
    for path, script in ((EVENTS / "events.parquet", "fire_events.py"), (DB, "build_db.py and danger_model.py")):
        if not path.exists():
            raise SystemExit(f"{path} is missing. Run: python pipeline/{script}")
    events = f"'{(EVENTS / 'events.parquet').as_posix()}'"
    con = duckdb.connect()
    con.execute(f"ATTACH '{DB.as_posix()}' AS rated (READ_ONLY)")
    con.execute(f"CREATE TABLE event_cell AS SELECT event_id, gy, gx, first_day, last_day "
                f"FROM '{(EVENTS / 'event_cells.parquet').as_posix()}'")
    build(con)
    check(con, events)
    report(con, events)
    con.execute(f"COPY link TO '{(EVENTS / 'event_danger.parquet').as_posix()}' (FORMAT parquet)")


if __name__ == "__main__":
    main()
