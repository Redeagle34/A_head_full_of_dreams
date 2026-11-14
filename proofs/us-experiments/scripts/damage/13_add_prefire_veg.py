"""Add pre-fire (LANDFIRE v1.4.0, ~2014 vintage) EVC/EVH and gridMET ERC at ignition to the MTBS sample, then
evaluate within-forest AUC (no post-fire fuel leakage)."""
import sys, os, json, pandas as pd, numpy as np
sys.path.insert(0,'explore'); import _env, ee
ee.Initialize(project=os.environ['EE_PROJECT'])
from sklearn.metrics import roc_auc_score
b=pd.read_csv(sys.argv[1])
evc=ee.ImageCollection('LANDFIRE/Vegetation/EVC/v1_4_0').filter(ee.Filter.eq('system:index','CONUS')).first().rename('EVC14')
evh=ee.ImageCollection('LANDFIRE/Vegetation/EVH/v1_4_0').filter(ee.Filter.eq('system:index','CONUS')).first().rename('EVH14')
img=evc.addBands(evh)
rows=[]
for i in range(0,len(b),4000):
    ch=b.iloc[i:i+4000]
    fc=ee.FeatureCollection([ee.Feature(ee.Geometry.Point([r.longitude,r.latitude]),{'k':int(ix)}) for ix,r in ch.iterrows()])
    rows+=[f['properties'] for f in img.reduceRegions(fc,ee.Reducer.first(),30,tileScale=4).getInfo()['features']]; print(i,flush=True)
x=pd.DataFrame(rows).set_index('k'); b=b.join(x)
b.to_csv(sys.argv[2],index=False)
b['high']=(b.sev==4).astype(int)
# LANDFIRE EVC codes: 101-199 = tree cover % (101 -> 10-19%? see catalog); keep raw code ranges
b['forest']=b.EVC14.between(100,199)
out={'forest_frac':round(b.forest.mean(),3),'high_frac_forest':round(b.high[b.forest].mean(),3),'high_frac_nonforest':round(b.high[~b.forest].mean(),3)}
f=b[b.forest]
for c in ['CFL','FLEP4','FLEP8','WHP','BP','EVC14','EVH14','VDep']:
    v=f[c].where(f[c]<=100) if c=='VDep' else f[c]; m=v.notna()
    out['forest_AUC_'+c]=round(roc_auc_score(f.high[m],v[m]),3)
out['forest_high_by_FRG']=f.groupby('FRG').high.agg(['mean','size']).round(3).to_dict('index')
print(out); json.dump(out,open(sys.argv[3],'w'),indent=1,default=str)
