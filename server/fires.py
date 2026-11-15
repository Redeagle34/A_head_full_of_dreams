"""The danger rating of a fire, in words. The fires themselves are in events.py.

The rating (pipeline/danger_model.py) has three parts, always shown apart:
  level       chance that the fire reaches 1,000 acres, as one of five words
  exposure    built-up surface within 5 km of where it started
  behaviour   what VIIRS saw in the first two days: footprint, growth, night burning, weather

The model is trained on the fire events themselves (pipeline/danger_model.py writes one
rating per event to data/events/event_danger.parquet); rating() below turns that row into words.

Change here:
  LEVELS, LEVEL_STARTS   names of the levels and the chance at which each starts
  EXPOSURE               words for how much is built nearby
  conditions()           the plain-language facts listed with each rating
"""
import math

from . import db

LEVELS = ["Low", "Moderate", "High", "Very High", "Extreme"]
LEVEL_STARTS = [0.01, 0.05, 0.15, 0.40]     # calibrated chance of reaching 1,000 acres

# (built-up hectares within 5 km, words). First row whose limit is above the value wins.
EXPOSURE = [(1, "almost nothing built nearby"), (30, "scattered buildings"),
            (300, "a small town or dense rural housing"), (math.inf, "a town or city")]

LAND_COVER = {1: "evergreen needleleaf forest", 2: "evergreen broadleaf forest", 3: "deciduous needleleaf forest",
              4: "deciduous broadleaf forest", 5: "mixed forest", 6: "closed shrubland", 7: "open shrubland",
              8: "woody savanna", 9: "savanna", 10: "grassland", 11: "wetland", 12: "cropland", 13: "built-up land",
              14: "cropland and natural vegetation", 15: "snow and ice", 16: "barren land", 17: "water"}

# Columns of data/events/event_danger.parquet that rating() reads.
COLUMNS = ("fire_id, parts, share, fire_share, rated_first_day, rated_last_day, days_seen, acres, acres_day2, growth, "
           "d1_night_share, level, p100, p1000, built_5km, vs, rmin, fm1000, pr30, tmmx, lc").split(", ")
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


class NotBuilt(RuntimeError):
    """The fires table is missing: the danger pipeline has not been run."""


def level_meanings():
    """What each level meant on years the model never saw: share of fires that reached 100 and 1,000 acres."""
    rows = _run("SELECT level, name, fires, reached_100, reached_1000, median_acres FROM danger_levels ORDER BY level")
    return [{"level": level, "name": name, "fires": fires, "reached_100": round(r100, 4),
             "reached_1000": round(r1000, 4), "median_acres": round(median)}
            for level, name, fires, r100, r1000, median in rows]


def _run(sql, params=None):
    try:
        return db.cursor().execute(sql, params or {}).fetchall()
    except Exception as e:
        if "does not exist" in str(e):
            raise NotBuilt("Fire ratings are not built yet. Run pipeline/danger_fires.py, danger_inputs.py, "
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


def rating(f):
    """One row of event_danger.parquet -> the rating of that fire event. None when the event has no rated part."""
    f = {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in f.items()}
    if f["fire_id"] is None:
        return None
    level = None if f["level"] is None else int(f["level"])
    return {
        "level": level, "level_name": None if level is None else LEVELS[level],
        "p100": _clean(f["p100"], 3), "p1000": _clean(f["p1000"], 3),
        "built_ha": _clean(None if f["built_5km"] is None else f["built_5km"] / 10_000, 1),
        "exposure": exposure_words(f["built_5km"]),
        "land_cover": LAND_COVER.get(f["lc"]), "conditions": conditions(f),
        # The VIIRS group the model judged: its dates, its footprint on cells of about 440 m, and how
        # much of the event it is (share of the event's VIIRS detections; fire_share is the other way round).
        "first_day": f["rated_first_day"].isoformat(), "last_day": f["rated_last_day"].isoformat(),
        "acres": round(f["acres"]), "acres_day2": round(f["acres_day2"]),
        "parts": f["parts"], "share": round(f["share"], 3), "fire_share": round(f["fire_share"], 3),
    }


def direction(lat, lon, to_lat, to_lon):
    """Compass word for the way from (lat, lon) to (to_lat, to_lon)."""
    bearing = math.degrees(math.atan2(
        math.sin(math.radians(to_lon - lon)) * math.cos(math.radians(to_lat)),
        math.cos(math.radians(lat)) * math.sin(math.radians(to_lat)) -
        math.sin(math.radians(lat)) * math.cos(math.radians(to_lat)) * math.cos(math.radians(to_lon - lon))))
    return COMPASS[round(bearing / 45) % 8]


def self_check():
    import datetime
    assert exposure_words(0) == EXPOSURE[0][1] and exposure_words(5e7) == EXPOSURE[-1][1]
    assert exposure_words(float("nan")) is None
    base = dict(days_seen=3, growth=2.0, d1_night_share=0.5, vs=8.0, rmin=12.0, fm1000=8.0, pr30=0.0, tmmx=312.0)
    assert len(conditions(base)) == 7, conditions(base)
    assert conditions(dict(base, days_seen=1, growth=0.0))[0] == "seen on one day only"
    f = dict(base, fire_id=1, parts=2, share=0.9, fire_share=1.0, rated_first_day=datetime.date(2024, 7, 24),
             rated_last_day=datetime.date(2024, 8, 12), acres=1234.4, acres_day2=200.0, level=3.0, p100=1.0, p1000=0.2,
             built_5km=250_000.0, lc=1)
    d = rating(f)
    assert d["level_name"] == "Very High" and d["built_ha"] == 25.0 and d["acres"] == 1234, d
    assert rating(dict(f, level=float("nan")))["level"] is None           # Hawaii: grouped, not rated
    assert rating(dict.fromkeys(COLUMNS)) is None                         # an event with no VIIRS detection
    assert direction(40.0, -121.5, 40.5, -121.0) == "NE"


if __name__ == "__main__":
    self_check()
    print("fires ok")
