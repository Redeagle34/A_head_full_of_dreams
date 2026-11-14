"""Prototype: does static hazard (WRC CFL/FLEP8, LANDFIRE fuels, FRG) predict MTBS high-severity?
Stratified sample of MTBS CONUS burned pixels (classes 1-4), years 2016-2022 (post LANDFIRE/WRC fuel vintages differ: caveat)."""
import sys, os, pandas as pd
sys.path.insert(0, 'explore'); import _env, ee
ee.Initialize(project=os.environ['EE_PROJECT'])
L='projects/sat-io/open-datasets/landfire/FUEL/'
mt=ee.ImageCollection('USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1')
for y in [2023,2024,2025,2026]:
    im=ee.Image(f'USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1/mtbs_CONUS_{y}')
    try:
        h=im.reduceRegion(ee.Reducer.frequencyHistogram(),ee.Geometry.Rectangle([-125,24,-66,50]),scale=2000,maxPixels=1e9,bestEffort=True,tileScale=4).getInfo()
        print('MTBS',y,h,flush=True)
    except Exception as e: print('MTBS hist fail',y,str(e)[:80],flush=True)
wrc=ee.ImageCollection('USDA/WRC/v0').filter(ee.Filter.eq('system:index','CONUS')).first().select(['CFL','FLEP4','FLEP8','WHP','BP'])
frg=ee.ImageCollection('LANDFIRE/Fire/FRG/v1_2_0').filter(ee.Filter.eq('system:index','CONUS')).first().rename('FRG')
vdep=ee.ImageCollection('LANDFIRE/Fire/VDep/v1_4_0').filter(ee.Filter.eq('system:index','CONUS')).first().rename('VDep')
cc=ee.Image(L+'CC/CC_LC_240').rename('CC') if False else ee.ImageCollection(L+'CC').filter(ee.Filter.stringContains('system:index','LC')).first().rename('CC')
rows=[]
for y in range(2016,2023):
    sev=ee.Image(f'USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1/mtbs_CONUS_{y}').rename('sev')
    sev=sev.updateMask(sev.gte(1).And(sev.lte(4)))
    st=sev.addBands([wrc,frg,vdep,cc]).addBands(ee.Image.pixelLonLat())
    fires=(ee.FeatureCollection('USFS/GTAC/MTBS/burned_area_boundaries/v1')
           .filter(ee.Filter.eq('Incid_Type','Wildfire'))
           .filterBounds(ee.Geometry.Rectangle([-125,24,-66,50]))
           .filter(ee.Filter.rangeContains('Ig_Date',ee.Date(f'{y}-01-01').millis(),ee.Date(f'{y}-12-31').millis()))
           .randomColumn('r',y).sort('r').limit(60))
    def per(f):
        return st.sample(region=f.geometry(),scale=30,numPixels=40,seed=y,geometries=False,tileScale=4,dropNulls=True).map(lambda p:p.set('Event_ID',f.get('Event_ID')))
    s=fires.map(per).flatten()
    r=[f['properties'] for f in s.getInfo()['features']]
    for q in r: q['year']=y
    rows+=r; print(y,len(r),flush=True)
df=pd.DataFrame(rows); df.to_csv(sys.argv[1],index=False); print(df.groupby('sev').size())
