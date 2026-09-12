from django.contrib import admin
from .models import Order, OrderItem

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    raw_id_fields = ['product']
    extra = 0 # No empty forms by default

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'email', 'status', 'availability_to_clarify', 'created', 'updated', 'paid']
    list_filter = ['status', 'availability_to_clarify', 'paid', 'created', 'updated']
    inlines = [OrderItemInline]
