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
            s = f"keys={list(d.keys())[:8]}" if isinstance(d, dict) else f"list[{len(d)}]"
        except:
            s = body[:60].decode(errors='replace')
        print(f"  OK {label:50s} [{r.status}, {len(body):>6}b] {s}")
        return d
    except urllib.error.HTTPError as e:
        print(f"  ER {label:50s} [{e.code}] {e.read()[:200].decode(errors='replace')}")

ed = get('/dashboard/executive/2026', 'GET /dashboard/executive/2026')
if ed:
    bm = ed.get('bottom_metrics') or {}
    print(f"        total_cos={ed.get('total_companies')} avg={bm.get('avg_completion')}%")
    print(f"        sectors={len(ed.get('sectors',[]))} ratings={'yes' if ed.get('ratings') else 'no'} exec_rows={len(ed.get('execution_chart',[]))}")
    print(f"        bp_tracker={'yes' if ed.get('bp_tracker') else 'no'} tax={'yes' if ed.get('tax_contribution') else 'no'} econ_eff={'yes' if ed.get('economic_effect') else 'no'}")
    print(f"        directions={len(ed.get('directions',[]))} governance={'yes' if ed.get('governance') else 'no'} standards={'yes' if ed.get('standards') else 'no'}")
get('/dashboard/executive/2025', '/dashboard/executive/2025')
get('/dashboard/executive/2026?sectors=mining&sectors=oilgas', '/dashboard/executive/2026?sectors=mining,oilgas')
get('/dashboard/executive/2026?bp_metric=profit', '/dashboard/executive/2026?bp_metric=profit')
