import json, urllib.request
BASE='http://localhost:8000'
tok=json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/auth/login',data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),headers={'Content-Type':'application/json'})).read())['access_token']
H={'Authorization':'Bearer '+tok,'Content-Type':'application/json'}
def q(sql):
    r=urllib.request.urlopen(urllib.request.Request(f'{BASE}/admin/db/query',data=json.dumps({'sql':sql,'dry_run':True}).encode(),headers=H))
    return json.loads(r.read())
cid='931facee-279b-4053-89e5-596a770a8e39'
print("tasks status distribution (UMK, FY2026, !archived):")
for row in q(f"SELECT status, COUNT(*), COUNT(linked_year) AS with_linked_year FROM tasks WHERE company_id='{cid}' AND is_archived=false AND portfolio_year=2026 GROUP BY status ORDER BY 2 DESC")['rows']:
    print(f"  {row[0]:12s} {row[1]:3d}  (with linked_year={row[2]})")
print()
print("projects status distribution:")
for row in q(f"SELECT status, COUNT(*), COUNT(linked_year) AS with_linked_year FROM projects WHERE company_id='{cid}' AND is_archived=false AND portfolio_year=2026 GROUP BY status ORDER BY 2 DESC")['rows']:
    print(f"  {row[0]:12s} {row[1]:3d}  (with linked_year={row[2]})")
