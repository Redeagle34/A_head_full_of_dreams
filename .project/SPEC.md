# SPEC: MODIS–VIIRS burning calendar (draft)

Mode: prototype (src: user, hackathon)
Status: draft, waiting for the team's answers to "Open decisions"
Source research: `.project/research/notebooks/modis-viirs-burning-calendar/`

## Goal

A website where firefighters, scientists, land managers and early warners pick a
U.S. region and dates and see a harmonized MODIS and VIIRS burning calendar:
historical patterns, unusual periods and critical periods, with downloadable data.
Scope: contiguous U.S. and Hawaii. Alaska, Mexico and other regions are later versions.

## Rule: built step by step

Each step ends in something that runs and can be shown. A step starts only after
the previous step's check passes. Nothing requested is dropped; capabilities that
are not in the first steps are placed in later steps below.

## Steps

| # | Step | Result you can see | Check |
|---|------|--------------------|-------|
| 1 | Archive access | One year of MODIS and one year of VIIRS detections for the U.S. downloaded from the FIRMS archive | Files open, row counts and date range printed |
| 2 | Full ingest | MODIS (2000–present) and VIIRS (2012–present) for the contiguous U.S. and Hawaii stored as Parquet, partitioned by sensor and year | Second run adds zero rows; counts per sensor and year reported |
| 3 | Calendar table | Region × week × sensor table of active cell-days on one common grid | Totals match the raw files for three sample regions |
| 4 | Harmonization | "MODIS-equivalent" series for 2000–present: MODIS as observed, and VIIRS passed through an observation operator that estimates what MODIS would have detected (see "Harmonization method") | On withheld overlap years, VIIRS-as-MODIS is closer to real MODIS than raw VIIRS counts and than a single multiplier; remaining error reported per region and season |
| 5 | Calendar screen | Website: pick region and dates, see week-by-year heatmap, typical range, unusual and critical periods flagged | Park Fire weeks (July 2024, Northern California) show as unusual |
| 6 | Downloads | CSV of the selected calendar and of native detections, plus a short report (sensor overlap, coverage, source versions) | Downloaded counts equal the counts on screen |
| 7 | Nearby map | Set a location and radius, see recent detections with source, time and confidence | Georgia and Hawaii test queries return the same IDs as the earlier proof |
| 8 | Landsat layer | 30 m Landsat detections as an optional cross-check on the map, with time lag shown | One matched case displayed; non-matches labeled "no usable scene" |
| 9 | Seven-day forecast | Probability of satellite-observed burning next week, seasonal and persistence baselines first | Scored on a withheld season against both baselines |
| 10 | Prevention and context | Fuels, past treatments, smoke, vegetation, aircraft perimeters | To be specified when step 9 is done |

Steps 1–6 are the hackathon core and answer the NASA challenge. Steps 7–10 are
added in order as time allows.

## Carried over from the investigation

- Native observations are stored once. Grid values are derived and never counted
  as separate detections.
- "No detection" under cloud or outside the swath is unknown, not zero. Until
  coverage masks are added, the calendar says so.
- Landsat is a higher-resolution cross-check, not ground truth.

## Harmonization method

Reference: [fmidev/FRP_OOp](https://github.com/fmidev/FRP_OOp) (M. Sofiev, Finnish
Meteorological Institute, extracted from IS4FIRES v3.0).

Idea: the sensors differ because a larger pixel needs a stronger fire to trigger a
detection. The operator gives each sensor a detection limit in MW that grows
linearly with pixel area (separate day and night coefficients), and a sigmoid
probability of detection around that limit. A fire far below the limit is not
seen; far above it is seen with its real FRP.

Use in this project:

- Direction is VIIRS to MODIS only. VIIRS is more sensitive, so a VIIRS detection
  can be tested against the MODIS limit. Fires MODIS never saw cannot be invented,
  so the long calendar is expressed in MODIS-equivalent units. The full VIIRS
  record stays available as its own, more detailed layer.
