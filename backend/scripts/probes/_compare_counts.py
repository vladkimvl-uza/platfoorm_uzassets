"""Compare per-company task/project counts across data sources."""
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


# Узметкомбинат
print("=" * 70)
print("Узметкомбинат — какие данные в БД")
print("=" * 70)

co = q("SELECT id::text, code, name_short FROM companies WHERE LOWER(code)='umk'")['rows'][0]
print(f"Company: {co[1]} ({co[0]}) name_short='{co[2]}'")
cid = co[0]

print("\n— tasks table (separate is_project flag):")
res = q(f"""
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE is_project = true) AS as_project,
  COUNT(*) FILTER (WHERE is_project = false OR is_project IS NULL) AS as_task,
  COUNT(*) FILTER (WHERE is_archived = true) AS archived,
  COUNT(*) FILTER (WHERE board_id IS NOT NULL) AS with_board,
  COUNT(*) FILTER (WHERE status = 'done') AS done,
  COUNT(*) FILTER (WHERE portfolio_year = 2026) AS y2026
FROM tasks
WHERE company_id = '{cid}'
""")
cols = res['columns']
row = res['rows'][0]
for c, v in zip(cols, row):
    print(f"  {c:20s} {v}")

print("\n— projects table:")
res = q(f"""
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE is_archived = true) AS archived,
  COUNT(*) FILTER (WHERE board_id IS NOT NULL) AS with_board,
  COUNT(*) FILTER (WHERE status = 'done') AS done,
  COUNT(*) FILTER (WHERE portfolio_year = 2026) AS y2026
FROM projects
WHERE company_id = '{cid}'
""")
cols = res['columns']
row = res['rows'][0]
for c, v in zip(cols, row):
    print(f"  {c:20s} {v}")

print("\n— what dashboard `_bucket_by_company` sees (board_id-based, FY2026):")
res = q(f"""
SELECT 'tasks' as kind, COUNT(*) AS total, COUNT(*) FILTER (WHERE status='done') AS done
FROM tasks t
WHERE t.is_archived = false
  AND t.portfolio_year = 2026
  AND t.board_id IS NOT NULL
  AND t.board_id IN (SELECT id FROM boards WHERE company_id = '{cid}')
UNION ALL
SELECT 'projects', COUNT(*), COUNT(*) FILTER (WHERE status='done')
FROM projects p
WHERE p.is_archived = false
  AND p.portfolio_year = 2026
  AND p.board_id IS NOT NULL
  AND p.board_id IN (SELECT id FROM boards WHERE company_id = '{cid}')
""")
for row in res['rows']:
    print(f"  {row[0]:10s} {row[2]}/{row[1]}")

print("\n— what CompanyWorkspace sees (company_id-based, !is_project, FY2026):")
res = q(f"""
SELECT 'tasks (workspace filter)' as kind, COUNT(*), COUNT(*) FILTER (WHERE status='done')
FROM tasks
WHERE company_id = '{cid}'
  AND is_archived = false
  AND portfolio_year = 2026
  AND (is_project = false OR is_project IS NULL)
UNION ALL
SELECT 'projects (workspace)', COUNT(*), COUNT(*) FILTER (WHERE status='done')
FROM projects
WHERE company_id = '{cid}'
  AND is_archived = false
  AND portfolio_year = 2026
""")
for row in res['rows']:
    print(f"  {row[0]:30s} {row[2]}/{row[1]}")

print("\n— tasks WITHOUT board_id (would be missed by dashboard):")
res = q(f"""
SELECT id::text, title, board_id IS NULL AS no_board, status
FROM tasks
WHERE company_id = '{cid}' AND is_archived=false AND portfolio_year=2026
  AND board_id IS NULL
LIMIT 5
""")
for row in res['rows']:
    print(f"  {row}")

print("\n— projects WITHOUT board_id (would be missed by dashboard):")
res = q(f"""
SELECT id::text, title, board_id IS NULL, status
FROM projects
WHERE company_id = '{cid}' AND is_archived=false AND portfolio_year=2026
  AND board_id IS NULL
LIMIT 5
""")
for row in res['rows']:
    print(f"  {row}")
