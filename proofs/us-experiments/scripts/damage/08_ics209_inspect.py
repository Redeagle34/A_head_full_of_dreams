"""Inspect ICS-209-PLUS wildfire incidents: structure-loss fields, fill, coordinates, linkage to MTBS/FOD."""
import pandas as pd, sys, json
f=sys.argv[1]
d=pd.read_csv(f,low_memory=False)
print(d.shape); cols=list(d.columns); print(cols)
keys=[c for c in cols if any(k in c.upper() for k in ['STR','DESTR','DAMAG','THREAT','FATAL','INJ','EVAC','COST','LAT','LON','MTBS','FOD','FSR','ACRES','IRWIN','FINAL'])]
s={}
for c in keys:
    nn=d[c].notna().sum(); s[c]={'nonnull':int(nn)}
    if pd.api.types.is_numeric_dtype(d[c]): s[c].update(gt0=int((d[c]>0).sum()), sum=float(d[c].sum()))
    print(c,s[c])
yr='START_YEAR' if 'START_YEAR' in cols else None
if yr and 'STR_DESTROYED_TOTAL' in cols:
    g=d.groupby(yr).agg(n=('INCIDENT_ID','size'),destroyed=('STR_DESTROYED_TOTAL','sum'),inc_with_loss=('STR_DESTROYED_TOTAL',lambda x:(x>0).sum()))
    print(g.tail(8)); s['by_year']=g.reset_index().to_dict('records')
json.dump(s,open(sys.argv[2],'w'),indent=1,default=str)
