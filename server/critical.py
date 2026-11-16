"""Critical nodes: which cells to treat with prescribed burns so a wildfire spreads as little as possible.

Plan and sources: CriticalNode.md. In short:

1. Landscape: the cells of the area on screen (pipeline/critical_landscape.py), at the finest of four
   sizes (about 1, 2, 4 or 10 km) that keeps the area under MAX_NODES cells that can burn. Each cell
   is a node; fire can pass between the 8 neighbours of a cell. Each cell has its own usual wind on
   high fire-danger days (gridMET), unless the request sets one wind for the whole area.
2. Monte Carlo (section 3 of the plan): thousands of fires, each ignited in a cell drawn by its
   historical ignition density, spread cell by cell with the jump probability of Alexandridis et al.
   (2008):  p_burn = p_h * (1 + p_veg) * (1 + p_den) * p_wind * p_slope
   p_h is calibrated so the simulated fires have the mean size of the real fires that started here.
3. Weights: p_ij = share of simulated fires that started in cell i and reached cell j
   (the definition of Yemshanov et al. 2021; Burn-P3 is replaced by step 2).
4. Objective (Yemshanov et al. 2021, Eq. 5): the sum of p_ij over pairs i != j that are both kept and
   still connected. Greedy (section 4 of the plan): treat, one at a time, the cell whose removal lowers
   the objective most per km2, until the area budget is used.

Removing a cell that is not a cut point lowers the objective only by its own pairs; only cut points
(articulation points) can split a block, so only they are re-checked in full. The answer is the same as
the plain greedy of the plan, found faster. The greedy is good, not necessarily optimal.

Pure Python on purpose: no numpy or networkx, so it runs inside the Vercel function as is.

Change here:
  P_VEG, forest P_DEN, C1, C2, A_S   the Alexandridis factors
  SIZES                              the cell sizes, finest first
  MAX_NODES, MAX_RUNS, MAX_TREATED   the largest search one request may ask for
"""
import math
import os
import pathlib
import random

from . import db
from .config import ROOT
from .events import LAND_COVER

EVENTS = pathlib.Path(os.environ.get("FIRE_EVENTS_DIR", ROOT / "data" / "events"))
# name -> (height, width) of a cell in degrees; file data/events/landscape_<name>.parquet. Finest first.
SIZES = {1: (0.01, 0.0125), 2: (0.02, 0.025), 4: (0.04, 0.05), 10: (0.1, 0.1)}
KM_PER_DEGREE = 111.32
MAX_NODES = 2500                # cells that can burn in one search
MAX_RUNS = 20_000
MAX_TREATED = 60                # cells one search may treat: the greedy re-checks the area once per cell
FALLBACK_WIND = (3.0, 270)      # m/s, from: where gridMET has no wind (Hawaii) and the request sets none
CALIBRATION_RUNS = 2000
CALIBRATION_STEPS = 20

# Alexandridis et al. (2008): wind c1, c2 (per m/s) and slope a (per degree).
C1, C2, A_S = 0.045, 0.131, 0.078
# p_veg by MCD12Q1 class: forests and shrubs carry fire best, crops and wetlands worst.
# Classes left out (13 built-up, 15 snow and ice, 16 barren, 17 water, no data) do not burn.
P_VEG = {1: 0.4, 2: 0.4, 3: 0.4, 4: 0.4, 5: 0.4, 6: 0.4, 7: 0.0, 8: 0.4, 9: 0.0, 10: 0.0,
         11: -0.3, 12: -0.3, 14: -0.3}
FOREST = {1, 2, 3, 4, 5, 8}
NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


class BadRequest(ValueError):
    """The request cannot be answered as asked; the message says why."""


class Missing(RuntimeError):
    """The landscape files are not built yet."""


def p_den(lc, treecover):
    """Vegetation density (Alexandridis: sparse -0.4, normal 0, dense 0.3), from tree cover in forests only."""
    if lc not in FOREST or treecover is None:
        return 0.0
    return -0.4 if treecover < 30 else 0.3 if treecover > 60 else 0.0


def vegetation(lc):
    return LAND_COVER.get(lc, "No land cover record") + ("" if lc in P_VEG else " (does not burn here)")


def cell_km(row, size):
    """(north-south, east-west) size of a cell in km."""
    dlat, dlon = size
    return dlat * KM_PER_DEGREE, dlon * KM_PER_DEGREE * math.cos(math.radians((row + 0.5) * dlat))


