"""Smoke-test всех KPI endpoints после refactor'а 2026-05-25."""
import json, urllib.request, urllib.error

BASE = 'http://localhost:8000'
req = urllib.request.Request(
    f'{BASE}/auth/login',
    data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type':'application/json'},
)
tok = json.loads(urllib.request.urlopen(req).read())['access_token']
H = {'Authorization': 'Bearer '+tok}

def get(url, label):
    try:
        r = urllib.request.urlopen(urllib.request.Request(BASE+url, headers=H))
        body = r.read()
        n = len(body)
        try:
            d = json.loads(body)
            sample = (
                f"len={len(d)}" if isinstance(d, list)
                else f"keys={list(d.keys())[:5]}" if isinstance(d, dict)
                else str(d)[:60]
            )
        except Exception:
            sample = body[:80].decode(errors='replace')
        print(f"  ✓ {label:50s}  [{r.status}, {n}b] {sample}")
        return d if 'd' in dir() else None
    except urllib.error.HTTPError as e:
        print(f"  ✗ {label:50s}  [{e.code}] {e.read()[:160].decode(errors='replace')}")

print("KPI endpoints after 10-layer refactor:")
print()
get('/kpi/available-companies', 'GET /available-companies')
get('/kpi/summary/2026/q1', 'GET /summary/2026/q1')
get('/kpi/summary/2026/year', 'GET /summary/2026/year')
get('/kpi/summary/2025/annual', 'GET /summary/2025/annual (alias)')
get('/kpi/templates', 'GET /templates')

# Pick one company for company-scoped endpoints
cos = get('/kpi/available-companies', 'sample lookup')
if cos and len(cos) > 0:
    cid = cos[0]['company_id']
    co_name = cos[0]['company_name_ru']
    print(f"\nCompany-scoped (sample: {co_name}):")
    get(f'/kpi/{cid}/2026', f'GET /{co_name[:20]}/2026')
    get(f'/kpi/attention/{cid}/2026/q1', f'GET /attention/.../2026/q1')
    get(f'/kpi/comment/{cid}/2026/q1', f'GET /comment/.../2026/q1')
