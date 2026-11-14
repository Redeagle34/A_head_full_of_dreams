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
