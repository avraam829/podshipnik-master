from django.contrib import admin
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django import forms
from django.urls import path
from django.db import transaction, connection
from django.contrib import messages
from decimal import Decimal, InvalidOperation
import re
import os
import tempfile
from django.core.exceptions import PermissionDenied
from .importing import import_xlsx, ImportValidationError

from openpyxl import Workbook, load_workbook

from .models import (
    Category, Product, Warehouse, Stock, Price,
    TelegramOrder, TelegramOrderItem,
)

admin.site.register(Category)
admin.site.register(Warehouse)
admin.site.register(Stock)
admin.site.register(Price)


# ── Telegram Orders в админке ────────────────

class TelegramOrderItemInline(admin.TabularInline):
    model = TelegramOrderItem
    extra = 0
    readonly_fields = ("product", "designation", "price", "quantity")


@admin.register(TelegramOrder)
class TelegramOrderAdmin(admin.ModelAdmin):
    list_display = (
        "id", "customer_name", "phone", "total",
        "status", "created_at", "telegram_username",
    )
    list_filter = ("status", "created_at")
    search_fields = ("customer_name", "phone", "telegram_username")
    readonly_fields = (
        "telegram_user_id", "telegram_username",
        "created_at", "updated_at",
    )
    list_editable = ("status",)
    inlines = [TelegramOrderItemInline]


# ── Утилиты ──────────────────────────────────

def to_decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def to_int(value):
    if value in (None, ""):
        return 0
    try:
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return 0


def clean_code(value):
    if value in (None, ""):
        return ""
    s = str(value).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


# ── Экспорт ──────────────────────────────────

def export_products_to_excel(modeladmin, request, queryset):
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"

    ws.append([
        "Родительская категория", "Категория", "Код",
        "Маркировка", "Производитель", "Описание",
        "Вес", "Длина", "Ширина", "Высота",
        "Склад", "Количество", "Зарезервировано", "Свободно",
        "Цена (Розница)", "Цена (Опт)",
    ])

    queryset = queryset.prefetch_related(
        "stocks__warehouse", "prices", "category__parent"
    )

    for p in queryset:
        parent = (
            p.category.parent.name
            if p.category and p.category.parent else ""
        )
        cat = p.category.name if p.category else ""
        prices = {x.price_type: x.price for x in p.prices.all()}

        if p.stocks.exists():
            for s in p.stocks.all():
                ws.append([
                    parent, cat, p.code, p.designation,
                    p.manufacturer, p.description,
                    p.weight, p.length, p.width, p.height,
                    s.warehouse.name, s.amount, s.reserved, s.free,
                    prices.get("retail"), prices.get("wholesale"),
                ])
        else:
            ws.append([
                parent, cat, p.code, p.designation,
                p.manufacturer, p.description,
                p.weight, p.length, p.width, p.height,
                "", "", "", "",
                prices.get("retail"), prices.get("wholesale"),
            ])

    resp = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet"
        )
    )
    resp["Content-Disposition"] = 'attachment; filename="products.xlsx"'
    wb.save(resp)
    return resp


export_products_to_excel.short_description = "Выгрузить в Excel"


# ── Пакетное удаление товаров ────────────────

def delete_products_in_batches(modeladmin, request, queryset):
    """Удаление выбранных товаров партиями по 500 штук."""
    BATCH_SIZE = 500
    product_ids = list(queryset.values_list('id', flat=True))
    total_count = len(product_ids)

    if total_count == 0:
        modeladmin.message_user(
            request,
            "Не выбрано ни одного товара для удаления.",
            level=messages.WARNING,
        )
        return

    deleted_count = 0
    errors = []

    for start in range(0, total_count, BATCH_SIZE):
        batch_ids = product_ids[start:start + BATCH_SIZE]
        try:
            with transaction.atomic():
                Stock.objects.filter(product_id__in=batch_ids).delete()
                Price.objects.filter(product_id__in=batch_ids).delete()
                TelegramOrderItem.objects.filter(
                    product_id__in=batch_ids
                ).delete()
                Product.objects.filter(id__in=batch_ids).delete()
                deleted_count += len(batch_ids)
        except Exception as e:
            errors.append(
                f"Пакет {start + 1}-{start + len(batch_ids)}: {e}"
            )

    if errors:
        modeladmin.message_user(
            request,
            f"Удалено {deleted_count} из {total_count} товаров. "
            f"Ошибок: {len(errors)}",
            level=messages.WARNING,
        )
        for err in errors[:10]:
            modeladmin.message_user(request, err, level=messages.ERROR)
    else:
        modeladmin.message_user(
            request,
            f"Успешно удалено {deleted_count} товаров ✅",
            level=messages.SUCCESS,
        )


