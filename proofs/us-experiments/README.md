# U.S. experiments: findings and ideas for the map

Independent experiments run on 2026-11-14 on the same FIRMS archive, plus
ground-truth fire reports, weather and a first prediction model. This note
lists what was measured, what it means for the current map, and what could be
added. Nothing here changes the pipeline or the website.

- `scripts/` the code behind every number (paths assume `data/country/`,
  `data/raw/`, `data/derived/` under the working folder; keys come from `.env`)
- `results/` the saved metrics
- `figures/` the charts
- `damage-research.md` full notes on estimating damage if a fire happens
- `models/` the three trained models, their training table and `MODEL_CARDS.md`

Scope: contiguous U.S. plus Alaska, FIRMS standard archive 2000–2025,
`type == 0`, MODIS confidence ≥ 30, VIIRS confidence nominal or high. Regions
(West, Central, East, Alaska) are defined in `scripts/21_us_aggregate.py`.

## 1. Short version

1. The observation-operator conversion you use holds up on our side too:
   predicted over actual Aqua stays between 0.93 and 1.04 in every year
   2013–2025. It has a regional bias and a drift after 2021 that are worth
   correcting (section 2).
2. Reported wildfires give an independent check that no satellite-only method
   has: satellites see 2% of fires under 1 acre and 72% of fires over 10,000
   acres. This is the "what the map cannot see" layer (section 3).
3. A model for "chance a fire starts today" and "chance it becomes large" is
   trained and beats the standard fire-danger index (section 4).
4. Damage if it burns is best described by how much is built nearby and by
   vegetation type, not by modelled flame length (section 5).
5. A list of gaps and ideas for the map is in section 6.

## 2. Harmonization

Measured (`results/harmonization_metrics.json`, `conversion_models.json`,
`obsop_metrics.json`; figures `us_C1`–`us_C5`):

| Quantity | Value |
|---|---|
| Naive jump in U.S. yearly detections, 2011 → 2013 | 3.42× |
| S-NPP / Aqua, raw detections (median of region-months) | 5.86 |
| S-NPP / Aqua, active 0.1° cell-days | 4.01 |
| NOAA-20 / S-NPP, cell-days | 1.05 |
| Terra / Aqua, cell-days | 0.87 |
| Power law VIIRS → Aqua, slope on log Aqua | −0.29 (ratio falls as activity rises) |

Counting active cell-days instead of detections removes a third of the gap
before any model is applied, and makes the ratio more stable.

Observation operator (Sofiev & Kouznetsov 2026, same parameters as
`pipeline/harmonize.py`, re-implemented, `scripts/27_obsop_test.py`):

- Predicted / actual Aqua cell-days per year, 2013–2025: 0.93 to 1.04.
- Correlation on region-months (log): 0.95.
- **Regional bias**, predicted / actual: East 0.84, Central 0.95, Alaska 1.14,
  West 1.18. Small agricultural fires in the East are under-predicted, large
  western fires over-predicted.
- **Drift**: every conversion we tried (single ratio, region × month ratio,
  power law, operator) under-predicts or over-predicts 2022–2025 by 5–13%
  when trained on earlier years. In your state-week table the same pattern
  shows as VIIRS-as-MODIS / Aqua of 0.96–1.01 through 2021 and 1.09 in 2022
  and 2025.
- Likely cause: orbit drift. Aqua's overpass moved from about 13:09 to 14:12
  local solar time and Terra's from 10:58 to 9:53 by 2025, so "MODIS" is not a
  fixed reference in recent years. Not isolated by experiment.
- Weighting MODIS detections by inverse detection probability did not help.

Suggestions:

- Apply a region factor (and a year factor from 2022) on top of the operator,
  fitted on overlap years. The numbers are in `results/obsop_region_month.csv`.
- State the drift as a limit in the README: after 2021 the MODIS-equivalent
  unit is tied to a satellite whose overpass time is changing.
- The combined layer is not yet scored at cell level. The reported-fire check
  below is one way to score it without using Aqua as its own judge.

## 3. Ground truth: reported fires versus satellites

Source: NIFC WFIGS Incident Locations (public ArcGIS service, U.S. Government
open data), 2014–2025. A report counts as "seen" when a detection falls within
2 km and from 1 day before to 3 days after discovery. Years 2023–2024
(`results/wfigs_detection_metrics.json`, `figures/us_E1_detection_by_size.png`).

