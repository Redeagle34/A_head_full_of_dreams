"""Does GOES lightning (GLM) flag lightning-caused fires before they are reported? Western U.S., fires discovered 2025-07-31 and 08-01.
Flashes: GOES-18 GLM-L2-LCFA, 2025-07-30 07:00 UTC .. 2025-08-02 07:00 UTC (public bucket noaa-goes18). Raw files are ~400 KB each
(about 5 GB for 72 h), so only flash time/lat/lon inside the western box are kept, per hour, in data/raw/glm/.
Outputs: data/derived/us/lightning_test.json"""
import requests, re, io, json, pathlib, sys, numpy as np, pandas as pd, netCDF4
from concurrent.futures import ThreadPoolExecutor
RAW = pathlib.Path("data/raw/glm"); RAW.mkdir(parents=True, exist_ok=True); B = "https://noaa-goes18.s3.amazonaws.com/"
HOURS = pd.date_range("2025-07-30 07:00", "2025-08-02 06:00", freq="h"); BOX = (-125, -104, 31, 49.5)
def one(key):
    for a in range(4):
        try:
            b = requests.get(B + key, timeout=60).content
            with netCDF4.Dataset("m", memory=b) as n:
                la, lo = n["flash_lat"][:].filled(np.nan), n["flash_lon"][:].filled(np.nan)
            t = pd.to_datetime(re.search(r"_s(\d{13})", key).group(1), format="%Y%j%H%M%S")
            m = (lo >= BOX[0]) & (lo <= BOX[1]) & (la >= BOX[2]) & (la <= BOX[3])
            return pd.DataFrame({"t": t, "lat": la[m].astype("float32"), "lon": lo[m].astype("float32")})
        except Exception as e: err = e
    print("FAIL", key, str(err)[:80], flush=True); return None
for h in HOURS:
    p = RAW / f"g18_{h:%Y%m%d_%H}.parquet"
    if p.exists(): continue
    x = requests.get(B, params={"list-type": "2", "prefix": f"GLM-L2-LCFA/{h:%Y/%j/%H}/"}, timeout=60).text; keys = re.findall(r"<Key>(.*?)</Key>", x)
    with ThreadPoolExecutor(24) as ex: parts = list(ex.map(one, keys))
    ok = [d for d in parts if d is not None]
    if len(ok) < 0.95 * max(len(keys), 1): print("hour incomplete, not cached", h, len(ok), len(keys), flush=True); continue
    pd.concat(ok).to_parquet(p); print(h, "files", len(keys), "flashes in box", sum(len(d) for d in ok), flush=True)
F = pd.concat(pd.read_parquet(f) for f in sorted(RAW.glob("g18_202507*.parquet")) + sorted(RAW.glob("g18_202508*.parquet")))
print("hours cached", len(list(RAW.glob("g18_*.parquet"))), "of", len(HOURS), "| flashes", len(F))
W = pd.read_parquet("data/raw/us_truth/wfigs_2025.parquet"); W = W[(W.IncidentTypeCategory == "WF") & W.InitialLongitude.between(BOX[0], BOX[1]) & W.InitialLatitude.between(BOX[2], BOX[3])]
W["t"] = W.FireDiscoveryDateTime.dt.tz_localize(None); W["day"] = (W.t + pd.to_timedelta(W.InitialLongitude / 15, unit="h")).dt.date.astype(str)
W = W[W.day.isin(["2025-07-31", "2025-08-01"])].rename(columns={"InitialLatitude": "lat", "InitialLongitude": "lon"}).reset_index(drop=True)
rng = np.random.default_rng(0); n = 3000
RND = pd.DataFrame({"lat": rng.uniform(BOX[2], BOX[3], n), "lon": rng.uniform(BOX[0], BOX[1], n), "t": rng.choice(W.t.values, n), "FireCause": "Random point"})
from scipy.spatial import cKDTree
fx = np.radians(F[["lat", "lon"]].values.astype(float)); c = np.cos(np.radians(40)); tree = cKDTree(np.c_[fx[:, 0], fx[:, 1] * c]); ft = F.t.values
def test(d, km, hours):
    q = np.radians(d[["lat", "lon"]].values); idx = tree.query_ball_point(np.c_[q[:, 0], q[:, 1] * c], km / 6371)
    hit, lead = [], []
    for i, t in zip(idx, d.t.values):
        dt = (t - ft[i]) / np.timedelta64(1, "h") if len(i) else np.array([]); ok = dt[(dt >= 0) & (dt <= hours)]
        hit.append(len(ok) > 0); lead.append(ok.max() if len(ok) else np.nan)      # lead = hours from first nearby flash to discovery
    return np.array(hit), np.array(lead)
R = {"flashes_in_box": int(len(F)), "hours": len(list(RAW.glob("g18_*.parquet"))), "fires": W.FireCause.value_counts().to_dict(), "tests": {}}
for km, hours in ((5, 24), (10, 24), (10, 48), (20, 48)):
    row = {}
    for cause, d in list(W.groupby("FireCause")) + [("Random point", RND)]:
        d = d[d.t - pd.Timedelta(hours=hours) >= HOURS[0]]            # only fires whose whole look-back window is covered
        if len(d) < 5: continue
        hit, lead = test(d, km, hours); row[cause] = {"n": int(len(d)), "flash_before": round(float(hit.mean()), 3), "median_lead_h": None if not hit.any() else round(float(np.nanmedian(lead)), 1)}
    R["tests"][f"{km}km_{hours}h"] = row
json.dump(R, open("data/derived/us/lightning_test.json", "w"), indent=1); print(json.dumps(R, indent=1))