def compass(degrees):
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][round(degrees / 45) % 8]


# ---------- Landscape ----------

def _file(name):
    return EVENTS / f"landscape_{name}.parquet"


def _window(bbox, size):
    west, south, east, north = bbox
    dlat, dlon = size
    return [math.floor(south / dlat), math.floor(north / dlat), math.floor(west / dlon), math.floor(east / dlon)]


def choose_size(bbox):
    """The finest cell size that keeps the area under MAX_NODES cells that can burn: (name, burnable cells)."""
    built = [name for name in SIZES if _file(name).exists()]
    if not built:
        raise Missing("The landscape files are missing. Run: python pipeline/critical_landscape.py")
    for name in built:
        r0, r1, c0, c1 = _window(bbox, SIZES[name])
        if (r1 - r0 + 1) * (c1 - c0 + 1) > MAX_NODES * 20:      # far too many, skip the count
            continue
        n = db.files().execute(
            f"SELECT count(*) FROM '{_file(name).as_posix()}' WHERE row BETWEEN ? AND ? AND col BETWEEN ? AND ? "
            f"AND lc IN ({', '.join(map(str, P_VEG))})", [r0, r1, c0, c1]).fetchall()[0][0]
        if n <= MAX_NODES:
            return name, n
    raise BadRequest(f"The area is too large for the search, even with cells of about {max(built)} km: zoom in.")


def size_info(bbox):
    """What the search would use for this view, so the panel can offer budgets in whole cells."""
    name, burnable = choose_size(bbox)
    west, south, east, north = bbox
    ns, ew = cell_km(math.floor((south + north) / 2 / SIZES[name][0]), SIZES[name])
    return {"size": name, "cell_km2": round(ns * ew, 2), "burnable": burnable, "max_treated": MAX_TREATED,
            "sizes": [n for n in SIZES if _file(n).exists()]}


def load(bbox, name):
    """The cells of a view at one size: {(row, col): {...}}."""
    r0, r1, c0, c1 = _window(bbox, SIZES[name])
    cur = db.files().execute(
        f"SELECT * FROM '{_file(name).as_posix()}' WHERE row BETWEEN ? AND ? AND col BETWEEN ? AND ?", [r0, r1, c0, c1])
    names = [d[0] for d in cur.description]
    return {(r["row"], r["col"]): r for r in (dict(zip(names, v)) for v in cur.fetchall())}


def cell_wind(a, wind_ms, wind_from):
    """(speed m/s, from degrees) in a cell: the request's wind where set, else the cell's usual wind."""
    ms = wind_ms if wind_ms is not None else a.get("wind_ms")
    frm = wind_from if wind_from is not None else a.get("wind_from")
    return (FALLBACK_WIND[0] if ms is None else ms), (FALLBACK_WIND[1] if frm is None else frm)


def factors(cells, size, wind_ms, wind_from):
    """Static part of p_burn for every jump: {cell: [(neighbour, factor)]}, so p_burn = min(1, p_h * factor).
    The wind is the wind of the burning cell."""
    out = {}
    for (r, c), a in cells.items():
        if a["lc"] not in P_VEG:
            continue
        ns, ew = cell_km(r, size)
        speed, frm = cell_wind(a, wind_ms, wind_from)
        toward = math.radians(frm + 180)                    # wind from the west blows toward the east
        jumps = []
        for dr, dc in NEIGHBOURS:
            nb = cells.get((r + dr, c + dc))
            if nb is None or nb["lc"] not in P_VEG:
                continue
            north_km, east_km = dr * ns, dc * ew
            dist_m = math.hypot(north_km, east_km) * 1000
            theta = math.atan2(east_km, north_km) - toward      # spread direction against the wind
            p_wind = math.exp(speed * (C1 + C2 * (math.cos(theta) - 1)))
            rise = (nb["elevation"] or 0) - (a["elevation"] or 0)
            p_slope = math.exp(A_S * math.degrees(math.atan(rise / dist_m)))
            jumps.append(((r + dr, c + dc), (1 + P_VEG[nb["lc"]]) * (1 + p_den(nb["lc"], nb["treecover"])) * p_wind * p_slope))
        out[(r, c)] = jumps
    return out


# ---------- Monte Carlo ----------

