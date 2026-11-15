"""Train the fire danger model and rate every fire.

Run:  python pipeline/danger_model.py     (after danger_fires.py, danger_inputs.py and build_db.py;
                                           stop the web server first, the database is written to)
Output: data/events/event_danger.parquet   the rating of every fire event that has VIIRS detections
        table `danger_levels` in data/fire.duckdb   what each level meant on the test years
        data/danger/model_large100.txt, model_large1000.txt, metrics.json

A fire is a fire event of pipeline/fire_events.py; the model is trained on those same fires.

Question the model answers, for a fire the satellites have watched for two days:
  will its footprint reach 100 acres? 1,000 acres?
A fire that is already that large at the end of day 2 gets probability 1.

Inputs: what the satellites saw on day 1 and day 2 (detections, radiative power, footprint,
growth, night burning), the weather of the first day and the weeks before, and the place
(terrain, vegetation, fire regime, population). See pipeline/danger_inputs.py.

Years: trained on 2012-2020, tuned on 2021, every reported score is from 2022-2025.

The five danger levels are cut on the calibrated chance of reaching 1,000 acres. What a level
means is measured on 2022-2025 and stored in `danger_levels`.

The size is the satellite footprint, not a surveyed perimeter. The check against agency
reports (reference table in proofs/us-experiments/models) is printed at the end.
"""
import json
import pathlib
import sys

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.fires import COLUMNS as RATING_COLUMNS, LEVELS, LEVEL_STARTS      # noqa: E402

DANGER = ROOT / "data" / "danger"
REFERENCE = ROOT / "proofs" / "us-experiments" / "models"
DB = ROOT / "data" / "fire.duckdb"
CELL = 0.04                                         # must equal danger_inputs.CELL

SATELLITE = ["d1_detections", "d1_frp", "d1_frp_max", "d1_acres", "d1_night_share",
             "d2_detections", "d2_frp", "d2_new_acres", "growth"]
WEATHER = ["erc", "bi", "fm100", "fm1000", "vpd", "vs", "rmin", "rmax", "tmmx", "pr", "srad",
           "erc_l1", "fm100_l1", "vpd_l1", "vs_l1", "erc7", "pr30", "erc_max30", "doy"]
PLACE = ["elevation", "slope", "log_pop", "frg", "mfri", "lc", "treecover"]
FEATURES = SATELLITE + WEATHER + PLACE
CATEGORICAL = ["frg", "lc"]
PARAMS = dict(n_estimators=600, learning_rate=0.05, num_leaves=63, min_child_samples=50, subsample=0.8,
              subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=1)
TRAIN_TO, VALIDATION, TEST_FROM = 2020, 2021, 2022
SIZES = (100, 1000)                                 # acres



def load():
    p = lambda name: f"'{(DANGER / name).as_posix()}'"      # noqa: E731
    con = duckdb.connect()
    table = con.execute(f"""
        SELECT f.*, w.* EXCLUDE (key, day), pl.* EXCLUDE (key)
        FROM {p('fires.parquet')} f
        LEFT JOIN {p('inputs_place.parquet')} pl
          ON pl.key = floor(f.start_lat / {CELL})::INT || '_' || floor(f.start_lon / {CELL})::INT
        LEFT JOIN {p('inputs_weather.parquet')} w ON w.key = pl.key AND w.day::DATE = f.first_day
    """).df()
    table["year"] = pd.to_datetime(table.first_day).dt.year
    table["doy"] = pd.to_datetime(table.first_day).dt.dayofyear
    table["log_pop"] = np.log1p(table.pop_density)
    table["growth"] = table.d2_new_acres / table.d1_acres
    table["acres_day2"] = table.d1_acres + table.d2_new_acres
    for column in CATEGORICAL:
        table[column] = table[column].astype("category")
    table["rated"] = (table.state != "HI") & table.erc.notna()     # Hawaii: lava is recorded as fire
    return table


def fit(rows, label, features=FEATURES):
    train, validation = rows[rows.year <= TRAIN_TO], rows[rows.year == VALIDATION]
    model = lgb.LGBMClassifier(**PARAMS).fit(
        train[features], train[label], eval_set=[(validation[features], validation[label])],
        callbacks=[lgb.early_stopping(50, verbose=False)])
    return model


