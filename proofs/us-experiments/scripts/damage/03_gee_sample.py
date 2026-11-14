"""Sample damage-relevant layers at test points (CONUS) to verify values/units."""
import sys, os, json
sys.path.insert(0, 'explore'); import _env, ee
ee.Initialize(project=os.environ['EE_PROJECT'])
L='projects/sat-io/open-datasets/landfire/'
out={}
d=json.load(open('data/raw/damage_research/gee_listing.json'))
ids=d['mtbs_ids']; conus=[i for i in ids if '_CONUS_' in i]; print('MTBS CONUS years',conus[0],conus[-1],len(conus))
out['mtbs_conus']=[conus[0],conus[-1],len(conus)]
for k in ['FUEL/CBD','FUEL/CBH','FUEL/CC','FUEL/CH','FUEL/FBFM13','FUEL/FBFM40','VEGETATION/VDEP','FIRE-REGIME/FRG','FIRE-REGIME/FRI']:
    c=ee.ImageCollection(L+k); ix=c.aggregate_array('system:index').getInfo(); out[k]=ix; print(k,ix)
pts={'Paradise_CA':[-121.60,39.76],'Lahaina_HI':[-156.68,20.88],'Flagstaff_AZ':[-111.70,35.15],'Okeechobee_FL':[-80.9,27.2]}
img=(ee.Image(L+'FUEL/FBFM40/F40_LC_240').rename('FBFM40')
  .addBands(ee.ImageCollection(L+'FUEL/CBD').filter(ee.Filter.stringContains('system:index','LC')).first().rename('CBD'))
  .addBands(ee.ImageCollection(L+'FUEL/CBH').filter(ee.Filter.stringContains('system:index','LC')).first().rename('CBH'))
  .addBands(ee.ImageCollection(L+'FUEL/CC').filter(ee.Filter.stringContains('system:index','LC')).first().rename('CC'))
  .addBands(ee.ImageCollection(L+'FUEL/CH').filter(ee.Filter.stringContains('system:index','LC')).first().rename('CH'))
  .addBands(ee.ImageCollection('LANDFIRE/Fire/FRG/v1_2_0').filter(ee.Filter.eq('system:index','CONUS')).first().rename('FRG'))
  .addBands(ee.ImageCollection('LANDFIRE/Fire/MFRI/v1_2_0').filter(ee.Filter.eq('system:index','CONUS')).first().rename('MFRI'))
  .addBands(ee.ImageCollection('LANDFIRE/Fire/VDep/v1_4_0').filter(ee.Filter.eq('system:index','CONUS')).first().rename('VDep'))
  .addBands(ee.Image('USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1/mtbs_CONUS_2018').rename('MTBS2018')))
print('FRG ids', ee.ImageCollection('LANDFIRE/Fire/FRG/v1_2_0').aggregate_array('system:index').getInfo())
for n,(x,y) in pts.items():
    v=img.reduceRegion(ee.Reducer.first(), ee.Geometry.Point([x,y]), 30).getInfo(); out[n]=v; print(n,v)
json.dump(out,open('data/raw/damage_research/gee_samples.json','w'),indent=1)
