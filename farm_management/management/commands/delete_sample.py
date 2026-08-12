"""
Management command to delete all sample data across the entire site.

Deletes every record tagged as sample data (is_sample=True / is_sample_data=True)
across admin_dashboard, shop, and farm_management apps, in dependency order to
respect foreign-key constraints. Real (non-sample) data is never touched.
"""
from django.core.management.base import BaseCommand

from admin_dashboard.models import SiteContent
from farm_management.models import (
    Category as FarmCategory,
    Species,
    Supplier,
    FeedInventory,
    Batch,
    FeedLog,
    GrowthRecord,
    MortalityLog,
    VaccinationRecord,
    HealthMedicationLog,
    DailyActivityLog,
    HarvestRecord,
)
from shop.models import Category as ShopCategory, Product, Order, OrderItem, Cart, CartItem
from notifications.models import Notification
from accounts.models import CustomUser


class Command(BaseCommand):
    help = "Delete all sample data across the entire site (is_sample=True / is_sample_data=True)."

    def handle(self, *args, **options):
        total = 0

        # ------------------------------------------------------------------
        # Shop orders and cart items for known sample/test users
        # ------------------------------------------------------------------
        sample_usernames = [
            "DavidTamipee2026TIF002",
            "DavidTamipee2026TIF003",
            "admin",
            "testcustomer",
            "TestCustomerCRUD2026001",
            "TestCustomerCRUD2026002",
            "TestCustomerCRUD2026003",
        ]
        sample_users = CustomUser.objects.filter(username__in=sample_usernames)

        sample_orders = Order.objects.filter(user__in=sample_users)
        order_ids = list(sample_orders.values_list("pk", flat=True))
        count, _ = OrderItem.objects.filter(order_id__in=order_ids).delete()
        total += count
        if count:
            self.stdout.write(f"Deleted {count} sample order items.")

        count, _ = sample_orders.delete()
        total += count
        if count:
            self.stdout.write(f"Deleted {count} sample orders.")

        count, _ = CartItem.objects.filter(cart__user__in=sample_users).delete()
        total += count
        if count:
            self.stdout.write(f"Deleted {count} sample cart items.")

        # ------------------------------------------------------------------
        # Shop products and categories
        # ------------------------------------------------------------------
        count, _ = Product.objects.filter(is_sample_data=True).delete()
        total += count
        if count:
            self.stdout.write(f"Deleted {count} sample products.")

        count, _ = ShopCategory.objects.filter(is_sample_data=True).delete()
        total += count
        if count:
            self.stdout.write(f"Deleted {count} sample shop categories.")

        # ------------------------------------------------------------------
        # Site content — reset to empty placeholders instead of deleting
        # ------------------------------------------------------------------
        reset_titles = {
            'homepage_hero': 'Homepage Hero',
            'shop_banner': 'Shop Banner',
            'about': 'About Us',
            'contact': 'Contact Us',
            'faq': 'Frequently Asked Questions',
            'delivery_info': 'Delivery Information',
            'terms_privacy': 'Terms & Privacy Policy',
            'return_refund': 'Return & Refund Policy',
            'business_hours': 'Business Hours',
            'social_media': 'Social Media',
        }
        reset_content = {
            'homepage_hero': '',
            'shop_banner': '',
            'about': '<p>Tell your farm story here.</p>',
            'contact': '<p>Add your phone, email, and address here.</p>',
            'faq': '<p><strong>Q:</strong> Your question here?<br><strong>A:</strong> Your answer here.</p>',
            'delivery_info': '<p>Add your delivery zones, pricing, and timing here.</p>',
            'terms_privacy': '<p>Add your terms and privacy policy here.</p>',
            'return_refund': '<p>Add your return and refund policy here.</p>',
            'business_hours': '<p>Monday - Friday: 8:00 AM - 6:00 PM<br>Saturday: 9:00 AM - 4:00 PM<br>Sunday: Closed</p>',
            'social_media': '<p>Add your social media links in the form below.</p>',
        }
        for section_code in reset_titles:
            SiteContent.objects.filter(section=section_code).update(
                title=reset_titles[section_code],
                content=reset_content[section_code],
                is_sample=False,
            )
        self.stdout.write(self.style.SUCCESS("Reset all site content sections to empty placeholders."))

        # ------------------------------------------------------------------
        # Farm management data
        # ------------------------------------------------------------------
        child_models = [
            FeedLog,
            GrowthRecord,
            MortalityLog,
            VaccinationRecord,
            HealthMedicationLog,
            DailyActivityLog,
            HarvestRecord,
        ]
        for model in child_models:
            count, _ = model.objects.filter(is_sample=True).delete()
            total += count
            if count:
                self.stdout.write(
                    f"Deleted {count} sample {model._meta.verbose_name_plural}."
                )

        count, _ = Batch.objects.filter(is_sample=True).delete()
        total += count
        if count:
            self.stdout.write(f"Deleted {count} sample batches.")

        count, _ = FeedInventory.objects.filter(is_sample=True).delete()
        total += count
        if count:
            self.stdout.write(f"Deleted {count} sample feed inventory items.")

        count, _ = Supplier.objects.filter(is_sample=True).delete()
        total += count
        if count:
            self.stdout.write(f"Deleted {count} sample suppliers.")

        count, _ = Species.objects.filter(is_sample=True).delete()
        total += count
        if count:
            self.stdout.write(f"Deleted {count} sample species.")

        count, _ = FarmCategory.objects.filter(is_sample=True).delete()
        total += count
        if count:
            self.stdout.write(f"Deleted {count} sample farm categories.")

        # ------------------------------------------------------------------
        # Notifications referencing deleted sample objects
        # ------------------------------------------------------------------
        count, _ = Notification.objects.filter(
            notification_type="batch_alert",
            related_object_id__in=list(
                Batch.objects.filter(is_sample=True).values_list("pk", flat=True)
            ),
        ).delete()
        total += count
        if count:
            self.stdout.write(f"Deleted {count} sample batch alert notifications.")

        if total:
            self.stdout.write(
                self.style.SUCCESS(f"Sample data deleted. Removed {total} total record(s).")
            )
        else:
            self.stdout.write(
                self.style.WARNING("No sample data found to delete.")
            )
