import json, urllib.request
req = urllib.request.Request(
    'http://localhost:8000/auth/login',
    data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type':'application/json'},
)
tok = json.loads(urllib.request.urlopen(req).read())['access_token']
H = {'Authorization': 'Bearer ' + tok}
d = json.loads(urllib.request.urlopen(urllib.request.Request(
    'http://localhost:8000/procurement/aggregate', headers=H,
)).read())
overpay = sum(float(r.get('sum_overpay') or 0) for r in d['rating'])
savings = sum(float(r.get('sum_savings') or 0) for r in d['rating'])
above_cnt = sum(int(r.get('above_count') or 0) for r in d['rating'])
print(f'rating len: {len(d["rating"])}')
print(f'Sum overpay: {overpay/1e9:,.2f} млрд UZS')
print(f'Sum savings: {savings/1e9:,.2f} млрд UZS')
print(f'NET (savings - overpay): {(savings - overpay)/1e9:,.2f} млрд UZS')
print(f'redCount sum(above_count): {above_cnt}')
print(f'kpis.above_market_pct: {d["kpis"]["above_market_pct"]}')
print(f'kpis.total_overpay_uzs (raw): {d["kpis"]["total_overpay_uzs"]}')
