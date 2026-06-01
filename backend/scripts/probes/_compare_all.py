"""For each company: compare what Workspace KPI vs Dashboard sector grid count."""
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


# Compare per-company numbers between two data sources
print(f"{'company':10s}  {'ws_t_done/total':>15s}  {'db_t_done/total':>15s}  {'ws_p_done/total':>15s}  {'db_p_done/total':>15s}  {'mismatch':10s}")
print("─" * 90)

res = q("""
WITH
ws_tasks AS (
  SELECT c.code,
         COUNT(*) AS total,
         COUNT(*) FILTER (WHERE t.status='done') AS done
  FROM companies c
  LEFT JOIN tasks t ON t.company_id = c.id
    AND t.is_archived=false AND t.portfolio_year=2026
  GROUP BY c.code
),
db_tasks AS (
  SELECT c.code,
         COUNT(t.id) AS total,
         COUNT(t.id) FILTER (WHERE t.status='done') AS done
  FROM companies c
  LEFT JOIN boards b ON b.company_id = c.id
  LEFT JOIN tasks t ON t.board_id = b.id
    AND t.is_archived=false AND t.portfolio_year=2026
  GROUP BY c.code
),
ws_proj AS (
  SELECT c.code,
         COUNT(*) AS total,
         COUNT(*) FILTER (WHERE p.status='done') AS done
  FROM companies c
  LEFT JOIN projects p ON p.company_id = c.id
    AND p.is_archived=false AND p.portfolio_year=2026
  GROUP BY c.code
),
db_proj AS (
  SELECT c.code,
         COUNT(p.id) AS total,
         COUNT(p.id) FILTER (WHERE p.status='done') AS done
  FROM companies c
  LEFT JOIN boards b ON b.company_id = c.id
  LEFT JOIN projects p ON p.board_id = b.id
    AND p.is_archived=false AND p.portfolio_year=2026
  GROUP BY c.code
)
SELECT ws_tasks.code,
       ws_tasks.done || '/' || ws_tasks.total AS ws_t,
       db_tasks.done || '/' || db_tasks.total AS db_t,
       ws_proj.done || '/' || ws_proj.total AS ws_p,
       db_proj.done || '/' || db_proj.total AS db_p,
       CASE WHEN ws_tasks.total != db_tasks.total OR ws_proj.total != db_proj.total THEN 'YES' ELSE '-' END AS mismatch
FROM ws_tasks
JOIN db_tasks USING (code)
JOIN ws_proj USING (code)
JOIN db_proj USING (code)
WHERE ws_tasks.total > 0 OR ws_proj.total > 0
ORDER BY mismatch DESC, ws_tasks.code
""")

for row in res['rows']:
    code, ws_t, db_t, ws_p, db_p, mis = row
    flag = '⚠️ ' if mis == 'YES' else '  '
    print(f"{flag}{code:8s}  {ws_t:>15s}  {db_t:>15s}  {ws_p:>15s}  {db_p:>15s}  {mis}")
