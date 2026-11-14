"""Step 5: build the data file the calendar website reads.

Run:  python pipeline/export_web.py     (after pipeline/harmonize.py)
Output: web/data/calendar.json and web/data/states.geojson

Calendar value per state and week, in MODIS (Aqua) active cell-days:
  source 0  Aqua observed all 7 days
  source 1  Aqua incomplete, VIIRS observed all 7 days -> MODIS-equivalent from VIIRS
  source 2  neither complete -> scaled up from the days that were observed
  null      nothing observed that week

Unusual, record and critical weeks are defined in server/stats.py.
"""
import datetime
import json
import pathlib
import sys

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.stats import analyse      # noqa: E402

CAL = ROOT / "data" / "calendar"
WEB = ROOT / "web" / "data"
FIRST_WEEK = "2002-07-01"       # Aqua starts 2002-07-04
MIN_ACTIVITY = 5                # cell-days; below this a week is never flagged


def load(con):
    """Rows: state, week_start, value, source, aqua, modis_equivalent, sd."""
    cal, har, det = (f"'{(CAL / n).as_posix()}'" for n in
                     ("calendar.parquet", "harmonized.parquet", "detections.parquet"))
    return con.execute(f"""
        WITH weeks AS (SELECT unnest(generate_series(DATE '{FIRST_WEEK}',
                              (SELECT max(week_start) FROM {cal}), INTERVAL 7 DAY))::DATE AS week_start),
        aqua_days AS (SELECT date_trunc('week', acq_date)::DATE AS week_start,
                             count(DISTINCT acq_date) AS n
                      FROM {det} WHERE satellite = 'Aqua' GROUP BY ALL),
        k AS (SELECT state, week_start FROM (SELECT DISTINCT state FROM {cal}), weeks)
        SELECT k.state, k.week_start,
               CASE WHEN coalesce(d.n, 0) = 7 THEN coalesce(a.active_cell_days, 0)
                    WHEN h.viirs_days_observed = 7 THEN h.modis_equivalent_cell_days
                    WHEN coalesce(d.n, 0) > 0 THEN coalesce(a.active_cell_days, 0) * 7.0 / d.n
                    WHEN h.viirs_days_observed > 0 THEN h.modis_equivalent_cell_days * 7.0 / h.viirs_days_observed
               END AS value,
               CASE WHEN coalesce(d.n, 0) = 7 THEN 0 WHEN h.viirs_days_observed = 7 THEN 1
                    WHEN coalesce(d.n, 0) > 0 OR h.viirs_days_observed > 0 THEN 2 END AS source,
               CASE WHEN coalesce(d.n, 0) > 0 THEN coalesce(a.active_cell_days, 0) END AS aqua,
               h.modis_equivalent_cell_days, h.modis_equivalent_cell_days_sd
        FROM k
        LEFT JOIN aqua_days d USING (week_start)
        LEFT JOIN {cal} a ON a.state = k.state AND a.week_start = k.week_start AND a.series = 'aqua'
        LEFT JOIN {har} h ON h.state = k.state AND h.week_start = k.week_start
        ORDER BY k.state, k.week_start
    """).fetchall()


def export_states(con):
    shp = next((ROOT / "data" / "raw" / "states").glob("*.shp")).as_posix()
    con.execute("INSTALL spatial; LOAD spatial")
    feats = con.execute(f"""
        SELECT STUSPS, NAME, ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.02))
        FROM ST_Read('{shp}') WHERE STUSPS IN (SELECT DISTINCT state FROM '{(CAL / "calendar.parquet").as_posix()}')
    """).fetchall()
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": i, "properties": {"state": s, "name": n}, "geometry": json.loads(g)}
        for i, (s, n, g) in enumerate(feats)]}
    (WEB / "states.geojson").write_text(json.dumps(gj, separators=(",", ":")))
    return {s: n for s, n, _ in feats}


def build():
    con = duckdb.connect()
    WEB.mkdir(parents=True, exist_ok=True)
    names = export_states(con)
    rows = load(con)
    weeks = sorted({r[1] for r in rows})
    out = {"generated": datetime.date.today().isoformat(), "unit": "MODIS (Aqua) active cell-days per week",
           "min_activity": MIN_ACTIVITY, "weeks": [w.isoformat() for w in weeks], "states": {}}
    r1 = lambda x: None if x is None else round(float(x), 1)
    for state in sorted(names):
        sr = [r for r in rows if r[0] == state]
        assert [r[1] for r in sr] == weeks
        values = [r1(r[2]) for r in sr]
        flags, ranks, clim = analyse(weeks, values, MIN_ACTIVITY)
        out["states"][state] = {"name": names[state], "value": values, "source": [r[3] for r in sr],
                                "aqua": [r[4] for r in sr], "viirs_as_modis": [r1(r[5]) for r in sr],
                                "sd": [r1(r[6]) for r in sr], "rank": ranks, "flag": flags, "clim": clim}
    return out


def main():
    out = build()
    path = WEB / "calendar.json"
    path.write_text(json.dumps(out, separators=(",", ":")))
    print(f"{path.relative_to(ROOT)}: {path.stat().st_size / 1e6:.1f} MB, "
          f"{len(out['states'])} states, {len(out['weeks'])} weeks "
          f"({out['weeks'][0]} to {out['weeks'][-1]})")
    # Step 5 check: Park Fire (ignited 24 July 2024, Northern California).
    ca = out["states"]["CA"]
    print("California, Park Fire weeks: week, value, typical p50-p90, rank, flag (1 unusual, 2 record)")
    for w in ("2024-07-22", "2024-07-29", "2024-08-05"):
        i = out["weeks"].index(w)
        wk = datetime.date.fromisoformat(w).isocalendar()[1]
        print(" ", w, ca["value"][i], f'{ca["clim"]["p50"][wk - 1]}-{ca["clim"]["p90"][wk - 1]}',
              ca["rank"][i], ca["flag"][i])
    n = sum(f > 0 for s in out["states"].values() for f in s["flag"])
    total = sum(v is not None for s in out["states"].values() for v in s["value"])
    print(f"flagged weeks: {n} of {total} ({100 * n / total:.1f}%)")


if __name__ == "__main__":
    main()