- Inputs come from the FIRMS files: `frp`, `daynight`, and pixel area from
  `scan × track`.
- The calendar sums detection probabilities (expected value) instead of the
  random draw used in the reference code, so results are repeatable.
- S-NPP and NOAA-20 often record the same fire twice; they are combined per cell
  and overpass time before the operator is applied.

Limits to state in the report:

- The reference code is GPL-3.0 and depends on the SILAM toolbox, Fortran and
  level-2 granules. This project re-implements the published formula in a few
  lines and cites the source; it does not copy the code. Team to confirm the
  repository license before any code is copied.
- FIRMS files carry no cloud mask, so MODIS cloud cover at the time of a VIIRS
  detection is unknown. First version assumes clear sky and a typical MODIS pixel
  size (2.45 km², the reference value).
- Coefficients were fit globally, not for the U.S. Step 4's check measures how
  well they hold here.

## Decisions

- Calendar regions: U.S. states first (src: user).
- Website: plain page with MapLibre and a chart library (src: user).
- Storage: Parquet + DuckDB. PostGIS is added when a step needs it (expected at
  step 7, nearby search), reading the same Parquet files (src: user).

## Not verified yet

- FIRMS yearly archive download for the full period (step 1 tests it).
- A FIRMS MAP_KEY may be needed; it stays in `.env`, never in the repository.

## Step results

- Step 1 passed (2026-11-14). FIRMS yearly U.S. files download without a key from
  `https://firms.modaps.eosdis.nasa.gov/data/country/<sensor>/<year>/`.
  2023: MODIS 94,000 rows (Aqua 51,287, Terra 42,713), VIIRS S-NPP 388,672 rows,
  both covering all 365 days, no unreadable rows.
  Consequences for step 2: the files include Alaska (to filter out) and a `type`
  column (0 vegetation fire, 1 volcano, 2 static land source, 3 offshore); the
  calendar counts type 0 only and keeps the others stored.
- Step 2 passed (2026-11-14). `python pipeline/ingest.py` stored 13,364,871 rows
  as Parquet in `data/parquet/sensor=<sensor>/year=<year>/` (285 MB; raw CSV 1.1 GB):
  MODIS Nov 2000–2025, VIIRS S-NPP Jan 2012–2025, VIIRS NOAA-20 Apr 2018–2025.
  A second run gave identical counts. 2023 counts equal step 1 minus Alaska rows.
  Still missing: 2026. The yearly archive has no 2026 file yet; recent months need
  the FIRMS API with a MAP_KEY (free, requested by a team member).
- Step 3 passed (2026-11-14). `python pipeline/calendar_table.py` (about 4 minutes)
  writes `data/calendar/calendar.parquet`: 178,684 rows, 48 contiguous states plus
  DC and Hawaii, weeks starting Monday, series modis / terra / aqua / viirs-snpp /
  viirs-jpss1, vegetation-fire detections (type 0) only. Checks: calendar totals
  equal source detections for every series; three boxes inside Kansas, Georgia and
  Hawaii have every detection assigned to the right state. 2,895 detections
  (0.03%) fall outside every state polygon (coast and border) and are not counted.
  Grid: 0.1 degree cells, not equal-area. State borders: U.S. Census 2023, 1:500,000.
