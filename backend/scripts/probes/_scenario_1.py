import json, urllib.request, urllib.error
BASE='http://localhost:8000'
admin_tok=json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/auth/login',data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),headers={'Content-Type':'application/json'})).read())['access_token']
ADM={'Authorization':'Bearer '+admin_tok,'Content-Type':'application/json'}
def q(sql):
    r=urllib.request.urlopen(urllib.request.Request(f'{BASE}/admin/db/query',data=json.dumps({'sql':sql,'dry_run':True}).encode(),headers=ADM))
    return json.loads(r.read())

target_id = q("SELECT id::text FROM users WHERE email='test@mail.ru'")['rows'][0][0]
r = urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/rbac/v3/users/{target_id}/preview-token', method='POST',
    data=b'', headers=ADM,
))
USR = {'Authorization':'Bearer '+json.loads(r.read())['access_token'], 'Content-Type':'application/json'}

def check(method, url, expect_status=None):
    try:
        req = urllib.request.Request(BASE+url, headers=USR, method=method)
        r = urllib.request.urlopen(req)
        body = r.read()
        code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
        body = e.read()
    short = body[:80].decode(errors='replace').replace('\n', ' ')
    expected = '✅' if (expect_status is None or code == expect_status) else '❌'
    print(f"  {expected} [{code}] {method:6s} {url:55s} {short}")

print("═══ scenario 1: test@mail.ru — NO permissions ═══\n")
print("── /auth/me ──")
check('GET', '/auth/me', 200)

print("\n── module endpoints (expect 403 — no view permissions) ──")
check('GET', '/companies', 403)
check('GET', '/tasks', 403)
check('GET', '/projects', 403)
check('GET', '/financials', 403)
check('GET', '/credit-portfolio/loans', 403)
check('GET', '/business-plan/companies', 403)
check('GET', '/esg/companies', 403)
check('GET', '/governance/board-overview', 403)
check('GET', '/kpi/co/NGMK/years/2026/managers', 403)
check('GET', '/ratings/companies', 403)
check('GET', '/procurement-analysis/companies', 403)

print("\n── admin endpoints (expect 403) ──")
check('GET', '/admin/audit/overview', 403)
check('GET', '/admin/db/schema', 403)
check('GET', '/rbac/v3/users', 403)
check('GET', '/admin/users/mfa-overview', 403)
check('GET', '/admin-broadcasts/templates', 403)
check('GET', '/admin/storage/status', 403)

print("\n── always-allowed for auth'd user ──")
check('GET', '/mfa/status', 200)
check('GET', '/dashboard/shareholder?year=2026', None)  # what does it return?
check('GET', '/users/search?q=test&limit=3', 200)  # autocomplete
