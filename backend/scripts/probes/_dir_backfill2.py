import json, urllib.request
BASE='http://localhost:8000'
tok=json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/auth/login',data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),headers={'Content-Type':'application/json'})).read())['access_token']
H={'Authorization':'Bearer '+tok,'Content-Type':'application/json'}
def q(sql, dry_run=True):
    r=urllib.request.urlopen(urllib.request.Request(f'{BASE}/admin/db/query',data=json.dumps({'sql':sql,'dry_run':dry_run}).encode(),headers=H))
    return json.loads(r.read())

# Backfill tasks
res = q("""
UPDATE tasks t
SET direction_id = d.id
FROM directions d
WHERE t.direction_id IS NULL
  AND d.code = LOWER(NULLIF(t.extra->>'direction',''))
""", dry_run=False)
print(f"tasks updated: {res.get('row_count')}")

# Backfill projects
res = q("""
UPDATE projects p
SET direction_id = d.id
FROM directions d
WHERE p.direction_id IS NULL
  AND d.code = LOWER(NULLIF(p.extra->>'direction',''))
""", dry_run=False)
print(f"projects updated: {res.get('row_count')}")

# Verify
res = q("""
SELECT
  (SELECT COUNT(*) FROM tasks WHERE direction_id IS NULL AND NULLIF(extra->>'direction','') IS NOT NULL) AS tasks_remaining,
  (SELECT COUNT(*) FROM projects WHERE direction_id IS NULL AND NULLIF(extra->>'direction','') IS NOT NULL) AS projects_remaining
""")
print(f"Remaining unbacked (should be [0,0]): {res.get('rows', [])}")
