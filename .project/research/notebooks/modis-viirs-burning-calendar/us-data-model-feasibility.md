# U.S. wildfire data and model feasibility

The prototype covers all 50 states, including Alaska and Hawaii. Territories can be represented by the same design and need a coverage decision. Mexico and other countries are later releases. Small requests below are access checks. National ingestion, coverage, model performance, and the website are still to be demonstrated.

## A shared analysis grid

Use stable cell IDs on a global equal-area grid. Test a 1 km historical grid, plus 375 m and 1 km grids for the forecast. See Revised spatial design for the scale tests and rendering rules. Clip cells against a land and geography mask, handle the antimeridian for Alaska, and test Alaska, Hawaii, and multiple mainland fire regimes. Retain native-resolution evidence separately for drill-down.

1. **Observations.** Archive original CSVs, rasters, and polygons with source, product version, geometry, observation time, and first availability or ingestion time. Use geographic and temporal joins with an explicit matching rule. Smoke polygons, aircraft and incident perimeters, Landsat images, and fuel rasters retain their own timestamps and coverage.
2. **Cell-day-sensor facts.** Map detections and observation masks to each cell. Keep raw detection count, detection-present flag, footprint/time support, clear observed area and detection confidence separately. Distinguish a supported zero from unknown coverage. Retain a positive detection even when the rest of the cell or week has poor coverage, and define minimum coverage for assigning a negative. Reingesting the same product version should be idempotent.
3. **Calendar.** Test common-grid active cell-days summed per week or month. Fit a seasonal and regional conversion on overlapping MODIS and VIIRS years only if it improves held-out performance over unadjusted common-grid statistics. Use matched Aqua and NOAA-20 daytime overpasses as a candidate calibration pair and test whether including additional passes improves or distorts comparability. Store observed counts, adjusted estimates, source and observation coverage. A single fire can produce many detections. Report uncertainty in the pre-VIIRS reconstruction and verify the chosen measure against raw totals and the seasonal patterns.
4. **Forecast features.** One row per cell and forecast issue date. Include seasonal historical detection frequency, 7- and 28-day activity, nearby-cell activity, LANDFIRE fuel proportions, recent clear-sky HLS greenness/moisture proxies and scene age, lagged NOAA smoke overlap, and archived GFS forecast summaries for lead days 1–7. Vegetation greenness is a reflectance proxy. Do not infer actual fuel moisture from an index alone. Require source material to have been available at issuance and use fuel-map vintages valid at the time. The model target is at least one qualifying NOAA-20 VIIRS vegetation-fire detection in the next seven days. NOAA-20 is a candidate fixed reference because it has more years than NOAA-21. Train against actual subsequent observations. MODIS-era harmonized estimates can inform historical climatology or lagged features if their validation warrants it.
5. **Decision context.** Publish the seven-day probability and supporting evidence for where to look. For incident review, display recent detections, source timestamps and confidence, Landsat observations, burn records, smoke and aircraft perimeters when available. For prevention, include fuels, prior treatment and exposure, with areas for expert review. Do not derive treatment priority directly from the weekly detection probability.

Store dense model features and raw archives in partitioned files. The national website should serve prepared summaries and tiles.

## Model comparison

| Candidate | Role and test |
| --- | --- |
| Seasonal frequency | Use prior years for the same region and part of the year, with sparse cells shrunk toward their region. Baseline for seasonality. |
| Persistence | Use recent detections as a predictor of continuing activity. Baseline for near-term persistence. |
| Regularized logistic regression | Combine the two baselines, nearby activity, and selected inputs. First learned probability model. |
| LightGBM | Test whether interactions between location, year, fuels, weather and recent activity improve skill. Evaluate added sources one at a time and select using validation years. |

