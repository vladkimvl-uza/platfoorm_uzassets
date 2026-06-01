import json, urllib.request
BASE='http://localhost:8000'
tok=json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/auth/login',data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),headers={'Content-Type':'application/json'})).read())['access_token']
H={'Authorization':'Bearer '+tok,'Content-Type':'application/json'}
def q(sql, dry=True):
    r=urllib.request.urlopen(urllib.request.Request(f'{BASE}/admin/db/query',data=json.dumps({'sql':sql,'dry_run':dry}).encode(),headers=H))
    return json.loads(r.read())

print("=== test@mail.ru details ===")
res = q("SELECT id::text, email, is_owner, must_change_password FROM users WHERE email='test@mail.ru'")
print(f"  {res['rows'][0]}")

print("\n=== Group 'ngmk' details ===")
res = q("SELECT id::text, code, name, company_id::text FROM groups WHERE code='ngmk'")
print(f"  {res['rows'][0]}")

print("\n=== Available roles ===")
res = q("SELECT id::text, code, name_ru FROM roles ORDER BY code LIMIT 15")
for row in res['rows']:
    print(f"  {row[0][:8]}  {row[1]:20s} {row[2]}")

print("\n=== Schema: group_permission_grant columns ===")
res = q("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='group_permission_grant' ORDER BY ordinal_position")
for row in res['rows']: print(f"  {row[0]}: {row[1]}")

print("\n=== Schema: user_group_role columns ===")
res = q("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='user_group_role' ORDER BY ordinal_position")
for row in res['rows']: print(f"  {row[0]}: {row[1]}")

print("\n=== Current state of test@mail.ru direct permissions ===")
res = q("""SELECT COUNT(*) FROM user_role WHERE user_id=(SELECT id FROM users WHERE email='test@mail.ru')""")
print(f"  user_role count: {res['rows'][0][0]}")
res = q("""SELECT COUNT(*) FROM user_group_role WHERE user_id=(SELECT id FROM users WHERE email='test@mail.ru')""")
print(f"  user_group_role count: {res['rows'][0][0]}")
