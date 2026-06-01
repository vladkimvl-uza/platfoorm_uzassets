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
            s = f"list[{len(d)}]" if isinstance(d, list) else f"keys={list(d.keys())[:5]}"
        except:
            s = body[:60].decode(errors='replace')
        print(f"  OK {label:50s} [{r.status}, {len(body):>6}b] {s}")
        return d
    except urllib.error.HTTPError as e:
        print(f"  ER {label:50s} [{e.code}] {e.read()[:160].decode(errors='replace')}")
cl = get('/companies-admin/v2/list', 'GET /companies-admin/v2/list')
if cl:
    print(f"        companies={len(cl)}")
    if cl:
        get(f'/companies-admin/v2/{cl[0]["code"]}', '/companies-admin/v2/{code}')
        get(f'/companies-admin/v2/{cl[0]["code"]}/year-overrides', '/companies-admin/v2/{code}/year-overrides')
get('/companies-admin/v2/list?only_active=true', '/companies-admin/v2/list?only_active=true')
get('/companies-admin/v2/list?search=Navoi', '/companies-admin/v2/list?search=Navoi')
get('/companies-admin/v2/tree/hierarchy', '/companies-admin/v2/tree/hierarchy')
get('/sectors-admin/v2/list', 'GET /sectors-admin/v2/list')
