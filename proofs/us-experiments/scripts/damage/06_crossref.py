"""Verify reference DOIs via Crossref API (title, journal, year)."""
import requests, json, sys
dois=sys.argv[2:]; H={'User-Agent':'SpaceApps2026-research/0.1'}
out={}
for d in dois:
    try:
        r=requests.get('https://api.crossref.org/works/'+d,headers=H,timeout=30)
        if r.status_code!=200: out[d]={'status':r.status_code}; print('X',r.status_code,d); continue
        m=r.json()['message']; a=m.get('author',[])
        rec={'title':(m.get('title') or [''])[0],'journal':(m.get('container-title') or [''])[0],'year':m.get('issued',{}).get('date-parts',[[None]])[0][0],
             'first':(a[0].get('family') if a else None),'n_auth':len(a),'vol':m.get('volume'),'page':m.get('page') or m.get('article-number')}
        out[d]=rec; print('OK',d,'|',rec['first'],rec['year'],'|',rec['title'][:110],'|',rec['journal'],rec['vol'],rec['page'])
    except Exception as e: print('ERR',d,e)
json.dump(out,open(sys.argv[1],'w'),indent=1)
