"""Remove the plain wall background from the team photos (no ML model needed).

Superpixels (SLIC) -> wall color model from the image border -> flood fill of wall-like
superpixels connected to the border -> largest person blob, holes filled, soft edge.
Usage: python cutout.py <in> <out.png> [threshold]
"""
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from skimage import color, filters, morphology, segmentation


def cutout(src, dst, thr=14.0, local=6.5, peel=8.0, max_side=1400):
    im = Image.open(src).convert("RGB")
    s = min(1.0, max_side / max(im.size))
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    rgb = np.asarray(im).astype(np.float64) / 255
    lab = color.rgb2lab(filters.gaussian(rgb, 1.5, channel_axis=-1))
    seg = segmentation.slic(rgb, n_segments=1800, compactness=14, start_label=0)
    n = seg.max() + 1
    mean = np.stack([ndi.mean(lab[..., k], seg, np.arange(n)) for k in range(3)], 1)

    # wall model: superpixels touching the top/left/right border (bottom has clothes)
    border = np.unique(np.concatenate([seg[0], seg[:, 0], seg[:, -1]]))
    wall = mean[border]
    med = np.median(wall, 0)
    keep = np.linalg.norm(wall - med, axis=1) < 18          # drop door frames, etc.
    wall = wall[keep]

    # distance of every superpixel to its nearest wall sample (handles lighting gradient)
    d = np.min(np.linalg.norm(mean[:, None, :] - wall[None, :, :] * [0.6, 1, 1] / [0.6, 1, 1], axis=2), axis=1)
    d_l = np.min(np.abs(mean[:, None, 0] - wall[None, :, 0]) * 0.5
                 + np.linalg.norm(mean[:, None, 1:] - wall[None, :, 1:], axis=2), axis=1)
    like = np.minimum(d, d_l) < thr

    # flood from the border through wall-like superpixels
    adj = [set() for _ in range(n)]
    for a, b in ((seg[:, :-1], seg[:, 1:]), (seg[:-1], seg[1:])):
        m = a != b
        for x, y in zip(a[m], b[m]):
            adj[x].add(y); adj[y].add(x)
    bg = np.zeros(n, bool)
    stack = [b for b in np.unique(np.concatenate([seg[0], seg[:, 0], seg[:, -1], seg[-1]])) if like[b]]
    for b in stack: bg[b] = True
    while stack:
        c = stack.pop()
        for nb in adj[c]:
            if not bg[nb] and like[nb] and np.linalg.norm((mean[nb] - mean[c]) * [0.6, 1, 1]) < local:
                bg[nb] = True; stack.append(nb)

    # peel: wall-coloured superpixels on the edge of the background, a few rounds
    dist = np.minimum(d, d_l)
    for _ in range(4):
        add = [c for c in range(n) if not bg[c] and dist[c] < peel and any(bg[x] for x in adj[c])]
        if not add: break
        bg[add] = True
    fg = ~bg[seg]
    fg = morphology.opening(fg, morphology.disk(3))
    lbl, k = ndi.label(fg)
    if k:
        sizes = ndi.sum(fg, lbl, range(1, k + 1))
        fg = lbl == (np.argmax(sizes) + 1)
    fg = ndi.binary_fill_holes(fg)
    fg = morphology.closing(fg, morphology.disk(4))
    alpha = filters.gaussian(fg.astype(float), 1.6)
    alpha = np.clip((alpha - 0.5) * 2.2 + 0.5, 0, 1)

    ys, xs = np.nonzero(alpha > 0.05)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    out = np.dstack([np.asarray(im), (alpha * 255).astype(np.uint8)])[y0:y1, x0:x1]
    Image.fromarray(out, "RGBA").save(dst, optimize=True)
    print(dst, out.shape[1], "x", out.shape[0], "fg", round(fg.mean(), 3))


if __name__ == "__main__":
    a = [float(x) for x in sys.argv[3:]]
    cutout(sys.argv[1], sys.argv[2], *a)
