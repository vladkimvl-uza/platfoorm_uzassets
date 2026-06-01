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


def hit(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(BASE + url, headers=H))
        return json.loads(r.read())
    except Exception as e:
        return {'_err': str(e)[:80]}


cid = '931facee-279b-4053-89e5-596a770a8e39'

# What /projects API returns for UMK
print("API: /projects?company_id=UMK&limit=500")
data = hit(f'/projects?company_id={cid}&limit=500')
if isinstance(data, dict) and 'items' in data:
    items = data['items']
elif isinstance(data, list):
    items = data
else:
    print(f"  unexpected shape: {data}")
    items = []

# Group by year
from collections import Counter
by_year_status = Counter()
for it in items:
    by_year_status[(it.get('portfolio_year'), it.get('status'))] += 1
print(f"  total returned: {len(items)}")
print("  by (year, status):")
for k, v in sorted(by_year_status.items(), key=lambda x: (x[0][0] or 0, x[0][1] or '')):
    print(f"    year={k[0]} status={k[1]:12s} n={v}")

# Compare with raw DB
print("\nDB (no API filtering): UMK projects all years:")
res = q(f"""
SELECT portfolio_year, status, COUNT(*)
FROM projects
WHERE company_id='{cid}' AND is_archived=false
GROUP BY portfolio_year, status
ORDER BY portfolio_year, status
""")
for row in res['rows']:
    print(f"    year={row[0]} status={row[1]:12s} n={row[2]}")

# Check tasks too
print("\nAPI: /tasks?company_id=UMK (default limit)")
data = hit(f'/tasks?company_id={cid}')
items = data.get('items', []) if isinstance(data, dict) else data
print(f"  total returned: {len(items)} total field: {data.get('total') if isinstance(data, dict) else '?'}")

# With limit=500
print("\nAPI: /tasks?company_id=UMK&limit=500")
data = hit(f'/tasks?company_id={cid}&limit=500')
items = data.get('items', []) if isinstance(data, dict) else data
print(f"  total returned: {len(items)} total field: {data.get('total') if isinstance(data, dict) else '?'}")
by_year_status = Counter()
for it in items:
    by_year_status[(it.get('portfolio_year'), it.get('status'))] += 1
for k, v in sorted(by_year_status.items(), key=lambda x: (x[0][0] or 0, x[0][1] or '')):
    print(f"    year={k[0]} status={k[1]:12s} n={v}")