| Final size (acres) | Reports | Seen by VIIRS | Seen by MODIS |
|---|---|---|---|
| under 1 | 49,666 | 2.1% | 0.6% |
| 1–10 | 9,343 | 9.5% | 2.1% |
| 10–100 | 4,679 | 25.7% | 9.5% |
| 100–1,000 | 1,855 | 49.5% | 28.9% |
| 1,000–10,000 | 663 | 56.4% | 48.0% |
| over 10,000 | 160 | 70.6% | 62.5% |

- With a looser match (10 km, 14 days) 88% of fires of 1,000 acres or more
  are seen, so part of the miss on large fires is the reported point being
  far from where the fire burned.
- Prescribed burns are seen far more often than wildfires (VIIRS 36.8% versus
  6.9%), because they are larger on average and lit in clear weather.
- For wildfires of 100 acres or more, the first VIIRS detection comes a median
  of 1.2 hours after the reported discovery; 33% are seen before the report;
  the slowest 10% take over 20.9 hours.
- Number of reports per year grows from about 10,000 (2015) to 33,000 (2025).
  This is reporting, not fire, so reports cannot be used as a trend.

What this gives the map: an honest "how sure are we" statement per area and
fire size, and markers for fires that were reported but never seen from orbit.

## 4. Prediction: will a fire start, and will it get large

Data: 149,912 reported wildfire starts (2014–2025) and 136,737 random
place-days, each with gridMET weather for that day and the day before, 7- and
30-day summaries, terrain, land cover, tree cover, population, LANDFIRE fire
regime, and the 2003–2013 MODIS fire climatology. Train ≤ 2021, test ≥ 2022.
LightGBM. Numbers are area under the ROC curve (0.5 = coin flip, 1 = perfect).
`results/prediction_results.json`, `figures/pred_shap_A_B.png`.

**A. A fire is reported here today**

| Model | Score |
|---|---|
| Energy Release Component alone (standard index) | 0.733 |
| Weather only | 0.824 |
| Place only (terrain, vegetation, population) | 0.813 |
| Past MODIS fire frequency only | 0.678 |
| Everything | 0.893 |
| Three-question decision tree | 0.78 |

- A model trained on other regions drops to 0.72–0.79 in a new region; a
  model trained in the region reaches 0.86–0.90. Use regional models.
- Strongest inputs: 1000-hour fuel moisture, population, land cover, minimum
  humidity, tree cover, 30-day rain.
- Past satellite fire frequency adds nothing once weather and place are in
  (0.893 with and without).

**B. Given a start, it reaches 100 or 1,000 acres**

| Target | Share of starts | ERC alone | Everything |
|---|---|---|---|
| ≥ 100 acres | 7.9% | 0.542 | 0.788 |
| ≥ 1,000 acres | 2.3% | – | 0.81 |

Limits, in plain terms:

- The scores are rankings, not yet real percentages. Calibration is the next
  step before showing "x% chance".
- The start model partly learns where people report fires (population is its
  second strongest input).
- Weather of the same day is used as if the forecast were perfect.
- Precision on large fires is low (0.30 at ≥ 100 acres): most flagged starts
  stay small.

## 5. Damage if it burns

Full notes with sources and licences in `damage-research.md`. Main results:

- **Structures**: on 20,853 incidents from ICS-209-PLUS (CC BY 4.0), fire size
  alone scores 0.71 for "any structure destroyed"; adding built-up surface
  within 5 km (GHSL) gives 0.78. Modelled flame length and the Wildfire Risk to
  Communities consequence layer add nothing.
- **Vegetation**: share of burned area at high severity in MTBS is 0.2% for
  grass, 1.6% for shrub, 10.2% for forest; in forest it is 7.5% where frequent
  low-severity fire is natural (Fire Regime Group I) and 23% where it is not
  (Group IV).
- Modelled flame length is inversely related to observed high severity (0.32
  to 0.39), so it should not be used as a severity proxy.
- Proposed score per place and day:
  `expected impact = P(start) × P(large | start) × (people term + vegetation term)`,
  shown as three separate factors and not only as one number.
- Fire regime also separates "good fire" from "bad fire": a low-severity fire
  in a Group I landscape is what the land is adapted to.

## 6. Gaps in the current map and ideas

Corrections to what exists:

