import json, urllib.request, urllib.error
BASE = 'http://localhost:8000'
def post(url, body, label):
    try:
        r = urllib.request.urlopen(urllib.request.Request(
            BASE+url,
            data=json.dumps(body).encode(),
            headers={'Content-Type':'application/json'},
        ))
        b = r.read()
        try:
            d = json.loads(b)
            s = f"keys={list(d.keys())[:6]}"
        except:
            s = b[:80].decode(errors='replace')
        print(f"  OK {label:50s} [{r.status}] {s}")
    except urllib.error.HTTPError as e:
        body = e.read()[:160].decode(errors='replace')
        print(f"  {('OK' if e.code in (400,401) else 'ER')} {label:50s} [{e.code}] {body}")

# valid creds, no MFA → should return tokens (DEV_DISABLE_MFA or no mfa_enabled)
post('/auth/login-mfa', {'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'},
     'POST /login-mfa valid creds')
# bad creds → 401
post('/auth/login-mfa', {'login':'test@uz-assets.uz','password':'wrong-pwd-zzz'},
     'POST /login-mfa bad creds')
# verify with neither path → 400
post('/auth/verify-mfa', {}, 'POST /verify-mfa empty')
# verify with bad challenge → 401
post('/auth/verify-mfa', {'challenge_id':'00000000-0000-0000-0000-000000000000','code':'123456'},
     'POST /verify-mfa bad challenge')
