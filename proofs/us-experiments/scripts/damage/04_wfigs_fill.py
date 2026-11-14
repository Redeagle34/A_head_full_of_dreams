"""Fill rates of damage-related fields on public WFIGS Incident Locations service."""
import requests, json, sys
B='https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations/FeatureServer/0/query'
H={'User-Agent':'SpaceApps2026-research/0.1'}
def cnt(w):
    r=requests.get(B,params={'where':w,'returnCountOnly':'true','f':'json'},headers=H,timeout=60).json()
    return r.get('count',r)
fields=['FireBehaviorGeneral','EstimatedCostToDate','EstimatedFinalCost','PredominantFuelGroup','PredominantFuelModel','PrimaryFuelModel','FireMgmtComplexity','IncidentComplexityLevel','FinalAcres','IncidentSize','FireCause']
base={"all":"IncidentTypeCategory='WF'","large(>=1000ac)":"IncidentTypeCategory='WF' AND IncidentSize>=1000"}
out={}
for bn,bw in base.items():
    n=cnt(bw); out[bn]={'n':n}
    for f in fields:
        out[bn][f]=cnt(f"{bw} AND {f} IS NOT NULL")
    print(bn,out[bn])
r=requests.get(B,params={'where':"IncidentTypeCategory='WF' AND IncidentSize>=1000 AND FireBehaviorGeneral IS NOT NULL",'outFields':'IncidentName,IncidentSize,FireBehaviorGeneral,PredominantFuelGroup,EstimatedCostToDate,FireDiscoveryDateTime','resultRecordCount':5,'f':'json'},headers=H,timeout=60).json()
out['sample']=[f['attributes'] for f in r.get('features',[])]
print(out['sample'])
r=requests.get(B,params={'where':"IncidentTypeCategory='WF' AND FireBehaviorGeneral IS NOT NULL",'groupByFieldsForStatistics':'FireBehaviorGeneral','outStatistics':json.dumps([{'statisticType':'count','onStatisticField':'OBJECTID','outStatisticFieldName':'n'}]),'f':'json'},headers=H,timeout=60).json()
out['fbg_values']=[f['attributes'] for f in r.get('features',[])]; print(out['fbg_values'])
json.dump(out,open(sys.argv[1],'w'),indent=1,default=str)
