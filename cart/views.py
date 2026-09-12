from decimal import Decimal
from uuid import UUID, uuid4

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from catalog.models import Product
from catalog.services import catalog_queryset
from .cart import Cart
from .models import Order, OrderItem

class QuantityForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, max_value=9999)


class CheckoutForm(forms.Form):
    checkout_token = forms.CharField(widget=forms.HiddenInput)
    contact_name = forms.CharField(label="Контактное лицо", max_length=150)
    email = forms.EmailField(label="Рабочий email")
    phone = forms.CharField(label="Телефон", max_length=32, required=False)
    company = forms.CharField(label="Компания", max_length=255, required=False)
    comment = forms.CharField(
        label="Комментарий к заявке",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 4}),
    )


def _checkout_token(request):
    token = request.session.get("checkout_token")
    if not token:
        token = str(uuid4())
        request.session["checkout_token"] = token
    return token


def _checkout_initial(request, token):
    user = request.user
    return {
        "checkout_token": token,
        "contact_name": user.first_name or user.username,
        "email": user.email,
        "phone": user.phone,
        "company": user.company,
    }


def _cart_items_for_checkout(request, lock=False):
    """Load products again and validate session quantities before saving an order."""
    raw_cart = Cart(request).cart
    if not raw_cart:
        raise ValueError("Ваша корзина пуста.")

    quantities = {}
    for raw_product_id, payload in raw_cart.items():
        try:
            product_id = int(raw_product_id)
            quantity = payload["quantity"]
        except (KeyError, TypeError, ValueError):
            raise ValueError("Состав корзины изменился. Проверьте позиции и повторите попытку.")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 9999:
            raise ValueError("Количество каждой позиции должно быть целым числом от 1 до 9999.")
        quantities[product_id] = quantity

    products = catalog_queryset().filter(pk__in=quantities)
    if lock:
        products = products.select_for_update()
    products = list(products)
    if len(products) != len(quantities):
        raise ValueError("Одна из позиций больше недоступна в каталоге. Проверьте корзину.")

    items = []
    availability_to_clarify = False
    for product in products:
        price = max(product.effective_price or Decimal("0"), Decimal("0"))
        availability_to_clarify = availability_to_clarify or bool(product.unknown_stock)
        items.append({"product": product, "quantity": quantities[product.pk], "price": price})
    return items, availability_to_clarify


def _render_checkout(request, form, items=None):
    if items is None:
        try:
            items, availability_to_clarify = _cart_items_for_checkout(request)
        except ValueError as error:
            messages.warning(request, str(error))
            return redirect("cart_detail")
    else:
        availability_to_clarify = any(item.get("availability_to_clarify", False) for item in items)
    known_total = sum((item["price"] * item["quantity"] for item in items), Decimal("0"))
    return render(request, "cart/checkout.html", {
        "form": form,
        "items": items,
        "known_total": known_total,
        "availability_to_clarify": availability_to_clarify,
    })

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
    cart.remove_by_id(product_id)
    return redirect('cart_detail')


@require_POST
def cart_update(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    form = QuantityForm(request.POST)
    if form.is_valid():
        Cart(request).add(product, form.cleaned_data['quantity'], update_quantity=True)
    else:
        messages.error(request, 'Укажите целое количество от 1 до 9999.')
    return redirect('cart_detail')


def cart_detail(request):
    cart = Cart(request)
    # Resolve/prune deleted positions before the template checks cart length.
    list(cart)
    return render(request, 'cart/detail.html', {'cart': cart})


@login_required(login_url="login")
@require_http_methods(["GET", "POST"])
def checkout(request):
    if request.method == "GET":
        token = _checkout_token(request)
        return _render_checkout(request, CheckoutForm(initial=_checkout_initial(request, token)))
    return _submit_checkout(request)


def _submit_checkout(request, legacy=False):
    data = request.POST.copy()
    if legacy and not data.get("contact_name"):
        token = _checkout_token(request)
        defaults = _checkout_initial(request, token)
        for field, value in defaults.items():
            if not data.get(field):
                data[field] = value
    form = CheckoutForm(data)
    if not form.is_valid():
        return _render_checkout(request, form)

    try:
        token = UUID(form.cleaned_data["checkout_token"])
    except (TypeError, ValueError, AttributeError):
        form.add_error(None, "Не удалось подтвердить заявку. Обновите страницу оформления и повторите попытку.")
        return _render_checkout(request, form)

    existing = Order.objects.filter(user=request.user, idempotency_key=token).first()
    if existing:
        return redirect("order_confirmation", order_id=existing.pk)

    if request.session.get("checkout_token") != str(token):
        form.add_error(None, "Страница оформления устарела. Обновите её и повторите попытку.")
        return _render_checkout(request, form)

    try:
        with transaction.atomic():
            items, availability_to_clarify = _cart_items_for_checkout(request, lock=True)
            order = Order.objects.create(
                user=request.user,
                email=form.cleaned_data["email"],
                contact_name=form.cleaned_data["contact_name"],
                phone=form.cleaned_data["phone"],
                company=form.cleaned_data["company"],
                comment=form.cleaned_data["comment"],
                availability_to_clarify=availability_to_clarify,
                idempotency_key=token,
            )
            OrderItem.objects.bulk_create([
                OrderItem(
                    order=order,
                    product=item["product"],
                    designation=item["product"].designation,
                    product_code=item["product"].code,
                    price=item["price"],
                    quantity=item["quantity"],
                )
                for item in items
            ])
    except ValueError as error:
        form.add_error(None, str(error))
        return _render_checkout(request, form)
    except IntegrityError:
        order = Order.objects.get(user=request.user, idempotency_key=token)

    Cart(request).clear()
    request.session.pop("checkout_token", None)
    return redirect("order_confirmation", order_id=order.pk)


@login_required(login_url="login")
@require_POST
def order_create(request):
    """Compatibility endpoint for existing clients posting directly from the cart."""
    return _submit_checkout(request, legacy=True)


@login_required(login_url="login")
def order_confirmation(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__product"), pk=order_id, user=request.user
    )
    return render(request, "cart/confirmation.html", {"order": order})
