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

## 12. All ideas in one table

Status words: **measured** = numbers in this folder; **trained** = model saved
in `models/`; **source checked** = the data answered on 2026-11-14 but nothing
is built; **idea** = not started. "Why" gives the measurement or source behind
each idea; numbers come from sections 2 to 5.

| # | Idea | Why | For whom | Data it needs | Status | Where |
|---|---|---|---|---|---|---|
| 1 | Harmonized MODIS + VIIRS calendar with unusual weeks | The challenge asks for it. Naive counts jump 3.42× when VIIRS arrives, so an unharmonized record shows a false rise | everyone | FIRMS archive | measured (and built in this repository) | section 2 |
| 2 | Count active cell-days, not detections, before converting | Removes a third of the sensor gap before any model (ratio 5.86 → 4.01) and the ratio varies less | scientists | FIRMS archive | measured | section 2 |
| 3 | Region and year correction on top of the observation operator | The operator is 16% low in the East and 18% high in the West; a user comparing regions would be misled | scientists | FIRMS overlap years | measured, not applied | section 2, `results/obsop_region_month.csv` |
| 4 | Power-law conversion as a simple cross-check | Cheap independent check: error 0.119 against 0.139 for a fixed ratio on held-out years | scientists | FIRMS overlap years | measured | `results/conversion_models.json` |
| 5 | State the orbit-drift limit after 2021 | Every method drifts 5–13% after 2021; saying so is more honest than hiding it | scientists | – | measured as a symptom, cause not isolated | section 2 |
| 6 | Check against reported fires (independent ground truth) | Scoring a MODIS-equivalent layer against MODIS is circular; agency reports depend on neither sensor | scientists, judges | NIFC WFIGS | measured | section 3 |
| 7 | "What satellites miss": detection rate by fire size and region | 2% of fires under 1 acre are seen and 72% over 10,000: a blank map does not mean no fire | responders, scientists | WFIGS + FIRMS | measured | section 3 |
| 8 | Reported-but-not-seen fire markers on the map | Reports appear a median of 9 minutes after discovery, before most satellite passes | responders | WFIGS live + FIRMS live | measured (one week), not on a map | section 14 |
| 9 | Time from discovery to first detection, per region | Median 1.2 h, slowest tenth over 20.9 h: tells a responder how far to trust the map for new starts | responders | WFIGS + FIRMS | measured (national) | section 3 |
| 10 | Fire-blind zones: cloud × time between passes × danger | Even fires over 10,000 acres go unmatched 28% of the time within 3 days; cloud and gaps between passes are a likely part of the reason. Not measured | early warning | cloud mask, orbit tracks, gridMET | idea | section 9 |
| 11 | Fill blind zones with data satellites do not give: reports, lightning, model risk | Where the satellites are blind, other evidence is the only evidence | early warning | WFIGS, GOES GLM, models | source checked | sections 8, 9 |
| 12 | "How sure are we" badge per area | One plain sentence per area turns sections 2 and 3 into something a non-specialist can act on | everyone | ideas 7 and 10 | idea | section 9 |
| 13 | Burning now: live detections, perimeters | The map stops at 2025; the named users work on today's fires | responders | FIRMS area API, WFIGS perimeters, FEDS | source checked | section 8 |
| 14 | Red Flag Warning banner | The official warning responders already act on; showing it avoids contradicting it | responders | api.weather.gov | source checked | section 8 |
| 15 | Today's fire potential (chance a fire starts) | 0.893 against 0.733 for the standard index on years never seen in training | early warning, firefighters | gridMET + static layers | trained, not calibrated | section 4, `models/` |
| 16 | Regional models instead of one national model | A model trained elsewhere drops to 0.72–0.79; trained in the region it reaches 0.86–0.90. Agrees with Shmuel et al. 2025 | scientists | same | measured, not saved | section 4 |
| 17 | Three-question decision tree as the plain "why" | Three questions reach 0.78, above the standard index, and can be read aloud. Same approach as Shmuel et al. 2025 | firefighters | same | measured (0.78) | `results/prediction_results.json` |
| 18 | Fire potential in the five fire-danger words, plus "× normal" | Firefighters already use the five levels; a new scale would need training | firefighters | idea 15 | idea | section 9 |
| 19 | This year against the usual range (PocketCard-style chart) | The NWCG PocketCard is the format crews are trained to read | firefighters | gridMET history | idea | section 9 |
| 20 | Top reasons for today's level (driest fuels, wind, no rain) | A level without reasons is not trusted; the strongest inputs are already known (fuel moisture, humidity, rain) | firefighters | model explanations | measured nationally, not per place | `figures/pred_shap_A_B.png` |
| 21 | Chance a start becomes large (100 / 1,000 acres) | 0.79–0.81 where the standard index is near chance (0.54): most starts stay small, and this separates them | responders | same as 15 | trained | section 4, `models/` |
| 22 | People and buildings exposed if it burns | Built-up surface within 5 km lifts structure-loss prediction from 0.71 to 0.78; flame-length layers add nothing | emergency managers | GHSL built-up within 5 km | measured | section 5, `damage-research.md` |
| 23 | Vegetation damage if it burns | High-severity share is 0.2% in grass, 1.6% in shrub, 10.2% in forest, and 7.5% versus 23% by fire regime within forest | land managers | land cover type × LANDFIRE fire regime, MTBS | measured | section 5 |
| 24 | Expected impact = start × large × damage, shown as three factors | The standard risk form (likelihood × consequence, Scott et al. 2013); one number alone hides why a place is red | everyone | ideas 15, 21, 22, 23 | idea, parts ready | section 5 |
| 25 | Good fire versus bad fire | Low-severity fire in a frequent-fire landscape is beneficial (Steel et al. 2015); treating all fire as bad misleads land managers | land managers | LANDFIRE fire regime, WFIGS prescribed-burn flag | measured in part | sections 3, 5 |
| 26 | Prescribed burns shown apart from wildfires | Prescribed burns are seen five times as often as wildfires, so they inflate the calendar where burning is planned | land managers, scientists | WFIGS `RX` | measured (seen 37% versus 7%) | section 3 |
| 27 | Good-fire windows: days suitable for prescribed burning | Land managers are a named audience and need the opposite of a danger alert. Reference: Matsypura et al. 2018 (abstract only) | land managers | gridMET + fire regime | idea | section 9 |
| 28 | Nearest fire stations | Requested as critical for responders; the points exist as open data | firefighters | OpenStreetMap | source checked, completeness unknown | section 8 |
| 29 | Suggested priority when several fires burn: chance of large × exposed, closest stations | When resources are short the question is which fire first; the two factors that answer it are ideas 21 and 22 | dispatch, responders | ideas 21, 22, 28 | idea | section 9 |
| 30 | Ranked list "highest potential today" | Early-warning staff scan many areas; a ranked list is faster than panning a map | early warning | idea 15 | idea | – |
| 31 | Smoke: plume outlines as context and as a hint of fire under cloud | Smoke is visible when the fire under it is not, and it affects crews and the public directly | responders | NOAA HMS polygons | measured (one week), not on a map | section 14 |
| 32 | Lightning as a cause of new starts | Natural causes are 30% of wildfire reports with a known cause in 2023–2024 (9,236 of 30,491) | early warning | GOES GLM | measured (two days) | section 16 |
| 33 | Landsat 30 m detections for close-up views | 30 m shows the fire edge that 375 m and 1 km cannot | responders, scientists | FIRMS `LANDSAT_NRT` | source checked | section 8 |
| 34 | Landsat check of the pre-2012 MODIS-only years | Before 2012 there is no VIIRS to check MODIS against; Landsat is the only finer record | scientists | Landsat 5 / 7 Collection 2 | proof of concept (5 of 5 scenes) | `results/landsat5_fire_poc_2007.csv` |
| 35 | Geostationary detections between polar passes | Polar satellites pass a few times a day; the slowest tenth of first detections takes over 20.9 h | responders | FIRMS `GOES_NRT`, GOES FDCF | source checked | section 8 |
| 36 | Briefing for the area on screen, in a fixed order | The named users ask 'what about my area today', not 'which layer shall I turn on' | everyone | all of the above | idea | section 9 |
| 37 | Click any unit: county, grid cell or drawn area | The area calendar already works for any box, so the cost is small | everyone | area calendar already supports any box | idea | – |
| 38 | Month and year views and "× median" next to the weekly calendar | Weekly cells are noisy for small areas; managers plan by season and year | scientists, managers | calendar table | idea | – |
| 39 | Data page for scientists: method, validation, per-sensor series, downloads | Scientists are a named audience and need the method and its errors, not the briefing | scientists | this folder | numbers ready | sections 2–5 |
| 40 | Short scroll story for first-time visitors and judges | A first-time visitor needs one worked example to understand the units | judges, public | one example fire | idea | – |
| 41 | Method works outside the U.S. with global layers | The challenge is global; these inputs exist worldwide. Not tested | global users | GHSL, GPW, FIRMS, MODIS products | not tested | section 8 |