- Step 4 passed (2026-11-14). `python pipeline/harmonize.py` (seconds) writes
  `data/calendar/harmonized.parquet` (36,400 rows, Jan 2012 - Dec 2025): per state
  and week, Aqua observed, VIIRS S-NPP and NOAA-20 raw, VIIRS-as-MODIS from the
  operator, `modis_equivalent_cell_days` with a standard deviation, and the number
  of days each sensor observed.
  Scored on withheld years 2021-2025 against real Aqua at state-week level, only
  on days both sensors observed (error = sum of absolute differences / Aqua total):
  S-NPP raw 3.06; one multiplier 0.52; multiplier per state and season 0.37;
  operator with published coefficients and no fitting 0.32 (total within 1% of
  Aqua); NOAA-20 operator 0.32; both VIIRS satellites plus a state-season factor
  0.27 (final product).
  Decisions made by the data:
  - Comparison target is Aqua, not Terra + Aqua: Aqua and VIIRS pass at similar
    local times.
  - Mean MODIS pixel (2.45 km2) is used. Averaging over swath pixel sizes
    over-predicted by 32% and was rejected on the training years 2013-2020.
  - Outage days are unknown, not zero. A day with no detection nationwide from a
    satellite counts as not observed: Aqua 35 days, S-NPP 38 days, NOAA-20 6 days.
    S-NPP was down 10-15 and 24-28 July 2024, during the Park Fire; NOAA-20 fills
    those days (week of 22 July 2024, California: Aqua 114, MODIS-equivalent 102).
  Known failures and limits:
  - Hawaii: operator predicts 998 cell-days where Aqua saw 83 in 2021-2025.
    Kilauea lava is labeled as vegetation fire and VIIRS sees it far more often.
  - By state the unfitted operator ranges from 0.78 (NC) to 1.38 (AZ) of Aqua.
    Summer is the worst season.
  - Partial-day outages and MODIS cloud cover at VIIRS overpass time are not
    modeled. The standard deviation covers detection chance only.
  - Before 2012 there is no VIIRS; the calendar uses MODIS as observed.
- Step 5 built, check NOT passed (2026-11-14). `python pipeline/export_web.py`
  writes `web/data/calendar.json` (1.6 MB, 50 states, 1,227 weeks from July 2002)
  and `web/data/states.geojson`. `web/index.html` shows: state map (click to
  select), state and year selectors, week-by-year heatmap with unusual and record
  weeks outlined, usual fire season bar, focus-year line against the typical
  range with the VIIRS MODIS-equivalent estimate, and a list of unusual periods.
  Verified in a browser: page loads without errors; map click, state, year range
  and Hawaii note work.
  Check result: California, week of 22 July 2024 (Park Fire) has 114 cell-days
  against a 90% level of 113.4 and ranks at 0.90 of other years, just under the
  flag threshold; the next two weeks rank 0.78 and 0.51. At whole-state level one
  large fire in California does not stand out against late-July weeks of 2008,
  2018, 2020 and 2021. The threshold was not changed to force a pass. Finer
  regions (county or drawn area) are the proposed fix.
  Limits: Hawaii is not on the map (dropdown only). Weeks before July 2002
  (Terra only, 2000-2002) are not shown; Terra is not converted to Aqua units.

## Map explorer (decided 2026-11-14, src: user)

The state calendar page was informative but hard to read. The product becomes a
full-screen map, like FIRMS or Google Earth, with the calendar as a panel for the
area on screen.

- Search bar on top: place, and date range up to the latest data.
- Transparent color layer over the map; zoom into a place of interest.
- Filters: data source MODIS, VIIRS, both, or none.
- Resolution follows the data source:

| Selection | Grid | Period |
|---|---|---|
| VIIRS only | 375 m | 2012 - latest |
| MODIS only | 1 km | 2000 - latest |
| Both (one harmonized layer, MODIS-equivalent) | 1.5 km | 2002 - latest |
| None | basemap only | - |

- Color can show: fire intensity (default), days with fire, or unusual versus normal.
- Server: FastAPI + DuckDB, code split into small readable modules.
- FIRMS MAP_KEY is not used now; `.env.example` reserves its place.
- Calendar for the area on screen replaces the county question: any area gets
  its own "typical".

### Map explorer result (2026-11-14)

Built: `pipeline/build_db.py`, `server/` (FastAPI + DuckDB), `web/index.html`,
`web/style.css`, `web/app.js`. The earlier page is kept as `web/states.html`.

Verified in a browser on the local server: page loads without errors; globe
with satellite imagery; fire layer for the whole country; Park Fire example
zooms in and shows the burn footprint at 1.5 km; VIIRS only at 375 m; unusual
versus normal; place search (Lake Tahoe); area history panel; CSV download.

