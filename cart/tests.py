from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from catalog.models import Product
from .models import Order
@override_settings(DEBUG=True,SECURE_SSL_REDIRECT=False,ALLOWED_HOSTS=['testserver'])
class CartTests(TestCase):
    def setUp(self):
        self.product=Product.objects.create(code='x',designation='7212',price=100)
    def test_quantity_validation(self):
        for value in ['bad',0,-1,10000]:
            response=self.client.post(f'/cart/add/{self.product.pk}/',{'quantity':value})
            self.assertEqual(response.status_code,302)
            self.assertFalse(self.client.session.get('cart'))
    def test_cart_serializes_and_current_price(self):
        self.client.post(f'/cart/add/{self.product.pk}/',{'quantity':2})
        response=self.client.get('/cart/')
        self.assertEqual(response.status_code,200)
        self.product.price=150
        self.product.save()
        self.assertContains(self.client.get('/cart/'),'300')
    def test_get_cannot_mutate(self):
        self.assertEqual(self.client.get(f'/cart/add/{self.product.pk}/').status_code,405)
        self.assertEqual(self.client.get(f'/cart/remove/{self.product.pk}/').status_code,405)
    def test_order(self):
        user=get_user_model().objects.create_user(username='buyer',password='test-only-pass',email='buyer@example.com')
        self.client.force_login(user)
        self.client.post(f'/cart/add/{self.product.pk}/',{'quantity':2})
        response=self.client.post('/cart/create_order/')
        self.assertEqual(response.status_code,302)
        self.assertEqual(Order.objects.count(),1)
        self.assertEqual(Order.objects.get().get_total_cost(),200)
        self.assertFalse(self.client.session['cart'])
