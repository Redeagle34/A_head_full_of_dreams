"""Fetch abstracts via OpenAlex (inverted index) for verification of reported numbers."""
import requests, json, sys
H={'User-Agent':'SpaceApps2026-research/0.1'}
out={}
for d in sys.argv[2:]:
    r=requests.get('https://api.openalex.org/works/doi:'+d,headers=H,timeout=30)
    if r.status_code!=200: print('X',r.status_code,d); continue
    m=r.json(); inv=m.get('abstract_inverted_index') or {}
    pos=sorted((p,w) for w,ps in inv.items() for p in ps); ab=' '.join(w for p,w in pos)
    out[d]={'title':m.get('title'),'oa':m.get('open_access',{}).get('oa_url'),'abstract':ab}
    print('=====',d,m.get('title'),'\n',ab[:1800],'\n')
json.dump(out,open(sys.argv[1],'w'),indent=1)
