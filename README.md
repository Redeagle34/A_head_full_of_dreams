# A head full of dreams

NASA Space Apps Challenge 2026, "MODIS and VIIRS hot spots".

A burning calendar for the United States (contiguous states and Hawaii): weekly
fire activity seen by satellite since 2002, in one comparable unit, with unusual
weeks, record weeks and the usual fire season marked for every state.

Intended users: firefighters, scientists, land managers and early-warning teams.

## The problem

MODIS (since 2000) and VIIRS (since 2012) both detect active fires, but they do
not count the same thing. VIIRS has smaller pixels and reports about four times
more detections than MODIS for the same fires. A long record that switches from
one sensor to the other shows a jump that is not real. The calendar needs one
unit across the whole period.

## Approach in short

1. Download every FIRMS detection for the U.S. (13.4 million rows, 2000–2025).
2. Count **active cell-days**: the number of 0.1° grid cells with at least one
   vegetation-fire detection on a given day. One large fire with hundreds of
   detections counts once per cell per day.
3. Convert VIIRS to **MODIS-equivalent** units with a fire-radiative-power
   observation operator: for each VIIRS fire, the probability that MODIS on the
   Aqua satellite would have detected it.
4. Compare every week with the same weeks in other years to flag unusual weeks.
5. Show it on a static web page.

## Repository structure

```
pipeline/
  ingest.py           step 2  download FIRMS archive, store as Parquet
  calendar_table.py   step 3  assign states, build state x week x sensor table
  harmonize.py        step 4  VIIRS -> MODIS-equivalent, scored on withheld years
  export_web.py       step 5  data files for the website, unusual-week flags
web/
  index.html          the calendar page (MapLibre + Observable Plot, no build step)
  data/               calendar.json, states.geojson (generated, committed)
data/                 raw CSV and Parquet (generated, not in git, about 1.6 GB)
proofs/               early feasibility scripts and their saved results
.project/
  SPEC.md             plan, decisions and measured results for every step
  research/           background research, sources and findings
requirements.txt      duckdb
```

## Pipeline

```
FIRMS yearly CSV ──ingest──> data/parquet/sensor=…/year=…/data.parquet
                                   │
Census state borders ──calendar_table──> data/calendar/calendar.parquet
                                   │     data/calendar/detections.parquet
                                   │
                         harmonize ──> data/calendar/harmonized.parquet
                                   │
                        export_web ──> web/data/calendar.json
                                       web/data/states.geojson ──> web/index.html
```

| Script | Input | Output | Run time |
|---|---|---|---|
| `ingest.py` | FIRMS country archive, U.S. files | Parquet per sensor and year, Alaska removed | about 20 minutes (download) |
| `calendar_table.py` | Parquet, U.S. Census state borders | weekly table per state and series; state-tagged detections | about 4 minutes |
| `harmonize.py` | state-tagged detections | weekly MODIS-equivalent values with standard deviation | seconds |
| `export_web.py` | calendar and harmonized tables | website data with flags and typical ranges | seconds |

Every script can be run again safely: it rebuilds its output from its input and
prints its own checks.

Storage is Parquet files queried with DuckDB. No database server is needed. A
PostGIS database is planned for the nearby-search step.

## Data sources

