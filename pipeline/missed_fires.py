"""Which reported wildfires were missed: by the satellites, and by the prediction model.

Run:  python pipeline/missed_fires.py     (after pipeline/calendar_table.py)
Output: data/events/reported_fires.parquet   one row per reported wildfire, with flags
        data/events/missed_summary.json      share missed, by fire size

Reported fires: the wildfire starts in proofs/us-experiments/models/training_table.parquet
(NIFC WFIGS incident reports, contiguous U.S., 2014 onward: every fire of 100 acres or
more and a random part of the smaller ones).

Two separate questions per fire
  seen by satellite   any MODIS / VIIRS vegetation-fire detection within RADIUS_KM, from one
                      day before the report to DAYS_AFTER days after (same rule as
                      proofs/us-experiments/scripts/24_wfigs_vs_firms.py)
  expected by model   the ignition model (model A) gave the place and day a score of at
                      least MODEL_THRESHOLD. The score is a ranking, not a probability
                      (see MODEL_CARDS.md); 0.5 is where the training table splits evenly.
                      Only fires from 2022 onward are a fair test: earlier ones were used
                      to train or tune the model.
"""
import json
import pathlib

import duckdb
import lightgbm as lgb
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODELS = ROOT / "proofs" / "us-experiments" / "models"
DET = f"'{(ROOT / 'data' / 'calendar' / 'detections.parquet').as_posix()}'"
OUT = ROOT / "data" / "events"
RADIUS_KM, DAYS_BEFORE, DAYS_AFTER = 2.0, 1, 3
MODEL_THRESHOLD = 0.5
BIN = 0.03                       # degrees; a 3 x 3 block of bins always covers RADIUS_KM


def score_fires():
    meta = json.loads((MODELS / "models_meta.json").read_text())
    table = pd.read_parquet(MODELS / "training_table.parquet")
    for column in ("frg", "lc"):
        table[column] = table[column].astype("category")
    fires = table[table.y == 1].copy()
    for key, name in (("A_ignition", "score_ignition"), ("B_large100", "score_large100"),
                      ("B_large1000", "score_large1000")):
        info = meta[key]
        # Read as text: a Windows checkout may have changed the line endings, which LightGBM rejects.
        text = (MODELS / info["file"]).read_bytes().replace(bytes([13, 10]), bytes([10])).decode("utf-8")
        fires[name] = lgb.Booster(model_str=text).predict(fires[info["features"]]).round(4)
    fires["date"] = pd.to_datetime(fires.date).dt.date
    fires["split"] = fires.year.map(lambda y: "train" if y <= 2020 else "validation" if y == 2021 else "test")
    fires["lc"] = fires.lc.astype(int)
    return fires[["id", "lat", "lon", "date", "year", "split", "acres", "FireCause", "POOState", "lc", "treecover",
                  "score_ignition", "score_large100", "score_large1000"]].rename(
                      columns={"FireCause": "cause", "POOState": "state", "lc": "land_cover"})


def match_satellites(con):
    """Table `seen`: per reported fire, detections near it in the days around the report."""
    con.execute(f"""
        CREATE TABLE det AS
        SELECT floor(latitude / {BIN})::INT AS by, floor(longitude / {BIN})::INT AS bx,
               latitude, longitude, acq_date, sensor <> 'modis' AS viirs
        FROM {DET} WHERE acq_date >= (SELECT min(date) - {DAYS_BEFORE} FROM fires)
    """)
    con.execute(f"""
        CREATE TABLE seen AS
        SELECT f.id, count(*) FILTER (WHERE NOT d.viirs) AS near_modis, count(*) FILTER (WHERE d.viirs) AS near_viirs,
               min(d.acq_date) AS first_seen
        FROM fires f, (SELECT unnest([-1, 0, 1]) AS oy) a, (SELECT unnest([-1, 0, 1]) AS ox) b, det d
        WHERE d.by = floor(f.lat / {BIN})::INT + a.oy AND d.bx = floor(f.lon / {BIN})::INT + b.ox
          AND d.acq_date BETWEEN f.date - {DAYS_BEFORE} AND f.date + {DAYS_AFTER}
          AND 6371 * 2 * asin(sqrt(pow(sin(radians(d.latitude - f.lat) / 2), 2) +
              cos(radians(f.lat)) * cos(radians(d.latitude)) * pow(sin(radians(d.longitude - f.lon) / 2), 2))) <= {RADIUS_KM}
        GROUP BY f.id
    """)


def main():
    fires = score_fires()                                    # noqa: F841  (read by DuckDB)
    con = duckdb.connect()
    con.execute("CREATE TABLE fires AS SELECT * FROM fires")
    last_day = con.execute(f"SELECT max(acq_date) FROM {DET}").fetchone()[0]
    match_satellites(con)
    con.execute(f"""
        CREATE TABLE reported AS
        SELECT f.*, coalesce(s.near_modis, 0) > 0 AS seen_modis, coalesce(s.near_viirs, 0) > 0 AS seen_viirs,
               s.id IS NOT NULL AS seen_satellite, s.first_seen,
               f.score_ignition >= {MODEL_THRESHOLD} AS expected_by_model,
               f.date + {DAYS_AFTER} <= DATE '{last_day}' AS satellite_record_covers
        FROM fires f LEFT JOIN seen s USING (id)
    """)
    assert con.execute("SELECT count(*) = count(DISTINCT id) FROM reported").fetchone()[0]
    OUT.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY (SELECT * FROM reported ORDER BY acres DESC NULLS LAST) "
                f"TO '{(OUT / 'reported_fires.parquet').as_posix()}' (FORMAT parquet)")
    size = ("CASE WHEN acres IS NULL THEN 'unknown' WHEN acres < 1 THEN '1 under 1 acre' WHEN acres < 100 THEN '2 1 to 100' "
            "WHEN acres < 1000 THEN '3 100 to 1,000' WHEN acres < 10000 THEN '4 1,000 to 10,000' ELSE '5 over 10,000' END")
    rows = con.execute(f"""
        SELECT {size} AS size, count(*) AS fires,
               round(avg((NOT seen_satellite)::INT), 3) AS missed_by_satellites,
               round(avg((NOT seen_viirs)::INT), 3) AS missed_by_viirs,
               round(avg((NOT seen_modis)::INT), 3) AS missed_by_modis,
               round(avg((NOT expected_by_model)::INT), 3) AS missed_by_model,
               round(avg((NOT seen_satellite AND NOT expected_by_model)::INT), 3) AS missed_by_both
        FROM reported WHERE split = 'test' AND satellite_record_covers GROUP BY ALL ORDER BY ALL""").df()
    print(f"Reported wildfires 2022 onward, up to {last_day} (test years of the model):")
    print(rows.to_string(index=False))
    (OUT / "missed_summary.json").write_text(json.dumps({
        "rule": {"radius_km": RADIUS_KM, "days_before": DAYS_BEFORE, "days_after": DAYS_AFTER,
                 "model_threshold": MODEL_THRESHOLD, "years": f"2022 to {last_day}"},
        "by_size": rows.to_dict("records")}, indent=1))


if __name__ == "__main__":
    main()
