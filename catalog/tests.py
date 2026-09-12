import json
from decimal import Decimal
from tempfile import NamedTemporaryFile
from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook
from .models import Product, Price, Stock, Warehouse, Category
from .services import normalize_designation, numeric_price, offer_sort_key, product_slug, catalog_queryset, ordered_products
from .importing import import_xlsx, ImportValidationError

@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'], SITE_URL='http://testserver', PRIMARY_DOMAIN='testserver')
class CatalogTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Подшипники')
        self.a = Product.objects.create(code='fag', designation='7212-B-XL-MP-UA', manufacturer='FAG', price=7124, category=self.category)
        self.b = Product.objects.create(code='skf', designation='7212 BEP', manufacturer='SKF', price=6800, category=self.category)
        self.c = Product.objects.create(code='skf2', designation='7212 BECBP', manufacturer='SKF', price=0, category=self.category)

    def test_numeric_order(self):
        self.assertEqual(list(ordered_products(catalog_queryset())), [self.b,self.a,self.c])
        self.assertEqual(sorted([self.c,self.a,self.b], key=offer_sort_key), [self.b,self.a,self.c])

    def test_retail_price_source(self):
        Price.objects.create(product=self.a, price_type='retail', price=6000)
        self.assertEqual(ordered_products(catalog_queryset()).first(), self.a)

    def test_normalized_search(self):
        for query in ['7212BEP', '7212 BEP', '7212-BEP', '7212 bep', '7212\u00a0BEP']:
            response = self.client.get('/search/', {'q':query})
            self.assertContains(response, self.b.get_absolute_url())
            self.assertNotContains(response, self.a.get_absolute_url())

    def test_permanent_slug_and_collision(self):
        old = self.a.slug
        self.a.designation = 'New designation'
        self.a.save()
        self.assertEqual(old, self.a.slug)
        twin = Product.objects.create(code='other', designation=self.b.designation, manufacturer='SKF')
        self.assertNotEqual(twin.slug, self.b.slug)

    def test_legacy_redirect(self):
        response = self.client.get(reverse('product_detail', args=[self.a.pk]))
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], self.a.get_absolute_url())

    def test_product_seo_and_404(self):
        response = self.client.get(self.a.get_absolute_url())
        self.assertEqual(response.status_code,200)
        self.assertContains(response, 'rel="canonical"', count=1)
        self.assertContains(response, '<h1>Подшипник 7212-B-XL-MP-UA</h1>', html=True)
        self.assertNotContains(response, 'noindex')
        schema = response.content.decode().split('<script type="application/ld+json">')[1].split('</script>')[0]
        self.assertEqual(json.loads(schema)['name'], self.a.designation)
        self.assertEqual(self.client.get('/podshipniki/absent/').status_code,404)

    def test_sitemap(self):
        response = self.client.get('/sitemap-products.xml')
        self.assertContains(response, self.a.get_absolute_url())
        self.assertContains(self.client.get('/sitemap.xml'), 'sitemap-products.xml')
        self.assertContains(self.client.get('/robots.txt'), 'http://testserver/sitemap.xml')

    def test_pagination_filter(self):
        for i in range(30):
            Product.objects.create(code=f'x{i}', designation=f'Test {i}', price=i+1)
        response = self.client.get('/catalog/', {'page':2})
        self.assertEqual(len(response.context['products']),9)
        self.assertContains(response, 'page=2', count=None)
        filtered = self.client.get('/catalog/', {'manufacturer':'FAG'})
        self.assertEqual(filtered.context['page_obj'].paginator.count,1)
        self.assertContains(filtered, 'noindex')

    def test_availability_sentinel(self):
        warehouse = Warehouse.objects.create(code='w',name='Склад')
        Stock.objects.create(product=self.a,warehouse=warehouse,amount=9999)
        response = self.client.get(self.a.get_absolute_url())
        self.assertContains(response, 'Наличие уточняйте')
        self.assertNotContains(response, '9999 шт.')

    def test_suggestions_plain_text(self):
        self.b.designation = '7212 <img src=x onerror=alert(1)>'
        self.b.save()
        response = self.client.get('/api/search-suggestions/', {'q':'7212'})
        self.assertEqual(response.status_code,200)
        self.assertTrue(any('<img' in p['designation'] for p in response.json()['suggestions']))
        page = self.client.get(self.b.get_absolute_url())
        self.assertNotContains(page, '<img src=x')
        self.assertContains(page, '&lt;img')

    def test_price_ties_spaces_and_brands(self):
        self.a.price = self.b.price
        self.a.save()
        self.assertEqual(ordered_products(catalog_queryset()).first(),self.a)