delete_products_in_batches.short_description = "🗑️ Удалить выбранные (пакетно)"


def delete_all_products(modeladmin, request, queryset):
    """Удаление ВСЕХ товаров из базы партиями."""
    BATCH_SIZE = 1000
    total_count = Product.objects.count()

    if total_count == 0:
        modeladmin.message_user(
            request, "База товаров уже пуста.", level=messages.INFO
        )
        return

    deleted_count = 0
    errors = []

    while True:
        batch_ids = list(
            Product.objects.values_list('id', flat=True)[:BATCH_SIZE]
        )
        if not batch_ids:
            break
        try:
            with transaction.atomic():
                Stock.objects.filter(product_id__in=batch_ids).delete()
                Price.objects.filter(product_id__in=batch_ids).delete()
                TelegramOrderItem.objects.filter(
                    product_id__in=batch_ids
                ).delete()
                Product.objects.filter(id__in=batch_ids).delete()
                deleted_count += len(batch_ids)
        except Exception as e:
            errors.append(f"Ошибка при удалении пакета: {e}")
            break

    if errors:
        modeladmin.message_user(
            request,
            f"Удалено {deleted_count} из {total_count} товаров. "
            f"Ошибки: {len(errors)}",
            level=messages.WARNING,
        )
        for err in errors[:5]:
            modeladmin.message_user(request, err, level=messages.ERROR)
    else:
        modeladmin.message_user(
            request,
            f"Полная очистка завершена: удалено {deleted_count} товаров ✅",
            level=messages.SUCCESS,
        )


delete_all_products.short_description = "⚠️ Удалить ВСЕ товары (полная очистка)"


