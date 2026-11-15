"""Prototype validation: extract consequence covariates at ICS-209-PLUS incident points (CONUS, 2005-2020)
from Earth Engine (WRC v0, GHSL built-up + population, LANDFIRE FRG/VDep, WUI-derived proxies) and save CSV.
Usage: python 09_ics209_extract.py <incidents_csv> <out_csv>"""
import sys, os, pandas as pd, numpy as np
sys.path.insert(0, 'explore'); import _env, ee
ee.Initialize(project=os.environ['EE_PROJECT'])
d=pd.read_csv(sys.argv[1],low_memory=False)
d['lat']=d['POO_LATITUDE'].fillna(d['LRGST_FOD_LATITUDE']); d['lon']=d['POO_LONGITUDE'].fillna(d['LRGST_FOD_LONGITUDE'])
d=d[(d.START_YEAR>=2005)&d.lat.between(24.5,49.5)&d.lon.between(-125,-66.5)&(d.FINAL_ACRES>=100)].copy()
d=d[['INCIDENT_ID','START_YEAR','FINAL_ACRES','STR_DESTROYED_TOTAL','STR_THREATENED_MAX','POO_STATE','lat','lon','DISCOVERY_DOY']].reset_index(drop=True)
print('incidents',len(d), (d.STR_DESTROYED_TOTAL>0).sum())
wrc=ee.ImageCollection('USDA/WRC/v0').filter(ee.Filter.eq('system:index','CONUS')).first()
built=ee.Image('JRC/GHSL/P2023A/GHS_BUILT_S/2020').select('built_surface')
pop=ee.Image('JRC/GHSL/P2023A/GHS_POP/2020')
frg=ee.ImageCollection('LANDFIRE/Fire/FRG/v1_2_0').filter(ee.Filter.eq('system:index','CONUS')).first().rename('FRG')
vdep=ee.ImageCollection('LANDFIRE/Fire/VDep/v1_4_0').filter(ee.Filter.eq('system:index','CONUS')).first().rename('VDep')
# neighbourhood sums within 5 km (GHSL 100 m): built m2 and population
k=ee.Kernel.circle(5000,'meters')
built5=built.reduceNeighborhood(ee.Reducer.sum(),k).rename('built_m2_5km')
pop5=pop.reduceNeighborhood(ee.Reducer.sum(),k).rename('pop_5km')
# WRC neighbourhood means at 270 m-ish
wrc_n=wrc.select(['CRPS','CFL','FLEP8','BP','WHP','RPS']).reduceNeighborhood(ee.Reducer.mean(),ee.Kernel.circle(2000,'meters')).regexpRename('_mean','_2km')
stack=wrc.select(['CRPS','CFL','FLEP4','FLEP8','BP','Exposure','RPS','WHP']).addBands(wrc_n).addBands(frg).addBands(vdep)
rows=[]
for i in range(0,len(d),1500):
    ch=d.iloc[i:i+1500]
    fc=ee.FeatureCollection([ee.Feature(ee.Geometry.Point([r.lon,r.lat]),{'INCIDENT_ID':r.INCIDENT_ID}) for r in ch.itertuples()])
    a=stack.reduceRegions(fc,ee.Reducer.first(),scale=270,tileScale=4)
    b=built5.addBands(pop5).reduceRegions(a,ee.Reducer.first(),scale=100,tileScale=4)
    rows+= [f['properties'] for f in b.getInfo()['features']]; print(i,len(rows),flush=True)
x=pd.DataFrame(rows); out=d.merge(x,on='INCIDENT_ID',how='left'); out.to_csv(sys.argv[2],index=False); print(out.describe().T)
