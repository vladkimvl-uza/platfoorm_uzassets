import json, urllib.request, urllib.error
BASE = 'http://localhost:8000'
tok = json.loads(urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/login',
    data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type':'application/json'},
)).read())['access_token']
H = {'Authorization': 'Bearer '+tok, 'Content-Type':'application/json'}

r = urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/admin/db/query',
    data=json.dumps({'sql':"""
SELECT s.relname AS tbl,
       s.n_live_tup AS live,
       s.n_dead_tup AS dead,
       ROUND(100.0 * s.n_dead_tup / NULLIF(s.n_live_tup + s.n_dead_tup, 0), 1) AS dead_pct
FROM pg_stat_user_tables s
WHERE s.schemaname = 'public' AND s.n_dead_tup > 0
ORDER BY s.n_dead_tup DESC LIMIT 10
""", 'dry_run':True}).encode(),
    headers=H,
))
res = json.loads(r.read())
print("Top dead-tuple tables AFTER ANALYZE:")
for row in res.get('rows', []):
    print(f"  {row[0]:30s} live={row[1]:>8} dead={row[2]:>6} ({row[3] or 0}%)")
