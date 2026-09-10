# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.contrib.sitemaps.views import index, sitemap
from catalog.sitemaps import ProductSitemap, StaticSitemap
sitemaps = {'products': ProductSitemap, 'pages': StaticSitemap}

urlpatterns = [
    path('sitemap.xml', index, {'sitemaps': sitemaps}, name='sitemap-index'),
    path('sitemap-<section>.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path("admin/", admin.site.urls),
    path("users/", include("users.urls")),
    path("cart/", include("cart.urls")),
    path("", include("catalog.urls")),
]