def spread_once(ignition, jumps, p_h, rng):
    """One simulated fire (CriticalNode.md, section 3). Returns the burned cells."""
    burned = {ignition}
    frontier = [ignition]
    while frontier:
        c = frontier.pop()
        for nb, f in jumps[c]:
            if nb not in burned and rng.random() < p_h * f:
                burned.add(nb)
                frontier.append(nb)
    return burned


def simulate(jumps, ignitions, weights, p_h, runs, seed):
    """Run `runs` fires. Returns (burn counts per cell, reach counts {i: {j: n}}, mean size)."""
    rng = random.Random(seed)
    starts = rng.choices(ignitions, cum_weights=weights, k=runs)
    burn, reach, total = {}, {}, 0
    for i in starts:
        burned = spread_once(i, jumps, p_h, rng)
        total += len(burned)
        row = reach.setdefault(i, {})
        for j in burned:
            burn[j] = burn.get(j, 0) + 1
            row[j] = row.get(j, 0) + 1
    return burn, reach, total / runs


def calibrate(jumps, ignitions, weights, target, seed):
    """p_h so the simulated fires have the mean size `target` (in cells). Bisection on a log scale, from
    no spread to every jump certain, with the same random numbers each step."""
    def too_big(p_h):           # stops as soon as the fires burned more than the target allows
        rng = random.Random(seed)
        limit, total = target * CALIBRATION_RUNS, 0
        for i in rng.choices(ignitions, cum_weights=weights, k=CALIBRATION_RUNS):
            total += len(spread_once(i, jumps, p_h, rng))
            if total > limit:
                return True
        return False

    min_f = min((f for js in jumps.values() for _, f in js if f > 0), default=1.0)
    lo, hi = 1e-6, 1.0 / min_f
    if not too_big(hi):
        return hi
    for _ in range(CALIBRATION_STEPS):
        mid = math.sqrt(lo * hi)
        if too_big(mid):
            hi = mid
        else:
            lo = mid
    return math.sqrt(lo * hi)


# ---------- Network and greedy ----------

def components(nodes, adjacent):
    """{node: block id} of the kept nodes."""
    comp, n = {}, 0
    for s in nodes:
        if s in comp:
            continue
        comp[s] = n
        stack = [s]
        while stack:
            for v in adjacent[stack.pop()]:
                if v in nodes and v not in comp:
                    comp[v] = n
                    stack.append(v)
        n += 1
    return comp


def cut_points(nodes, adjacent):
    """Articulation points of the kept nodes (Tarjan, without recursion)."""
    disc, low, cuts, t = {}, {}, set(), 0
    for root in nodes:
        if root in disc:
            continue
        disc[root] = low[root] = t
        t += 1
        children = 0
        stack = [(root, None, iter(adjacent[root]))]
        while stack:
            u, parent, it = stack[-1]
            for v in it:
                if v not in nodes:
                    continue
                if v not in disc:
                    disc[v] = low[v] = t
                    t += 1
                    if u == root:
                        children += 1
                    stack.append((v, u, iter(adjacent[v])))
                    break
                if v != parent:
                    low[u] = min(low[u], disc[v])
            else:
                stack.pop()
                if parent is not None:
                    low[parent] = min(low[parent], low[u])
                    if parent != root and low[u] >= disc[parent]:
                        cuts.add(parent)
        if children > 1:
            cuts.add(root)
    return cuts


def objective(nodes, comp, p):
    """Sum of p_ij over kept pairs i != j in the same block."""
    return sum(v for i, row in p.items() if i in nodes for j, v in row.items()
               if j != i and j in nodes and comp[j] == comp[i])