| Gap | Note |
|---|---|
| Data ends 31 Dec 2025 | FIRMS area API covers the rest; S-NPP near-real-time stopped 2026-11-02, so live data is NOAA-20 and NOAA-21 |
| Region bias and post-2021 drift in the combined layer | Section 2 |
| Combined layer not scored at cell level | Section 3 gives an independent check |
| Satellite basemap is Esri World Imagery | Proprietary imagery; the challenge asks for free and open data. NASA GIBS is a candidate, not tested in the map |
| Color scale adapts to the screen | The same color means different things in different views; a fixed-scale option would help comparison |
| NOAA-21 not included; MODIS-only layer mixes Terra-only years with Terra + Aqua years | No NOAA-21 country archive exists; it is available through the API |
| Needs a running server | A static export of popular views would allow a public link without hosting |

Ideas not in the map yet:

| Idea | What we have |
|---|---|
| Burning now: live detections, fire perimeters (NIFC WFIGS), Red Flag Warnings (api.weather.gov) | Sources checked today; not built |
| Today's fire potential for the area on screen | Section 4 model; needs calibration and a daily weather pull (gridMET lags about 3 days) |
| If a fire starts here: chance it gets large, what is exposed, good or bad fire | Sections 4 and 5 |
| What satellites miss: detection rate by fire size, reported-but-not-seen markers | Section 3; markers not built |
| Nearest fire stations and a suggested priority (chance of large fire × damage) | OpenStreetMap has 14,487 U.S. fire-station points (ODbL); completeness not measured |
| Prescribed burns shown apart from wildfires, and good-fire windows | WFIGS marks prescribed burns (RX) |
| Landsat 30 m layer and a pre-2012 check | Simple Landsat-5 rule found fire pixels in 5 of 5 same-day 2007 scenes (`results/landsat5_fire_poc_2007.csv`); no omission study |
| Smoke (NOAA HMS polygons) and lightning (GOES GLM) | Sources checked only |
| A page for scientists: method, validation numbers, per-sensor comparison, downloads | Numbers in this folder |

## 7. Sources and licences

| Source | Used for | Licence |
|---|---|---|
| NASA FIRMS MODIS C6.1 and VIIRS archives | detections | NASA open data |
| Sofiev & Kouznetsov 2026, Geosci. Model Dev. 19:10123 | observation operator (parameters only; the GPL-3 code was not copied) | CC BY 4.0 |
| NIFC WFIGS Incident Locations | reported fires | U.S. Government open data |
| gridMET (Abatzoglou 2013), via Earth Engine | weather, fuel moisture, ERC | public domain |
| LANDFIRE fire regime layers | fire regime | U.S. Government open data |
| MTBS | burn severity | U.S. Government open data |
| ICS-209-PLUS (St. Denis et al. 2023) | structure loss | CC BY 4.0 |
| GHSL built-up surface | exposure | CC BY 4.0 |
| GPW v4.11 population density (CIESIN) | population input | CC BY 4.0 |
| MODIS land cover (MCD12Q1), tree cover (MOD44B), SRTM | static inputs | NASA open data |
| OpenStreetMap | fire stations | ODbL |

Not verified: exact licence wording of each catalogue entry beyond what the
provider pages state; completeness of OpenStreetMap fire stations; NASA GIBS as
a drop-in basemap.

## 8. Data sources checked and ready to use

All answered on 2026-11-14. None needs a paid account. "EE" means the Google
Earth Engine catalogue id (free account and project needed).

