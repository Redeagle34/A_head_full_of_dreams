"""AUC of static hazard layers for MTBS high severity, split by fire year relative to fuel vintage
(WRC uses LANDFIRE 2020 fuels; LANDFIRE fuels in sat-io are LF 2.4.0 = 2023 conditions)."""
import sys, json, pandas as pd
from sklearn.metrics import roc_auc_score
b=pd.read_csv(sys.argv[1]); b['high']=(b.sev==4).astype(int); out={}
for name,sub in {'2016-2020 (pre-vintage, leakage)':b[b.year<=2020],'2021-2022 (after WRC fuel vintage)':b[b.year>=2021]}.items():
    o={'n':len(sub),'fires':int(sub.Event_ID.nunique()),'high_frac':round(sub.high.mean(),3)}
    for c in ['CFL','FLEP4','FLEP8','WHP','BP','CC','VDep']:
        v=sub[c].where(sub[c]<=100) if c in('CC','VDep') else sub[c]; m=v.notna()
        o[c]=round(roc_auc_score(sub.high[m],v[m]),3)
    o['high_by_FRG']=sub.groupby('FRG').high.mean().round(3).to_dict()
    out[name]=o; print(name,o)
json.dump(out,open(sys.argv[2],'w'),indent=1,default=str)
