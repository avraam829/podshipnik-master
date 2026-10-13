import tempfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings

from scripts.configure_domains import ALIASES, configure
from .models import Category


class DomainConfigTests(SimpleTestCase):
    def test_preserves_secrets_and_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            original = '# Config\nDJANGO_SECRET_KEY=unchanged\nTG_BOT_TOKEN=unchanged\nADDITIONAL_DOMAINS=old.example\nSITE_DOMAINS=gpz5.ru,old.example\n'
            path.write_text(original, encoding='utf-8')
            configure(path)
            content = path.read_text(encoding='utf-8')
            self.assertIn('DJANGO_SECRET_KEY=unchanged\n', content)
            self.assertIn('TG_BOT_TOKEN=unchanged\n', content)
            self.assertIn('old.example', content)
            site_domains = next(line.split('=', 1)[1] for line in content.splitlines() if line.startswith('SITE_DOMAINS='))
            self.assertTrue(all(token.endswith(',') for token in site_domains.split()[:-1]))
            self.assertEqual([token.rstrip(',') for token in site_domains.split()], ['gpz5.ru', *ALIASES, 'old.example'])
            for domain in ALIASES:
                self.assertIn(domain, content)
            self.assertEqual(len(list((path.parent / 'backups').iterdir())), 1)
            configure(path)
            self.assertEqual(path.read_text(encoding='utf-8'), content)


@override_settings(DEBUG=False, SECURE_SSL_REDIRECT=False,
                   ALLOWED_HOSTS=['gpz5.ru', *ALIASES],
                   PRIMARY_DOMAIN='gpz5.ru', SITE_URL='https://gpz5.ru')
class ProductionDomainTests(TestCase):
    def test_all_aliases_preserve_paths(self):
        for domain in ALIASES:
            with self.subTest(domain=domain):
                response = self.client.get('/catalog/?page=2', HTTP_HOST=domain)
                self.assertEqual(response.status_code, 301)
                self.assertEqual(response['Location'], 'https://gpz5.ru/catalog/?page=2')


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False,
                   ALLOWED_HOSTS=['testserver'], PRIMARY_DOMAIN='testserver',
                   SITE_URL='http://testserver')
class CategorySeoTests(TestCase):
    def test_sitemaps_have_no_exclusion_header(self):
        for url in ['/sitemap.xml', '/sitemap-pages.xml', '/sitemap-products.xml', '/sitemap-categories.xml']:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn('X-Robots-Tag', response.headers)
        self.assertIn('noindex', self.client.get('/search/').headers['X-Robots-Tag'])

    def test_categories_in_sitemap(self):
        category = Category.objects.create(name='Precision bearings')
        self.assertContains(self.client.get('/sitemap.xml'), '/sitemap-categories.xml')
        self.assertContains(self.client.get('/sitemap-categories.xml'), f'http://testserver/category/{category.pk}/')
        response = self.client.get(f'/category/{category.pk}/')
        self.assertContains(response, 'name="description" content="Precision bearings.')
        self.assertNotContains(response, 'noindex')
