import json, urllib.request, urllib.error
BASE = 'http://localhost:8000'
tok = json.loads(urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/login',
    data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type':'application/json'},
)).read())['access_token']
H = {'Authorization': 'Bearer '+tok, 'Content-Type':'application/json'}

def q(sql):
    try:
        r = urllib.request.urlopen(urllib.request.Request(
            f'{BASE}/admin/db/query',
            data=json.dumps({'sql':sql, 'dry_run':False}).encode(),
            headers=H,
        ))
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'_error': e.code, '_body': e.read()[:200].decode(errors='replace')}

print("ANALYZE (public schema):")
r = q("ANALYZE")
if '_error' in r:
    print(f"  ERROR {r['_error']}: {r['_body']}")
else:
    print(f"  OK · {r.get('duration_ms')}ms · command={r.get('command')}")

print()
print("Try VACUUM ANALYZE (expect to fail in txn):")
r = q("VACUUM ANALYZE")
if '_error' in r:
    print(f"  EXPECTED FAIL {r['_error']}: {r['_body'][:160]}")
else:
    print(f"  Unexpectedly OK · {r.get('duration_ms')}ms")
