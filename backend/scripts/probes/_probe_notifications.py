"""Smoke-test Notifications module after refactor."""
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
        req = urllib.request.Request(BASE+url, headers={**H, 'Content-Type':'application/json'},
                                     method=method,
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

print("Notifications:")
fd = hit('GET', '/notifications/feed', 'GET /notifications/feed')
if fd:
    print(f"        total={fd.get('total')} unread={fd.get('unread_count')}")
uc = hit('GET', '/notifications/unread-count', 'GET /notifications/unread-count')
if uc:
    print(f"        unread={uc.get('total')}")
hit('GET', '/notifications/feed?unread_only=true', 'GET /notifications/feed?unread_only=true')
prefs = hit('GET', '/notifications/preferences', 'GET /notifications/preferences')
types = hit('GET', '/notifications/types', 'GET /notifications/types')
if types:
    print(f"        types={len(types.get('types',[]))}, categories={types.get('categories')}")

# Self-test send (creates a notification, then list, then mark-read, then archive)
test = hit('POST', '/notifications/test', 'POST /notifications/test')
if test and test.get('id'):
    nid = test['id']
    hit('GET', f'/notifications/{nid}', 'GET /notifications/{id}')
    hit('POST', f'/notifications/{nid}/read', 'POST /notifications/{id}/read')
    hit('POST', f'/notifications/{nid}/archive', 'POST /notifications/{id}/archive')
