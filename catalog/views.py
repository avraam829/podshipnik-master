from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Sum, Value
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from django.urls import reverse
from django.http import JsonResponse
import re

from .models import Category, Product

PRODUCTS_PER_PAGE = 24


def index(request):
    return render(request, "catalog/index.html")


def category_view(request, category_id):
    category = get_object_or_404(
        Category.objects.select_related("parent"), id=category_id
    )
    subcategories = category.children.all()

    # Собираем все id: текущая + дети + внуки
    category_ids = [category.id]
    children = category.children.all()
    if children.exists():
        child_ids = list(children.values_list("id", flat=True))
        category_ids += child_ids
        # Внуки
        grandchild_ids = list(
            Category.objects
            .filter(parent_id__in=child_ids)
            .values_list("id", flat=True)
        )
        category_ids += grandchild_ids

    products_qs = (
        Product.objects
        .filter(category_id__in=category_ids)
        .annotate(total_stock=Coalesce(Sum("stocks__amount"), Value(0)))
        .select_related("category")
        .order_by("designation")
    )

    paginator = Paginator(products_qs, PRODUCTS_PER_PAGE)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "catalog/category.html", {
        "category": category,
        "subcategories": subcategories,
        "products": page_obj,
        "page_obj": page_obj,
    })


def search(request):
    query = request.GET.get("q", "").strip()
    page_obj = None
    products = []

    if query:
        products_qs = (
            Product.objects.filter(
                Q(designation__icontains=query)
                | Q(manufacturer__icontains=query)
                | Q(description__icontains=query)
            )
            .annotate(total_stock=Coalesce(Sum("stocks__amount"), Value(0)))
            .select_related("category")
            .order_by("designation")
        )
        paginator = Paginator(products_qs, PRODUCTS_PER_PAGE)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        products = page_obj

    return render(request, "catalog/search.html", {
        "query": query,
        "products": products,
        "page_obj": page_obj,
    })

def search_suggestions(request):
    query = request.GET.get("q", "").strip()
    suggestions = []
    if query:
        products = Product.objects.filter(
            Q(designation__icontains=query) | Q(manufacturer__icontains=query)
        )[:10]

        for p in products:
            highlighted = re.sub(
                f"({re.escape(query)})",
                r"<strong>\1</strong>",
                p.designation,
                flags=re.IGNORECASE,
            )
            suggestions.append({
                "designation": highlighted,
                "manufacturer": p.manufacturer or "",
                "url": reverse("product_detail", args=[p.id]),
                "price": str(p.price) if p.price else None,  # ← добавить
            })

    return JsonResponse({"suggestions": suggestions})


def product_detail(request, product_id):
    product = get_object_or_404(
        Product.objects.select_related("category", "category__parent"),
        id=product_id,
    )
    stocks = product.stocks.select_related("warehouse").all()
    prices = product.prices.all()

    totals = stocks.aggregate(
        total_amount=Sum("amount"),
        total_free=Sum("free"),
    )

    return render(request, "catalog/product_detail.html", {
        "product": product,
        "stocks": stocks,
        "prices": prices,
        "total_amount": totals["total_amount"] or 0,
        "total_free": totals["total_free"] or 0,
    })