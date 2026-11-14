# Three-sensor technical proof

Run from the repository root in PowerShell.

```powershell
python -m pip install --target proofs/three-sensor/.data/libs -r proofs/three-sensor/requirements.txt
$env:PYTHONPATH = (Resolve-Path 'proofs/three-sensor/.data/libs').Path
python proofs/three-sensor/prove.py
npm install --prefix proofs/three-sensor/.data --no-audit --no-fund @electric-sql/pglite@0.5.16 @electric-sql/pglite-postgis@0.2.16
node proofs/three-sensor/postgis.mjs
```

The Python command downloads missing public NASA FIRMS footprint bundles and the Census state mask. It reuses files in `.data` on subsequent runs. The published feeds are rolling. Back up the saved bundles before using `--refresh` to sample a newer interval. The PostGIS script uses PGlite. Pass a fresh local directory as its optional argument to test persistence and reopening. The current MVP covers the contiguous 48 states. The public FIRMS bundle also supplies Hawaii, which the proof filters out. The first-run receipts document the earlier batch, which included Alaska.

The output directory contains native detections (CSV and GeoJSON), per-footprint 375 m grid overlap, candidate cross-sensor pairs, observed daily activity, and JSON diagnostics. Each candidate pair is a spatial overlap within a test time window. The daily activity file contains detections only. Missing sensor-days have unknown observation coverage. The candidate case is selected from overlapping detections, and therefore is unsuitable as an unbiased validation sample.

The nationwide sample used a 1:20 million Census state boundary mask on the reported centroid. Fine border and coastal attribution needs more detailed boundaries. The polygon from FIRMS is an estimated sensor footprint. The grid allocation fractions measure overlap, and each parent observation retains a single identifier regardless of how many cells it intersects.

Landsat comes from the public CONUS/Hawaii rolling feed. Full historical backfill, cloud and swath coverage denominators, native-server benchmarks, production version reconciliation, and browser integration remain open.

- [FIRMS footprint service](https://firms.modaps.eosdis.nasa.gov/api/kml_fire_footprints/)
- [U.S. Census cartographic boundaries](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html)
- [PGlite PostGIS extension](https://pglite.dev/extensions/#postgis)

## Follow-up proofs

Run these commands with the pinned requirements installed and `PYTHONPATH` set as above. Use the saved November 2026 rolling bundles for the fixed Georgia Landsat replay.

```powershell
python proofs/three-sensor/landsat_coverage.py
python proofs/three-sensor/historical_gibs.py
python proofs/three-sensor/historical_coverage.py
node proofs/three-sensor/postgis.mjs proofs/three-sensor/.data/postgis-mainland
```

- **Landsat coverage** reads USGS Landsat Collection 2 QA at three mainland locations and across the full MODIS footprint in Georgia. The positive live Georgia reference compares scene acquisition times with the original MODIS detection. The test distinguishes available clear imagery from no clear scene within a window. It estimates area fractions for clear, cloudy, snow/water, and unobserved parts of the Georgia footprint. One Oregon scene was cloudy at the sampled point. Cloud, shadow, fill, snow, and water decoding also has a fixture check. [USGS QA bits](https://www.usgs.gov/landsat-missions/landsat-collection-2-quality-assessment-bands) · [Planetary Computer access](https://planetarycomputer.microsoft.com/docs/)
- **Historical replay** downloads geographic NASA GIBS points for 12 site-days in winter, summer and autumn. It uses the original coordinate attributes, retains product versions, and checks how a simple detection-count multiplier fitted in one case transfers to other cases. Some browse records identify themselves as near-real-time. Full harmonization requires coverage masks, archive version checks, and independent evaluation at the proposed 375 m scale. [NASA GIBS vector examples](https://github.com/nasa-gibs/gibs-web-examples)
- **Persistent PostGIS** reopens a disk-backed PGlite database after two loads. Docker returned HTTP 500, so the run measures portability and persistence in the embedded engine. Native PostgreSQL server and national tile performance remain open.

The mainland JSON receipts record current results. Earlier receipts document superseded geographic scopes. Cached detailed outputs and the artifact database live under `.data`.

### MODIS and VIIRS coverage join

`historical_coverage.py` joins GIBS detections on a common 375 m grid using the reported centroids and UTC dates. It adds candidate granule counts from NASA CMR using the region and date, and exports `historical-cell-days.csv` with native counts. The 329 shared cells are daily co-detections. They do not measure simultaneous agreement. Cells without a detection carry an unknown-coverage status because a catalog footprint is insufficient to establish usable pixel coverage.

CMR found both Aqua MODIS MYD14 and NOAA-20 VIIRS VJ114IMG assets. Actual raster reads returned Earthdata HTTP 401. For the next proof, make Earthdata Login credentials available through an authorized environment or supply the files locally. The probe can try a user-provided `EARTHDATA_TOKEN`. The starter files used for the byte probes are named in `mainland-coverage-join-results.json`. Pixel-level cloud masks and geolocation still have to be decoded and aligned before validating agreement on held-out overpasses.
