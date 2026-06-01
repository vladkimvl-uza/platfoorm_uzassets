import json, urllib.request
BASE='http://localhost:8000'
tok=json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/auth/login',data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),headers={'Content-Type':'application/json'})).read())['access_token']
H={'Authorization':'Bearer '+tok,'Content-Type':'application/json'}
def q(sql):
    r=urllib.request.urlopen(urllib.request.Request(f'{BASE}/admin/db/query',data=json.dumps({'sql':sql,'dry_run':True}).encode(),headers=H))
    return json.loads(r.read())

print("Non-owner users + their flags:")
res = q("""
SELECT u.email, u.is_owner, u.must_change_password,
       COALESCE(string_agg(DISTINCT r.code, ',' ORDER BY r.code), '-') AS roles
FROM users u
LEFT JOIN user_role ur ON ur.user_id = u.id
LEFT JOIN roles r ON r.id = ur.role_id
WHERE u.is_active = true AND u.is_owner = false
GROUP BY u.id, u.email, u.is_owner, u.must_change_password
ORDER BY u.email
""")
for row in res.get('rows', []):
    print(f"  {row[0]:30s} owner={row[1]!s:5s} must_change_pw={row[2]!s:5s} roles={row[3]}")
