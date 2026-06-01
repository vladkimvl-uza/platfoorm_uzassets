import json, urllib.request
BASE='http://localhost:8000'
tok=json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/auth/login',data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),headers={'Content-Type':'application/json'})).read())['access_token']
H={'Authorization':'Bearer '+tok,'Content-Type':'application/json'}
def q(sql):
    r=urllib.request.urlopen(urllib.request.Request(f'{BASE}/admin/db/query',data=json.dumps({'sql':sql,'dry_run':True}).encode(),headers=H))
    return json.loads(r.read())

print("Distribution of direction sources in tasks:")
res = q("""
SELECT
  COUNT(*) AS total,
  COUNT(direction_id) AS with_dir_id,
  COUNT(NULLIF(extra->>'direction','')) AS with_extra_dir,
  COUNT(*) FILTER (WHERE direction_id IS NULL AND COALESCE(extra->>'direction','')='') AS no_direction
FROM tasks
""")
for row in res.get('rows', []): print(f"  {row}")

print()
print("Distribution in projects:")
res = q("""
SELECT
  COUNT(*) AS total,
  COUNT(direction_id) AS with_dir_id,
  COUNT(NULLIF(extra->>'direction','')) AS with_extra_dir,
  COUNT(*) FILTER (WHERE direction_id IS NULL AND COALESCE(extra->>'direction','')='') AS no_direction
FROM projects
""")
for row in res.get('rows', []): print(f"  {row}")
