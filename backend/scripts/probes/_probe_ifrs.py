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
            s = f"keys={list(d.keys())[:7]}"
        except:
            s = body[:60].decode(errors='replace')
        print(f"  OK {label:55s} [{r.status}, {len(body):>6}b] {s}")
    except urllib.error.HTTPError as e:
        print(f"  ER {label:55s} [{e.code}] {e.read()[:180].decode(errors='replace')}")
get('/financials/companies/ngmk/ifrs-editor?period=FY&consolidated=true',
    'GET IFRS schema /ngmk FY consolidated')
get('/financials/companies/ngmk/ifrs-editor?period=Q1&consolidated=false',
    'GET IFRS schema /ngmk Q1 standalone')
get('/financials/companies/ngmk/ifrs-editor/history?limit=3',
    'GET IFRS history /ngmk')
get('/financials/companies/ngmk/ifrs-editor/template?years=2024,2025&period=FY',
    'GET IFRS template /ngmk')
get('/financials/companies/ngmk/ifrs-nsbu-diff?year=2024',
    'GET IFRS-NSBU diff /ngmk 2024')
