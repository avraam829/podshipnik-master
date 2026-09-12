from django.db import models
from django.conf import settings
from catalog.models import Product
import uuid

class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Cart for {self.user.username}'

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f'{self.quantity} of {self.product.designation}'


class Order(models.Model):
    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Заявка принята"),
        (STATUS_CONFIRMED, "Подтверждена"),
        (STATUS_CANCELLED, "Отменена"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders', verbose_name="Пользователь")
    email = models.EmailField(verbose_name="Email")
    contact_name = models.CharField(max_length=150, blank=True, default="", verbose_name="Контактное лицо")
    phone = models.CharField(max_length=32, blank=True, default="", verbose_name="Телефон")
    company = models.CharField(max_length=255, blank=True, default="", verbose_name="Компания")
    comment = models.TextField(blank=True, default="", verbose_name="Комментарий")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, verbose_name="Статус")
    availability_to_clarify = models.BooleanField(default=False, verbose_name="Наличие требует уточнения")
    idempotency_key = models.UUIDField(null=True, blank=True, unique=True, default=None, editable=False)
    created = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated = models.DateTimeField(auto_now=True, verbose_name="Обновлен")
    paid = models.BooleanField(default=False, verbose_name="Оплачен")

    class Meta:
        ordering = ['-created']
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'

    def __str__(self):
        return f'Заказ {self.id} от {self.user.username}'

    def get_total_cost(self):
        return sum(item.get_cost() for item in self.items.all())


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name="Заказ")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name="Товар")
    designation = models.CharField(max_length=255, blank=True, default="", verbose_name="Обозначение на момент заявки")
    product_code = models.CharField(max_length=100, blank=True, default="", verbose_name="Код товара на момент заявки")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена")
    quantity = models.PositiveIntegerField(default=1, verbose_name="Количество")

    class Meta:
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказа'

    def __str__(self):
        return str(self.id)

    def get_cost(self):
        return self.price * self.quantity
