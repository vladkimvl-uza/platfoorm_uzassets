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
        print(f"  OK {label:50s} [{r.status}, {len(body):>5}b] {s}")
        return d
    except urllib.error.HTTPError as e:
        print(f"  ER {label:50s} [{e.code}] {e.read()[:160].decode(errors='replace')}")
# Find a task to list attachments
tasks = json.loads(urllib.request.urlopen(urllib.request.Request(BASE+'/tasks?limit=1', headers=H)).read())
if tasks.get('items'):
    tid = tasks['items'][0]['id']
    get(f'/attachments/task/{tid}', '/attachments/task/{tid}')
# project
projs = json.loads(urllib.request.urlopen(urllib.request.Request(BASE+'/projects?limit=1', headers=H)).read())
if projs.get('items'):
    pid = projs['items'][0]['id']
    get(f'/attachments/project/{pid}', '/attachments/project/{pid}')
# company (need company id)
cos = json.loads(urllib.request.urlopen(urllib.request.Request(BASE+'/companies?limit=1', headers=H)).read())
if cos.get('items'):
    cid = cos['items'][0]['id']
    get(f'/attachments/company/{cid}', '/attachments/company/{cid}')
