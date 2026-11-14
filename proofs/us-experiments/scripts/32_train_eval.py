"""Experiments A (ignition) and B (large-fire given ignition). CONUS, NIFC WFIGS labels, gridMET+static+FIRMS-climatology features.
Honest evaluation: temporal holdout (train 2014-2021 / test 2022-2026) and leave-one-region-out. Baselines = single fire-danger indices."""
import pandas as pd, numpy as np, json, glob, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import lightgbm as lgb, shap
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.tree import DecisionTreeRegressor, export_text
S = pd.read_parquet("data/derived/pred/samples.parquet")
F = pd.DataFrame([r for f in sorted(glob.glob("data/raw/gee_features/chunk_*.json")) for r in json.load(open(f))])
D = S.merge(F, on="id", how="inner"); D["year"] = pd.to_datetime(D.date).dt.year; D["doy"] = pd.to_datetime(D.date).dt.dayofyear
D["region"] = np.where(D.lon < -104, "West", np.where(D.lon < -90, "Central", "East"))
D["log_pop"] = np.log1p(D.pop_density); D["log_clim_m"] = np.log1p(D.firms_clim_month); D["log_clim_y"] = np.log1p(D.firms_clim_year)
WEATHER = ["erc", "bi", "fm100", "fm1000", "vpd", "vs", "rmin", "rmax", "tmmx", "pr", "srad", "erc_l1", "fm100_l1", "vpd_l1", "vs_l1", "erc7", "pr30", "erc_max30"]
STATIC = ["elevation", "slope", "log_pop", "frg", "mfri", "lc", "treecover"]
CLIM = ["log_clim_m", "log_clim_y"]; SEAS = ["doy"]
CAT = ["frg", "lc"]
for c in CAT: D[c] = D[c].astype("category")
R = {"n_samples": int(len(D)), "class_counts": D.y.value_counts().to_dict(), "dropped_no_features": int(len(S) - len(D))}
print("joined", R)
def fit(Xtr, ytr, Xva=None, yva=None, w=None):
    m = lgb.LGBMClassifier(n_estimators=600, learning_rate=0.05, num_leaves=63, min_child_samples=50, subsample=0.8, subsample_freq=1,
                           colsample_bytree=0.8, verbose=-1)
    if Xva is not None: m.fit(Xtr, ytr, eval_set=[(Xva, yva)], callbacks=[lgb.early_stopping(50, verbose=False)])
    else: m.fit(Xtr, ytr)
    return m
def evaluate(name, d, label, feats_sets, tr_mask, te_mask, baselines):
    out = {}
    te = d[te_mask]; tr = d[tr_mask]
    for b, sign in baselines.items():
        out[f"baseline_{b}"] = round(roc_auc_score(te[label], sign * te[b]), 3)
    for fs_name, feats in feats_sets.items():
        va = tr[tr.year == tr.year.max()]; trn = tr[tr.year < tr.year.max()]
        m = fit(trn[feats], trn[label], va[feats], va[label])
        p = m.predict_proba(te[feats])[:, 1]
        out[f"lgbm_{fs_name}"] = {"AUC": round(roc_auc_score(te[label], p), 3), "PR_AUC": round(average_precision_score(te[label], p), 3)}
        if fs_name == "all": best = (m, feats, p)
    out["test_base_rate"] = round(float(te[label].mean()), 4)
    return out, best
