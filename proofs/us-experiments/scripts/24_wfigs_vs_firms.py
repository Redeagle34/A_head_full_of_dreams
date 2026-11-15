"""Experiment E: share of NIFC-reported fires (WFIGS 2023-2024) detected by satellites, by size class, region and sensor.
Match = any filtered detection within R km and [discovery-1d, discovery+3d]. Also: time from discovery to first satellite detection."""
import pandas as pd, numpy as np, json, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from sklearn.neighbors import BallTree
R_KM = 2.0; RE = 6371.0; out = {}
def pts(year):
    fr = []
    for f, sensor in [(f"data/country/viirs-snpp_{year}_United_States.csv", "VIIRS"), (f"data/country/viirs-jpss1_{year}_United_States.csv", "VIIRS"),
                      (f"data/country/modis_{year}_United_States.csv", "MODIS")]:
        d = pd.read_csv(f, usecols=["latitude", "longitude", "acq_date", "acq_time", "confidence", "type"], dtype={"confidence": str})
        good = (pd.to_numeric(d.confidence, errors="coerce") >= 30) if sensor == "MODIS" else d.confidence.isin(["n", "h"])
        d = d[good & (d["type"] == 0)]
        d["t"] = pd.to_datetime(d.acq_date + " " + d.acq_time.astype(str).str.zfill(4), format="%Y-%m-%d %H%M", utc=True); d["sensor"] = sensor
        fr.append(d[["latitude", "longitude", "t", "sensor"]])
    return pd.concat(fr, ignore_index=True)
rows = []
for y in [2023, 2024]:
    w = pd.read_parquet(f"data/raw/us_truth/wfigs_{y}.parquet").dropna(subset=["InitialLatitude", "InitialLongitude", "FireDiscoveryDateTime"])
    w = w[w.IncidentTypeCategory.isin(["WF", "RX"])].copy()
    w["acres"] = w.FinalAcres.fillna(w.IncidentSize).fillna(w.DiscoveryAcres)
    p = pts(y)
    for sensor in ["VIIRS", "MODIS", "ANY"]:
        q = p if sensor == "ANY" else p[p.sensor == sensor]
        tree = BallTree(np.radians(q[["latitude", "longitude"]].values), metric="haversine")
        ind = tree.query_radius(np.radians(w[["InitialLatitude", "InitialLongitude"]].values), r=R_KM / RE)
        tq = q.t.values
        hit = np.zeros(len(w), bool); lag = np.full(len(w), np.nan)
        disc = w.FireDiscoveryDateTime.values
        for i, ix in enumerate(ind):
            if len(ix) == 0: continue
            dt = (tq[ix] - disc[i]) / np.timedelta64(1, "h")
            ok = (dt >= -24) & (dt <= 72)
            if ok.any(): hit[i] = True; lag[i] = dt[ok].min()
        w[f"hit_{sensor}"] = hit; w[f"lag_{sensor}"] = lag
    w["year"] = y; rows.append(w)
W = pd.concat(rows, ignore_index=True)
bins = [-1, 1, 10, 100, 1000, 10000, 1e9]; labs = ["<1 ac", "1-10", "10-100", "100-1k", "1k-10k", ">10k"]
W["size"] = pd.cut(W.acres, bins, labels=labs)
lon = W.InitialLongitude; W["region"] = np.where(W.POOState.isin(["US-AK"]), "Alaska", np.where(lon < -104, "West", np.where(lon < -90, "Central", "East")))
t = W[W.IncidentTypeCategory == "WF"].groupby("size", observed=True).agg(n=("hit_ANY", "size"), VIIRS=("hit_VIIRS", "mean"), MODIS=("hit_MODIS", "mean"), ANY=("hit_ANY", "mean"))
print("Wildfires (WF) detected by size class, 2023-2024:\n", t.round(3).to_string())
out["wf_by_size"] = t.round(3).reset_index().to_dict("records")
t2 = W.groupby(["IncidentTypeCategory"]).agg(n=("hit_ANY", "size"), VIIRS=("hit_VIIRS", "mean"), MODIS=("hit_MODIS", "mean"), unknown_size=("acres", lambda s: s.isna().mean()))
print("\nBy type:\n", t2.round(3).to_string()); out["by_type"] = t2.round(3).reset_index().to_dict("records")
big = W[(W.IncidentTypeCategory == "WF") & (W.acres >= 100)]
t3 = big.groupby("region").agg(n=("hit_ANY", "size"), VIIRS=("hit_VIIRS", "mean"), MODIS=("hit_MODIS", "mean"))
print("\nWF >=100 acres by region:\n", t3.round(3).to_string()); out["wf100_by_region"] = t3.round(3).reset_index().to_dict("records")
lg = big.lag_VIIRS.dropna()
out["lag_hours_first_VIIRS_vs_discovery_wf100"] = {"median": round(float(lg.median()), 1), "share_before_discovery": round(float((lg < 0).mean()), 3), "p90": round(float(lg.quantile(.9)), 1)}
print("\nFirst VIIRS detection minus reported discovery (h), WF>=100ac:", out["lag_hours_first_VIIRS_vs_discovery_wf100"])
# cause breakdown of detection
t4 = W[(W.IncidentTypeCategory == "WF")].groupby("FireCause").agg(n=("hit_ANY", "size"), ANY=("hit_ANY", "mean"))
print("\nBy cause:\n", t4.round(3).to_string()); out["wf_by_cause"] = t4.round(3).reset_index().to_dict("records")
W.drop(columns=[c for c in W.columns if W[c].dtype == object and c not in ("IncidentTypeCategory", "FireCause", "POOState", "region")]).to_parquet("data/derived/us/wfigs_matched_2023_2024.parquet")
fig, ax = plt.subplots(figsize=(8, 4)); t[["MODIS", "VIIRS"]].plot.bar(ax=ax); ax.set_ylabel("share detected"); ax.set_title(f"NIFC-reported US wildfires seen by satellite (≤{R_KM:g} km, −1/+3 days), 2023–24")
for i, n in enumerate(t.n): ax.text(i, 1.01, f"n={n}", ha="center", fontsize=7)
ax.set_ylim(0, 1.1); plt.tight_layout(); plt.savefig("outputs/us_E1_detection_by_size.png", dpi=130)
json.dump(out, open("data/derived/us/wfigs_detection_metrics.json", "w"), indent=1, default=str)
