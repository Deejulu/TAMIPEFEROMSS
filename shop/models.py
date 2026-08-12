from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify
from decimal import Decimal


class Category(models.Model):
    name = models.CharField(_("name"), max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(_("description"), blank=True)
    is_sample_data = models.BooleanField(_("sample data"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(_("name"), max_length=200)
    description = models.TextField(_("description"), blank=True)
    price = models.DecimalField(_("price"), max_digits=10, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(_("stock quantity"), default=0)
    low_stock_threshold = models.PositiveIntegerField(
        _("low stock threshold"),
        default=5,
        help_text=_("Stock level below which product is considered low stock"),
    )
    image = models.ImageField(
        _("image"),
        upload_to="products/",
        blank=True,
        null=True,
    )
    is_active = models.BooleanField(_("active"), default=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name=_("category"),
    )
    is_sample_data = models.BooleanField(_("sample data"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def in_stock(self):
        """Return True if stock is available."""
        return self.stock_quantity > 0

    @property
    def is_low_stock(self):
        """Return True if stock is at or below the low stock threshold."""
        return self.stock_quantity <= self.low_stock_threshold

    def decrement_stock(self, quantity):
        """Reduce stock by given quantity. Raises ValueError if insufficient."""
        if quantity > self.stock_quantity:
            raise ValueError(_("Insufficient stock"))
        self.stock_quantity -= quantity
        self.save(update_fields=["stock_quantity"])

    def increment_stock(self, quantity):
        """Increase stock by given quantity."""
        self.stock_quantity += quantity
        self.save(update_fields=["stock_quantity"])


class Cart(models.Model):
    """
    Shopping cart for a user or session.
    
    Linked to an authenticated user or an anonymous session key.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="cart",
        verbose_name=_("user"),
    )
    session_key = models.CharField(
        _("session key"),
        max_length=40,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("cart")
        verbose_name_plural = _("carts")

    def __str__(self):
        if self.user:
            return f"Cart #{self.pk} - {self.user.full_name}"
        return f"Cart #{self.pk} - Guest"

    @property
    def total(self):
        """Calculate the total price of all items in the cart."""
        return sum(item.subtotal for item in self.items.all())

    @property
    def item_count(self):
        """Return the total number of items in the cart."""
        return sum(item.quantity for item in self.items.all())

    @property
    def is_empty(self):
        """Return True if the cart has no items."""
        return not self.items.exists()


class CartItem(models.Model):
    """
    An item in a shopping cart.
    
    Links a product with a quantity within a specific cart.
    """
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("cart"),
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        verbose_name=_("product"),
    )
    quantity = models.PositiveIntegerField(_("quantity"), default=1)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("cart item")
        verbose_name_plural = _("cart items")
        unique_together = [["cart", "product"]]

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    @property
    def subtotal(self):
        """Calculate the subtotal for this line item."""
        return self.product.price * Decimal(str(self.quantity))


class Order(models.Model):
    """
    Customer order created from a cart at checkout.
    
    Tracks the lifecycle from pending through to delivered/cancelled.
    """
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        CONFIRMED = "confirmed", _("Confirmed")
        PROCESSING = "processing", _("Processing")
        AWAITING_DELIVERY = "awaiting_delivery", _("Awaiting Delivery")
        SHIPPED = "shipped", _("Shipped")
        DELIVERED = "delivered", _("Delivered")
        CANCELLED = "cancelled", _("Cancelled")

    # Ordered, non-cancelled lifecycle used to build a minimal status timeline.
    STATUS_FLOW = [
        Status.PENDING,
        Status.CONFIRMED,
        Status.PROCESSING,
        Status.AWAITING_DELIVERY,
        Status.SHIPPED,
        Status.DELIVERED,
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name=_("user"),
        help_text=_("User who placed the order. May be null if user is deleted."),
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    total = models.DecimalField(
        _("total"),
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    subtotal = models.DecimalField(
        _("subtotal"),
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text=_("Item total before delivery charges."),
    )
    delivery_option = models.ForeignKey(
        "admin_dashboard.DeliveryOption",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name=_("delivery option"),
    )
    delivery_fee = models.DecimalField(
        _("delivery fee"),
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    payment_method = models.CharField(
        _("payment method"),
        max_length=50,
        blank=True,
        default="",
        help_text=_("Payment method used for this order"),
    )
    delivery_address = models.TextField(
        _("delivery address"),
        blank=True,
        default="",
        help_text=_("Delivery address for this order"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        ordering = ["-created_at"]

    def __str__(self):
        user_name = self.user.full_name if self.user else "Deleted User"
        return f"Order #{self.pk} - {user_name} ({self.get_status_display()})"

    @property
    def estimated_delivery_date(self):
        if not self.delivery_option:
            return None
        from datetime import timedelta
        from django.utils import timezone

        return (self.created_at or timezone.now()).date() + timedelta(
            days=self.delivery_option.estimated_days
        )

    def recalculate_totals(self, save=True):
        """
        Recompute subtotal/delivery_fee/total from the order's current
        line items and delivery option selection.
        """
        subtotal = sum(
            (item.subtotal for item in self.items.all()), Decimal("0.00")
        )
        delivery_fee = self.delivery_option.price if self.delivery_option else Decimal("0.00")
        self.subtotal = subtotal
        self.delivery_fee = delivery_fee
        self.total = subtotal + delivery_fee
        if save:
            self.save(update_fields=["subtotal", "delivery_fee", "total"])
        return self.total

    @property
    def status_timeline(self):
        """
        Minimal, robust status timeline derived from the order's current
        status. Each step is marked 'done', 'current', or 'upcoming'.
        Cancelled orders show a short two-step timeline instead.
        """
        labels = dict(self.Status.choices)

        if self.status == self.Status.CANCELLED:
            return [
                {"code": self.Status.PENDING, "label": labels[self.Status.PENDING], "state": "done"},
                {"code": self.Status.CANCELLED, "label": labels[self.Status.CANCELLED], "state": "current"},
            ]

        try:
            current_index = self.STATUS_FLOW.index(self.status)
        except ValueError:
            current_index = 0

        steps = []
        for index, code in enumerate(self.STATUS_FLOW):
            if index < current_index:
                state = "done"
            elif index == current_index:
                state = "current"
            else:
                state = "upcoming"
            steps.append({"code": code, "label": labels[code], "state": state})
        return steps


class OrderItem(models.Model):
    """
    A line item within an order.

    Stores the product details as they were at time of purchase,
    so order history remains accurate even if product changes later.
    """
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("order"),
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("product"),
    )
    product_name = models.CharField(
        _("product name"),
        max_length=200,
        help_text=_("Product name at time of purchase"),
    )
    quantity = models.PositiveIntegerField(_("quantity"))
    price = models.DecimalField(
        _("price"),
        max_digits=10,
        decimal_places=2,
        help_text=_("Price per unit at time of purchase"),
    )

    class Meta:
        verbose_name = _("order item")
        verbose_name_plural = _("order items")

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"

    @property
    def subtotal(self):
        """Calculate the subtotal for this line item."""
        return self.price * Decimal(str(self.quantity))


class Payment(models.Model):
    """
    Payment record linked to an Order.

    Created when Paystack confirms a successful transaction.
    Tracks the Paystack reference, amount, and status.
    Stock is only decremented after payment is confirmed successful.
    """

    STATUS_CHOICES = [
        ("pending", _("Pending")),
        ("success", _("Successful")),
        ("failed", _("Failed")),
    ]

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name=_("order"),
    )
    reference = models.CharField(
        _("reference"),
        max_length=50,
        unique=True,
        help_text=_("Paystack transaction reference"),
    )
    amount = models.DecimalField(
        _("amount"),
        max_digits=10,
        decimal_places=2,
        help_text=_("Amount paid in NGN"),
    )
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=STATUS_CHOICES,
        default="pending",
    )
    paystack_response = models.JSONField(
        _("Paystack response"),
        default=dict,
        blank=True,
        help_text=_("Raw response data from Paystack"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment #{self.pk} - Order #{self.order.pk} - {self.status}"
