"""Fires: one row per fire event, with its danger rating; and the reported fires that were missed.

A fire is detections of MODIS and VIIRS that touch on a grid of about 1 km and follow
within 5 days (pipeline/fire_events.py). This is the only kind of fire the page lists.

Reads the Parquet files written by pipeline/fire_events.py, pipeline/event_enrich.py,
pipeline/event_danger.py and pipeline/missed_fires.py. Each is optional: a missing file
gives an empty answer or an empty field, and a note saying which script to run.

Change here:
  MAX_EVENTS, MAX_RADIUS_KM   most fires in one answer, widest search around a point
  find()                      the order of the list
"""
import datetime
import decimal
import json

import duckdb

from . import fires
from .config import EE_PROJECT, ROOT

EVENTS = ROOT / "data" / "events"
DLAT, DLON = 0.01, 0.0125       # the grid of pipeline/fire_events.py
MAX_EVENTS = 300
MAX_RADIUS_KM = 500
EARTH_KM = 6371.0
MAX_CELLS = 30_000
MAX_REPORTED = 5_000

# MODIS land cover (MCD12Q1, IGBP classes).
LAND_COVER = {1: "Evergreen needleleaf forest", 2: "Evergreen broadleaf forest", 3: "Deciduous needleleaf forest",
              4: "Deciduous broadleaf forest", 5: "Mixed forest", 6: "Closed shrubland", 7: "Open shrubland",
              8: "Woody savanna", 9: "Savanna", 10: "Grassland", 11: "Wetland", 12: "Cropland", 13: "Built-up",
              14: "Cropland and natural vegetation", 15: "Snow and ice", 16: "Barren", 17: "Water"}


class Missing(RuntimeError):
    """A data file has not been built yet; the message names the script."""


def _file(name, script):
    path = EVENTS / name
    if not path.exists():
        raise Missing(f"{name} is missing. Run: python pipeline/{script}")
    return f"'{path.as_posix()}'"


def _rows(sql, params=()):
    cur = duckdb.connect().execute(sql, params)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def _plain(row):
    """Dates to text and exact decimals to plain numbers, so the row can be sent as JSON and used in sums."""
    def one(v):
        if isinstance(v, (datetime.date, datetime.datetime)):
            return v.isoformat()
        return float(v) if isinstance(v, decimal.Decimal) else v
    return {k: one(v) for k, v in row.items()}


def _source():
    """SQL for the events with what the optional files add: (FROM clause, columns, note about a missing rating file)."""
    tables, columns, note = [f"{_file('events.parquet', 'fire_events.py')} e"], ["e.*"], None
    for name, alias, added in (("enrichment.parquet", "x", ["burned_km2", "vegetation"]),
                               ("event_danger.parquet", "r", fires.COLUMNS)):
        path = EVENTS / name
        if path.exists():
            tables.append(f"LEFT JOIN '{path.as_posix()}' {alias} USING (event_id)")
            columns += [f"{alias}.{c}" for c in added]
        else:
            columns += [f"NULL AS {c}" for c in added]
            if alias == "r":
                note = "Danger levels are not linked to the fires yet. Run: python pipeline/event_danger.py"
    return " ".join(tables), ", ".join(columns), note


def _shape(row):
    """A database row as the page gets it: plain values, vegetation as a list, the rating as `danger`."""
    rated = {c: row.pop(c) for c in fires.COLUMNS}
    row = _with_vegetation(_plain(row))
    row["danger"] = fires.rating(rated)
    return row


def _with_vegetation(row):
    veg = row.pop("vegetation", None)
    row["vegetation"] = None
    if veg:
        parts = sorted(json.loads(veg).items(), key=lambda kv: -kv[1])
        total = sum(v for _, v in parts) or 1
        row["vegetation"] = [{"name": LAND_COVER.get(int(k), f"class {k}"), "km2": round(v, 2),
                              "share": round(v / total, 3)} for k, v in parts if v > 0]
    return row