def delete_all_products_fast(modeladmin, request, queryset):
    """Быстрое удаление через RAW SQL."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM products_stock")
            cursor.execute("DELETE FROM products_price")
            cursor.execute("DELETE FROM products_telegramorderitem")
            cursor.execute("DELETE FROM products_product")
        modeladmin.message_user(
            request,
            "Все товары и связанные данные удалены (быстрый режим) ✅",
            level=messages.SUCCESS,
        )
    except Exception as e:
        modeladmin.message_user(
            request,
            f"Ошибка при быстром удалении: {e}",
            level=messages.ERROR,
        )


delete_all_products_fast.short_description = "⚡ БЫСТРО удалить ВСЕ (SQL)"


# ── Формы ─────────────────────────────────────

class ExcelImportForm(forms.Form):
    dry_run = forms.BooleanField(label='Только проверить, без записи в БД', required=False, initial=True)
    file = forms.FileField(
        label="Excel файл (.xlsx)",
        help_text="Максимальный размер файла: 200 MB",
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        # Проверка расширения
        name = f.name.lower()
        if not (name.endswith(".xlsx") or name.endswith(".xls")):
            raise forms.ValidationError(
                "Допустимы только файлы .xlsx и .xls"
            )
        # Проверка размера (200 MB)
        if f.size > 200 * 1024 * 1024:
            raise forms.ValidationError(
                f"Файл слишком большой: "
                f"{f.size // 1024 // 1024} MB. Максимум 200 MB."
            )
        return f


class DeleteConfirmForm(forms.Form):
    confirm = forms.BooleanField(
        label="Я подтверждаю удаление всех товаров",
        required=True,
    )


# ── Константы ─────────────────────────────────

DEFAULT_WAREHOUSE = "Основной склад"
IMPORT_BATCH_SIZE = 200


# ── Вспомогательная функция импорта ──────────

def _save_upload_to_tmp(uploaded_file) -> str:
    """
    Сохраняет загруженный файл во временный файл на диске.
    Возвращает путь к временному файлу.
    Работает и с InMemoryUploadedFile, и с TemporaryUploadedFile.
    """
    suffix = os.path.splitext(uploaded_file.name)[-1] or ".xlsx"
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        os.close(tmp_fd)
        # Если файл уже на диске (TemporaryUploadedFile) — просто читаем
        uploaded_file.seek(0)
        with open(tmp_path, "wb") as out:
            for chunk in uploaded_file.chunks(chunk_size=1024 * 1024):  # 1MB chunks
                out.write(chunk)
    except Exception:
        os.unlink(tmp_path)
        raise
    return tmp_path


def _process_import_row(
    row_data,
    cat_cache,
    wh_cache,
    auto_num,
):
    """
    Обрабатывает одну строку Excel.
    Возвращает (success: bool, new_auto_num: int, error_msg: str | None)
    """
    row = list(row_data) + [None] * 16
    (
        parent_name, category_name, code,
        designation, manufacturer, description,
        weight, length, width, height,
        warehouse_name, amount, reserved, _,
        retail_price, wholesale_price,
    ) = row[:16]

    # Пропускаем полностью пустые строки
    if not any([parent_name, category_name, code, designation]):
        return True, auto_num, None

    # ── Категории ──────────────────────────
    parent = None
    if parent_name:
        pn = str(parent_name).strip()
        key = (pn, None)
        if key not in cat_cache:
            obj, _ = Category.objects.get_or_create(
                name=pn, parent=None
            )
            cat_cache[key] = obj
        parent = cat_cache[key]

    category = None
    if category_name:
        cn = str(category_name).strip()
        pid = parent.id if parent else None
        key = (cn, pid)
        if key not in cat_cache:
            obj, _ = Category.objects.get_or_create(
                name=cn, parent=parent
            )
            cat_cache[key] = obj
        category = cat_cache[key]

    # ── Числа ──────────────────────────────
    weight_d    = to_decimal(weight)
    length_d    = to_decimal(length)
    width_d     = to_decimal(width)
    height_d    = to_decimal(height)
    amount_i    = to_int(amount)
    reserved_i  = to_int(reserved)
    retail_d    = to_decimal(retail_price)
    wholesale_d = to_decimal(wholesale_price)

    product_data = {
        "designation": str(designation).strip() if designation else "",
        "manufacturer": str(manufacturer).strip() if manufacturer else "",
        "description":  str(description).strip()  if description  else "",
        "weight":   weight_d,
        "length":   length_d,
        "width":    width_d,
        "height":   height_d,
        "category": category,
        "price": retail_d if retail_d is not None else Decimal("0.00"),
    }

    # ── Товар ──────────────────────────────
    code_clean = clean_code(code)
    if code_clean:
        product, _ = Product.objects.update_or_create(
            code=code_clean,
            defaults=product_data,
        )
    else:
        product = Product.objects.create(
            code=f"AUTO-{auto_num:06d}",
            **product_data,
        )
        auto_num += 1

    # ── Цены ───────────────────────────────
    if retail_d is not None:
        Price.objects.update_or_create(
            product=product,
            price_type="retail",
            defaults={"price": retail_d},
        )
    if wholesale_d is not None:
        Price.objects.update_or_create(
            product=product,
            price_type="wholesale",
            defaults={"price": wholesale_d},
        )

    # ── Склад ──────────────────────────────
    wh_name = str(warehouse_name).strip() if warehouse_name else ""
    if not wh_name and amount_i > 0:
        wh_name = DEFAULT_WAREHOUSE

    if wh_name:
        if wh_name not in wh_cache:
            obj, _ = Warehouse.objects.get_or_create(
                name=wh_name,
                defaults={"code": wh_name.upper()[:50]},
            )
            wh_cache[wh_name] = obj

        Stock.objects.update_or_create(
            product=product,
            warehouse=wh_cache[wh_name],
            defaults={
                "amount":   amount_i,
                "reserved": reserved_i,
            },
        )

    return True, auto_num, None


# ── ProductAdmin ──────────────────────────────

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    readonly_fields = ("code",)
    list_display = (
        "code", "designation", "manufacturer", "category", "price",
    )
    list_filter  = ("category", "manufacturer")
    search_fields = ("code", "designation", "manufacturer", "description")
    actions = [
        export_products_to_excel,
        delete_products_in_batches,
        delete_all_products,
    ]
    change_list_template = "admin/products_changelist.html"

    # ── URLs ─────────────────────────────────

    def get_urls(self):
        return [
            path(
                "import-excel/",
                self.admin_site.admin_view(self.import_from_excel),
                name="product_import_excel",
            ),
            path(
                "delete-all/",
                self.admin_site.admin_view(self.delete_all_view),
                name="product_delete_all",
            ),
        ] + super().get_urls()

    # ── Удаление всех товаров ─────────────

    def delete_all_view(self, request):
        """Страница подтверждения полного удаления товаров."""
        if not self.has_delete_permission(request):
            raise PermissionDenied
        if request.method == "POST":
            form = DeleteConfirmForm(request.POST)
            if form.is_valid():
                BATCH_SIZE = 1000
                deleted_count = 0

                while True:
                    batch_ids = list(
                        Product.objects.values_list('id', flat=True)[:BATCH_SIZE]
                    )
                    if not batch_ids:
                        break
                    with transaction.atomic():
                        Stock.objects.filter(
                            product_id__in=batch_ids
                        ).delete()
                        Price.objects.filter(
                            product_id__in=batch_ids
                        ).delete()
                        TelegramOrderItem.objects.filter(
                            product_id__in=batch_ids
                        ).delete()
                        Product.objects.filter(id__in=batch_ids).delete()
                        deleted_count += len(batch_ids)

                self.message_user(
                    request,
                    f"Удалено {deleted_count} товаров ✅",
                    level=messages.SUCCESS,
                )
                return redirect("..")
        else:
            form = DeleteConfirmForm()

        context = {
            "form":           form,
            "total_products": Product.objects.count(),
            "total_stocks":   Stock.objects.count(),
            "total_prices":   Price.objects.count(),
            "opts":           self.model._meta,
            "title":          "Удаление всех товаров",
        }
        return render(request, "admin/delete_all_confirm.html", context)

    # ── Импорт ───────────────────────────────

    def import_from_excel(self, request):
        if not (self.has_add_permission(request) and self.has_change_permission(request)):
            raise PermissionDenied
        form = ExcelImportForm(request.POST or None, request.FILES or None)
        if request.method == 'POST' and form.is_valid():
            path = _save_upload_to_tmp(form.cleaned_data['file'])
            try:
                result = import_xlsx(path, dry_run=form.cleaned_data['dry_run'])
                self.message_user(request, str(result), level=messages.SUCCESS)
            except (ImportValidationError, ValueError, OSError) as error:
                form.add_error('file', str(error))
            finally:
                os.unlink(path)
        return render(request, 'admin/excel_import.html', {'form': form, 'opts': self.model._meta})

    def legacy_import_from_excel(self, request):
        if request.method != "POST":
            return render(
                request,
                "admin/excel_import.html",
                {"form": ExcelImportForm()},
            )

        form = ExcelImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(
                request, "admin/excel_import.html", {"form": form}
            )

        uploaded_file = form.cleaned_data["file"]

        # ── Сохраняем файл на диск ───────────
        try:
            tmp_path = _save_upload_to_tmp(uploaded_file)
        except Exception as e:
            self.message_user(
                request,
                f"Не удалось сохранить файл: {e}",
                level=messages.ERROR,
            )
            return render(
                request, "admin/excel_import.html", {"form": form}
            )

        # ── Читаем и импортируем ─────────────
        try:
            wb = load_workbook(tmp_path, read_only=True, data_only=True)
            ws = wb.active

            # Кеши — загружаем один раз
            cat_cache: dict = {}
            for c in Category.objects.select_related("parent").all():
                cat_cache[(c.name, c.parent_id)] = c

            wh_cache: dict = {}
            for w in Warehouse.objects.all():
                wh_cache[w.name] = w

            last_auto = (
                Product.objects
                .filter(code__startswith="AUTO-")
                .order_by("-code")
                .values_list("code", flat=True)
                .first()
            )
            m = re.search(r"AUTO-(\d+)", last_auto) if last_auto else None
            auto_num = int(m.group(1)) + 1 if m else 1

            errors   = []
            imported = 0

            # ── Потоковая обработка пакетами ──
            current_batch      = []
            current_batch_start = 2  # Номер строки первой строки в пакете

            def flush_batch(batch_rows, start_line):
                """Записывает пакет строк в БД."""
                nonlocal imported, auto_num

                try:
                    with transaction.atomic():
                        for idx, raw_row in enumerate(batch_rows):
                            line = start_line + idx
                            try:
                                ok, auto_num, err = _process_import_row(
                                    raw_row, cat_cache, wh_cache, auto_num
                                )
                                if ok and err is None:
                                    imported += 1
                                elif err:
                                    errors.append(f"Строка {line}: {err}")
                            except Exception as row_err:
                                errors.append(
                                    f"Строка {line}: {row_err}"
                                )
                except Exception as tx_err:
                    errors.append(
                        f"Транзакция строк {start_line}–"
                        f"{start_line + len(batch_rows) - 1}: {tx_err}"
                    )

            for raw_row in ws.iter_rows(min_row=2, values_only=True):
                current_batch.append(raw_row)

                if len(current_batch) >= IMPORT_BATCH_SIZE:
                    flush_batch(current_batch, current_batch_start)
                    current_batch_start += len(current_batch)
                    current_batch = []

            # Остаток
            if current_batch:
                flush_batch(current_batch, current_batch_start)

            wb.close()

        finally:
            # Удаляем временный файл в любом случае
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        # ── Результат ────────────────────────
        if errors:
            self.message_user(
                request,
                f"Импорт: {imported} записей, ошибок: {len(errors)}",
                level=messages.WARNING,
            )
            for err in errors[:20]:
                self.message_user(request, err, level=messages.ERROR)
        else:
            self.message_user(
                request,
                f"Импорт завершён: {imported} записей ✅",
                level=messages.SUCCESS,
            )

        return redirect("..")