## 13. Research used, and what each decision rests on

How much of each paper was read is stated, because a title is not evidence.

**Read in full or in the relevant parts**

| Source | What we took from it | Decision it supports |
|---|---|---|
| Sofiev & Kouznetsov 2026, *Geosci. Model Dev.* 19:10123 (CC BY 4.0) | detection-limit and detection-probability formulas and parameters for MODIS and VIIRS | convert VIIRS to MODIS-equivalent with a physical operator, not a ratio; direction VIIRS → MODIS because a missed fire cannot be recreated |
| Shmuel, Lazebnik, Heifetz, Glickman & Price 2025, *npj Natural Hazards*, doi:10.1038/s44304-025-00126-y | regional fire-weather models beat global ones (0.79 → 0.86 with one decision tree per country) | test regional against national models (idea 16); offer a small decision tree as the readable version (idea 17); use a single index as the baseline to beat |
| Parks et al. 2018, *Environ. Res. Lett.* 13:044037 | drivers of high-severity fire in western U.S. forests: live fuel carries 53% of the influence, fire weather 23%, climate 14%, terrain 10% | predict vegetation damage from vegetation type and fire regime (idea 23) |
| SHIFT repository and its limits file (Apache-2.0) | how a ratio-based calendar is built and where its authors say it is weak | section 11 |
| FRP_OOp repository (GPL-3) | checked the published parameters against the code; code not copied | same as Sofiev & Kouznetsov |
| Team repository pipeline and server | – | section 6 |