def score(y, p):
    return {"n": int(len(y)), "positives": int(y.sum()), "auc": round(roc_auc_score(y, p), 3),
            "pr_auc": round(average_precision_score(y, p), 3)}


def train(table, metrics):
    """Adds p100 and p1000 (calibrated) to the table."""
    for size in SIZES:
        label = f"large{size}"
        table[label] = (table.acres >= size).astype(int)
        open_rows = table[table.rated & (table.acres_day2 < size)]        # not that large yet
        model = fit(open_rows, label)
        model.booster_.save_model(str(DANGER / f"model_{label}.txt"))
        raw = pd.Series(model.predict_proba(open_rows[FEATURES])[:, 1], index=open_rows.index)
        validation = open_rows.year == VALIDATION
        calibrate = IsotonicRegression(out_of_bounds="clip").fit(raw[validation], open_rows[label][validation])
        table[f"p{size}"] = np.where(table.rated, 1.0, np.nan)
        table.loc[open_rows.index, f"p{size}"] = calibrate.predict(raw)

        test = open_rows[open_rows.year >= TEST_FROM]
        result = {"trees": int(model.best_iteration_), "test_not_yet_large": score(test[label], raw[test.index])}
        for name, features in {"satellite_only": SATELLITE, "weather_and_place_only": WEATHER + PLACE}.items():
            other = fit(open_rows, label, features)
            result[f"test_{name}"] = score(test[label], other.predict_proba(test[features])[:, 1])
        result["test_day1_footprint_alone"] = score(test[label], test.d1_acres)
        all_test = table[table.rated & (table.year >= TEST_FROM)]
        result["test_all_fires"] = score(all_test[label], all_test[f"p{size}"])
        gain = pd.Series(model.booster_.feature_importance("gain"), index=FEATURES).sort_values(ascending=False)
        result["strongest_inputs"] = list(gain.index[:8])
        metrics[label] = result
        print(label, json.dumps(result))


def levels(table, metrics):
    """Adds `level` (0-4, empty when not rated) and returns the table of what each level means."""
    table["level"] = np.where(table.rated, np.searchsorted(LEVEL_STARTS, table.p1000.fillna(0), side="right"), np.nan)
    test = table[table.rated & (table.year >= TEST_FROM)]
    meaning = test.groupby("level").agg(fires=("fire_id", "size"), reached_100=("large100", "mean"),
                                        reached_1000=("large1000", "mean"),
                                        median_acres=("acres", "median")).reset_index()
    meaning["level"] = meaning.level.astype(int)
    meaning["name"] = [LEVELS[i] for i in meaning.level]
    meaning["share_of_large_fires"] = (test.groupby("level").large1000.sum() / test.large1000.sum()).values
    # Higher level, more fires that got large: the levels must be in order on unseen years.
    assert meaning.reached_1000.is_monotonic_increasing, meaning
    assert meaning.reached_100.is_monotonic_increasing, meaning
    metrics["levels_on_test_years"] = json.loads(meaning.round(4).to_json(orient="records"))
    print(meaning.round(3).to_string(index=False))
    return meaning