class UtilityTests(SimpleTestCase):
    def test_normalize_unicode(self):
        self.assertEqual(normalize_designation(' 7212\u00a0—BEP '),'7212bep')
        self.assertNotEqual(normalize_designation('7212-BEP'),normalize_designation('7212-BECBP'))
    def test_prices(self):
        for value in [None,'',0,'0','NaN','Infinity',-1]:
            self.assertIsNone(numeric_price(value))
        self.assertEqual(numeric_price('1\u00a0234,50'),Decimal('1234.50'))
        self.assertLess(numeric_price('9'),numeric_price('100'))
    def test_slug(self):
        self.assertEqual(product_slug('7212--BEP','SKF','a'),product_slug('7212--BEP','SKF','a'))
        self.assertIn('7212-bep',product_slug('7212--BEP','SKF','a'))

@override_settings(DEBUG=True,SECURE_SSL_REDIRECT=False)
class ImportTests(TestCase):
    def workbook(self, rows):
        handle=NamedTemporaryFile(suffix='.xlsx',delete=False)
        handle.close()
        self.addCleanup(__import__('os').unlink,handle.name)
        wb=Workbook()
        wb.active.append(['Родительская категория','Категория','Код','Маркировка','Производитель','Описание','Вес','Длина','Ширина','Высота','Склад','Количество','Зарезервировано','Свободно','Цена Розница','Цена Опт'])
        for row in rows: wb.active.append(row)
        wb.save(handle.name)
        return handle.name
    def row(self, code=None,price=100):
        return ['Подшипники','Шариковые',code,'7212 BEP','SKF','',None,None,None,None,'Склад',9999,0,None,price,None]
    def test_dry_run_and_repeat(self):
        path=self.workbook([self.row()])
        self.assertEqual(import_xlsx(path)['created'],1)
        self.assertEqual(Product.objects.count(),0)
        import_xlsx(path,False)
        self.assertEqual(import_xlsx(path,False)['unchanged'],1)
        self.assertEqual(Product.objects.count(),1)
    def test_changed_no_code_refused(self):
        import_xlsx(self.workbook([self.row()]),False)
        with self.assertRaises(ImportValidationError):
            import_xlsx(self.workbook([self.row(price=200)]),False)
        self.assertEqual(Product.objects.get().price,100)
    def test_code_updates_preserve_url(self):
        path=self.workbook([self.row(code='known')])
        import_xlsx(path,False)
        slug=Product.objects.get().slug
        import_xlsx(self.workbook([self.row(code='known',price=50)]),False)
        product=Product.objects.get()
        self.assertEqual(product.price,50)
        self.assertEqual(product.slug,slug)
        self.assertEqual(Price.objects.get().price,50)
    def test_invalid_rows_atomic(self):
        bad=self.row(code='bad',price=-1)
        with self.assertRaises(ImportValidationError):
            import_xlsx(self.workbook([self.row(),bad]),False)
        self.assertEqual(Product.objects.count(),0)
    def test_excel_error_is_unknown(self):
        result=import_xlsx(self.workbook([self.row(price='#VALUE!')]),False)
        self.assertEqual(len(result['warnings']),1)
        self.assertEqual(Product.objects.get().price,0)

    def test_multiple_warehouses_roundtrip(self):
        first=self.row(code='multi')
        second=self.row(code='multi')
        second[10]='Другой склад'
        result=import_xlsx(self.workbook([first,second]),False)
        self.assertEqual(result['created'],1)
        self.assertEqual(Product.objects.count(),1)
        self.assertEqual(Stock.objects.count(),2)
        self.assertEqual(Price.objects.count(),1)

    def test_conflicting_code_rejected(self):
        with self.assertRaises(ImportValidationError):
            import_xlsx(self.workbook([self.row(code='same'),self.row(code='same',price=200)]),False)
        self.assertEqual(Product.objects.count(),0)


@override_settings(DEBUG=True,SECURE_SSL_REDIRECT=False,ALLOWED_HOSTS=['testserver'])
class AdminPermissionsTests(TestCase):
    def test_staff_without_model_permissions(self):
        from django.contrib.auth import get_user_model
        user=get_user_model().objects.create_user(username='staff',password='test-only-pass',is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get('/admin/catalog/product/import-excel/').status_code,403)
        self.assertEqual(self.client.get('/admin/catalog/product/delete-all/').status_code,403)


@override_settings(DEBUG=False,SECURE_SSL_REDIRECT=False,ALLOWED_HOSTS=['primary.example','alias.example','127.0.0.1'],PRIMARY_DOMAIN='primary.example',SITE_URL='https://primary.example')
class DomainTests(TestCase):
    def test_alias_preserves_path_query(self):
        response=self.client.get('/search/?q=7212',HTTP_HOST='alias.example')
        self.assertEqual(response.status_code,301)
        self.assertEqual(response['Location'],'https://primary.example/search/?q=7212')
    def test_health_does_not_redirect(self):
        self.assertEqual(self.client.get('/health/',HTTP_HOST='127.0.0.1').status_code,200)
