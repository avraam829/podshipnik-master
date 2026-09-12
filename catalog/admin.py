import os
import tempfile
from zipfile import BadZipFile
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import path
from openpyxl import Workbook
from .models import Category, Product, Warehouse, Stock, Price, TelegramOrder, TelegramOrderItem
from .importing import EXCEL_HEADERS, import_xlsx, ImportValidationError

admin.site.register(Category)
admin.site.register(Warehouse)
admin.site.register(Stock)
admin.site.register(Price)

class TelegramOrderItemInline(admin.TabularInline):
    model = TelegramOrderItem
    extra = 0
    readonly_fields = ('product','designation','price','quantity')

@admin.register(TelegramOrder)
class TelegramOrderAdmin(admin.ModelAdmin):
    list_display=('id','customer_name','phone','total','status','created_at','telegram_username')
    list_filter=('status','created_at')
    search_fields=('customer_name','phone','telegram_username')
    readonly_fields=('telegram_user_id','telegram_username','created_at','updated_at')
    list_editable=('status',)
    inlines=[TelegramOrderItemInline]

def _xlsx_response(workbook, filename):
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    workbook.save(response)
    return response


def _new_catalog_workbook():
    wb=Workbook()
    ws=wb.active
    ws.title='Products'
    ws.append(EXCEL_HEADERS)
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = 'A1:P1'
    for column, width in enumerate((24, 24, 18, 28, 18, 40, 12, 12, 12, 12, 20, 14, 18, 14, 16, 16), 1):
        ws.column_dimensions[chr(64 + column)].width = width
    return wb, ws


@admin.action(description='Выгрузить выбранные товары в Excel', permissions=['view'])
def export_products_to_excel(modeladmin, request, queryset):
    wb, ws = _new_catalog_workbook()
    for product in queryset.select_related('category__parent').prefetch_related('stocks__warehouse','prices'):
        prices={p.price_type:p.price for p in product.prices.all()}
        stocks=list(product.stocks.all()) or [None]
        for stock in stocks:
            category=product.category
            ws.append([category.parent.name if category and category.parent else '', category.name if category else '',
                product.code,product.designation,product.manufacturer,product.description,
                product.weight,product.length,product.width,product.height,
                stock.warehouse.name if stock else '',stock.amount if stock else 0,stock.reserved if stock else 0,stock.free if stock else 0,
                prices.get('retail',product.price),prices.get('wholesale')])
    # Imported strings must remain text, never executable spreadsheet formulas.
    for row in ws:
        for cell in row:
            if isinstance(cell.value,str):
                cell.data_type='s'
    return _xlsx_response(wb, 'products.xlsx')

class ExcelImportForm(forms.Form):
    file=forms.FileField(
        label='Excel (.xlsx)',
        help_text='До 20 МБ. Нужны все 16 колонок в порядке шаблона; сначала выполните проверку.',
    )
    dry_run=forms.BooleanField(label='Только проверить, без записи в БД',required=False,initial=True)
    def clean_file(self):
        file=self.cleaned_data['file']
        if not file.name.lower().endswith('.xlsx') or file.size>20*1024*1024:
            raise forms.ValidationError('Нужен файл .xlsx размером до 20 MB.')
        return file

class DeleteConfirmForm(forms.Form):
    confirm=forms.BooleanField(label='Подтверждаю удаление всех товаров',required=True)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    readonly_fields=('slug','search_key','has_spaces')
    list_display=('code','designation','manufacturer','category','price')
    list_filter=('category','manufacturer')
    search_fields=('code','designation','manufacturer','description')
    actions=[export_products_to_excel]
    change_list_template='admin/products_changelist.html'
    def get_urls(self):
        return [
            path('import-excel/',self.admin_site.admin_view(self.import_from_excel),name='product_import_excel'),
            path('import-template/',self.admin_site.admin_view(self.import_template),name='product_import_template'),
            path('delete-all/',self.admin_site.admin_view(self.delete_all_view),name='product_delete_all'),
        ] + super().get_urls()
    def import_template(self, request):
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        workbook, _ = _new_catalog_workbook()
        return _xlsx_response(workbook, 'catalog-import-template.xlsx')
    def import_from_excel(self,request):
        if not (self.has_add_permission(request) and self.has_change_permission(request)):
            raise PermissionDenied
        form=ExcelImportForm(request.POST or None,request.FILES or None)
        result = None
        if request.method=='POST' and form.is_valid():
            descriptor, filename=tempfile.mkstemp(suffix='.xlsx')
            try:
                with os.fdopen(descriptor,'wb') as stream:
                    for chunk in form.cleaned_data['file'].chunks():
                        stream.write(chunk)
                result=import_xlsx(filename,dry_run=form.cleaned_data['dry_run'])
                mode='Проверка' if result['dry_run'] else 'Импорт'
                self.message_user(
                    request,
                    f"{mode}: строк {result['rows']}, новых {result['created']}, "
                    f"по существующим кодам {result['updated']}, без изменений {result.get('unchanged',0)}."
                )
                for warning in result.get('warnings',[])[:20]:
                    self.message_user(request,warning,level=messages.WARNING)
            except (ImportValidationError,BadZipFile,ValueError,OSError,KeyError) as error:
                form.add_error('file',str(error))
            finally:
                os.unlink(filename)
        return render(request,'admin/excel_import.html',{
            **self.admin_site.each_context(request), 'form':form, 'opts':self.model._meta,
            'result': result,
        })
    def delete_all_view(self,request):
        if not self.has_delete_permission(request):
            raise PermissionDenied
        form=DeleteConfirmForm(request.POST or None)
        if request.method=='POST' and form.is_valid():
            try:
                with transaction.atomic():
                    Product.objects.all().delete()
                self.message_user(request,'Товары удалены.')
                return redirect('..')
            except ProtectedError:
                self.message_user(request,'Удаление отменено: товары связаны с сохранёнными заказами.',level=messages.ERROR)
        return render(request,'admin/delete_all_confirm.html',{**self.admin_site.each_context(request),
            'form':form,'opts':self.model._meta,'total_products':Product.objects.count(),
            'total_stocks':Stock.objects.count(),'total_prices':Price.objects.count()})
