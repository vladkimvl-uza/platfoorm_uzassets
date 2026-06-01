"""Smoke-test Projects module after refactor."""
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
            if isinstance(d, list):
                s = f"list[{len(d)}]"
            elif isinstance(d, dict):
                s = f"keys={list(d.keys())[:6]}"
            else:
                s = str(d)[:60]
        except Exception:
            s = body[:80].decode(errors='replace')
        print(f"  OK {label:55s} [{r.status}, {len(body):>7}b] {s}")
        return d if isinstance(d, (dict, list)) else None
    except urllib.error.HTTPError as e:
        print(f"  ER {label:55s} [{e.code}] {e.read()[:160].decode(errors='replace')}")

print("Projects:")
plist = get('/projects?limit=5', '/projects?limit=5')
if plist:
    print(f"        total={plist.get('total')}, items={len(plist.get('items',[]))}")
    print(f"        by_status={plist.get('by_status')}, years={plist.get('available_years')}")
    if plist.get('items'):
        pid = plist['items'][0]['id']
        get(f'/projects/{pid}', f'/projects/{{pid}}')
        get(f'/projects/{pid}/tasks', f'/projects/{{pid}}/tasks')

# Filters
get('/projects?limit=10&status=active', '/projects?status=active')
get('/projects?limit=10&priority=high', '/projects?priority=high')
get('/projects?limit=10&only_overdue=true', '/projects?only_overdue=true')
get('/projects?limit=10&has_economic_effect=true', '/projects?has_economic_effect=true')
