# Nationwide three-sensor MVP

## Proposed scope

Cover the contiguous 48 United States with a globe-style map. Ingest only MODIS, VIIRS, and Landsat active-fire data in scheduled batches. Landsat supplies 30 m satellite corroboration where observations coincide. Preserve observed records for all three sources and retain the footprint and quality of each observation. The prototype focuses on incident review and scientific access. The previously discussed forecast, fuel-treatment workflows, smoke and vegetation sources, and expansion beyond the U.S. are later work at the team's direction.

## User workflows

- Firefighter: enter a location or drop a pin, choose a radius and date window, and see nearby detections. Inspect the source, observation time, and corroboration. Distinguish an observed thermal anomaly from a corroborated detection. If there is a solid-red corroboration style, draw it at the footprint supported by the evidence and include a label and timestamp.
- Scientist: select the same area and dates and download native observations as CSV or GeoJSON, grid-level evidence as a separate CSV, and a report covering sensor overlap, coverage, uncertainty, and source versions. Recommend a minimal historical calendar plot in the report to retain the link to the NASA challenge. Full interactive historical calendar scope awaits team confirmation.

## Sensor agreement at 375 m

Use a fixed grid of 375 m cells as a reference for display and comparison. Preserve each MODIS and VIIRS observation once with its native footprint. Where a MODIS footprint intersects a reference cell, record the parent observation ID and overlap fraction. Every intersected cell can show the same coarse evidence flag. The flag means the cell intersects a footprint that contains a detected heat source somewhere. It must never count as a separate detection, replicate fire radiative power, or count as confirmed burning in that cell. Derive native counts from distinct source observation IDs. Make actual footprint geometry the default where it is available, and indicate estimated footprints when required.

Count agreement only for spatially and temporally comparable observations. Use timestamp and footprint overlap in the first test, then check the effect of stricter time and overlap criteria and unequal cloud or observation coverage. Report matched detections, unmatched detections in evaluable coverage, and unavailable comparison coverage separately. Landsat is a higher-resolution satellite cross-check rather than an independent ground survey. Report its time lag and coverage, and leave non-matches unresolved when an on-time usable scene is unavailable. Shared-grid alignment and demonstrated record harmonization are distinct milestones.

- [FIRMS footprint API](https://firms.modaps.eosdis.nasa.gov/api/kml_fire_footprints/)
- [MODIS product description and footprint fields](https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_MODIS_Firehotspots.html)
- [VIIRS product description and footprint fields](https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html)
- [Landsat 30 m active fire product](https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_Landsat_Firehotspots.html)

## Storage and first proof

Store versioned source files by product and date in object storage or on disk. Use a batch job to validate and deduplicate inputs and upsert them to time-partitioned PostGIS tables with spatial indexes. Use sparse derived grid evidence and retain source observation IDs. Store native Landsat active-fire detections as vectors and any optional imagery as raster files. The website and exports query the prepared database. Precompute or cache map tiles where nationwide payload and query measurements warrant it.

Check a Landsat data pull with the documented access path, then run a matched-overpass proof that joins a MODIS footprint, VIIRS evidence, and Landsat corroboration and exports a scientist report for the same selection. Test repeated ingestion, distinct native detection counts under grid overlap, missing coverage, and map/query behavior across the contiguous U.S. Run the full national backfill and coverage evaluation as part of the MVP. The batch cadence, historical range, weather-free basemap choice, report format, and matching thresholds remain to be specified. No application or ingestion job has been built in this discussion.


## First technical proof

The proof scripts and source receipts are in [proofs/three-sensor](../../../../proofs/three-sensor/README.md). The public 7-day KMZ endpoint provided estimated footprint polygons for all three sensor families without credentials. Alaska has MODIS and VIIRS bundles. Its Landsat footprint bundle is unavailable from this endpoint.

The November 7–14, 2026 UTC snapshot yielded 47,741 distinct detections inside a generalized U.S. state mask. A 20 km Georgia query produced 390 native records and 532 grid relationships, with fractions summing to one per observation. Nearby GeoJSON and scientist CSV IDs agreed. PostGIS returned the same selection and retained 47,741 rows after replaying the input batch.

None of the MODIS/VIIRS or MODIS/Landsat footprint pairs were within 30 minutes. At 90 minutes, the counts were 224 and 455, respectively. At 180 minutes they were 1,962 and 515. At that wider tolerance, two distinct MODIS observations each had candidates from both other families. The selected Georgia query is a positive search example and the estimate is sensitive to timing. Treat unmatched coverage as unknown until swath and cloud masks are used. The counts do not measure wildfire events or validate agreement.

Still open: verify the Landsat access path for Alaska, implement swath/cloud denominators and test validated matching, run a multi-season archive backfill and historical harmonization, benchmark a persistent native PostGIS deployment, and test the globe and report download in a browser.

## Follow-up proofs

The team excluded Alaska from the MVP. The scoped batch retained 47,736 records and PostGIS returned the same 390 Georgia IDs after reopening the disk-backed PGlite database. Hawaii passed a real nearby query. Docker's native service returned HTTP 500.

The Landsat scene check read six clear QA pixels in total at the Park Fire, Lahaina, and the Georgia selection. In Georgia, the two adjacent Landsat scenes were approximately 65 minutes after MODIS, outside the 30-minute window but within 90 minutes. The query was for a point and established scene evidence rather than full footprint coverage.

NASA GIBS historical replay decoded 30 tiles for 12 site-days in 2022–2024, covering three seasons across California, Hawaii, and Georgia. It yielded 693 Aqua MODIS and 4,373 NOAA-20 VIIRS observations. A multiplier of 5.73 fit on the California summer case reduced raw-count errors in the other California and Hawaii samples while still undershooting both. It could not account for the Georgia sample, which had six VIIRS detections and zero MODIS detections. Coverage in GIBS empty rows is unresolved.

See the [proof instructions and receipts](../../../../proofs/three-sensor/README.md). Still open: observed-clear coverage for MODIS and VIIRS, area-based Landsat QA and time matching, independent coverage-aware harmonization at 375 m, the full archive backfill, native-server load tests, and browser integration.

## Contiguous U.S. follow-up

The MVP now excludes Hawaii as well as Alaska. The seven-day batch retained 47,178 distinct records after restart and duplicate replay. California and Georgia nearby queries passed, and the Georgia export still matched all 390 IDs. The historical proof replaced the Hawaii case with Oregon. The 375 m common grid has 4,003 historical cell-days with at least one detection and 329 with detections from both sensors. Joined CMR catalog granules establish regional overpass candidates. Raster byte probes for both sensor masks returned HTTP 401. Preserve unknown coverage until pixels can be decoded.

Landsat optical QA was clear across 100% of the sampled Georgia MODIS footprint in two scenes about 65 minutes later. One Oregon scene had cloud and cirrus flags at the sampled point. The 90% clear-area threshold used in this proof is provisional. Remaining tests include held-out mask-aware agreement, full archive backfill, native-server performance, and browser workflows.
