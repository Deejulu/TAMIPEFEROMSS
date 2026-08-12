import hashlib
import hmac
import json
import uuid
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.urls import reverse

from .models import Product, Cart, CartItem, Order, OrderItem, Category, Payment
from admin_dashboard.models import DeliveryOption, PaymentMethodSetting, MinimumOrderAmount, SiteContent


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


def _available_delivery_options():
    """Ensure checkout has sensible defaults until an admin customizes delivery."""
    defaults = (
        (DeliveryOption.Code.SAME_DAY, 1),
        (DeliveryOption.Code.STANDARD, 3),
        (DeliveryOption.Code.ECONOMY, 7),
    )
    for code, days in defaults:
        DeliveryOption.objects.get_or_create(
            code=code,
            defaults={"estimated_days": days},
        )
    return DeliveryOption.objects.filter(enabled=True)


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
    cart_item_quantities = {
        item.product_id: item.quantity
        for item in cart.items.select_related("product").all()
    }
    
    # Annotate products with cart quantity for easy template access
    for product in products:
        product.cart_quantity = cart_item_quantities.get(product.id, 0)
    
    # Get homepage hero and shop banner content
    homepage_hero = SiteContent.get_section_content('homepage_hero')
    shop_banner = SiteContent.get_section_content('shop_banner')

    context = {
        "products": products,
        "categories": categories,
        "products_by_category": products_by_category,
        "cart": cart,
        "cart_item_ids": cart_item_ids,
        "cart_item_quantities": cart_item_quantities,
        "homepage_hero": homepage_hero,
        "shop_banner": shop_banner,
    }
    return render(request, "shop/product_list.html", context)


def product_detail(request, pk):
    """Display the complete details for one active product."""
    product = get_object_or_404(
        Product.objects.select_related("category"),
        pk=pk,
        is_active=True,
    )
    cart = _get_or_create_cart(request)
    cart_item = cart.items.filter(product=product).first()
    return render(
        request,
        "shop/product_detail.html",
        {
            "product": product,
            "cart": cart,
            "is_in_cart": cart_item is not None,
            "cart_quantity": cart_item.quantity if cart_item else 0,
        },
    )


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
            "product_id": product.id,
            "quantity": cart_item.quantity,
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
    cart = _get_or_create_cart(request)
    if cart.is_empty:
        messages.error(request, _("Your cart is empty."))
        return redirect("shop:cart")
    min_order = MinimumOrderAmount.get_instance()
    if min_order.enabled and cart.total < min_order.minimum_amount:
        messages.error(
            request,
            _("Your cart total is below the minimum order amount of ₦{:.2f}.").format(
                min_order.minimum_amount
            ),
        )
        return redirect("shop:cart")
    delivery_options = _available_delivery_options()
    if not delivery_options.exists():
        messages.error(request, _("Delivery is temporarily unavailable."))
        return redirect("shop:cart")
    enabled_payment_methods = [
        {"code": code, "label": label}
        for code, label in PaymentMethodSetting.PAYMENT_METHOD_CHOICES
        if PaymentMethodSetting.is_enabled(code)
    ]
    if not enabled_payment_methods:
        messages.error(request, _("No payment methods are currently available."))
        return redirect("shop:cart")
    return render(request, "shop/checkout.html", {
        "cart": cart,
        "cart_items": cart.items.select_related("product"),
        "delivery_options": delivery_options,
        "subtotal": cart.total,
        "delivery_address": request.user.default_delivery_address,
        "paystack_public_key": settings.PAYSTACK_PUBLIC_KEY,
        "enabled_payment_methods": enabled_payment_methods,
    })


