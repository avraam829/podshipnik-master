"""Read-only public SEO checks; no authentication or production writes."""
import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET


def fetch(url):
    if os.name == 'nt':
        # Windows' native TLS backend works on hosts where Python TLS times out.
        with tempfile.TemporaryDirectory() as directory:
            header_file = Path(directory) / 'headers'
            process = subprocess.run([
                'curl.exe', '-fsSL', '--max-time', '30', '-D', str(header_file),
                '-w', '\n__SBA_META__%{http_code} %{url_effective}', url,
            ], capture_output=True, timeout=35, check=True)
            body, metadata = process.stdout.decode('utf-8').rsplit('\n__SBA_META__', 1)
            status, final = metadata.split(' ', 1)
            raw = header_file.read_text(encoding='utf-8').strip().split('\n\n')[-1]
            headers = dict(line.split(': ', 1) for line in raw.splitlines()[1:] if ': ' in line)
            return int(status), final, headers, body
    request = urllib.request.Request(url, headers={'User-Agent': 'SBA-SEO-check/1.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, response.url, dict(response.headers), response.read().decode('utf-8')


def check_page(url):
    try:
        status, final, headers, html = fetch(url)
        def match(pattern):
            found = re.search(pattern, html, re.I | re.S)
            return found.group(1).strip() if found else None
        return {
            'url': url, 'status': status, 'final_url': final,
            'title': match(r'<title>(.*?)</title>'),
            'h1': match(r'<h1[^>]*>(.*?)</h1>'),
            'canonical': match(r'<link[^>]*rel="canonical"[^>]*href="([^"]+)"'),
            'meta_description': match(r'<meta[^>]*name="description"[^>]*content="([^"]+)"'),
            'robots_meta': match(r'<meta[^>]*name="robots"[^>]*content="([^"]+)"'),
            'x_robots_tag': headers.get('X-Robots-Tag'),
            'has_product_description': bool(re.search(r'<h2>Описание</h2>', html)),
            'spec_fields': len(re.findall(r'<dt>', html)),
            'has_product_schema': '"@type": "Product"' in html,
        }
    except Exception as error:
        return {'url': url, 'error': str(error)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='https://gpz5.ru')
    args = parser.parse_args()
    base = args.base.rstrip('/')
    result = {'base': base}
    status, _, _, robots = fetch(base + '/robots.txt')
    result['robots'] = {'status': status, 'content': robots}
    status, _, _, xml = fetch(base + '/sitemap.xml')
    ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    maps = [node.text for node in ET.fromstring(xml).findall('sm:sitemap/sm:loc', ns)]
    result['sitemap_index'] = {'status': status, 'maps': maps}
    product_maps = [url for url in maps if '/sitemap-products.xml' in url]
    samples = [base + '/', base + '/catalog/', base + '/contacts/']
    result['product_maps_checked'] = []
    for url in dict.fromkeys([product_maps[0], product_maps[-1]] if product_maps else []):
        status, _, _, xml = fetch(url)
        locations = [node.text for node in ET.fromstring(xml).findall('sm:url/sm:loc', ns)]
        result['product_maps_checked'].append({'url': url, 'status': status, 'count': len(locations)})
        if locations:
            samples.extend(locations[i] for i in sorted({0, len(locations)//2, len(locations)-1}))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        result['pages'] = list(pool.map(check_page, dict.fromkeys(samples)))
    print(json.dumps(result, ensure_ascii=True, indent=2))
