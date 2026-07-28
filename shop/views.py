import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.urls import reverse

from .models import Product, Cart, CartItem, Order, OrderItem, Category
from admin_dashboard.models import SiteContent


def _get_or_create_cart(request):
    """
    Get the user's cart or create one.
    
    For authenticated users, links cart to user.
    For anonymous users, uses session key.
    """
    if request.user.is_authenticated:
        cart, created = Cart.objects.get_or_create(user=request.user)
    else:
        session_key = request.session.session_key
        if not session_key:
            request.session.save()
            session_key = request.session.session_key
        cart, created = Cart.objects.get_or_create(
            session_key=session_key,
            defaults={"user": None},
        )
    return cart


def product_list(request):
    """
    Display all active products in a grid layout, grouped by category.
    """
    products = Product.objects.filter(is_active=True).select_related('category').order_by("-created_at")
    categories = Category.objects.all().order_by('name')
    
    products_by_category = {}
    for product in products:
        cat_name = product.category.name if product.category else "Uncategorized"
        products_by_category.setdefault(cat_name, []).append(product)
    
    cart = _get_or_create_cart(request)
    cart_item_ids = set(cart.items.values_list("product_id", flat=True))
    
    # Get homepage hero and shop banner content
    homepage_hero = SiteContent.get_section_content('homepage_hero')
    shop_banner = SiteContent.get_section_content('shop_banner')

    context = {
        "products": products,
        "categories": categories,
        "products_by_category": products_by_category,
        "cart": cart,
        "cart_item_ids": cart_item_ids,
        "homepage_hero": homepage_hero,
        "shop_banner": shop_banner,
    }
    return render(request, "shop/product_list.html", context)


def cart_view(request):
    """
    Display the user's cart with all items and total.
    """
    cart = _get_or_create_cart(request)
    context = {
        "cart": cart,
    }
    return render(request, "shop/cart.html", context)


@require_POST
def add_to_cart(request, product_id):
    """
    Add a product to the cart.
    
    If the product is already in the cart, increment quantity.
    Returns JSON for AJAX requests, redirect for regular form posts.
    """
    product = get_object_or_404(Product, pk=product_id, is_active=True)

    if not product.in_stock:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "error": _("Out of stock")}, status=400)
        messages.error(request, _("This product is out of stock."))
        return redirect("shop:product_list")

    cart = _get_or_create_cart(request)
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={"quantity": 1},
    )

    if not created:
        cart_item.quantity += 1
        cart_item.save()

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "success": True,
            "item_count": cart.item_count,
            "cart_total": str(cart.total),
            "message": _("Added to cart"),
        })

    messages.success(request, _("Added to cart."))
    return redirect("shop:product_list")


@require_POST
def remove_from_cart(request, item_id):
    """
    Remove an item from the cart.
    """
    cart = _get_or_create_cart(request)
    cart_item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    cart_item.delete()

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "success": True,
            "item_count": cart.item_count,
            "cart_total": str(cart.total),
            "is_empty": cart.is_empty,
        })

    messages.success(request, _("Removed from cart."))
    return redirect("shop:cart")


@require_POST
def update_cart_item(request, item_id):
    """
    Update the quantity of a cart item.
    """
    cart = _get_or_create_cart(request)
    cart_item = get_object_or_404(CartItem, pk=item_id, cart=cart)

    try:
        data = json.loads(request.body)
        quantity = int(data.get("quantity", 1))
    except (json.JSONDecodeError, ValueError, TypeError):
        quantity = int(request.POST.get("quantity", 1))

    if quantity < 1:
        cart_item.delete()
    else:
        if quantity > cart_item.product.stock_quantity:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({
                    "success": False,
                    "error": _("Not enough stock available"),
                }, status=400)
            messages.error(request, _("Not enough stock available."))
            return redirect("shop:cart")

        cart_item.quantity = quantity
        cart_item.save()

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "success": True,
            "item_count": cart.item_count,
            "cart_total": str(cart.total),
            "item_subtotal": str(cart_item.subtotal) if cart_item.pk else "0",
            "is_empty": cart.is_empty,
        })

    return redirect("shop:cart")


@login_required
def checkout(request):
    """
    Convert the cart into an Order and initiate payment.

    Flow:
    1. Get the user's cart
    2. Validate cart is not empty
    3. Check minimum order amount
    4. Get enabled payment methods
    5. Create Order + OrderItems from cart contents
    6. Clear the cart
    7. Render checkout page with enabled payment methods
    """
    from admin_dashboard.models import PaymentMethodSetting, MinimumOrderAmount
    
    cart = _get_or_create_cart(request)

    if cart.is_empty:
        messages.error(request, _("Your cart is empty."))
        return redirect("shop:cart")

    # Check minimum order amount
    min_order = MinimumOrderAmount.get_instance()
    if min_order.enabled and min_order.minimum_amount > 0:
        if cart.total < min_order.minimum_amount:
            messages.error(
                request,
                _("Your cart total (₦{:.2f}) is below the minimum order amount of ₦{:.2f}. "
                  "Please add more items to your cart.").format(cart.total, min_order.minimum_amount)
            )
            return redirect("shop:cart")

    # Get enabled payment methods
    enabled_payment_methods = []
    for method, label in PaymentMethodSetting.PAYMENT_METHOD_CHOICES:
        if PaymentMethodSetting.is_enabled(method):
            enabled_payment_methods.append({'code': method, 'label': label})
    
    # Ensure at least one payment method is enabled
    if not enabled_payment_methods:
        messages.error(
            request,
            _("No payment methods are currently available. Please contact support.")
        )
        return redirect("shop:cart")

    order = Order.objects.create(
        user=request.user,
        status=Order.Status.PENDING,
        total=cart.total,
    )

    for cart_item in cart.items.select_related("product"):
        OrderItem.objects.create(
            order=order,
            product=cart_item.product,
            product_name=cart_item.product.name,
            quantity=cart_item.quantity,
            price=cart_item.product.price,
        )

    cart.items.all().delete()

    return render(request, "shop/checkout.html", {
        "order": order,
        "paystack_public_key": settings.PAYSTACK_PUBLIC_KEY,
        "paystack_amount": int(order.total * 100),
        "enabled_payment_methods": enabled_payment_methods,
    })


