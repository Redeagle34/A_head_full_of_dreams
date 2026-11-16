# A head full of dreams

NASA Space Apps Challenge 2026, "MODIS and VIIRS hot spots".

<p align="center">
  <a href="https://youtu.be/9uPJrPJp4v0" title="Watch the 30-second presentation on YouTube">
    <img src=".github/readme-video.jpg" alt="A Head Full of Dreams: 30-second presentation of Burning Calendar (click to play)" width="100%">
  </a>
  <br>
  <b><a href="https://youtu.be/9uPJrPJp4v0">Watch the 30-second presentation on YouTube</a></b>
  &middot; <a href="web/media/tutorial-30s.mp4">download the MP4 (1080p, 60 fps)</a>
</p>

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
- **Report:** opens the scientific report for the area and dates on screen (below).
- **State overview:** the earlier state-by-state calendar, at `/states.html`.

## Scientific report

`/report.html`, or the **Report** button on the map. Three choices, then **Build report**:

1. **Places:** any mix of U.S. states (tick them) and areas (search a county, park or
   city; or come from the map, which adds the area on screen). The report adds the
   places together and counts nothing twice where they overlap.
2. **Dates.**
3. **Sections:** tick what the report should hold.

| Section | What it shows |
|---|---|
| Summary | fires, area, largest fire, activity against normal for the same dates |
| Fire activity by year | the harmonized series per year, 2002 onward |
| Seasonal pattern | a typical year by week, and the usual fire season |
| Unusual and record weeks | each week of the period against its time of year |
| Fires in the period | counts by size, and the 15 largest with their danger level |
| Danger levels of the fires | fires per level, and what each level meant in 2022-2025 |
| Vegetation burned | land cover inside the burned-area map |
| Reported fires the satellites missed | share of agency reports seen, by fire size |
| MODIS and VIIRS side by side | raw detections of each sensor per year |
| Methods and limits, Data sources | how the numbers are made and from what |

The report can be printed or saved as PDF, every table can be downloaded as CSV, and
all its numbers as one JSON file. To add or change a section: `SECTIONS` and one function
in `server/report.py`, and the function of the same name in `RENDER` in `web/report.js`.

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
| Low | 474,721 | 0.11% |
| Moderate | 28,147 | 2.6% |
| High | 4,417 | 8.5% |
| Very High | 1,699 | 21% |
| Extreme | 3,430 | 97% |

The rating is a suggestion to help decide where to look first. It is not a
dispatch order.

How it is made:

- **Fires**: MODIS and VIIRS detections that touch on squares of about 1 km and
  follow within 5 days are one fire (`pipeline/fire_events.py`): 2,035,833 fires,
  2000-2025. The 1,435,928 that have VIIRS detections (2012-2025) are rated.
- **Size**: the satellite footprint, on cells of about 440 m. Against agency
  reports of 100 acres or more it is 0.93 of the reported size (median).
- **Model**: gradient-boosted trees (LightGBM). Inputs: what the satellites saw
  on day 1 and day 2, weather and fuel dryness (gridMET), terrain, vegetation,
  fire regime and population. Trained on 2012-2020, tuned on 2021.
- **Score on 2022-2025**: ranks fires that are still under 1,000 acres on day 2
  by whether they get there with an AUC of 0.936 (satellite inputs alone 0.895,
  weather and place alone 0.865). Against agency-reported final size it scores
  0.904, where a weather-and-place model trained on reports scores 0.750.

The weather-and-place inputs and the comparison model come from the team's
experiments in `proofs/us-experiments`.

### One definition of a fire

The page, the danger model and the fire tables all use the same fire: MODIS and VIIRS
detections that touch on squares of about 1 km and follow within 5 days
(`pipeline/fire_events.py`). The danger model is trained on those fires, so a fire and its
rating are the same thing.

What the rating does not cover:

- Fires seen by MODIS only (all fires before 2012) and fires in Hawaii have no level.
- The rating counts VIIRS detections only, so its numbers mean the same in every year.
  Its size is the VIIRS footprint on squares of 440 m; the fire's area counts squares of
  1 km from both sensors, and is the larger of the two.
- Day 1 of the rating is the first day with a VIIRS detection.
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

| Route | Answers |
|---|---|
| `GET /api/events?bbox&start&end&min_km2&min_level` | fires in the box and dates with their danger rating, largest first |
| `GET /api/events/near?lat&lon&km&start&end&min_km2&min_level` | the same around a point, most dangerous first, then nearest |
| `GET /api/events/{id}` | one fire, its ground cells and nearby agency reports |
| `GET /api/events/{id}/sharp` | Landsat pictures before and after, burn severity (Earth Engine; set `EE_PROJECT` in `.env`) |
| `GET /api/reported?bbox&start&end&missed` | reported wildfires; `missed` is `satellite`, `model`, `both` or `all` |
| `GET /api/tle` | orbit data of the satellites (CelesTrak, cached 6 hours) |
| `GET /api/report/sections` | the sections a report can hold |
| `POST /api/report` | the report as data. Body: `states` (two-letter codes), `boxes` (`name`, `bbox`), `start`, `end`, `sections` |

