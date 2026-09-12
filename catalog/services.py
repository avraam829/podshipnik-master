"""Catalog identity, search and numeric ordering, shared by all web queries."""
import unicodedata
from decimal import Decimal, InvalidOperation
from django.db.models import Case, When, Value, IntegerField, DecimalField, F, Sum, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.utils.text import slugify


def normalize_designation(value):
    text = unicodedata.normalize('NFKC', str(value or '')).casefold()
    return ''.join(c for c in text if not c.isspace() and unicodedata.category(c) != 'Pd' and c != '-')


def numeric_price(value):
    try:
        number = Decimal(str(value).replace('\u00a0', '').replace(' ', '').replace(',', '.'))
        return number if number.is_finite() and number > 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def offer_sort_key(product):
    price = numeric_price(product.price)
    name = product.designation
    return (price is None, price or Decimal(0), any(c.isspace() for c in name.strip()),
            normalize_designation(name), product.manufacturer, product.code)


def product_slug(designation, manufacturer, code):
    # The existing unique business code resolves even same-brand/name collisions.
    label = slugify(f'{designation} {manufacturer}', allow_unicode=True)[:180].strip('-') or 'podshipnik'
    identity = str(code).encode('utf-8').hex()
    return f'{label}-{identity}'


def catalog_queryset():
    from .models import Product, Stock, Price
    retail = Price.objects.filter(product_id=OuterRef('pk'), price_type='retail', price__gt=0).values('price')[:1]
    stock = Stock.objects.filter(product_id=OuterRef('pk')).values('product_id').annotate(
        free_total=Sum('free')).values('free_total')[:1]
    unknown = Stock.objects.filter(product_id=OuterRef('pk'), amount=9999).values('pk')[:1]
    return Product.objects.select_related('category').annotate(
        effective_price=Coalesce(Subquery(retail), F('price')),
        total_stock=Coalesce(Subquery(stock), Value(0)),
        unknown_stock=Subquery(unknown),
    )


def ordered_products(queryset):
    return queryset.annotate(
        missing_price=Case(When(effective_price__gt=0, then=Value(0)), default=Value(1), output_field=IntegerField()),
        price_order=Case(When(effective_price__gt=0, then=F('effective_price')), default=Value(0), output_field=DecimalField(max_digits=10,decimal_places=2)),
    ).order_by('missing_price', 'price_order', 'has_spaces', 'search_key', 'manufacturer', 'code')
