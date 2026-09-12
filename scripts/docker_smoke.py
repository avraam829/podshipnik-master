"""HTTP checks against the running Gunicorn process; no database writes."""
import json
import os
import re
from urllib.request import Request, urlopen

base = os.environ.get('SMOKE_BASE_URL', 'http://127.0.0.1:8000')
headers = {}
if os.environ.get('SMOKE_HTTPS_PROXY') == 'True':
    headers = {'X-Forwarded-Proto': 'https', 'Host': os.environ['PRIMARY_DOMAIN']}
results = []
for path in ('/health/', '/', '/catalog/', '/users/login/', '/users/register/', '/cart/', '/robots.txt', '/sitemap.xml'):
    with urlopen(Request(base + path, headers=headers), timeout=30) as response:
        body = response.read().decode()
        assert response.status == 200, (path, response.status)
        results.append({'path': path, 'status': response.status})
        if path == '/':
            stylesheets = re.findall(r'href="(/static/[^\"]+\.css)"', body)
            assert stylesheets, 'No stylesheet links'
            for stylesheet in stylesheets:
                with urlopen(Request(base + stylesheet, headers=headers), timeout=30) as static:
                    assert static.status == 200 and 'text/css' in static.headers.get('Content-Type', '')
                    assert len(static.read()) > 100
                    results.append({'path': stylesheet, 'status': static.status})
print(json.dumps({'checks': results}, ensure_ascii=False, indent=2))
