# Model cards

Three models, trained on 2026-11-14 by `../scripts/33_save_models.py`. They are
the same models whose scores are reported in `../README.md` section 4, saved to
files. Every number below is in `models_meta.json`.

| File | Question it answers |
|---|---|
| `model_A_ignition.txt` | Will a wildfire be reported at this place on this day? |
| `model_B_large100.txt` | If a wildfire starts here today, will it reach 100 acres or more? |
| `model_B_large1000.txt` | If a wildfire starts here today, will it reach 1,000 acres or more? |
| `training_table.parquet` | Every row used for training, validation and testing (286,649 rows) |
| `models_meta.json` | Inputs, settings, row counts, scores, reliability tables, library versions |
| `predict_example.py` | Loads each model and scores a few rows |

These are experiments, not operational forecasts. Do not use them to decide
where to send people or equipment.

## What is common to all three

**Type.** Gradient-boosted decision trees (LightGBM 4.7.0, binary
classification). Saved in LightGBM's text format; load with
`lightgbm.Booster(model_file=...)`. Trained with scikit-learn 1.9.1,
pandas 3.1.1, numpy 2.5.4.

**Settings.** Up to 600 trees, learning rate 0.05, 63 leaves, at least 50 rows
per leaf, 80% of rows and 80% of columns per tree, early stopping after 50
rounds without improvement on the validation year.

**Area.** Contiguous U.S. only (latitude 24.4 to 49.5, longitude −125 to −66.9).
No Alaska, Hawaii or territories.

**Periods.**

| Split | Years | Use |
|---|---|---|
| Training | 2014–2020 | fit the trees |
| Validation | 2021 | choose the number of trees |
| Test | 2022 onward | all reported scores; never seen in training |

**Label source.** NIFC WFIGS Incident Locations, wildfires only (`WF`), 2014 to
2025, one record per 0.05° cell and day (the largest is kept). Date is the
discovery time shifted to local solar time. Size is `FinalAcres`, or
`IncidentSize` when that is empty.

**Inputs (28).** One value per place and day.

| Group | Columns | Source |
|---|---|---|
| Weather, same day | `erc` energy release component, `bi` burning index, `fm100` and `fm1000` dead fuel moisture, `vpd` vapour pressure deficit, `vs` wind speed, `rmin` `rmax` relative humidity, `tmmx` maximum temperature (K), `pr` rain, `srad` sunlight | gridMET, 4 km (Earth Engine `IDAHO_EPSCOR/GRIDMET`) |
| Weather, day before | `erc_l1`, `fm100_l1`, `vpd_l1`, `vs_l1` | gridMET |
| Weather, recent | `erc7` mean of 7 days, `erc_max30` maximum of 30 days, `pr30` rain in 30 days | gridMET |
| Season | `doy` day of year | – |
| Terrain | `elevation`, `slope` | SRTM |
| People | `log_pop` = log(1 + people per km²) | GPW v4.11, 2020 |
| Vegetation | `lc` land cover class (category), `treecover` percent | MCD12Q1 2019 (IGBP), MOD44B 2019 |
| Fire regime | `frg` Fire Regime Group (category), `mfri` mean fire return interval class | LANDFIRE |
| Past fire | `log_clim_m`, `log_clim_y` = log(1 + MODIS active cell-days per month / per year in the 0.25° cell, 2003–2013) | FIRMS MODIS archive |

Past fire uses 2003–2013 only, so it never overlaps the label years.

**Shared limits.**

- Weather of the same day is used as if the forecast were perfect. With a real
  forecast the scores will be lower. Not measured.
- gridMET is about 3 days behind, so "today" needs a forecast source that is
  not wired in.
- Land cover, tree cover and population are fixed at 2019–2020 for all years.
- Labels are reports, not fires. Reports per year in the table grow from 577
  (2014, the service was new) to 19,826 (2025). Places with more people and
  more agencies report more.
- Not tested outside the contiguous U.S.

## Model A: a wildfire is reported here today

**Training data.** 149,912 reported wildfire starts and 136,737 random
place-days (random point in the bounding box, random day 2014-01-01 to
2026-11-08; points over sea or outside the U.S. were dropped when weather was
missing). All starts of 100 acres or more are included; smaller ones are a
random subset.

| Split | Rows | Fire starts |
|---|---|---|
| Training 2014–2020 | 134,840 | 60,262 |
| Validation 2021 | 26,547 | 15,768 |
| Test 2022–2026 | 125,262 | 73,882 |

Trees used: 428.

**Test results.**

| Measure | Value |
|---|---|
| Area under ROC curve | 0.893 |
| Area under precision-recall curve | 0.92 (share of starts in the test table: 0.59) |
| Brier score | 0.139 (0.242 for always answering the average) |
| By region | West 0.873, Central 0.869, East 0.843 |
| Energy release component alone, for comparison | 0.733 |

Known flaw in the test table: the 9,044 random place-days from 2026 have no
fire starts next to them, because 2026 reports were not downloaded. Without
2026 the score is 0.896 (116,218 rows), so the conclusion does not change.

