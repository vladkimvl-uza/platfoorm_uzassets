"""Smoke-test Governance module after refactor."""
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

print("Governance:")
ov = get('/governance/overview', '/governance/overview')
if ov:
    print(f"        total_cos={ov['kpis']['total_companies']} with_data={ov['kpis'].get('companies_with_data')}")
    print(f"        avg_indep={ov['kpis'].get('avg_independent_pct')} avg_women={ov['kpis'].get('avg_women_pct')}")
    print(f"        rankings={len(ov.get('rankings',[]))} years={ov.get('available_years')}")
    if ov.get('rankings'):
        rk = ov['rankings'][0]
        print(f"        #1: {rk.get('company_abbr')} score={rk.get('governance_score')} ({rk.get('governance_score_1200')}/1200)")
        cid = rk['company_id']
        get(f'/governance/companies/{cid}', f'/governance/companies/{{cid}}')
        get(f'/governance/companies/{cid}/members', f'/governance/companies/{{cid}}/members')
get('/governance/overview?year=2025', '/governance/overview?year=2025')
get('/governance/overview?sector_code=mining', '/governance/overview?sector_code=mining')
