"""The map grid: square cells of a chosen size in metres.

Rows have a fixed height in latitude. Within a row, the cell width in longitude
is stretched by 1 / cos(latitude), so every cell covers about size x size metres
on the ground anywhere in the U.S.
"""
import math

METRES_PER_DEGREE = 111_320.0
MAX_COLUMNS = 700               # the layer never draws more columns than this

# Finest cell each data source supports (see .project/SPEC.md, "Map explorer").
BASE_SIZE_M = {"viirs": 375, "modis": 1000, "both": 1500}


def cell_sql(size_m, lat="lat", lon="lon"):
    """SQL expressions (row, column) of the cell that holds a point."""
    dlat = size_m / METRES_PER_DEGREE
    row = f"floor({lat} / {dlat!r})"
    col = f"floor({lon} / ({dlat!r} / cos(radians(({row} + 0.5) * {dlat!r}))))"
    return f"{row}::INT", f"{col}::INT"


def cell_bounds(size_m, row, col):
    """[west, south, east, north] of a cell, in degrees."""
    dlat = size_m / METRES_PER_DEGREE
    south = row * dlat
    dlon = dlat / math.cos(math.radians((row + 0.5) * dlat))
    west = col * dlon
    return [round(west, 5), round(south, 5), round(west + dlon, 5), round(south + dlat, 5)]


def choose_size(layer, west, south, east, north):
    """Cell size for a view: the layer's finest size, doubled until it fits the screen."""
    width_m = (east - west) * METRES_PER_DEGREE * math.cos(math.radians((south + north) / 2))
    size = BASE_SIZE_M[layer]
    while width_m / size > MAX_COLUMNS:
        size *= 2
    return size


def self_check():
    # A cell is about size x size metres, and a point lands inside its own cell.
    for lat, lon in [(25.0, -80.0), (39.7, -121.8), (48.9, -100.0)]:
        for size in (375, 1500, 24000):
            dlat = size / METRES_PER_DEGREE
            row = math.floor(lat / dlat)
            col = math.floor(lon / (dlat / math.cos(math.radians((row + 0.5) * dlat))))
            w, s, e, n = cell_bounds(size, row, col)
            assert w - 1e-4 <= lon <= e + 1e-4 and s - 1e-4 <= lat <= n + 1e-4
            width = (e - w) * METRES_PER_DEGREE * math.cos(math.radians((s + n) / 2))
            assert abs(width - size) / size < 0.01, (size, width)
    assert choose_size("viirs", -121.9, 39.6, -121.6, 39.9) == 375
    assert choose_size("both", -125, 24, -66, 50) > 1500


if __name__ == "__main__":
    self_check()
    print("grid ok")
