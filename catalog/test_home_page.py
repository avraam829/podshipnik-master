from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import HomePage, HomePageBlock


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class HomePageTests(TestCase):
    def test_seeded_content(self):
        response = self.client.get('/')
        for text in ['шпиндельных групп', 'ISO 9001:2015', '12 месяцев',
                     'до 36 месяцев', 'на основании отдельного договора',
                     'обучение коллектива', 'Обеспечение резервов']:
            self.assertContains(response, text)

    def test_edit_order_visibility_and_escape(self):
        page = HomePage.objects.get(pk=1)
        page.title = 'Новый заголовок'
        page.save()
        page.blocks.all().delete()
        HomePageBlock.objects.create(page=page, title='Поздний блок', body='<script>alert(1)</script>\n\nВторой абзац', position=20)
        HomePageBlock.objects.create(page=page, title='Первый блок', body='Текст', position=10)
        HomePageBlock.objects.create(page=page, title='Скрытый блок', body='Скрытый', is_visible=False)
        response = self.client.get('/')
        self.assertContains(response, 'Новый заголовок')
        self.assertNotContains(response, 'Скрытый блок')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;')
        content = response.content.decode()
        self.assertLess(content.index('Первый блок'), content.index('Поздний блок'))

    def test_admin_can_save_page_and_inline(self):
        user = get_user_model().objects.create_superuser(username='editor', password='test-password')
        self.client.force_login(user)
        page = HomePage.objects.get(pk=1)
        page.blocks.all().delete()
        url = reverse('admin:catalog_homepage_change', args=[1])
        self.assertContains(self.client.get(url), 'Заголовок блока')
        response = self.client.post(url, {
            'title': 'Из админки', 'intro': 'Вступление', 'catalog_label': 'Каталог',
            'blocks-TOTAL_FORMS': '1', 'blocks-INITIAL_FORMS': '0',
            'blocks-MIN_NUM_FORMS': '0', 'blocks-MAX_NUM_FORMS': '1000',
            'blocks-0-title': 'Новый блок', 'blocks-0-body': 'Сохранённый текст',
            'blocks-0-position': '10', 'blocks-0-is_visible': 'on', '_save': 'Сохранить',
        })
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get('/'), 'Сохранённый текст')

    def test_anonymous_admin_denied(self):
        response = self.client.get(reverse('admin:catalog_homepage_change', args=[1]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)
