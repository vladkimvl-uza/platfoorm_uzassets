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
            s = f"list[{len(d)}]" if isinstance(d, list) else f"keys={list(d.keys())[:6]}"
        except:
            s = body[:60].decode(errors='replace')
        print(f"  OK {label:50s} [{r.status}, {len(body):>6}b] {s}")
        return d
    except urllib.error.HTTPError as e:
        print(f"  ER {label:50s} [{e.code}] {e.read()[:200].decode(errors='replace')}")

get('/credit-portfolio/loans?company_code=ung', 'GET /loans?company_code=ung')
get('/credit-portfolio/companies-with-loans', 'GET /companies-with-loans')
get('/credit-portfolio/aggregate', 'GET /aggregate')
get('/credit-portfolio/aggregate?company_code=ung', 'GET /aggregate?co=ung')
get('/credit-portfolio/risk-metrics?company_code=ung', 'GET /risk-metrics?co=ung')
get('/credit-portfolio/risk-bubble?company_code=ung', 'GET /risk-bubble?co=ung')
get('/credit-portfolio/sankey?company_code=ung', 'GET /sankey?co=ung')
get('/credit-portfolio/companies-overview', 'GET /companies-overview')
get('/credit-portfolio/fx-rates', 'GET /fx-rates')
