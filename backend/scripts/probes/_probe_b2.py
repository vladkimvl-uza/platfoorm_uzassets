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
        print(f"  OK {label:50s} [{r.status}, {len(body):>5}b] {s}")
    except urllib.error.HTTPError as e:
        print(f"  {('OK' if e.code in (403,) else 'ER')} {label:50s} [{e.code}] {e.read()[:160].decode(errors='replace')}")
get('/directions', 'GET /directions')
get('/elasticity/constants', 'GET /elasticity/constants')
get('/webhooks/events', 'GET /webhooks/events')
get('/webhooks/stats', 'GET /webhooks/stats')
get('/admin/audit/overview?hours=24', 'GET /admin/audit/overview')
get('/admin/audit/stats?hours=24', 'GET /admin/audit/stats')
