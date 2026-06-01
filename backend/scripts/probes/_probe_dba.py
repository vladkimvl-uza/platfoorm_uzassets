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
            s = (f"keys={list(d.keys())[:4]}" if isinstance(d, dict)
                 else f"list[{len(d)}]")
        except:
            s = body[:60].decode(errors='replace')
        print(f"  OK {label:50s} [{r.status}, {len(body):>6}b] {s}")
    except urllib.error.HTTPError as e:
        print(f"  {('OK' if e.code in (403,) else 'ER')} {label:50s} [{e.code}] {e.read()[:180].decode(errors='replace')}")
def post(url, body, label):
    try:
        r = urllib.request.urlopen(urllib.request.Request(
            BASE+url,
            data=json.dumps(body).encode(),
            headers={'Content-Type':'application/json', **H},
        ))
        b = r.read()
        try:
            d = json.loads(b)
            s = f"keys={list(d.keys())[:5]}"
        except:
            s = b[:60].decode(errors='replace')
        print(f"  OK {label:50s} [{r.status}, {len(b)}b] {s}")
    except urllib.error.HTTPError as e:
        print(f"  ER {label:50s} [{e.code}] {e.read()[:160].decode(errors='replace')}")

get('/admin/db/schema', 'GET /admin/db/schema')
post('/admin/db/query', {'sql':'SELECT 1 AS test','dry_run':False},
     'POST /admin/db/query SELECT 1')
post('/admin/db/query', {'sql':'SELECT count(*) FROM users','dry_run':False},
     'POST /admin/db/query count users')
get('/admin/db/table/companies/rows?limit=2', 'GET /table/companies/rows')
