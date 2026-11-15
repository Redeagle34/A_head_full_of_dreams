"""Compare MODIS->VIIRS conversion models on US region-months. Train 2013-2020, test 2021-2025 (and backward: train 2016-2020 -> test 2013-2015).
M0 ratio of totals per region x month (SHIFT-style, no shrinkage needed at this scale)
M1 power law: log V = a[region,moy] + b*log M  (activity-dependent ratio; zero stays zero)
M2 M1 + c*log(mean MODIS FRP per detection) + d*(share of MODIS detections that are night)  (observable-in-MODIS-era proxies of fire-size mix)
Target: SNPP 0.1deg fire-cell-days; predictor: Aqua (same overpass)."""
import pandas as pd, numpy as np, glob, json
from sklearn.linear_model import LinearRegression
d = pd.concat(pd.read_parquet(f) for f in glob.glob("data/derived/us/agg_*.parquet"))
k = d[(d["filter"] == "keep") & (d.region != "Hawaii")].copy(); k["ym"] = k.date.dt.to_period("M")
g = k.groupby(["ym", "region", "sat"]).agg(c=("n_c01", "sum"), n=("n_det", "sum"), frp=("frp_sum", "sum")).reset_index()
night = k[k.daynight == "N"].groupby(["ym", "region", "sat"]).n_det.sum().rename("nn")
g = g.merge(night, on=["ym", "region", "sat"], how="left").fillna({"nn": 0})
A = g[g.sat == "Aqua"].set_index(["ym", "region"]); V = g[g.sat == "SNPP"].set_index(["ym", "region"])
D = pd.DataFrame({"M": A.c, "V": V.c, "mfrp": A.frp / A.n, "night": A.nn / A.n}).dropna().reset_index()
D = D[(D.M >= 5) & (D.V >= 5) & (D.ym >= pd.Period("2012-03", "M"))]
D["y"] = D.ym.dt.year; D["moy"] = D.ym.dt.month; D["lM"] = np.log(D.M); D["lV"] = np.log(D.V); D["lF"] = np.log(D.mfrp)
def design(x, feats):
    X = pd.get_dummies(x.region + "_" + x.moy.astype(str)).astype(float)
    for f in feats: X[f] = x[f].values
    return X
def run(tr, te):
    res = {}
    r = tr.groupby(["region", "moy"]).apply(lambda z: z.V.sum() / z.M.sum(), include_groups=False).rename("k").reset_index()
    p0 = te.merge(r, on=["region", "moy"], how="left"); res["M0_ratio"] = (p0.M * p0.k).values
    for name, feats in {"M1_powerlaw": ["lM"], "M2_powerlaw+frp+night": ["lM", "lF", "night"]}.items():
        Xtr = design(tr, feats); Xte = design(te, feats).reindex(columns=Xtr.columns, fill_value=0)
        # fit residual model: lV - lM = a + (b-1) lM + ...
        m = LinearRegression().fit(Xtr, tr.lV - tr.lM, sample_weight=tr.V)
        res[name] = np.exp(m.predict(Xte) + te.lM.values); res[name + "_coef"] = dict(zip(feats, np.round(m.coef_[-len(feats):], 3)))
    out = {}
    for kk, p in res.items():
        if kk.endswith("_coef"): out[kk] = {a: float(b) for a, b in p.items()}; continue
        t = te.assign(p=p)
        rm = (np.abs(np.log(t.p / t.V))).median()                        # region-month median |log error|
        us = t.groupby("ym")[["p", "V"]].sum(); usm = (np.abs(us.p / us.V - 1)).median()
        yr = t.groupby("y")[["p", "V"]].sum(); yre = ((yr.p / yr.V - 1)).round(3).to_dict()
        out[kk] = {"region_month_median_abs_log_err": round(float(rm), 3), "US_month_MAPE": round(float(usm), 3), "US_year_err": {int(a): b for a, b in yre.items()}}
    return out
R = {"forward_train2013-20_test2021-25": run(D[D.y.between(2013, 2020)], D[D.y >= 2021]),
     "backward_train2016-20_test2013-15": run(D[D.y.between(2016, 2020)], D[D.y.between(2013, 2015)])}
print(json.dumps(R, indent=1)); json.dump(R, open("data/derived/us/conversion_models.json", "w"), indent=1)
