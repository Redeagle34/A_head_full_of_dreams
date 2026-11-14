---
type: notebook
topic: modis-viirs-burning-calendar
status: active
question: "How can comparable MODIS and VIIRS observations support historical analysis, prevention, incident review and a seven-day detection forecast?"
updated: 2026-11-14
freshness: science
---
# MODIS–VIIRS burning calendar

Several public systems cover individual goals. SHIFT provides an example of sensor calibration, GWIS shows historical comparisons, FIRMS sets the response benchmark, and a Bolivia preprint tests the forecast target directly. None of the inspected results establishes performance for the team's region. [[modis-viirs-burning-calendar-f004]] [[modis-viirs-burning-calendar-f006]] [[modis-viirs-burning-calendar-f007]] [[modis-viirs-burning-calendar-f011]]

The forecast target is satellite-observed burning over the following seven days. A probability of at least one qualifying vegetation-fire detection per grid cell is a candidate definition. Confirm the cell size, reference platform and observation-coverage rules with the data. [[modis-viirs-burning-calendar-f001]] [[modis-viirs-burning-calendar-f002]] [[modis-viirs-burning-calendar-f011]]

- [Problem tree](modis-viirs-burning-calendar-problem.html)
- [[modis-viirs-burning-calendar-brief]]
- [[modis-viirs-burning-calendar-state]]

| Existing option | What it offers | Limit | Cheapest test |
| --- | --- | --- | --- |
| SHIFT and published sensor comparison | Common grid and overlap calibration, with an Apache-2.0 reference implementation | A smooth transition does not verify historical estimates. Published radiative-power factors are specific to the products and aggregation. SHIFT reported overlap between uncertainty calibration and verification years. [[modis-viirs-burning-calendar-f003]] [[modis-viirs-burning-calendar-f004]] [[modis-viirs-burning-calendar-f005]] | Compare raw counts, shared-grid active cell-days, and a regional seasonal multiplier. Reserve whole years before fitting. |
| GWIS | Historical comparisons and downloadable charts | Country and administrative scales, with a burned-area focus. [[modis-viirs-burning-calendar-f006]] | Recreate the current-versus-typical comparison with week or month totals and an observation-coverage indicator. |
| FIRMS, CalVTP, NIROPS | Recent observations plus independent incident, burn and aircraft context in selected U.S. regions | Incomplete spatial and temporal coverage. Incident perimeters and satellite observations have different timestamps. [[modis-viirs-burning-calendar-f007]] [[modis-viirs-burning-calendar-f008]] [[modis-viirs-burning-calendar-f009]] | Review a documented incident, a documented completed prescribed burn, and an unmatched detection. |
| Fireshed Registry | Practical inputs for prevention planning including past treatments and community exposure | Landscape planning scale. Local suitability needs local inputs. [[modis-viirs-burning-calendar-f010]] | Check whether selected zones include plausible treatment areas for expert review and display the supporting layers. |
| Bolivia weekly benchmark and ECMWF Probability of Fire | Published seasonal and persistence baselines, more complex models, and tests against satellite detections | Bolivia study is a preprint, uses retired S-NPP and has no demonstrated transfer here. ECMWF uses a daily target. [[modis-viirs-burning-calendar-f001]] [[modis-viirs-burning-calendar-f011]] [[modis-viirs-burning-calendar-f012]] | Use a continuing VIIRS stream as a candidate live target. Compare seasonal frequency and prior-week activity in a held-out season before evaluating added inputs. |

Pending: reference location, local data access and reuse checks, live stream quality, regional forecast skill, exact calendar measure, and a coherent prototype design covering all three objectives.


## U.S. release and additional evidence

First release targets the United States. Mexico and other regions are future releases. Keep the MODIS–VIIRS calendar portable. Maintain explicit source coverage, spatial support, observation time, and availability time for each optional data layer.

| Option, in recommended order | Benefit | Risk | Cheapest test |
| --- | --- | --- | --- |
| Proposal 1. MODIS and VIIRS calendar plus Landsat, vegetation and smoke layers | Serves historical analysis, next-week forecasting, incident review and prevention through the same region and dates. [[modis-viirs-burning-calendar-f004]] [[modis-viirs-burning-calendar-f011]] [[modis-viirs-burning-calendar-f013]] [[modis-viirs-burning-calendar-f016]] [[modis-viirs-burning-calendar-f018]] | Each layer measures something different and has its own coverage and lag. | Replay July 2024 around the Park Fire. Compare the two sensor series. Add a documented completed burn for the context and prevention workflows. |
| Proposal 2. Test vegetation and smoke as forecast predictors | Measures the improvement beyond seasonal frequency and last week's detections. [[modis-viirs-burning-calendar-f011]] [[modis-viirs-burning-calendar-f017]] [[modis-viirs-burning-calendar-f018]] | Future imagery, product revisions and data published after the issue time inflate retrospective scores if used as input. | Compare a baseline with vegetation added and then with lagged smoke added on the same held-out weeks. |
| Proposal 3. Merge Landsat detections into the historical count | Uses fine-grained active-fire observations when present. [[modis-viirs-burning-calendar-f014]] | Acquisition cadence and footprint differ from MODIS and VIIRS. This introduces another observing-system change into the count. | Compare Landsat detections to matched overpasses as an evidence layer and quantify missing local coverage. |

Candidate incident replay within the national prototype: Park Fire in Northern California, July 2024. USGS confirms Landsat imagery and CAL FIRE provides incident reports. Confirm archived smoke polygons, a clear pre-fire scene, downloadable detections, actual aircraft perimeter coverage and a documented prescribed burn before committing the demo. [[modis-viirs-burning-calendar-f013]] [[modis-viirs-burning-calendar-f020]]


## National scope and technical investigation

The team confirmed that the prototype covers the entire United States. Northern California is an access-check and incident example. Mexico and other regions are future versions. See [data and model feasibility](us-data-model-feasibility.md) for live endpoint probes, the common grid, model comparisons and the website data path.

## Three-sensor MVP

The team selected MODIS, VIIRS, and Landsat for the first nationwide prototype. See [MVP scope and proposed validation](three-sensor-mvp.md). The feasibility notes retain the wider roadmap.
