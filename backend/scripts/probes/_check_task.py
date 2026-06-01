import json, urllib.request
BASE = 'http://localhost:8000'
tok = json.loads(urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/login',
    data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type':'application/json'},
)).read())['access_token']
H = {'Authorization': 'Bearer '+tok, 'Content-Type':'application/json'}

TASK_ID = '55ce9403-4d1c-4dc0-95a7-59bb9577710c'

# 1. Get current task
r = urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/tasks/{TASK_ID}', headers=H,
))
task = json.loads(r.read())
print("=== Current task ===")
print(f"  status={task.get('status')!r}")
print(f"  progress_percent={task.get('progress_percent')!r}")
print(f"  title={task.get('title')!r}")
print(f"  updated_at={task.get('updated_at')!r}")

# 2. Recent task_history via /admin/db/query
r = urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/admin/db/query',
    data=json.dumps({
        'sql': f"SELECT created_at, action, field_name, old_value, new_value "
               f"FROM task_history WHERE task_id = '{TASK_ID}' "
               f"ORDER BY created_at DESC LIMIT 10",
        'dry_run': True,
    }).encode(),
    headers=H,
))
hist = json.loads(r.read())
print()
print("=== Recent task_history (last 10) ===")
for row in hist.get('rows', []):
    print(f"  {row[0][:19]}  {row[1]:18s}  {(row[2] or '-'):20s}  '{row[3] or ''}' → '{row[4] or ''}'")
