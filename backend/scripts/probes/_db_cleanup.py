import json, urllib.request, urllib.error
BASE = 'http://localhost:8000'
tok = json.loads(urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/login',
    data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type':'application/json'},
)).read())['access_token']
H = {'Authorization': 'Bearer '+tok, 'Content-Type':'application/json'}

def q(sql, dry_run=True):
    """Run SQL via /admin/db/query."""
    try:
        r = urllib.request.urlopen(urllib.request.Request(
            f'{BASE}/admin/db/query',
            data=json.dumps({'sql':sql, 'dry_run':dry_run}).encode(),
            headers=H,
        ))
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {'_error': e.code, '_body': e.read()[:300].decode(errors='replace')}

# ───── INVENTORY: probe / test data candidates ─────
print("=" * 70)
print("1. financial_reports by source pattern:")
print("=" * 70)
res = q("""
SELECT LEFT(source, 70) AS source_prefix,
       standard, report_type,
       COUNT(*) AS cnt,
       MAX(created_at) AS last_created
FROM financial_reports
GROUP BY LEFT(source, 70), standard, report_type
ORDER BY cnt DESC LIMIT 30
""")
if '_error' in res:
    print(f"ERROR: {res}")
else:
    for row in res.get('rows', []):
        print(f"  {row[3]:5d} · {row[1]}/{row[2]:3} · {str(row[4])[:19]} · {row[0]}")
    print(f"  total groups: {res.get('row_count')}")

print()
print("=" * 70)
print("2. Tables we'll target for VACUUM ANALYZE:")
print("=" * 70)
res = q("""
SELECT relname AS tbl,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS sz,
       n_live_tup AS live,
       n_dead_tup AS dead
FROM pg_class c
JOIN pg_namespace ns ON ns.oid = c.relnamespace
LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
WHERE ns.nspname = 'public'
  AND c.relkind = 'r'
  AND n_dead_tup > 0
ORDER BY n_dead_tup DESC NULLS LAST
LIMIT 20
""")
if '_error' in res:
    print(f"ERROR: {res}")
else:
    for row in res.get('rows', []):
        print(f"  {row[0]:30s} {row[1]:>10s} · live={row[2]:>8} dead={row[3]:>6}")
