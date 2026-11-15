"""Vercel entry point: the same application as `uvicorn server.main:app`.

Vercel refuses files above 100 MB, so data/fire.duckdb is uploaded in pieces
(data/deploy/fire.duckdb.part*, made with `split -b 90M`) and joined here in
/tmp when the function starts.
"""
import os
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

parts = sorted((ROOT / "data" / "deploy").glob("fire.duckdb.part*"))
if parts:
    target = pathlib.Path("/tmp/fire.duckdb")
    if not target.exists():
        tmp = target.with_suffix(".joining")
        with open(tmp, "wb") as out:
            for part in parts:
                with open(part, "rb") as src:
                    shutil.copyfileobj(src, out)
        tmp.replace(target)
    os.environ["FIRE_DB_PATH"] = str(target)

from server.main import app  # noqa: E402,F401
