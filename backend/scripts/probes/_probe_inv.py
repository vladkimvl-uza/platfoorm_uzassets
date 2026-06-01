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
        b = r.read()
        print(f"  OK {label:50s} [{r.status}, {len(b)}b]")
    except urllib.error.HTTPError as e:
        print(f"  {('OK' if e.code in (403,400) else 'ER')} {label:50s} [{e.code}] {e.read()[:120].decode(errors='replace')}")
get('/invest-projects-storage/root/.json', 'GET /root/.json (correct)')
get('/invest-projects-storage/root/companies/ngmk.json', 'GET path companies/ngmk')
