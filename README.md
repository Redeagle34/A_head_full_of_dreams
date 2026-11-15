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
5. Show it on a full-screen map: search a place, pick dates, zoom in, and read
   the fire layer and the history of the area on screen.

## The map page

- **Top bar:** place search, date range, quick dates and examples.
- **Filters:** satellite data (MODIS + VIIRS combined, VIIRS only, MODIS only,
  none) and what the color shows (fire intensity, days with fire, unusual versus
  normal).
- **Fire layer:** transparent colored squares over satellite imagery. Squares
  get finer as you zoom in, down to the finest size the data supports:

| Satellite data | Finest square | Period |
|---|---|---|
| VIIRS only | 375 m | 2012 – 2025 |
| MODIS only | 1 km | 2000 – 2025 |
| MODIS + VIIRS combined (MODIS-equivalent) | 1.5 km | 2002 – 2025 |

- **Area history:** weekly calendar of whatever is on screen, with unusual and
  record weeks, the usual fire season, and a CSV download.
- **State overview:** the earlier state-by-state calendar, at `/states.html`.

## Fires one by one, missed fires, satellites and the time bar

Added on the branch `fire-events-satellite-globe`. Method, sources and measured results:
[.project/research/notebooks/modis-viirs-burning-calendar/fire-events-validation-satellites.md](.project/research/notebooks/modis-viirs-burning-calendar/fire-events-validation-satellites.md).

- **Fires** button: every fire in view as one event, with first and last day, duration,
  area (from hotspots, from the MODIS burned-area map, and burn severity from Landsat),
  the vegetation that burned, pictures before and after, and the agency reports it matches.
  A switch shows reported wildfires that the satellites missed or that the prediction
  model did not expect.
- **Satellites** button, or zoom out: Terra, Aqua, Suomi NPP, NOAA-20, NOAA-21 and
  Landsat 8 in orbit as NASA 3D models. Pick one to see the strip it is scanning, the
  picture it takes of that ground (click to enlarge), its position, height, speed and
  viewing angle, and its next passes over the centre of the screen.
- **Time bar** at the bottom: type the dates, drag the period or its edges, make it
  shorter or longer, zoom the bar, and press Play to watch the map change through time.

| Script | Output | Needs |
|---|---|---|
| `pipeline/fire_events.py` | `data/events/events.parquet`, `event_cells.parquet` | `calendar_table.py` |
| `pipeline/event_enrich.py [project] [min_km2]` | `data/events/enrichment.parquet` (burned area, vegetation) | Earth Engine sign-in |
| `pipeline/missed_fires.py` | `data/events/reported_fires.parquet`, `missed_summary.json` | `lightgbm`, the models in `proofs/us-experiments/models/` |

| Route | Answers |
|---|---|
| `GET /api/events?bbox&start&end&min_km2` | fires in the box and dates, largest first |
| `GET /api/events/{id}` | one fire, its ground cells and nearby agency reports |
| `GET /api/events/{id}/sharp` | Landsat pictures before and after, burn severity (Earth Engine; set `EE_PROJECT` in `.env`) |
| `GET /api/reported?bbox&start&end&missed` | reported wildfires; `missed` is `satellite`, `model`, `both` or `all` |
| `GET /api/tle` | orbit data of the satellites (CelesTrak, cached 6 hours) |

## Repository structure

```
pipeline/               builds the data, in this order
  ingest.py             download FIRMS archive, store as Parquet
  calendar_table.py     assign states, build state x week x sensor table
  harmonize.py          VIIRS -> MODIS-equivalent, scored on withheld years
  export_web.py         data files for the state overview page
  build_db.py           data/fire.duckdb, the database the server reads
server/                 FastAPI application
  main.py               routes and input checks only
  queries.py            the SQL behind each route
  grid.py               map grid: cell size, cell of a point, cell bounds
  stats.py              typical range, unusual and record weeks
  db.py                 read-only DuckDB connection
  config.py             paths, limits, .env loading
web/
  index.html            map page: layout
  style.css             map page: appearance
  app.js                map page: behaviour (sections are listed at the top)
  states.html           state overview page
  data/                 calendar.json, states.geojson (generated, committed)
data/                   raw CSV, Parquet, fire.duckdb (generated, not in git)
proofs/                 early feasibility scripts and their saved results
.project/
  SPEC.md               plan, decisions and measured results for every step
  research/             background research, sources and findings
.env.example            template for .env (reserved place for FIRMS_MAP_KEY)
requirements.txt        duckdb, fastapi, uvicorn
```

