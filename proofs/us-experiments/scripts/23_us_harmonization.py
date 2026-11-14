"""Experiment C (US): naive jump, per-sensor ratios, gridding effect, calibration with holdout, drift, FRP."""
import pandas as pd, numpy as np, glob, json, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
O = "outputs/"; M = {}
d = pd.concat(pd.read_parquet(f) for f in glob.glob("data/derived/us/agg_*.parquet"))
k = d[d["filter"] == "keep"].copy(); k["ym"] = k.date.dt.to_period("M")
mon = k.groupby(["ym", "sat", "region"])[["n_det", "n_c01", "n_c001"]].sum().reset_index()
us = mon.groupby(["ym", "sat"])[["n_det", "n_c01", "n_c001"]].sum().reset_index()
piv = {m: us.pivot(index="ym", columns="sat", values=m).fillna(0) for m in ["n_det", "n_c01", "n_c001"]}
X = piv["n_det"].index.to_timestamp()

# 1 naive stacked
fig, ax = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
naive = piv["n_det"].sum(1)
ax[0].plot(X, naive.values, color="k", lw=1); ax[0].set_title("Naive: all FIRMS detections stacked (US, monthly) — fake jump when VIIRS arrives")
ax[0].axvline(pd.Timestamp("2012-01-20"), color="r", ls="--"); ax[0].axvline(pd.Timestamp("2018-04-01"), color="r", ls=":")
for s, c in zip(["Terra", "Aqua", "SNPP", "NOAA20"], ["tab:orange", "tab:blue", "tab:green", "tab:purple"]):
    ax[1].plot(X, piv["n_c01"][s].replace(0, np.nan).values, label=s, color=c, lw=1)
ax[1].set_title("Per satellite: fire-cell-days at 0.1° (vegetation fires, confidence-filtered)"); ax[1].legend(); ax[1].set_yscale("log")
plt.tight_layout(); plt.savefig(O + "us_C1_naive_vs_per_sensor.png", dpi=130); plt.close()
yr = naive.groupby(naive.index.year).sum(); M["naive_annual"] = {int(a): int(b) for a, b in yr.items()}
M["naive_jump_2011_to_2013"] = round(yr[2013] / yr[2011], 2)

# 2 ratio SNPP/Aqua by unit (overlap, full months)
ov = (X >= "2012-03-01")
res = {}
fig, ax = plt.subplots(figsize=(12, 4))
for m, c in zip(["n_det", "n_c001", "n_c01"], ["k", "tab:red", "tab:blue"]):
    r = (piv[m]["SNPP"] / piv[m]["Aqua"].replace(0, np.nan))[ov]
    res[m] = {"median": round(float(r.median()), 2), "cv": round(float(r.std() / r.mean()), 2), "p10": round(float(r.quantile(.1)), 2), "p90": round(float(r.quantile(.9)), 2)}
    ax.plot(X[ov], r.values, color=c, lw=1, label=f"{m}: median {res[m]['median']}, CV {res[m]['cv']}")
ax.set_yscale("log"); ax.set_title("VIIRS SNPP / Aqua MODIS monthly ratio (same ~13:30/01:30 overpass) by counting unit"); ax.legend()
plt.tight_layout(); plt.savefig(O + "us_C2_ratio_by_unit.png", dpi=130); plt.close()
M["snpp_over_aqua_ratio"] = res
M["n20_over_snpp_c01"] = round(float((piv["n_c01"]["NOAA20"] / piv["n_c01"]["SNPP"].replace(0, np.nan))[X >= "2018-05-01"].median()), 2)
M["terra_over_aqua_c01"] = round(float((piv["n_c01"]["Terra"] / piv["n_c01"]["Aqua"].replace(0, np.nan))[X >= "2003-01-01"].median()), 2)

# 3 calibration: predict SNPP c01 from Aqua c01; train 2013-2020, test 2021-2025
mr = mon.pivot_table(index=["ym", "region"], columns="sat", values="n_c01", fill_value=0).reset_index()
mr["moy"] = mr.ym.dt.month; mr["y"] = mr.ym.dt.year
tr = mr[(mr.y >= 2013) & (mr.y <= 2020)]; te = mr[mr.y >= 2021]
def fit(keys):
    g = tr.groupby(keys).apply(lambda x: x.SNPP.sum() / max(x.Aqua.sum(), 1), include_groups=False).rename("ratio")
    return g
cal = {}
for name, keys in {"single": None, "region": ["region"], "region_x_month": ["region", "moy"]}.items():
    if keys is None: pred = te.Aqua * tr.SNPP.sum() / tr.Aqua.sum()
    else: pred = te.Aqua * te.merge(fit(keys).reset_index(), on=keys, how="left").ratio.values
    tot = te.assign(p=pred.values if hasattr(pred, "values") else pred).groupby("ym")[["SNPP", "p"]].sum()
    ape = (tot.p - tot.SNPP).abs() / tot.SNPP
    cal[name] = {"US_monthly_MAPE": round(float(ape.median()), 3), "US_annual_err": {int(a): round(float(b), 3) for a, b in
                  (tot.groupby(tot.index.year).sum().pipe(lambda t: (t.p - t.SNPP) / t.SNPP)).items()},
                 "corr": round(float(np.corrcoef(tot.p, tot.SNPP)[0, 1]), 3)}
