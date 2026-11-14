"""MTBS high-severity vs pre-fire lifeform/cover (LANDFIRE EVC v1.4.0 codes) and static hazard layers.
EVC codes (GEE catalog): 101-109 tree 10..100%, 111-119 shrub, 121-129 herb; 151-153 tree coarse."""
import sys, json, pandas as pd, numpy as np
from sklearn.metrics import roc_auc_score
b=pd.read_csv(sys.argv[1]); b['high']=(b.sev==4).astype(int)
e=b.EVC14
b['life']=np.select([e.between(101,109)|e.between(151,153),e.between(111,119)|e.between(161,163),e.between(121,129)|e.between(171,172)],['tree','shrub','herb'],'other')
b['tree_cov']=np.where(e.between(101,109),(e-100)*10+5,np.nan)
out={'by_lifeform':b.groupby('life').high.agg(['mean','size']).round(3).to_dict('index')}
out['AUC_all_is_tree']=round(roc_auc_score(b.high,(b.life=='tree').astype(int)),3)
t=b[b.life=='tree']
for c in ['tree_cov','CFL','FLEP8','WHP','VDep']:
    v=t[c].where(t[c]<=100) if c=='VDep' else t[c]; m=v.notna(); out['tree_AUC_'+c]=round(roc_auc_score(t.high[m],v[m]),3)
out['tree_high_by_FRG']=t.groupby('FRG').high.agg(['mean','size']).round(3).to_dict('index')
# good-fire view: fraction of burned pixels in FRG I/III that were low/moderate (1-3) vs high
fr=b[b.FRG.isin([1,3])]
out['FRG1_3_share_low_mod']=round((fr.sev<=3).mean(),3); out['FRG1_3_share_high']=round((fr.sev==4).mean(),3)
print(json.dumps(out,indent=1,default=str)); json.dump(out,open(sys.argv[2],'w'),indent=1,default=str)
