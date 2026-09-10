import json
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q
from django.core.paginator import Paginator, InvalidPage
from django.http import JsonResponse, HttpResponse, Http404
from .models import Category, Product
from .services import catalog_queryset, ordered_products, normalize_designation

PRODUCTS_PER_PAGE = 24

def index(request):
    return render(request, 'catalog/index.html')

def listing(request, category=None):
    query = request.GET.get('q', '').strip()[:120]
    brand = request.GET.get('manufacturer', '').strip()[:100]
    products = catalog_queryset()
    if category:
        ids = {category.pk}
        frontier = ids.copy()
        while frontier:
            frontier = set(Category.objects.filter(parent_id__in=frontier).values_list('pk', flat=True)) - ids
            ids.update(frontier)
        products = products.filter(category_id__in=ids)
    if query:
        products = products.filter(Q(search_key__contains=normalize_designation(query)) | Q(manufacturer__icontains=query) | Q(description__icontains=query))
    if brand:
        products = products.filter(manufacturer=brand)
    try:
        page = Paginator(ordered_products(products), PRODUCTS_PER_PAGE).page(request.GET.get('page', 1))
    except InvalidPage:
        raise Http404('Страница не найдена')
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'catalog/list.html', {
        'category': category, 'query': query, 'manufacturer': brand,
        'products': page, 'page_obj': page, 'page_query': params.urlencode(),
        'brands': Product.objects.exclude(manufacturer='').order_by('manufacturer').values_list('manufacturer', flat=True).distinct(),
        'noindex': bool(query or brand or request.path == '/search/'),
    })

def category_view(request, category_id):
    return listing(request, get_object_or_404(Category, pk=category_id))

def search(request):
    return listing(request)

def search_suggestions(request):
    query = request.GET.get('q', '').strip()[:120]
    products = []
    if len(query) >= 2:
        products = ordered_products(catalog_queryset().filter(Q(search_key__contains=normalize_designation(query)) | Q(manufacturer__icontains=query)))[:10]
    return JsonResponse({'suggestions': [{
        'designation': p.designation, 'manufacturer': p.manufacturer,
        'url': p.get_absolute_url(), 'price': str(p.effective_price) if p.effective_price > 0 else None,
    } for p in products]})

def product_detail(request, product_id=None, slug=None):
    if product_id is not None:
        return redirect(get_object_or_404(Product, pk=product_id).get_absolute_url(), permanent=True)
    product = get_object_or_404(catalog_queryset(), slug=slug)
    schema = {'@context': 'https://schema.org', '@type': 'Product', 'name': product.designation,
              'sku': product.code, 'url': settings.SITE_URL + product.get_absolute_url()}
    if product.manufacturer:
        schema['brand'] = {'@type': 'Brand', 'name': product.manufacturer}
    if product.description:
        schema['description'] = product.description
    return render(request, 'catalog/product_detail.html', {
        'product': product, 'stocks': product.stocks.select_related('warehouse'),
        'prices': product.prices.all(), 'schema_json': json.dumps(schema, ensure_ascii=False).replace('<', '\\u003c'),
    })

def robots(request):
    content = 'User-agent: *\nDisallow: /admin/\nDisallow: /cart/\nDisallow: /users/\nDisallow: /api/\n'
    return HttpResponse(content + f'Sitemap: {settings.SITE_URL}/sitemap.xml\n', content_type='text/plain')

def health(request):
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
    return JsonResponse({'status': 'ok'})
