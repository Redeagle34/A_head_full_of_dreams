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
- **Fires:** one list of fires, the same in the panel and as markers on the map,
  colored by danger level like U.S. fire danger signs (green, blue, yellow, orange,
  red). Show the fires on screen (largest first) or around a point: choose my
  location, the map centre or a click, and a distance; the most dangerous come
  first, then the nearest. Click a fire for its rating and its details.
- **State overview:** the earlier state-by-state calendar, at `/states.html`.

## Fire danger rating

Each fire gets three factors, always shown apart:

1. **Chance of getting large**: one of five levels, from the chance that the
   fire reaches 1,000 acres, judged after two days of satellite passes.
2. **What is exposed**: built-up surface within 5 km of where it started.
3. **What the satellites saw**: footprint, growth on day 2, peak radiative
   power, night burning, and the weather of the first day in plain words.

What the levels meant in 2022-2025, years the model never saw:

| Level | Fires | Reached 1,000 acres |
|---|---|---|
| Low | 513,427 | 0.07% |
| Moderate | 19,635 | 2.2% |
| High | 5,606 | 7.7% |
| Very High | 1,098 | 24% |
| Extreme | 4,021 | 96% |

The rating is a suggestion to help decide where to look first. It is not a
dispatch order.

How it is made:

- **Fires**: VIIRS detections that touch in space (cells of about 1.6 km) and
  time (gaps of up to 2 days) are one fire: 1,517,969 fires, 2012-2025.
- **Size**: the satellite footprint, on cells of about 440 m. Against agency
  reports of 100 acres or more it is 0.91 of the reported size (median).
- **Model**: gradient-boosted trees (LightGBM). Inputs: what the satellites saw
  on day 1 and day 2, weather and fuel dryness (gridMET), terrain, vegetation,
  fire regime and population. Trained on 2012-2020, tuned on 2021.
- **Score on 2022-2025**: ranks fires that are still under 1,000 acres on day 2
  by whether they get there with an AUC of 0.944 (satellite inputs alone 0.928,
  weather and place alone 0.859). Against agency-reported final size it scores
  0.912, where a weather-and-place model trained on reports scores 0.748.

The weather-and-place inputs and the comparison model come from the team's
experiments in branch `us-findings` (`proofs/us-experiments`).

### One definition of a fire on the page

The page lists one kind of fire: MODIS and VIIRS detections that touch on squares of
about 1 km and follow within 5 days (`pipeline/fire_events.py`). The danger model was
trained on a stricter grouping (VIIRS only, gaps of up to 2 days, above), and its inputs
and scores belong to that grouping. `pipeline/event_danger.py` carries each rating over:
every VIIRS detection lies in exactly one fire of each kind, so the two are matched by the
detections they share, and a fire takes the level of the rated group that holds most of
its VIIRS detections.

What still differs, and is said on the page:

- A fire can hold several rated groups (a pause of 3 to 5 days splits the groups but not
  the fire). Its page says when the rated group is only part of it.
- The rating's size is the footprint on squares of 440 m; the fire's area counts squares
  of 1 km from both sensors.
- Fires seen by MODIS only (all fires before 2012) and fires in Hawaii have no level.
- The table of what each level meant counts rated groups, not fires.

Training the model again on the fires of the page would remove these differences.
## Fires one by one, missed fires, satellites and the time bar

Added on the branch `fire-events-satellite-globe`. Method, sources and measured results:
[.project/research/notebooks/modis-viirs-burning-calendar/fire-events-validation-satellites.md](.project/research/notebooks/modis-viirs-burning-calendar/fire-events-validation-satellites.md).

- **Fires** button: every fire in view or around a point, with its danger level, first and last day, duration,
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
| `pipeline/event_danger.py` | `data/events/event_danger.parquet` (danger level of each fire) | `fire_events.py`, `danger_model.py` |

| Route | Answers |
|---|---|
| `GET /api/events?bbox&start&end&min_km2&min_level` | fires in the box and dates with their danger rating, largest first |
| `GET /api/events/near?lat&lon&km&start&end&min_km2&min_level` | the same around a point, most dangerous first, then nearest |
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
  danger_fires.py       group VIIRS detections into the fires the danger model rates
  danger_inputs.py      weather and place inputs per fire, from Google Earth Engine
  danger_model.py       train the danger model, rate every fire, store it in the database
  fire_events.py        group MODIS and VIIRS detections into the fires the page lists
  event_danger.py       give each listed fire its danger rating
  check_keys.py         test the keys in .env (FIRMS, Earth Engine)
