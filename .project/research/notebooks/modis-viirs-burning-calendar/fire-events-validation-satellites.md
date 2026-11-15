# Fire events, cross-checks and the satellite view

Written 2026-11-14 with the branch `fire-events-satellite-globe`. Numbers are from runs on
that day; the scripts print them again when rerun.

## 1. How others check active-fire results, and what we took from it

| Source | What it does | Used here |
|---|---|---|
| Schroeder et al. 2008, *Remote Sens. Environ.* (MODIS and GOES against 30 m ASTER and Landsat) | Counts fires in a sharp image taken at the same moment, then asks how many the coarse product saw. About three quarters of the fires sampled were missed by MODIS; most false alarms sat on recent burns | Same question, different reference: we compare against fires reported by agencies (`pipeline/missed_fires.py`). A 30 m same-moment check is not built |
| Giglio, Schroeder & Justice 2016 (MODIS Collection 6 validation, more than 2,500 ASTER scenes) | Global daytime false-alarm rate 1.2% | Reason to treat a detection as real and to concentrate on what is missed |
| Sofiev & Kouznetsov 2026, *Geosci. Model Dev.* 19:10123 | Detection limit by pixel size; applies each sensor's limit to the other's fires and compares | Already the harmonization method; the cloud term was piloted in `proofs/cloud-pilot/` |
| Balch et al. 2020, *Remote Sens.* 12:3498 (FIRED) | Groups burned pixels that touch in space and follow in time into fire events; duration and spread follow from that | `pipeline/fire_events.py` applies the same rule to active-fire detections: neighbouring 1 km cells, at most 5 days apart |
| MODIS burned-area product MCD64A1 (Giglio et al. 2018) | Burned area from the change in the surface, independent of hotspots | Second opinion on each fire's area (`pipeline/event_enrich.py`) |
| USGS burn-severity practice (dNBR from Landsat before and after; 0.27 and up is moderate or high) | Severity from two sharp images | Third opinion, on request per fire (`/api/events/{id}/sharp`) |

## 2. Measured results

**Fire events.** 11,320,264 detections became 2,035,833 fires. 963 are 100 km² or larger;
they hold 6% of all burned cells. The two largest are the 2020 August Complex area
(4,947 km² from hotspots; reported about 4,180 km²) and the 2021 Dixie Fire area
(4,742 km²; reported about 3,900 km²). The hotspot area overstates: cells are rounded up
and neighbouring fires merge.

**Area cross-check.** For the 963 largest fires the hotspot area and the MCD64A1 burned
area correlate at 0.94. Totals: 284,286 km² from hotspots against 223,748 km² mapped
burned, so hotspots read 27% higher. Under 1% of these fires have no mapped burn.

**Missed fires** (reported wildfires 2022–2025, the years the ignition model never saw;
"missed by satellites" = no detection within 2 km from 1 day before to 3 days after):

| Final size | Fires | Missed by satellites | Not expected by the model (score under 0.5) | Both |
|---|---|---|---|---|
| under 1 acre | 39,025 | 98% | 22% | 21% |
| 1 to 100 | 18,190 | 84% | 31% | 27% |
| 100 to 1,000 | 3,525 | 46% | 27% | 13% |
| 1,000 to 10,000 | 1,140 | 39% | 21% | 8% |
| over 10,000 | 264 | 32% | 10% | 5% |

The 2 km rule is strict for large fires: the reported point is where the fire started,
and the hotspots can be elsewhere in the perimeter. A perimeter-based match is the next step.

**One fire end to end** (Park Fire, California, 2024): 23 days from first to last
detection; 1,830 km² from hotspots; 1,684 km² in MCD64A1; 1,296 km² of moderate or high
severity in Landsat inside the picture box; burned grassland 28%, woody savanna 25%,
savanna 23%, evergreen needleleaf forest 23%; matched to the agency report of 429,603
acres (1,739 km²), seen by satellite, model score 0.82.

## 3. Where the satellites are

| Need | Source | Key |
|---|---|---|
| Orbit of each satellite | CelesTrak GP data, `celestrak.org/NORAD/elements/gp.php?CATNR=<number>&FORMAT=TLE` | none |
| Position and overpass times from an orbit | SGP4 model, `satellite.js` in the browser | none |
| 3D models | NASA 3D Resources, `github.com/nasa/NASA-3D-Resources` (Aqua, Terra, Suomi NPP, Landsat 8) | none |
| Picture of the ground under a satellite | NASA Worldview Snapshots, `wvs.earthdata.nasa.gov/api/v1/snapshot` | none |

Catalogue numbers: Terra 25994, Aqua 27424, Suomi NPP 37849, NOAA-20 43013, NOAA-21 54234,
Landsat 8 39084. Strip widths: MODIS 2,330 km, VIIRS 3,060 km, Landsat 185 km.

Checked on the page: Suomi NPP and NOAA-20 pass Kansas around 02:20 to 02:45 local time,
as their 01:30 solar-time orbit predicts. Terra and Aqua no longer keep their design
times (10:30 and 13:30): both orbits are drifting, which the live solar time on the card shows.

Limits: there is no live camera feed from these satellites. The card shows the most recent
daytime picture each one published of the ground now under it (the same day or the day
before for MODIS and VIIRS; within about three weeks for Landsat, else a wider NOAA-20
picture, labelled as such). N2YO and similar services offer ready-made pass predictions
but need a key; computing passes from the public orbit data gives the same answer.

## 4. Not done

- Nothing is deployed to Google Cloud: the signed-in account can use Earth Engine on the
  project but may not list or enable services, create keys or see billing.
- No same-moment 30 m validation (the Schroeder method).
- Reported-fire matching uses the starting point, not the perimeter.
- Vegetation is split only where MCD64A1 maps a burn; small and cropland fires have none.
