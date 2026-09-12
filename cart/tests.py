from django.test import Client, TestCase, override_settings
from django.contrib.auth import get_user_model
from catalog.models import Product, Stock, Warehouse
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
        self.assertEqual(self.client.get(f'/cart/update/{self.product.pk}/').status_code,405)

    def test_cart_quantity_can_be_updated_from_cart(self):
        self.client.post(f'/cart/add/{self.product.pk}/', {'quantity': 1})
        response = self.client.post(f'/cart/update/{self.product.pk}/', {'quantity': 3})
        self.assertRedirects(response, '/cart/', fetch_redirect_response=False)
        self.assertEqual(self.client.session['cart'][str(self.product.pk)]['quantity'], 3)
        self.client.post(f'/cart/update/{self.product.pk}/', {'quantity': 0})
        self.assertEqual(self.client.session['cart'][str(self.product.pk)]['quantity'], 3)
    def test_order(self):
        user=get_user_model().objects.create_user(username='buyer',password='test-only-pass',email='buyer@example.com')
        self.client.force_login(user)
        self.client.post(f'/cart/add/{self.product.pk}/',{'quantity':2})
        response=self.client.post('/cart/create_order/')
        self.assertEqual(response.status_code,302)
        self.assertEqual(Order.objects.count(),1)
        self.assertEqual(Order.objects.get().get_total_cost(),200)
        self.assertFalse(self.client.session['cart'])
        from django.db.models.deletion import ProtectedError
        with self.assertRaises(ProtectedError):
            self.product.delete()

    def _checkout_data(self, user, **overrides):
        self.client.force_login(user)
        self.client.get('/cart/checkout/')
        data = {
            'checkout_token': self.client.session['checkout_token'],
            'contact_name': 'Иван Петров',
            'email': user.email,
            'phone': '+7 900 000-00-00',
            'company': 'ООО Тест',
            'comment': 'Нужна спецификация.',
        }
        data.update(overrides)
        return data

    def test_checkout_requires_login_and_csrf(self):
        response = self.client.get('/cart/checkout/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/users/login/', response['Location'])

        user = get_user_model().objects.create_user(username='csrf', password='test-only-pass', email='csrf@example.com')
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(user)
        response = csrf_client.post('/cart/checkout/', {})
        self.assertEqual(response.status_code, 403)

    def test_checkout_refreshes_price_and_is_idempotent(self):
        user = get_user_model().objects.create_user(username='refresh', password='test-only-pass', email='refresh@example.com')
        self.client.force_login(user)
        self.client.post(f'/cart/add/{self.product.pk}/', {'quantity': 2})
        data = self._checkout_data(user)
        self.product.price = 150
        self.product.save()

        response = self.client.post('/cart/checkout/', data)
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.items.get().price, 150)
        self.assertEqual(order.get_total_cost(), 300)
        self.assertEqual(order.contact_name, 'Иван Петров')

        replay = self.client.post('/cart/checkout/', data)
        self.assertEqual(replay.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)
        self.assertIn(f'/cart/orders/{order.pk}/confirmation/', replay['Location'])

    def test_order_history_and_confirmation_are_owner_scoped(self):
        User = get_user_model()
        owner = User.objects.create_user(username='owner', password='test-only-pass', email='owner@example.com')
        outsider = User.objects.create_user(username='outsider', password='test-only-pass', email='outsider@example.com')
        foreign_order = Order.objects.create(user=outsider, email=outsider.email, contact_name='Other')
        own_order = Order.objects.create(user=owner, email=owner.email, contact_name='Owner')
        Order.objects.filter(pk=own_order.pk).update(status=Order.STATUS_CONFIRMED)

        self.client.force_login(owner)
        response = self.client.get('/users/account/')
        self.assertContains(response, f'Заявка №{own_order.pk}')
        self.assertNotContains(response, f'Заявка №{foreign_order.pk}')
        self.assertEqual(self.client.get(f'/cart/orders/{foreign_order.pk}/confirmation/').status_code, 404)
        self.assertEqual(self.client.get(f'/cart/orders/{own_order.pk}/confirmation/').status_code, 200)

    def test_unknown_stock_is_saved_as_availability_to_clarify(self):
        user = get_user_model().objects.create_user(username='stock', password='test-only-pass', email='stock@example.com')
        warehouse = Warehouse.objects.create(code='unknown', name='Уточняется')
        Stock.objects.create(product=self.product, warehouse=warehouse, amount=9999)
        self.client.force_login(user)
        self.client.post(f'/cart/add/{self.product.pk}/', {'quantity': 1})
        response = self.client.post('/cart/checkout/', self._checkout_data(user))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Order.objects.get().availability_to_clarify)

    def test_cart_can_remove_a_product_deleted_after_it_was_added(self):
        self.client.post(f'/cart/add/{self.product.pk}/', {'quantity': 1})
        product_id = self.product.pk
        self.product.delete()
        response = self.client.post(f'/cart/remove/{product_id}/')
        self.assertRedirects(response, '/cart/', fetch_redirect_response=False)
        self.assertFalse(self.client.session.get('cart'))

    def test_order_item_keeps_catalog_identity_snapshot(self):
        user = get_user_model().objects.create_user(username='snapshot', password='test-only-pass', email='snapshot@example.com')
        self.client.force_login(user)
        self.client.post(f'/cart/add/{self.product.pk}/', {'quantity': 1})
        self.client.post('/cart/checkout/', self._checkout_data(user))
        item = Order.objects.get().items.get()
        self.assertEqual(item.designation, '7212')
        self.assertEqual(item.product_code, 'x')

    def test_deleted_product_does_not_leave_an_uncheckoutable_cart(self):
        self.client.post(f'/cart/add/{self.product.pk}/', {'quantity': 1})
        self.product.delete()
        response = self.client.get('/cart/')
        self.assertContains(response, 'Корзина пуста')
        self.assertFalse(self.client.session.get('cart'))
