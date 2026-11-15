"""Vercel entry point: the same application as `uvicorn server.main:app`, on the small copy of the data.

A Vercel function may hold 225 MB of code, packages and data, so it reads data/deploy/, written by
pipeline/prepare_deploy.py: the observations as Parquet files and the small tables in fire.duckdb.
When the function starts, that small database is copied to the temporary folder (the only one a
function can write to) and the table `obs` is added to it as a view over the Parquet files. The rest
of the server does not know the difference.

The cache of satellite orbits goes to the temporary folder too. Answers are compressed: a Vercel
function may not answer with more than 4.5 MB (server/main.py).

To try this start-up on your computer:  python -m uvicorn api.index:app --port 8791
"""
import os
import pathlib
import shutil
import sys
import tempfile

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DEPLOY = ROOT / "data" / "deploy"
TMP = pathlib.Path(tempfile.gettempdir())

if (DEPLOY / "fire.duckdb").exists():
    from pipeline.prepare_deploy import obs_view_sql

    target = TMP / "fire.duckdb"
    if not target.exists():
        building = target.with_suffix(".building")
        shutil.copyfile(DEPLOY / "fire.duckdb", building)
        con = duckdb.connect(str(building))
        con.execute(f"CREATE OR REPLACE VIEW obs AS {obs_view_sql(DEPLOY)}")
        con.close()
        building.replace(target)
    os.environ["FIRE_DB_PATH"] = str(target)
    os.environ["FIRE_EVENTS_DIR"] = str(DEPLOY / "events")
os.environ.setdefault("TLE_CACHE_PATH", str(TMP / "tle_cache.json"))

from server.main import app  # noqa: E402,F401   (it compresses its answers itself)
