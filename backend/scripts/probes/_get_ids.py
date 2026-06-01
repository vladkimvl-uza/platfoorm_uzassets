import json, urllib.request
BASE='http://localhost:8000'
tok=json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/auth/login',data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),headers={'Content-Type':'application/json'})).read())['access_token']
H={'Authorization':'Bearer '+tok,'Content-Type':'application/json'}
def q(sql):
    r=urllib.request.urlopen(urllib.request.Request(f'{BASE}/admin/db/query',data=json.dumps({'sql':sql,'dry_run':True}).encode(),headers=H))
    return json.loads(r.read())

print("NGMK task:")
res = q("""SELECT id::text, title FROM tasks WHERE company_id='160ad041-9f14-49be-8b40-ffa5effc250c' LIMIT 1""")
print(f"  {res['rows'][0][0]}  {res['rows'][0][1][:50]}")

print("AGMK task (other company):")
res = q("""SELECT t.id::text, t.title, c.code FROM tasks t JOIN companies c ON c.id=t.company_id WHERE c.code='agmk' LIMIT 1""")
if res['rows']:
    print(f"  {res['rows'][0][0]}  co={res['rows'][0][2]}  {res['rows'][0][1][:50]}")

# Get NGMK company id
print("\nCompanies sample:")
res = q("SELECT id::text, code FROM companies WHERE code IN ('ngmk', 'agmk', 'ung') ORDER BY code")
for row in res['rows']:
    print(f"  {row[1]:8s} {row[0]}")

# Department_worker role id
print("\nDepartment_worker role id:")
res = q("SELECT id::text FROM roles WHERE code='department_worker'")
print(f"  {res['rows'][0][0]}")
