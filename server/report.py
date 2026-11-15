"""The scientific report: fire activity of chosen places and dates, in chosen sections.

Places: any mix of U.S. states and boxes (west, south, east, north). Everything is counted
once, also where a box overlaps a chosen state or another box.

  weekly series   observations of the harmonized layer (MODIS-equivalent, since July 2002)
                  whose state is chosen or whose point is in a box
  fires           fire events whose state is chosen or whose centre is in a box
  reports         agency-reported wildfires whose state is chosen or whose point is in a box

Change here:
  SECTIONS        the sections a reader can tick, in the order they are printed
  SIZE_CLASSES    fire size classes, km2
  REPORT_SIZES    reported-fire size classes, acres
  METHODS, SOURCES  the fixed text
Each section is one function named like its key; build() calls the ticked ones.
"""
import datetime
import json
import re

from . import db, events, fires, queries, stats

LAYER = "both"
TOP_FIRES = 15
MAX_STATES, MAX_BOXES = 60, 20

SECTIONS = {
    "summary": "Summary",
    "yearly": "Fire activity by year",
    "seasonality": "Seasonal pattern",
    "unusual": "Unusual and record weeks in the period",
    "fires": "Fires in the period",
    "danger": "Danger levels of the fires",
    "vegetation": "Vegetation burned",
    "missed": "Reported fires the satellites missed",
    "sensors": "MODIS and VIIRS side by side",
    "methods": "Methods and limits",
    "sources": "Data sources",
}
SIZE_CLASSES = [(0, 2, "under 2 km²"), (2, 10, "2 to 10 km²"), (10, 100, "10 to 100 km²"), (100, 1e9, "100 km² and more")]
REPORT_SIZES = [(0, 1, "under 1 acre"), (1, 100, "1 to 100"), (100, 1000, "100 to 1,000"),
                (1000, 10000, "1,000 to 10,000"), (10000, 1e12, "over 10,000")]

METHODS = [
    ("One unit across sensors",
     "VIIRS reports about four times more detections than MODIS for the same fires. The weekly series here is in "
     "MODIS (Aqua) equivalent units: VIIRS fires are merged into clusters of about one MODIS pixel, and each cluster "
     "counts by the probability that MODIS would have detected it (fire-radiative-power observation operator of "
     "Sofiev, IS4FIRES v3.0, published coefficients). Withheld years 2021-2025, state-week level: error 0.27 of the "
     "Aqua total, against 3.06 for raw VIIRS."),
    ("Weekly value", "Active cell-days: cells of 1.5 km with fire on a day, summed over the week and the chosen places. "
     "For the harmonized layer a cell-day counts by its probability of being seen by MODIS."),
    ("Unusual and record weeks",
     "Each week is compared with the same week, one before and one after, in all other years. Unusual: above 90% of "
     "them. Record: above all of them. Weeks under 5% of the busiest week of the places (and under 3 cell-days) are "
     "never flagged. Usual fire season: weeks whose long-term mean is at least half of the peak week."),
    ("One fire", "MODIS and VIIRS detections that touch on squares of about 1 km and follow within 5 days are one fire. "
     "Area is the area of those squares: it misses what burned under cloud or between passes and rounds up to whole "
     "squares. A fire belongs to the state where most of it burned and to a box when its centre is inside."),
    ("Danger level", "Chance that a fire's VIIRS footprint reaches 1,000 acres, judged after two days of passes, in five "
     "levels. Gradient-boosted trees on what VIIRS saw on day 1 and 2, weather and fuel dryness (gridMET), terrain, "
     "vegetation, fire regime and population. Trained on 2012-2020, tuned on 2021. On 2022-2025: AUC 0.936 for fires "
     "still under 1,000 acres on day 2; 0.904 against agency-reported final size."),
    ("Limits", "No detection under cloud looks like no fire. Days on which a satellite reports nothing anywhere are "
     "treated as not observed. Before July 2002 only Terra flew, so the harmonized series starts then. Before 2012 "
     "there is no VIIRS: fires are smaller and shorter in the record and have no danger level. Lava in Hawaii is "
     "recorded as fire. Fire size is a satellite estimate, not a surveyed perimeter. Data ends where the FIRMS yearly "
     "archive ends."),
]
SOURCES = [
    ("NASA FIRMS, MODIS Collection 6.1 (Terra, Aqua) and VIIRS 375 m (Suomi NPP, NOAA-20) active fire archive",
     "https://firms.modaps.eosdis.nasa.gov/country/"),
    ("Sofiev, M.: fire radiative power observation operator, IS4FIRES v3.0", "https://github.com/fmidev/FRP_OOp"),
    ("NIFC WFIGS Incident Locations (reported wildfires)", "https://data-nifc.opendata.arcgis.com/"),
    ("gridMET daily surface meteorology (Abatzoglou 2013), LANDFIRE, SRTM, MODIS MCD12Q1, MCD64A1 and MOD44B, "
     "GPW v4.11, GHSL, through Google Earth Engine", "https://developers.google.com/earth-engine/datasets"),
    ("U.S. Census Bureau cartographic boundary files 2023 (states)",
     "https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html"),
]