def find(start, end, min_km2, bbox=None, near=None, min_level=0):
    """Fires that burned between start and end, in a map view (bbox) or within `km` of a point (near = lat, lon, km).

    Order: largest first (map view); highest danger level first, then nearest (around a point).
    Distance is to the nearest edge of the fire's bounding box, 0 inside it.
    """
    tables, columns, note = _source()
    where, params = ['e."end" >= $start AND e.start <= $end AND e.area_km2 >= $min_km2'], \
        {"start": start, "end": end, "min_km2": min_km2}
    distance = "NULL"
    if near:
        lat, lon, radius = near
        # Nearest point of the fire's box to the centre, then the great-circle distance to it.
        distance = f"""2 * {EARTH_KM} * asin(sqrt(
            pow(sin(radians(greatest(e.south, least(e.north, $lat)) - $lat) / 2), 2) +
            cos(radians($lat)) * cos(radians(greatest(e.south, least(e.north, $lat)))) *
            pow(sin(radians(greatest(e.west, least(e.east, $lon)) - $lon) / 2), 2)))"""
        where.append("e.north >= $lat - $reach AND e.south <= $lat + $reach "       # a first coarse cut
                     "AND e.east >= $lon - $reach / cos(radians($lat)) AND e.west <= $lon + $reach / cos(radians($lat))")
        params |= {"lat": lat, "lon": lon, "reach": radius / 111.0, "km": radius}
    else:
        west, south, east, north = bbox
        where.append("e.east >= $west AND e.west <= $east AND e.north >= $south AND e.south <= $north")
        params |= {"west": west, "south": south, "east": east, "north": north}
    outer = ["km <= $km"] if near else []
    if min_level > 0:
        outer.append("level >= $min_level")
        params["min_level"] = min_level
    order = "level DESC NULLS LAST, km ASC, area_km2 DESC" if near else "area_km2 DESC"
    rows = _rows(f"""SELECT * FROM (SELECT {columns}, {distance} AS km FROM {tables} WHERE {' AND '.join(where)})
                     {'WHERE ' + ' AND '.join(outer) if outer else ''} ORDER BY {order}, event_id LIMIT {MAX_EVENTS + 1}""", params)
    events = []
    for row in rows[:MAX_EVENTS]:
        km = row.pop("km")
        row = _shape(row)
        if near:
            row["km"] = round(km, 1)
            row["direction"] = fires.direction(near[0], near[1], row["lat"], row["lon"])
        events.append(row)
    return {"events": events, "truncated": len(rows) > MAX_EVENTS, "limit": MAX_EVENTS, "note": note}


def event(event_id):
    """One fire: its numbers, its rating and its ground cells (GeoJSON, each with the day it first burned)."""
    tables, columns, _ = _source()
    rows = _rows(f"SELECT {columns} FROM {tables} WHERE e.event_id = ?", [event_id])
    if not rows:
        return None
    info = _shape(rows[0])
    cells = _rows(f"""SELECT gy, gx, first_day, last_day, days FROM {_file('event_cells.parquet', 'fire_events.py')}
                      WHERE event_id = ? ORDER BY first_day LIMIT {MAX_CELLS}""", [event_id])
    start = datetime.date.fromisoformat(info["start"])
    features = []
    for c in cells:
        w, s = c["gx"] * DLON, c["gy"] * DLAT
        ring = [[round(w, 5), round(s, 5)], [round(w + DLON, 5), round(s, 5)], [round(w + DLON, 5), round(s + DLAT, 5)],
                [round(w, 5), round(s + DLAT, 5)], [round(w, 5), round(s, 5)]]
        features.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
                         "properties": {"day": (c["first_day"] - start).days, "first_day": c["first_day"].isoformat(),
                                        "last_day": c["last_day"].isoformat(), "days": c["days"]}})
    info["cells"] = {"type": "FeatureCollection", "features": features}
    info["reported"] = reported_near(info)
    return info


def reported_near(info):
    """Reported wildfires inside the fire's box (plus 2 km) while it burned (from 3 days before)."""
    path = EVENTS / "reported_fires.parquet"
    if not path.exists():
        return []
    pad = 0.02
    rows = _rows(f"""SELECT id, lat, lon, date, acres, cause, seen_satellite, score_ignition, expected_by_model, split
                     FROM '{path.as_posix()}'
                     WHERE lon BETWEEN ? AND ? AND lat BETWEEN ? AND ? AND date BETWEEN ?::DATE - 3 AND ?::DATE
                     ORDER BY acres DESC NULLS LAST LIMIT 20""",
                 [info["west"] - pad, info["east"] + pad, info["south"] - pad, info["north"] + pad,
                  info["start"], info["end"]])
    return [_plain(r) for r in rows]


def reported(bbox, start, end, missed):
    """Reported wildfires in the box and dates. `missed`: 'satellite', 'model', 'both' or 'all'."""
    west, south, east, north = bbox
    where = {"satellite": "NOT seen_satellite AND satellite_record_covers",
             "model": "NOT expected_by_model AND split = 'test'",
             "both": "NOT seen_satellite AND satellite_record_covers AND NOT expected_by_model AND split = 'test'",
             "all": "true"}[missed]
    src = _file("reported_fires.parquet", "missed_fires.py")
    cond = f"lon BETWEEN ? AND ? AND lat BETWEEN ? AND ? AND date BETWEEN ? AND ? AND {where}"
    params = [west, east, south, north, start, end]
    total = _rows(f"SELECT count(*) AS n FROM {src} WHERE {cond}", params)[0]["n"]
    rows = _rows(f"""SELECT id, lat, lon, date, acres, cause, split, seen_modis, seen_viirs, seen_satellite,
                            score_ignition, score_large100, expected_by_model
                     FROM {src} WHERE {cond} ORDER BY acres DESC NULLS LAST LIMIT {MAX_REPORTED}""", params)
    summary = EVENTS / "missed_summary.json"
    return {"total": total, "shown": len(rows), "fires": [_plain(r) for r in rows],
            "summary": json.loads(summary.read_text()) if summary.exists() else None}


