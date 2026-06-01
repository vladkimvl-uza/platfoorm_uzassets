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
for r in d['rating']:
    name = (r.get('company_name') or '')[:30]
    sec = r.get('company_sector') or 'NULL'
    col = r.get('company_color')
    print(f"{name:30s} | {sec:25s} | {col}")
