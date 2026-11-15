"""Test the Sofiev & Kouznetsov (2026, GMD 19:10123) FRP observation operator on US FIRMS data.
Own re-implementation of the published functional form (parameters as in github.com/fmidev/FRP_OOp FRP_OOp_pixel.py, GPL-3; we do not copy code).
  DL(S) = a*S + b  [MW], S = pixel area km2 (FIRMS scan*track); day/night & instrument specific
  r(S)  = r0 + r1/S ;  P(F) = max(0, 1/(1+exp(-r(F-DL))) - c)/(1-c)
T1 detection limits. T2 zero-fit prediction: from SNPP fires, predict how many 0.1deg cell-days Aqua should see; compare to actual (2013-2025).
T3 MODIS->VIIRS: Horvitz-Thompson weighting of Aqua cell-days by 1/P (uses only MODIS-era observables: FRP, pixel size, day/night)."""
import pandas as pd, numpy as np, json, glob
P = {"MODIS": dict(dr0=.07, dr1=1.26, nr0=.11, nr1=1.06, c=.045, da=4.44, db=.52, na=4.43, nb=1.01),
     "VIIRS": dict(dr0=.61, dr1=.21, nr0=2.12, nr1=1.02, c=.05, da=6.17, db=1.44, na=1.38, nb=.35)}
def DL(inst, S, night): p = P[inst]; return np.where(night, p["na"]*S + p["nb"], p["da"]*S + p["db"])
def prob(inst, F, S, night):
    p = P[inst]; r = np.where(night, p["nr0"] + p["nr1"]/S, p["dr0"] + p["dr1"]/S)
    x = np.clip(-r*(F - DL(inst, S, night)), -50, 50)
    return np.clip((1/(1+np.exp(x)) - p["c"])/(1 - p["c"]), 0, 1)
out = {}
out["T1_DL_MW"] = {f"{i}_{w}_{n}": round(float(DL(i, S, n == "night")), 2) for i, Ss in [("MODIS", {"nadir(1x1)": 1.0, "edge(4.8x2.0)": 9.6}), ("VIIRS", {"nadir(.375^2)": .14, "edge(.8x.8)": .64})] for w, S in Ss.items() for n in ["day", "night"]}
print("T1 detection limits (MW):", out["T1_DL_MW"])
reg = lambda lat, lon: np.where((lat > 51) & (lon < -129), "Alaska", np.where(lon < -104, "West", np.where(lon < -90, "Central", "East")))
cols = ["latitude", "longitude", "acq_date", "frp", "scan", "track", "daynight", "confidence", "type", "satellite"]
T2, T3 = [], []
MODIS_S_MEAN = 2.45  # FRP-weighted mean MODIS pixel area (paper/code)
for y in range(2013, 2026):
    v = pd.read_csv(f"data/country/viirs-snpp_{y}_United_States.csv", usecols=cols, dtype={"confidence": str})
    v = v[v.confidence.isin(["n", "h"]) & (v["type"] == 0) & (v.latitude > 23)]
    v["c01"] = np.floor(v.latitude*10).astype(int)*10000 + np.floor(v.longitude*10).astype(int)
    v["c001"] = np.floor(v.latitude*100).astype(np.int64)*100000 + np.floor(v.longitude*100).astype(np.int64)
    # aggregate VIIRS FRP to ~1 km (MODIS-pixel-sized) clusters per overpass-day, then P(MODIS sees cluster)
    g = v.groupby(["acq_date", "daynight", "c001", "c01"], as_index=False).agg(F=("frp", "sum"), lat=("latitude", "first"), lon=("longitude", "first"))
    g["pm"] = prob("MODIS", g.F.values, MODIS_S_MEAN, (g.daynight == "N").values)
    # P(MODIS sees the 0.1deg cell-day) = 1 - prod(1 - p)
    g["lq"] = np.log1p(-np.minimum(g.pm, .999999))
    cd = g.groupby(["acq_date", "c01"], as_index=False).agg(lq=("lq", "sum"), lat=("lat", "first"), lon=("lon", "first"))
    cd["p_cell"] = 1 - np.exp(cd.lq); cd["region"] = reg(cd.lat.values, cd.lon.values); cd["m"] = pd.to_datetime(cd.acq_date).dt.month
    a = pd.read_csv(f"data/country/modis_{y}_United_States.csv", usecols=cols)
    a = a[(a.satellite == "Aqua") & (pd.to_numeric(a.confidence, errors="coerce") >= 30) & (a["type"] == 0) & (a.latitude > 23)]
    a["c01"] = np.floor(a.latitude*10).astype(int)*10000 + np.floor(a.longitude*10).astype(int)
    a["p"] = prob("MODIS", a.frp.values, (a.scan*a.track).values, (a.daynight == "N").values)
    ac = a.groupby(["acq_date", "c01"], as_index=False).agg(lq=("p", lambda s: np.log1p(-np.minimum(s, .999)).sum()), lat=("latitude", "first"), lon=("longitude", "first"))
    ac["p_cell"] = 1 - np.exp(ac.lq); ac["w"] = 1/np.maximum(ac.p_cell, .1)
    ac["region"] = reg(ac.lat.values, ac.lon.values); ac["m"] = pd.to_datetime(ac.acq_date).dt.month
    for (r_, m_), x in cd.groupby(["region", "m"]):
        aa = ac[(ac.region == r_) & (ac.m == m_)]
        T2.append({"y": y, "region": r_, "m": m_, "viirs_cd": len(x), "pred_aqua_cd": x.p_cell.sum(), "aqua_cd": len(aa), "aqua_ht": aa.w.sum()})
    print(y, "done", flush=True)
