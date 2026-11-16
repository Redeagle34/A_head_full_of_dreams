"""Prepare everything the video page needs, into video/assets and video/data.

- Fire detections (real FIRMS archive from the project's parquet files)
- Satellite imagery mosaics (Esri World Imagery tiles) for the map zoom
- World land outline (world-atlas) and Blue Marble texture for the globes
- Copies of the NASA satellite models

Run:  python -I video/tools/prep_assets.py
"""
import io
import json
import math
import pathlib
import shutil
import time
import urllib.request

import duckdb
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "A_head_full_of_dreams"
OUT = ROOT / "video"
ASSETS = OUT / "assets"
DATA = OUT / "data"
UA = {"User-Agent": "video-asset-prep/1.0"}


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print("retry", url, e)
            time.sleep(1.5 * (i + 1))


# ---------------------------------------------------------------- fire data
def fires():
    c = duckdb.connect()
    src = f"read_parquet('{(APP / 'data/parquet').as_posix()}/**/*.parquet', hive_partitioning=true, union_by_name=true)"
    # Day-level detections over California (MODIS: Terra/Aqua, VIIRS: S-NPP/NOAA-20)
    rows = c.sql(f"""
        select round(longitude,4), round(latitude,4), round(scan,3), round(track,3),
               round(coalesce(frp,0),1), sensor, satellite, acq_time
        from {src}
        where year=2020 and acq_date='2020-09-08'
          and longitude between -126 and -114 and latitude between 32 and 43
    """).fetchall()
    out = []
    for lo, la, sc, tr, frp, sensor, sat, tm in rows:
        s = 0 if sensor == "modis" else 1
        out.append([lo, la, sc, tr, frp, s, sat, int(tm)])
    (DATA / "fires_ca_20200908.json").write_text(json.dumps(out, separators=(",", ":")))
    print("CA detections", len(out))

    # Globe dots: all US detections 1-14 Sep 2020, gridded 0.1 deg
    g = c.sql(f"""
        select round(longitude*10)/10 lo, round(latitude*10)/10 la, count(*) n, round(sum(coalesce(frp,0))) f
        from {src}
        where year=2020 and acq_date between '2020-09-01' and '2020-09-14'
        group by 1,2
    """).fetchall()
    (DATA / "fires_us_sep2020.json").write_text(json.dumps([[a, b, n, f] for a, b, n, f in g], separators=(",", ":")))
    print("US grid cells", len(g))


# ---------------------------------------------------------------- tiles
def lonlat_to_tile(lon, lat, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    lr = math.radians(lat)
    y = (1 - math.log(math.tan(lr) + 1 / math.cos(lr)) / math.pi) / 2 * n
    return x, y


ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"


def mosaic(name, z, lon0, lat0, lon1, lat1):
    x0, y0 = lonlat_to_tile(lon0, lat1, z)
    x1, y1 = lonlat_to_tile(lon1, lat0, z)
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    nx, ny = x1 - x0 + 1, y1 - y0 + 1
    img = Image.new("RGB", (nx * 256, ny * 256), (8, 14, 24))
    for j in range(ny):
        for i in range(nx):
            b = get(ESRI.format(z=z, x=x0 + i, y=y0 + j))
            img.paste(Image.open(io.BytesIO(b)).convert("RGB"), (i * 256, j * 256))
    path = ASSETS / "tiles" / f"{name}.jpg"
    img.save(path, quality=90)
    print("mosaic", name, z, nx, "x", ny)
    return {"name": name, "z": z, "x0": x0, "y0": y0, "nx": nx, "ny": ny, "src": f"assets/tiles/{name}.jpg"}


def tiles():
    meta = [
        mosaic("z5_westna", 5, -152, 12, -68, 62),
        mosaic("z7_california", 7, -129, 30.5, -110, 45),
        mosaic("z9_norcal", 9, -125.2, 38.4, -120.6, 41.4),
        mosaic("z11_august", 11, -123.85, 39.55, -122.25, 40.45),
    ]
    (DATA / "mosaics.json").write_text(json.dumps(meta, indent=1))


# ---------------------------------------------------------------- misc
def misc():
    (ASSETS / "land-110m.json").write_bytes(get("https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/land-110m.json"))
    (ASSETS / "land-50m.json").write_bytes(get("https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/land-50m.json"))
    for f in ["earth-blue-marble.jpg", "earth-topology.png"]:
        (ASSETS / f).write_bytes(get(f"https://unpkg.com/three-globe@2.31.0/example/img/{f}"))
    for f in ["terra.glb", "aqua.glb", "suomi-npp.glb"]:
        shutil.copy(APP / "web/models" / f, ASSETS / f)
    print("misc done")


if __name__ == "__main__":
    for d in (ASSETS / "tiles", DATA):
        d.mkdir(parents=True, exist_ok=True)
    fires()
    misc()
    tiles()
