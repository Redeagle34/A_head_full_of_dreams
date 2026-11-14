"""Verify Earth Engine assets relevant to wildfire damage/severity."""
import sys, os, json
sys.path.insert(0, 'explore'); import _env, ee
ee.Initialize(project=os.environ['EE_PROJECT'])
ids = [
 'USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1',
 'USFS/GTAC/MTBS/burned_area_boundaries/v1',
 'LANDFIRE/Fire/FRG/v1_2_0','LANDFIRE/Fire/MFRI/v1_2_0','LANDFIRE/Fire/VDep/v1_4_0',
 'LANDFIRE/Fire/VCC/v1_4_0','LANDFIRE/Fire/PLS/v1_2_0','LANDFIRE/Fire/PMS/v1_2_0','LANDFIRE/Fire/PRS/v1_2_0',
 'LANDFIRE/Vegetation/EVT/v1_4_0','LANDFIRE/Vegetation/BPS/v1_4_0','LANDFIRE/Vegetation/EVC/v1_4_0','LANDFIRE/Vegetation/EVH/v1_4_0',
 'projects/sat-io/open-datasets/landfire/FUEL/FBFM40','projects/sat-io/open-datasets/landfire/FBFM40',
 'projects/sat-io/open-datasets/WRC','projects/sat-io/open-datasets/USFS/WRC',
 'projects/sat-io/open-datasets/MSBuildings/US','GOOGLE/Research/open-buildings/v3/polygons',
 'CIESIN/GPWv411/GPW_Population_Density','WorldPop/GP/100m/pop','JRC/GHSL/P2023A/GHS_POP','JRC/GHSL/P2023A/GHS_BUILT_S',
 'FIRMS','MODIS/061/MCD64A1','USGS/3DEP/10m','IDAHO_EPSCOR/GRIDMET',
 'projects/sat-io/open-datasets/USFS/wildfire_hazard_potential',
]
out={}
for a in ids:
    try:
        info = ee.data.getAsset(a)
        rec={'type':info.get('type'),'start':info.get('startTime'),'end':info.get('endTime')}
        if info.get('type') in ('IMAGE_COLLECTION',):
            c=ee.ImageCollection(a); f=c.first()
            rec['size']=c.size().getInfo() if 'GRIDMET' not in a and 'FIRMS' not in a and 'WorldPop' not in a else 'skip'
            rec['bands']=[b['id'] for b in f.getInfo()['bands']][:12]
        elif info.get('type')=='IMAGE':
            rec['bands']=[b['id'] for b in ee.Image(a).getInfo()['bands']][:12]
        out[a]=rec; print('OK ',a,rec)
    except Exception as e:
        out[a]={'error':str(e)[:150]}; print('ERR',a,str(e)[:120])
json.dump(out,open('data/raw/damage_research/gee_assets.json','w'),indent=1)
