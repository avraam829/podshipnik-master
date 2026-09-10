from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название")
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="Родительская категория",
    )

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        return self.name


class Product(models.Model):
    slug = models.SlugField(max_length=400, unique=True, allow_unicode=True, editable=False)
    search_key = models.CharField(max_length=255, db_index=True, editable=False)
    has_spaces = models.BooleanField(default=False, editable=False)
    code = models.CharField(
        max_length=100, unique=True, verbose_name="Внутренний код"
    )
    designation = models.CharField(
        max_length=255, verbose_name="Маркировка производителя"
    )
    manufacturer = models.CharField(
        max_length=100, blank=True, default="", verbose_name="Производитель"
    )
    description = models.TextField(
        blank=True, default="", verbose_name="Описание"
    )
    weight = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True, verbose_name="Вес"
    )
    length = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Длина"
    )
    width = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Ширина"
    )
    height = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Высота"
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        verbose_name="Категория",
    )
    price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, verbose_name="Цена"
    )

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        indexes = [
            models.Index(fields=["designation"]),
            models.Index(fields=["manufacturer"]),
        ]

    def __str__(self):
        return f"{self.designation} ({self.manufacturer})"

    def save(self, *args, **kwargs):
        from .services import normalize_designation, product_slug
        self.search_key = normalize_designation(self.designation)
        self.has_spaces = any(c.isspace() for c in self.designation.strip())
        if not self.slug:
            self.slug = product_slug(self.designation, self.manufacturer, self.code)
        if kwargs.get('update_fields'):
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'search_key', 'has_spaces', 'slug'}
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('product_canonical', args=[self.slug])


class Warehouse(models.Model):
    code = models.CharField(
        max_length=50, unique=True, verbose_name="Код склада"
    )
    name = models.CharField(max_length=255, verbose_name="Название")

    class Meta:
        verbose_name = "Склад"
        verbose_name_plural = "Склады"

    def __str__(self):
        return self.name


class Stock(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="stocks", verbose_name="Товар"
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, related_name="stocks", verbose_name="Склад"
    )
    amount = models.IntegerField(default=0, verbose_name="Количество")
    reserved = models.IntegerField(default=0, verbose_name="Зарезервировано")
    free = models.IntegerField(default=0, verbose_name="Свободно")

    class Meta:
        verbose_name = "Остаток"
        verbose_name_plural = "Остатки"
        unique_together = ("product", "warehouse")

    def save(self, *args, **kwargs):
        self.free = self.amount - self.reserved
        super().save(*args, **kwargs)


class Price(models.Model):
    PRICE_TYPES = (
        ("retail", "Розница"),
        ("wholesale", "Опт"),
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="prices", verbose_name="Товар"
    )
    price_type = models.CharField(
        max_length=20, choices=PRICE_TYPES, verbose_name="Тип цены"
    )
    price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Цена"
    )

    class Meta:
        verbose_name = "Цена"
        verbose_name_plural = "Цены"
        unique_together = ("product", "price_type")


# ═══════════════════════════════════════════
# Telegram Orders
# ═══════════════════════════════════════════

class TelegramOrder(models.Model):
    STATUS_CHOICES = (
        ("new", "Новый"),
        ("confirmed", "Подтверждён"),
        ("processing", "В обработке"),
        ("shipped", "Отправлен"),
        ("delivered", "Доставлен"),
        ("cancelled", "Отменён"),
    )

    telegram_user_id = models.BigIntegerField(verbose_name="Telegram ID")
    telegram_username = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Username"
    )
    customer_name = models.CharField(
        max_length=255, verbose_name="Имя клиента"
    )
    phone = models.CharField(max_length=50, verbose_name="Телефон")
    address = models.TextField(
        blank=True, default="", verbose_name="Адрес доставки"
    )
    comment = models.TextField(
        blank=True, default="", verbose_name="Комментарий"
    )
    total = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name="Сумма"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="new",
        verbose_name="Статус",
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name="Создан"
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Обновлён"
    )

    class Meta:
        verbose_name = "Заказ (Telegram)"
        verbose_name_plural = "Заказы (Telegram)"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Заказ #{self.id} — {self.customer_name}"


class TelegramOrderItem(models.Model):
    order = models.ForeignKey(
        TelegramOrder, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True
    )
    designation = models.CharField(
        max_length=255, verbose_name="Маркировка"
    )
    price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Цена"
    )
    quantity = models.IntegerField(default=1, verbose_name="Количество")

    class Meta:
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказа"

    def __str__(self):
        return f"{self.designation} × {self.quantity}"

    @property
    def subtotal(self):
        return self.price * self.quantity