Checks:
- Database: native layers hold exactly the source detections; satellite weights
  add up to 1 on every day; every observation has a weight.
- Speed: Park Fire area 0.04 s; whole country, one year 0.09 s; whole country,
  all VIIRS years 0.65 s; area history for the whole country 0.5 s.
- Step 5 check now passes at area level: in the Park Fire area the week of
  22 July 2024 is a record week (542 cell-days) and the next two are unusual, in
  all three layers.

Not done or not verified:
- Data ends 31 December 2025; the MAP_KEY place is reserved in `.env.example`.
- The harmonized layer at 1.5 km cells is not scored against Aqua at cell level;
  the score in step 4 is at state-week level.
- "Days with fire" for single-sensor layers counts a day when any satellite of
  the family saw fire, so periods with two satellites detect slightly more.
- Color scale adapts to the squares on screen.
- Not tested: phone layout, "My location", clicking a square for its popup.
- Still open from the original plan: scientist report, radius search for
  firefighters, Landsat layer, seven-day forecast, prevention layers, Hawaii
  volcano mask, Terra years 2000-2002 in the combined layer.

## Fire danger and radius search (decided 2026-11-14, src: user)

Decision: before the radius search, rate how dangerous each fire is; then rank
the fires near a point by that rating. Starting point: the experiments of branch
`us-findings` (`proofs/us-experiments`), which trained models on agency fire
reports with weather and place inputs. Keys for Earth Engine and FIRMS live in
`.env`; `pipeline/check_keys.py` tests them.

Review of the reference models (re-run by us):
- Saved models reproduce their reported scores exactly (0.893, 0.788, 0.810).
- "Fire reported here today" (model A) scores 0.737 inside the same 1-degree
  area and month, against 0.893 overall: most of its skill is where fires get
  reported. Not used.
- "A start reaches 100 / 1,000 acres" (model B) ranks well but uses no satellite
  data. Adding the VIIRS detections near the start lifted it from 0.788 to 0.876
  and from 0.810 to 0.883. This is why the danger model below combines both.

Built:
- `pipeline/danger_fires.py`: VIIRS detections grouped into 1,517,969 fires
  (touching cells of about 1.6 km, gaps of up to 2 days). Size = satellite
  footprint on cells of about 440 m.
- `pipeline/danger_inputs.py`: weather (gridMET), terrain, vegetation, fire
  regime, population and built-up surface within 5 km, from Earth Engine, for
  257,146 cells and 1,514,518 cell-days. About 17 minutes.
- `pipeline/danger_model.py`: LightGBM, "will the footprint reach 1,000 acres",
  judged at the end of the fire's second day. Train 2012-2020, validation 2021,
  test 2022-2025. Calibrated on 2021 and cut into five levels.
- `server/fires.py`, routes `/api/fires`, `/api/fires/near`, `/api/danger/levels`.
- `web/danger.js`: fire markers colored by level, the three factors of a fire in
  a popup, and the "Fires nearby" panel.

Results on 2022-2025 (never used for training):

| Check | Result |
|---|---|
| Rank fires not yet 1,000 acres on day 2 by whether they get there (AUC) | 0.944 |
| Same, satellite inputs only | 0.928 |
| Same, weather and place only | 0.859 |
| Same, day-1 footprint alone | 0.779 |
| Against agency reports: rating ranks reported size >= 1,000 acres (6,196 reports) | 0.912 |
| Reference model B-1000 on the same reports | 0.748 |
| Footprint against reported size, log correlation | 0.69 |
| Footprint / reported size, median, reports of 100 acres or more | 0.91 |

| Level | Fires 2022-2025 | Reached 1,000 acres | Share of all large fires |
|---|---|---|---|
| Low | 513,427 | 0.07% | 7% |
| Moderate | 19,635 | 2.2% | 8% |
| High | 5,606 | 7.7% | 8% |
| Very High | 1,098 | 24% | 5% |
| Extreme | 4,021 | 96% | 72% |

