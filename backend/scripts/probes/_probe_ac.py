import json, urllib.request, urllib.error
BASE = 'http://localhost:8000'
tok = json.loads(urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/login',
    data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type':'application/json'},
)).read())['access_token']
H = {'Authorization': 'Bearer '+tok}
def get(url, label, auth=True):
    headers = H if auth else {}
    try:
        r = urllib.request.urlopen(urllib.request.Request(BASE+url, headers=headers))
        body = r.read()
        try:
            d = json.loads(body)
            s = f"keys={list(d.keys())[:5]}" if isinstance(d, dict) else f"list[{len(d)}]"
        except:
            s = body[:60].decode(errors='replace')
        print(f"  OK {label:50s} [{r.status}, {len(body):>7}b] {s}")
        return d
    except urllib.error.HTTPError as e:
        print(f"  ER {label:50s} [{e.code}] {e.read()[:160].decode(errors='replace')}")
get('/api-catalog/status', 'GET /api-catalog/status (public)', auth=False)
s = get('/api-catalog/summary', 'GET /api-catalog/summary')
if s:
    print(f"        title={s.get('title')} total={s.get('total_endpoints')} modules={len(s.get('modules',[]))}")
get('/api-catalog/scopes', 'GET /api-catalog/scopes')
get('/api-catalog/openapi.json', 'GET /api-catalog/openapi.json')
get('/api-catalog/openapi.enriched.json', 'GET /api-catalog/openapi.enriched.json')
get('/api-catalog/postman.json', 'GET /api-catalog/postman.json')