@require_POST
@login_required
def place_order(request):
    """Create an order from the cart after validating checkout selections."""
    cart = _get_or_create_cart(request)
    if cart.is_empty:
        messages.error(request, _("Your cart is empty."))
        return redirect("shop:cart")
    delivery_address = request.POST.get("delivery_address", "").strip()
    if not delivery_address:
        messages.error(request, _("Please provide a delivery address."))
        return redirect("shop:checkout")
    delivery_option = get_object_or_404(
        DeliveryOption, pk=request.POST.get("delivery_option"), enabled=True
    )
    payment_method = request.POST.get("payment_method")
    if payment_method not in {
        code for code, _ in PaymentMethodSetting.PAYMENT_METHOD_CHOICES
        if PaymentMethodSetting.is_enabled(code)
    }:
        messages.error(request, _("Please select an available payment method."))
        return redirect("shop:checkout")
    subtotal = cart.total
    order = Order.objects.create(
        user=request.user,
        status=Order.Status.PENDING,
        subtotal=subtotal,
        delivery_fee=delivery_option.price,
        total=subtotal + delivery_option.price,
        delivery_option=delivery_option,
        delivery_address=delivery_address,
        payment_method=payment_method,
    )
    for cart_item in cart.items.select_related("product"):
        OrderItem.objects.create(
            order=order, product=cart_item.product, product_name=cart_item.product.name,
            quantity=cart_item.quantity, price=cart_item.product.price,
        )
    cart.items.all().delete()
    if payment_method == "paystack":
        return _initialize_paystack_payment(request, order)
    reference = f"{payment_method}-{uuid.uuid4().hex[:24]}"
    Payment.objects.create(order=order, reference=reference, amount=order.total)
    if payment_method == "cash_on_delivery":
        order.status = Order.Status.PROCESSING
        order.save(update_fields=["status"])
    return redirect("shop:payment_success", pk=order.pk)