Checks that passed: every VIIRS detection belongs to exactly one fire; the Park
Fire (24 July - 12 August 2024, footprint 266,307 acres against 429,603 official)
and Lahaina each come out as one fire; Earth Engine values equal the reference
training table on 200 rows (difference 0); built-up within 5 km equals an exact
sum at test points (Chico 1,300 ha); levels are in order on the test years;
routes answer in about 0.25 s; in the browser the radius search lists 24 fires
within 50 km of Chico for the Park Fire dates, the Park Fire first.

Not done or not verified:
- Most fires rated Extreme are already over 1,000 acres on day 2. For fires
  still small on day 2 the levels are Low to Very High, and 7% of the fires
  that later got large were rated Low.
- The 100-acre target is not shown: a footprint cell is 47 acres, so 100 acres
  is three cells and 32% of Low fires reach it.
- The rating describes a fire after two days of satellite passes. It is not a
  forecast for a fire seen today for the first time; no day-1 model yet.
- Weather is the observed weather of the first day, as in the reference models.
- Training on agency-reported sizes instead of footprints was not tried; the
  footprint-trained rating already ranks reported sizes at 0.912.
- Hawaii is not rated (lava is recorded as fire): 1,663 fires without a level.
- Model results move by about 0.005 between runs when inputs are re-pulled.
- Data ends 31 December 2025; 2026 through the FIRMS key is not loaded.
- `data/fire.duckdb` is now 344 MB: the hosted copy was not redeployed and a
  redeploy would not fit the current 100 MB piece scheme without changes.
- Phone layout: the top bar and the panel leave little map visible. "My
  location" was not tested (needs a real device).
- Branch `us-findings` is not merged; its training table and models are read
  from a local copy in `data/raw/reference/`.
- Still open from the original plan: scientist report (last), Landsat layer,
  seven-day forecast, prevention layers, Hawaii volcano mask, Terra 2000-2002.

## Merge of branch fire-events-satellite-globe (2026-11-14, src: user)

Merged into main: fires as single events with Landsat before/after pictures and
burn severity, reported fires that were missed, satellites in orbit as 3D
models, and the time bar. The branch also carried the commits of `us-findings`
(`proofs/us-experiments`), so the danger scripts now read the reference table
from there.

Resolved by keeping both sides. Two files of main were renamed first because
the branch has files of the same name with other content:
`pipeline/fire_events.py` -> `pipeline/danger_fires.py`, `web/fires.js` ->
`web/danger.js`. `requirements.txt` stays server-only; pipeline packages are in
`requirements-pipeline.txt` (the Landsat pictures route needs `earthengine-api`).

Checked after the merge: every route answers (Landsat pictures for the Park
Fire in 16 s); `pipeline/fire_events.py` (2,035,833 events), `missed_fires.py`
and `event_enrich.py` (5,562 fires) run; in the browser the satellites panel,
time bar, fire list, danger markers and radius search load together.

Open after the merge:
- Two definitions of "a fire" now exist: events (gaps up to 5 days, cells of
  about 1 km, MODIS and VIIRS; 2,035,833) and rated fires (gaps up to 2 days,
  cells of about 1.6 km, VIIRS; 1,517,969). Two panels list them: "Fires" and
  "Fires nearby". They should become one.
- The Terra 3D model asks for two texture files that are not in the repository
  (404); the model still shows.
- Six buttons and the time bar crowd narrow screens; phone layout not reworked.

## One fire definition (decided 2026-11-15, src: user)

Decision: one definition of a fire everywhere, the fire event of
`pipeline/fire_events.py` (MODIS and VIIRS detections that touch on squares of
about 1 km and follow within 5 days), and the danger model trained again on
those fires. Done on branch `integration`, which also holds the Terra textures,
the layout for narrow screens, the Vercel setup and the AWS scripts.

