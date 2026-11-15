"""Prepare a small copy of the data for the site on Vercel, and check it fits.

Run:  python pipeline/prepare_deploy.py     (after the database and the files in data/events/ are built)

Output, all in data/deploy/ (the only data folder that is uploaded):
  fire.duckdb               the small tables of data/fire.duckdb: day_w, meta, danger_levels
  obs_modis.parquet         the observations of the MODIS layer
  obs_viirs.parquet         the observations of the VIIRS layer
  obs_both_viirs.parquet    the VIIRS part of the harmonized layer; its Aqua part is read from obs_modis.parquet
  events/                   the files of data/events/ that the server reads

Why a copy: a Vercel function may hold FUNCTION_LIMIT of code, packages and data, and data/ as built is
about 300 MB. The copy is the same data, stored smaller:
  - observations as Parquet with strong compression instead of inside the database; api/index.py makes
    the table `obs` a view over these files when the function starts
  - the Aqua observations of the harmonized layer are not stored twice
  - coordinates to 4 decimals (about 10 m; the finest pixel is 375 m), radiative power to 0.1 MW,
    ratings to the digits the page shows
Nothing is left out: the script checks that every table and file keeps all its rows.

Limits (Vercel, November 2026): the function limit below is the one a real deploy reported; no single
file above 100 MB.
"""
import pathlib
import shutil
import sys

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "fire.duckdb"
EVENTS = ROOT / "data" / "events"
OUT = ROOT / "data" / "deploy"

MB = 1024 * 1024
FILE_LIMIT = 100 * MB
FUNCTION_LIMIT = 225 * MB
PACKAGES = 40 * MB              # duckdb, fastapi, uvicorn inside the function, after Vercel trims them (measured from a deploy)
ZSTD = "FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 19, ROW_GROUP_SIZE 100000"
OBS = ("layer, source, acq_date, round(lat, 4) AS lat, round(lon, 4) AS lon, round(frp, 1) AS frp, "
       "round(p, 3)::FLOAT AS p, state")
# file server/events.py reads -> (script that writes it, the SELECT that stores it smaller)
EVENT_FILES = {
    "events.parquet": ("fire_events.py", "SELECT * FROM {src} ORDER BY state, start"),
    "event_cells.parquet": ("fire_events.py", "SELECT * FROM {src} ORDER BY event_id"),
    "enrichment.parquet": ("event_enrich.py", "SELECT * FROM {src} ORDER BY event_id"),
    "reported_fires.parquet": ("missed_fires.py", "SELECT * FROM {src} ORDER BY date"),
    "event_danger.parquet": ("danger_model.py", """
        SELECT event_id, fire_id, parts, share, fire_share, rated_first_day, rated_last_day, days_seen,
               round(acres) AS acres, round(acres_day2) AS acres_day2, round(growth, 2) AS growth,
               round(d1_night_share, 2) AS d1_night_share, level, round(p100, 3) AS p100, round(p1000, 3) AS p1000,
               round(built_5km, -2) AS built_5km, round(vs, 1) AS vs, round(rmin) AS rmin, round(fm1000, 1) AS fm1000,
               round(pr30, 1) AS pr30, round(tmmx, 1) AS tmmx, lc
        FROM {src} ORDER BY event_id"""),
}
PLAIN_FILES = {"missed_summary.json": "missed_fires.py"}