| Need | Source | Where | Note |
|---|---|---|---|
| Live detections | FIRMS area API: `VIIRS_NOAA20_NRT`, `VIIRS_NOAA21_NRT`, `MODIS_NRT`, `LANDSAT_NRT`, `GOES_NRT` | firms.modaps.eosdis.nasa.gov/api/area | Needs MAP_KEY. GOES limited to a 1–2 day range. S-NPP NRT stopped 2026-11-02 |
| Yearly archive without a key | FIRMS country files | `firms.modaps.eosdis.nasa.gov/data/country/<sensor>/<year>/<sensor>_<year>_United_States.csv` | modis, viirs-snpp, viirs-jpss1. No NOAA-21 files, no 2026 file |
| Reported fires and prescribed burns | NIFC WFIGS Incident Locations | `services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations/FeatureServer/0/query` | 431,631 records, 2014 →. Records appear a median of 9 minutes after discovery. No structure or fatality fields |
| Fire perimeters | NIFC WFIGS perimeters; NASA FEDS | NIFC open data; `openveda.cloud/api/features` | FEDS collections listed, not used yet |
| Weather warnings | NWS alerts API | `api.weather.gov/alerts/active` | Red Flag Warnings; 0 active when checked |
| Daily weather and fire danger | gridMET | EE `IDAHO_EPSCOR/GRIDMET` | 4 km, 1979 →, about 3 days behind. ERC, BI, fuel moisture, VPD, wind |
| Fire regime, vegetation | LANDFIRE FRG, MFRI, VDep, EVT | EE `LANDFIRE/Fire/...`, `LANDFIRE/Vegetation/...` | 30 m |
| Burn severity | MTBS mosaics and boundaries | EE `USFS/GTAC/MTBS/...` | 30 m, 1984 → |
| Burned area | MCD64A1; FIRMS `BA_MODIS`, `BA_VIIRS` | EE; FIRMS | Monthly |
| Structure loss per incident | ICS-209-PLUS | figshare 10.6084/m9.figshare.19858927.v3 | 1999–2020 |
| Buildings and people | GHSL built-up and population; GPW | EE `JRC/GHSL/P2023A/...`, `CIESIN/GPWv411/...` | Global, so the method transfers outside the U.S. |
| Smoke | NOAA HMS smoke polygons | `satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Smoke_Polygons/Shapefile/<yyyy>/<mm>/` | Daily shapefiles |
| Lightning | GOES-19 GLM | `s3://noaa-goes19/GLM-L2-LCFA` | Public bucket, 180 files per hour |
| Geostationary fire | GOES-18 FDCF | EE | Every 10 minutes, coarse |
| Soil moisture | SMAP L4 | EE | Not used yet |
| Old Landsat scenes | Landsat Collection 2 | EE; Planetary Computer STAC | Landsat 5 back to 1984 |
| Fire stations | OpenStreetMap `amenity=fire_station` | Overpass API | 14,487 U.S. points. Send a User-Agent header or it answers 406 |

Did not work from a script: FPA FOD download (403), WRC full archive (403),
HIFLD fire stations (address no longer valid).

Licence warning: `pyretechnics` (fire-behaviour library) moved to a non-OSI
licence on 2026-10-05; details in `damage-research.md`.

## 9. Product ideas, by audience

The challenge names early-warning staff, emergency responders, scientists,
land managers and firefighters. One way to serve all of them from the map:

- **A briefing for the area on screen**, in this order: burning now → today's
  fire potential → why → if a fire starts → is this normal (your area
  calendar) → how sure are we.
- **Fire potential in familiar words**: the five fire-danger levels
  responders already use (Low to Extreme), plus a number and "× normal for
  this week". A chart of this year against the usual range, in the style of
  the NWCG Fire Danger PocketCard, answers "why".
- **How sure are we**: a badge per area built from section 3 (fire size the
  satellites reliably see here) and from cloud cover and time between passes.
- **Fire-blind zones**: places and days where cloud or pass gaps hide fire
  while danger is high; fill them with reported fires, lightning and the
  model's risk. Not built.
- **Suggested priority**: when several fires burn, rank them by chance of
  growing large × what is exposed, and show the closest stations. Label it a
  suggestion, not a dispatch order.
- **Good-fire windows** for land managers: days when weather allows a
  prescribed burn in a landscape adapted to frequent fire.
- **Time to first detection** (section 3) as a stated fact per region: it
  tells a responder how much to rely on the map for new starts.
- **A data page for scientists**: method, the validation tables above,
  per-sensor series and downloads.

## 10. Trained models

`models/` holds the three saved models from section 4, the full training table
(286,649 rows) and `MODEL_CARDS.md`, which states for each model the question
it answers, training, validation and test years, row counts, inputs, scores,
reliability and limits. `models/predict_example.py` shows how to load them.
Before wiring them into the map, read "The output is not a real-world
probability" in the cards.

## 11. How this compares with another public entry (SHIFT)

Read on 2026-11-14 from github.com/squadronzero/project-shift (Apache-2.0).
It is a global harmonized calendar with its own list of scientific limits.
Points where the work in this repository and in this folder differs:

- It converts with ratios and assumes the VIIRS / MODIS ratio does not change
  with fire activity. We measure that the ratio falls as activity rises
  (slope 0.71 where a fixed ratio means 1).
- It does not use the Sofiev & Kouznetsov observation operator; this
  repository does.
- Its outside check is GFED, which is itself built from MODIS. Section 3 here
  checks against agency reports that do not depend on either sensor.
- It flags cloudy months; it has no per-fire-size detection rate, no reported
  fires, no fire potential and no damage estimate.

Its repository may have changed since we read it.
