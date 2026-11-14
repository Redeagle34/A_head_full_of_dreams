"""Validate prototype consequence & severity scores against open labels.
A) ICS-209-PLUS: P(any structure destroyed) and log1p(destroyed) vs consequence proxies (AUC / Spearman).
B) MTBS: P(high severity | burned) vs CFL/FLEP8/CC/FRG/VDep (AUC), high-sev fraction by FRG."""
import sys, json, numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
from scipy.stats import spearmanr
res={}
a=pd.read_csv(sys.argv[1]); a=a.dropna(subset=['CRPS'])
a['y']=(a.STR_DESTROYED_TOTAL>0).astype(int)
a['log_area']=np.log10(a.FINAL_ACRES.clip(lower=1))
a['log_built']=np.log1p(a.built_m2_5km.fillna(0)); a['log_pop']=np.log1p(a.pop_5km.fillna(0))
a['FLEP8x']=a['FLEP8_2km'].fillna(0); a['CFLx']=a['CFL_2km'].fillna(0)
# hackathon consequence score: exposure (log built-up within 5 km) x intensity (CFL neighbourhood) — rank-normalised
r=lambda s: s.rank(pct=True)
a['C_score']=r(a.log_built)*0.6+r(a.CFLx)*0.2+r(a.CRPS_2km.fillna(0))*0.2
print('ICS n',len(a),'pos',a.y.sum())
A={}
for c in ['log_built','log_pop','CRPS','CRPS_2km','RPS_2km','CFLx','FLEP8x','WHP_2km','Exposure','C_score','log_area']:
    s=a[c].fillna(a[c].median()); A[c]={'AUC_anyDestroyed':round(roc_auc_score(a.y,s),3),'spearman_logDestroyed':round(spearmanr(s,np.log1p(a.STR_DESTROYED_TOTAL)).correlation,3)}
    print('ICS',c,A[c])
# conditional on size: does C_score add info beyond fire size? (logistic regression AUC, 5-fold)
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_predict
for feats in [['log_area'],['log_area','log_built'],['log_area','log_built','CFLx','CRPS_2km'],['log_built','CFLx','CRPS_2km']]:
    X=a[feats].fillna(0).values; p=cross_val_predict(LogisticRegression(max_iter=1000),X,a.y,cv=5,method='predict_proba')[:,1]
    A['LR:'+'+'.join(feats)]=round(roc_auc_score(a.y,p),3); print('LR',feats,A['LR:'+'+'.join(feats)])
# loss rate by built-up decile
a['bdec']=pd.qcut(a.log_built.rank(method='first'),10,labels=False)
A['pAnyDestroyed_by_built_decile']=a.groupby('bdec').y.mean().round(3).tolist(); print(A['pAnyDestroyed_by_built_decile'])
res['ICS209']=A
b=pd.read_csv(sys.argv[2]); b['high']=(b.sev==4).astype(int)
B={'n':len(b),'class_counts':b.sev.value_counts().sort_index().to_dict()}
bb=b.copy()
for c in ['CFL','FLEP4','FLEP8','WHP','BP','CC','VDep']:
    v=bb[c].where(bb[c]<=100 if c in('CC','VDep') else bb[c].notna()); m=v.notna()
    B[c]=round(roc_auc_score(bb.high[m],v[m]),3); print('MTBS AUC high-sev',c,B[c],m.sum())
B['high_frac_by_FRG']=bb.groupby('FRG').high.agg(['mean','size']).round(3).to_dict('index'); print(B['high_frac_by_FRG'])
res['MTBS']=B
json.dump(res,open(sys.argv[3],'w'),indent=1,default=str)
