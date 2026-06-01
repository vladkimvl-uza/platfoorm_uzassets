import json, urllib.request
BASE='http://localhost:8000'
tok=json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/auth/login',data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),headers={'Content-Type':'application/json'})).read())['access_token']
H={'Authorization':'Bearer '+tok,'Content-Type':'application/json'}
def q(sql):
    r=urllib.request.urlopen(urllib.request.Request(f'{BASE}/admin/db/query',data=json.dumps({'sql':sql,'dry_run':True}).encode(),headers=H))
    return json.loads(r.read())

print("=== Permissions of role 'department_worker' ===")
res = q("""
SELECT p.code FROM permissions p
JOIN role_permission rp ON rp.permission_id = p.id
JOIN roles r ON r.id = rp.role_id
WHERE r.code='department_worker'
ORDER BY p.code
""")
for row in res['rows']: print(f"  {row[0]}")

print("\n=== Permissions of role 'audit_viewer' ===")
res = q("""
SELECT p.code FROM permissions p
JOIN role_permission rp ON rp.permission_id = p.id
JOIN roles r ON r.id = rp.role_id
WHERE r.code='audit_viewer'
ORDER BY p.code
""")
for row in res['rows']: print(f"  {row[0]}")

# Sample 10 NGMK task IDs for cross-co testing
print("\n=== NGMK task ids (for /tasks/{id} test) ===")
res = q("""SELECT id::text, title FROM tasks WHERE company_id='160ad041-9f14-49be-8b40-ffa5effc250c' LIMIT 3""")
for row in res['rows']: print(f"  {row[0]} {row[1][:50]}")

print("\n=== Non-NGMK task id (for cross-co access test) ===")
res = q("""SELECT id::text, title, c.code FROM tasks t JOIN companies c ON c.id=t.company_id WHERE t.company_id!='160ad041-9f14-49be-8b40-ffa5effc250c' LIMIT 1""")
for row in res['rows']: print(f"  {row[0]} co={row[2]} {row[1][:50]}")
