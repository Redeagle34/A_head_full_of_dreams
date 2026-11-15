"""Train the three models exactly as evaluated in 32_train_eval.py and save them with their training table and metadata.
Outputs (data/derived/pred/models/): training_table.parquet, model_A_ignition.txt, model_B_large100.txt, model_B_large1000.txt, models_meta.json"""
import pandas as pd, numpy as np, json, glob, pathlib, lightgbm as lgb, sklearn
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
OUT = pathlib.Path("data/derived/pred/models"); OUT.mkdir(parents=True, exist_ok=True)
S = pd.read_parquet("data/derived/pred/samples.parquet")
F = pd.DataFrame([r for f in sorted(glob.glob("data/raw/gee_features/chunk_*.json")) for r in json.load(open(f))])
D = S.merge(F, on="id", how="inner"); D["year"] = pd.to_datetime(D.date).dt.year; D["doy"] = pd.to_datetime(D.date).dt.dayofyear
D["region"] = np.where(D.lon < -104, "West", np.where(D.lon < -90, "Central", "East"))
D["log_pop"] = np.log1p(D.pop_density); D["log_clim_m"] = np.log1p(D.firms_clim_month); D["log_clim_y"] = np.log1p(D.firms_clim_year)
WEATHER = ["erc", "bi", "fm100", "fm1000", "vpd", "vs", "rmin", "rmax", "tmmx", "pr", "srad", "erc_l1", "fm100_l1", "vpd_l1", "vs_l1", "erc7", "pr30", "erc_max30"]
STATIC = ["elevation", "slope", "log_pop", "frg", "mfri", "lc", "treecover"]; CLIM = ["log_clim_m", "log_clim_y"]
FEATS = WEATHER + ["doy"] + STATIC + CLIM; CAT = ["frg", "lc"]
D.drop(columns=[c for c in D.columns if D[c].dtype == object and c not in ("date", "region", "id")], errors="ignore").to_parquet(OUT / "training_table.parquet", index=False)
print("table", D.shape, list(D.columns))
for c in CAT: D[c] = D[c].astype("category")
PARAMS = dict(n_estimators=600, learning_rate=0.05, num_leaves=63, min_child_samples=50, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
def train(d, label, name):
    tr = d[d.year <= 2020]; va = d[d.year == 2021]; te = d[d.year >= 2022]
    m = lgb.LGBMClassifier(**PARAMS).fit(tr[FEATS], tr[label], eval_set=[(va[FEATS], va[label])], callbacks=[lgb.early_stopping(50, verbose=False)])
    p = m.predict_proba(te[FEATS])[:, 1]; y = te[label].values
    q = pd.qcut(p, 10, duplicates="drop"); rel = pd.DataFrame({"p": p, "y": y}).groupby(q, observed=True).agg(mean_score=("p", "mean"), observed_rate=("y", "mean"), n=("y", "size")).round(4)
    m.booster_.save_model(str(OUT / f"{name}.txt"))
    b = lgb.Booster(model_file=str(OUT / f"{name}.txt")); assert np.allclose(b.predict(te[FEATS]), p, atol=1e-9)   # saved file reproduces the scores
    return {"file": f"{name}.txt", "label": label, "features": FEATS, "categorical": CAT, "params": PARAMS, "trees_used": int(m.best_iteration_),
            "train": {"years": "2014-2020", "n": int(len(tr)), "positives": int(tr[label].sum())},
            "validation_early_stopping": {"years": "2021", "n": int(len(va)), "positives": int(va[label].sum())},
            "test": {"years": f"2022-{int(te.year.max())}", "n": int(len(te)), "positives": int(y.sum()), "base_rate": round(float(y.mean()), 4),
                     "AUC": round(roc_auc_score(y, p), 3), "PR_AUC": round(average_precision_score(y, p), 3), "Brier": round(brier_score_loss(y, p), 4),
                     "Brier_of_constant_base_rate": round(float(y.mean() * (1 - y.mean())), 4),
                     "AUC_by_region": {r: round(roc_auc_score(g[label], g.p), 3) for r, g in te.assign(p=p).groupby("region") if g[label].nunique() > 1},
                     "reliability_deciles": rel.reset_index(drop=True).to_dict("records")}}
M = {"date_range_samples": [str(D.date.min()), str(D.date.max())], "years": D.year.value_counts().sort_index().to_dict(),
     "versions": {"lightgbm": lgb.__version__, "sklearn": sklearn.__version__, "pandas": pd.__version__, "numpy": np.__version__}}
M["A_ignition"] = train(D, "y", "model_A_ignition")
P = D[(D.y == 1) & D.acres.notna()].copy()
for thr in (100, 1000):
    P[f"big{thr}"] = (P.acres >= thr).astype(int); M[f"B_large{thr}"] = train(P, f"big{thr}", f"model_B_large{thr}")
M["B_sampling"] = {"positives_with_size_in_table": int(len(P)), "share_ge100_in_table": round(float(P.big100.mean()), 4), "share_ge1000_in_table": round(float(P.big1000.mean()), 4)}
json.dump(M, open(OUT / "models_meta.json", "w"), indent=1, default=str)
for k in ("A_ignition", "B_large100", "B_large1000"): print(k, json.dumps({a: M[k][a] for a in ("trees_used", "train", "validation_early_stopping")}), json.dumps(M[k]["test"], indent=0)[:1500])
print(M["years"], M["B_sampling"], M["versions"])
