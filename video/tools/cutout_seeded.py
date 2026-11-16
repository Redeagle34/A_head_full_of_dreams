"""Cut out a person from a busy background with a seeded random-walker segmentation.

Usage: python cutout_seeded.py <in> <out.png> "<fg boxes>" [bg_margin]
fg boxes: semicolon-separated x0,y0,x1,y1 in 0..1 image fractions that are surely the person.
Background seeds: a margin along the top, left and right edges (and the bottom unless the person
touches it). Works on SLIC superpixels so edges follow colour boundaries.
"""
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from skimage import color, filters, morphology, segmentation, transform


def run(src, dst, boxes, margin=0.04, bg_boxes=(), bottom_bg=False):
    im = Image.open(src).convert("RGB")
    rgb = np.asarray(im).astype(float) / 255
    H, W = rgb.shape[:2]
    s = 700 / max(H, W)
    small = transform.resize(rgb, (round(H * s), round(W * s)), anti_aliasing=True)
    h, w = small.shape[:2]
    lab = color.rgb2lab(small)
    seeds = np.zeros((h, w), np.int32)
    m = max(2, int(margin * max(h, w)))
    seeds[:m, :] = 1; seeds[:, :m] = 1; seeds[:, -m:] = 1
    if bottom_bg: seeds[-m:, :] = 1
    for b in bg_boxes:
        x0, y0, x1, y1 = b
        seeds[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)] = 1
    for b in boxes:
        x0, y0, x1, y1 = b
        seeds[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)] = 2
    feat = np.dstack([lab[..., 0] / 100 * 1.0, lab[..., 1] / 60, lab[..., 2] / 60])
    lbl = segmentation.random_walker(feat, seeds, beta=1400, mode="cg_j", channel_axis=-1, tol=1e-3)
    fg = lbl == 2
    fg = morphology.opening(fg, morphology.disk(2))
    L, k = ndi.label(fg)
    if k: fg = L == (np.argmax(ndi.sum(fg, L, range(1, k + 1))) + 1)
    fg = ndi.binary_fill_holes(fg)
    a = transform.resize(fg.astype(float), (H, W), order=1)
    a = filters.gaussian(a, 1.2)
    a = np.clip((a - 0.5) * 2.4 + 0.5, 0, 1)
    ys, xs = np.nonzero(a > 0.05)
    out = np.dstack([np.asarray(im), (a * 255).astype(np.uint8)])[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    Image.fromarray(out, "RGBA").save(dst, optimize=True)
    print(dst, out.shape[1], "x", out.shape[0])


if __name__ == "__main__":
    boxes = [tuple(map(float, b.split(","))) for b in sys.argv[3].split(";")]
    bg = [tuple(map(float, b.split(','))) for b in sys.argv[5].split(';')] if len(sys.argv) > 5 else []
    run(sys.argv[1], sys.argv[2], boxes, float(sys.argv[4]) if len(sys.argv) > 4 else 0.04, bg)
