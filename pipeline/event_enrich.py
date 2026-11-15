"""For the larger fires: how much burned according to an independent map, and what vegetation.

Run:  python pipeline/event_enrich.py [earth-engine-project] [min_km2]
      (after pipeline/fire_events.py; needs Google Earth Engine sign-in)
Output: data/events/enrichment.parquet   event_id, burned_km2, vegetation (JSON: class -> km2)

Per fire, inside its bounding box and in the calendar months it burned:
  burned_km2   area the MODIS burned-area map (MCD64A1, 500 m) marks as burned. This comes
               from the change in the land surface, not from hotspots, so it is a second
               opinion on the hotspot-based area_km2.
  vegetation   that burned area split by land cover (MCD12Q1, IGBP classes) of the year
               before the fire.

Limits: the box can hold a neighbouring fire of the same months; MCD64A1 misses small and
low-severity burns (most cropland fires), where burned_km2 is 0 and vegetation is empty.
Safe to rerun: finished fires are kept and skipped.
"""
import datetime
import json
import pathlib
import sys

import duckdb
import ee
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVENTS = ROOT / "data" / "events"
OUT = EVENTS / "enrichment.parquet"
BATCH = 150
LAND_COVER_YEARS = (2001, 2022)          # years MCD12Q1 is taken from


def month_start(day, add=0):
    month = day.month - 1 + add
    return datetime.date(day.year + month // 12, month % 12 + 1, 1)


def enrich(rows):
    """rows: dicts with event_id, start, end, west, south, east, north -> list of result dicts."""
    features = []
    for r in rows:
        lc_year = min(max(r["start"].year - 1, LAND_COVER_YEARS[0]), LAND_COVER_YEARS[1])
        features.append(ee.Feature(ee.Geometry.Rectangle([r["west"], r["south"], r["east"], r["north"]]), {
            "event_id": r["event_id"], "m0": month_start(r["start"]).isoformat(),
            "m1": month_start(r["end"], 1).isoformat(), "lc0": f"{lc_year}-01-01", "lc1": f"{lc_year + 1}-01-01"}))
    burned_maps = ee.ImageCollection("MODIS/061/MCD64A1").select("BurnDate")
    land_cover = ee.ImageCollection("MODIS/061/MCD12Q1").select("LC_Type1")
    nothing = ee.ImageCollection([ee.Image.constant(0).rename("BurnDate")])

    def one(f):
        burned = (burned_maps.filterDate(f.get("m0"), f.get("m1")).map(lambda i: i.gt(0).unmask(0))
                  .merge(nothing).max())
        lc = land_cover.filterDate(f.get("lc0"), f.get("lc1")).first()
        image = ee.Image.pixelArea().divide(1e6).updateMask(burned).addBands(lc)
        groups = image.reduceRegion(ee.Reducer.sum().group(1, "lc"), f.geometry(), 500, maxPixels=1e9).get("groups")
        return ee.Feature(None, {"event_id": f.get("event_id"), "groups": groups})

    out = []
    for f in ee.FeatureCollection(features).map(one).getInfo()["features"]:
        veg = {str(g["lc"]): round(g["sum"], 3) for g in f["properties"].get("groups") or []}
        out.append({"event_id": f["properties"]["event_id"], "burned_km2": round(sum(veg.values()), 2),
                    "vegetation": json.dumps(veg)})
    return out


def main():
    ee.Initialize(project=sys.argv[1] if len(sys.argv) > 1 else None)
    min_km2 = float(sys.argv[2]) if len(sys.argv) > 2 else 25.0
    done = pd.read_parquet(OUT) if OUT.exists() else pd.DataFrame(columns=["event_id", "burned_km2", "vegetation"])
    todo = duckdb.connect().execute(f"""
        SELECT event_id, start, "end", west, south, east, north FROM '{(EVENTS / 'events.parquet').as_posix()}'
        WHERE area_km2 >= ? ORDER BY area_km2 DESC""", [min_km2]).df()
    todo = todo[~todo.event_id.isin(done.event_id)].to_dict("records")
    print(f"fires of {min_km2:g} km2 or more still to do: {len(todo)} (done before: {len(done)})", flush=True)
    for i in range(0, len(todo), BATCH):
        rows = enrich(todo[i:i + BATCH])
        new = pd.DataFrame(rows)
        done = new if done.empty else pd.concat([done, new], ignore_index=True)
        done.astype({"event_id": "int64", "burned_km2": "float64"}).to_parquet(OUT)
        print(f"  {min(i + BATCH, len(todo))} / {len(todo)}", flush=True)
    assert done.event_id.is_unique
    both = duckdb.connect().execute(f"""
        SELECT count(*), round(sum(x.burned_km2)), round(sum(e.area_km2)), round(corr(x.burned_km2, e.area_km2), 3),
               round(avg((x.burned_km2 = 0)::INT), 3)
        FROM '{OUT.as_posix()}' x JOIN '{(EVENTS / 'events.parquet').as_posix()}' e USING (event_id)""").fetchone()
    print(f"fires: {both[0]} | burned-area map total {both[1]:.0f} km2 | hotspot total {both[2]:.0f} km2 | "
          f"correlation {both[3]} | share with no mapped burn {both[4]}")


if __name__ == "__main__":
    main()