t = pd.DataFrame(T2); t.to_csv("data/derived/us/obsop_region_month.csv", index=False)
tot = t.groupby("y")[["viirs_cd", "pred_aqua_cd", "aqua_cd", "aqua_ht"]].sum()
tot["pred/actual_aqua"] = (tot.pred_aqua_cd/tot.aqua_cd).round(3); tot["k_obs"] = (tot.viirs_cd/tot.aqua_cd).round(3); tot["k_phys"] = (tot.viirs_cd/tot.pred_aqua_cd).round(3); tot["k_HT"] = (tot.viirs_cd/tot.aqua_ht).round(3)
print("\nT2/T3 yearly US totals:\n", tot.round(0).astype({"pred/actual_aqua": float, "k_obs": float, "k_phys": float, "k_HT": float}).to_string())
z = t[(t.aqua_cd >= 20)]
out["T2_pred_over_actual_aqua_by_region"] = z.groupby("region").apply(lambda q: round(q.pred_aqua_cd.sum()/q.aqua_cd.sum(), 3), include_groups=False).to_dict()
out["T2_corr_log_pred_vs_actual_regionmonth"] = round(float(np.corrcoef(np.log(z.pred_aqua_cd), np.log(z.aqua_cd))[0, 1]), 3)
out["T2_corr_log_k_obs_vs_k_phys"] = round(float(np.corrcoef(np.log(z.viirs_cd/z.aqua_cd), np.log(z.viirs_cd/z.pred_aqua_cd))[0, 1]), 3)
# T3: holdout ratio model on raw vs HT-weighted Aqua (train 2013-2020, test 2021-2025)
def holdout(col):
    tr, te = z[z.y <= 2020], z[z.y >= 2021]
    k = tr.groupby(["region", "m"]).apply(lambda q: q.viirs_cd.sum()/q[col].sum(), include_groups=False).rename("k").reset_index()
    e = te.merge(k, on=["region", "m"]); e["p"] = e.k*e[col]
    yr = e.groupby("y")[["p", "viirs_cd"]].sum()
    return {"region_month_median_abs_log_err": round(float(np.abs(np.log(e.p/e.viirs_cd)).median()), 3), "year_err": {int(a): round(float(b), 3) for a, b in (yr.p/yr.viirs_cd - 1).items()},
            "cv_of_ratio_across_years": round(float(z.groupby("y").apply(lambda q: q.viirs_cd.sum()/q[col].sum(), include_groups=False).pipe(lambda s: s.std()/s.mean())), 3)}
out["T3_raw_aqua"] = holdout("aqua_cd"); out["T3_HT_weighted_aqua"] = holdout("aqua_ht")
print(json.dumps({k: v for k, v in out.items() if k != "T1_DL_MW"}, indent=1))
json.dump(out, open("data/derived/us/obsop_metrics.json", "w"), indent=1)