@require_POST
@login_required
def paystack_callback(request):
    """
    Handle Paystack webhook/callback for payment confirmation.

    Verifies the transaction with Paystack, creates a Payment record,
    updates Order status, and decrements stock only on success.
    """
    try:
        data = json.loads(request.body)
        reference = data.get("reference")
    except (json.JSONDecodeError, AttributeError):
        reference = request.POST.get("reference")

    if not reference:
        return JsonResponse({"success": False, "error": "No reference provided"}, status=400)

    import urllib.request
    import urllib.error

    verify_url = f"https://api.paystack.co/transaction/verify/{reference}"
    req = urllib.request.Request(verify_url)
    req.add_header("Authorization", f"Bearer {settings.PAYSTACK_SECRET_KEY}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            result = json.loads(body)
    except urllib.error.URLError:
        return JsonResponse({"success": False, "error": "Paystack verification failed"}, status=500)

    if not result.get("status"):
        return JsonResponse({"success": False, "error": "Paystack verification unsuccessful"}, status=400)

    transaction_data = result.get("data", {})
    status = transaction_data.get("status", "")
    amount = transaction_data.get("amount", 0) / 100  # Paystack returns in kobo
    reference = transaction_data.get("reference", reference)

    order_id = request.POST.get("order_id")
    try:
        order = Order.objects.get(pk=order_id, user=request.user)
    except Order.DoesNotExist:
        return JsonResponse({"success": False, "error": "Order not found"}, status=404)

    payment, created = Payment.objects.get_or_create(
        order=order,
        reference=reference,
        defaults={
            "amount": amount,
            "status": "success" if status == "success" else "failed",
            "paystack_response": transaction_data,
        },
    )

    if status == "success" and created:
        order.status = Order.Status.PAID
        order.save(update_fields=["status"])
        for item in order.items.select_related("product").all():
            product = item.product
            if product:
                old_stock = product.stock_quantity
                product.decrement_stock(item.quantity)
                new_stock = product.stock_quantity
                if old_stock > settings.LOW_STOCK_THRESHOLD and new_stock <= settings.LOW_STOCK_THRESHOLD:
                    from notifications.utils import maybe_notify_low_stock
                    maybe_notify_low_stock(product, old_stock, new_stock)
        return JsonResponse({"success": True, "message": "Payment confirmed"})
    else:
        payment.status = "failed"
        payment.save(update_fields=["status"])
        return JsonResponse({"success": False, "error": "Payment failed"}, status=400)


def about_page(request):
    """
    Public About page that pulls content from SiteContent model.
    Accessible to all users (logged in or not).
    """
    about_content = SiteContent.get_section_content('about')
    
    context = {
        'about_content': about_content,
        'page_title': 'About Us',
    }
    
    return render(request, 'shop/about.html', context)


def contact_page(request):
    """
    Public Contact page that pulls content from SiteContent model.
    Accessible to all users (logged in or not).
    """
    contact_content = SiteContent.get_section_content('contact')
    
    context = {
        'contact_content': contact_content,
        'page_title': 'Contact Us',
    }
    
    return render(request, 'shop/contact.html', context)


def faq_page(request):
    """
    Public FAQ page that pulls content from SiteContent model.
    Accessible to all users (logged in or not).
    """
    faq_content = SiteContent.get_section_content('faq')
    
    context = {
        'faq_content': faq_content,
        'page_title': 'FAQ',
    }
    
    return render(request, 'shop/faq.html', context)


def delivery_info_page(request):
    """
    Public Delivery Information page that pulls content from SiteContent model.
    Accessible to all users (logged in or not).
    """
    delivery_content = SiteContent.get_section_content('delivery_info')
    
    context = {
        'delivery_content': delivery_content,
        'page_title': 'Delivery Information',
    }
    
    return render(request, 'shop/delivery_info.html', context)


def terms_privacy_page(request):
    """
    Public Terms & Privacy page that pulls content from SiteContent model.
    Accessible to all users (logged in or not).
    """
    terms_content = SiteContent.get_section_content('terms_privacy')
    
    context = {
        'terms_content': terms_content,
        'page_title': 'Terms & Privacy',
    }
    
    return render(request, 'shop/terms_privacy.html', context)


def return_refund_page(request):
    """
    Public Return & Refund Policy page that pulls content from SiteContent model.
    Accessible to all users (logged in or not).
    """
    return_content = SiteContent.get_section_content('return_refund')
    
    context = {
        'return_content': return_content,
        'page_title': 'Return & Refund Policy',
    }
    
    return render(request, 'shop/return_refund.html', context)
