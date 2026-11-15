"""Critical nodes: which cells to treat with prescribed burns so a wildfire spreads as little as possible.

Plan and sources: CriticalNode.md. In short:

1. Landscape: the 0.1 degree cells of the area on screen (pipeline/critical_landscape.py). Each cell is
   a node; fire can pass between the 8 neighbours of a cell.
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
  MAX_NODES, MAX_RUNS, MAX_BUDGET_KM2   the largest search one request may ask for
"""
import math
import os
import pathlib
import random

import duckdb

from .config import ROOT
from .events import LAND_COVER

LANDSCAPE = pathlib.Path(os.environ.get("FIRE_EVENTS_DIR", ROOT / "data" / "events")) / "landscape.parquet"
CELL = 0.1                      # degrees
KM_PER_DEGREE = 111.32
MAX_NODES = 2500                # about 5 x 5 degrees
MAX_RUNS = 20_000
MAX_BUDGET_KM2 = 5000           # about 50 cells: the greedy re-checks the area once per treated cell
CALIBRATION_RUNS = 2000
CALIBRATION_STEPS = 14

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
    """landscape.parquet is not built yet."""


def p_den(lc, treecover):
    """Vegetation density (Alexandridis: sparse -0.4, normal 0, dense 0.3), from tree cover in forests only."""
    if lc not in FOREST or treecover is None:
        return 0.0
    return -0.4 if treecover < 30 else 0.3 if treecover > 60 else 0.0


def vegetation(lc):
    return LAND_COVER.get(lc, "No land cover record") + ("" if lc in P_VEG else " (does not burn here)")


def cell_km(row):
    """(north-south, east-west) size of a cell in km."""
    return CELL * KM_PER_DEGREE, CELL * KM_PER_DEGREE * math.cos(math.radians((row + 0.5) * CELL))


# ---------- Landscape ----------

def load(bbox):
    """The cells of a view: {(row, col): {...}}."""
    if not LANDSCAPE.exists():
        raise Missing("landscape.parquet is missing. Run: python pipeline/critical_landscape.py")
    west, south, east, north = bbox
    r0, r1 = math.floor(south / CELL), math.floor(north / CELL)
    c0, c1 = math.floor(west / CELL), math.floor(east / CELL)
    if (r1 - r0 + 1) * (c1 - c0 + 1) > MAX_NODES * 2:
        raise BadRequest(f"The area is too large for the search: zoom in to at most about {MAX_NODES:,} cells of 0.1 degree.")
    cur = duckdb.connect().execute(
        f"SELECT * FROM '{LANDSCAPE.as_posix()}' WHERE row BETWEEN ? AND ? AND col BETWEEN ? AND ?", [r0, r1, c0, c1])
    names = [d[0] for d in cur.description]
    cells = {(r["row"], r["col"]): r for r in (dict(zip(names, v)) for v in cur.fetchall())}
    burnable = sum(1 for c in cells.values() if c["lc"] in P_VEG)
    if burnable > MAX_NODES:
        raise BadRequest(f"The area holds {burnable:,} cells that can burn; zoom in to at most {MAX_NODES:,}.")
    return cells


def factors(cells, wind_ms, wind_from):
    """Static part of p_burn for every jump: {cell: [(neighbour, factor)]}, so p_burn = min(1, p_h * factor)."""
    toward = math.radians(wind_from + 180)                  # wind from the west blows toward the east
    out = {}
    for (r, c), a in cells.items():
        if a["lc"] not in P_VEG:
            continue
        ns, ew = cell_km(r)
        jumps = []
        for dr, dc in NEIGHBOURS:
            nb = cells.get((r + dr, c + dc))
            if nb is None or nb["lc"] not in P_VEG:
                continue
            north_km, east_km = dr * ns, dc * ew
            dist_m = math.hypot(north_km, east_km) * 1000
            theta = math.atan2(east_km, north_km) - toward      # spread direction against the wind
            p_wind = math.exp(wind_ms * (C1 + C2 * (math.cos(theta) - 1)))
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
    """p_h so the simulated fires have the mean size `target` (in cells). Bisection, same random numbers each step."""
    max_f = max((f for js in jumps.values() for _, f in js), default=1.0)
    lo, hi = 0.0, 1.0 / max_f
    if simulate(jumps, ignitions, weights, hi, CALIBRATION_RUNS, seed)[2] <= target:
        return hi
    for _ in range(CALIBRATION_STEPS):
        mid = (lo + hi) / 2
        if simulate(jumps, ignitions, weights, mid, CALIBRATION_RUNS, seed)[2] < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


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
        for n in kept:
            if cost[n] > left:
                continue
            if n in cuts:                       # may split its block: count again without it
                block = {v for v in kept if comp[v] == comp[n]} - {n}
                sub = components(block, adjacent)
                before = sum(v for i in block | {n} for j, v in p.get(i, {}).items()
                             if j != i and j in kept and comp[j] == comp[n])
                after = sum(v for i in block for j, v in p.get(i, {}).items()
                            if j != i and j in block and sub[j] == sub[i])
                drop = before - after
            else:                               # removes only its own pairs
                drop = sum(v for j, v in p.get(n, {}).items() if j != n and j in kept and comp[j] == comp[n]) \
                     + sum(v for i, v in p_in.get(n, {}).items() if i != n and i in kept and comp[i] == comp[n])
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

