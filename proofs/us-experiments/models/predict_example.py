"""Load a saved model and score rows of the training table. Run from this folder: python predict_example.py"""
import json
import lightgbm as lgb
import pandas as pd

meta = json.load(open("models_meta.json"))
table = pd.read_parquet("training_table.parquet")
for column in ("frg", "lc"):                       # the two categorical inputs
    table[column] = table[column].astype("category")

for key in ("A_ignition", "B_large100", "B_large1000"):
    info = meta[key]
    model = lgb.Booster(model_file=info["file"])
    rows = table[table.year >= 2022].head(5)
    print(key, model.predict(rows[info["features"]]).round(3))
