"""Smoke-test ESG module after refactor."""
import json, urllib.request, urllib.error

BASE = 'http://localhost:8000'
tok = json.loads(urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/login',
    data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type':'application/json'},
)).read())['access_token']
H = {'Authorization': 'Bearer '+tok}

def get(url, label):
    try:
        r = urllib.request.urlopen(urllib.request.Request(BASE+url, headers=H))
        body = r.read()
        try:
            d = json.loads(body)
            if isinstance(d, list):
                s = f"list[{len(d)}]"
            elif isinstance(d, dict):
                s = f"keys={list(d.keys())[:6]}"
            else:
                s = str(d)[:60]
        except Exception:
            s = body[:80].decode(errors='replace')
        print(f"  OK {label:55s} [{r.status}, {len(body):>7}b] {s}")
        return d if isinstance(d, (dict, list)) else None
    except urllib.error.HTTPError as e:
        print(f"  ER {label:55s} [{e.code}] {e.read()[:160].decode(errors='replace')}")

print("ESG:")
ov = get('/esg/overview', '/esg/overview')
if ov:
    k = ov.get('kpis', {})
    print(f"        total={k.get('total_companies')}, with_data={k.get('companies_with_data')}, metrics={k.get('metrics_total')}")
    print(f"        coverage={k.get('coverage_pct')}%, leader={k.get('leader_company_name')} ({k.get('leader_rating_letter')})")
    print(f"        pillars={[p['pillar']+':'+str(p['metric_count']) for p in ov.get('pillars',[])]}")
    print(f"        rankings={len(ov.get('rankings',[]))} sector_breakdown={len(ov.get('sector_breakdown',[]))} recent={len(ov.get('recent_updates',[]))}")
    if ov.get('rankings'):
        cid = ov['rankings'][0]['company_id']
        get(f'/esg/companies/{cid}', f'/esg/companies/{{cid}}')

get('/esg/overview?year=2025', '/esg/overview?year=2025')
get('/esg/overview?sector_code=mining_metallurgy', '/esg/overview?sector=mining')

issues = get('/esg/issues?limit=10', '/esg/issues?limit=10')
get('/esg/issues?status=open&limit=10', '/esg/issues?status=open')
get('/esg/issues?severity=critical&limit=10', '/esg/issues?severity=critical')
