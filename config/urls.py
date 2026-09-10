# config/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("users/", include("users.urls")),
    path("cart/", include("cart.urls")),
    path("", include("catalog.urls")),
]