Why not the earlier plan of carrying ratings over from the old VIIRS grouping:
`pipeline/event_danger.py` failed its own check on real data (254 VIIRS
detections fell into two events), because a cell can burn again inside the date
range another event has for that cell. It was removed.

Changes:
- `fire_events.py` also writes `event_cell_days.parquet`: the fire of every
  burning cell and day. This is the exact link from a detection to its fire.
- `danger_fires.py` no longer groups detections. It reads that link and counts,
  per fire, what VIIRS saw day by day. `fire_id` is the `event_id`.
- `danger_inputs.py` re-pulled for the new first days (16 minutes).
- `danger_model.py` trains on the events and writes one rating per event to
  `data/events/event_danger.parquet`. The ratings are no longer stored in
  `fire.duckdb`, which is back to 156 MB.
- Reference models are loaded as text: a Windows checkout stores them with CRLF
  line ends, which LightGBM cannot parse.

Results on 2022-2025 (never used for training), 1,435,928 fires with VIIRS:

| Check | Events (now) | Old VIIRS grouping |
|---|---|---|
| Rank fires not yet 1,000 acres on day 2 (AUC) | 0.936 | 0.944 |
| Same, satellite inputs only | 0.895 | 0.928 |
| Same, weather and place only | 0.865 | 0.859 |
| Rating ranks agency-reported size >= 1,000 acres | 0.904 | 0.912 |
| Reference model B-1000 on the same reports | 0.750 | 0.748 |
| Footprint / reported size, median, 100 acres up | 0.93 | 0.91 |

| Level | Fires 2022-2025 | Reached 1,000 acres | Share of all large fires |
|---|---|---|---|
| Low | 474,721 | 0.11% | 10% |
| Moderate | 28,147 | 2.6% | 14% |
| High | 4,417 | 8.5% | 7% |
| Very High | 1,699 | 21% | 7% |
| Extreme | 3,430 | 97% | 63% |

Checked in the browser on the local server: one Fires button; list on screen
(10 fires of 2 km2 or more around the Park Fire) and around a point (5 within
50 km, the Park Fire first); a fire's page shows its level, exposure and what
VIIRS saw; markers colored by level; satellites panel, time bar; no console
errors (the Terra texture errors are gone); Landsat pictures for the Park Fire
answer in 22 s. At 375 x 812 the top bar, the panel
and the time bar do not overlap and nothing scrolls sideways. Every route
answers in under 0.5 s.

Not done or not verified:
- Scores are slightly lower than on the old grouping: with gaps of up to 5 days
  more fires restart after day 2, which the first two days cannot show.
- 10% of the fires that later got large were rated Low.
- Fires seen by MODIS only (all before 2012, some after) and fires in Hawaii
  have no level.
- The Vercel setup and the AWS scripts were not run for real. `prepare_deploy.py`
  ran: upload 319 MB (database 149, events 161, web 9), above the 100 MB that
  Vercel allows without the Pro plan; the function fits (about 390 of 500 MB)
  only without `earthengine-api`, so Landsat pictures would be off there.
- 3D satellites were not looked at on a wide screen; "My location" needs a real
  device.

## Scientific report (decided 2026-11-15, src: user)

Decision: teammates rebuild the data themselves (no shared data file). Then the
scientist report: aggregated over places the reader selects, with a checkbox
list of what to include.

Built:
- `server/report.py`: places are any mix of states and boxes, turned into one
  condition so nothing is counted twice. Eleven sections, one function each.
- Routes `GET /api/report/sections`, `POST /api/report`.
- `web/report.html`, `report.css`, `report.js`: builder (states as checkboxes,
  areas by place search or from the map, dates, sections as checkboxes) and a
  printable document with charts; CSV per table, JSON of the whole report,
  print or save as PDF.
- **Report** button on the map: opens the report for the area and dates on screen.
- `build_db.py`: every database row now carries its state (exact state filter;
  database 170 MB), and a rebuild keeps the table of danger levels.