| Source | Used for | Period |
|---|---|---|
| [NASA FIRMS country archive](https://firms.modaps.eosdis.nasa.gov/country/) MODIS Collection 6.1 | Terra and Aqua detections | Nov 2000 – Dec 2025 |
| FIRMS VIIRS 375 m, S-NPP | detections | Jan 2012 – Dec 2025 |
| FIRMS VIIRS 375 m, NOAA-20 | detections | Apr 2018 – Dec 2025 |
| [U.S. Census cartographic boundaries 2023](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html), 1:500,000 | state assignment | — |

Only detections of FIRMS type 0 (presumed vegetation fire) are counted. Volcanoes,
static land sources and offshore sources stay in the stored data.

## Harmonization method

Based on the observation operator of M. Sofiev, Finnish Meteorological Institute
(IS4FIRES v3.0, [fmidev/FRP_OOp](https://github.com/fmidev/FRP_OOp)). This
repository re-implements the published formula; it contains no code from that
project.

- A sensor detects a fire when its radiative power exceeds a detection limit
  that grows with pixel area. MODIS pixels are larger, so MODIS misses small fires.
- VIIRS 375 m pixels are merged into clusters about the size of one MODIS pixel
  and their power is added.
- For each cluster the operator gives the probability that MODIS would detect
  it. Probabilities are summed, not sampled, so results are repeatable.
- The conversion goes from VIIRS to MODIS only. Fires that MODIS never saw
  cannot be reconstructed.
- The reference is Aqua, not Terra + Aqua, because Aqua and VIIRS pass at
  similar local times.
- A day on which a satellite has no detection anywhere in the country is treated
  as not observed, never as "no fire". When both VIIRS satellites work, they are
  averaged.

### Measured accuracy

Withheld years 2021–2025, state-week level, against real Aqua, on days both
sensors observed. Error = sum of absolute differences / Aqua total.

| Method | Error | Total / Aqua |
|---|---|---|
| VIIRS raw | 3.06 | 4.06 |
| VIIRS × one multiplier | 0.52 | 1.06 |
| VIIRS × multiplier per state and season | 0.37 | 1.08 |
| Operator, published coefficients, no fitting | 0.32 | 1.01 |
| Both VIIRS satellites, operator × state-season factor (used) | 0.27 | 1.05 |

Multipliers and factors were fit on 2013–2020 only.

## Calendar values and flags

Value per state and week, in MODIS (Aqua) active cell-days:

- Aqua observed all 7 days: the Aqua count.
- Aqua incomplete, VIIRS complete: the MODIS-equivalent value from VIIRS.
- Neither complete: scaled up from the observed days.

Each week is compared with the same week, one before and one after, in all other
years for that state:

- **Unusual**: above 90% of those weeks, and at least 5 cell-days.
- **Record**: above all of them, and at least 5 cell-days.
- **Usual fire season**: weeks of the year whose long-term mean is at least half
  of the state's peak week.

## Run

```bash
pip install -r requirements.txt
```

```bash
python pipeline/ingest.py
```

```bash
python pipeline/calendar_table.py
```

```bash
python pipeline/harmonize.py
```

```bash
python pipeline/export_web.py
```

```bash
python -m http.server 8765 --directory web
```

Then open http://localhost:8765. The website data in `web/data/` is committed, so
the last command alone is enough to view the calendar.

## Known limits

- **Regions are whole states.** One large fire in a big state may not stand out.
  The Park Fire week (22 July 2024, California) ranks at the 90% level but is not
  flagged.
- **Hawaii is unreliable.** Lava from Kilauea is recorded as vegetation fire and
  VIIRS sees it far more often than MODIS. Hawaii is also not drawn on the map
  (state list only).
- **2000–2002 is not shown.** Those years have Terra only, and Terra is not
  converted to Aqua units.
- **2026 is missing.** FIRMS has no yearly file yet; recent months need the FIRMS
  API with a MAP_KEY (kept in `.env`, never in git).
- **Clouds and partial outages are not modeled.** No detection under cloud looks
  like no fire. The standard deviation covers detection chance only.
- **Grid cells are 0.1° in latitude and longitude**, not equal-area.
- The operator coefficients are global; by state the unfitted result ranges from
  0.78 (North Carolina) to 1.38 (Arizona) of Aqua.

## Roadmap

| Step | Status |
|---|---|
| 1. Archive access | done |
| 2. Full ingest | done |
| 3. Calendar table | done |
| 4. Harmonization | done |
| 5. Calendar screen | built; Park Fire check not passed at state level |
| 6. Downloads: CSV and report | next |
| 7. Nearby map for firefighters | planned |
| 8. Landsat 30 m cross-check layer | planned |
| 9. Seven-day forecast | planned |
| 10. Prevention and context layers (fuels, treatments, smoke, vegetation, aircraft) | planned |

Later versions: Alaska, Mexico and other regions.

Details, decisions and results for every step: [.project/SPEC.md](.project/SPEC.md).
