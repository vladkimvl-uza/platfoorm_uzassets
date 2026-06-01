import json, urllib.request
BASE='http://localhost:8000'
tok=json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/auth/login',data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),headers={'Content-Type':'application/json'})).read())['access_token']
H={'Authorization':'Bearer '+tok,'Content-Type':'application/json'}
def q(sql):
    r=urllib.request.urlopen(urllib.request.Request(f'{BASE}/admin/db/query',data=json.dumps({'sql':sql,'dry_run':True}).encode(),headers=H))
    return json.loads(r.read())

# 1. board_id coverage for tasks
print("Tasks: with/without board_id (filter portfolio_year=2026):")
print("  cols:", q("SELECT 1 AS dummy WHERE FALSE").get('columns'))
res = q("""
SELECT
  COUNT(*) AS total_y26,
  COUNT(board_id) AS with_board,
  COUNT(*) FILTER (WHERE board_id IS NULL) AS no_board
FROM tasks
WHERE portfolio_year = 2026
""")
print(f"  {res.get('rows', [])}")

print()
print("Projects: with/without board_id (filter portfolio_year=2026):")
res = q("""
SELECT
  COUNT(*) AS total_y26,
  COUNT(board_id) AS with_board,
  COUNT(*) FILTER (WHERE board_id IS NULL) AS no_board
FROM projects
WHERE portfolio_year = 2026
""")
print(f"  {res.get('rows', [])}")

print()
print("Tasks where extra.direction matches a directions.code but direction_id is NULL:")
res = q("""
SELECT t.extra->>'direction' AS extra_dir, COUNT(*) AS n
FROM tasks t
LEFT JOIN directions d ON d.code = LOWER(t.extra->>'direction')
WHERE t.direction_id IS NULL
  AND NULLIF(t.extra->>'direction','') IS NOT NULL
  AND t.portfolio_year = 2026
GROUP BY t.extra->>'direction'
ORDER BY n DESC LIMIT 20
""")
for row in res.get('rows', []): print(f"  '{row[0]}': {row[1]}")
