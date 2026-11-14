# Expected damage / severity "if it burns" — research notes (Space Apps 2026)

Scope: component (3) of the system — expected damage/severity given that a fire happens at a location on a day.
Components (1) P(ignition) and (2) P(large | ignition) are built elsewhere and are not covered here.
Status tags: **VERIFIED** = queried or read on 2026-11-14 (evidence cached under `data/raw/damage_research/`, scripts under `explore/damage/`); **UNVERIFIED** = from memory / not checked.

---

## 1. Conclusion (read this first)

1. **Use the USFS Wildfire Risk to Communities raster stack in Earth Engine (`USDA/WRC/v0`) for the fire-behaviour intensity output only** (see item 6: it did not predict severity or structure loss in today's tests). VERIFIED: it is in the official GEE catalog with bands `BP, CFL, CRPS, Exposure, FLEP4, FLEP8, RPS, WHP` for CONUS/AK/HI at 30 m, licence CC-BY-4.0, citation Scott et al. 2024 (RDS-2020-0016-2). This already contains (b) conditional fire intensity (CFL = conditional flame length, FLEP4/FLEP8 = probability flame length > 4 ft / > 8 ft if a fire occurs) and (c) a consequence-to-homes layer (CRPS, 0–100) produced by FSim/FlamMap. No large download needed.
2. **Ecological severity** ((a)): train/validate against **MTBS annual burn-severity mosaics** (`USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1`, VERIFIED, CONUS images 1984–2026 listed). Start from a pre-fire lifeform × Fire Regime Group prior (item 6), then add pre-fire NDVI/NDMI, topography and day-of fire weather (gridMET ERC/BI/wind), as in Parks et al. 2018 — that step was not tested today. LANDFIRE fuels (FBFM40, CC, CH, CBH, CBD) are VERIFIED in the GEE community catalog (`projects/sat-io/open-datasets/landfire/FUEL/*`, LANDFIRE 2.4.0) but are a 2023 vintage, so they describe post-fire fuels for older fires.
3. **People/assets** ((c)): built-up surface and population around the point (GHSL `JRC/GHSL/P2023A/GHS_BUILT_S` + `GHS_POP`, VERIFIED, global → gives the global fallback), WUI class (SILVIS WUI 1990–2020 v4, VERIFIED as `projects/sat-io/open-datasets/CONUS_WUI`, CC0), WRC CRPS/Exposure. **Validate with ICS-209-PLUS 1999–2020** (VERIFIED: figshare DOI 10.6084/m9.figshare.19858927.v3, **CC BY 4.0**, 48.7 MB wildfire zip downloaded; 34,622 wildfire incidents, `STR_DESTROYED_TOTAL > 0` for 5,412). **WFIGS Incident Locations has NO structures-destroyed fields** (VERIFIED, 97 fields listed).
4. **Good fire vs bad fire** ((d)): LANDFIRE Fire Regime Group (FRG), Mean Fire Return Interval (MFRI) and Vegetation Departure (VDep) (all VERIFIED in GEE). Down-weight ecological damage where FRG = I (≤35 yr, low/mixed severity) and VDep is low and predicted severity is low–moderate ("restorative" fire); up-weight where FRG I/III is burning at high severity (uncharacteristic) or VDep is high. Stand-replacing fire in FRG II/IV/V is "in regime" ecologically but still dangerous to people.
5. **Recommended output** for each (location, day):
   `ExpectedImpact = P(ign) × P(large|ign) × Consequence`, with `Consequence = w_people·C_people + w_eco·C_eco`, both on 0–1, and C_eco already regime-adjusted. Report the three factors separately as well (a single number hides why a cell is red).
6. **Prototype validation run today** (hackathon-grade, details §4.5) changed the design in two ways:
   - **WRC flame-length layers are NOT a proxy for ecological severity.** On 16,367 MTBS burned pixels (419 fires, 2016–2022) CFL/FLEP4/FLEP8 have AUC 0.32/0.32/0.39 for "high severity" — i.e. inversely related; the likely reasons (not isolated today) are that modelled flame length is high in grass/shrub, where MTBS high severity is rare, and that the fuel layers post-date many of the fires (herb 0.2%, shrub 1.6%, tree 10.2% high). Pre-fire lifeform alone (tree vs not, LANDFIRE EVC v1.4.0) gives AUC 0.74. Keep intensity (b) and ecological severity (a) as separate outputs.
   - **Exposure, not hazard, explains structure loss.** On 20,853 ICS-209-PLUS incidents (CONUS, 2005–2020, ≥100 ac; 2,442 with structures destroyed) fire size alone gives AUC 0.71 for "any structure destroyed"; adding built-up surface within 5 km (GHSL) gives 0.78 (5-fold CV); adding WRC CFL and CRPS adds nothing (0.78). Built-up alone: 0.58. So C_people = exposure, and P(large) carries most of the signal.
7. **Licence red flag:** `pyretechnics` switched on 2026-10-05 from EPL-2.0 (OSI) to a custom non-OSI "community/commercial" dual licence (VERIFIED from the repo commit history). If you use it at all, pin tag `2026.8.10` (VERIFIED EPL-2.0 licence file at that tag). Simpler: rely on WRC CFL/FLEP (already FSim/FlamMap output) or `firelab/behave` (VERIFIED: US-Government public-domain notice — not an OSI licence per se, but public domain; cite it).

---

## 2. Source table

Legend: Res = spatial resolution; Lat = latency; Verdict U = use, M = maybe, S = skip.

| # | Dataset | What it gives (damage axis) | Res / coverage / years | Access + auth | Licence / cite | Verification | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | **MTBS annual burn severity mosaics** `USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1` | (a) thematic severity: 0 bg, 1 unburned–low, 2 low, 3 moderate, 4 high, 5 increased greenness, 6 non-mapping | 30 m; CONUS/AK/HI/PR; images `mtbs_CONUS_1984`…`mtbs_CONUS_2026` (43 CONUS images listed; GEE catalog page states 1984–2024 — treat 2025/26 as partial); fires ≥1000 ac W / ≥500 ac E; latency ~1–2 yr | GEE, no extra auth | US-Gov funded, "can be used without additional permissions or fees"; cite "USDA Forest Service/US Geological Survey. Monitoring Trends in Burn Severity Thematic Burn Severity" | VERIFIED (asset listing, catalog page, Paradise CA 2018 pixel = 3) | **U** (label) |
| 2 | **MTBS burned-area boundaries** `USFS/GTAC/MTBS/burned_area_boundaries/v1` | per-fire perimeters + dNBR thresholds (`Low_T, Mod_T, High_T`), `Ig_Date`, `irwinID` | 30,730 features | GEE | same as 1 | VERIFIED (props listed) | **U** (join key to fires/IRWIN) |
| 3 | **Wildfire Risk to Communities** `USDA/WRC/v0` | BP (annual burn prob.), **CFL** (ft), **FLEP4/FLEP8**, **CRPS** (0–100, consequence to a hypothetical home if it burns), Exposure (0–1 direct/indirect), RPS = BP×CRPS, WHP | 30 m; CONUS, AK, HI; catalog dates 2020–2022 (fuels LANDFIRE 2020 v2.2.0 per RDS page); static | GEE, no extra auth | **CC-BY-4.0**; Scott J.H. et al. 2024, *Wildfire Risk to Communities: Spatial datasets of landscape-wide wildfire risk components for the United States*, 2nd Ed., USFS RDS, doi:10.2737/RDS-2020-0016-2 | VERIFIED (bands + sample values at 4 points; catalog page) | **U** (core) |
| 4 | WRC v2 full archive (RDS-2020-0016-2) | same + extra layers | state zips, some >27 GB (per search result) | fs.usda.gov RDS — **HTTP 403 to scripted requests** | CC-BY-4.0 | PARTIAL (403; info from search snippet) | S (GEE copy is enough) |
| 5 | **LANDFIRE fuels** (community catalog) `projects/sat-io/open-datasets/landfire/FUEL/{FBFM40,FBFM13,CC,CH,CBH,CBD,FVC,FVH,FVT,FCCS,...}` | (b) inputs to Rothermel/crown fire: fuel model, canopy cover %, canopy height (×10 m), CBH (×10 m), CBD (×100 kg m⁻³) | 30 m; images `*_LA_240` (AK), `*_LC_240` (CONUS), `*_LH_240` (HI), `*_LV_240`; LANDFIRE 2.4.0 (LF2023) | GEE community catalog | LANDFIRE = public domain, "no use restrictions"; add a descriptive modifier to derivatives; cite LANDFIRE product + Rollins 2009 | VERIFIED (asset ids; Paradise sample FBFM40=186, CC=35, CH=230, CBH=34, CBD=6). Scale factors UNVERIFIED (standard LANDFIRE convention) | **U** |
| 6 | LANDFIRE official GEE: `LANDFIRE/Fire/FRG/v1_2_0`, `MFRI/v1_2_0`, `VDep/v1_4_0`, `VCC/v1_4_0`, `PLS/PMS/PRS v1_2_0`, `LANDFIRE/Vegetation/{EVT,BPS,EVC,EVH}/v1_4_0` | (d) fire regime: FRG 1–5; MFRI classes 1–22 (1=0–5 yr … 22=>1000 yr); VDep 0–100 (+codes 101–181); PLS/PMS/PRS = % of fires historically low/mixed/replacement severity | 30 m; CONUS/AK/HI; older LANDFIRE vintage (FRG/MFRI v1.2.0 ~2010 date; VDep v1.4.0) | GEE | public domain | VERIFIED (assets, class tables from catalog pages, samples) | **U** |
| 7 | LANDFIRE LFPS API `https://lfps.usgs.gov/arcgis/rest/services/LandfireProductService/GPServer` | any LANDFIRE layer clipped to AOI, multi-band GeoTIFF | 30–9990 m resample | ArcGIS GP async job, **no token required** (params: Layer_List, Area_of_Interest, Output_Projection, Resample_Resolution) | public domain | VERIFIED (service + task params) | M (fallback if GEE copies missing) |
| 8 | **ICS-209-PLUS 1999–2020** figshare 10.6084/m9.figshare.19858927.v3 (St. Denis et al. 2023, Sci Data 10:112) | (c) per-incident `STR_DESTROYED_TOTAL`, `_RES_`, `_COMM_`, `STR_DAMAGED_*`, `STR_THREATENED_MAX`, `FATALITIES`, `INJURIES_TOTAL`, `PEAK_EVACUATIONS`, `PROJECTED_FINAL_IM_COST`, POO lat/lon, `MTBS_FIRE_LIST`, FOD ids, FIRED ids | 34,622 wildfire incidents; points; 1999–2020 (static) | figshare HTTP, no auth; wildfire zip 48.7 MB (source zip 427 MB — not downloaded) | **CC BY 4.0** | VERIFIED (downloaded, field stats in `ics209_fieldstats.json`) | **U** (label for C_people) |
| 9 | ICS-209-PLUS 1999–2014 (figshare 8048252 v14) | older version | — | figshare | CC0 | VERIFIED | S (superseded) |
| 10 | **WFIGS Incident Locations** (NIFC) | 97 fields; damage-related: **none for structures/fatalities**. Has `FireBehaviorGeneral` (Minimal/Moderate/Active/Extreme), `EstimatedCostToDate`, `EstimatedFinalCost`, `PrimaryFuelModel`, `PredominantFuelGroup`, `FireMgmtComplexity`, `IncidentComplexityLevel`, `TotalIncidentPersonnel` | points; 392,576 WF records | ArcGIS REST, no auth | public (NIFC open data) | VERIFIED — fill rates below | M (weak behaviour label; cost) |
| 11 | **FEMA National Risk Index**, tracts layer `services.arcgis.com/XG15cJAlne2vxtgt/.../National_Risk_Index_Census_Tracts/FeatureServer/0` | wildfire component: `WFIR_AFREQ` (annual freq.), `WFIR_EXPB/EXPP/EXPA/EXPT` (exposed building value, population, agriculture, total), `WFIR_HLRB/P/A` (historic loss ratios), `WFIR_EALT` (expected annual loss $), `WFIR_RISKS/RISKR` | census tract; US | ArcGIS REST, no auth (hazards.fema.gov download timed out; fema.gov 403) | US Gov public (licence text not read — UNVERIFIED) | VERIFIED (26 WFIR fields listed, query returned) | M (tract-level $ exposure; coarse) |
| 12 | **SILVIS WUI 1990–2020 v4** `projects/sat-io/open-datasets/CONUS_WUI` | WUICLASS/WUIFLAG 1990–2020, housing density `HUDEN2020`, `POPDEN2020`, `VEG2019PC` | census-block polygons; CONUS | GEE community catalog (FeatureCollection) | CC0 per community catalog; cite Radeloff et al. 2023, doi:10.2737/RDS-2015-0012-4 (SILVIS page: "Version 4 – last updated February 2025") | VERIFIED (asset + properties) | **U** |
| 13 | **GHSL** `JRC/GHSL/P2023A/GHS_BUILT_S`, `GHS_POP` | built-up m² and population, epochs 1975–2030 (12 images) | 100 m; **global** | GEE | JRC open (CC BY 4.0 — UNVERIFIED here) | VERIFIED (assets) | **U** (global fallback) |
| 14 | GPWv4.11 `CIESIN/GPWv411/GPW_Population_Density`; WorldPop `WorldPop/GP/100m/pop` | population | ~1 km / 100 m; global | GEE | CC BY 4.0 (UNVERIFIED) | VERIFIED (assets) | M |
| 15 | Microsoft Building Footprints `projects/sat-io/open-datasets/MSBuildings/US/<State>` (51 tables); Google Open Buildings v3 `GOOGLE/Research/open-buildings/v3/polygons` | building counts in buffer | polygons; US / global South | GEE | MS: **ODbL** (VERIFIED, `LICENSE-DATA`); Google: CC BY 4.0 / ODbL (UNVERIFIED) | VERIFIED | M (heavy; GHSL is cheaper) |
| 16 | USFS Wildfire Hazard Potential 2023 (RDS-2015-0047-4) | WHP index 270 m | CONUS | RDS + `apps.fs.usda.gov` ImageServer — **both 403** to scripted requests | — | PARTIAL (403) | S (WHP band already in `USDA/WRC/v0`) |
| 17 | FSim national burn probability | BP, FLP | CONUS | RDS (403) | — | NOT VERIFIED | S (BP in WRC) |
| 18 | **FIRMS FRP** | per-detection fire radiative power (MW) — intensity proxy | 375 m VIIRS / 1 km MODIS; global; NRT ~3 h | FIRMS API/CSV — **needs free MAP_KEY (email registration)**; the GEE `FIRMS` asset has only `T21, confidence, line_number` — **no FRP band** (VERIFIED) | NASA open data | VERIFIED (GEE bands) | M (post-hoc validation; team already has FIRMS) |
| 19 | RAVG (USFS GTAC) | post-fire basal-area loss, canopy-cover loss, CBI, for large fires on forested NFS lands | 30 m; NFS forest only; ~45 days post-fire | web download, burnseverity.cr.usgs.gov/ravg | US Gov | VERIFIED (page 200, description read) | S (subset of MTBS-like info; not needed) |
| 20 | BAER | soil burn severity for post-fire emergency response | per-incident | web | — | NOT VERIFIED | S |
| 21 | gridMET `IDAHO_EPSCOR/GRIDMET` | day-of weather: `erc, bi, vs, rmin, tmmx, vpd…` | 4 km; CONUS; daily, ~1–2 day latency | GEE | public domain (UNVERIFIED) | VERIFIED (bands) | **U** (already in main pipeline) |
| 22 | `USGS/3DEP/10m` (deprecated → `USGS/3DEP/10m_collection`) | slope/aspect for spread | 10 m CONUS | GEE | public domain | VERIFIED (deprecation warning) | U (or LANDFIRE TOPOGRAPHY/SLPD) |

**WFIGS fill rates** (VERIFIED, `IncidentTypeCategory='WF'`, `data/raw/damage_research/wfigs_fillrates.json`):

| field | all WF (n=392,576) | WF with IncidentSize ≥1000 ac (n=6,468) |
|---|---|---|
| FireBehaviorGeneral | 28,621 (7.3%) | 5,145 (79.5%) |
| EstimatedCostToDate | 21,278 (5.4%) | 6,042 (93.4%) |
| EstimatedFinalCost | 3,225 (0.8%) | 1,422 (22.0%) |
| PrimaryFuelModel | 31,289 (8.0%) | 5,636 (87.1%) |
| PredominantFuelGroup | 39,603 (10.1%) | 618 (9.6%) |
| FireMgmtComplexity | 34,590 (8.8%) | 4,245 (65.6%) |
| IncidentComplexityLevel | 29,051 (7.4%) | 1,496 (23.1%) |
| FinalAcres | 44,634 (11.4%) | 474 (7.3%) |

`FireBehaviorGeneral` value counts (all WF): Minimal 21,611; Moderate 4,229; Active 2,311; Extreme 470.

**ICS-209-PLUS 1999–2020 field stats** (VERIFIED, 34,622 wildfire incidents): `STR_DESTROYED_TOTAL>0` in 5,412 incidents (sum 109,016); `STR_DESTROYED_RES_TOTAL>0` 2,443; `STR_DAMAGED_TOTAL>0` 2,705; `STR_THREATENED_MAX` non-null 13,194; `FATALITIES>0` 223 (sum 543); `MTBS_FIRE_LIST` non-null 9,353; POO lat/lon non-null 34,200. Destroyed by year (sum): 2017 13,288; 2018 24,756; 2019 970; 2020 18,098. Note: structure fields are zero-filled, so "0" can mean "not reported".

---

## 3. Methods that predict severity / damage from pre-fire conditions

### 3.1 Physics: fire behaviour (axis b)
- **Rothermel surface spread** (Rothermel 1972, USDA FS Res. Pap. INT-115 — UNVERIFIED, no DOI) with the 40 Scott & Burgan fuel models (Scott & Burgan 2005, RMRS-GTR-153, doi:10.2737/RMRS-GTR-153 — VERIFIED via Crossref); full explanation in Andrews 2018, RMRS-GTR-371, doi:10.2737/RMRS-GTR-371 (VERIFIED).
  Outputs: rate of spread R, reaction intensity; Byram fireline intensity I = H·w·R; flame length L = 0.0775·I^0.46 (Byram 1959 — UNVERIFIED from memory).
- **Crown fire initiation** (Van Wagner 1977, Can. J. For. Res. 7:23–34, doi:10.1139/x77-004 — VERIFIED): critical surface intensity I₀ = (0.010·CBH·(460+25.9·FMC))^1.5; active crown if R > 3.0/CBD. Linked surface–crown system: Scott & Reinhardt 2001, RMRS-RP-29, doi:10.2737/RMRS-RP-29 (VERIFIED). Inputs map 1:1 to LANDFIRE FBFM40/CBH/CBD.
- **Open implementations**:
  - `firelab/behave` (C++ BehavePlus core) — VERIFIED repo; LICENCE.md = US-Government public-domain notice.
  - `pyregence/pyretechnics` (Python; modules `surface_fire`, `crown_fire`, `fuel_models`, `load_landfire`, `spot_fire` — VERIFIED at tag 2026.8.10). **Licence changed to non-OSI dual licence on 2026-10-05** (VERIFIED) → only tag ≤2026.8.10 (EPL-2.0) is rules-compliant.
  - Pre-computed: WRC CFL/FLEP4/FLEP8 are FSim/FlamMap outputs under 97th-percentile-ish weather (method details in the WRC v2 methods PDF — not read, UNVERIFIED). Using them avoids running a fire model by tomorrow.
- **Hackathon shortcut**: scale the static CFL by a day-of weather ratio, e.g. `CFL_day = CFL × f(ERC_day/ERC_p97)` — an approximation, not physics. A proper version runs Rothermel per day with gridMET wind and fuel moistures.

### 3.2 Statistical/ML models of burn severity (axis a)
- **Parks et al. 2018**, ERL 13:044037, doi:10.1088/1748-9326/aab791 (VERIFIED, read): boosted regression trees per ecoregion; response = high severity (RBR ≥ 298); 16 predictors (NDVI/NDMI/EVI, topography, climate, day-of-burn fire weather BI/ERC/Tmax). **Cross-validated AUC mean 0.72 (0.66–0.81)**; relative influence: live fuel 53.1%, fire weather 22.9%, climate 13.7%, topography 10.3%. Western US forests, 2002–2015.
- **Dillon et al. 2011**, Ecosphere 2:art130, doi:10.1890/ES11-00271.1 (VERIFIED, abstract): Random Forest on MTBS, 1984–2006, NW + SW US; **classification accuracy 68–84%**; topography the most important predictor; predictability lower in big fire years.
- **Birch et al. 2015**, Ecosphere 6, doi:10.1890/ES14-00213.1 (VERIFIED, abstract): daily dNBR, 42 fires in ID/MT; **percent existing vegetation cover** strongest; fine fuel moisture, RH, wind also important; bottom-up factors dominate severity.
- **Parks et al. 2019**, Remote Sensing 11:1735, doi:10.3390/rs11141735 (VERIFIED, abstract): RF maps CBI from spectral indices; 8,075 plots / 263 fires; **cross-validated R² 0.72**; GEE code provided — useful to convert MTBS/RBR into ecologically meaningful CBI.
- **Miller & Thode 2007**, RSE 109:66–80, doi:10.1016/j.rse.2006.12.006 (VERIFIED): RdNBR definition.
- Terminology: **Keeley 2009**, IJWF 18:116–126, doi:10.1071/WF07049 (VERIFIED) — intensity ≠ severity ≠ burn severity; keep the three outputs separate.

### 3.3 FRP ↔ severity
- **Heward et al. 2013**, IJWF 22:910–918, doi:10.1071/WF12087 (VERIFIED, abstract): 16 western US fires; per-pixel MODIS FRP vs severity **not reliable**; but across fires **69% of variation in RdNBR explained by the 90th-percentile MODIS FRP**. → Use FRP only as a fire-level (not pixel-level) severity proxy.
- FRP physics: Wooster et al. 2005, JGR 110, doi:10.1029/2005JD006318 (VERIFIED title). VIIRS 375 m: Schroeder et al. 2014, RSE 143:85–96, doi:10.1016/j.rse.2013.12.008 (VERIFIED title).

### 3.4 Structure loss (axis c)
- **Syphard et al. 2012**, PLoS ONE 7:e33954, doi:10.1371/journal.pone.0033954 (VERIFIED, abstract): >5,500 destroyed/damaged structures in S. California; loss most likely at **low-to-intermediate structure densities**, small isolated clusters, higher in herbaceous fuels; empirical housing-pattern maps beat fuel-based hazard maps.
- **Syphard, Brennan & Keeley 2014**, IJWF 23:1165–1175, doi:10.1071/WF13158 (VERIFIED, abstract): defensible space most effective at 5–20 m; >30 m no extra benefit; landscape factors (low housing density, distance to roads) more important.
- **Knapp et al. 2021**, Fire Ecology 17:25, doi:10.1186/s42408-021-00117-0 (VERIFIED, abstract): Camp Fire (18,804 structures); survival 11.5% (pre-1997 homes) vs 38.5% (1997+); strongest predictors = distance to nearest destroyed structure, # destroyed within 100 m, canopy cover within 100 m (<53% helps).
- **Higuera et al. 2023**, PNAS Nexus 2:pgad005, doi:10.1093/pnasnexus/pgad005 (VERIFIED, abstract): West-wide structure loss +246% (2010–2020 vs 1999–2009); loss rate per area burned +160%; human-ignited fires caused 76% of structure loss and destroyed ~10× more structures per area burned than lightning fires. → Supports multiplying P(ign) (human-driven) with exposure.
- **Radeloff et al. 2018**, PNAS 115:3314–3319, doi:10.1073/pnas.1718850115 (VERIFIED title) — WUI growth.
- Risk framework: **Scott, Thompson & Calkin 2013**, RMRS-GTR-315, doi:10.2737/RMRS-GTR-315 (VERIFIED title) — risk = Σ burn probability × conditional net value change (the basis of RPS = BP × CRPS). **Finney et al. 2011**, SERRA 25:973–1000, doi:10.1007/s00477-011-0462-z (VERIFIED) — FSim.

### 3.5 Fire regime / good vs bad fire (axis d)
- **Steel et al. 2015**, Ecosphere 6, doi:10.1890/ES14-00224.1 (VERIFIED, abstract): in fuel-limited, historically frequent-fire forests (yellow pine, mixed conifer) the proportion of high-severity fire increases with time since last fire / modern FRI → high-severity fire there is *uncharacteristic*; red fir / redwood (climate-limited) show no such relation.
- **Kolden 2019**, Fire 2:30, doi:10.3390/fire2020030 (VERIFIED title) — prescribed / beneficial fire deficit.
- Thode et al. 2011, IJWF 20:223–239, doi:10.1071/WF09060 (VERIFIED title) — severity regime distributions.
- LANDFIRE: Rollins 2009, IJWF 18:235–249, doi:10.1071/WF08088 (VERIFIED title).

---

## 4. Proposed design — "damage if it burns" (feasible by tomorrow)

All inputs are GEE assets already verified; one `reduceRegions` per grid cell batch, same as the main pipeline.

### 4.1 Inputs per cell (CONUS, with global fallback)
| Component | CONUS input | Global fallback |
|---|---|---|
| Intensity (static; reported as its own output, not fed to S_eco or C_people) | `USDA/WRC/v0` CFL, FLEP8 | none → derive from land cover + tree cover (e.g. MODIS VCF; UNVERIFIED) |
| Intensity (day) | gridMET ERC (or BI) percentile at that cell | ERA5/FWI if team has it (UNVERIFIED) |
| Crown-fire potential | LANDFIRE CC, CBH, CBD + Van Wagner I₀ vs surface intensity | — |
| Ecological severity | MTBS-trained model or rule: P(high sev) | — |
| Regime | LANDFIRE FRG, MFRI, VDep (+ PRS = % replacement) | — (assume neutral 1.0) |
| People / assets | GHSL built-up m² and population within 5 km; WUI class (SILVIS); WRC CRPS, Exposure | GHSL built-up + pop (global) |

### 4.2 Formulas (hackathon-grade, explicitly heuristic)
1. **Fire-behaviour intensity index** I ∈ [0,1]
   `I = clip( 0.5·FLEP8 + 0.5·min(CFL/12 ft, 1) , 0,1) × w_day`, with `w_day = clip(ERC_pct/0.8, 0.5, 1.25)` (ERC percentile relative to the cell's own climatology from gridMET). The CFL/12-ft and the ERC scaling are choices, not literature values.
   Optional crown flag: `crown = (CBH>0) & (I_surface_kW/m > (0.010·CBH_m·(460+25.9·100))^1.5)` using FMC = 100% (assumption).
2. **Ecological severity** S_eco ∈ [0,1] = P(MTBS class 4 | burned), either
   (a) quick model: LightGBM on the MTBS per-fire sample (§4.5) with features pre-fire lifeform/EVC/EVH (LANDFIRE v1.4.0), FRG, slope, pre-fire NDVI/NDMI, + gridMET at the burn date if the team joins MTBS `Ig_Date`; or
   (b) rule if no time to train — **do NOT use S_eco = I** (§4.5 shows it is anti-correlated). Use a lookup of the MTBS high-severity share by pre-fire lifeform × FRG measured in §4.5: non-tree ≈ 0.01; tree & FRG 1 ≈ 0.08; tree & FRG 3 ≈ 0.10; tree & FRG 4 ≈ 0.23; tree & FRG 5 ≈ 0.20 (rescale to 0–1 by dividing by 0.25), then multiply by `w_day`. For non-forest, ecological harm is better expressed through the regime term than through MTBS class 4.
3. **Regime adjustment** (good fire vs bad fire) — multiplier R on ecological harm:
   - FRG 1 (≤35 yr, low/mixed) and S_eco < 0.3 → R = 0.3 ("restorative fire"; can even be reported as *beneficial*).
   - FRG 1 or 3 and S_eco ≥ 0.5 → R = 1.5 (uncharacteristic high severity; Steel et al. 2015).
   - FRG 2, 4 (replacement regimes) → R = 0.8 (in-regime; ecosystem adapted).
   - FRG 5 (>200 yr) → R = 1.0.
   - Optional, untested: multiply by `(0.5 + VDep/100)`. §4.5 found VDep does not rank MTBS high severity in the assumed direction (AUC 0.42), so default is to leave it out and show VDep as context only.
   `C_eco = clip(S_eco × R, 0, 1)`. The R values are value judgements, not fitted.
4. **People/assets** C_people ∈ [0,1]:
   `C_people = pct_rank(log1p(built_surface_mean_5km))` (GHSL, global). §4.5 shows WRC CFL/CRPS add no skill for structure loss once exposure and size are known, so keep them out of the score (show CRPS only as a context layer); WUI flag (+0.1 for interface/intermix) is an untested option. Rationale: Syphard 2012 / Higuera 2023 → exposure dominates.
5. **Consequence** = `0.7·C_people + 0.3·C_eco` (weights are a value choice; expose a slider in the UI).
6. **Expected impact** = `P(ign) × P(large|ign) × Consequence`. This follows the RMRS-GTR-315 risk definition (probability × conditional consequence). Show the three factors as a stacked explanation; an "Expected structures at risk" variant is `P(ign)·P(large|ign)·E[structures destroyed | large fire]` with the last term fitted on ICS-209-PLUS (§4.5, Poisson/Tweedie regression on log built-up, CFL, CRPS).

### 4.3 Validation with open labels
- **C_people**: ICS-209-PLUS 1999–2020 incidents in CONUS (POO points) → AUC of P(any structure destroyed) and Spearman with log(destroyed). Control for fire size (log acres) — otherwise you validate P(large), not consequence. Done in §4.5.
- **S_eco**: MTBS mosaics → AUC for class 4 vs 1–3 on pixels; also fire-level %high-severity vs FIRMS FRP p90 (Heward 2013).
- **Intensity**: WFIGS `FireBehaviorGeneral` (Minimal/Moderate/Active/Extreme; 79.5% filled for ≥1000 ac fires) as ordinal label vs I (Spearman). Weak, but independent.
- Time split: train ≤2016, test 2017–2020 (ICS) / 2017–2022 (MTBS).

### 4.4 Known caveats
- Fuel vintage leakage: LANDFIRE 2.4.0 / WRC (LF 2020 fuels) **post-date many MTBS fires** — already-burned areas look like low fuel (e.g. Paradise CA CFL is low in WRC because the 2018 Camp Fire changed fuels). For validation use fires that occurred after the fuel vintage or accept optimistic/pessimistic bias; state this on the slides.
- CRPS is "if a home were there" — it is not exposure; combine with built-up/WUI.
- ICS-209 zeros may be unreported; POO point ≠ where homes burned (they burn downwind, km away) → 5 km buffers.
- MTBS 2025/2026 images exist but the catalog page says 1984–2024; treat as provisional.

### 4.5 Prototype validation results (VERIFIED — computed today; scripts `explore/damage/09–14`, outputs `validation.json`, `mtbs_auc_by_period.json`, `mtbs_forest_auc.json`, `mtbs_lifeform_auc.json`)

**A. Structure loss (ICS-209-PLUS 1999–2020).** Sample: CONUS incidents 2005–2020 with FINAL_ACRES ≥ 100 and valid coordinates: n = 20,853; 2,442 (11.7%) with `STR_DESTROYED_TOTAL > 0`. Covariates sampled at the point of origin. Label: any structure destroyed.

| predictor (single) | AUC | Spearman vs log(1+destroyed) |
|---|---|---|
| log10 final acres (fire size) | 0.710 | 0.241 |
| GHSL built-up, mean within 5 km (log) | 0.584 | 0.097 |
| GHSL population, mean within 5 km (log) | 0.577 | 0.088 |
| WRC FLEP8 (2 km mean) | 0.557 | 0.066 |
| WRC CFL (2 km mean) | 0.553 | 0.061 |
| WRC CRPS (2 km mean) | 0.550 | 0.057 |
| WRC RPS (2 km mean) | 0.502 | 0.004 |
| WRC WHP (2 km mean) | 0.496 | −0.001 |
| WRC Exposure (point) | 0.407 | −0.120 |
| heuristic C_score (0.6 built + 0.2 CFL + 0.2 CRPS, ranks) | 0.624 | 0.142 |

Logistic regression, 5-fold CV AUC: size only 0.708; **size + built-up 0.779**; size + built-up + CFL + CRPS 0.779; built-up + CFL + CRPS (no size) 0.594.
P(any destroyed) by built-up decile (low→high): 0.061, 0.075, 0.099, 0.120, 0.126, 0.120, 0.111, 0.125, 0.137, 0.196.
Reading: exposure adds real skill on top of size (+0.07 AUC) and the loss rate triples from the lowest to the highest built-up decile; the WRC hazard layers add nothing at the origin point. Caveats: random (not temporal) CV; origin point, not perimeter; zeros may be unreported; "built-up within 5 km" is a kernel *mean* (m² per 100 m pixel), not a sum; WRC fuels post-date most of these fires.

**B. Ecological severity (MTBS).** Sample: 60 random MTBS wildfires per year 2016–2022 (419 fires), 40 pixels each → 16,367 burned pixels (classes 1–4: 2,122 / 11,031 / 2,399 / 815; 5.0% high).

| predictor | AUC for class 4 (all pixels) | 2021–2022 only (after WRC fuel vintage, n = 4,739) | tree pixels only (n = 7,109) |
|---|---|---|---|
| WRC CFL | 0.324 | 0.374 | 0.451 |
| WRC FLEP4 | 0.315 | 0.340 | — |
| WRC FLEP8 | 0.390 | 0.426 | 0.437 |
| WRC WHP | 0.544 | 0.565 | 0.457 |
| WRC BP | 0.484 | 0.544 | — |
| LANDFIRE CC (LF 2.4.0, post-fire vintage) | 0.458 | 0.500 | — |
| LANDFIRE VDep | 0.424 | 0.367 | 0.402 |
| pre-fire lifeform = tree (EVC v1.4.0) | **0.740** | — | — |
| pre-fire EVH v1.4.0 code | 0.763 (largely a lifeform code) | — | — |
| pre-fire tree cover % (EVC) | — | — | 0.518 |

High-severity share by pre-fire lifeform: herb 0.2% (n 4,996), shrub 1.6% (3,643), tree 10.2% (7,109). Within tree pixels by FRG: FRG 1 7.5% (n 4,244), FRG 3 9.8% (1,654), FRG 4 23.1% (661), FRG 5 19.6% (459), FRG 2 1.1% (88). In FRG 1+3 overall, 93.7% of burned pixels were low/moderate/unburned.
Reading: (i) static layers cannot rank severity *within* forest (all AUC ≈ 0.4–0.52) — the literature (Parks 2018: live fuel 53%, fire weather 23%) says pre-fire NDVI/NDMI and day-of weather are needed; these were not tested today. (ii) Lifeform × FRG gives a usable prior. (iii) The regime logic is supported: replacement-regime forests (FRG 4/5) burn at high severity ~2–3× more often than frequent-fire forests (FRG 1), where most burned area is low/moderate — the "good fire" case. Caveats: MTBS class thresholds are analyst-set per fire; class 4 in grass/shrub is under-represented by dNBR; fires <1000 ac (W) / <500 ac (E) absent; 40 px/fire is a small sample; the AUC < 0.5 for VDep contradicts the assumed direction of the `(0.5+VDep/100)` multiplier in §4.2 — treat that multiplier as an untested value judgement or drop it.

**Not done:** WFIGS `FireBehaviorGeneral` vs intensity; FRP p90 vs MTBS; any model with day-of weather or pre-fire NDVI; temporal hold-out.

---

## 5. Compliance (hackathon rules: free/public data, OSI code, cite all, no proprietary)

| Item | Status |
|---|---|
| WRC (`USDA/WRC/v0`) | CC-BY-4.0 — OK, cite Scott et al. 2024 |
| MTBS, LANDFIRE, RAVG, WFIGS, gridMET, 3DEP | US Government public data — OK; LANDFIRE asks for a "descriptive modifier" on derivative products |
| ICS-209-PLUS 1999–2020 | CC BY 4.0 — OK, cite St. Denis et al. 2023 + figshare DOI |
| SILVIS WUI v4 | CC0 per GEE community catalog — OK |
| MS Building Footprints | ODbL — OK but share-alike for derived *databases*; cite |
| GHSL / GPW / WorldPop | open (CC BY 4.0 — licence text not re-read today) |
| FEMA NRI | public US Gov; licence text not read (UNVERIFIED) |
| FIRMS FRP via API | free but **requires registration (MAP_KEY)** — flag as "registration-gated"; the GEE `FIRMS` asset has no FRP |
| `pyretechnics` | **CONFLICT** at HEAD (non-OSI dual licence since 2026-10-05). Pin `2026.8.10` (EPL-2.0, OSI-approved) or avoid |
| `firelab/behave` | public-domain US-Gov notice — OK (not an OSI licence; public domain) |
| GEE community catalog (`projects/sat-io/...`) | community mirror; cite underlying producers (LANDFIRE, SILVIS, Microsoft) plus Roy, S. et al. awesome-gee-community-catalog (UNVERIFIED citation form) |
| Google Earth Engine itself | a free-for-noncommercial platform, not OSI; data are open — mention as compute platform only, do not promote |
| RDS archive (fs.usda.gov) & apps.fs.usda.gov | returned **HTTP 403** to scripted requests — prefer the GEE copies |
| BehavePlus/FlamMap/FSim desktop | free US-Gov software but not OSI-licensed source releases (UNVERIFIED); we only use their published outputs (WRC) |

---

## 6. References (DOIs verified via Crossref API on 2026-11-14 unless marked)
- Andrews, P.L. 2018. The Rothermel surface fire spread model and associated developments. USDA FS RMRS-GTR-371. doi:10.2737/RMRS-GTR-371
- Birch, D.S. et al. 2015. Vegetation, topography and daily weather influenced burn severity in central Idaho and western Montana forests. Ecosphere 6. doi:10.1890/ES14-00213.1
- Dillon, G.K. et al. 2011. Both topography and climate affected forest and woodland burn severity in two regions of the western US, 1984 to 2006. Ecosphere 2:art130. doi:10.1890/ES11-00271.1
- Finney, M.A. et al. 2011. A simulation of probabilistic wildfire risk components for the continental United States. SERRA 25:973–1000. doi:10.1007/s00477-011-0462-z
- Heward, H. et al. 2013. Is burn severity related to fire intensity? IJWF 22:910–918. doi:10.1071/WF12087
- Higuera, P.E. et al. 2023. Shifting social-ecological fire regimes explain increasing structure loss from Western wildfires. PNAS Nexus 2:pgad005. doi:10.1093/pnasnexus/pgad005
- Keeley, J.E. 2009. Fire intensity, fire severity and burn severity. IJWF 18:116–126. doi:10.1071/WF07049
- Knapp, E.E. et al. 2021. Housing arrangement and vegetation factors associated with single-family home survival in the 2018 Camp Fire. Fire Ecology 17:25. doi:10.1186/s42408-021-00117-0
- Kolden, C.A. 2019. We're not doing enough prescribed fire in the western United States to mitigate wildfire risk. Fire 2:30. doi:10.3390/fire2020030
- Miller, J.D. & Thode, A.E. 2007. Quantifying burn severity … RdNBR. RSE 109:66–80. doi:10.1016/j.rse.2006.12.006
- Parks, S.A. et al. 2018. High-severity fire: evaluating its key drivers and mapping its probability across western US forests. ERL 13:044037. doi:10.1088/1748-9326/aab791
- Parks, S.A. et al. 2019. Giving ecological meaning to satellite-derived fire severity metrics across North American forests. Remote Sens. 11:1735. doi:10.3390/rs11141735
- Radeloff, V.C. et al. 2018. Rapid growth of the US wildland-urban interface raises wildfire risk. PNAS 115:3314–3319. doi:10.1073/pnas.1718850115
- Radeloff, V.C. et al. 2023. The 1990–2020 wildland-urban interface of the conterminous United States – geospatial data, 4th Ed. USFS RDS. doi:10.2737/RDS-2015-0012-4 (from GEE community catalog page; not resolved via Crossref)
- Rollins, M.G. 2009. LANDFIRE: a nationally consistent vegetation, wildland fire, and fuel assessment. IJWF 18:235–249. doi:10.1071/WF08088
- Rothermel, R.C. 1972. A mathematical model for predicting fire spread in wildland fuels. USDA FS Res. Pap. INT-115. (UNVERIFIED, no DOI checked)
- Schroeder, W. et al. 2014. The New VIIRS 375 m active fire detection data product. RSE 143:85–96. doi:10.1016/j.rse.2013.12.008
- Scott, J.H. & Burgan, R.E. 2005. Standard fire behavior fuel models. RMRS-GTR-153. doi:10.2737/RMRS-GTR-153
- Scott, J.H. & Reinhardt, E.D. 2001. Assessing crown fire potential by linking models of surface and crown fire behavior. RMRS-RP-29. doi:10.2737/RMRS-RP-29
- Scott, J.H., Thompson, M.P. & Calkin, D.E. 2013. A wildfire risk assessment framework for land and resource management. RMRS-GTR-315. doi:10.2737/RMRS-GTR-315
- Scott, J.H. et al. 2024. Wildfire Risk to Communities: Spatial datasets of landscape-wide wildfire risk components for the United States, 2nd Ed. USFS RDS. doi:10.2737/RDS-2020-0016-2 (from GEE catalog page)
- St. Denis, L.A. et al. 2020. All-hazards dataset mined from the US National Incident Management System 1999–2014. Sci. Data 7:64. doi:10.1038/s41597-020-0403-0
- St. Denis, L.A. et al. 2023. All-hazards dataset mined from the US National Incident Management System 1999–2020. Sci. Data 10:112. doi:10.1038/s41597-023-01955-0 ; data: figshare doi:10.6084/m9.figshare.19858927.v3 (CC BY 4.0)
- Steel, Z.L., Safford, H.D. & Viers, J.H. 2015. The fire frequency-severity relationship and the legacy of fire suppression in California forests. Ecosphere 6. doi:10.1890/ES14-00224.1
- Syphard, A.D. et al. 2012. Housing arrangement and location determine the likelihood of housing loss due to wildfire. PLoS ONE 7:e33954. doi:10.1371/journal.pone.0033954
- Syphard, A.D., Brennan, T.J. & Keeley, J.E. 2014. The role of defensible space for residential structure protection during wildfires. IJWF 23:1165–1175. doi:10.1071/WF13158
- Thode, A.E. et al. 2011. Quantifying the fire regime distributions for severity in Yosemite National Park. IJWF 20:223–239. doi:10.1071/WF09060
- Van Wagner, C.E. 1977. Conditions for the start and spread of crown fire. Can. J. For. Res. 7:23–34. doi:10.1139/x77-004
- Wooster, M.J. et al. 2005. Retrieval of biomass combustion rates and totals from fire radiative power observations. JGR 110. doi:10.1029/2005JD006318
- Byram, G.M. 1959. Combustion of forest fuels. In: Davis, K.P. (ed.) Forest Fire: Control and Use. (UNVERIFIED)

## Appendix — files produced
- Scripts: `explore/damage/01_gee_assets.py` … `14_mtbs_lifeform_auc.py`
- Cached evidence: `data/raw/damage_research/` (`gee_assets.json`, `gee_listing.json`, `gee_samples.json`, `gee_wrc.json`, `wfigs_layer.json`, `wfigs_fillrates.json`, `nri_tracts_layer.json`, `nri_sample.json`, `crossref*.json`, `openalex_abstracts*.json`, `ics209plus/`, `ics209_fieldstats.json`, `ics209_covariates.csv`, `mtbs_severity_sample.csv`, `mtbs_severity_sample_prefire.csv`, `validation.json`, `mtbs_auc_by_period.json`, `mtbs_forest_auc.json`, `mtbs_lifeform_auc.json`, `http_status.txt`, licence files `lic_*`)