FS = {"weather_only": WEATHER + SEAS, "static_only": STATIC, "clim_only": CLIM, "all_minus_clim": WEATHER + SEAS + STATIC, "all": WEATHER + SEAS + STATIC + CLIM}
BASE_A = {"erc": 1, "bi": 1, "vpd": 1, "fm100": -1, "log_pop": 1, "log_clim_m": 1}
# ---------- Experiment A ----------
A, (mA, fA, pA) = evaluate("A", D, "y", FS, D.year <= 2021, D.year >= 2022, BASE_A)
R["A_temporal"] = A; print("A temporal:", json.dumps(A, indent=1))
teA = D[D.year >= 2022].assign(p=pA)
R["A_temporal_by_region_AUC"] = {r: round(roc_auc_score(g.y, g.p), 3) for r, g in teA.groupby("region")}
# leave-one-region-out (global model trained on other regions) vs regional model (Shmuel-style regional calibration)
lro = {}
for r in ["West", "Central", "East"]:
    tr = D[(D.region != r) & (D.year <= 2021)]; te = D[(D.region == r) & (D.year >= 2022)]
    mg = fit(tr[fA], tr.y); trr = D[(D.region == r) & (D.year <= 2021)]; mr = fit(trr[fA], trr.y)
    lro[r] = {"global_other_regions_AUC": round(roc_auc_score(te.y, mg.predict_proba(te[fA])[:, 1]), 3),
              "regional_model_AUC": round(roc_auc_score(te.y, mr.predict_proba(te[fA])[:, 1]), 3),
              "erc_only_AUC": round(roc_auc_score(te.y, te.erc), 3)}
R["A_region_transfer"] = lro; print("A region transfer:", lro)
# distilled explainable tree (depth 3 and 5) on LightGBM logit
trA = D[D.year <= 2021]; logit = mA.predict(trA[fA], raw_score=True)
num = [f for f in fA if f not in CAT]
for depth in [3, 5]:
    t = DecisionTreeRegressor(max_depth=depth, min_samples_leaf=500).fit(trA[num], logit)
    R[f"A_tree_depth{depth}_AUC"] = round(roc_auc_score(teA.y, t.predict(teA[num])), 3)
    if depth == 3: R["A_tree_depth3_rules"] = export_text(t, feature_names=num, decimals=1)
print(R["A_tree_depth3_rules"]); print("tree AUCs", R["A_tree_depth3_AUC"], R["A_tree_depth5_AUC"])
sv = shap.TreeExplainer(mA).shap_values(teA[fA].sample(4000, random_state=0))
sv = sv[1] if isinstance(sv, list) else sv
imp = pd.Series(np.abs(sv).mean(0), index=fA).sort_values(ascending=False); R["A_shap_mean_abs"] = imp.round(4).to_dict()
# ---------- Experiment B ----------
P = D[(D.y == 1) & D.acres.notna()].copy()
for thr in [100, 1000]:
    P[f"big{thr}"] = (P.acres >= thr).astype(int)
    out, (mB, fB, pB) = evaluate("B", P, f"big{thr}", {"weather_only": WEATHER + SEAS, "all_minus_clim": WEATHER + SEAS + STATIC, "all": WEATHER + SEAS + STATIC + CLIM},
                                 P.year <= 2021, P.year >= 2022, {"erc": 1, "bi": 1, "vpd": 1, "fm1000": -1, "log_pop": -1, "log_clim_m": 1})
    R[f"B_large_ge{thr}ac"] = out; print(f"B >= {thr}:", json.dumps(out, indent=1))
    if thr == 100:
        sv = shap.TreeExplainer(mB).shap_values(P[P.year >= 2022][fB].sample(min(4000, (P.year >= 2022).sum()), random_state=0)); sv = sv[1] if isinstance(sv, list) else sv
        R["B100_shap_mean_abs"] = pd.Series(np.abs(sv).mean(0), index=fB).sort_values(ascending=False).round(4).to_dict()
R["B_label_rates"] = {"n_ignitions_with_size": int(len(P)), "share_ge100": round(float(P.big100.mean()), 4), "share_ge1000": round(float(P.big1000.mean()), 4)}
json.dump(R, open("data/derived/pred/results.json", "w"), indent=1, default=str)
fig, ax = plt.subplots(1, 2, figsize=(13, 5))
pd.Series(R["A_shap_mean_abs"]).head(15)[::-1].plot.barh(ax=ax[0], title="A: what drives ignition risk (mean |SHAP|)")
pd.Series(R["B100_shap_mean_abs"]).head(15)[::-1].plot.barh(ax=ax[1], title="B: what drives a fire to exceed 100 acres")
plt.tight_layout(); plt.savefig("outputs/pred_shap_A_B.png", dpi=130)
print("SHAP A top:", list(R["A_shap_mean_abs"])[:8]); print("SHAP B top:", list(R["B100_shap_mean_abs"])[:8])
