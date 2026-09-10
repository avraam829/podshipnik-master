from django.contrib.sitemaps import Sitemap
from django.conf import settings
from django.urls import reverse
from .models import Product

class ProductSitemap(Sitemap):
    limit = 5000
    def items(self):
        return Product.objects.order_by('pk').only('slug')
    def get_urls(self, page=1, site=None, protocol=None):
        from types import SimpleNamespace
        return super().get_urls(page, SimpleNamespace(domain=settings.PRIMARY_DOMAIN), settings.SITE_URL.split(':')[0])

class StaticSitemap(ProductSitemap):
    def items(self):
        return ['index', 'catalog', 'contacts']
    def location(self, item):
        return reverse(item)
