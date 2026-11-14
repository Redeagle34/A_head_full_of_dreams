"""Step 2: download the FIRMS yearly U.S. archive and store it as Parquet.

Run:  python pipeline/ingest.py
Safe to rerun: existing raw files are skipped and each sensor-year Parquet file
is rewritten from its raw file, so a second run changes no counts.
"""
import datetime
import pathlib
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PARQUET = ROOT / "data" / "parquet"
BASE = "https://firms.modaps.eosdis.nasa.gov/data/country"
# sensor -> first year of the record
SENSORS = {"modis": 2000, "viirs-snpp": 2012, "viirs-jpss1": 2018}
LAST_YEAR = datetime.date.today().year
# ponytail: Alaska is excluded with a latitude cut (contiguous U.S. tops out
# near 49.4 N, Hawaii near 22 N). Replace with a state polygon join in step 3.
MAX_LAT = 50.0


def download(sensor, year):
    """Fetch one sensor-year CSV. Returns its path, or None if FIRMS has no file."""
    name = f"{sensor}_{year}_United_States.csv"
    dest = RAW / name
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    part = dest.with_suffix(".part")
    req = urllib.request.Request(f"{BASE}/{sensor}/{year}/{name}",
                                 headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r, open(part, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
    except urllib.error.HTTPError as e:
        part.unlink(missing_ok=True)
        if e.code == 404:
            return None
        raise
    part.rename(dest)  # only complete downloads get the final name
    return dest


def to_parquet(con, sensor, year, csv_path):
    out = PARQUET / f"sensor={sensor}" / f"year={year}"
    out.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
        COPY (
            SELECT * FROM read_csv('{csv_path.as_posix()}', header=true,
                types={{'acq_time': 'VARCHAR', 'confidence': 'VARCHAR',
                        'satellite': 'VARCHAR', 'version': 'VARCHAR'}})
            WHERE latitude <= {MAX_LAT}
        ) TO '{(out / "data.parquet").as_posix()}' (FORMAT parquet)
    """)


def summary(con):
    return con.execute(f"""
        SELECT sensor, year, count(*) AS n_rows,
               min(acq_date) AS first_day, max(acq_date) AS last_day
        FROM read_parquet('{PARQUET.as_posix()}/*/*/*.parquet',
                          hive_partitioning=true, union_by_name=true)
        GROUP BY ALL ORDER BY ALL
    """).fetchall()


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    jobs = [(s, y) for s, first in SENSORS.items() for y in range(first, LAST_YEAR + 1)]
    with ThreadPoolExecutor(4) as pool:
        paths = list(pool.map(lambda j: download(*j), jobs))
    con = duckdb.connect()
    missing = []
    for (sensor, year), path in zip(jobs, paths):
        if path is None:
            missing.append(f"{sensor} {year}")
        else:
            to_parquet(con, sensor, year, path)
    rows = summary(con)
    for r in rows:
        print(*r)
    print("total rows:", sum(r[2] for r in rows))
    print("no file at FIRMS:", ", ".join(missing) or "none")


if __name__ == "__main__":
    main()
