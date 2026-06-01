import json
import time
import urllib.request

BASE = 'http://localhost:8000'
USER_ID = '86935283-86af-4a0e-8140-113c3da70dd0'
NGMK_GROUP_ID = '159eaf6e-3516-41c7-b657-ca6302efc9da'

# Wait out rate-limit
print("Waiting 70s for rate-limit reset...")
time.sleep(70)

tok = json.loads(urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/login',
    data=json.dumps({'login': 'test@uz-assets.uz', 'password': 'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type': 'application/json'},
)).read())['access_token']
H = {'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'}


def q(sql, dry=False):
    r = urllib.request.urlopen(urllib.request.Request(
        f'{BASE}/admin/db/query',
        data=json.dumps({'sql': sql, 'dry_run': dry}).encode(), headers=H,
    ))
    return json.loads(r.read())


q(f"DELETE FROM user_group_role WHERE user_id='{USER_ID}'")
q(f"DELETE FROM user_role WHERE user_id='{USER_ID}'")
q(f"DELETE FROM group_permission_grant WHERE group_id='{NGMK_GROUP_ID}' AND permission_code='financials.view'")
res = q(
    f"SELECT (SELECT COUNT(*) FROM user_role WHERE user_id='{USER_ID}'), "
    f"(SELECT COUNT(*) FROM user_group_role WHERE user_id='{USER_ID}'), "
    f"(SELECT COUNT(*) FROM group_permission_grant WHERE group_id='{NGMK_GROUP_ID}')",
    dry=True,
)
print(f"After cleanup: user_role={res['rows'][0][0]} user_group_role={res['rows'][0][1]} group_perms={res['rows'][0][2]}")
print("Expected: all zeros")
