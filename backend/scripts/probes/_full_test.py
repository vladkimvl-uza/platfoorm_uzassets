import json, urllib.request, urllib.error
BASE = 'http://localhost:8000'

USER_ID = '86935283-86af-4a0e-8140-113c3da70dd0'
NGMK_GROUP_ID = '159eaf6e-3516-41c7-b657-ca6302efc9da'
NGMK_CO_ID = '160ad041-9f14-49be-8b40-ffa5effc250c'
AGMK_CO_ID = '45bd5459-9cec-4a2f-9476-d324827f59b9'
DEPT_WORKER_ROLE_ID = 'd2426631-12a6-403d-8569-867af19ed86e'
NGMK_TASK_ID = '64173c7b-8f00-4e21-9cee-eb09eac3de1c'
AGMK_TASK_ID = '57f31dbf-01ea-4ad4-a3f4-7c7f1758fb5c'


def admin_token():
    r = urllib.request.urlopen(urllib.request.Request(
        f'{BASE}/auth/login',
        data=json.dumps({'login': 'test@uz-assets.uz', 'password': 'Rtv152D4CTPdqkOC'}).encode(),
        headers={'Content-Type': 'application/json'},
    ))
    return json.loads(r.read())['access_token']


def admin_q(sql, dry=True):
    h = {'Authorization': 'Bearer ' + admin_token(), 'Content-Type': 'application/json'}
    r = urllib.request.urlopen(urllib.request.Request(
        f'{BASE}/admin/db/query',
        data=json.dumps({'sql': sql, 'dry_run': dry}).encode(), headers=h,
    ))
    return json.loads(r.read())


def get_user_token():
    h = {'Authorization': 'Bearer ' + admin_token(), 'Content-Type': 'application/json'}
    r = urllib.request.urlopen(urllib.request.Request(
        f'{BASE}/rbac/v3/users/{USER_ID}/preview-token', method='POST', data=b'', headers=h,
    ))
    return json.loads(r.read())['access_token']


def check(label, method, url, token, body=None, expect=None):
    h = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
    data = json.dumps(body).encode() if body else None
    try:
        req = urllib.request.Request(BASE + url, headers=h, method=method, data=data)
        r = urllib.request.urlopen(req)
        code = r.status
        rb = r.read()
    except urllib.error.HTTPError as e:
        code = e.code
        rb = e.read()
    try:
        d = json.loads(rb)
        if isinstance(d, list):
            summ = f"list[{len(d)}]"
        elif 'items' in d:
            summ = f"items={len(d.get('items', []))} total={d.get('total', '?')}"
        elif 'companies_by_sector' in d:
            cos = sum(len(s['companies']) for s in d['companies_by_sector'])
            summ = f"sectors={len(d['companies_by_sector'])} companies={cos}"
        elif 'permissions' in d:
            summ = f"perms={len(d.get('permissions', []))} roles={d.get('roles', [])}"
        else:
            summ = ' '.join(
                f"{k}={v}" if not isinstance(v, (dict, list)) else f"{k}=..."
                for k, v in list(d.items())[:3]
            )
    except Exception:
        summ = rb[:60].decode(errors='replace')
    ok = 'OK ' if (expect is None or code == expect) else 'XX '
    print(f"  {ok} [{code}] {method:6s} {url:60s} {label}")
    print(f"          {summ[:120]}")


print("=" * 70)
print("  Phase 0: BASELINE - test@mail.ru, no perms")
print("=" * 70)
tok = get_user_token()
check("auth.me", 'GET', '/auth/me', tok)
check("tasks list", 'GET', '/tasks', tok, expect=403)
check("companies list", 'GET', '/companies', tok, expect=403)

print("\n" + "=" * 70)
print("  Phase 1: grant role 'department_worker' DIRECTLY (no scope)")
print("=" * 70)
admin_q(f"INSERT INTO user_role (user_id, role_id) VALUES ('{USER_ID}', '{DEPT_WORKER_ROLE_ID}') ON CONFLICT DO NOTHING", dry=False)
tok = get_user_token()
check("auth.me - perms granted?", 'GET', '/auth/me', tok)
check("tasks (global)", 'GET', '/tasks', tok, expect=200)
check("tasks NGMK", 'GET', f'/tasks/{NGMK_TASK_ID}', tok, expect=200)
check("tasks AGMK", 'GET', f'/tasks/{AGMK_TASK_ID}', tok, expect=200)
check("financials (not in role)", 'GET', '/financials', tok, expect=403)
check("companies (no companies.view)", 'GET', '/companies', tok, expect=403)
check("admin/db (not owner)", 'GET', '/admin/db/schema', tok, expect=403)

