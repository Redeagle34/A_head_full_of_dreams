"""Blind-zone test on one real week: which reported fires did satellites miss, and what do non-imaging feeds add?
Reports: NIFC WFIGS (discovered 2026-11-09..11). Detections: FIRMS NRT 2026-11-09..13 (cached by 20_us_nrt_sources.py).
Cloud: MODIS Terra/Aqua daily cloud flag (MOD09GA/MYD09GA state_1km) at the report point. Smoke: NOAA HMS daily polygons.
Outputs: data/derived/us/blind_week.parquet, blind_week_metrics.json"""
import sys, os, io, json, pathlib, zipfile, requests, numpy as np, pandas as pd, geopandas as gpd
sys.path.insert(0, os.path.dirname(__file__)); import _env  # noqa
UA = {"User-Agent": "SpaceApps2026-research/0.1"}; RAW = pathlib.Path("data/raw"); D0, D1 = "2026-11-09", "2026-11-11"
# ---- reports
p = RAW / "us_truth/wfigs_2026-11-01_2026-11-14.json"
if not p.exists():
    BASE = "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations/FeatureServer/0/query"
    rows, off = [], 0
    while True:
        j = requests.get(BASE, params={"where": "FireDiscoveryDateTime >= DATE '2026-11-01' AND FireDiscoveryDateTime < DATE '2026-11-15'",
            "outFields": "UniqueFireIdentifier,IncidentName,IncidentTypeCategory,FireDiscoveryDateTime,CreatedOnDateTime_dt,FireCause,IncidentSize,DiscoveryAcres,FinalAcres,POOState,InitialLatitude,InitialLongitude",
            "returnGeometry": "false", "resultOffset": off, "resultRecordCount": 2000, "orderByFields": "OBJECTID", "f": "json"}, headers=UA, timeout=120).json()
        if "error" in j: sys.exit(str(j["error"]))
        rows += [f["attributes"] for f in j.get("features", [])]; off = len(rows)
        if not j.get("exceededTransferLimit"): break
    p.write_text(json.dumps(rows))
W = pd.DataFrame(json.loads(p.read_text())); W["t"] = pd.to_datetime(W.FireDiscoveryDateTime, unit="ms", utc=True)
print("reports Nov 1-14:", len(W), W.IncidentTypeCategory.value_counts().to_dict())
W = W.rename(columns={"InitialLatitude": "lat", "InitialLongitude": "lon"}).dropna(subset=["lat", "lon"])
W = W[W.lat.between(24.4, 49.5) & W.lon.between(-125, -66.9) & W.IncidentTypeCategory.isin(["WF", "RX"])]
W["day"] = (W.t + pd.to_timedelta(W.lon / 15, unit="h")).dt.tz_localize(None).dt.normalize()
W = W[W.day.between(D0, D1)].reset_index(drop=True); W["acres"] = W.FinalAcres.fillna(W.IncidentSize).fillna(W.DiscoveryAcres)
print("in window:", len(W), W.IncidentTypeCategory.value_counts().to_dict(), "| with size", int(W.acres.notna().sum()))
# ---- detections
def load(s, f):
    d = pd.read_csv(RAW / "firms" / f); d["src"] = s; d["day"] = pd.to_datetime(d.acq_date); return d[["latitude", "longitude", "day", "src"]]
DET = pd.concat([load("VIIRS", "conus_VIIRS_NOAA20_NRT_2026-11-09_5d.csv"), load("VIIRS", "conus_VIIRS_NOAA21_NRT_2026-11-09_5d.csv"),
                 load("MODIS", "conus_MODIS_NRT_2026-11-09_5d.csv"), load("LANDSAT", "conus_LANDSAT_NRT_2026-11-09_5d.csv"),
                 load("GOES", "conus_GOES_NRT_2026-11-12_2d.csv")])
print("detections:", DET.groupby("src").size().to_dict())
from scipy.spatial import cKDTree
def seen(src, km, lag=2):
    out = np.zeros(len(W), bool)
    for dd in range(0, lag + 1):
        for day, g in DET[DET.src.isin(src)].groupby("day"):
            m = (W.day + pd.Timedelta(days=dd) == day).values
            if not m.any(): continue
            x = np.radians(g[["latitude", "longitude"]].values); q = np.radians(W.loc[m, ["lat", "lon"]].values); c = np.cos(q[:, 0].mean())
            dist, _ = cKDTree(np.c_[x[:, 0], x[:, 1] * c]).query(np.c_[q[:, 0], q[:, 1] * c]); out[np.where(m)[0][dist * 6371 <= km]] = True
    return out
