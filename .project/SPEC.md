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
