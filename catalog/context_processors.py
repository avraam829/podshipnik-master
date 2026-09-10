from django.db.models import Count, Prefetch
from .models import Category


def categories(request):
    all_categories = Category.objects.annotate(
        product_count=Count("products", distinct=True)
    )

    children_qs = all_categories.filter(parent__isnull=False)

    top_level = (
        all_categories
        .filter(parent__isnull=True)
        .prefetch_related(
            Prefetch(
                "children",
                queryset=children_qs,
                to_attr="children_with_counts",
            )
        )
    )

    for cat in top_level:
        cat.total_product_count = cat.product_count
        if hasattr(cat, "children_with_counts"):
            cat.total_product_count += sum(
                c.product_count for c in cat.children_with_counts
            )
            cat.children_list = cat.children_with_counts
        else:
            cat.children_list = []

    return {"categories": top_level}