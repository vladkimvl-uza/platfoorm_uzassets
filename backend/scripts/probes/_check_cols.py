import json
import urllib.request

BASE = 'http://localhost:8000'
tok = json.loads(urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/login',
    data=json.dumps({'login': 'test@uz-assets.uz', 'password': 'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type': 'application/json'},
)).read())['access_token']
H = {'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'}


def q(sql):
    r = urllib.request.urlopen(urllib.request.Request(
        f'{BASE}/admin/db/query',
        data=json.dumps({'sql': sql, 'dry_run': True}).encode(), headers=H,
    ))
    return json.loads(r.read())


print("tasks columns:")
for r in q("SELECT column_name FROM information_schema.columns WHERE table_name='tasks' ORDER BY ordinal_position")['rows']:
    print(f"  {r[0]}")
print()
print("projects columns:")
for r in q("SELECT column_name FROM information_schema.columns WHERE table_name='projects' ORDER BY ordinal_position")['rows']:
    print(f"  {r[0]}")
