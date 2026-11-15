"""NIFC WFIGS Incident Locations (public ArcGIS service, no key) for selected years -> parquet (cached)."""
import requests, pandas as pd, pathlib, time, sys
R = pathlib.Path("data/raw/us_truth"); UA = {"User-Agent": "SpaceApps2026-research/0.1"}
BASE = "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations/FeatureServer/0/query"
F = "UniqueFireIdentifier,IncidentName,IncidentTypeCategory,FireDiscoveryDateTime,FireOutDateTime,FireCause,FireCauseGeneral,IncidentSize,DiscoveryAcres,FinalAcres,POOState,InitialLatitude,InitialLongitude,POOLandownerCategory"
for y in [int(a) for a in sys.argv[1:]] or [2023, 2024]:
    p = R / f"wfigs_{y}.parquet"
    if p.exists(): print("cached", p); continue
    rows, off = [], 0
    while True:
        r = requests.get(BASE, params={"where": f"FireDiscoveryDateTime >= DATE '{y}-01-01' AND FireDiscoveryDateTime < DATE '{y+1}-01-01'",
                                       "outFields": F, "returnGeometry": "false", "resultOffset": off, "resultRecordCount": 2000,
                                       "orderByFields": "OBJECTID", "f": "json"}, headers=UA, timeout=120)
        j = r.json(); feats = j.get("features", [])
        if "error" in j: print("ERR", j["error"]); break
        rows += [f["attributes"] for f in feats]; off += len(feats)
        if not feats or not j.get("exceededTransferLimit"): break
        time.sleep(0.5)
    d = pd.DataFrame(rows)
    for c in ["FireDiscoveryDateTime", "FireOutDateTime"]:
        if c in d: d[c] = pd.to_datetime(d[c], unit="ms", utc=True)
    d.to_parquet(p); print(y, len(d), d.IncidentTypeCategory.value_counts().to_dict())