class BadRequest(ValueError):
    """The request cannot be answered; the message is shown to the reader."""


class Place:
    """The chosen places as SQL conditions. Values are checked here, so they can be written into the SQL."""

    def __init__(self, states, boxes):
        states = sorted({s.upper() for s in states})
        if not states and not boxes:
            raise BadRequest("Choose at least one state or area.")
        if len(states) > MAX_STATES or len(boxes) > MAX_BOXES:
            raise BadRequest(f"At most {MAX_STATES} states and {MAX_BOXES} areas.")
        if any(not re.fullmatch(r"[A-Z]{2}", s) for s in states):
            raise BadRequest("States are two-letter codes, for example CA.")
        self.states, self.boxes = states, []
        for box in boxes:
            west, south, east, north = (float(v) for v in box["bbox"])
            if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
                raise BadRequest("An area must be west, south, east, north in degrees.")
            self.boxes.append({"name": str(box.get("name") or "Area")[:80], "bbox": [west, south, east, north]})

    def where(self, lat, lon, state):
        """Condition for rows with columns lat, lon and a two-letter state expression."""
        parts = [f"{state} IN ({', '.join(repr(s) for s in self.states)})"] if self.states else []
        parts += [f"({lat} BETWEEN {s!r} AND {n!r} AND {lon} BETWEEN {w!r} AND {e!r})"
                  for w, s, e, n in (b["bbox"] for b in self.boxes)]
        return "(" + " OR ".join(parts) + ")"

    def describe(self):
        return {"states": self.states, "boxes": self.boxes}


def _events_sql(place, d0, d1, columns="e.*", extra=""):
    """Fire events of the places that burned between d0 and d1."""
    tables, _, _ = events._source()
    return (f"SELECT {columns} FROM {tables} WHERE {place.where('e.lat', 'e.lon', 'e.state')} "
            f"AND e.\"end\" >= DATE '{d0}' AND e.start <= DATE '{d1}' {extra}")


def _shift(day, years):
    try:
        return day.replace(year=day.year + years)
    except ValueError:                              # 29 February
        return day.replace(year=day.year + years, day=28)


def _series(place):
    """Weekly series of the places over the whole record (computed once per report)."""
    data = queries.weekly(LAYER, place.where("o.lat", "o.lon", "o.state"), {})
    data["dates"] = [datetime.date.fromisoformat(w) for w in data["weeks"]]
    return data


def _window_total(series, d0, d1):
    return sum(v for w, v in zip(series["dates"], series["value"]) if d0 <= w + datetime.timedelta(days=6) and w <= d1)


# ---------- sections ----------

def summary(place, d0, d1, series):
    total = _window_total(series, d0, d1)
    out = {"cell_days": round(total, 1), "unit": series["unit"], "normal": None}
    if (d1 - d0).days <= 366:
        first, last = series["dates"][0], series["dates"][-1] + datetime.timedelta(days=6)
        others = []
        for k in range(first.year - d0.year, last.year - d1.year + 1):
            a, b = _shift(d0, k), _shift(d1, k)
            if k != 0 and a >= first and b <= last:
                others.append((a.year, _window_total(series, a, b)))
        if len(others) >= 3:
            values = sorted(v for _, v in others)
            out["normal"] = {"years": len(others), "median": round(stats.quantile(values, 0.5), 1),
                             "p90": round(stats.quantile(values, 0.9), 1),
                             "years_below": sum(v < total for v in values)}
    row = events._rows(_events_sql(place, d0, d1, "count(*) AS n, coalesce(sum(e.area_km2), 0) AS km2, max(e.area_km2) AS largest"))[0]
    out |= {"fires": row["n"], "area_km2": round(float(row["km2"]), 1),
            "largest_km2": None if row["largest"] is None else round(float(row["largest"]), 1)}
    return out


def yearly(place, d0, d1, series):
    totals, weeks = {}, {}
    for w, v in zip(series["dates"], series["value"]):
        year = (w + datetime.timedelta(days=3)).year            # the year that holds most of the week
        totals[year] = totals.get(year, 0) + v
        weeks[year] = weeks.get(year, 0) + 1
    full = sorted(v for y, v in totals.items() if weeks[y] >= 52)
    last_year = series["dates"][-1].year
    totals = {y: v for y, v in totals.items() if y <= last_year}      # the last week can reach into the next year
    return {"unit": series["unit"].replace("per week", "per year"),
            "median_full_years": round(stats.quantile(full, 0.5), 1) if full else None,
            "years": [{"year": y, "cell_days": round(totals[y], 1), "complete": weeks[y] >= 52} for y in sorted(totals)]}