W["seen_polar"] = seen(["VIIRS", "MODIS"], 2); W["seen_landsat"] = seen(["LANDSAT"], 2); W["seen_polar_5km"] = seen(["VIIRS", "MODIS"], 5)
# ---- smoke
SM = []
for day in pd.date_range(D0, "2026-11-13"):
    z = RAW / f"us_extra/hms_smoke{day:%Y%m%d}.zip"
    if not z.exists():
        r = requests.get(f"https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Smoke_Polygons/Shapefile/{day:%Y/%m}/hms_smoke{day:%Y%m%d}.zip", headers=UA, timeout=120)
        if r.status_code != 200: print("smoke missing", day.date(), r.status_code); continue
        z.write_bytes(r.content)
    try: g = gpd.read_file(f"zip://{z}"); g["day"] = day; SM.append(g)
    except Exception as e: print("smoke unreadable", day.date(), str(e)[:80])
SM = pd.concat(SM) if SM else None
if SM is not None:
    print("smoke polygons per day:", SM.groupby("day").size().to_dict(), "cols", [c for c in SM.columns if c != "geometry"])
    P = gpd.GeoDataFrame(W[["day"]], geometry=gpd.points_from_xy(W.lon, W.lat), crs=4326); smk = np.zeros(len(W), bool)
    for dd in (0, 1):
        for day, g in SM.groupby("day"):
            m = (W.day + pd.Timedelta(days=dd) == day).values
            if m.any(): smk[np.where(m)[0]] |= P[m].within(g.to_crs(4326).geometry.buffer(0).union_all()).values
    W["under_smoke"] = smk
# ---- cloud at the MODIS overpasses (observed)
import ee; ee.Initialize(project=os.environ["EE_PROJECT"])
cp = RAW / "us_extra/blind_week_cloud.json"
if not cp.exists():
    res = {}
    for day in pd.date_range(D0, "2026-11-12"):
        m = (W.day == day) | (W.day + pd.Timedelta(days=1) == day)
        fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([float(r.lon), float(r.lat)]), {"i": int(i)}) for i, r in W[m].iterrows()])
        for col in ("MODIS/061/MOD09GA", "MODIS/061/MYD09GA"):
            ic = ee.ImageCollection(col).filterDate(f"{day:%Y-%m-%d}", f"{day + pd.Timedelta(days=1):%Y-%m-%d}")
            if ic.size().getInfo() == 0: continue
            img = ic.first().select("state_1km").bitwiseAnd(3).rename("c")
            for f in img.reduceRegions(fc, ee.Reducer.first(), 1000).getInfo()["features"]:
                res.setdefault(str(f["properties"]["i"]), {})[f"{day:%m%d}_{col[-7:-4]}"] = f["properties"].get("first")
    cp.write_text(json.dumps(res))
C = json.loads(cp.read_text())
def cloud(i, day):
    v = [x for k, x in C.get(str(i), {}).items() if x is not None and k[:4] in (f"{day:%m%d}", f"{day + pd.Timedelta(days=1):%m%d}")]
    return np.nan if not v else float(np.mean([x in (1, 2) for x in v]))     # share of looks that were cloudy or mixed
W["cloud_share"] = [cloud(i, r.day) for i, r in W.iterrows()]; W["cloudy"] = W.cloud_share >= 0.5
W.drop(columns=["t"]).assign(day=W.day.astype(str)).to_parquet("data/derived/us/blind_week.parquet")
# ---- summary
wf = W[W.IncidentTypeCategory == "WF"]; R = {"window_local_days": [D0, D1], "n_reports": int(len(W)), "n_wildfire": int(len(wf)), "n_prescribed": int((W.IncidentTypeCategory == "RX").sum())}
def rate(d, c): return None if len(d) == 0 else round(float(d[c].mean()), 3)
for name, d in (("wildfire", wf), ("prescribed", W[W.IncidentTypeCategory == "RX"]), ("wildfire_ge10ac", wf[wf.acres >= 10]), ("wildfire_ge100ac", wf[wf.acres >= 100])):
    known = d[d.cloud_share.notna()]
    R[name] = {"n": int(len(d)), "seen_polar_2km": rate(d, "seen_polar"), "seen_polar_5km": rate(d, "seen_polar_5km"), "seen_landsat_2km": rate(d, "seen_landsat"),
               "cloud_known_n": int(len(known)), "cloudy_share": rate(known, "cloudy"),
               "seen_if_clear": rate(known[~known.cloudy], "seen_polar"), "n_clear": int((~known.cloudy).sum()),
               "seen_if_cloudy": rate(known[known.cloudy], "seen_polar"), "n_cloudy": int(known.cloudy.sum()),
               "under_smoke": rate(d, "under_smoke") if "under_smoke" in d else None,
               "unseen_n": int((~d.seen_polar).sum()), "unseen_and_cloudy_n": int((~known.seen_polar & known.cloudy).sum()),
               "unseen_under_smoke_n": int((~d.seen_polar & d.under_smoke).sum()) if "under_smoke" in d else None}
json.dump(R, open("data/derived/us/blind_week_metrics.json", "w"), indent=1); print(json.dumps(R, indent=1))
print(wf.sort_values("acres", ascending=False)[["IncidentName", "POOState", "acres", "day", "seen_polar", "cloud_share", "under_smoke"]].head(12).to_string())
