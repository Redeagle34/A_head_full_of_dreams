"""Fires and their danger rating: list them for a map view or around a point.

A fire is a group of VIIRS detections that touch in space and time (pipeline/fire_events.py).
Its rating (pipeline/danger_model.py) has three parts, always shown apart:
  level       chance that the fire reaches 1,000 acres, as one of five words
  exposure    built-up surface within 5 km of where it started
  behaviour   what the satellites saw: size, growth, radiative power, night burning

Change here:
  LEVELS, LEVEL_STARTS   names of the levels and the chance at which each starts
  EXPOSURE               words for how much is built nearby
  conditions()           the plain-language facts listed with each fire
  MAX_FIRES, MAX_RADIUS_KM
"""
import math

from . import db

LEVELS = ["Low", "Moderate", "High", "Very High", "Extreme"]
LEVEL_STARTS = [0.01, 0.05, 0.15, 0.40]     # calibrated chance of reaching 1,000 acres
MAX_FIRES = 400                             # most fires in one answer
MAX_RADIUS_KM = 500
EARTH_KM = 6371.0
CIRCLE_5KM_HA = 7854.0

# (built-up hectares within 5 km, words). First row whose limit is above the value wins.
EXPOSURE = [(1, "almost nothing built nearby"), (30, "scattered buildings"),
            (300, "a small town or dense rural housing"), (math.inf, "a town or city")]

LAND_COVER = {1: "evergreen needleleaf forest", 2: "evergreen broadleaf forest", 3: "deciduous needleleaf forest",
              4: "deciduous broadleaf forest", 5: "mixed forest", 6: "closed shrubland", 7: "open shrubland",
              8: "woody savanna", 9: "savanna", 10: "grassland", 11: "wetland", 12: "cropland", 13: "built-up land",
              14: "cropland and natural vegetation", 15: "snow and ice", 16: "barren land", 17: "water"}

COLUMNS = ("fire_id, state, first_day, last_day, days_seen, lat, lon, west, south, east, north, acres, acres_day2, "
           "growth, frp_max, d1_night_share, level, p100, p1000, built_5km, vs, rmin, fm1000, pr30, tmmx, lc")
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


class NotBuilt(RuntimeError):
    """The fires table is missing: the danger pipeline has not been run."""


def level_meanings():
    """What each level meant on years the model never saw: share of fires that reached 100 and 1,000 acres."""
    rows = _run("SELECT level, name, fires, reached_100, reached_1000, median_acres FROM danger_levels ORDER BY level")
    return [{"level": level, "name": name, "fires": fires, "reached_100": round(r100, 4),
             "reached_1000": round(r1000, 4), "median_acres": round(median)}
            for level, name, fires, r100, r1000, median in rows]


def find(d0, d1, bbox=None, near=None, min_level=0):
    """Fires seen between d0 and d1, in a map view (bbox) or within `km` of a point (near = lat, lon, km).

    Order: highest level first; then nearest first (around a point) or largest first (map view).
    Distance is to the nearest edge of the fire's bounding box, 0 inside it.
    """
    where, params = ["first_day <= $d1 AND last_day >= $d0"], {"d0": d0, "d1": d1}
    distance = "NULL"
    if near:
        lat, lon, radius = near
        # Nearest point of the fire's box to the centre, then the great-circle distance to it.
        distance = f"""2 * {EARTH_KM} * asin(sqrt(
            pow(sin(radians(greatest(south, least(north, $lat)) - $lat) / 2), 2) +
            cos(radians($lat)) * cos(radians(greatest(south, least(north, $lat)))) *
            pow(sin(radians(greatest(west, least(east, $lon)) - $lon) / 2), 2)))"""
        reach = radius / 111.0                              # degrees of latitude, a first coarse cut
        where.append("north >= $lat - $reach AND south <= $lat + $reach "
                     "AND east >= $lon - $reach / cos(radians($lat)) AND west <= $lon + $reach / cos(radians($lat))")
        params |= {"lat": lat, "lon": lon, "reach": reach, "km": radius}
    else:
        west, south, east, north = bbox
        where.append("east >= $west AND west <= $east AND north >= $south AND south <= $north")
        params |= {"west": west, "south": south, "east": east, "north": north}
    if min_level > 0:
        where.append("level >= $min_level")
        params["min_level"] = min_level
    order = "level DESC NULLS LAST, " + ("km ASC" if near else "acres DESC")
    rows = _run(f"""SELECT * FROM (SELECT {COLUMNS}, {distance} AS km FROM fires WHERE {' AND '.join(where)})
                    {'WHERE km <= $km' if near else ''} ORDER BY {order} LIMIT {MAX_FIRES + 1}""", params)
    names = COLUMNS.split(", ") + ["km"]
    fires = [_describe(dict(zip(names, row)), near) for row in rows[:MAX_FIRES]]
    return {"fires": fires, "truncated": len(rows) > MAX_FIRES}


