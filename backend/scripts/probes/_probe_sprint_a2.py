"""Smoke-test KPI + Procurement endpoints после refactor'а 2026-05-25."""
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
                sample = f"len={len(d)}"
            elif isinstance(d, dict):
                sample = f"keys={list(d.keys())[:6]}"
            else:
                sample = str(d)[:60]
        except Exception:
            sample = body[:80].decode(errors='replace')
        print(f"  ✓ {label:55s} [{r.status}, {len(body):>7}b] {sample}")
        return d if isinstance(d, (dict, list)) else None
    except urllib.error.HTTPError as e:
        print(f"  ✗ {label:55s} [{e.code}] {e.read()[:200].decode(errors='replace')}")
        return None

print("KPI endpoints:")
get('/kpi/available-companies', 'GET /kpi/available-companies')
ks = get('/kpi/summary/2026/q1', 'GET /kpi/summary/2026/q1')
if ks and 'overall' in ks:
    print(f"        ↳ overall={ks.get('overall')}, co_count={ks.get('co_count')}")

print("\nProcurement endpoints:")
pa = get('/procurement/aggregate', 'GET /procurement/aggregate (no filter)')
if pa:
    k = pa.get('kpis', {})
    print(f"        ↳ total_companies={k.get('total_companies')}, total_closures={k.get('total_closures')}, "
          f"above_market_pct={k.get('above_market_pct'):.1f}%")
    print(f"        ↳ rating len={len(pa.get('rating',[]))}, purchases len={len(pa.get('purchases',[]))}")

get('/procurement/aggregate?year=2026', 'GET /procurement/aggregate?year=2026')

# Sample one closure for editing roundtrip (skip mutation, just check shape)
purchases = pa.get('purchases', []) if pa else []
if purchases:
    cid = purchases[0]['id']
    print(f"\n  sample closure id: {cid}")
