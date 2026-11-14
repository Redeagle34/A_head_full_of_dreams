"""Extract per-sample features from Earth Engine. Input: data/derived/pred/samples.parquet (id, lat, lon, date).
Output: one cached JSON per chunk in data/raw/gee_features/. Chunks are consecutive dates so each chunk needs few daily images.
Features (day d = label day; we use d's gridMET as a stand-in for a next-day forecast, d-1 and antecedent windows as observed):
 gridMET d: erc bi fm100 fm1000 vpd vs rmin rmax tmmx pr srad ; d-1: erc_l1 fm100_l1 vpd_l1 vs_l1 ; erc7 (mean d-7..d-1), pr30 (sum d-30..d-1), erc_max30
 static: elevation, slope (SRTM), pop_density (GPW v4.11 2020), FRG & MFRI (LANDFIRE), lc (MCD12Q1 2019 IGBP), tree cover (MOD44B 2019)"""
import sys, os, json, pathlib, time, pandas as pd, numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(__file__)); import _env, ee
ee.Initialize(project=os.environ["EE_PROJECT"])
OUT = pathlib.Path("data/raw/gee_features"); OUT.mkdir(parents=True, exist_ok=True)
GM = ee.ImageCollection("IDAHO_EPSCOR/GRIDMET")
dem = ee.Image("USGS/SRTMGL1_003")
STATIC = ee.Image.cat([
    dem.select("elevation"), ee.Terrain.slope(dem).rename("slope"),
    ee.ImageCollection("CIESIN/GPWv411/GPW_Population_Density").filterDate("2020-01-01", "2021-01-01").first().rename("pop_density"),
    ee.ImageCollection("LANDFIRE/Fire/FRG/v1_2_0").mosaic().rename("frg"),
    ee.ImageCollection("LANDFIRE/Fire/MFRI/v1_2_0").mosaic().rename("mfri"),
    ee.ImageCollection("MODIS/061/MCD12Q1").filterDate("2019-01-01", "2020-01-01").first().select("LC_Type1").rename("lc"),
    ee.ImageCollection("MODIS/061/MOD44B").filterDate("2019-01-01", "2020-01-01").first().select("Percent_Tree_Cover").rename("treecover"),
])
B = ["erc", "bi", "fm100", "fm1000", "vpd", "vs", "rmin", "rmax", "tmmx", "pr", "srad"]
def day_image(d):
    d = ee.Date(d)
    cur = GM.filterDate(d, d.advance(1, "day")).first().select(B)
    prev = GM.filterDate(d.advance(-1, "day"), d).first().select(["erc", "fm100", "vpd", "vs"], ["erc_l1", "fm100_l1", "vpd_l1", "vs_l1"])
    w7 = GM.filterDate(d.advance(-7, "day"), d).select("erc").mean().rename("erc7")
    w30 = GM.filterDate(d.advance(-30, "day"), d)
    return ee.Image.cat([cur, prev, w7, w30.select("pr").sum().rename("pr30"), w30.select("erc").max().rename("erc_max30"), STATIC])
def run_chunk(i, df):
    p = OUT / f"chunk_{i:05d}.json"
    if p.exists(): return i, "cached"
    fcs = []
    for d, g in df.groupby("date"):
        fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([float(r.lon), float(r.lat)]), {"id": int(r.id)}) for r in g.itertuples()])
        fcs.append(day_image(d).sampleRegions(collection=fc, scale=4000, geometries=False))
    for attempt in range(8):
        try:
            res = ee.FeatureCollection(fcs).flatten().getInfo()
            p.write_text(json.dumps([f["properties"] for f in res["features"]])); return i, len(res["features"])
        except Exception as e:
            time.sleep(min(120, 10 * 2 ** attempt)); err = str(e)[:150]
    return i, "FAIL " + err
if __name__ == "__main__":
    S = pd.read_parquet(sys.argv[1] if len(sys.argv) > 1 else "data/derived/pred/samples.parquet").sort_values(["date", "id"])
    S["date"] = S.date.astype(str)
    size = int(os.environ.get("CHUNK", 1500)); workers = int(os.environ.get("WORKERS", 8))
    chunks = [S.iloc[j:j + size] for j in range(0, len(S), size)]
    print("samples", len(S), "chunks", len(chunks), flush=True); t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(run_chunk, i, c) for i, c in enumerate(chunks)]
        for n, f in enumerate(as_completed(futs)):
            i, r = f.result()
            if n % 10 == 0 or "FAIL" in str(r): print(f"{n+1}/{len(chunks)} chunk {i}: {r}  {time.time()-t0:.0f}s", flush=True)
    print("DONE", flush=True)
