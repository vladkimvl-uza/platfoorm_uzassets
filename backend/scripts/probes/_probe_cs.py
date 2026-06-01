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
            s = f"list[{len(d)}]" if isinstance(d, list) else f"keys={list(d.keys())[:5]}"
        except:
            s = body[:60].decode(errors='replace')
        print(f"  OK {label:50s} [{r.status}, {len(body):>6}b] {s}")
        return d
    except urllib.error.HTTPError as e:
        print(f"  ER {label:50s} [{e.code}] {e.read()[:160].decode(errors='replace')}")
get('/credit-scenario/scenarios', 'GET /scenarios')
get('/credit-scenario/state-summary', 'GET /state-summary')
get('/credit-scenario/debt-ratios?top_n=5', 'GET /debt-ratios?top_n=5')
get('/credit-scenario/repayment-forecast', 'GET /repayment-forecast')
get('/credit-scenario/top-loans?top_n=5', 'GET /top-loans?top_n=5')
get('/credit-scenario/custom-indicators', 'GET /custom-indicators')
get('/credit-scenario/formula/default', 'GET /formula/default')
get('/credit-scenario/default-rr-by-lender', 'GET /default-rr-by-lender')
get('/credit-scenario/overview', 'GET /overview')
get('/credit-scenario/drilldown/loans?limit=5', 'GET /drilldown/loans')
get('/credit-scenario/drilldown/groups-by-company?top_n=5', 'GET /drilldown/groups-by-company')