print("\n" + "=" * 70)
print("  Phase 2: WRITE attempts (no .edit/.delete in dept_worker)")
print("=" * 70)
check("PATCH /tasks/NGMK", 'PATCH', f'/tasks/{NGMK_TASK_ID}', tok, body={'status': 'done'}, expect=403)
check("DELETE /tasks/NGMK", 'DELETE', f'/tasks/{NGMK_TASK_ID}', tok, expect=403)

print("\n" + "=" * 70)
print("  Phase 3: revoke direct + add to NGMK group only")
print("=" * 70)
admin_q(f"DELETE FROM user_role WHERE user_id='{USER_ID}'", dry=False)
admin_q(f"INSERT INTO user_group_role (user_id, group_id, role_id) VALUES ('{USER_ID}', '{NGMK_GROUP_ID}', '{DEPT_WORKER_ROLE_ID}') ON CONFLICT DO NOTHING", dry=False)
tok = get_user_token()
check("auth.me - scope active", 'GET', '/auth/me', tok)
check("tasks list (only NGMK?)", 'GET', '/tasks', tok, expect=200)
check("tasks/NGMK", 'GET', f'/tasks/{NGMK_TASK_ID}', tok, expect=200)
check("tasks/AGMK (cross-co - 403?)", 'GET', f'/tasks/{AGMK_TASK_ID}', tok, expect=403)
check("tasks?company_id=NGMK", 'GET', f'/tasks?company_id={NGMK_CO_ID}', tok, expect=200)
check("tasks?company_id=AGMK", 'GET', f'/tasks?company_id={AGMK_CO_ID}', tok, expect=200)

print("\n" + "=" * 70)
print("  Phase 4: ADD financials.view via group_permission_grant")
print("=" * 70)
admin_q(f"INSERT INTO group_permission_grant (group_id, permission_code, grant_type, granted_by_id) SELECT '{NGMK_GROUP_ID}', 'financials.view', 'grant', (SELECT id FROM users WHERE email='test@uz-assets.uz') WHERE NOT EXISTS (SELECT 1 FROM group_permission_grant WHERE group_id='{NGMK_GROUP_ID}' AND permission_code='financials.view')", dry=False)
tok = get_user_token()
check("financials list", 'GET', '/financials', tok, expect=200)
check("financials?co=ngmk", 'GET', '/financials?company_code=ngmk', tok, expect=200)
check("financials?co=agmk (other)", 'GET', '/financials?company_code=agmk', tok, expect=200)
check("portfolio/summary", 'GET', '/financials/portfolio/summary?standard=IFRS&currency=UZS&years=2024', tok, expect=200)

print("\n" + "=" * 70)
print("  Phase 5: CLEANUP - revert all changes")
print("=" * 70)
admin_q(f"DELETE FROM user_group_role WHERE user_id='{USER_ID}'", dry=False)
admin_q(f"DELETE FROM user_role WHERE user_id='{USER_ID}'", dry=False)
admin_q(f"DELETE FROM group_permission_grant WHERE group_id='{NGMK_GROUP_ID}' AND permission_code='financials.view'", dry=False)
res = admin_q(f"SELECT (SELECT COUNT(*) FROM user_role WHERE user_id='{USER_ID}'), (SELECT COUNT(*) FROM user_group_role WHERE user_id='{USER_ID}'), (SELECT COUNT(*) FROM group_permission_grant WHERE group_id='{NGMK_GROUP_ID}')")
print(f"  After cleanup: user_role={res['rows'][0][0]} user_group_role={res['rows'][0][1]} group_perms={res['rows'][0][2]}")
tok = get_user_token()
check("post-cleanup: tasks (403)", 'GET', '/tasks', tok, expect=403)