server/                 FastAPI application
  main.py               routes and input checks only
  queries.py            the SQL behind each route
  grid.py               map grid: cell size, cell of a point, cell bounds
  stats.py              typical range, unusual and record weeks
  events.py             the fires: in a map view, around a point, one by one; reported fires
  fires.py              the danger rating in words: level names, exposure, conditions
  db.py                 read-only DuckDB connection
  config.py             paths, limits, .env loading
web/
  index.html            map page: layout
  style.css             map page: appearance
  app.js                map page: behaviour (sections are listed at the top)
  fires.js              map page: the Fires panel, fire markers and the search around a point
  states.html           state overview page
  data/                 calendar.json, states.geojson (generated, committed)
data/                   raw CSV, Parquet, fire.duckdb (generated, not in git)
proofs/                 early feasibility scripts and their saved results
.project/
  SPEC.md               plan, decisions and measured results for every step
  research/             background research, sources and findings
.env.example            template for .env (FIRMS key, Earth Engine project)
requirements.txt        web server: duckdb, fastapi, uvicorn
requirements-pipeline.txt  extra packages for the danger pipeline
```

## Server API

| Route | Answers |
|---|---|
| `GET /api/meta` | first and last day of each layer |
| `GET /api/cells?layer&bbox&start&end&metric` | colored grid cells for the view |
| `GET /api/calendar?layer&bbox` | weekly history of the area, with flags |
| `GET /api/detections.csv?layer&bbox&start&end` | observations behind the layer |
| `GET /api/danger/levels` | what each level meant in 2022-2025 |

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

data/calendar/detections.parquet ──danger_fires──> data/danger/fires.parquet
                                                        │
Google Earth Engine ──danger_inputs──> data/danger/inputs_place.parquet, inputs_weather.parquet
                                                        │
                                    danger_model ──> tables `fires`, `danger_levels` in data/fire.duckdb
```

| Script | Input | Output | Run time |
|---|---|---|---|
| `ingest.py` | FIRMS country archive, U.S. files | Parquet per sensor and year, Alaska removed | about 20 minutes (download) |
| `calendar_table.py` | Parquet, U.S. Census state borders | weekly table per state and series; state-tagged detections | about 4 minutes |
| `harmonize.py` | state-tagged detections | weekly MODIS-equivalent values with standard deviation | seconds |
| `export_web.py` | calendar and harmonized tables | state overview data with flags and typical ranges | seconds |
| `build_db.py` | state-tagged detections | `fire.duckdb` with the three map layers (156 MB) | seconds |
| `danger_fires.py` | state-tagged detections | fires and their daily growth | seconds |
| `danger_inputs.py` | fires, Earth Engine | weather and place inputs per fire | about 17 minutes |
| `danger_model.py` | fires, inputs | danger model, level of every fire, written into `fire.duckdb` (344 MB) | about 4 minutes |

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

Fire danger (optional; needs `EE_PROJECT` in `.env` and `earthengine authenticate`):

```bash
pip install -r requirements-pipeline.txt
```

```bash
python pipeline/check_keys.py
```

```bash
python pipeline/danger_fires.py
```

```bash
python pipeline/danger_inputs.py
```

```bash
python pipeline/danger_model.py
```

```bash
python pipeline/fire_events.py
```

```bash
python pipeline/event_danger.py
```

Run `danger_model.py` again after every `build_db.py`, with the server stopped.

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
- **The danger level describes a fire after two days.** It is not a forecast
  for a fire seen today for the first time. Most fires rated Extreme are
  already over 1,000 acres on day 2.
- **Fire size is a satellite footprint**, not a surveyed perimeter (Park Fire:
  266,307 acres seen, 429,603 official).
- **Hawaii has no danger level.**
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
| 7. Fire danger rating and nearby fires for firefighters | done; a day-1 rating for new fires is planned |
| 8. Landsat 30 m cross-check layer | planned |
| 9. Seven-day forecast | planned |
| 10. Prevention and context layers (fuels, treatments, smoke, vegetation, aircraft) | planned |

Later versions: Alaska, Mexico and other regions.

Details, decisions and results for every step: [.project/SPEC.md](.project/SPEC.md).
