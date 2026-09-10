"""Transactional XLSX import. Original spreadsheets are never modified."""
import hashlib
import json
from decimal import Decimal, InvalidOperation
from openpyxl import load_workbook
from django.db import transaction
from .models import Category, Product, Price, Stock, Warehouse
from .services import normalize_designation, product_slug


class ImportValidationError(ValueError):
    pass


def decimal_cell(value, field, line):
    if value in (None, ''):
        return None
    try:
        number = Decimal(str(value).replace('\u00a0', '').replace(' ', '').replace(',', '.'))
        if not number.is_finite() or number < 0 or number >= 10000000:
            raise InvalidOperation
        return number
    except (InvalidOperation, ValueError):
        raise ImportValidationError(f'Строка {line}: некорректное поле {field}.')


def read_rows(path):
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        if sheet.max_row > 100001 or sheet.max_column != 16:
            raise ImportValidationError('Ожидаются 16 колонок и не более 100 000 строк.')
        iterator = sheet.iter_rows(values_only=True)
        header = next(iterator)
        def key(value):
            return ''.join(c for c in str(value or '').casefold() if c.isalnum())
        expected = ['Родительская категория', 'Категория', 'Код', 'Маркировка', 'Производитель', 'Описание', 'Вес', 'Длина', 'Ширина', 'Высота', 'Склад', 'Количество', 'Зарезервировано', 'Свободно', 'Цена Розница', 'Цена Опт']
        if [key(v) for v in header] != [key(v) for v in expected]:
            raise ImportValidationError('Заголовки Excel не соответствуют шаблону экспорта.')
        rows = []
        warnings = []
        for line, values in enumerate(iterator, 2):
            if not any(v is not None for v in values):
                continue
            row = list(values)
            if row[3] is None or not str(row[3]).strip():
                raise ImportValidationError(f'Строка {line}: отсутствует маркировка.')
            for index in (0, 1, 2, 3, 4, 5, 10):
                row[index] = str(row[index]) if row[index] is not None else ''
            row[2] = row[2].strip()
            if len(row[3]) > 255 or len(row[4]) > 100 or len(row[2]) > 100:
                raise ImportValidationError(f'Строка {line}: слишком длинная маркировка, бренд или код.')
            for index in (6, 7, 8, 9, 11, 12, 14, 15):
                if index in (14, 15) and str(row[index]).startswith(('#VALUE!', '#N/A', '#REF!', '#DIV/0!', '#NUM!')):
                    warnings.append(f'Строка {line}: ошибка Excel {row[index]} в цене; цена по запросу.')
                    row[index] = None
                row[index] = decimal_cell(row[index], expected[index], line)
            for index in (11, 12):
                if row[index] is not None and row[index] != row[index].to_integral_value():
                    raise ImportValidationError(f'Строка {line}: количество должно быть целым.')
            if (row[12] or 0) > (row[11] or 0):
                raise ImportValidationError(f'Строка {line}: резерв больше остатка.')
            rows.append(row)
        return rows, warnings
    finally:
        workbook.close()


