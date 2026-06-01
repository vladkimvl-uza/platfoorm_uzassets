"""UI smoke test — имитирует вызовы фронта по основным юзер-сценариям."""
import json, urllib.request, urllib.error, time

BASE = 'http://localhost:8000'
tok = json.loads(urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/login',
    data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type':'application/json'},
)).read())['access_token']
H = {'Authorization': 'Bearer '+tok}

results = []
def hit(method, url, label, **kw):
    try:
        t0 = time.time()
        req = urllib.request.Request(BASE+url, headers=H, method=method, **kw)
        r = urllib.request.urlopen(req)
        body = r.read()
        ms = int((time.time()-t0)*1000)
        results.append((label, r.status, len(body), ms, None))
        print(f"  ✓ [{r.status}] {label:55s} {len(body):>8}b  {ms:>5}ms")
    except urllib.error.HTTPError as e:
        results.append((label, e.code, 0, 0, e.read()[:80].decode(errors='replace')))
        print(f"  ✗ [{e.code}] {label:55s} {results[-1][4]}")
    except Exception as e:
        results.append((label, 0, 0, 0, str(e)))
        print(f"  ✗ [ERR] {label:55s} {e}")

# Scenario 1: Open /workspace?tab=kpi → KPI tab
print("=== UI Scenario 1: workspace?tab=kpi (load company KPI editor) ===")
companies = hit('GET', '/kpi/available-companies', 'kpi.available-companies')
if results[-1][1] == 200:
    cos = json.loads(urllib.request.urlopen(urllib.request.Request(BASE+'/kpi/available-companies', headers=H)).read())
    if cos:
        cid = cos[0]['company_id']
        co_name = cos[0]['company_name_ru']
        print(f"     sample: {co_name}")
        hit('GET', f'/kpi/{cid}/2026', 'kpi.get_company_year')
        hit('GET', f'/kpi/attention/{cid}/2026/q1', 'kpi.attention')
        hit('GET', f'/kpi/comment/{cid}/2026/q1', 'kpi.comment')

# Scenario 2: Open /kpi → portfolio dashboard
print("\n=== UI Scenario 2: /kpi (portfolio summary) ===")
hit('GET', '/kpi/summary/2026/q1', 'kpi.summary.2026.q1')
hit('GET', '/kpi/summary/2026/q2', 'kpi.summary.2026.q2')
hit('GET', '/kpi/summary/2026/year', 'kpi.summary.2026.year')
hit('GET', '/kpi/summary/2025/annual', 'kpi.summary.2025.annual (alias)')

# Scenario 3: Procurement analysis
print("\n=== UI Scenario 3: /procurement/analysis ===")
hit('GET', '/procurement/aggregate', 'procurement.aggregate (all)')
hit('GET', '/procurement/aggregate?year=2026', 'procurement.aggregate.year=2026')

# Scenario 4: Tasks list
print("\n=== UI Scenario 4: /tasks ===")
hit('GET', '/boards', 'tasks.boards')
hit('GET', '/tasks?limit=50&offset=0', 'tasks.list.first50')
hit('GET', '/tasks?status=done&limit=10', 'tasks.list.done')
hit('GET', '/tasks?priority=high&limit=20', 'tasks.list.high-priority')
hit('GET', '/tasks?only_overdue=true&limit=20', 'tasks.list.overdue')

# Aggregate metrics
print("\n=== Summary ===")
ok = sum(1 for _,c,_,_,_ in results if c==200)
errs = [r for r in results if r[1] != 200]
total_ms = sum(r[3] for r in results)
print(f"  {ok}/{len(results)} OK · total {total_ms}ms")
for r in errs:
    print(f"  ERR: {r[0]} → {r[4][:80]}")
