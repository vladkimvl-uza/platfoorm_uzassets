import json, urllib.request
BASE='http://localhost:8000'
tok=json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/auth/login',data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),headers={'Content-Type':'application/json'})).read())['access_token']
H={'Authorization':'Bearer '+tok,'Content-Type':'application/json'}
def q(sql):
    r=urllib.request.urlopen(urllib.request.Request(f'{BASE}/admin/db/query',data=json.dumps({'sql':sql,'dry_run':True}).encode(),headers=H))
    return json.loads(r.read())

# Existing users + their effective access
print("=== Existing users ===")
res = q("""
SELECT u.email,
       u.is_owner,
       COALESCE(string_agg(DISTINCT r.code, ',' ORDER BY r.code), '-') AS roles,
       (SELECT COUNT(*) FROM user_group_role ugr WHERE ugr.user_id = u.id) AS group_memberships
FROM users u
LEFT JOIN user_role ur ON ur.user_id = u.id
LEFT JOIN roles r ON r.id = ur.role_id
WHERE u.is_active = true
GROUP BY u.id, u.email, u.is_owner
ORDER BY u.email
LIMIT 25
""")
for row in res.get('rows', []):
    print(f"  {row[0]:35s} owner={row[1]!s:5s} roles={row[2]:30s} groups={row[3]}")

print()
print("=== Groups overview ===")
res = q("""
SELECT g.code, g.name, g.company_id IS NOT NULL AS company_scoped,
       (SELECT COUNT(*) FROM user_group_role ugr WHERE ugr.group_id = g.id) AS members,
       (SELECT COUNT(*) FROM group_permission_grant gpg WHERE gpg.group_id = g.id) AS perms
FROM groups g
ORDER BY g.code
LIMIT 25
""")
for row in res.get('rows', []):
    print(f"  {row[0]:25s} {(row[1] or '')[:30]:30s} co_scoped={row[2]!s:5s} members={row[3]:3} perms={row[4]}")
