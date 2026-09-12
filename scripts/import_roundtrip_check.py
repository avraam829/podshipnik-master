"""Export/reimport the real catalog on a temporary SQLite copy; source stays read-only."""
import io
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
source = Path(sys.argv[1] if len(sys.argv) > 1 else '/data/db.sqlite3').resolve(strict=True)
with tempfile.TemporaryDirectory(prefix='sba-import-check-') as directory:
    temporary = Path(directory)
    database = temporary / 'catalog.sqlite3'
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as original:
        with sqlite3.connect(database) as copy:
            original.backup(copy)
    os.environ['DATABASE_PATH'] = str(database)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connections
    from catalog.admin import export_products_to_excel
    from catalog.importing import import_xlsx
    from catalog.models import Product, Stock, Warehouse
    from catalog.services import catalog_queryset

    call_command('migrate', interactive=False, stdout=io.StringIO())
    fields = ('id', 'code', 'designation', 'manufacturer', 'description', 'weight',
              'length', 'width', 'height', 'category_id', 'slug')
    products_before = list(Product.objects.order_by('pk').values_list(*fields))
    prices_before = list(catalog_queryset().order_by('pk').values_list('pk', 'effective_price'))
    stocks_before = list(Stock.objects.order_by('pk').values_list('product_id', 'warehouse_id', 'amount', 'reserved', 'free'))
    warehouses_before = Warehouse.objects.count()
    workbook = temporary / 'catalog.xlsx'
    workbook.write_bytes(export_products_to_excel(None, None, Product.objects.all()).content)
    preview = import_xlsx(workbook)
    applied = import_xlsx(workbook, dry_run=False)
    assert products_before == list(Product.objects.order_by('pk').values_list(*fields)), 'Product identity/content changed'
    assert prices_before == list(catalog_queryset().order_by('pk').values_list('pk', 'effective_price')), 'Effective prices changed'
    assert stocks_before == list(Stock.objects.order_by('pk').values_list('product_id', 'warehouse_id', 'amount', 'reserved', 'free')), 'Stocks changed'
    assert warehouses_before == Warehouse.objects.count(), 'Warehouses duplicated'
    connections.close_all()
    print(json.dumps({'source_products': len(products_before), 'preview': preview, 'applied': applied,
                      'identity_content_prices_stocks_preserved': True, 'source_read_only': True}, ensure_ascii=False, indent=2))