def compare_with_reports(table, metrics):
    """Agency reports with a final size (reference table): does the rating rank the reported size?"""
    reference = REFERENCE / "training_table.parquet"
    if not reference.exists():
        print("reference table missing, comparison with agency reports skipped")
        return
    con = duckdb.connect()
    fires = table[table.rated][["fire_id", "first_day", "last_day", "west", "south", "east", "north",       # noqa: F841
                                "acres", "p100", "p1000", "year"]]
    matched = con.execute(f"""
        WITH report AS (SELECT id, lat, lon, date::DATE AS day, acres FROM '{reference.as_posix()}'
                        WHERE y = 1 AND acres IS NOT NULL),
        tile AS (SELECT f.*, unnest(range(floor((south - 0.03) * 10)::INT, floor((north + 0.03) * 10)::INT + 1)) AS ty
                 FROM fires f),
        tiles AS (SELECT *, unnest(range(floor((west - 0.04) * 10)::INT, floor((east + 0.04) * 10)::INT + 1)) AS tx
                  FROM tile),
        pair AS (SELECT r.id, r.acres AS reported, t.fire_id, t.acres, t.p100, t.p1000, t.year
                 FROM report r JOIN tiles t ON t.ty = floor(r.lat * 10)::INT AND t.tx = floor(r.lon * 10)::INT
                 WHERE r.day BETWEEN t.first_day::DATE - 1 AND t.last_day::DATE
                   AND r.lat BETWEEN t.south - 0.03 AND t.north + 0.03 AND r.lon BETWEEN t.west - 0.04 AND t.east + 0.04)
        -- one fire per report (the largest), then one report per fire (the largest)
        SELECT arg_max(id, reported) AS id, max(reported) AS reported, fire_id, any_value(acres) AS acres,
               any_value(p100) AS p100, any_value(p1000) AS p1000, any_value(year) AS year
        FROM (SELECT id, any_value(reported) AS reported, arg_max(fire_id, acres) AS fire_id, max(acres) AS acres,
                     arg_max(p100, acres) AS p100, arg_max(p1000, acres) AS p1000, arg_max(year, acres) AS year
              FROM pair GROUP BY id)
        GROUP BY fire_id""").df()
    test = matched[matched.year >= TEST_FROM]
    result = {"reports_with_a_fire": int(len(matched)), "test_reports": int(len(test)),
              "footprint_vs_reported_size_log_correlation":
                  round(float(np.corrcoef(np.log1p(test.acres), np.log1p(test.reported))[0, 1]), 3),
              "median_footprint_over_reported_100_acres_up":
                  round(float((test.acres / test.reported)[test.reported >= 100].median()), 2)}
    for size in SIZES:
        result[f"rating_ranks_reported_{size}"] = score((test.reported >= size).astype(int), test[f"p{size}"])
    # The reference model (weather and place only, trained on reports) on the same reports.
    meta = json.loads((REFERENCE / "models_meta.json").read_text())
    rows = pd.read_parquet(reference)
    for column in CATEGORICAL:
        rows[column] = rows[column].astype("category")
    rows = rows.set_index("id").loc[test.id]
    for size in SIZES:
        # as text: a Windows checkout stores these files with CRLF line ends, which LightGBM cannot parse
        booster = lgb.Booster(model_str=(REFERENCE / f"model_B_large{size}.txt").read_text())
        p = booster.predict(rows[meta[f"B_large{size}"]["features"]])
        result[f"reference_model_ranks_reported_{size}"] = score((test.reported.values >= size).astype(int), p)
    metrics["against_agency_reports"] = result
    print("against agency reports:", json.dumps(result, indent=1))


def store(table, meaning):
    """The rating of each fire, in the columns server/fires.py reads, and the meaning of the levels."""
    rated = table.rename(columns={"fire_id": "event_id", "first_day": "rated_first_day", "last_day": "rated_last_day"})
    rated = rated.assign(fire_id=rated.event_id, parts=1, share=1.0, fire_share=1.0, lc=rated.lc.astype("float"))
    rated = rated[["event_id"] + RATING_COLUMNS]            # noqa: F841  (read by DuckDB below)
    con = duckdb.connect(str(DB))
    out = (ROOT / "data" / "events" / "event_danger.parquet").as_posix()
    con.execute(f"""COPY (SELECT * REPLACE (level::TINYINT AS level, lc::SMALLINT AS lc,
                                           rated_first_day::DATE AS rated_first_day, rated_last_day::DATE AS rated_last_day)
                         FROM rated ORDER BY event_id) TO '{out}' (FORMAT parquet, COMPRESSION zstd)""")
    con.execute("DROP TABLE IF EXISTS fires")               # older runs kept the ratings in the database
    con.execute("CREATE OR REPLACE TABLE danger_levels AS SELECT * FROM meaning")
    print("stored:", con.execute(f"SELECT count(*), count(level) FROM '{out}'").fetchone(), "fires, rated")
    con.close()


def main():
    metrics = {"years": {"train": f"2012-{TRAIN_TO}", "validation": VALIDATION, "test": f"{TEST_FROM}-2025"},
               "level_starts_chance_of_1000_acres": dict(zip(LEVELS[1:], LEVEL_STARTS))}
    table = load()
    metrics["fires"] = {"all": int(len(table)), "rated": int(table.rated.sum())}
    print(metrics["fires"])
    train(table, metrics)
    meaning = levels(table, metrics)
    compare_with_reports(table, metrics)
    (DANGER / "metrics.json").write_text(json.dumps(metrics, indent=1))
    store(table, meaning)


if __name__ == "__main__":
    main()
