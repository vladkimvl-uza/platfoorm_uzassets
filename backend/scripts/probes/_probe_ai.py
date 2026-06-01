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
        d = None
        try:
            d = json.loads(rb) if rb else None
            s = f"keys={list(d.keys())[:5]}" if isinstance(d, dict) else (f"list[{len(d)}]" if isinstance(d, list) else 'empty')
        except:
            s = rb[:60].decode(errors='replace')
        print(f"  OK {label:50s} [{r.status}, {len(rb):>5}b] {s}")
        return d
    except urllib.error.HTTPError as e:
        print(f"  ER {label:50s} [{e.code}] {e.read()[:160].decode(errors='replace')}")
hit('GET', '/ai/health', 'GET /ai/health')
hit('GET', '/ai/config', 'GET /ai/config')
hit('GET', '/ai/conversations', 'GET /ai/conversations')
c = hit('POST', '/ai/conversations', 'POST /ai/conversations', body={'title': 'probe convo'})
if c and c.get('id'):
    cid = c['id']
    hit('GET', f'/ai/conversations/{cid}', 'GET /ai/conversations/{id}')
    hit('PATCH', f'/ai/conversations/{cid}', 'PATCH /ai/conversations/{id}', body={'title':'renamed probe'})
    hit('DELETE', f'/ai/conversations/{cid}', 'DELETE /ai/conversations/{id}')
