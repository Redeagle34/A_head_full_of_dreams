"""Pull last 5 days of every FIRMS NRT source over CONUS (cached), summarize per source."""
import sys, os, pathlib, requests, pandas as pd, io
sys.path.insert(0, os.path.dirname(__file__)); import _env  # noqa
K = os.environ["FIRMS_MAP_KEY"]; RAW = pathlib.Path("data/raw/firms"); RAW.mkdir(parents=True, exist_ok=True)
BBOX = "-125,24,-66,50"; DAYS = 5; DATE = "2026-11-09"  # 2026-11-09 .. 11-13
SRC = ["MODIS_NRT", "VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "LANDSAT_NRT", "GOES_NRT"]
out = {}
for s in SRC:
    p = RAW / f"conus_{s}_{DATE}_{DAYS}d.csv"
    if not p.exists():
        r = requests.get(f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{K}/{s}/{BBOX}/{DAYS}/{DATE}", timeout=180)
        p.write_text(r.text)
    t = p.read_text()
    try: d = pd.read_csv(io.StringIO(t))
    except Exception: print(s, "UNPARSEABLE:", t[:150]); continue
    out[s] = d
    cols = ",".join(d.columns)
    print(f"\n## {s}: rows={len(d)}  cols={cols}")
    if len(d):
        print("  dates", d.acq_date.min(), "->", d.acq_date.max(), "| per-day", d.groupby('acq_date').size().to_dict())
        if 'confidence' in d: print("  confidence", d.confidence.astype(str).value_counts().head(6).to_dict())
        if 'frp' in d: print("  FRP MW p10/p50/p90:", d.frp.quantile([.1,.5,.9]).round(2).tolist())
        if 'daynight' in d: print("  day/night", d.daynight.value_counts().to_dict())
        print("  unique acq_time count", d.acq_time.nunique())
