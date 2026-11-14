"""List community-catalog folders (sat-io) for LANDFIRE fuels, WRC, WHP; MTBS image ids."""
import sys, os, json
sys.path.insert(0, 'explore'); import _env, ee
ee.Initialize(project=os.environ['EE_PROJECT'])
out={}
def ls(p, depth=0, maxd=2):
    try:
        r=ee.data.listAssets({'parent':p})['assets']
    except Exception as e:
        print('ERR',p,str(e)[:100]); return
    out[p]=[(a['id'],a['type']) for a in r]
    for a in r:
        print('  '*depth, a['type'], a['id'].replace('projects/sat-io/open-datasets/',''))
        if a['type']=='FOLDER' and depth<maxd: ls(a['id'],depth+1,maxd)
for p in ['projects/sat-io/open-datasets/landfire','projects/sat-io/open-datasets/USFS','projects/sat-io/open-datasets/MSBuildings/US']:
    print('==',p); ls(p,0,2 if 'MSB' not in p else 0)
# root listing filtered
for p in ['projects/sat-io/open-datasets/WUI','projects/sat-io/open-datasets/SILVIS','projects/sat-io/open-datasets/wildfire-risk','projects/sat-io/open-datasets/WRC','projects/sat-io/open-datasets/FEMA','projects/sat-io/open-datasets/USFS-WRC','projects/sat-io/open-datasets/FSIM','projects/sat-io/open-datasets/whp']:
    print('==',p); ls(p,0,1)
mt=ee.ImageCollection('USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1')
ids=mt.aggregate_array('system:index').getInfo(); out['mtbs_ids']=ids; print('MTBS',ids[:3],ids[-4:])
fc=ee.FeatureCollection('USFS/GTAC/MTBS/burned_area_boundaries/v1')
print('MTBS bnd props', fc.first().propertyNames().getInfo()); print(fc.size().getInfo())
f40=ee.ImageCollection('projects/sat-io/open-datasets/landfire/FUEL/FBFM40'); print('F40 ids',f40.aggregate_array('system:index').getInfo())
json.dump(out,open('data/raw/damage_research/gee_listing.json','w'),indent=1)
