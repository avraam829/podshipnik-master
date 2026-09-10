import json
from django.core.management.base import BaseCommand
from catalog.models import (
    Category, Product, Warehouse, Stock, Price
)
from decimal import Decimal


class Command(BaseCommand):
    help = "Импорт каталога из prepared_for_db.json"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="prepared_for_db.json",
            help="Путь к JSON файлу"
        )

    def handle(self, *args, **options):
        file_path = options["file"]

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        categories_data = data["categories"]
        warehouses_data = data["warehouses"]

        # 1️⃣ Склады
        warehouse_map = {}
        for wh in warehouses_data:
            warehouse, _ = Warehouse.objects.get_or_create(
                code=wh["code"],
                defaults={"name": wh["name"]}
            )
            warehouse_map[wh["code"]] = warehouse

        # 2️⃣ Категории
        category_map = {}

        def import_categories(tree, parent=None):
            for name, content in tree.items():
                category, _ = Category.objects.get_or_create(
                    name=name,
                    parent=parent
                )
                category_map[name] = category

                if isinstance(content, dict):
                    import_categories(
                        {k: v for k, v in content.items() if k != "_items"},
                        parent=category
                    )

        import_categories(categories_data)

        # 3️⃣ Товары, остатки, цены
        product_counter = Product.objects.count()

        def import_products(tree):
            nonlocal product_counter
        
            for name, content in tree.items():
                if not isinstance(content, dict):
                    continue
                
                current_category = category_map.get(name)
        
                items = content.get("_items", [])
                for entry in items:
                    product_counter += 1
                    product_data = entry["product"]
        
                    product = Product.objects.create(
                        code=f"AUTO-{product_counter:06d}",
                        designation=product_data["designation"],
                        manufacturer=product_data.get("manufacturer") or "",
                        description=product_data.get("description"),
                        weight=product_data.get("weight"),
                        length=product_data.get("length"),
                        width=product_data.get("width"),
                        height=product_data.get("height"),
                        category=current_category  # ✅ ВАЖНО
                    )
        
                    for stock in entry["stocks"]:
                        Stock.objects.create(
                            product=product,
                            warehouse=warehouse_map[stock["warehouse"]],
                            amount=stock["amount"] or 0,
                            reserved=stock["reserved"] or 0
                        )
        
                    for price in entry["prices"]:
                        if price["price"] == "on_request":
                            continue
                        
                        Price.objects.create(
                            product=product,
                            price_type=price["price_type"],
                            price=Decimal(price["price"])
                        )
        
                import_products(content)

        import_products(categories_data)

        self.stdout.write(self.style.SUCCESS("Импорт успешно завершён"))
