from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from catalog.models import Product
from .cart import Cart
from .models import Order, OrderItem

@require_POST
def cart_add(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, id=product_id)
    quantity = int(request.POST.get('quantity', 1))
    cart.add(product=product, quantity=quantity)
    # Redirect back to the previous page, or to the cart page as a fallback
    return redirect(request.META.get('HTTP_REFERER', 'cart_detail'))

def cart_remove(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, id=product_id)
    cart.remove(product)
    return redirect('cart_detail')

def cart_detail(request):
    cart = Cart(request)
    return render(request, 'cart/detail.html', {'cart': cart})

@login_required
@require_POST
def order_create(request):
    cart = Cart(request)
    if not cart:
        messages.warning(request, "Ваша корзина пуста.")
        return redirect('cart_detail')
    
    # Check if the user's email is available
    if not request.user.email:
        messages.error(request, "Для оформления заказа необходимо указать email в вашем профиле.")
        return redirect('cart_detail') # Or redirect to profile edit page

    order = Order.objects.create(user=request.user, email=request.user.email)
    
    for item in cart:
        OrderItem.objects.create(
            order=order,
            product=item['product'],
            price=item['price'], # Price at the time of order
            quantity=item['quantity']
        )
    
    cart.clear() # Clear the cart after order is created
    messages.success(request, f"Спасибо за заказ! Информация передана менеджеру, с вами свяжутся по почте {request.user.email} в ближайшее время.")
    return redirect('cart_detail') # Redirect back to cart detail, which will now be empty