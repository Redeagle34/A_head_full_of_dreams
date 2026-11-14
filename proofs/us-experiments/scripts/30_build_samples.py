"""Build prediction samples (CONUS, 2014-2025).
Positives: NIFC WFIGS wildfire (WF) discoveries, deduplicated per 0.05deg cell-day. Local date = UTC + lon/15 h.
Negatives: uniform random points x random days over the CONUS bbox (non-CONUS/ocean dropped later when gridMET is null).
Experiment A: P(new reported wildfire | location-day)  -> case-control (all large fires + random subset of others, equal negatives).
Experiment B: P(final size >= 100 ac | a wildfire started) -> positives only, label from FinalAcres/IncidentSize.
Also attaches the leakage-free FIRMS climatology (harmonized MODIS 2003-2013 fire-cell-days per 0.25deg cell & month)."""
import pandas as pd, numpy as np, glob, pathlib
rng = np.random.default_rng(42); OUT = pathlib.Path("data/derived/pred"); OUT.mkdir(parents=True, exist_ok=True)
W = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob("data/raw/us_truth/wfigs_20*.parquet"))], ignore_index=True)
W = W[(W.IncidentTypeCategory == "WF") & ~W.POOState.isin(["US-AK", "US-HI", "US-PR", "US-GU", "US-VI"])]
W = W.dropna(subset=["InitialLatitude", "InitialLongitude", "FireDiscoveryDateTime"])
W = W[W.InitialLatitude.between(24.4, 49.5) & W.InitialLongitude.between(-125, -66.9)]
W["date"] = (W.FireDiscoveryDateTime + pd.to_timedelta(W.InitialLongitude / 15, unit="h")).dt.tz_localize(None).dt.date
W = W[(pd.to_datetime(W.date) >= "2014-01-01") & (pd.to_datetime(W.date) <= "2026-11-08")]
W["acres"] = W.FinalAcres.fillna(W.IncidentSize)
W["c005"] = (np.floor(W.InitialLatitude * 20)).astype(int) * 100000 + np.floor(W.InitialLongitude * 20).astype(int)
W = W.sort_values("acres", ascending=False).drop_duplicates(["c005", "date"])
print("WF CONUS 2014-2026 deduped:", len(W), "| with size:", W.acres.notna().mean().round(3), "| >=100ac:", (W.acres >= 100).sum(), "| >=1000ac:", (W.acres >= 1000).sum())
print(W.groupby(pd.to_datetime(W.date).dt.year).size().to_dict())
pos = W.rename(columns={"InitialLatitude": "lat", "InitialLongitude": "lon"})[["lat", "lon", "date", "acres", "FireCause", "POOState"]]
NPOS = 150_000
big = pos[pos.acres >= 100]; rest = pos.drop(big.index)
posA = pd.concat([big, rest.sample(min(len(rest), NPOS - len(big)), random_state=1)]); posA["y"] = 1
# negatives
n = int(len(posA) * 1.6)
days = pd.date_range("2014-01-01", "2026-11-08")
neg = pd.DataFrame({"lat": rng.uniform(24.4, 49.5, n), "lon": rng.uniform(-125, -66.9, n), "date": rng.choice(days, n)})
neg["date"] = pd.to_datetime(neg.date).dt.date; neg["y"] = 0
S = pd.concat([posA, neg], ignore_index=True); S["id"] = np.arange(len(S))
S["sample_weight_note"] = np.where(S.y == 1, "case", "background")
# FIRMS climatology (MODIS era 2003-2013, Terra+Aqua cell-days at 0.1deg, per 0.25deg cell & month) - strictly before label years
cd = pd.concat(pd.read_parquet(f) for f in glob.glob("data/derived/us/cd025_modis_*.parquet"))
cd = cd[cd.year.between(2003, 2013)].groupby(["c025", "month"]).celldays01.sum().div(11).rename("firms_clim_month").reset_index()
ann = cd.groupby("c025").firms_clim_month.sum().rename("firms_clim_year").reset_index()
S["c025"] = np.floor(S.lat * 4).astype(int) * 10000 + np.floor(S.lon * 4).astype(int); S["month"] = pd.to_datetime(S.date).dt.month
S = S.merge(cd, on=["c025", "month"], how="left").merge(ann, on="c025", how="left").fillna({"firms_clim_month": 0, "firms_clim_year": 0})
S.to_parquet(OUT / "samples.parquet")
print("samples:", len(S), S.y.value_counts().to_dict())
