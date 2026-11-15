"""Proof of concept: detect active fire in historical Landsat-5 TM (pre-2012) in Earth Engine, at locations/dates where MODIS saw strong fires.
Rule adapted from Schroeder et al. 2016 (Landsat-8 OLI): rho_SWIR2/rho_NIR > 2.5, rho_SWIR2 - rho_NIR > 0.3, rho_SWIR2 > 0.5 (TM: SWIR2=B7, NIR=B4).
Daytime only (Landsat ~10:00-10:30 local, same overpass time as Terra)."""
import sys, os, json, pandas as pd, numpy as np; sys.path.insert(0, os.path.dirname(__file__)); import _env, ee
ee.Initialize(project=os.environ["EE_PROJECT"])
m = pd.read_csv("data/country/modis_2007_United_States.csv")
m = m[(m.satellite == "Terra") & (m.daynight == "D") & (m["type"] == 0) & (m.latitude < 49.5) & (m.longitude > -125)]
cand = m.sort_values("frp", ascending=False).drop_duplicates(subset=["acq_date"]).head(40)
rows = []
for r in cand.itertuples():
    pt = ee.Geometry.Point(r.longitude, r.latitude); d0 = ee.Date(r.acq_date)
    ic = ee.ImageCollection("LANDSAT/LT05/C02/T1_TOA").filterBounds(pt).filterDate(d0, d0.advance(1, "day"))
    n = ic.size().getInfo()
    if n == 0: continue
    img = ic.first(); b7, b4 = img.select("B7"), img.select("B4")
    fire = b7.divide(b4).gt(2.5).And(b7.subtract(b4).gt(0.3)).And(b7.gt(0.5))
    region = pt.buffer(5000)
    s = ee.Dictionary({"fire_px": fire.reduceRegion(ee.Reducer.sum(), region, 30).get("B7"),
                       "cloud": img.get("CLOUD_COVER"), "id": img.get("system:index")}).getInfo()
    rows.append({"date": r.acq_date, "lat": r.latitude, "lon": r.longitude, "modis_frp": r.frp, **s})
    print(rows[-1], flush=True)
    if len(rows) >= 8: break
pd.DataFrame(rows).to_csv("data/derived/us/landsat5_fire_poc_2007.csv", index=False)
print("same-day Landsat-5 scenes found:", len(rows), "| with fire pixels:", sum(1 for x in rows if (x["fire_px"] or 0) > 0))