**Abstract only** (details and DOIs in `damage-research.md`)

| Source | Point used |
|---|---|
| Dillon et al. 2011; Birch et al. 2015 | terrain and existing vegetation cover dominate burn severity |
| Parks et al. 2019 | how satellite severity indices relate to field severity |
| Heward et al. 2013 | fire radiative power per pixel is not a reliable severity measure → we do not turn FRP into damage |
| Syphard et al. 2012; Knapp et al. 2021 | structure loss depends on housing arrangement and neighbouring structures → use built-up surface nearby (idea 22) |
| Higuera et al. 2023 | rising structure loss in the West, mostly from human-caused fires |
| Steel et al. 2015 | in frequent-fire forests, severity rises with time since last fire → good versus bad fire (idea 25) |
| St. Denis et al. 2023, *Sci. Data* 10:112 | the ICS-209-PLUS incident data set used for the structure-loss test |

**Title or data description only**: Scott, Thompson & Calkin 2013 (risk =
likelihood × consequence, the shape of idea 24); Finney et al. 2011;
Radeloff et al. 2018; Thode et al. 2011; Wooster et al. 2005;
Schroeder et al. 2014; Abatzoglou 2013 (gridMET).

**Our own measurements that decided something**

| Decision | Evidence |
|---|---|
| Count cell-days, not detections | ratio 5.86 → 4.01 and steadier (section 2) |
| Do not use modelled flame length as severity or as structure risk | scores 0.32–0.39 against MTBS; adds nothing to structure loss (section 5) |
| Do not use past satellite fire frequency as a predictor | 0.893 with and without it (section 4) |
| Do not present the fire-start score as a percentage yet | reliability table in `models/MODEL_CARDS.md` |
| Train on reports, not on satellite detections | satellites see 2% of the smallest fires (section 3) |
| gridMET for weather | 4 km, daily since 1979, already contains ERC and fuel moisture for the U.S. |
| Split by year, not at random | neighbouring days and places are near-copies; a random split would flatter the score |

**Saved but not used**

| Source | Why not |
|---|---|
| Zeng et al. 2026, *Fire* 9:511, doi:10.3390/fire9110511 (review of 811 papers on machine learning for forest-fire prediction) | read only after the models were trained. Its conclusions (tree ensembles strong for susceptibility; open problems are class imbalance, transfer between regions, interpretability) agree with what we found, but it did not shape any choice |
| Sengupta & Woodford 2025, *Appl. Comput. Geosci.*, doi:10.1016/j.acags.2025.100266 (review of explainable machine learning for wildfire prediction) | could not be opened; not read |
| Matsypura, Prokopyev & Zahar 2018, *Eur. J. Oper. Res.*, doi:10.1016/j.ejor.2017.06.050 (optimizing prescribed burning) | title and abstract only; a candidate reference for idea 27, nothing built on it |
| Shmuel et al. code files | not used; our models are written separately |
| NASA GFWED fire-weather database | considered for weather; gridMET chosen for the U.S. (finer grid, includes ERC). GFWED remains the option for use outside the U.S. |

## 14. Blind-zone test on one real week

`scripts/40_blind_feeds.py`, `results/blind_week_metrics.json`. Fires
discovered 9–11 November 2026 in the contiguous U.S., from the live WFIGS
feed: 172 wildfires and 91 prescribed burns. Detections are FIRMS
near-real-time VIIRS (NOAA-20, NOAA-21) and MODIS for 9–13 November, matched
within 2 km on the discovery day or the two days after. Cloud is the observed
cloud flag at the Terra and Aqua daytime passes (MOD09GA / MYD09GA) on the
discovery day and the next day; "cloudy" means at least half of those looks
were cloudy or mixed. Smoke is the NOAA HMS daily outlines.

