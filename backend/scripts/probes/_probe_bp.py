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

print("BP:")
get('/bp/metrics', 'GET /bp/metrics')
ac = get('/bp/available-companies', 'GET /bp/available-companies')
if isinstance(ac, list) and ac:
    cid = ac[0]['company_id']
    yr = ac[0]['years'][0]
    print(f"        sample: {ac[0]['company_name_ru']} years={ac[0]['years']}")
    get(f'/bp/{cid}/{yr}/q1', f'/bp/{{cid}}/{{yr}}/q1')
    get(f'/bp/{cid}/{yr}/annual', f'/bp/{{cid}}/{{yr}}/annual')
    get(f'/bp/raw/{cid}/{yr}', f'/bp/raw/{{cid}}/{{yr}}')
    get(f'/bp/attention/{cid}/{yr}/q1', f'/bp/attention/{{cid}}/{{yr}}/q1')
    get(f'/bp/comment/{cid}/{yr}/q1', f'/bp/comment/{{cid}}/{{yr}}/q1')

sm = get('/bp/summary/2026/q1', 'GET /bp/summary/2026/q1')
if sm:
    print(f"        co_count={sm.get('co_count')} totals={len(sm.get('totals',[]))} by_co={len(sm.get('by_company',[]))} by_q={len(sm.get('by_quarter',[]))}")
get('/bp/summary/2026/annual', 'GET /bp/summary/2026/annual')
get('/bp/summary/2026/q1?metric=cogs', 'GET /bp/summary/2026/q1?metric=cogs')
