"""How much do the models lose when today's weather is not available? Same table, same split as 33_save_models.py.
'yesterday' = only inputs known the evening before (day-before values, 7- and 30-day summaries), plus place and season."""
import pandas as pd, json, lightgbm as lgb
from sklearn.metrics import roc_auc_score, average_precision_score
D = pd.read_parquet("data/derived/pred/models/training_table.parquet")
for c in ("frg", "lc"): D[c] = D[c].astype("category")
TODAY = ["erc", "bi", "fm100", "fm1000", "vpd", "vs", "rmin", "rmax", "tmmx", "pr", "srad"]; YEST = ["erc_l1", "fm100_l1", "vpd_l1", "vs_l1", "erc7", "pr30", "erc_max30"]
PLACE = ["doy", "elevation", "slope", "log_pop", "frg", "mfri", "lc", "treecover", "log_clim_m", "log_clim_y"]
SETS = {"today_and_yesterday": TODAY + YEST + PLACE, "yesterday_only": YEST + PLACE, "slow_only_30day": ["pr30", "erc_max30", "erc7"] + PLACE, "place_and_season_only": PLACE}
P = dict(n_estimators=600, learning_rate=0.05, num_leaves=63, min_child_samples=50, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
def run(d, label):
    tr, va, te = d[d.year <= 2020], d[d.year == 2021], d[d.year >= 2022]; out = {}
    for name, f in SETS.items():
        m = lgb.LGBMClassifier(**P).fit(tr[f], tr[label], eval_set=[(va[f], va[label])], callbacks=[lgb.early_stopping(50, verbose=False)])
        p = m.predict_proba(te[f])[:, 1]; out[name] = {"AUC": round(roc_auc_score(te[label], p), 3), "PR_AUC": round(average_precision_score(te[label], p), 3)}
    return out
R = {"A_ignition": run(D, "y")}
B = D[(D.y == 1) & D.acres.notna()].copy(); B["big100"] = (B.acres >= 100).astype(int); B["big1000"] = (B.acres >= 1000).astype(int)
R["B_large100"] = run(B, "big100"); R["B_large1000"] = run(B, "big1000")
json.dump(R, open("data/derived/pred/lagged_weather_test.json", "w"), indent=1); print(json.dumps(R, indent=1))