def bounds(r, c):
    return [round(c * CELL, 4), round(r * CELL, 4), round((c + 1) * CELL, 4), round((r + 1) * CELL, 4)]


def run(bbox, budget_km2, wind_ms=None, wind_from=270.0, runs=10_000, seed=1):
    cells = load(bbox)
    return search(cells, budget_km2, wind_ms, wind_from, runs, seed)


def search(cells, budget_km2, wind_ms, wind_from, runs, seed):
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
    if wind_ms is None:                         # the usual wind on the first day of the fires here
        winds = sorted(cells[k]["wind"] for k in ignitions if cells[k]["wind"] is not None)
        wind_ms = winds[len(winds) // 2] if winds else 3.0
    jumps = factors(cells, wind_ms, wind_from)
    target = sum(cells[k]["size_sum"] for k in ignitions) / acc
    p_h = calibrate(jumps, ignitions, weights, target, seed)
    burn, reach, mean_size = simulate(jumps, ignitions, weights, p_h, runs, seed)

    p = {i: {j: n / runs for j, n in row.items()} for i, row in reach.items()}
    p_in = {}
    for i, row in p.items():
        for j, v in row.items():
            p_in.setdefault(j, {})[i] = v
    adjacent = {k: [nb for nb, _ in jumps[k]] for k in nodes}
    cost = {k: cell_km(k[0])[0] * cell_km(k[0])[1] for k in nodes}
    chosen = greedy(nodes, adjacent, p, p_in, cost, budget_km2)

    before = objective(nodes, components(nodes, adjacent), p)
    kept = nodes - {k for k, _ in chosen}
    after = objective(kept, components(kept, adjacent), p)
    order = sorted(nodes)
    check = spearman([burn.get(k, 0) for k in order], [cells[k]["burned"] for k in order]) if len(order) > 2 else None
    return {
        "cells": [{"bounds": bounds(*k), "burn_probability": round(burn.get(k, 0) / runs, 5),
                   "ignitions": cells[k]["ignitions"], "fires_seen": cells[k]["burned"], "vegetation": vegetation(cells[k]["lc"])}
                  for k in order],
        "critical": [{"rank": n + 1, "bounds": bounds(*k), "drop": round(d, 6),
                      "share": round(d / before, 4) if before else 0, "km2": round(cost[k], 1),
                      "burn_probability": round(burn.get(k, 0) / runs, 5), "vegetation": vegetation(cells[k]["lc"])}
                     for n, (k, d) in enumerate(chosen)],
        "summary": {
            "cells": len(cells), "burnable": len(nodes), "runs": runs, "seed": seed,
            "wind_ms": round(wind_ms, 1), "wind_from": wind_from, "p_h": round(p_h, 5),
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
                    "burned": ign, "wind": 2.0}
        cells = {}
        for r in range(400, 403):
            for c in range(-1000, -997):
                cells[(r, c)] = cell(ign=5)
                cells[(r, c + 4)] = cell(ign=5)
            cells[(r, -997)] = cell(lc=17)      # water between the blocks
        cells[(401, -997)] = cell()             # the bridge
        return cells
    one_cell = cell_km(401)[0] * cell_km(401)[1] + 1
    out = search(landscape(30), budget_km2=one_cell, wind_ms=0.0, wind_from=270, runs=500, seed=3)
    assert [c["bounds"] for c in out["critical"]] == [bounds(401, -997)], out["critical"]
    s = out["summary"]
    assert 0 < s["objective_after"] < s["objective_before"], s
    # Small fires: the calibrated p_h gives the real mean size.
    s = search(landscape(3), budget_km2=one_cell, wind_ms=0.0, wind_from=270, runs=3000, seed=3)["summary"]
    assert abs(s["mean_size_simulated"] - s["mean_size_target"]) < 0.5, s
    # Cut points of a path a-b-c: only b.
    adj = {"a": ["b"], "b": ["a", "c"], "c": ["b"]}
    assert cut_points({"a", "b", "c"}, adj) == {"b"}
    assert spearman([1, 2, 3], [10, 20, 30]) == 1.0


if __name__ == "__main__":
    self_check()
    print("critical ok")
