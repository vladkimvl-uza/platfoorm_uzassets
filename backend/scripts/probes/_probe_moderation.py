"""Smoke-test Moderation module after refactor + verify gate_or_apply still works."""
import json, urllib.request, urllib.error

BASE = 'http://localhost:8000'
tok = json.loads(urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/login',
    data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type':'application/json'},
)).read())['access_token']
H = {'Authorization': 'Bearer '+tok}

def get(url, label):
    try:
        r = urllib.request.urlopen(urllib.request.Request(BASE+url, headers=H))
        body = r.read()
        try:
            d = json.loads(body)
            if isinstance(d, list):
                s = f"list[{len(d)}]"
            elif isinstance(d, dict):
                s = f"keys={list(d.keys())[:6]}"
            else:
                s = str(d)[:60]
        except Exception:
            s = body[:80].decode(errors='replace')
        print(f"  OK {label:55s} [{r.status}, {len(body):>7}b] {s}")
        return d if isinstance(d, (dict, list)) else None
    except urllib.error.HTTPError as e:
        print(f"  ER {label:55s} [{e.code}] {e.read()[:160].decode(errors='replace')}")

print("Moderation dashboard:")
ov = get('/moderation/overview', '/moderation/overview')
if ov:
    print(f"        pending={ov.get('pending')} under_review={ov.get('under_review')}")
    print(f"        rules_active={ov.get('rules_active_count')}/{ov.get('rules_total_count')}, moderators={ov.get('moderators_count')}, external={ov.get('external_users_count')}")
get('/moderation/catalog', '/moderation/catalog')

print("\nQueue listings:")
q = get('/moderation/queue', '/moderation/queue')
if q:
    print(f"        total={q.get('total')} counts={q.get('counts_by_status')}")
get('/moderation/queue?status=pending', '/moderation/queue?status=pending')
get('/moderation/my-submissions', '/moderation/my-submissions')

print("\nRules:")
get('/moderation/rules', '/moderation/rules')

print("\nUsers sub-tabs:")
get('/moderation/moderators', '/moderation/moderators')
get('/moderation/submitted-users', '/moderation/submitted-users')

print("\nRegression: gate_or_apply still works (KPI fetch should not break):")
get('/kpi/summary/2026/q1', '/kpi/summary (gate_or_apply path)')
