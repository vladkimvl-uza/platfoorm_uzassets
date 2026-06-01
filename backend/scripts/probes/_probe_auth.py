import json, urllib.request, urllib.error
BASE = 'http://localhost:8000'

# 1. LOGIN
print("=== 1. LOGIN ===")
r1 = urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/login',
    data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type':'application/json'},
))
tokens = json.loads(r1.read())
print(f"  OK login [{r1.status}] access={tokens['access_token'][:30]}... refresh={tokens['refresh_token'][:30]}...")
tok = tokens['access_token']
ref = tokens['refresh_token']

# 2. ME
print("=== 2. ME ===")
r2 = urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/me',
    headers={'Authorization':'Bearer '+tok},
))
me = json.loads(r2.read())
print(f"  OK me [{r2.status}] email={me.get('email')} is_owner={me.get('is_owner')} roles={me.get('roles')[:3]}")

# 3. MFA STATUS
print("=== 3. MFA STATUS ===")
r3 = urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/mfa/status',
    headers={'Authorization':'Bearer '+tok},
))
mfa_s = json.loads(r3.read())
print(f"  OK mfa/status [{r3.status}] {mfa_s}")

# 4. MFA onboarding status
print("=== 4. MFA onboarding/status ===")
r4 = urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/mfa/onboarding/status',
    headers={'Authorization':'Bearer '+tok},
))
print(f"  OK onboarding [{r4.status}] {r4.read().decode()[:120]}")

# 5. ADMIN mfa-overview
print("=== 5. ADMIN /mfa-overview ===")
r5 = urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/admin/users/mfa-overview',
    headers={'Authorization':'Bearer '+tok},
))
ov = json.loads(r5.read())
print(f"  OK [{r5.status}] users={ov['summary']['total']} mfa_enabled={ov['summary']['mfa_enabled_count']}")

# 6. REFRESH
print("=== 6. REFRESH ===")
r6 = urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/refresh',
    data=json.dumps({'refresh_token':ref}).encode(),
    headers={'Content-Type':'application/json'},
))
new_tokens = json.loads(r6.read())
print(f"  OK refresh [{r6.status}] new_access={new_tokens['access_token'][:30]}...")

# 7. LOGOUT
print("=== 7. LOGOUT ===")
r7 = urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/logout',
    data=json.dumps({'refresh_token':new_tokens['refresh_token']}).encode(),
    headers={'Content-Type':'application/json','Authorization':'Bearer '+new_tokens['access_token']},
))
print(f"  OK logout [{r7.status}]")

# 8. FORGOT-PASSWORD init (expect 404 on bogus login)
print("=== 8. FORGOT-PASSWORD init bad login ===")
try:
    r8 = urllib.request.urlopen(urllib.request.Request(
        f'{BASE}/auth/forgot-password',
        data=json.dumps({'login':'nonexistent_email_xxx@test.com'}).encode(),
        headers={'Content-Type':'application/json'},
    ))
    print(f"  ER unexpected 200")
except urllib.error.HTTPError as e:
    print(f"  OK 404 [{e.code}] {e.read().decode()[:120]}")