def import_xlsx(path, dry_run=True):
    rows, warnings = read_rows(path)
    digest = hashlib.sha256(json.dumps(rows, ensure_ascii=False, default=str).encode()).hexdigest()
    missing_codes = any(not row[2] for row in rows)
    prefix = f'XLS-{digest[:16]}-'
    # A no-code file can be loaded once into an empty catalog. Its exact repeat is a no-op.
    # A changed no-code file cannot safely be mapped onto existing products.
    if missing_codes and Product.objects.exists():
        imported_codes = set(Product.objects.filter(code__startswith=prefix).values_list('code', flat=True))
        if all(row[2] or f'{prefix}{i:06d}' in imported_codes for i, row in enumerate(rows, 1)):
            return {'rows': len(rows), 'created': 0, 'updated': 0, 'unchanged': len(rows), 'dry_run': dry_run, 'warnings': warnings}
        raise ImportValidationError('В файле отсутствуют коды, а каталог уже заполнен. Сначала выгрузите каталог с кодами и перенесите изменения в этот файл. Автоматическое сопоставление неоднозначно; данные не изменены.')
    seen = set()
    for row in rows:
        if row[2] and row[2] in seen:
            raise ImportValidationError(f'Повтор кода {row[2]}: объедините данные или задайте отдельные коды. Данные не изменены.')
        seen.add(row[2])
    existing = set(Product.objects.filter(code__in=[r[2] for r in rows if r[2]]).values_list('code', flat=True))
    result = {'rows': len(rows), 'created': sum(r[2] not in existing for r in rows), 'updated': sum(r[2] in existing for r in rows), 'dry_run': dry_run, 'warnings': warnings}
    if dry_run:
        return result
    with transaction.atomic():
        # SQLite obtains a write lock before checking again; unique codes protect other backends.
        if missing_codes and Product.objects.exists():
            raise ImportValidationError('Каталог изменился во время проверки. Повторите предварительную проверку.')
        categories, warehouses = {}, {}
        new_products, stock_specs, price_specs = [], [], []
        for i, row in enumerate(rows, 1):
            parent_name, name, code, designation, brand, description = row[:6]
            parent = None
            if parent_name:
                parent = categories.setdefault((parent_name, None), None)
                if parent is None:
                    parent, _ = Category.objects.get_or_create(name=parent_name, parent=None)
                    categories[(parent_name, None)] = parent
            category = None
            if name:
                key = (name, parent.pk if parent else None)
                if key not in categories:
                    categories[key], _ = Category.objects.get_or_create(name=name, parent=parent)
                category = categories[key]
            code = code or f'{prefix}{i:06d}'
            fields = dict(designation=designation, manufacturer=brand, description=description,
                weight=row[6], length=row[7], width=row[8], height=row[9], category=category, price=row[14] or Decimal(0))
            if code in existing:
                product = Product.objects.get(code=code)
                for field, value in fields.items():
                    setattr(product, field, value)
                product.save()
            else:
                product = Product(code=code, **fields, slug=product_slug(designation, brand, code),
                    search_key=normalize_designation(designation), has_spaces=any(c.isspace() for c in designation.strip()))
                new_products.append(product)
            warehouse_name = row[10] or 'Основной склад'
            if warehouse_name not in warehouses:
                wh_code = 'WH-' + hashlib.sha256(warehouse_name.encode()).hexdigest()[:20]
                warehouses[warehouse_name], _ = Warehouse.objects.get_or_create(code=wh_code, defaults={'name': warehouse_name})
            stock_specs.append((code, warehouses[warehouse_name], int(row[11] or 0), int(row[12] or 0)))
            price_specs.append((code, row[14], row[15]))
        Product.objects.bulk_create(new_products, batch_size=500)
        products = {p.code: p for p in Product.objects.filter(code__in=[s[0] for s in stock_specs])}
        new_stocks, new_prices = [], []
        for code, warehouse, amount, reserved in stock_specs:
            if code in existing:
                Stock.objects.update_or_create(product=products[code], warehouse=warehouse,
                    defaults={'amount': amount, 'reserved': reserved, 'free': amount - reserved})
            else:
                new_stocks.append(Stock(product=products[code], warehouse=warehouse, amount=amount, reserved=reserved, free=amount-reserved))
        for code, retail, wholesale in price_specs:
            for kind, value in [('retail', retail), ('wholesale', wholesale)]:
                if code in existing:
                    if value is None:
                        Price.objects.filter(product=products[code], price_type=kind).delete()
                    else:
                        Price.objects.update_or_create(product=products[code], price_type=kind, defaults={'price': value})
                elif value is not None:
                    new_prices.append(Price(product=products[code], price_type=kind, price=value))
        Stock.objects.bulk_create(new_stocks, batch_size=500)
        Price.objects.bulk_create(new_prices, batch_size=500)
    return result
