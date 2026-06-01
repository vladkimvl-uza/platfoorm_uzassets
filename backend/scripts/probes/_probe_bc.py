import json, urllib.request, urllib.error
BASE = 'http://localhost:8000'
# bot_callbacks requires HMAC signature — we can't easily test happy path without secret
# Verify that endpoints return 401 (auth required) — that's correct behavior
def get_no_sig(url, label, method='POST', body=None):
    try:
        req = urllib.request.Request(
            BASE+url, method=method,
            headers={'Content-Type': 'application/json'},
            data=json.dumps(body).encode() if body else b'{}',
        )
        r = urllib.request.urlopen(req)
        print(f"  ?? {label:50s} [{r.status}, unexpected]")
    except urllib.error.HTTPError as e:
        # 401 = correctly enforces signature
        body = e.read()[:80].decode(errors='replace')
        marker = 'EXPECTED' if e.code == 401 else 'unexpected'
        print(f"  {marker:8s} {label:42s} [{e.code}] {body}")
get_no_sig('/bot/moderation/approve', 'POST /bot/moderation/approve', body={'chat_id':1,'submission_id':'x'})
get_no_sig('/bot/moderation/reject',  'POST /bot/moderation/reject',  body={'chat_id':1,'submission_id':'x'})
get_no_sig('/bot/tg-link/confirm',    'POST /bot/tg-link/confirm',    body={'chat_id':1,'token':'x'})
get_no_sig('/bot/tg-link/deny',       'POST /bot/tg-link/deny',       body={'chat_id':1,'token':'x'})
get_no_sig('/bot/tg-callbacks/mfa-report', 'POST /bot/tg-callbacks/mfa-report', body={'chat_id':1})
