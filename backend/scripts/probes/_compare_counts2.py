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


cid = '931facee-279b-4053-89e5-596a770a8e39'  # UMK
print("Узметкомбинат (UMK)")
print("=" * 60)

print("\n— tasks (filtered as CompanyWorkspace does: company_id + FY2026 + !archived):")
res = q(f"""
SELECT COUNT(*) AS total,
       COUNT(*) FILTER (WHERE status='done') AS done,
       COUNT(board_id) AS with_board,
       COUNT(*) FILTER (WHERE board_id IS NULL) AS no_board
FROM tasks
WHERE company_id='{cid}' AND is_archived=false AND portfolio_year=2026
""")
for c, v in zip(res['columns'], res['rows'][0]):
    print(f"    {c:15s} {v}")

print("\n— projects (CompanyWorkspace filters):")
res = q(f"""
SELECT COUNT(*) AS total,
       COUNT(*) FILTER (WHERE status='done') AS done,
       COUNT(board_id) AS with_board,
       COUNT(*) FILTER (WHERE board_id IS NULL) AS no_board
FROM projects
WHERE company_id='{cid}' AND is_archived=false AND portfolio_year=2026
""")
for c, v in zip(res['columns'], res['rows'][0]):
    print(f"    {c:15s} {v}")

print("\n— Dashboard (_bucket_by_company uses board_to_company map):")
print("    only tasks where board belongs to UMK's boards")
res = q(f"""
WITH umk_boards AS (
  SELECT id FROM boards WHERE company_id='{cid}'
)
SELECT 'tasks' AS kind,
       COUNT(*) AS total,
       COUNT(*) FILTER (WHERE status='done') AS done
FROM tasks t
WHERE t.is_archived=false AND t.portfolio_year=2026
  AND t.board_id IS NOT NULL
  AND t.board_id IN (SELECT id FROM umk_boards)
UNION ALL
SELECT 'projects',
       COUNT(*),
       COUNT(*) FILTER (WHERE status='done')
FROM projects p
WHERE p.is_archived=false AND p.portfolio_year=2026
  AND p.board_id IS NOT NULL
  AND p.board_id IN (SELECT id FROM umk_boards)
""")
for row in res['rows']:
    print(f"    {row[0]:10s} {row[2]}/{row[1]}")

print("\n— Tasks WITH board_id but board belongs to OTHER company (data mismatch):")
res = q(f"""
SELECT t.id::text, t.title, t.status, b.company_id::text AS board_co
FROM tasks t
JOIN boards b ON b.id = t.board_id
WHERE t.company_id='{cid}' AND b.company_id != '{cid}'
  AND t.is_archived=false AND t.portfolio_year=2026
LIMIT 10
""")
print(f"  Count: {len(res.get('rows', []))}")
for row in res['rows'][:5]:
    print(f"    {row[0][:8]} status={row[2]} board_co={row[3][:8]} {row[1][:50]}")

print("\n— Projects WITH board_id but board belongs to OTHER company:")
res = q(f"""
SELECT p.id::text, p.title, p.status, b.company_id::text AS board_co
FROM projects p
JOIN boards b ON b.id = p.board_id
WHERE p.company_id='{cid}' AND b.company_id != '{cid}'
  AND p.is_archived=false AND p.portfolio_year=2026
LIMIT 10
""")
print(f"  Count: {len(res.get('rows', []))}")
for row in res['rows'][:5]:
    print(f"    {row[0][:8]} status={row[2]} board_co={row[3][:8]} {row[1][:50]}")

print("\n— Tasks where board.company_id matches UMK but task.company_id is DIFFERENT (reverse mismatch):")
res = q(f"""
SELECT t.id::text, t.title, t.company_id::text, t.status
FROM tasks t
JOIN boards b ON b.id = t.board_id
WHERE b.company_id='{cid}' AND (t.company_id != '{cid}' OR t.company_id IS NULL)
  AND t.is_archived=false AND t.portfolio_year=2026
LIMIT 5
""")
print(f"  Count: {len(res.get('rows', []))}")
for row in res['rows'][:5]:
    print(f"    {row[0][:8]} task_co={row[2][:8] if row[2] else 'NULL'} status={row[3]} {row[1][:50]}")
