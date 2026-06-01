"""Smoke-test Notes module after refactor."""
import json, urllib.request, urllib.error

BASE = 'http://localhost:8000'
tok = json.loads(urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/login',
    data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type':'application/json'},
)).read())['access_token']
H = {'Authorization': 'Bearer '+tok}

def hit(method, url, label, body=None):
    try:
        req = urllib.request.Request(BASE+url, headers={**H, 'Content-Type':'application/json'}, method=method,
                                     data=json.dumps(body).encode() if body else None)
        r = urllib.request.urlopen(req)
        rb = r.read()
        try:
            d = json.loads(rb)
            if isinstance(d, list):
                s = f"list[{len(d)}]"
            elif isinstance(d, dict):
                s = f"keys={list(d.keys())[:6]}"
            else:
                s = str(d)[:60]
        except Exception:
            s = rb[:80].decode(errors='replace')
        print(f"  OK {label:55s} [{r.status}, {len(rb):>7}b] {s}")
        return d if isinstance(d, (dict, list)) else None
    except urllib.error.HTTPError as e:
        print(f"  ER {label:55s} [{e.code}] {e.read()[:160].decode(errors='replace')}")

print("Notes:")
nl = hit('GET', '/notes?limit=5', 'GET /notes')
if nl:
    print(f"        total={nl.get('total')}, items={len(nl.get('items',[]))}")
    print(f"        tags={[t['tag'] for t in nl.get('tag_counts',[])[:5]]}")
hit('GET', '/notes/tags?limit=10', 'GET /notes/tags')
hit('GET', '/notes/by-entity?entity_type=task&entity_key=xxx', 'GET /notes/by-entity (key)')

# create + update + delete cycle
created = hit('POST', '/notes', 'POST /notes (create)', body={
    'title': 'refactor probe', 'body': 'auto-test', 'kind': 'observation',
    'tags': ['probe'], 'is_pinned': False,
})
if created and created.get('id'):
    nid = created['id']
    hit('PATCH', f'/notes/{nid}', 'PATCH /notes/{id}', body={'title': 'refactor probe (updated)'})
    hit('DELETE', f'/notes/{nid}', 'DELETE /notes/{id}')
