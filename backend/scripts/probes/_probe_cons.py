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
        print(f"  ER {label:50s} [{e.code}] {e.read()[:160].decode(errors='replace')}")

cl = get('/consultants', 'GET /consultants')
if cl and cl.get('consultants'):
    print(f"        consultants={len(cl['consultants'])}")
get('/consultants?include_inactive=true', 'GET /consultants?include_inactive')
ov = get('/consultants/overview', 'GET /consultants/overview')
if ov:
    kp = ov.get('kpis', {})
    print(f"        kpis: tasks_covered={kp.get('tasks_covered')} cos_covered={kp.get('companies_covered')} active={kp.get('consultants_active')} avg={kp.get('avg_completion_pct')}%")
    print(f"        consultants={len(ov.get('consultants',[]))} heatmap_rows={len(ov.get('heatmap',{}).get('rows',[]))} dirs={len(ov.get('dirs',[]))} projects={len(ov.get('projects',[]))}")
get('/consultants/overview?year=2026', '/consultants/overview?year=2026')
# Try by-company with sample co
import json
co_resp = json.loads(urllib.request.urlopen(urllib.request.Request(BASE+'/companies?limit=1', headers=H)).read())
if co_resp.get('items'):
    cid = co_resp['items'][0]['id']
    get(f'/consultants/by-company/{cid}', '/consultants/by-company/{co}')