def greedy(nodes, adjacent, p, p_in, cost, budget):
    """Cells to treat, in order: [(cell, objective drop)]. nodes: set of cells; p, p_in: p_ij by row and by column."""
    kept = set(nodes)
    chosen, left = [], budget
    while True:
        comp = components(kept, adjacent)
        cuts = cut_points(kept, adjacent)
        best, best_score, best_drop = None, 0.0, 0.0
        blocks = {}
        for v in kept:
            blocks.setdefault(comp[v], set()).add(v)
        for n in kept:
            if cost[n] > left:
                continue
            # Its own pairs go with it.
            drop = sum(v for j, v in p.get(n, {}).items() if j != n and j in kept and comp[j] == comp[n]) \
                + sum(v for i, v in p_in.get(n, {}).items() if i != n and i in kept and comp[i] == comp[n])
            if n in cuts:                       # it splits its block: add the pairs between the parts
                block = blocks[comp[n]] - {n}
                sub = components(block, adjacent)
                sizes = {}
                for v in sub.values():
                    sizes[v] = sizes.get(v, 0) + 1
                largest = max(sizes, key=sizes.get)
                # Every split pair has an end outside the largest part: count from those ends only.
                for i in block:
                    if sub[i] == largest:
                        continue
                    drop += sum(v for j, v in p.get(i, {}).items() if j in block and sub[j] != sub[i])
                    drop += sum(v for j, v in p_in.get(i, {}).items() if j in block and sub[j] == largest)
            if drop / cost[n] > best_score:
                best, best_score, best_drop = n, drop / cost[n], drop
        if best is None:
            return chosen
        chosen.append((best, best_drop))
        kept.discard(best)
        left -= cost[best]


# ---------- Check of the simulation ----------

def ranks(values):
    order = sorted(range(len(values)), key=values.__getitem__)
    out, i = [0.0] * len(values), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2
        i = j + 1
    return out


def spearman(a, b):
    """Rank correlation; None when either side is constant."""
    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va, vb = sum((x - ma) ** 2 for x in ra), sum((y - mb) ** 2 for y in rb)
    return cov / math.sqrt(va * vb) if va and vb else None


# ---------- The request ----------

def bounds(r, c, size):
    dlat, dlon = size
    return [round(c * dlon, 5), round(r * dlat, 5), round((c + 1) * dlon, 5), round((r + 1) * dlat, 5)]


def run(bbox, budget_km2, wind_ms=None, wind_from=None, runs=10_000, seed=1):
    name, _ = choose_size(bbox)
    out = search(load(bbox, name), SIZES[name], budget_km2, wind_ms, wind_from, runs, seed)
    out["summary"]["size"] = name
    return out


def search(cells, size, budget_km2, wind_ms, wind_from, runs, seed):
    if not 1 <= runs <= MAX_RUNS:
        raise BadRequest(f"runs must be between 1 and {MAX_RUNS:,}")
    nodes = {k for k, a in cells.items() if a["lc"] in P_VEG}
    ignitions = [k for k in nodes if cells[k]["ignitions"]]
    if not ignitions:
        raise BadRequest("No fire started in this area in 2000-2025 on land that can burn, so there is nothing to simulate.")
    weights, acc = [], 0
    for k in ignitions:
        acc += cells[k]["ignitions"]
        weights.append(acc)
    jumps = factors(cells, size, wind_ms, wind_from)
    target = sum(cells[k]["size_sum"] for k in ignitions) / acc
    p_h = calibrate(jumps, ignitions, weights, target, seed)
    burn, reach, mean_size = simulate(jumps, ignitions, weights, p_h, runs, seed)

    p = {i: {j: n / runs for j, n in row.items()} for i, row in reach.items()}
    p_in = {}
    for i, row in p.items():
        for j, v in row.items():
            p_in.setdefault(j, {})[i] = v
    adjacent = {k: [nb for nb, _ in jumps[k]] for k in nodes}
    cost = {k: cell_km(k[0], size)[0] * cell_km(k[0], size)[1] for k in nodes}
    if budget_km2 > MAX_TREATED * max(cost.values()) * 1.01:
        raise BadRequest(f"At this cell size one search treats at most {MAX_TREATED} cells "
                         f"(about {round(MAX_TREATED * max(cost.values())):,} km2): choose a smaller area to treat or zoom out.")
    chosen = greedy(nodes, adjacent, p, p_in, cost, budget_km2)

    before = objective(nodes, components(nodes, adjacent), p)
    kept = nodes - {k for k, _ in chosen}
    after = objective(kept, components(kept, adjacent), p)
    order = sorted(nodes)
    winds = [cell_wind(cells[k], wind_ms, wind_from) for k in ignitions]
    east = sum(w[0] * math.sin(math.radians(w[1])) for w in winds)
    north = sum(w[0] * math.cos(math.radians(w[1])) for w in winds)
    fallback = sum(1 for k in nodes if (wind_ms is None and cells[k].get("wind_ms") is None)
                   or (wind_from is None and cells[k].get("wind_from") is None))
    check = spearman([burn.get(k, 0) for k in order], [cells[k]["burned"] for k in order]) if len(order) > 2 else None
    return {
        "cells": [{"bounds": bounds(*k, size), "burn_probability": round(burn.get(k, 0) / runs, 5),
                   "ignitions": cells[k]["ignitions"], "fires_seen": cells[k]["burned"], "vegetation": vegetation(cells[k]["lc"]),
                   "wind_ms": round(cell_wind(cells[k], wind_ms, wind_from)[0], 1),
                   "wind_from": compass(cell_wind(cells[k], wind_ms, wind_from)[1])}
                  for k in order],
        "critical": [{"rank": n + 1, "bounds": bounds(*k, size), "drop": round(d, 6),
                      "share": round(d / before, 4) if before else 0, "km2": round(cost[k], 1),
                      "burn_probability": round(burn.get(k, 0) / runs, 5), "vegetation": vegetation(cells[k]["lc"])}
                     for n, (k, d) in enumerate(chosen)],
        "summary": {
            "cells": len(cells), "burnable": len(nodes), "runs": runs, "seed": seed,
            "wind_per_cell": wind_ms is None or wind_from is None, "wind_fallback_cells": fallback,
            "wind_ms": round(sum(w[0] for w in winds) / len(winds), 1),
            "wind_from": compass(math.degrees(math.atan2(east, north)) % 360), "p_h": round(p_h, 5),
            "mean_size_target": round(target, 3), "mean_size_simulated": round(mean_size, 3),
            "objective_before": round(before, 6), "objective_after": round(after, 6),
            "reduction": round(1 - after / before, 4) if before else 0,
            "treated_km2": round(sum(cost[k] for k, _ in chosen), 1), "budget_km2": budget_km2,
            "check_spearman": None if check is None else round(check, 3),
        },
    }