## Server API

| Route | Answers |
|---|---|
| `GET /api/meta` | first and last day of each layer |
| `GET /api/cells?layer&bbox&start&end&metric` | colored grid cells for the view |
| `GET /api/calendar?layer&bbox` | weekly history of the area, with flags |
| `GET /api/detections.csv?layer&bbox&start&end` | observations behind the layer |

`layer` is `viirs`, `modis` or `both`; `bbox` is `west,south,east,north`;
`metric` is `intensity`, `days` or `unusual`. Interactive documentation is at
`/docs` when the server runs.

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
                                       web/data/states.geojson ──> web/states.html

data/calendar/detections.parquet ──build_db──> data/fire.duckdb ──server──> web/index.html
```

| Script | Input | Output | Run time |
|---|---|---|---|
| `ingest.py` | FIRMS country archive, U.S. files | Parquet per sensor and year, Alaska removed | about 20 minutes (download) |
| `calendar_table.py` | Parquet, U.S. Census state borders | weekly table per state and series; state-tagged detections | about 4 minutes |
| `harmonize.py` | state-tagged detections | weekly MODIS-equivalent values with standard deviation | seconds |
| `export_web.py` | calendar and harmonized tables | state overview data with flags and typical ranges | seconds |
| `build_db.py` | state-tagged detections | `fire.duckdb` with the three map layers (156 MB) | seconds |

Every script can be run again safely: it rebuilds its output from its input and
prints its own checks.

Storage is Parquet files and one DuckDB file. The server opens the DuckDB file
read-only; map queries answer in well under a second. A PostGIS database can be
added if a later step needs it.

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
python pipeline/build_db.py
```

```bash
python -m uvicorn server.main:app --port 8780
```

Then open http://localhost:8780. The data must be built once (first five
commands, about 25 minutes, mostly download); after that only the last command
is needed.

## Known limits

- **Whole-state calendars hide single fires.** On the state overview page the
  Park Fire week (22 July 2024, California) is not flagged. On the map page, the
  history of the Park Fire area flags it as a record week.
- **Hawaii is unreliable.** Lava from Kilauea is recorded as vegetation fire and
  VIIRS sees it far more often than MODIS.
- **The combined layer starts in July 2002.** Before that only Terra flew, and
  Terra is not converted to Aqua units. MODIS only goes back to November 2000.
- **Single-sensor layers are not comparable over time.** "VIIRS only" has one
  satellite until 2018 and two after; "MODIS only" has one until 2002. Use the
  combined layer to compare years.
- **Colors are relative to the view.** The scale stretches to the squares on
  screen, so the same color can mean different values after zooming.
- **Third-party services.** Satellite imagery comes from Esri World Imagery,
  map labels from OpenFreeMap, place search from OpenStreetMap Nominatim. Their
  terms and rate limits apply.
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
| 5. Calendar screen | done as the map page; Park Fire area flagged as a record week |
| 6. Downloads: CSV and report | CSV done; report planned |
| 7. Nearby map for firefighters | place search and "my location" done; radius search planned |
| 8. Landsat 30 m cross-check layer | planned |
| 9. Seven-day forecast | planned |
| 10. Prevention and context layers (fuels, treatments, smoke, vegetation, aircraft) | planned |

Later versions: Alaska, Mexico and other regions.

Details, decisions and results for every step: [.project/SPEC.md](.project/SPEC.md).
