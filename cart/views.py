from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django import forms
from catalog.models import Product
from .cart import Cart
from .models import Order, OrderItem

class QuantityForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, max_value=9999)

@require_POST
def cart_add(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, pk=product_id)
    form = QuantityForm(request.POST)
    if form.is_valid():
        try:
            cart.add(product, form.cleaned_data['quantity'])
            messages.success(request, 'Товар добавлен в корзину.')
        except ValueError as error:
            messages.error(request, str(error))
    else:
        messages.error(request, 'Укажите целое количество от 1 до 9999.')
    return redirect(product.get_absolute_url())

@require_POST
def cart_remove(request, product_id):
    cart = Cart(request)
    cart.remove(get_object_or_404(Product, pk=product_id))
    return redirect('cart_detail')

def cart_detail(request):
    return render(request, 'cart/detail.html', {'cart': Cart(request)})

@login_required
@require_POST
def order_create(request):
    cart = Cart(request)
    if not request.user.email:
        messages.error(request, 'Для оформления заказа необходим email в профиле.')
        return redirect('cart_detail')
    with transaction.atomic():
        items = list(cart)
        if not items:
            messages.warning(request, 'Ваша корзина пуста.')
            return redirect('cart_detail')
        order = Order.objects.create(user=request.user, email=request.user.email)
        OrderItem.objects.bulk_create([OrderItem(order=order, product=item['product'], price=item['price'], quantity=item['quantity']) for item in items])
    cart.clear()
    messages.success(request, f'Заявка №{order.pk} сохранена. Итоговую стоимость и наличие подтвердит менеджер.')
    return redirect('cart_detail')
