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
            s = f"keys={list(d.keys())[:6]}" if isinstance(d, dict) else f"list[{len(d)}]"
        except:
            s = body[:60].decode(errors='replace')
        print(f"  OK {label:50s} [{r.status}, {len(body):>6}b] {s}")
        return d
    except urllib.error.HTTPError as e:
        print(f"  ER {label:50s} [{e.code}] {e.read()[:200].decode(errors='replace')}")
sh = get('/dashboard/shareholder', 'GET /dashboard/shareholder')
if sh:
    k = sh.get('kpis',{})
    print(f"        kpis: proj={k.get('projects')} done_proj={k.get('done_proj')} tasks={k.get('tasks')} done_tasks={k.get('done_tasks')}")
    print(f"        statuses={len(sh.get('statuses',[]))} cos_sec={len(sh.get('companies_by_sector',[]))} dirs={len(sh.get('directions',[]))} rings={len(sh.get('ratings',{}).get('rings',[]))}")
    print(f"        completion: companies={len(sh.get('completion',{}).get('by_company',[]))} avg={sh.get('completion',{}).get('portfolio_avg')}%")
get('/dashboard/shareholder?year=2026', 'GET /dashboard/shareholder?year=2026')
kd = get('/dashboard/kpi-drill?bucket=overdue&entity=tasks', 'GET /dashboard/kpi-drill (overdue tasks)')
if kd:
    sm = kd.get('summary',{})
    print(f"        bucket=overdue: tasks={sm.get('tasks_count')} cos={sm.get('companies_count')} extra={sm.get('extra_value')} ({sm.get('extra_label')})")
get('/dashboard/kpi-drill?bucket=done&entity=projects', '/dashboard/kpi-drill (done proj)')
get('/dashboard/kpi-drill?bucket=active&entity=tasks&year=2026', '/dashboard/kpi-drill (active 2026)')
# pick a company
cos = json.loads(urllib.request.urlopen(urllib.request.Request(BASE+'/companies?limit=1', headers=H)).read())
if cos.get('items'):
    cc = cos['items'][0]['code']
    cd = get(f'/dashboard/company-drill?company_code={cc}', '/dashboard/company-drill')
    if cd:
        sm = cd.get('summary',{})
        print(f"        company={cc}: progress={sm.get('progress_pct')}% tasks={sm.get('tasks_total')} done={sm.get('tasks_done')}")
