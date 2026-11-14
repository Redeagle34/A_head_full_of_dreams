"""Verify USDA/WRC/v0 (Wildfire Risk to Communities) in GEE and sample it."""
import sys, os, json
sys.path.insert(0, 'explore'); import _env, ee
ee.Initialize(project=os.environ['EE_PROJECT'])
out={}
for a in ['USDA/WRC/v0','USFS/GTAC/WRC/v0']:
    try:
        i=ee.data.getAsset(a); print(a,i['type']); out[a]=i.get('type')
        c=ee.ImageCollection(a); print(c.aggregate_array('system:index').getInfo()[:10], c.size().getInfo())
        img=c.mosaic(); b=img.bandNames().getInfo(); print(b); out[a+'_bands']=b
        for n,(x,y) in {'Paradise_CA':[-121.60,39.76],'Flagstaff_AZ':[-111.70,35.15],'Okeechobee_FL':[-80.9,27.2],'Boulder_CO':[-105.29,40.0]}.items():
            v=img.reduceRegion(ee.Reducer.first(),ee.Geometry.Point([x,y]),30).getInfo(); print(n,v); out[n]=v
    except Exception as e: print('ERR',a,str(e)[:150])
json.dump(out,open('data/raw/damage_research/gee_wrc.json','w'),indent=1)
