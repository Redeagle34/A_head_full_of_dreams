"""Prepare the data for a copy of the site on Vercel, and check it fits.

Run:  python pipeline/prepare_deploy.py     (after the database and the files in data/events/ are built,
                                             with the server stopped)

Output: data/deploy/fire.duckdb.part00, part01, ...   data/fire.duckdb cut in pieces of 90 MB
        (the same as `split -b 90M -d data/fire.duckdb data/deploy/fire.duckdb.part`)

Vercel refuses files above 100 MB; api/index.py joins the pieces in /tmp when the function starts.
The files in data/events/ are uploaded as they are, so each must stay under 100 MB.

Limits checked (Vercel documentation, November 2026):
  function, unpacked      500 MB for Python   https://vercel.com/docs/functions/limitations#bundle-size-limits
  /tmp                    500 MB              https://vercel.com/docs/functions/runtimes#file-system-support
  upload from the CLI     100 MB on the Hobby plan, 1 GB on Pro   https://vercel.com/docs/limits#static-file-uploads
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "fire.duckdb"
EVENTS = ROOT / "data" / "events"
OUT = ROOT / "data" / "deploy"

MB = 1024 * 1024
PIECE = 90 * MB
FILE_LIMIT = 100 * MB
FUNCTION_LIMIT = 500 * MB
TMP_LIMIT = 500 * MB
UPLOAD_HOBBY = 100 * MB
# Size of the packages inside the function, measured with `vercel build` (Python 3.12, November 2026).
PACKAGES = {"requirements.txt": 78 * MB, "requirements.txt and earthengine-api": 216 * MB}
# script that writes each file server/events.py reads; None: optional
EVENT_FILES = {"events.parquet": "fire_events.py", "event_cells.parquet": "fire_events.py",
               "enrichment.parquet": "event_enrich.py", "event_danger.parquet": "event_danger.py",
               "reported_fires.parquet": "missed_fires.py",
               "missed_summary.json": "missed_fires.py"}


def split_database():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("fire.duckdb.part*"):
        old.unlink()
    count = 0
    with open(DB, "rb") as src:
        while True:
            piece = src.read(PIECE)
            if not piece:
                break
            (OUT / f"fire.duckdb.part{count:02d}").write_bytes(piece)
            count += 1
    return count


def main():
    if not DB.exists():
        sys.exit(f"{DB} is missing. Run: python pipeline/build_db.py")
    count = split_database()
    db_size = DB.stat().st_size
    joined = sum(p.stat().st_size for p in OUT.glob("fire.duckdb.part*"))
    assert joined == db_size, "the pieces do not add up to the database"
    print(f"fire.duckdb: {db_size / MB:.0f} MB in {count} pieces in {OUT}")

    problems = []
    events_size = 0
    for name, script in EVENT_FILES.items():
        path = EVENTS / name
        if not path.exists():
            print(f"  {name}: missing, its part of the page will say so. Run: python pipeline/{script}")
            continue
        size = path.stat().st_size
        events_size += size
        print(f"  {name}: {size / MB:.1f} MB")
        if size > FILE_LIMIT:
            problems.append(f"{name} is above 100 MB; Vercel will refuse it")
    extra = [p.name for p in EVENTS.glob("*") if p.name not in EVENT_FILES] if EVENTS.exists() else []
    if extra:
        print(f"  also in data/events/ and uploaded although the server does not read them: {', '.join(extra)}")
        events_size += sum((EVENTS / n).stat().st_size for n in extra if (EVENTS / n).is_file())

    web = sum(p.stat().st_size for p in (ROOT / "web").rglob("*") if p.is_file())
    code = sum(p.stat().st_size for d in ("server", "api") for p in (ROOT / d).rglob("*.py"))
    upload = db_size + events_size + web + code
    print(f"upload: {upload / MB:.0f} MB (database {db_size / MB:.0f}, events {events_size / MB:.0f}, web {web / MB:.0f})")
    if upload > UPLOAD_HOBBY:
        print("  above 100 MB: the Vercel documentation allows this on the Pro plan only (1 GB)")
    if db_size > TMP_LIMIT:
        problems.append("fire.duckdb is above 500 MB and will not fit in /tmp")
    for name, packages in PACKAGES.items():
        function = db_size + events_size + (web - sum(p.stat().st_size for p in (ROOT / "web" / "models").glob("*"))) + code + packages
        fits = "fits" if function <= FUNCTION_LIMIT else "DOES NOT FIT"
        print(f"function with {name}: about {function / MB:.0f} MB of 500 MB: {fits}")
        if function > FUNCTION_LIMIT and name == "requirements.txt":
            problems.append("the function is above 500 MB; see 'Deploy to Vercel' in README.md (large functions)")
    for p in problems:
        print("PROBLEM:", p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
