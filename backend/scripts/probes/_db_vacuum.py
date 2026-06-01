import json, urllib.request, urllib.error
BASE = 'http://localhost:8000'
tok = json.loads(urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/login',
    data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type':'application/json'},
)).read())['access_token']
H = {'Authorization': 'Bearer '+tok, 'Content-Type':'application/json'}

def q(sql, dry_run=False):
    try:
        r = urllib.request.urlopen(urllib.request.Request(
            f'{BASE}/admin/db/query',
            data=json.dumps({'sql':sql, 'dry_run':dry_run}).encode(),
            headers=H,
        ))
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read()[:400].decode(errors='replace')
        return {'_error': e.code, '_body': body}

print("=" * 70)
print("1. Dead tuples scan (top 20):")
print("=" * 70)
res = q("""
SELECT s.relname AS tbl,
       pg_size_pretty(pg_total_relation_size(s.relid)) AS sz,
       s.n_live_tup AS live,
       s.n_dead_tup AS dead,
       ROUND(100.0 * s.n_dead_tup / NULLIF(s.n_live_tup + s.n_dead_tup, 0), 1) AS dead_pct
FROM pg_stat_user_tables s
WHERE s.schemaname = 'public'
ORDER BY s.n_dead_tup DESC NULLS LAST
LIMIT 20
""", dry_run=True)
if '_error' in res:
    print(f"ERROR: {res}")
else:
    rows = res.get('rows', [])
    total_dead = sum(r[3] or 0 for r in rows)
    for row in rows:
        print(f"  {row[0]:35s} {row[1]:>10s} live={row[2]:>8} dead={row[3]:>6} ({row[4] or 0}%)")
    print(f"  TOTAL dead in top 20: {total_dead}")