# ---- sharper before / after pictures from Landsat, through Google Earth Engine ----

_ee = None


def _earth_engine():
    global _ee
    if _ee is None:
        import ee
        ee.Initialize(project=EE_PROJECT or None)
        _ee = ee
    return _ee


def sharp_pictures(info, days=45):
    """Cloud-free Landsat views before and after a fire, and the burn severity between them.

    Before: the DAYS days up to the day before the fire. After: the DAYS days from the day
    after it ended. Colors: shortwave infrared, near infrared, red: healthy plants are
    green, burned ground is red-brown. Severity: drop in the normalized burn ratio (dNBR);
    0.27 and more counts as moderate or high (USGS classes).
    """
    ee = _earth_engine()
    start, end = datetime.date.fromisoformat(info["start"]), datetime.date.fromisoformat(info["end"])
    pad_x, pad_y = max(0.02, (info["east"] - info["west"]) * 0.25), max(0.02, (info["north"] - info["south"]) * 0.25)
    box = ee.Geometry.Rectangle([info["west"] - pad_x, info["south"] - pad_y, info["east"] + pad_x, info["north"] + pad_y])

    def prepare(collection, swir2, nir, red):
        def one(img):
            qa = img.select("QA_PIXEL")
            clear = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0)).And(qa.bitwiseAnd(1 << 1).eq(0))
            return (img.select([swir2, nir, red], ["swir2", "nir", "red"]).multiply(0.0000275).add(-0.2)
                    .updateMask(clear).copyProperties(img, ["system:time_start"]))
        return ee.ImageCollection(collection).filterBounds(box).map(one)

    landsat = (prepare("LANDSAT/LC09/C02/T1_L2", "SR_B7", "SR_B5", "SR_B4")
               .merge(prepare("LANDSAT/LC08/C02/T1_L2", "SR_B7", "SR_B5", "SR_B4"))
               .merge(prepare("LANDSAT/LE07/C02/T1_L2", "SR_B7", "SR_B4", "SR_B3"))
               .merge(prepare("LANDSAT/LT05/C02/T1_L2", "SR_B7", "SR_B4", "SR_B3")))
    day = datetime.timedelta(days=1)

    def window(a, b):
        ic = landsat.filterDate(a.isoformat(), (b + day).isoformat())
        return ic.median(), ic.size()

    before, n_before = window(start - days * day, start - day)
    after, n_after = window(end + day, end + days * day)
    nbr = lambda im: im.normalizedDifference(["nir", "swir2"])
    dnbr = nbr(before).subtract(nbr(after)).rename("dnbr")
    severe = dnbr.gte(0.27)
    stats = (severe.multiply(ee.Image.pixelArea()).rename("severe_m2").addBands(dnbr.mask().multiply(ee.Image.pixelArea()).rename("valid_m2"))
             .reduceRegion(ee.Reducer.sum(), box, 60, maxPixels=1e9))
    numbers = ee.Dictionary({"n_before": n_before, "n_after": n_after, "stats": stats}).getInfo()
    width_km = (info["east"] - info["west"] + 2 * pad_x) * 111.32 * 0.78
    view = {"region": box, "dimensions": 640, "format": "jpg"}
    color = {"bands": ["swir2", "nir", "red"], "min": 0.0, "max": 0.45}
    out = {"days": days, "width_km": round(width_km, 1),
           "before": {"from": (start - days * day).isoformat(), "to": (start - day).isoformat(), "scenes": numbers["n_before"]},
           "after": {"from": (end + day).isoformat(), "to": (end + days * day).isoformat(), "scenes": numbers["n_after"]},
           "severe_km2": None, "valid_km2": None}
    if numbers["n_before"]:
        out["before"]["url"] = before.getThumbURL({**view, **color})
    if numbers["n_after"]:
        out["after"]["url"] = after.getThumbURL({**view, **color})
    if numbers["n_before"] and numbers["n_after"]:
        out["severity_url"] = dnbr.getThumbURL({**view, "min": -0.1, "max": 0.8,
                                                "palette": ["1a9850", "ffffbf", "fdae61", "d73027", "7f0000"]})
        out["severe_km2"] = round((numbers["stats"].get("severe_m2") or 0) / 1e6, 2)
        out["valid_km2"] = round((numbers["stats"].get("valid_m2") or 0) / 1e6, 2)
    return out