def _initialize_paystack_payment(request, order):
    if not settings.PAYSTACK_SECRET_KEY:
        messages.error(request, _("Card payments are not configured. Please choose another method."))
        return redirect("accounts:order_detail", pk=order.pk)
    reference = f"tamipee-{order.pk}-{uuid.uuid4().hex[:16]}"
    Payment.objects.create(order=order, reference=reference, amount=order.total)
    payload = urllib.parse.urlencode({
        "email": request.user.email,
        "amount": int(order.total * 100),
        "reference": reference,
        "currency": "NGN",
        "callback_url": request.build_absolute_uri(reverse("shop:paystack_callback")),
    }).encode()
    print(f"[PAYSTACK INIT] order={order.pk} payload={payload.decode()}")
    paystack_request = urllib.request.Request(
        "https://api.paystack.co/transaction/initialize", data=payload,
        headers={
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "User-Agent": "Mozilla/5.0 (compatible; Tamipee/1.0)",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(paystack_request, timeout=15) as response:
            raw_body = response.read().decode("utf-8")
            result = json.loads(raw_body)
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            pass
        print(f"[PAYSTACK INIT HTTPError] order={order.pk} status={exc.code} body={body}")
        messages.error(request, _("Card payment provider returned an error. Please try again or choose another method."))
        return redirect("accounts:order_detail", pk=order.pk)
    except urllib.error.URLError as exc:
        print(f"[PAYSTACK INIT URLError] order={order.pk} error={exc.reason}")
        messages.error(request, _("Unable to reach the card payment provider. Please try again."))
        return redirect("accounts:order_detail", pk=order.pk)
    except Exception as exc:
        import traceback
        print(f"[PAYSTACK INIT Exception] order={order.pk} error={exc}")
        traceback.print_exc()
        messages.error(request, _("Unable to start card payment. Please try again."))
        return redirect("accounts:order_detail", pk=order.pk)
    print(f"[PAYSTACK INIT] order={order.pk} response={raw_body}")
    authorization_url = result.get("data", {}).get("authorization_url")
    if not result.get("status") or not authorization_url:
        print(f"[PAYSTACK INIT] order={order.pk} missing authorization_url status={result.get('status')} message={result.get('message')}")
        messages.error(request, _("Card payment provider returned an error. Please try again or choose another method."))
        return redirect("accounts:order_detail", pk=order.pk)
    return redirect(authorization_url)


@login_required
def payment_success(request, pk):
    order = get_object_or_404(Order.objects.select_related("delivery_option"), pk=pk, user=request.user)
    return render(request, "shop/payment_success.html", {"order": order})


@login_required
def payment_failure(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    return render(request, "shop/payment_failure.html", {"order": order})


@require_POST
@login_required
def update_order_delivery_address(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    delivery_address = request.POST.get("delivery_address", "").strip()
    if not delivery_address:
        messages.error(request, _("Please provide a delivery address."))
    else:
        order.delivery_address = delivery_address
        order.save(update_fields=["delivery_address"])
        messages.success(request, _("Delivery address saved for this order."))
    return redirect("accounts:order_detail", pk=order.pk)


def paystack_callback(request):
    """
    Handle Paystack webhook/callback for payment confirmation.

    Verifies the transaction with Paystack, creates a Payment record,
    updates Order status, and decrements stock only on success.
    """
    reference = request.GET.get("reference") or request.POST.get("reference")

    if not reference:
        return JsonResponse({"success": False, "error": "No reference provided"}, status=400)

    verify_url = f"https://api.paystack.co/transaction/verify/{reference}"
    req = urllib.request.Request(verify_url)
    req.add_header("Authorization", f"Bearer {settings.PAYSTACK_SECRET_KEY}")
    req.add_header("User-Agent", "Mozilla/5.0 (compatible; Tamipee/1.0)")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            result = json.loads(body)
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode("utf-8")
        except Exception:
            err_body = ""
        print(f"[PAYSTACK VERIFY HTTPError] reference={reference} status={exc.code} body={err_body}")
        return JsonResponse({"success": False, "error": "Paystack verification failed"}, status=500)
    except urllib.error.URLError as exc:
        print(f"[PAYSTACK VERIFY URLError] reference={reference} error={exc.reason}")
        return JsonResponse({"success": False, "error": "Paystack verification failed"}, status=500)

    print(f"[PAYSTACK VERIFY] reference={reference} response={body}")
    if not result.get("status"):
        return JsonResponse({"success": False, "error": "Paystack verification unsuccessful"}, status=400)

    transaction_data = result.get("data", {})
    status = transaction_data.get("status", "")
    amount = transaction_data.get("amount", 0) / 100  # Paystack returns in kobo
    reference = transaction_data.get("reference", reference)

    try:
        payment = Payment.objects.select_related("order").get(reference=reference)
    except Payment.DoesNotExist:
        return redirect("shop:product_list")
    order = payment.order
    if Decimal(str(amount)) != order.total:
        payment.status = "failed"
        payment.paystack_response = transaction_data
        payment.save(update_fields=["status", "paystack_response"])
        return redirect("shop:payment_failure", pk=order.pk)

    if status == "success" and payment.status != "success":
        payment.status = "success"
        payment.paystack_response = transaction_data
        payment.save(update_fields=["status", "paystack_response"])
        order.status = Order.Status.PROCESSING
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
        return redirect("shop:payment_success", pk=order.pk)
    else:
        payment.status = "failed"
        payment.paystack_response = transaction_data
        payment.save(update_fields=["status", "paystack_response"])
        return redirect("shop:payment_failure", pk=order.pk)


@csrf_exempt
@require_POST
def paystack_webhook(request):
    """
    Handle Paystack server-to-server webhooks.

    Verifies the webhook signature, then updates Payment/Order status
    based on the event type. This runs independently of the customer's
    browser, so payments are confirmed even if the customer closes
    their tab mid-payment.
    """
    if not settings.PAYSTACK_WEBHOOK_SECRET:
        return JsonResponse({"status": "error", "message": "Webhook secret not configured"}, status=500)

    signature = request.headers.get("x-paystack-signature", "")
    if not signature:
        return JsonResponse({"status": "error", "message": "Missing signature"}, status=400)

    payload = request.body
    expected_signature = hmac.new(
        settings.PAYSTACK_WEBHOOK_SECRET.encode("utf-8"),
        payload,
        hashlib.sha512,
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        return JsonResponse({"status": "error", "message": "Invalid signature"}, status=400)

    try:
        event = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"status": "error", "message": "Invalid payload"}, status=400)

    event_type = event.get("event", "")
    transaction_data = event.get("data", {})

    if event_type not in ("charge.success", "charge.failed"):
        return JsonResponse({"status": "success", "message": "Event ignored"}, status=200)

    reference = transaction_data.get("reference", "")
    if not reference:
        return JsonResponse({"status": "error", "message": "No reference in payload"}, status=400)

    try:
        payment = Payment.objects.select_related("order").get(reference=reference)
    except Payment.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Payment not found"}, status=404)

    order = payment.order
    amount = Decimal(str(transaction_data.get("amount", 0) / 100))

    if event_type == "charge.success" and payment.status != "success":
        if amount != order.total:
            payment.status = "failed"
            payment.paystack_response = transaction_data
            payment.save(update_fields=["status", "paystack_response"])
            return JsonResponse({"status": "error", "message": "Amount mismatch"}, status=400)

        payment.status = "success"
        payment.paystack_response = transaction_data
        payment.save(update_fields=["status", "paystack_response"])

        if order.status != Order.Status.PROCESSING:
            order.status = Order.Status.PROCESSING
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

        return JsonResponse({"status": "success", "message": "Payment confirmed"}, status=200)

    elif event_type == "charge.failed":
        payment.status = "failed"
        payment.paystack_response = transaction_data
        payment.save(update_fields=["status", "paystack_response"])
        return JsonResponse({"status": "success", "message": "Payment marked failed"}, status=200)

    return JsonResponse({"status": "success", "message": "No action taken"}, status=200)


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
