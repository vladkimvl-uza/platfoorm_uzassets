import json, urllib.request
req = urllib.request.Request(
    'http://localhost:8000/auth/login',
    data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type':'application/json'},
)
tok = json.loads(urllib.request.urlopen(req).read())['access_token']
d = json.loads(urllib.request.urlopen(urllib.request.Request(
    'http://localhost:8000/procurement/aggregate',
    headers={'Authorization':'Bearer '+tok},
)).read())
print('rating len:', len(d.get('rating',[])))
print('rating keys (first row):', list(d.get('rating',[{}])[0].keys()))
print()
for r in d.get('rating',[]):
    n = r.get('co_name') or r.get('company_name') or r.get('company_id') or 'NULL'
    ov = float(r.get('sum_overpay') or 0)
    sv = float(r.get('sum_savings') or 0)
    dv = float(r.get('sum_dev') or 0)
    ac = r.get('above_count') or 0
    tc = r.get('total_count') or 0
    print(f"{str(n)[:40]:40s}  ov={ov/1e9:9.2f}  sv={sv/1e9:9.2f}  dev={dv/1e9:9.2f}  above={ac:3d}/{tc:3d}")
print()
print('KPIs:', d.get('kpis'))
