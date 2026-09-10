from decimal import Decimal
from django.conf import settings
from catalog.services import catalog_queryset

class Cart:
    def __init__(self, request):
        self.session = request.session
        self.cart = self.session.get(settings.CART_SESSION_ID, {}).copy()
    def save(self):
        self.session[settings.CART_SESSION_ID] = self.cart
        self.session.modified = True
    def add(self, product, quantity=1, update_quantity=False):
        key = str(product.pk)
        current = self.cart.get(key, {}).get('quantity', 0)
        total = quantity if update_quantity else current + quantity
        if not 1 <= total <= 9999:
            raise ValueError('Количество должно быть от 1 до 9999.')
        self.cart[key] = {'quantity': total}
        self.save()
    def remove(self, product):
        self.cart.pop(str(product.pk), None)
        self.save()
    def __iter__(self):
        for product in catalog_queryset().filter(pk__in=self.cart):
            quantity = self.cart[str(product.pk)]['quantity']
            price = max(product.effective_price, Decimal(0))
            yield {'product': product, 'quantity': quantity, 'price': price, 'total_price': price * quantity}
    def __len__(self):
        return sum(item['quantity'] for item in self.cart.values())
    def get_total_price(self):
        return sum((item['total_price'] for item in self), Decimal(0))
    def clear(self):
        self.cart = {}
        self.save()
