# Critical Nodes and Fire Spread Simulation

Prevention module for the harmonized MODIS/VIIRS burning calendar. It determines which cells are worth treating with preventive burns to fragment the fire's spread routes across the landscape.

This document explains, in order: the paper it is based on, the objective function, how the weight probabilities are computed with a Monte Carlo simulation, the selection heuristic, and how it integrates with the current project.

---

## 1. The base paper

**Yemshanov, D., Liu, N., Thompson, D. K., Parisien, M-A., Barber, Q. E., Koch, F. H., Reimer, J. (2021). *Detecting critical nodes in forest landscape networks to reduce wildfire spread*. PLOS ONE 16(10): e0258060.**
[https://doi.org/10.1371/journal.pone.0258060](https://doi.org/10.1371/journal.pone.0258060) (open access, CC0)

### What it solves

Given a limited budget of area to treat, it decides **which patches to burn preventively so that a wildfire spreads as little as possible** across the landscape.

### How it models the landscape

The landscape is represented as a network (graph):
- **Node** = a land patch. In the paper, 1 km² hexagons. In this project, cells of the 0.1° grid.
- **Edge** = a connection exists between two patches if fire can spread from one to the other.
- **p_ij** = probability that a fire started in patch i reaches patch j.

Treating a node (a controlled burn) is equivalent to **removing it from the network** along with its connections. By removing the right patches, the network breaks into disconnected blocks and the fire can no longer cross from one side to the other.

### Where the p_ij come from in the original paper

The paper uses the **Burn-P3** simulator: it generates thousands of fires with realistic ignition, weather, and spread (Canadian FBP engine), and counts, for each pair of cells, how many times a fire started in one reached the other. We do not have Burn-P3 or its calibrated input layers, so we replace that part with our own Monte Carlo simulation (see section 3).

---

## 2. The objective function

The problem is **Critical Node Detection** (CND). The paper's central formulation (its Equation 5) is:

```
minimize    SUM_i SUM_{j != i}  u_ij * p_ij

subject to: SUM_i  c_i * (1 - x_i)  <=  B
```

### Variables

| Symbol | Meaning |
|---|---|
| `x_i` | Binary. 1 if cell i is kept, 0 if it is burned (removed from the network). |
| `u_ij` | Binary. 1 if i and j are both kept and still connected by a fire route. |
| `p_ij` | Fire spread probability from i to j. This is the **weight**. |
| `c_i` | Cost (area) of treating cell i. |
| `B` | Budget: maximum area that can be burned. |

### What it means

The objective function **minimizes the expected number of cell pairs that remain connected by a route the fire can travel**, weighted by the spread probability. Each burn breaks connections and lowers that total. The constraint limits how many cells can be treated.

The weight `p_ij` is what makes the solution prioritize cutting the **most likely** spread routes, not just any route. That is why computing the p_ij well is the step that matters most, and it is what the Monte Carlo simulation does.

---

## 3. Computing the p_ij weights with Monte Carlo

We do not use Burn-P3. We build a **Monte Carlo fire spread simulator based on a cellular automaton**: we ignite thousands of virtual fires, let them spread cell by cell under probabilistic rules, and count.

### Input layers

| Ingredient | Source | Role |
|---|---|---|
| Ignition density | FIRMS history per cell (already in the project) | Where a fire is most likely to start |
| Flammability | Land cover (ESA WorldCover or MODIS MCD12Q1) | Forest burns differently than desert |
| Slope | Elevation model (SRTM or Copernicus DEM) | Fire climbs uphill faster |
| Wind | NASA POWER or ERA5 | Spread direction and speed |

The minimal version uses only ignition and flammability. Wind and slope are added afterward.

### The spread model

For each simulated fire:
1. Ignite a cell, chosen at random with probability proportional to its historical ignition density.
2. The fire tries to pass to neighboring cells. The jump probability to a neighbor depends on: the neighbor's flammability, whether the slope rises toward it, and whether the wind blows in that direction.
3. Repeat the spread until the fire passes to no neighbor (it dies out).
4. Record which cells burned and which jumps occurred.

Core of the simulator:

```python
import numpy as np

def spread_once(ignition, flammability, slope_factor, wind_factor, rng):
    """One simulated fire. Returns the burned cells and the i->j jumps."""
    burning = {ignition}
    burned = set()
    frontier = [ignition]
    jumps = []
    while frontier:
        c = frontier.pop()
        burned.add(c)
        for nb in neighbors(c):
            if nb in burned:
                continue
            # jump probability: fuel x slope x wind
            p = flammability[nb] * slope_factor(c, nb) * wind_factor(c, nb)
            if rng.random() < p:
                jumps.append((c, nb))        # counts toward p_ij
                if nb not in burning:
                    burning.add(nb)
                    frontier.append(nb)
    return burned, jumps
```

### From jumps to probabilities

`spread_once` is run many times (5,000 to 10,000):

- **Burn probability** of a cell = (times it appears in `burned`) / (total runs). This is a risk heat map.
- **p_ij** = (times the jump i -> j occurred) / (total runs). This is the weight that enters the objective function.

The probabilities are obtained by **counting frequencies**, which is stochastic but converges: more runs, more stable. The simulator is not a heuristic, it is a Monte Carlo method (repeated random sampling).

### Validation

The simulated burn probability is compared against the real FIRMS fire history. If the areas the simulator says burn the most match where FIRMS actually saw more fire, the model is credible. This is the same logic the paper used to validate Burn-P3 against the national fire database.

---

## 4. The critical node selection heuristic

Yes, a heuristic goes here. The paper solves the objective function with an exact solver (GUROBI), which guarantees the optimum but is slow and requires a license. For this project we use a **greedy heuristic**: fast, no paid dependencies, and good enough for a demo.

### How the greedy works

Repeat, until the budget is exhausted:
1. For each candidate cell, compute how much the network connectivity would drop if it were removed.
2. Remove the cell that drops it the most.
3. Repeat.

```python
import networkx as nx

def critical_nodes(G, budget):
    """G: nodes = cells, edges weighted by p_ij. budget: cells to treat."""
    chosen = []
    H = G.copy()
    for _ in range(budget):
        base = sum(len(c) * (len(c) - 1) for c in nx.connected_components(H))
        best, best_drop = None, -1
        for n in list(H.nodes):
            T = H.copy()
            T.remove_node(n)
            after = sum(len(c) * (len(c) - 1) for c in nx.connected_components(T))
            drop = base - after
            if drop > best_drop:
                best, best_drop = n, drop
        chosen.append(best)
        H.remove_node(best)
    return chosen
```

### Honesty about the heuristic

The greedy gives a **good, not necessarily optimal** solution. It can get stuck in a local optimum. It is a deliberate trade-off: we exchange the optimality guarantee for speed and simplicity. This is stated plainly in the pitch.

---

## 5. Integration with the current project

The module sits on top of the existing architecture without breaking it.

```
pipeline/
  layers.py          download and clip land cover, slope, and wind to the 0.1 degree grid
  simulate.py        run the Monte Carlo -> burn_prob.parquet and spread.parquet
  critical_nodes.py  read spread.parquet, run the greedy -> critical.parquet
server/
  queries.py         + SQL for the new layers
  main.py            + route GET /api/critical?bbox&budget
web/
  app.js             + "critical cells" layer and + "burn probability" layer
data/
  layers.parquet, burn_prob.parquet, spread.parquet, critical.parquet
```

Flow:

```
FIRMS (ignition density) ┐
land cover, slope, wind  ┼─ simulate.py ─> burn_prob.parquet
                         │                 spread.parquet ─ critical_nodes.py ─> critical.parquet
                         │                                                            │
                                                                   server /api/critical ─> web (map layer)
```

---

## References

- Yemshanov et al. (2021), *Detecting critical nodes in forest landscape networks to reduce wildfire spread*, PLOS ONE. [https://doi.org/10.1371/journal.pone.0258060](https://doi.org/10.1371/journal.pone.0258060)
- Matsypura, Prokopyev, Zahar (2018), *Wildfire fuel management: network-based models and optimization of prescribed burning*, European Journal of Operational Research 264(2):774-796. (original CND formulation)
- Parisien et al., Burn-P3, Canadian Forest Service. (reference simulator replaced here by our own Monte Carlo)