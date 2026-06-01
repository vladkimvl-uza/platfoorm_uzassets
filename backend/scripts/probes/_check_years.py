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


# Live API: hit /dashboard/shareholder for 2026 + 2025 + check what API actually returns
def hit(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(BASE + url, headers=H))
        return json.loads(r.read())
    except Exception as e:
        return {'_err': str(e)[:80]}


cid = '931facee-279b-4053-89e5-596a770a8e39'

print("Live API: /dashboard/shareholder for different years")
print("=" * 60)
for year in [2024, 2025, 2026]:
    data = hit(f'/dashboard/shareholder?year={year}')
    if '_err' in data:
        print(f"  Year {year}: ERROR {data['_err']}")
        continue
    # Find UMK in companies_by_sector
    for sector in data.get('companies_by_sector', []):
        for co in sector.get('companies', []):
            if co.get('code') == 'umk':
                print(f"  Year {year} UMK: progress={co.get('progress_pct')}% "
                      f"projects={co.get('projects_done')}/{co.get('projects_total')} "
                      f"tasks={co.get('tasks_done')}/{co.get('tasks_total')}")
                break

# Also UMK breakdown in DB across all years
print("\nDB: UMK tasks by year:")
for r in q(f"SELECT portfolio_year, status, COUNT(*) FROM tasks WHERE company_id='{cid}' AND is_archived=false GROUP BY portfolio_year, status ORDER BY portfolio_year DESC, status")['rows']:
    print(f"  year={r[0]} status={r[1]:12s} n={r[2]}")

print("\nDB: UMK projects by year:")
for r in q(f"SELECT portfolio_year, status, COUNT(*) FROM projects WHERE company_id='{cid}' AND is_archived=false GROUP BY portfolio_year, status ORDER BY portfolio_year DESC, status")['rows']:
    print(f"  year={r[0]} status={r[1]:12s} n={r[2]}")