## Prevention: cells to treat with prescribed burns

The **Prevention** button on the map. For the area on screen it finds the cells where a
prescribed burn cuts the most likely routes a wildfire would spread along. Plan and sources:
[CriticalNode.md](CriticalNode.md) (Yemshanov et al. 2021; Alexandridis et al. 2008).

Cell size follows the zoom: the finest of about 1, 2, 4 or 10 km that keeps the area under 2,500
cells that can burn. 1 km (0.01° x 0.0125°) is the grid the fires are recorded on
(`pipeline/fire_events.py`), so it is the finest size the fire record supports.

1. **Simulated fires** (Monte Carlo, 2,000-20,000): each starts in a cell drawn by how many fires
   started there in 2000-2025, and jumps to each of the 8 neighbours with
   `p_h x (1 + p_veg) x (1 + p_den) x p_wind x p_slope`: land cover (MCD12Q1), tree cover in forests
   (MOD44B), the wind of the burning cell, and the height difference between cells (SRTM). Each
   cell's usual wind is its mean gridMET wind on its high fire-danger days, 2012-2025 (energy
   release component in its own top 10%): speed as the mean speed, direction as the vector mean.
   The panel can set one wind for the whole area instead. `p_h` is set so the simulated
   fires have the mean size of the real fires that started in the area.
2. **Weights:** `p_ij` = share of simulated fires that started in cell `i` and reached cell `j`.
3. **Search:** treat, one at a time, the cell that lowers the sum of `p_ij` over pairs still
   connected the most per km², until the chosen number of cells (up to 60) is treated (greedy, as
   in the plan; good, not necessarily optimal).

The panel shows the burn probability of every cell, the cells to treat in order, how much each
lowers the connected routes, and two checks: simulated against real mean fire size, and the rank
correlation between simulated burn probability and how many real fires touched each cell.

Data: `python pipeline/critical_landscape.py` (Earth Engine, about 15 minutes) writes
`data/events/landscape_1.parquet`, `_2`, `_4` and `_10`, one row per cell. Land cover, tree cover,
height and wind come from Earth Engine in 8° tiles, kept in `data/raw/ee/critical/`. Search:
`server/critical.py`, pure Python so it also runs on Vercel; a few seconds. Check:
`python -m server.critical`. The Vercel copy carries only the 10 km cells (the finer files do not
fit next to the rest), so on Vercel every search uses 10 km cells.

Limits: fires stop at the edge of the screen; built-up land, water, snow and barren land do not
burn; the usual wind is an average and the wind on a fire's day can differ; Hawaii has no gridMET
wind (3 m/s from the west, or the wind chosen in the panel); no fuel moisture or season. Ignitions include agricultural burning, so in farm valleys (for example the Sacramento
Valley) cropland cells can rank first.

## Repository structure

```
pipeline/               builds the data, in this order
  ingest.py             download FIRMS archive, store as Parquet
  calendar_table.py     assign states, build state x week x sensor table
  harmonize.py          VIIRS -> MODIS-equivalent, scored on withheld years
  export_web.py         data files for the state overview page
  build_db.py           data/fire.duckdb, the database the server reads
  danger_fires.py       what VIIRS saw of each fire, day by day: satellite inputs of the danger model
  danger_inputs.py      weather and place inputs per fire, from Google Earth Engine
  danger_model.py       train the danger model, rate every fire, store it in the database
  fire_events.py        group MODIS and VIIRS detections into the fires the page lists
  critical_landscape.py the cells of the Prevention search at 1, 2, 4, 10 km: ignitions, land cover, height, wind
  check_keys.py         test the keys in .env (FIRMS, Earth Engine)
server/                 FastAPI application
  main.py               routes and input checks only
  queries.py            the SQL behind each route
  grid.py               map grid: cell size, cell of a point, cell bounds
  stats.py              typical range, unusual and record weeks
  events.py             the fires: in a map view, around a point, one by one; reported fires
  report.py             the scientific report: places, sections, fixed text
  critical.py           Prevention: fire spread simulation and the cells to treat (CriticalNode.md)
  fires.py              the danger rating in words: level names, exposure, conditions
  db.py                 read-only DuckDB connection
  config.py             paths, limits, .env loading
web/
  index.html            map page (the Guide map design): cover with play and the tutorial video,
                        then the full map; draft-guide.css and draft-guide.js are its look and its parts
  draft-base.css, draft-common.js   shared by the design pages (index.html, draft-park, draft-forecast)
  app.js                map behaviour shared by every map page (sections are listed at the top)
  fires.js              the Fires panel, fire markers and the search around a point
  prevention.js         the Prevention panel and its layers
  satellites.js         satellites, their 3D models, scan lines and passes
  timeline.js           the time bar
  media/                tutorial-30s.mp4 and its poster (made from video/, see video/README.md)
  classic.html, style.css, layout.js, tour.js   the previous map page, kept as classic.html
  drafts.html           the three design drafts side by side (draft-park, draft-forecast, the Guide map)
  report.html, report.css, report.js   scientific report page
  states.html           state overview page
  data/                 calendar.json, states.geojson (generated, committed)
data/                   raw CSV, Parquet, fire.duckdb (generated, not in git)
proofs/                 early feasibility scripts and their saved results
video/                  the 37 s presentation video: animation source, script, render tools (see its README.md)
.project/
  SPEC.md               plan, decisions and measured results for every step
  research/             background research, sources and findings
deploy/aws/             scripts and steps to run the site on AWS (see its README.md)
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
| `GET /api/critical/size?bbox` | Prevention: the cell size a search would use for the view |
| `GET /api/critical?bbox&budget_km2&wind_ms&wind_from&runs&seed` | Prevention: burn probability per cell and the cells to treat; without `wind_ms`, `wind_from` each cell keeps its usual wind |

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

data/calendar/detections.parquet ──fire_events──> data/events/events.parquet, event_cells, event_cell_days
                                                        │
                                    danger_fires ──> data/danger/fires.parquet
                                                        │
Google Earth Engine ──danger_inputs──> data/danger/inputs_place.parquet, inputs_weather.parquet
                                                        │
                                    danger_model ──> data/events/event_danger.parquet,
                                                     table `danger_levels` in data/fire.duckdb
```