def build(con):
    """Write the copy. Returns the row counts to check: [(what, rows in the source, rows in the copy)]."""
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "events").mkdir(parents=True)
    out = lambda name: (OUT / name).as_posix()          # noqa: E731
    con.execute(f"ATTACH '{DB.as_posix()}' AS src (READ_ONLY)")
    con.execute(f"ATTACH '{out('fire.duckdb')}' AS small")
    for table in ("day_w", "meta", "danger_levels"):
        if con.execute("SELECT count(*) FROM information_schema.tables WHERE table_catalog = 'src' AND table_name = ?",
                       [table]).fetchone()[0]:
            con.execute(f"CREATE TABLE small.{table} AS SELECT * FROM src.{table}")
    con.execute("DETACH small")
    parts = {"obs_modis.parquet": "layer = 'modis'", "obs_viirs.parquet": "layer = 'viirs'",
             "obs_both_viirs.parquet": "layer = 'both' AND source <> 'aqua'"}
    for name, where in parts.items():
        con.execute(f"COPY (SELECT {OBS} FROM src.obs WHERE {where} ORDER BY acq_date, state) TO '{out(name)}' ({ZSTD})")
    counts = [(f"obs {layer}", con.execute("SELECT count(*) FROM src.obs WHERE layer = ?", [layer]).fetchone()[0],
               con.execute(f"SELECT count(*) FROM ({obs_view_sql(OUT)}) WHERE layer = ?", [layer]).fetchone()[0])
              for layer in ("modis", "viirs", "both")]
    for name, (script, select) in EVENT_FILES.items():
        path = EVENTS / name
        if not path.exists():
            print(f"  {name}: missing, its part of the page will say so. Run: python pipeline/{script}")
            continue
        src = f"'{path.as_posix()}'"
        con.execute(f"COPY ({select.format(src=src)}) TO '{out('events/' + name)}' ({ZSTD})")
        counts.append((name, con.execute(f"SELECT count(*) FROM {src}").fetchone()[0],
                       con.execute(f"SELECT count(*) FROM '{out('events/' + name)}'").fetchone()[0]))
    for name in PLAIN_FILES:
        if (EVENTS / name).exists():
            shutil.copy(EVENTS / name, OUT / "events" / name)
    return counts


def obs_view_sql(folder):
    """The table `obs` as a query over the Parquet files in `folder` (also used by api/index.py)."""
    f = lambda name: (pathlib.Path(folder) / name).as_posix()          # noqa: E731
    columns = "source, acq_date, lat, lon, frp, p::DOUBLE AS p, state"
    return (f"SELECT layer, {columns} FROM read_parquet(['{f('obs_modis.parquet')}', '{f('obs_viirs.parquet')}', "
            f"'{f('obs_both_viirs.parquet')}']) "
            f"UNION ALL SELECT 'both' AS layer, {columns} FROM read_parquet('{f('obs_modis.parquet')}') WHERE source = 'aqua'")


def main():
    if not DB.exists():
        sys.exit(f"{DB} is missing. Run: python pipeline/build_db.py")
    con = duckdb.connect()
    counts = build(con)
    problems = [f"{what}: {before:,} rows in the data, {after:,} in the copy" for what, before, after in counts if before != after]
    # The harmonized layer adds up to the same fire days after the Aqua rows are read from the MODIS file.
    before, after = (con.execute(f"SELECT round(sum(p), 0) FROM {t} WHERE layer = 'both'").fetchone()[0]
                     for t in ("src.obs", f"({obs_view_sql(OUT)})"))
    if abs(before - after) > 1e-4 * before:              # probabilities are stored to 3 decimals
        problems.append(f"harmonized layer: sum of detection probabilities {before} in the data, {after} in the copy")

    data = 0
    for path in sorted(p for p in OUT.rglob("*") if p.is_file()):
        size = path.stat().st_size
        data += size
        print(f"  {path.relative_to(OUT).as_posix()}: {size / MB:.1f} MB")
        if size > FILE_LIMIT:
            problems.append(f"{path.name} is above 100 MB; Vercel will refuse it")
    models = sum(p.stat().st_size for p in (ROOT / "web" / "models").glob("*"))
    web = sum(p.stat().st_size for p in (ROOT / "web").rglob("*") if p.is_file()) - models
    code = sum(p.stat().st_size for d in ("server", "api") for p in (ROOT / d).rglob("*.py"))
    function = data + web + code + PACKAGES
    print(f"data {data / MB:.0f} MB (as built: {(DB.stat().st_size + sum(p.stat().st_size for p in EVENTS.glob('*') if p.name in EVENT_FILES)) / MB:.0f} MB)")
    print(f"function: about {function / MB:.0f} MB of {FUNCTION_LIMIT / MB:.0f} MB: {'fits' if function <= FUNCTION_LIMIT else 'DOES NOT FIT'}")
    if function > FUNCTION_LIMIT:
        problems.append("the function is above Vercel's limit")
    for p in problems:
        print("PROBLEM:", p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
