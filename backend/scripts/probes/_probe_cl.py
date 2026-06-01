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
        print(f"  ER {label:50s} [{e.code}] {e.read()[:200].decode(errors='replace')}")
get('/field-definitions', 'GET /field-definitions')
get('/library-tabs', 'GET /library-tabs')
get('/library-views', 'GET /library-views')
ll = get('/library/companies?limit=5', 'GET /library/companies?limit=5')
if ll and ll.get('items'):
    print(f"        total={ll.get('total')} items={len(ll['items'])} columns={len(ll.get('columns',[]))}")
    cid = ll['items'][0]['id']
    get(f'/library/companies/{cid}', '/library/companies/{cid}')
    get(f'/library/companies/{cid}/activity?limit=5', '/library/companies/{cid}/activity')