Use chronological splits with a seven-day buffer at boundaries to keep target windows from crossing between folds. Reserve the latest complete standard-processing periods and geographic blocks in different fire regimes, including Alaska and Hawaii where support allows. Fit feature transforms, thresholds and probability calibration using training or validation only. Use precision-recall for ranking rare detections, Brier score and reliability plots for probability quality, and recall among the highest-ranked area for monitoring. Report performance and coverage by geography and season. Compare all models on the same eligible sample. Measure the gain from vegetation, past smoke and forecast weather before committing model complexity. The Bolivia results motivate the comparison, but national transfer awaits measurement. [Bolivia benchmark](https://arxiv.org/abs/2611.08539)

## Source checks and remaining work

| Input | Verified on November 14, 2026 | Next proof |
| --- | --- | --- |
| MODIS, NOAA-20 and NOAA-21 FIRMS | Three public 24-hour CSVs returned 200 and records dated November 13. MODIS and VIIRS use different brightness fields. The sampled rolling headers omit the vegetation-fire type field. | Validate authenticated area and standard-history requests, identify a defensible vegetation filter for recent data, and build archive/version handling. [FIRMS Area API](https://firms.modaps.eosdis.nasa.gov/api/area) |
| MODIS and VIIRS masks | Earthdata CMR found six MYD14A1 v061 tiles over a multi-week request and ten VJ114IMG v002 swaths in a four-day window. | With Earthdata access, read a mask, classify clear/cloud/missing support, and compare support against detection locations. Confirm Aqua and Terra coverage. [MODIS mask](https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/MYD14A1/) · [VIIRS mask](https://www.earthdata.nasa.gov/s3fs-public/2025-06/VIIRS_C2_AF-375m_User_Guide_1.2.pdf) |
| Landsat and Sentinel-2 | CMR returned nine HLS L30 and six HLS S30 results for a four-day Park Fire catalog query. Two guessed public FIRMS Landsat rolling paths returned 404. | Download one HLS tile and QA mask with Earthdata Login. Use documented keyed FIRMS LANDSAT_NRT and measure footprint coverage by region. [NASA HLS access](https://hls.gsfc.nasa.gov/data-access-and-tools/) · [FIRMS](https://firms.modaps.eosdis.nasa.gov/api/area) |
| NOAA HMS | July 26, 2024 smoke archive returned a ZIP with shapefile and its three sidecar files. | Load geometries, check schema and coverage by state and era, and retain product generation/availability for historical replay. [NOAA smoke archive](https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Smoke_Polygons/Shapefile/2024/07/) |
| LANDFIRE | Catalog and documented LFPS health endpoint returned 200. | Retrieve versioned CONUS, Alaska and Hawaii fuels mosaics and validate class proportions, NoData, release dates and historical vintages. Small LFPS jobs require an email. [LANDFIRE downloads](https://landfire.gov/data) |
| NOAA GFS | November 13 00Z 168-hour GRIB index returned 200. | Retrieve a few variables with byte-range requests, verify archived issuance coverage and map weather to the grid. Keep weather's native effective resolution visible. [NOAA GFS](https://www.ncei.noaa.gov/products/weather-climate-models/global-forecast) |
| Incident and prescribed-burn records | NIFC WFIGS querying returned one polygon record with the documented incident-name field. | Verify named wildfire and prescribed-fire samples, reporting and perimeter timestamps, data coverage by region, and an independent aircraft perimeter. Include local treatment records where available. [NIFC WFIGS](https://data-nifc.opendata.arcgis.com/pages/d6ef1367fadc4405b5f09c98e52ed972) · [Aircraft progression archive](https://research.fs.usda.gov/treesearch/81275) |

## Storage and website candidate

Use a batch Python/geospatial job for collection and transformations. Keep original raster and weather files in object storage or on disk, and write Parquet partitions by source, region and period. Store indexed cell geometries, calendar summaries, forecast tile metadata and incident metadata in PostgreSQL/PostGIS. Roll up cells for national zoom and use vector tiles for the map. A region/date query returns calendar summaries and coverage. Clicking a cell returns the forecast period, recent observations, provenance and links to available Landsat imagery, smoke and incident records. Prevention uses different fields to show local treatment and exposure information. The browser reads these prepared products. [PostGIS vector tile output](https://postgis.net/docs/ST_AsMVT.html)

## Proof before website construction

Collect one small valid payload for each source lane and join them into cell-day facts, a regional calendar response, and a cell-week training table. Check idempotency, timezone boundaries, distinct valid-zero and unknown coverage, availability at issue time, and data from CONUS, Alaska and Hawaii. Run national overlap and forecast benchmarks and measure data volume and query speed. Carry all planned website capabilities into structuring when those results identify viable sources and models.

## Live probe receipts

Executed read-only requests from the workspace on November 14, 2026. Counts refer to sample responses and are not national coverage measurements.

```text
{"source": "MODIS rolling CSV", "http": 200, "columns": ["latitude", "longitude", "brightness", "scan", "track", "acq_date", "acq_time", "satellite", "confidence", "version", "bright_t31", "frp", "daynight"], "sample_date": "2026-11-13"}
{"source": "NOAA-20 VIIRS rolling CSV", "http": 200, "columns": ["latitude", "longitude", "bright_ti4", "scan", "track", "acq_date", "acq_time", "satellite", "confidence", "version", "bright_ti5", "frp", "daynight"], "sample_date": "2026-11-13"}
{"source": "NOAA-21 VIIRS rolling CSV", "http": 200, "columns": ["latitude", "longitude", "bright_ti4", "scan", "track", "acq_date", "acq_time", "satellite", "confidence", "version", "bright_ti5", "frp", "daynight"], "sample_date": "2026-11-13"}
{"source": "Landsat HLS catalog", "http": 200, "hits": "9", "granule": "HLS.L30.T10SEJ.2024208T185105.v2.0"}
{"source": "Sentinel HLS catalog", "http": 200, "hits": "6", "granule": "HLS.S30.T10TEK.2024207T185921.v2.0"}
{"source": "VIIRS fire-mask catalog", "http": 200, "hits": "10", "granule": "VJ114IMG.A2024207.1018.002.2024207172002"}
{"source": "MODIS fire-mask catalog", "http": 200, "hits": "0", "granule": null}
{"source": "NOAA HMS archived smoke", "http": 200, "files": ["hms_smoke20240726.shp", "hms_smoke20240726.shx", "hms_smoke20240726.dbf", "hms_smoke20240726.prj"]}
{"source": "LANDFIRE catalog", "http": 200, "type": "text/html; charset=utf-8"}
{"source": "GFS 7-day forecast index", "http": 200, "index_entries_sample": 153}
{"source": "NIFC sample query", "error": "{'code': 400, 'message': 'Cannot perform query. Invalid query parameters.', 'details': [\"'outFields' parameter is invalid\"]}"}

{"source": "FIRMS Landsat rolling CSV", "error": "HTTP Error 404: Not Found"}
{"source": "MODIS tile fire-mask catalog", "http": 200, "hits": "6", "granule": "MYD14A1.A2024201.h08v04.061.2024211093759"}
{"source": "NIFC Park wildfire record", "http": 200, "features": 1}
{"source": "LANDFIRE LFPS service", "error": "HTTP Error 404: Not Found"}

200 {"message":"The service is up","success":true}
https://firms.modaps.eosdis.nasa.gov/data/active_fire/landsat/csv/LANDSAT_US_24h.csv HTTP Error 404: Not Found
200 []
```


## Revised spatial design

The nationwide prototype should preserve native spatial detail and publish the finest defensible forecast. The initial 5, 10 and 20 km proposal is superseded by the resolution tests below.

- Record each sensor's nominal resolution, source product, observation time and pixel footprint where available. FIRMS scan and track fields describe the size of a detection pixel. Use provider geometry or the product geolocation where possible. A detection indicates an active heat signal somewhere in its footprint. [MODIS active fire guide](https://www.earthdata.nasa.gov/sites/default/files/imported/MODIS_C6_Fire_User_Guide_B.pdf) · [VIIRS product attributes](https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html)
- Test a 1 km equal-area reference grid for historical comparisons. Match observations in time and use actual coverage and footprints when available. Aggregate if comparison at 1 km breaks down in held-out tests. Keep recent native detections accessible regardless of the scale selected for the calendar.
- Compare 375 m and 1 km cell grids for the seven-day NOAA-20 target. Define a reproducible binary label using the reported VIIRS detection centroid and use observation masks to determine whether an absence is evaluable. Store the footprint alongside the centroid. The map's forecast is the chance a cell receives at least one qualifying detection in the specified seven days. Check geographic and seasonal reliability, detection ranking, and positional sensitivity before choosing a published scale. Coarser weather predictors describe regional conditions. Fine inputs can justify local variation when validated.
- Render the forecast on a continuous color scale. Draw solid red over an observed active-fire footprint where the selected evidence supports it. A 30 m Landsat OLI detection can refine the marked area. A post-fire burn scar gets a distinct style. Include evidence source and observation date on click, and retire the active styling when the observation ages out. A single Landsat scene may be unavailable or cloud obscured. Preserve the originally issued probability so analysts can replay and score it. [FIRMS Landsat product](https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_Landsat_Firehotspots.html) · [USGS burn-ratio guide](https://www.usgs.gov/landsat-missions/landsat-normalized-burn-ratio)
- Landsat 8/9 has 30 m multispectral bands, 15 m panchromatic imagery and 100 m native thermal bands. FIRMS Landsat 30 m detections come from OLI. Sentinel-2 provides 10 m in select visible and near-infrared bands and 20 m in the shortwave infrared. Those resolutions describe imagery products. [USGS Landsat 8](https://www.usgs.gov/landsat-missions/landsat-8) · [ESA Sentinel-2 instrument](https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-2/Instrument)
- At roughly 9 million square km of land, a 1 km grid means roughly 9 million full-cell equivalents. A 375 m grid means about 64 million. Benchmark tiling, model memory and run time before national publication. Use tiled rasters and partitioned training files for dense probabilities and imagery. Keep PostGIS for spatial indexing, summary queries, tile metadata and vector observations. Lower map zooms can display a labeled summary such as maximum cell probability. Computing the probability of any detection in a region is a different target and requires independent calibration.

Pending proof: harmonization error at 1 km, held-out forecast comparison at 375 m and 1 km, observation and evidence display rules, and benchmarked national generation and serving. Live authenticated feed and raster checks from the original feasibility pass remain open.