**The output is not a real-world probability.** The table holds about as many
fire starts as non-fire rows, while in reality a start at a given place and day
is rare. A score of 0.9 means "ranks among the most fire-like place-days", not
"90% chance". Within the table the score is also too low at the bottom:

| Mean score | Share that were fire starts |
|---|---|
| 0.008 | 0.050 |
| 0.036 | 0.136 |
| 0.103 | 0.251 |
| 0.239 | 0.417 |
| 0.445 | 0.598 |
| 0.651 | 0.756 |
| 0.794 | 0.847 |
| 0.881 | 0.907 |
| 0.934 | 0.951 |
| 0.974 | 0.986 |

To show a percentage, the score has to be rescaled to the true rate of starts
per map cell and day. Not done. Until then, show it as a rank or as a level
(for example the five fire-danger words).

**Other findings** (from `../scripts/32_train_eval.py`):

- A model trained without a region scores 0.72–0.79 in that region; a model
  trained only on that region scores 0.86–0.90. Regional models were tested
  but are not saved here.
- Strongest inputs: `fm1000`, `log_pop`, `lc`, `rmin`, `treecover`, `pr30`.
- Past fire adds nothing: 0.893 with and without it.
- Population is the second strongest input, so the model partly learns where
  fires get reported.

## Model B-100: a start reaches 100 acres or more

**Training data.** Only the fire starts from the table above that have a
recorded size: 123,302 rows.

| Split | Rows | Reached 100 acres |
|---|---|---|
| Training 2014–2020 | 50,716 | 5,964 |
| Validation 2021 | 10,387 | 1,083 |
| Test 2022–2025 | 62,199 | 4,934 |

Trees used: 128.

**Test results.**

| Measure | Value |
|---|---|
| Area under ROC curve | 0.788 |
| Area under precision-recall curve | 0.303 (share of large fires in the test table: 0.079) |
| Brier score | 0.0668 (0.0730 for always answering the average) |
| By region | Central 0.845, East 0.769, West 0.758 |
| Energy release component alone | 0.542 |

**Reliability.** The score runs about a third too high:

| Mean score | Share that reached 100 acres |
|---|---|
| 0.011 | 0.007 |
| 0.030 | 0.024 |
| 0.056 | 0.039 |
| 0.101 | 0.071 |
| 0.214 | 0.141 |
| 0.449 | 0.308 |

(Six of ten bins shown; all ten are in `models_meta.json`.)

**Limits.**

- Large fires are over-represented: the table keeps every start of 100 acres
  or more but only a subset of the smaller ones. In the table 9.7% of starts
  are large; among all 247,136 de-duplicated reports the share is about 4.9%.
  Real-world chances are therefore lower than the score, on top of the
  over-statement above.
- Most starts the model flags stay small: precision is low.
- Size depends on how hard and how early a fire is fought, which the model
  does not see.

## Model B-1000: a start reaches 1,000 acres or more

Same rows and splits as B-100.

| Split | Rows | Reached 1,000 acres |
|---|---|---|
| Training 2014–2020 | 50,716 | 2,079 |
| Validation 2021 | 10,387 | 354 |
| Test 2022–2025 | 62,199 | 1,404 |

Trees used: 92.

| Measure | Value |
|---|---|
| Area under ROC curve | 0.810 |
| Area under precision-recall curve | 0.123 (share in the test table: 0.023) |
| Brier score | 0.0214 (0.0221 for always answering the average) |
| By region | Central 0.887, West 0.800, East 0.738 |

The Brier score is barely better than the average answer: this model ranks
starts usefully but should not be read as a percentage. Its top tenth of scores
averages 0.162 while 10.8% of those starts reached 1,000 acres. The limits of
B-100 apply, more strongly, because there are few such fires.

## The training table

`training_table.parquet`, 286,649 rows, 27 MB. Main columns:

| Column | Meaning |
|---|---|
| `id` | row number from the sampling step |
| `lat`, `lon`, `date` | place and local day |
| `y` | 1 = reported wildfire start, 0 = random place-day |
| `acres` | final size, fire starts only (empty for some) |
| `FireCause`, `POOState` | as reported, fire starts only |
| `year`, `doy`, `month`, `region` | derived from date and longitude (West < −104, Central < −90, East) |
| `firms_clim_month`, `firms_clim_year`, `c025` | past MODIS fire in the 0.25° cell |
| `pop_density` | people per km² |
| the 28 inputs | see the table above |

Missing codes: `frg` −9999 and classes 111–133 are LANDFIRE fill, water, snow, barren, sparse or
indeterminate codes, kept as their own categories.

To rebuild from nothing: `22_wfigs_download.py` → `21_us_aggregate.py` →
`30_build_samples.py` → `31_gee_features.py` (Earth Engine, in
300-point batches; 1,500-point batches failed) → `33_save_models.py`.

## Licences of the training data

NIFC WFIGS: U.S. Government open data. gridMET: public domain. LANDFIRE, SRTM,
MODIS products, FIRMS: U.S. Government or NASA open data. GPW v4.11: CC BY 4.0.
The table is a derived product of these and can be shared with attribution.