| | Wildfires | Prescribed burns |
|---|---|---|
| Reports | 172 | 91 |
| Seen by VIIRS or MODIS | 9.9% | 37.4% |
| Seen by Landsat | 2.3% | 6.6% |
| Cloudy at the passes | 63% | 81% |
| Seen when clear | 12.7% (of 63) | 58.8% (of 17) |
| Seen when cloudy | 8.3% (of 109) | 32.4% (of 74) |
| Reported but never seen | 155 | 57 |
| ... of which cloudy | 100 | 50 |
| Under a smoke outline (same or next day) | 75% | 68% |

What it says:

- Reports are the feed that fills the gap: 155 of 172 wildfires were known to
  the agencies and invisible in the detections. Two thirds of the wildfires
  were under 1 acre, so most would be missed with a clear sky too.
- Cloud matters most for fires large enough to see: prescribed burns were
  seen 59% of the time when clear and 32% when cloudy.
- Smoke outlines covered 15–33% of the country on these days and 75% of
  wildfire reports. That is a real signal, but the outlines are regional: they
  say "fire somewhere in here", not where.
- Landsat adds little for new fires because it passes rarely.

Limits: one week, in November, with 20 wildfires of 10 acres or more. The
match window is one day shorter than in section 3. Cloud is taken from MODIS
passes and applied to VIIRS, which passes at a similar time of day.

## 15. What the models lose without today's weather

`scripts/42_lagged_weather_test.py`, `results/lagged_weather_test.json`. Same
table and split as the saved models; only the inputs change. Scores are area
under the ROC curve on 2022 onward.

| Inputs | Fire starts | Reaches 100 acres | Reaches 1,000 acres |
|---|---|---|---|
| Today's and yesterday's weather, place, season (saved models) | 0.893 | 0.788 | 0.810 |
| Only what is known the evening before | 0.885 | 0.775 | 0.798 |
| Only 7- and 30-day summaries | 0.879 | 0.760 | 0.781 |
| Place and season only, no weather | 0.860 | 0.750 | 0.771 |

Two readings, both important:

- A forecast for tomorrow can be made from data known today with a small
  loss (0.893 → 0.885). The models do not need a weather forecast to be useful
  one day ahead. gridMET itself is about 3 days behind; that lag was not
  tested, but the 30-day-summary row (0.879) suggests the loss stays small.
- Most of the fire-start score comes from place and season (0.860 with no
  weather at all). The random non-fire rows are spread over the whole country,
  so the model first learns where and when fires are reported at all. Weather
  adds 0.03. The score therefore says less about "is today worse than usual
  here" than 0.893 suggests. A fairer test of that question compares each
  fire with other days at the same place; not done.

## 16. Lightning as an early sign of fire

`scripts/41_lightning_test.py`, `results/lightning_test.json`. Western U.S.
(longitude −125 to −104), wildfires discovered on 31 July and 1 August 2025:
328 with cause "Natural", 79 "Human", 192 "Undetermined". Lightning is every
flash from the GOES-18 lightning mapper (GLM) over 72 hours, 545,100 flashes
in the box, all 72 hours complete. The question: was there a flash near the
fire's reported point in the hours before discovery?

| Flash within 5 km in the 24 h before discovery | Share | Median hours from first flash to discovery |
|---|---|---|
| Natural-cause fires (328) | 83.5% | 9.5 |
| Undetermined (192) | 38.0% | 10.9 |
| Human-caused fires (79) | 8.9% | 18.1 |
| Random points in the same box and hours (3,000) | 22.9% | 17.0 |

Within 10 km the natural-cause share is 92.7% (random points 32.5%).

What it says:

- Lightning marks where lightning fires will be reported, hours ahead and
  through cloud: a median of 9.5 hours before discovery.
- It is not a fire detector. 23% of random points also had a flash nearby, so
  most flashes start nothing. It is a "watch here" layer, strongest when
  combined with dry fuels.
- Undetermined fires sit between the two groups (38%), which suggests a part
  of them are lightning fires.

Limits: these two days were chosen because they had the most natural-cause
reports of 2025, so lightning was widespread; a quiet day was not tested.
Agencies may use lightning maps when they assign the cause, which would
inflate the 83.5%. The lightning mapper locates flashes to several
kilometres, and it misses some. Download size is about 5 GB for 72 hours, so
only flash positions inside the box are kept.
