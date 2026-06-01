import json, urllib.request
BASE = 'http://localhost:8000'
tok = json.loads(urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/login',
    data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type':'application/json'},
)).read())['access_token']
H = {'Authorization': 'Bearer '+tok, 'Content-Type':'application/json'}
TASK_ID = '55ce9403-4d1c-4dc0-95a7-59bb9577710c'

# 1. Get current status
r = urllib.request.urlopen(urllib.request.Request(f'{BASE}/tasks/{TASK_ID}', headers=H))
before = json.loads(r.read())
print(f"BEFORE: status={before['status']!r} updated_at={before['updated_at'][:19]}")

# 2. PATCH status: active → review
r = urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/tasks/{TASK_ID}',
    data=json.dumps({'status':'review'}).encode(),
    headers=H, method='PATCH',
))
patched = json.loads(r.read())
print(f"PATCH response: status={patched['status']!r}  ← should be 'review'")

# 3. Re-fetch to confirm DB-level persistence
r = urllib.request.urlopen(urllib.request.Request(f'{BASE}/tasks/{TASK_ID}', headers=H))
after = json.loads(r.read())
print(f"AFTER GET: status={after['status']!r} updated_at={after['updated_at'][:19]}")

# 4. Restore to 'active' for cleanup
r = urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/tasks/{TASK_ID}',
    data=json.dumps({'status':'active'}).encode(),
    headers=H, method='PATCH',
))
restored = json.loads(r.read())
print(f"CLEANUP restore: status={restored['status']!r}")

if after['status'] == 'review':
    print("\n  ✅ FIX WORKS — status persisted to DB")
else:
    print(f"\n  ❌ FIX FAILED — status still {after['status']!r}")
