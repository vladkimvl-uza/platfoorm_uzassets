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
            s = f"keys={list(d.keys())[:6]}" if isinstance(d, dict) else f"list[{len(d)}]"
        except:
            s = body[:60].decode(errors='replace')
        print(f"  OK {label:50s} [{r.status}, {len(body):>6}b] {s}")
        return d
    except urllib.error.HTTPError as e:
        print(f"  ER {label:50s} [{e.code}] {e.read()[:120].decode(errors='replace')}")
cl = get('/companies', 'GET /companies')
if cl:
    print(f"        total={cl.get('total')} items={len(cl.get('items',[]))}")
    if cl.get('items'):
        co_code = cl['items'][0]['code']
        get(f'/companies/{co_code}', f'/companies/{{code}}')
        get(f'/companies/{co_code}/financials', f'/companies/{{code}}/financials')
        get(f'/companies/{co_code}/governance', f'/companies/{{code}}/governance')
get('/companies?sector=mining&limit=5', '/companies?sector=mining')
get('/companies?search=Navoi', '/companies?search=Navoi')
get('/companies?sort_by=governance_score&sort_dir=desc&limit=5', '/companies?sort=gov_score')
sl = get('/companies/sectors/list', 'GET /companies/sectors/list')
if sl:
    print(f"        sectors={len(sl) if isinstance(sl,list) else '?'}")
get('/companies/sectors/list?include_counts=true', '/companies/sectors/list?counts')