- `queries.weekly()`: the weekly series for any place condition; the area
  calendar of the map uses it with a box.

Checked:
- Self-checks of `server/report.py` (place conditions, bad input refused, window
  sums) pass.
- California + Oregon + a Flint Hills box, July to September 2024: 1.0 s; 7,782
  active cell-days, 2.1 times the median of 23 other years; 2,137 fires; week of
  22 July 2024 is a record. All states, whole record: 2.1 s.
- Bad requests answer 400 with a plain message (no place, long state name,
  dates reversed, unknown section, box with west after east).
- Browser: all 11 sections draw with their charts and tables, no console
  errors; unticking sections removes them; All and None for states; place
  search adds Butte County as an area; removing an area; the Report button on
  the map opens the report with the area and dates; at phone width nothing
  scrolls sideways.

Not done or not verified:
- Print and PDF output was not looked at; neither were the CSV and JSON files
  opened (the links are made and named).
- Charts were checked by count, not by eye, except the first screen.
- An area is the box around a place, not its outline. States are exact.
- A fire belongs to the state where most of it burned and to a box when its
  centre is inside, so a fire across a border is counted in one place only.
- No trend test or confidence intervals; the yearly section is descriptive.
- Vegetation covers fires of 10 km2 or more; reported fires start in 2014.
- The area name passed from the map can be stale while the map is still moving.
- Still open from the original plan: seven-day forecast, prevention layers,
  Hawaii volcano mask, Terra 2000-2002, 2026 data.

### Report output check (2026-11-15)

Checked with a headless browser: one picture per section, the report printed
to PDF and rendered page by page, every CSV parsed, the JSON read.

Found and fixed:
- Print: sections refused to split, so pages were left almost empty (12 pages,
  two nearly blank), and tables shrank to their content because the phone rule
  also applied on paper. Now 8 pages, full-width tables, table headings repeat
  on each page, no chart, row or tile is cut.
- CSV: no byte-order mark, so Excel would show km2 headings wrongly; the flag
  column had no heading; shares had no unit. Now with the mark, "Flag (1
  unusual, 2 record)", and "(fraction)" on share columns.
- Charts: the missed-fires axis did not say percent; two axis labels touched a
  tick; dates wrapped inside table cells.

Confirmed: all eight charts match their tables; the builder and the CSV links
are not printed; each of the nine CSV files has the rows of its table; the JSON
holds places, dates and the eleven sections.

Not verified: printing from the browser's own print dialog (margins and paper
size chosen there), and opening the CSV in Excel itself.

## Public copy on Vercel updated (2026-11-15, src: user)

The public copy now runs the current main: one Fires panel with danger levels,
satellites, time bar, phone layout, scientific report.

First try failed: Vercel reported a function of 342 MB against a limit of
225 MB (the 500 MB assumed before was wrong, and the upload limit of 100 MB
did not apply). `pipeline/prepare_deploy.py` was rewritten to write a smaller
copy of the same data in `data/deploy/` (180 MB instead of 303 MB):
observations as compressed Parquet, Aqua rows of the harmonized layer stored
once, coordinates to 4 decimals, ratings to the digits shown. `api/index.py`
makes the table `obs` a view over those files at start-up.

Checked:
- The script's own checks: every table and file keeps all its rows; the
  harmonized layer adds up to the same total (within rounding).
- The same start-up on this computer, against the normal local server, on 12
  routes: same status, same answer sizes, same speed; report totals differ by
  0.02% (7,677.7 against 7,679.2 active cell-days).
- On Vercel, preview and public address: page, report page, scripts, 3D models
  and every data route answer 200; the report for California, Oregon and a
  Flint Hills box answers in under 1 s. First request after a pause: 4.3 s.

Not done or not verified:
- Landsat pictures are off on Vercel (503 with the reason).
- The public page was checked by its routes, not looked at in a browser or on
  a phone.
- The estimate in `prepare_deploy.py` says 222 of 225 MB: little room for more
  data on Vercel.
