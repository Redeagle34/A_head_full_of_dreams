"""Reproject the Web-Mercator mosaics to equirectangular patches (PNG with feathered alpha)
so the 3D globe can show the same imagery as the flat map at the hand-off."""
import json
import math
import pathlib

import numpy as np
from PIL import Image

OUT = pathlib.Path(__file__).resolve().parents[1]
meta = {m["name"]: m for m in json.loads((OUT / "data/mosaics.json").read_text())}


def tile_lon(x, z):
    return x / 2 ** z * 360 - 180


def tile_lat(y, z):
    n = math.pi - 2 * math.pi * y / 2 ** z
    return math.degrees(math.atan(math.sinh(n)))


def patch(name, ppd, feather=0.06):
    m = meta[name]
    z = m["z"]
    src = np.asarray(Image.open(OUT / m["src"]).convert("RGB"))
    lon0, lon1 = tile_lon(m["x0"], z), tile_lon(m["x0"] + m["nx"], z)
    lat1, lat0 = tile_lat(m["y0"], z), tile_lat(m["y0"] + m["ny"], z)
    W, H = int((lon1 - lon0) * ppd), int((lat1 - lat0) * ppd)
    lons = lon0 + (np.arange(W) + 0.5) / W * (lon1 - lon0)
    lats = lat1 - (np.arange(H) + 0.5) / H * (lat1 - lat0)
    n = 2 ** z
    px = ((lons + 180) / 360 * n - m["x0"]) * 256
    lr = np.radians(lats)
    py = ((1 - np.log(np.tan(lr) + 1 / np.cos(lr)) / math.pi) / 2 * n - m["y0"]) * 256
    PX, PY = np.meshgrid(px, py)
    PX = np.clip(PX, 0, src.shape[1] - 1).astype(np.int32)
    PY = np.clip(PY, 0, src.shape[0] - 1).astype(np.int32)
    rgb = src[PY, PX]
    u = np.minimum(np.arange(W) / W, 1 - np.arange(W) / W) / feather
    v = np.minimum(np.arange(H) / H, 1 - np.arange(H) / H) / feather
    a = np.clip(np.minimum.outer(v, u), 0, 1)
    a = (a * a * (3 - 2 * a) * 255).astype(np.uint8)
    img = Image.fromarray(np.dstack([rgb, a]), "RGBA")
    path = OUT / "assets/tiles" / f"patch_{name}.png"
    img.save(path, optimize=True)
    print(name, W, H, [lon0, lon1, lat0, lat1])
    return {"src": f"assets/tiles/patch_{name}.png", "lon0": lon0, "lon1": lon1, "lat0": lat0, "lat1": lat1}


patches = [patch("z5_westna", 22, 0.22), patch("z7_california", 70, 0.16)]
(OUT / "data/patches.json").write_text(json.dumps(patches, indent=1))