def self_check():
    # Two blocks of forest joined by one bridge cell. Fires here are large (real mean size above the
    # landscape, so p_h is at its cap): with a budget of one cell the greedy treats the bridge.
    def landscape(size):
        def cell(lc=1, ign=0):
            return {"lc": lc, "treecover": 50, "elevation": 0, "ignitions": ign, "size_sum": size * ign,
                    "burned": ign, "wind_ms": 2.0, "wind_from": 270}
        cells = {}
        for r in range(400, 403):
            for c in range(-1000, -997):
                cells[(r, c)] = cell(ign=5)
                cells[(r, c + 4)] = cell(ign=5)
            cells[(r, -997)] = cell(lc=17)      # water between the blocks
        cells[(401, -997)] = cell()             # the bridge
        return cells
    size = SIZES[10]
    one_cell = cell_km(401, size)[0] * cell_km(401, size)[1] + 1
    out = search(landscape(30), size, budget_km2=one_cell, wind_ms=0.0, wind_from=270, runs=500, seed=3)
    assert [c["bounds"] for c in out["critical"]] == [bounds(401, -997, size)], out["critical"]
    s = out["summary"]
    assert 0 < s["objective_after"] < s["objective_before"], s
    # Small fires: the calibrated p_h gives the real mean size.
    s = search(landscape(3), size, budget_km2=one_cell, wind_ms=0.0, wind_from=270, runs=3000, seed=3)["summary"]
    assert abs(s["mean_size_simulated"] - s["mean_size_target"]) < 0.5, s
    # Per-cell wind: a cell's own wind where the request sets none; downwind jumps are likelier than upwind ones.
    assert cell_wind({"wind_ms": 5.0, "wind_from": 90}, None, None) == (5.0, 90)
    assert cell_wind({"wind_ms": None, "wind_from": None}, None, None) == FALLBACK_WIND
    assert cell_wind({"wind_ms": 5.0, "wind_from": 90}, None, 270) == (5.0, 270)
    land = landscape(3)
    two = {(400, -1000): land[(400, -1000)] | {"wind_ms": 8.0, "wind_from": 270},
           (400, -999): land[(400, -999)] | {"wind_ms": 8.0, "wind_from": 270}}
    jumps = factors(two, size, None, None)
    assert dict(jumps[(400, -1000)])[(400, -999)] > dict(jumps[(400, -999)])[(400, -1000)]
    # Cut points of a path a-b-c: only b.
    adj = {"a": ["b"], "b": ["a", "c"], "c": ["b"]}
    assert cut_points({"a", "b", "c"}, adj) == {"b"}
    assert spearman([1, 2, 3], [10, 20, 30]) == 1.0


if __name__ == "__main__":
    self_check()
    print("critical ok")
