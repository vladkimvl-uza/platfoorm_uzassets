import json, urllib.request, urllib.error
BASE='http://localhost:8000'
admin_tok=json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/auth/login',data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),headers={'Content-Type':'application/json'})).read())['access_token']
ADM={'Authorization':'Bearer '+admin_tok,'Content-Type':'application/json'}
def q(sql):
    r=urllib.request.urlopen(urllib.request.Request(f'{BASE}/admin/db/query',data=json.dumps({'sql':sql,'dry_run':True}).encode(),headers=ADM))
    return json.loads(r.read())

# Get demo user id
res = q("SELECT id::text, email, is_owner FROM users WHERE email='demo@uz-assets.uz'")
demo_id, demo_email, demo_owner = res['rows'][0]
print(f"Target: {demo_email} (owner={demo_owner})")

# Impersonate
r = urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/rbac/v3/users/{demo_id}/preview-token', method='POST',
    data=b'', headers=ADM,
))
demo_tok = json.loads(r.read())['access_token']
DEMO = {'Authorization':'Bearer '+demo_tok, 'Content-Type':'application/json'}

def check(method, url, label, expect_403=False):
    try:
        req = urllib.request.Request(BASE+url, headers=DEMO, method=method)
        r = urllib.request.urlopen(req)
        body = r.read()
        try:
            d = json.loads(body)
            if isinstance(d, list):
                summary = f"list[{len(d)}]"
            elif isinstance(d, dict):
                if 'items' in d:
                    summary = f"items={len(d['items'])}"
                elif 'permissions' in d:
                    summary = f"perms={len(d['permissions'])} roles={d.get('roles')}"
                else:
                    summary = f"keys={list(d.keys())[:5]}"
            else:
                summary = str(d)[:60]
        except:
            summary = body[:60].decode(errors='replace')
        marker = "❌LEAK" if expect_403 else "  ok "
        print(f"  {marker} {method:6s} {url:55s} [{r.status}] {summary}")
    except urllib.error.HTTPError as e:
        marker = "  ok " if (expect_403 and e.code == 403) else ("❌"+str(e.code) if not expect_403 else "  ok ")
        body = e.read()[:120].decode(errors='replace')
        print(f"  {marker} {method:6s} {url:55s} [{e.code}] {body}")

print()
print("═════ scenario 1: demo user — NO roles, NO permissions ═════")
print()
print("─── auth ───")
check('GET', '/auth/me', 'identity')

print()
print("─── modules user SHOULD NOT see (expect 403) ───")
check('GET', '/companies', 'companies list', expect_403=True)
check('GET', '/tasks', 'tasks list', expect_403=True)
check('GET', '/financials', 'financials list', expect_403=True)
check('GET', '/financials/portfolio/summary?standard=IFRS&currency=UZS&years=2024', 'portfolio summary', expect_403=True)
check('GET', '/kpi/co/NGMK/years/2026/managers', 'kpi managers', expect_403=True)
check('GET', '/credit-portfolio/loans', 'credit loans', expect_403=True)
check('GET', '/business-plan/companies', 'bp companies', expect_403=True)
check('GET', '/esg/companies', 'esg companies', expect_403=True)
check('GET', '/governance/board-overview', 'governance', expect_403=True)
check('GET', '/procurement-analysis/companies', 'procurement', expect_403=True)
check('GET', '/ratings/companies', 'ratings', expect_403=True)

print()
print("─── admin-only endpoints (expect 403) ───")
check('GET', '/admin/audit/overview', 'admin audit', expect_403=True)
check('GET', '/admin/db/schema', 'admin DB console', expect_403=True)
check('GET', '/rbac/v3/users', 'admin RBAC users', expect_403=True)
check('GET', '/admin/users/mfa-overview', 'admin MFA overview', expect_403=True)
check('GET', '/admin-broadcasts/templates', 'admin broadcasts', expect_403=True)
check('GET', '/admin/storage/status', 'admin storage', expect_403=True)
check('GET', '/external-apis/keys', 'external apis', expect_403=True)
