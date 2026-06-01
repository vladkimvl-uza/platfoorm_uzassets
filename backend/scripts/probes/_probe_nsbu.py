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
            s = f"keys={list(d.keys())[:6]}"
        except:
            s = body[:60].decode(errors='replace')
        print(f"  OK {label:50s} [{r.status}, {len(body):>6}b] {s}")
    except urllib.error.HTTPError as e:
        print(f"  ER {label:50s} [{e.code}] {e.read()[:180].decode(errors='replace')}")
get('/financials/companies/ngmk/nsbu-editor', 'GET NSBU schema /ngmk')
get('/financials/companies/ngmk/nsbu-editor/history?limit=5', 'GET NSBU history /ngmk')
get('/financials/companies/ngmk/nsbu-editor/template?years=2024,2025',
    'GET NSBU template /ngmk')
