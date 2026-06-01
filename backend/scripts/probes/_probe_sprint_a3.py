"""Smoke-test KPI + Procurement + Tasks after refactor."""
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
        print(f"  ✓ {label:55s} [{r.status}, {len(body):>7}b] {s}")
        return d if isinstance(d, (dict, list)) else None
    except urllib.error.HTTPError as e:
        print(f"  ✗ {label:55s} [{e.code}] {e.read()[:160].decode(errors='replace')}")

print("KPI:")
get('/kpi/available-companies', '/kpi/available-companies')
ks = get('/kpi/summary/2026/q1', '/kpi/summary/2026/q1')
if ks: print(f"        overall={ks.get('overall'):.1f}, co={ks.get('co_count')}")

print("\nProcurement:")
pa = get('/procurement/aggregate', '/procurement/aggregate')
if pa:
    k = pa.get('kpis', {})
    print(f"        cos={k.get('total_companies')} closures={k.get('total_closures')} above={k.get('above_market_pct'):.1f}%")

print("\nTasks:")
bs = get('/boards', '/boards')
if bs: print(f"        boards total={bs.get('total')}")
ts = get('/tasks?limit=5', '/tasks?limit=5')
if ts: print(f"        tasks total={ts.get('total')}, sample={len(ts.get('items',[]))}")

# Sample one board for kanban
if bs and bs.get('items'):
    bid = bs['items'][0]['id']
    get(f'/boards/{bid}/kanban', f'/boards/{{bid}}/kanban')
    get(f'/boards/{bid}', f'/boards/{{bid}}')

# Sample one task
if ts and ts.get('items'):
    tid = ts['items'][0]['id']
    get(f'/tasks/{tid}', f'/tasks/{{tid}}')