def seasonality(place, d0, d1, series):
    clim = series["clim"]
    return {"unit": series["unit"],
            "weeks": [{"week": k + 1, "mean": clim["mean"][k], "p50": clim["p50"][k], "p90": clim["p90"][k],
                       "season": bool(clim["critical"][k])} for k in range(len(clim["p50"]))]}


def unusual(place, d0, d1, series):
    clim, rows = series["clim"], []
    for w, v, flag in zip(series["dates"], series["value"], series["flag"]):
        if d0 <= w + datetime.timedelta(days=6) and w <= d1:
            k = min(w.isocalendar()[1], len(clim["p50"])) - 1
            rows.append({"week": w.isoformat(), "cell_days": v, "typical": clim["p50"][k], "p90": clim["p90"][k], "flag": flag})
    return {"unit": series["unit"], "weeks_in_period": len(rows), "series": rows,
            "flagged": [r for r in rows if r["flag"]]}


def fires_in_period(place, d0, d1, series):
    case = " ".join(f"WHEN e.area_km2 < {hi} THEN {i}" for i, (_, hi, _) in enumerate(SIZE_CLASSES))
    by_size = {r["k"]: r for r in events._rows(_events_sql(
        place, d0, d1, f"CASE {case} END AS k, count(*) AS n, sum(e.area_km2) AS km2, sum(e.duration_days) AS days",
        "GROUP BY ALL"))}
    _, columns, note = events._source()
    top = events._rows(_events_sql(place, d0, d1, columns, f"ORDER BY e.area_km2 DESC, e.event_id LIMIT {TOP_FIRES}"))
    largest = []
    for row in top:
        row = events._shape(row)
        largest.append({"start": row["start"], "end": row["end"], "state": row["state"], "days": row["duration_days"],
                        "area_km2": row["area_km2"], "burned_km2": row["burned_km2"], "lat": row["lat"], "lon": row["lon"],
                        "level": row["danger"]["level_name"] if row["danger"] else None})
    return {"note": note,
            "by_size": [{"size": name, "fires": by_size.get(i, {}).get("n", 0),
                         "area_km2": round(float(by_size.get(i, {}).get("km2") or 0), 1),
                         "mean_days": round(float(by_size[i]["days"]) / by_size[i]["n"], 1) if i in by_size else None}
                        for i, (_, _, name) in enumerate(SIZE_CLASSES)],
            "largest": largest}


def danger(place, d0, d1, series):
    path = events.EVENTS / "event_danger.parquet"
    if not path.exists():
        return {"note": "Danger levels are not built yet. Run: python pipeline/danger_model.py", "levels": [], "meaning": []}
    rows = events._rows(_events_sql(place, d0, d1, "r.level AS level, count(*) AS n, sum(e.area_km2) AS km2", "GROUP BY ALL"))
    by_level = {r["level"]: r for r in rows}
    levels = [{"level": name, "fires": by_level.get(i, {}).get("n", 0),
               "area_km2": round(float(by_level.get(i, {}).get("km2") or 0), 1)} for i, name in enumerate(fires.LEVELS)]
    levels.append({"level": "Not rated", "fires": by_level.get(None, {}).get("n", 0),
                   "area_km2": round(float(by_level.get(None, {}).get("km2") or 0), 1)})
    return {"note": None, "levels": levels, "meaning": fires.level_meanings()}


def vegetation(place, d0, d1, series):
    if not (events.EVENTS / "enrichment.parquet").exists():
        return {"note": "Burned-area and vegetation data are not built yet. Run: python pipeline/event_enrich.py", "classes": []}
    rows = events._rows(_events_sql(place, d0, d1, "x.vegetation AS vegetation, x.burned_km2 AS burned_km2, e.area_km2",
                                    "AND x.burned_km2 IS NOT NULL"))
    total = {}
    for row in rows:
        for key, km2 in json.loads(row["vegetation"] or "{}").items():
            total[key] = total.get(key, 0) + km2
    burned = sum(total.values()) or 1
    classes = sorted(({"name": events.LAND_COVER.get(int(k), f"class {k}"), "km2": round(v, 1), "share": round(v / burned, 4)}
                      for k, v in total.items() if v > 0), key=lambda c: -c["km2"])
    return {"note": None, "fires_with_map": len(rows), "burned_km2": round(sum(float(r["burned_km2"] or 0) for r in rows), 1),
            "hotspot_km2": round(sum(float(r["area_km2"]) for r in rows), 1), "classes": classes}