def _run(sql, params=None):
    try:
        return db.cursor().execute(sql, params or {}).fetchall()
    except Exception as e:
        if "does not exist" in str(e):
            raise NotBuilt("Fire ratings are not built yet. Run pipeline/fire_events.py, danger_inputs.py, "
                           "danger_model.py.") from e
        raise


def _clean(value, digits):
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else round(value, digits)


def exposure_words(built_m2):
    if built_m2 is None or math.isnan(built_m2):
        return None
    hectares = built_m2 / 10_000
    return next(words for limit, words in EXPOSURE if hectares < limit)


def conditions(f):
    """Plain facts about the fire and its first day. Facts, not the model's reasoning."""
    out = []
    if f["days_seen"] == 1:
        out.append("seen on one day only")
    elif f["growth"] is not None and f["growth"] >= 1:
        times = f["growth"] + 1
        out.append("footprint grew more than 10 times on day 2" if times > 10 else f"footprint grew {times:.1f} times on day 2")
    elif f["growth"] == 0:
        out.append("not seen on day 2")
    if f["d1_night_share"]:
        out.append("burned at night on day 1")
    if f["vs"] is not None and f["vs"] >= 6:
        out.append(f"strong wind, {f['vs'] * 3.6:.0f} km/h")
    if f["rmin"] is not None and f["rmin"] <= 20:
        out.append(f"very dry air, {f['rmin']:.0f}% humidity")
    if f["fm1000"] is not None and f["fm1000"] <= 10:
        out.append("very dry heavy fuels")
    if f["pr30"] is not None and f["pr30"] < 5:
        out.append("almost no rain in 30 days")
    if f["tmmx"] is not None and f["tmmx"] - 273.15 >= 35:
        out.append(f"hot, {f['tmmx'] - 273.15:.0f} °C")
    return out


def _describe(f, near):
    f = {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in f.items()}
    out = {
        "id": f["fire_id"], "state": f["state"], "lat": round(f["lat"], 4), "lon": round(f["lon"], 4),
        "bbox": [round(f[k], 4) for k in ("west", "south", "east", "north")],
        "first_day": f["first_day"].isoformat(), "last_day": f["last_day"].isoformat(), "days_seen": f["days_seen"],
        "acres": round(f["acres"]), "acres_day2": round(f["acres_day2"]), "frp_max": _clean(f["frp_max"], 1),
        "level": f["level"], "level_name": None if f["level"] is None else LEVELS[f["level"]],
        "p100": _clean(f["p100"], 3), "p1000": _clean(f["p1000"], 3),
        "built_ha": _clean(None if f["built_5km"] is None else f["built_5km"] / 10_000, 1),
        "exposure": exposure_words(f["built_5km"]),
        "land_cover": LAND_COVER.get(f["lc"]), "conditions": conditions(f),
    }
    if near:
        lat, lon, _ = near
        out["km"] = round(f["km"], 1)
        bearing = math.degrees(math.atan2(
            math.sin(math.radians(f["lon"] - lon)) * math.cos(math.radians(f["lat"])),
            math.cos(math.radians(lat)) * math.sin(math.radians(f["lat"])) -
            math.sin(math.radians(lat)) * math.cos(math.radians(f["lat"])) * math.cos(math.radians(f["lon"] - lon))))
        out["direction"] = COMPASS[round(bearing / 45) % 8]
    return out


def self_check():
    assert exposure_words(0) == EXPOSURE[0][1] and exposure_words(5e7) == EXPOSURE[-1][1]
    assert exposure_words(float("nan")) is None
    base = dict(days_seen=3, growth=2.0, d1_night_share=0.5, vs=8.0, rmin=12.0, fm1000=8.0, pr30=0.0, tmmx=312.0)
    assert len(conditions(base)) == 7, conditions(base)
    assert conditions(dict(base, days_seen=1, growth=0.0))[0] == "seen on one day only"
    # A fire due north-east of the point.
    f = dict(base, fire_id=1, state="CA", first_day=__import__("datetime").date(2024, 7, 24),
             last_day=__import__("datetime").date(2024, 8, 12), lat=40.5, lon=-121.0, west=-121.1, south=40.4,
             east=-120.9, north=40.6, acres=1234.4, acres_day2=200.0, frp_max=55.55, level=3, p100=1.0, p1000=0.2,
             built_5km=250_000.0, lc=1, km=42.0)
    d = _describe(f, (40.0, -121.5, 100))
    assert d["direction"] == "NE" and d["level_name"] == "Very High" and d["built_ha"] == 25.0, d


if __name__ == "__main__":
    self_check()
    print("fires ok")
