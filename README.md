# A head full of dreams

NASA Space Apps project: a harmonized MODIS and VIIRS burning calendar for the
United States (contiguous states and Hawaii).

## Run

```bash
pip install -r requirements.txt
python pipeline/ingest.py          # download FIRMS archive (about 1.1 GB) -> data/parquet
python pipeline/calendar_table.py  # state x week x sensor table (about 4 minutes)
python pipeline/harmonize.py       # VIIRS -> MODIS-equivalent, scored on withheld years
python pipeline/export_web.py      # web/data/calendar.json
python -m http.server 8765 --directory web
```

Then open http://localhost:8765. The website data in `web/data/` is committed, so
the last command alone is enough to view the calendar.

Plan, decisions and results per step: `.project/SPEC.md`.