| Script | Input | Output | Run time |
|---|---|---|---|
| `ingest.py` | FIRMS country archive, U.S. files | Parquet per sensor and year, Alaska removed | about 20 minutes (download) |
| `calendar_table.py` | Parquet, U.S. Census state borders | weekly table per state and series; state-tagged detections | about 4 minutes |
| `harmonize.py` | state-tagged detections | weekly MODIS-equivalent values with standard deviation | seconds |
| `export_web.py` | calendar and harmonized tables | state overview data with flags and typical ranges | seconds |
| `build_db.py` | state-tagged detections | `fire.duckdb` with the three map layers, each row with its state (170 MB) | seconds |
| `fire_events.py` | state-tagged detections | the fires: one row each, their cells, their cell-days | seconds |
| `danger_fires.py` | fires, state-tagged detections | what VIIRS saw of each fire, day by day | seconds |
| `danger_inputs.py` | fires, Earth Engine | weather and place inputs per fire | about 17 minutes |
| `danger_model.py` | fires, inputs | danger model, level of every fire (`data/events/event_danger.parquet`) | about 4 minutes |

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
python pipeline/fire_events.py
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

`build_db.py` keeps the table of danger levels when it is run again, so the model does
not have to be trained again after it.

```bash
python pipeline/critical_landscape.py
```

```bash
python -m uvicorn server.main:app --port 8780
```

Then open http://localhost:8780. The data must be built once (first five
commands, about 25 minutes, mostly download); after that only the last command
is needed.

## Deploy to Vercel

The copy on Vercel is the same application, started by `api/index.py`, on a smaller copy
of the data.

1. Build the data (see Run), then make the small copy:

```bash
python pipeline/prepare_deploy.py
```

It writes `data/deploy/` and prints its size against Vercel's limit. Run it again after
every `build_db.py`, `fire_events.py` or `danger_model.py`.

2. Publish:

```bash
vercel deploy --prod
```

What goes up (`.vercelignore`): `server/`, `api/`, `web/`, `data/deploy/` and
`pipeline/prepare_deploy.py`. Not the raw data, the rest of the pipeline or `.env`.

How it differs from the local server:

- **Data:** a Vercel function may hold 225 MB of code, packages and data; the data as
  built is about 300 MB. `prepare_deploy.py` stores the same rows smaller (180 MB):
  observations as compressed Parquet instead of inside the database, the Aqua
  observations of the harmonized layer stored once, coordinates to 4 decimals (about
  10 m), radiative power to 0.1 MW. Numbers differ from the local server by up to 0.1%.
  When the function starts, `api/index.py` copies the small database to the temporary
  folder and adds the observations to it as a view over the Parquet files.
- **First request after a pause** takes a few seconds.
- **3D models:** `web/` is served by Vercel as static files and `web/models/` is left
  out of the function to keep it small.
- **Answers** are compressed, because a function may not answer with more than 4.5 MB.
- **Landsat pictures** (`/api/events/{id}/sharp`) are off: Earth Engine does not fit in
  the function next to the data. The route answers 503 with the reason and the rest works.
- **Missing data:** a part of the page whose file was not built says which script to
  run; nothing else fails.

To try the Vercel start-up on your computer: `python -m uvicorn api.index:app --port 8791`.

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
