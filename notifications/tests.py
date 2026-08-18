from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

from accounts.models import CustomUser
from notifications.models import Notification
from notifications.utils import maybe_notify_low_stock
from shop.models import Product, Order, OrderItem, Payment, Category

User = get_user_model()


@override_settings(TESTING=False)
class NotificationSignalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="test@example.com",
            full_name="Test User",
            password="testpass123",
            username="testuser1",
        )
        cls.category = Category.objects.create(
            name="Test Category",
            description="Test category for notifications",
        )

    def test_order_created_creates_notification(self):
        order = Order.objects.create(user=self.user, total=Decimal("1000.00"))
        self.assertEqual(Notification.objects.filter(notification_type='order').count(), 1)
        notif = Notification.objects.filter(notification_type='order').first()
        self.assertIn(f"New order #{order.id}", notif.message)
        self.assertEqual(notif.related_object_id, order.id)

    def test_payment_success_creates_notification(self):
        order = Order.objects.create(user=self.user, total=Decimal("1000.00"))
        payment = Payment.objects.create(
            order=order,
            reference="ref123",
            amount=Decimal("1000.00"),
            status="success",
        )
        self.assertEqual(Notification.objects.filter(notification_type='payment').count(), 1)
        notif = Notification.objects.filter(notification_type='payment').first()
        self.assertIn("Payment of ₦1000.00", notif.message)
        self.assertIn(f"Order #{order.id}", notif.message)

    def test_payment_updated_to_success_creates_notification(self):
        order = Order.objects.create(user=self.user, total=Decimal("1000.00"))
        payment = Payment.objects.create(
            order=order,
            reference="ref-transition",
            amount=Decimal("1000.00"),
            status="pending",
        )
        self.assertEqual(Notification.objects.filter(notification_type='payment').count(), 0)
        payment.status = "success"
        payment.save(update_fields=["status"])
        self.assertEqual(Notification.objects.filter(notification_type='payment').count(), 1)
        notif = Notification.objects.filter(notification_type='payment').first()
        self.assertIn("Payment of ₦1000.00", notif.message)
        self.assertIn(f"Order #{order.id}", notif.message)

    def test_payment_resaved_as_success_does_not_create_duplicate(self):
        order = Order.objects.create(user=self.user, total=Decimal("1000.00"))
        payment = Payment.objects.create(
            order=order,
            reference="ref-dup",
            amount=Decimal("1000.00"),
            status="success",
        )
        self.assertEqual(Notification.objects.filter(notification_type='payment').count(), 1)
        payment.amount = Decimal("1000.01")
        payment.save(update_fields=["amount"])
        self.assertEqual(Notification.objects.filter(notification_type='payment').count(), 1)

    def test_payment_failed_does_not_create_notification(self):
        order = Order.objects.create(user=self.user, total=Decimal("1000.00"))
        Payment.objects.create(
            order=order,
            reference="ref456",
            amount=Decimal("1000.00"),
            status="failed",
        )
        self.assertEqual(Notification.objects.filter(notification_type='payment').count(), 0)

    def test_new_user_creates_notification(self):
        extra_count = Notification.objects.filter(notification_type='user').count()
        user = User.objects.create_user(
            email="newuser@example.com",
            full_name="New User",
            password="testpass123",
            username="newuser2",
        )
        self.assertEqual(Notification.objects.filter(notification_type='user').count(), extra_count + 1)
        notif = Notification.objects.filter(notification_type='user').order_by('-created_at').first()
        self.assertIn("New user registered: New User", notif.message)
        self.assertEqual(notif.related_object_id, user.id)


class LowStockNotificationTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Test Category",
            description="Test category for low stock tests",
        )

    def test_low_stock_notification_created_when_crossing_threshold(self):
        product = Product.objects.create(
            name="Tomatoes",
            price=Decimal("1500.00"),
            stock_quantity=15,
            category=self.category,
        )
        maybe_notify_low_stock(product, 15, 8)
        self.assertEqual(Notification.objects.filter(notification_type='low_stock').count(), 1)
        notif = Notification.objects.filter(notification_type='low_stock').first()
        self.assertIn("Tomatoes", notif.message)
        self.assertIn("8 units left", notif.message)

    def test_no_low_stock_when_already_below_threshold(self):
        product = Product.objects.create(
            name="Tomatoes",
            price=Decimal("1500.00"),
            stock_quantity=15,
            category=self.category,
        )
        maybe_notify_low_stock(product, 8, 5)
        self.assertEqual(Notification.objects.filter(notification_type='low_stock').count(), 0)

    def test_no_duplicate_unread_low_stock_notification(self):
        product = Product.objects.create(
            name="Tomatoes",
            price=Decimal("1500.00"),
            stock_quantity=15,
            category=self.category,
        )
        maybe_notify_low_stock(product, 15, 8)
        self.assertEqual(Notification.objects.filter(notification_type='low_stock').count(), 1)
        maybe_notify_low_stock(product, 8, 5)
        self.assertEqual(Notification.objects.filter(notification_type='low_stock').count(), 1)

    def test_low_stock_notification_created_after_marking_previous_read(self):
        product = Product.objects.create(
            name="Tomatoes",
            price=Decimal("1500.00"),
            stock_quantity=15,
            category=self.category,
        )
        maybe_notify_low_stock(product, 15, 8)
        notif = Notification.objects.filter(notification_type='low_stock').first()
        notif.is_read = True
        notif.save(update_fields=['is_read'])
        maybe_notify_low_stock(product, 12, 9)
        self.assertEqual(Notification.objects.filter(notification_type='low_stock').count(), 2)
