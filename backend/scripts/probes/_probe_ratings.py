"""Smoke-test Ratings module after refactor."""
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

print("Ratings:")
rl = get('/ratings?limit=10', '/ratings?limit=10')
if rl:
    print(f"        total={rl['total']}, credit={rl.get('credit_count')}, esg={rl.get('esg_count')}")
    print(f"        by_agency={rl.get('by_agency')}")
    if rl.get('items'):
        cc = rl['items'][0].get('company_code')
        if cc:
            get(f'/companies/{cc}/ratings', f'/companies/{{cc}}/ratings')
get('/ratings?agency=Fitch', '/ratings?agency=Fitch')
get('/ratings?is_esg=true', '/ratings?is_esg=true')
get('/ratings?is_esg=false', '/ratings?is_esg=false')
get('/ratings?sort_by=agency&sort_dir=asc&limit=5', '/ratings?sort=agency')