def missed(place, d0, d1, series):
    path = events.EVENTS / "reported_fires.parquet"
    if not path.exists():
        return {"note": "Reported fires are not built yet. Run: python pipeline/missed_fires.py", "by_size": []}
    case = " ".join(f"WHEN acres < {hi} THEN {i}" for i, (_, hi, _) in enumerate(REPORT_SIZES))
    rows = events._rows(f"""
        SELECT CASE WHEN acres IS NULL THEN -1 {case} END AS k, count(*) AS n,
               avg(seen_viirs::INT) AS viirs, avg(seen_modis::INT) AS modis, avg(seen_satellite::INT) AS either
        FROM '{path.as_posix()}'
        WHERE {place.where('lat', 'lon', 'substr(state, 4)')} AND date BETWEEN DATE '{d0}' AND DATE '{d1}'
          AND satellite_record_covers GROUP BY ALL""")
    by = {r["k"]: r for r in rows}
    names = [(i, name) for i, (_, _, name) in enumerate(REPORT_SIZES)] + [(-1, "size unknown")]
    return {"note": None if rows else "No reported wildfire in these places and dates (reports start in 2014).",
            "by_size": [{"size": name, "reports": by[i]["n"], "seen_viirs": round(by[i]["viirs"], 3),
                         "seen_modis": round(by[i]["modis"], 3), "seen_either": round(by[i]["either"], 3)}
                        for i, name in names if i in by]}


def sensors(place, d0, d1, series):
    tables, _, _ = events._source()
    rows = events._rows(f"""SELECT year(e.start) AS year, sum(e.detections_modis) AS modis, sum(e.detections_viirs) AS viirs,
                                   count(*) AS fires
                            FROM {tables} WHERE {place.where('e.lat', 'e.lon', 'e.state')} GROUP BY ALL ORDER BY ALL""")
    return {"years": [{"year": r["year"], "modis": int(r["modis"]), "viirs": int(r["viirs"]), "fires": r["fires"]} for r in rows]}


def methods(place, d0, d1, series):
    return {"items": [{"title": t, "text": x} for t, x in METHODS]}


def sources(place, d0, d1, series):
    last = db.cursor().execute("SELECT last_day FROM meta WHERE layer = ?", [LAYER]).fetchone()[0]
    return {"items": [{"name": n, "url": u} for n, u in SOURCES], "data_ends": last.isoformat()}


BUILDERS = {"summary": summary, "yearly": yearly, "seasonality": seasonality, "unusual": unusual,
            "fires": fires_in_period, "danger": danger, "vegetation": vegetation, "missed": missed,
            "sensors": sensors, "methods": methods, "sources": sources}
NEEDS_SERIES = {"summary", "yearly", "seasonality", "unusual"}


def build(states, boxes, d0, d1, sections):
    """The report as data: {places, start, end, sections: [{key, title, data}]} in the fixed order of SECTIONS."""
    if d0 > d1:
        raise BadRequest("The first day is after the last day.")
    unknown = [s for s in sections if s not in SECTIONS]
    if unknown:
        raise BadRequest(f"Unknown section: {unknown[0]}")
    place = Place(states, boxes)
    chosen = [key for key in SECTIONS if key in sections]
    series = _series(place) if NEEDS_SERIES & set(chosen) else None
    out = []
    for key in chosen:
        try:
            data = BUILDERS[key](place, d0, d1, series)
        except events.Missing as e:                 # a data file is not built: say so in that section only
            data = {"note": str(e)}
        out.append({"key": key, "title": SECTIONS[key], "data": data})
    return {"places": place.describe(), "start": d0.isoformat(), "end": d1.isoformat(),
            "generated": datetime.date.today().isoformat(), "sections": out}


def self_check():
    assert set(BUILDERS) == set(SECTIONS)
    p = Place(["ca", "NV"], [{"name": "x", "bbox": [-122, 39, -121, 40]}])
    assert p.where("lat", "lon", "state") == "(state IN ('CA', 'NV') OR (lat BETWEEN 39.0 AND 40.0 AND lon BETWEEN -122.0 AND -121.0))"
    for bad in (([], []), (["California"], []), (["CA'; --"], []), ([], [{"bbox": [1, 2, 0, 3]}])):
        try:
            Place(*bad)
        except BadRequest:
            continue
        raise AssertionError(bad)
    week = lambda s: datetime.date.fromisoformat(s)      # noqa: E731
    series = {"dates": [week("2024-07-01"), week("2024-07-08"), week("2024-07-15")], "value": [1.0, 2.0, 4.0]}
    assert _window_total(series, week("2024-07-07"), week("2024-07-10")) == 3.0      # touches the first two weeks
    assert _shift(week("2024-02-29"), 1) == week("2025-02-28")


if __name__ == "__main__":
    self_check()
    print("report ok")
