"""The questions the map asks the database.

Every function takes a layer ('viirs', 'modis' or 'both'), a bounding box in
degrees and, where it applies, a date range.

Two numbers are computed per grid cell and day:
  fire day    was there fire in the cell that day? For 'viirs' and 'modis' this is
              1 when any satellite of the family detected fire. For 'both' it is
              the expected MODIS answer, between 0 and 1.
  intensity   fire radiative power in MW, averaged over the satellites observing.
"""
import datetime

from . import db, stats
from .config import CALENDAR_CELL_M, MAX_CELLS, MAX_CSV_ROWS
from .grid import cell_bounds, cell_sql, choose_size

AREA_MIN_ACTIVITY = 3           # cell-days; below this an area week is never flagged
AREA_MIN_SHARE = 0.05           # ... and below this share of the area's busiest week


class BadRequest(ValueError):
    """The request cannot be answered; the message is shown to the user."""


def meta():
    rows = db.cursor().execute("SELECT layer, first_day, last_day FROM meta").fetchall()
    return {layer: {"first_day": a.isoformat(), "last_day": b.isoformat()} for layer, a, b in rows}


def _daily_sql(layer, size_m, date_filter, join="", key=""):
    """SQL giving one row per cell and day: r, c, acq_date, [key,] d (fire day), f (intensity)."""
    row, col = cell_sql(size_m, "o.lat", "o.lon")
    fire_day = "sum(w.w * s.q)" if layer == "both" else "max(s.q)"
    return f"""
        SELECT s.r, s.c, s.acq_date, {key and 's.' + key + ','} {fire_day} AS d, sum(w.w * s.f) AS f
        FROM (SELECT {row} AS r, {col} AS c, o.acq_date, o.source, {key and key + ','}
                     1 - exp(sum(ln(greatest(1 - o.p, 1e-9)))) AS q, sum(o.p * o.frp) AS f
              FROM obs o {join}
              WHERE o.layer = $layer AND {date_filter}
                AND o.lat BETWEEN $south AND $north AND o.lon BETWEEN $west AND $east
              GROUP BY ALL) s
        JOIN day_w w ON w.layer = $layer AND w.source = s.source AND w.acq_date = s.acq_date
        GROUP BY ALL"""


def _shift_years(day, k):
    try:
        return day.replace(year=day.year + k)
    except ValueError:                              # 29 February
        return day.replace(year=day.year + k, day=28)


def _reference_windows(layer, d0, d1):
    """The same calendar window in every other year the layer covers."""
    first, last = db.cursor().execute(
        "SELECT first_day, last_day FROM meta WHERE layer = ?", [layer]).fetchone()
    windows = []
    for k in range(first.year - d0.year, last.year - d1.year + 1):
        a, b = _shift_years(d0, k), _shift_years(d1, k)
        if k != 0 and a >= first and b <= last:
            windows.append((a, b))
    return windows


def cells(layer, bbox, d0, d1, metric):
    """Grid cells with fire in the view. Each cell: [west, south, east, north, days, intensity, normal_days]."""
    west, south, east, north = bbox
    size_m = choose_size(layer, *bbox)
    params = {"layer": layer, "west": west, "south": south, "east": east, "north": north}
    now = f"SELECT r, c, sum(d) AS days, sum(f) AS frp FROM ({_daily_sql(layer, size_m, 'o.acq_date BETWEEN $d0 AND $d1')}) GROUP BY ALL"
    params |= {"d0": d0, "d1": d1}
    n_ref = 0
    if metric == "unusual":
        if (d1 - d0).days > 366:
            raise BadRequest("Unusual versus normal needs a date range of one year or less.")
        windows = _reference_windows(layer, d0, d1)
        n_ref = len(windows)
        if n_ref < 3:
            raise BadRequest("Not enough other years with data to say what is normal for these dates.")
        values = ", ".join(f"(DATE '{a}', DATE '{b}')" for a, b in windows)
        ref_daily = _daily_sql(layer, size_m, "true", join=f"JOIN (VALUES {values}) win(a, b) ON o.acq_date BETWEEN win.a AND win.b")
        sql = f"""
            WITH now AS ({now}),
                 ref AS (SELECT r, c, sum(d) / {n_ref} AS normal FROM ({ref_daily}) GROUP BY ALL)
            SELECT coalesce(now.r, ref.r), coalesce(now.c, ref.c),
                   coalesce(days, 0), coalesce(frp, 0), coalesce(normal, 0)
            FROM now FULL JOIN ref USING (r, c)
            WHERE abs(coalesce(days, 0) - coalesce(normal, 0)) >= 0.05
            ORDER BY abs(coalesce(days, 0) - coalesce(normal, 0)) DESC LIMIT {MAX_CELLS + 1}"""
    else:
        sql = f"SELECT r, c, days, frp, NULL FROM ({now}) ORDER BY frp DESC LIMIT {MAX_CELLS + 1}"
    rows = db.cursor().execute(sql, params).fetchall()
    truncated = len(rows) > MAX_CELLS
    rows = rows[:MAX_CELLS]
    return {
        "size_m": size_m, "metric": metric, "truncated": truncated, "reference_years": n_ref,
        "total_days": round(sum(r[2] for r in rows), 1), "total_frp": round(sum(r[3] for r in rows)),
        "cells": [cell_bounds(size_m, r, c) + [round(days, 2), round(frp, 1),
                                               None if normal is None else round(normal, 2)]
                  for r, c, days, frp, normal in rows],
    }


def calendar(layer, bbox):
    """Weekly fire activity of an area over the whole record, with unusual weeks flagged.

    Value = active cell-days per week on a 1.5 km grid.
    """
    west, south, east, north = bbox
    cur = db.cursor()
    first, last = cur.execute("SELECT first_day, last_day FROM meta WHERE layer = ?", [layer]).fetchone()
    rows = cur.execute(
        f"SELECT date_trunc('week', acq_date)::DATE AS week, sum(d) FROM ({_daily_sql(layer, CALENDAR_CELL_M, 'true')}) "
        "GROUP BY ALL",
        {"layer": layer, "west": west, "south": south, "east": east, "north": north}).fetchall()
    by_week = dict(rows)
    week = first - datetime.timedelta(days=first.weekday())
    weeks = []
    while week <= last:
        weeks.append(week)
        week += datetime.timedelta(days=7)
    values = [round(by_week.get(w, 0.0), 1) for w in weeks]
    min_activity = max(AREA_MIN_ACTIVITY, AREA_MIN_SHARE * max(values, default=0))
    flags, ranks, clim = stats.analyse(weeks, values, min_activity)
    return {"unit": "active 1.5 km cell-days per week", "weeks": [w.isoformat() for w in weeks],
            "value": values, "flag": flags, "rank": ranks, "clim": clim}


def detections_csv(layer, bbox, d0, d1):
    """CSV text of the observations behind the layer, for download."""
    west, south, east, north = bbox
    rows = db.cursor().execute(
        f"""SELECT source, acq_date, round(lat, 5), round(lon, 5), round(frp, 1), round(p, 3)
            FROM obs WHERE layer = $layer AND acq_date BETWEEN $d0 AND $d1
              AND lat BETWEEN $south AND $north AND lon BETWEEN $west AND $east
            ORDER BY acq_date, source LIMIT {MAX_CSV_ROWS}""",
        {"layer": layer, "d0": d0, "d1": d1, "west": west, "south": south, "east": east, "north": north}).fetchall()
    header = "satellite,date,latitude,longitude,frp_mw,modis_detection_probability\n"
    return header + "".join(",".join(str(v) for v in r) + "\n" for r in rows)
