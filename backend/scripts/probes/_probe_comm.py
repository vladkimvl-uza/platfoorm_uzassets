import json, urllib.request, urllib.error
BASE = 'http://localhost:8000'
tok = json.loads(urllib.request.urlopen(urllib.request.Request(
    f'{BASE}/auth/login',
    data=json.dumps({'login':'test@uz-assets.uz','password':'Rtv152D4CTPdqkOC'}).encode(),
    headers={'Content-Type':'application/json'},
)).read())['access_token']
H = {'Authorization': 'Bearer '+tok}
def hit(method, url, label, body=None):
    try:
        req = urllib.request.Request(BASE+url, headers={**H, 'Content-Type':'application/json'},
                                     method=method,
                                     data=json.dumps(body).encode() if body else None)
        r = urllib.request.urlopen(req)
        rb = r.read()
        try:
            d = json.loads(rb)
            s = f"keys={list(d.keys())[:6]}" if isinstance(d, dict) else f"list[{len(d)}]"
        except:
            s = rb[:60].decode(errors='replace') if rb else 'empty'
        print(f"  OK {label:50s} [{r.status}, {len(rb):>5}b] {s}")
        return d if isinstance(d, (dict, list)) else None
    except urllib.error.HTTPError as e:
        print(f"  ER {label:50s} [{e.code}] {e.read()[:200].decode(errors='replace')}")

# Get a task to test against
tasks = json.loads(urllib.request.urlopen(urllib.request.Request(BASE+'/tasks?limit=1', headers=H)).read())
if tasks.get('items'):
    tid = tasks['items'][0]['id']
    hit('GET', f'/tasks/{tid}/comments', 'GET /tasks/{id}/comments')
    c = hit('POST', f'/tasks/{tid}/comments', 'POST /tasks/{id}/comments', body={'body': 'test comment from probe'})
    if c and c.get('id'):
        cid = c['id']
        hit('PATCH', f'/comments/tasks/{cid}', 'PATCH /comments/tasks/{cid}', body={'body': 'test comment edited'})
        hit('DELETE', f'/comments/tasks/{cid}', 'DELETE /comments/tasks/{cid}')

# Now project
projects = json.loads(urllib.request.urlopen(urllib.request.Request(BASE+'/projects?limit=1', headers=H)).read())
if projects.get('items'):
    pid = projects['items'][0]['id']
    hit('GET', f'/projects/{pid}/comments', 'GET /projects/{id}/comments')
    c = hit('POST', f'/projects/{pid}/comments', 'POST /projects/{id}/comments', body={'body': 'test project comment'})
    if c and c.get('id'):
        cid = c['id']
        hit('DELETE', f'/comments/projects/{cid}', 'DELETE /comments/projects/{cid}')
