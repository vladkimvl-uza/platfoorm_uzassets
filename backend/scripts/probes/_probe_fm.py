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
        print(f"  ER {label:50s} [{e.code}] {e.read()[:200].decode(errors='replace')}")
get('/finmodel/template', 'GET /finmodel/template')
get('/finmodel/macro/global', 'GET /finmodel/macro/global')
cos = json.loads(urllib.request.urlopen(urllib.request.Request(BASE+'/companies?limit=1', headers=H)).read())
if cos.get('items'):
    cid = cos['items'][0]['id']
    get(f'/finmodel/{cid}', f'/finmodel/{{cid}}')
    get(f'/finmodel/{cid}/scenarios', f'/finmodel/{{cid}}/scenarios')
    get(f'/finmodel/{cid}/comments', f'/finmodel/{{cid}}/comments')
    get(f'/finmodel/{cid}/2026', f'/finmodel/{{cid}}/2026')
    get(f'/finmodel/{cid}/2026/macro', f'/finmodel/{{cid}}/2026/macro')
    get(f'/finmodel/{cid}/2026/validate', f'/finmodel/{{cid}}/2026/validate')
