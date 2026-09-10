from django.urls import path
from . import views
from django.views.generic import TemplateView
urlpatterns = [
    path("", views.index, name="index"),
    path("catalog/", views.listing, name="catalog"),
    path("podshipniki/<str:slug>/", views.product_detail, name="product_canonical"),
    path("robots.txt", views.robots),
    path("health/", views.health),
    path("category/<int:category_id>/", views.category_view, name="category"),
    path("search/", views.search, name="search"),
    path("product/<int:product_id>/", views.product_detail, name="product_detail"),
    path("api/search-suggestions/", views.search_suggestions, name="search_suggestions"),
    path('contacts/', TemplateView.as_view(template_name='pages/contacts.html'), name='contacts'),
]
