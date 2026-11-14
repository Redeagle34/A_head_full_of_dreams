"""Step 5: build the data file the calendar website reads.

Run:  python pipeline/export_web.py     (after pipeline/harmonize.py)
Output: web/data/calendar.json and web/data/states.geojson

Calendar value per state and week, in MODIS (Aqua) active cell-days:
  source 0  Aqua observed all 7 days
  source 1  Aqua incomplete, VIIRS observed all 7 days -> MODIS-equivalent from VIIRS
  source 2  neither complete -> scaled up from the days that were observed
  null      nothing observed that week

"Typical" for a week of the year = the same state in the same week, one week
before and one week after, over all other years.
  unusual  = value above 90% of those reference weeks, and at least MIN_ACTIVITY
  record   = value above every reference week, and at least MIN_ACTIVITY
  critical = weeks of the year whose long-term mean is at least half of the
             state's peak week (its recurring fire season)
"""
import datetime
import json
import pathlib
import statistics

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAL = ROOT / "data" / "calendar"
WEB = ROOT / "web" / "data"
FIRST_WEEK = "2002-07-01"       # Aqua starts 2002-07-04
MIN_ACTIVITY = 5                # cell-days; below this a week is never flagged
UNUSUAL_RANK = 0.90


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


def quantile(sorted_values, q):
    if not sorted_values:
        return 0.0
    i = q * (len(sorted_values) - 1)
    lo = int(i)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (i - lo)


def analyse(weeks, values):
    """Flags per week and climatology per week of the year for one state."""
    iso = [w.isocalendar() for w in weeks]          # (year, week, weekday)
    by_woy = {}
    for (yr, wk, _), v in zip(iso, values):
        if v is not None:
            by_woy.setdefault(wk, []).append((yr, v))

    def reference(wk, skip_year=None):
        out = []
        for d in (-1, 0, 1):
            w = (wk - 1 + d) % 52 + 1 if wk <= 52 else (52 if d < 0 else 53 if d == 0 else 1)
            out += [v for y, v in by_woy.get(w, []) if y != skip_year]
        return out

    flags, ranks = [], []
    for (yr, wk, _), v in zip(iso, values):
        ref = reference(wk, skip_year=yr)
        if v is None or not ref:
            flags.append(0), ranks.append(None)
            continue
        rank = sum(r < v for r in ref) / len(ref)
        ranks.append(round(rank, 2))
        flag = 0
        if v >= MIN_ACTIVITY:
            flag = 2 if v > max(ref) else 1 if rank >= UNUSUAL_RANK else 0
        flags.append(flag)
    clim = {"p10": [], "p50": [], "p90": [], "mean": []}
    for wk in range(1, 54):
        ref = sorted(reference(wk))
        clim["p10"].append(round(quantile(ref, 0.10), 1))
        clim["p50"].append(round(quantile(ref, 0.50), 1))
        clim["p90"].append(round(quantile(ref, 0.90), 1))
        clim["mean"].append(round(statistics.fmean(ref), 1) if ref else 0.0)
    peak = max(clim["mean"])
    clim["critical"] = [int(peak >= 1 and m >= 0.5 * peak) for m in clim["mean"]]
    return flags, ranks, clim


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
        flags, ranks, clim = analyse(weeks, values)
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
