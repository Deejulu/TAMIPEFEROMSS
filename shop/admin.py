from django.contrib import admin
from .models import Product, Cart, CartItem, Order, OrderItem


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "price", "stock_quantity", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "description"]
    list_editable = ["price", "stock_quantity", "is_active"]


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ["subtotal"]


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["pk", "user", "session_key", "item_count", "total", "created_at"]
    inlines = [CartItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["subtotal"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["pk", "user", "status", "total", "created_at"]
    list_filter = ["status"]
    search_fields = ["user__email"]
    inlines = [OrderItemInline]
