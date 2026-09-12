"""Exhaustive database/sitemap coverage; HTTP render sample configurable with --all."""
import os
import sys
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.test import Client, override_settings
from catalog.models import Product
from catalog.sitemaps import ProductSitemap

with override_settings(DEBUG=True,SECURE_SSL_REDIRECT=False,ALLOWED_HOSTS=['testserver'],PRIMARY_DOMAIN='testserver',SITE_URL='http://testserver'):
    client=Client()
    sitemap=ProductSitemap()
    urls=set()
    for page in sitemap.paginator.page_range:
        urls.update(entry['location'] for entry in sitemap.get_urls(page=page))
    products=list(Product.objects.order_by('pk').only('pk','slug','designation'))
    for product in products:
        assert 'http://testserver'+product.get_absolute_url() in urls
    sampled=products if '--all' in sys.argv else products[::max(1,len(products)//100)]
    for product in sampled:
        response=client.get(product.get_absolute_url())
        assert response.status_code==200
        html=response.content.decode()
        assert html.count('rel="canonical"')==1
        assert '<title>' in html and '<h1>' in html and 'name="description"' in html
        assert 'noindex' not in html
        redirect=client.get(f'/product/{product.pk}/')
        assert redirect.status_code==301 and redirect['Location']==product.get_absolute_url()
    result={'sitemap_urls':len(urls),'products':len(products),'rendered_and_redirect_tested':len(sampled),'all_http_tested':'--all' in sys.argv}
    Path('docs/evidence/seo-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
