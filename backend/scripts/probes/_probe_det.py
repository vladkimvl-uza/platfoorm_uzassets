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
            if isinstance(d, dict):
                s = f"keys={list(d.keys())[:6]}"
            else:
                s = f"list[{len(d)}]"
        except:
            s = body[:60].decode(errors='replace')
        print(f"  OK {label:55s} [{r.status}, {len(body):>6}b] {s}")
    except urllib.error.HTTPError as e:
        print(f"  ER {label:55s} [{e.code}] {e.read()[:180].decode(errors='replace')}")
get('/financials/detailed/canonical/catalog', 'GET /detailed/canonical/catalog')
get('/financials/detailed/ngmk?standard=IFRS&report_type=BS', 'GET /detailed/ngmk BS')
get('/financials/detailed/ngmk?standard=IFRS&report_type=PL', 'GET /detailed/ngmk PL')
get('/financials/detailed/ngmk?standard=NSBU&report_type=BS', 'GET /detailed/ngmk NSBU BS')
get('/financials/detailed/nonexistent?standard=IFRS&report_type=BS', 'GET /detailed/nonexistent (expect 404)')