M["calibration_holdout_2021_2025"] = cal
rt = fit(["region", "moy"]).reset_index()
fig, ax = plt.subplots(figsize=(9, 4))
for r_, g in rt.groupby("region"): ax.plot(g.moy, g.ratio, marker="o", label=r_)
ax.set_title("SNPP/Aqua ratio (0.1° fire-cell-days) by region & month, fit 2013–2020"); ax.set_xlabel("month"); ax.legend()
plt.tight_layout(); plt.savefig(O + "us_C3_ratio_region_month.png", dpi=130); plt.close()
M["ratio_region_month"] = {f"{a}-{b}": round(c, 2) for a, b, c in rt.itertuples(index=False)}

# 4 harmonized series (VIIRS-SNPP-equivalent fire-cell-days); MODIS era: Aqua scaled; before Aqua (2000-07/2002): Terra scaled
mr["harm"] = np.nan
f = fit(["region", "moy"]).reset_index()
mr = mr.merge(f, on=["region", "moy"], how="left")
ta = tr.groupby(["region", "moy"]).apply(lambda x: x.SNPP.sum() / max(x.Terra.sum(), 1), include_groups=False).rename("rt").reset_index()
mr = mr.merge(ta, on=["region", "moy"], how="left")
mr["harm"] = np.where(mr.ym >= pd.Period("2012-02", "M"), mr.SNPP, np.where(mr.Aqua > 0, mr.Aqua * mr.ratio, mr.Terra * mr.rt))
H = mr.groupby("ym").harm.sum(); H.index = H.index.to_timestamp()
H.to_frame("harmonized_viirs_equiv_celldays").to_csv("data/derived/us/harmonized_monthly_us.csv")
med = H.groupby(H.index.month).transform("median"); anom = (H - med) / med
fig, ax = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
ax[0].plot(X, (naive / naive[X >= "2013"].mean()).values, color="0.6", lw=1, label="naive detections (scaled)")
ax[0].plot(H.index, (H / H[H.index >= "2013"].mean()).values, color="tab:red", lw=1.3, label="harmonized (VIIRS-equivalent fire-cell-days)")
ax[0].axvline(pd.Timestamp("2012-01-20"), color="k", ls="--"); ax[0].legend(); ax[0].set_title("US monthly burning activity: naive vs harmonized")
ax[1].bar(anom.index, anom.values, width=25, color=np.where(anom > 0, "tab:red", "tab:blue")); ax[1].set_title("Anomaly vs median of same calendar month (2000–2025)")
plt.tight_layout(); plt.savefig(O + "us_C4_harmonized_and_anomaly.png", dpi=130); plt.close()
hy = H.groupby(H.index.year).sum(); M["harmonized_annual"] = {int(a): int(b) for a, b in hy.items()}
M["harm_jump_2011_to_2013"] = round(hy[2013] / hy[2011], 2)

# 5 overpass drift + FRP
ds = pd.concat(pd.read_parquet(f) for f in glob.glob("data/derived/us/dist_*.parquet"))
fig, ax = plt.subplots(1, 2, figsize=(13, 4))
for (s, dn), g in ds.groupby(["sat", "daynight"]):
    g = g.sort_values("year"); ax[0].plot(g.year, g.lst_median, marker=".", label=f"{s} {dn}")
ax[0].set_title("Median local solar time of US detections (orbit drift)"); ax[0].legend(fontsize=7, ncol=2)
q = ds[ds.year >= 2019].groupby(["sat", "daynight"]).frp_q.apply(lambda s: np.median(np.vstack(s), 0))
for (s, dn), v in q.items(): ax[1].plot([10, 25, 50, 75, 90, 99], v, marker="o", label=f"{s} {dn}")
ax[1].set_yscale("log"); ax[1].set_xlabel("percentile"); ax[1].set_ylabel("FRP (MW)"); ax[1].set_title("FRP distribution per sensor (2019–2025)"); ax[1].legend(fontsize=7, ncol=2)
plt.tight_layout(); plt.savefig(O + "us_C5_drift_frp.png", dpi=130); plt.close()
M["lst_median_day"] = {s: {int(y): round(v, 2) for y, v in g[["year", "lst_median"]].values} for s, g in ds[ds.daynight == "D"].groupby("sat")}
M["frp_quantiles_2019_2025"] = {f"{a}_{b}": [round(x, 1) for x in v] for (a, b), v in q.items()}
json.dump(M, open("data/derived/us/harmonization_metrics.json", "w"), indent=1, default=str)
print(json.dumps({k: v for k, v in M.items() if k not in ("ratio_region_month", "naive_annual", "harmonized_annual")}, indent=1, default=str))
