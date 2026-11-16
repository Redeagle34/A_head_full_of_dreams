"""Second pass on a cutout: erase leftover wall-coloured pixels that touch the transparent area.

Usage: python clean_cutout.py <original photo> <cutout.png> [threshold]
The wall colour is the median of the original photo's top/left/right border.
"""
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from skimage import color, filters, morphology


def clean(orig, path, thr=10.0):
    o = np.asarray(Image.open(orig).convert("RGB")).astype(float) / 255
    border = np.concatenate([o[:8].reshape(-1, 3), o[:, :8].reshape(-1, 3), o[:, -8:].reshape(-1, 3)])
    wall = np.median(color.rgb2lab(border[None])[0], 0)

    im = np.asarray(Image.open(path).convert("RGBA")).copy()
    lab = color.rgb2lab(filters.gaussian(im[..., :3] / 255.0, 1.0, channel_axis=-1))
    d = np.sqrt(((lab[..., 0] - wall[0]) * 0.45) ** 2 + (lab[..., 1] - wall[1]) ** 2 + (lab[..., 2] - wall[2]) ** 2)
    clear = im[..., 3] < 100
    wallish = d < thr
    lbl, n = ndi.label(clear | wallish)
    keep = np.unique(lbl[clear])
    erase = np.isin(lbl, keep[keep > 0]) & ~clear
    a = (im[..., 3] > 100) & ~erase
    a = morphology.opening(a, morphology.disk(2))
    lab2, k = ndi.label(a)
    if k:
        a = lab2 == (np.argmax(ndi.sum(a, lab2, range(1, k + 1))) + 1)
    a = ndi.binary_fill_holes(a)
    soft = np.clip((filters.gaussian(a.astype(float), 1.2) - 0.5) * 2.2 + 0.5, 0, 1)
    im[..., 3] = (np.minimum(soft, im[..., 3] / 255.0) * 255).astype(np.uint8)
    Image.fromarray(im, "RGBA").save(path, optimize=True)
    print(path, "erased", int(erase.sum()), "px")


if __name__ == "__main__":
    clean(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 10.0)
