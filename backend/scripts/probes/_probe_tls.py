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
            s = f"keys={list(d.keys())[:5]}" if isinstance(d, dict) else f"list[{len(d)}]"
        except:
            s = body[:60].decode(errors='replace')
        print(f"  OK {label:50s} [{r.status}, {len(body):>5}b] {s}")
        return d
    except urllib.error.HTTPError as e:
        print(f"  ER {label:50s} [{e.code}] {e.read()[:200].decode(errors='replace')}")
st = get('/admin/tls/status', 'GET /admin/tls/status')
if st:
    print(f"        active={st.get('active_label')}, info_present={st.get('info',{}).get('present')}")
    if st.get('info'):
        print(f"        subject={st['info'].get('subject','?')[:60]}, days_left={st['info'].get('days_left')}")
