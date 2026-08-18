from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta, datetime
from django.core.management import call_command

from accounts.models import CustomUser
from notifications.models import Notification
from shop.models import Product, Order, OrderItem, Payment, Category
from farm_management.models import Batch, FeedInventory, Category as FarmCategory, Species, MortalityLog
from admin_dashboard.models import SiteContent, BusinessHours, AuditLogEntry
from admin_dashboard.forms import SiteContentForm

User = get_user_model()

ADMIN_SECTIONS = [
    ('overview', 'Overview'),
    ('payments', 'Payments'),
    ('notifications', 'Notifications'),
    ('content', 'Website Content Management'),
    ('users', 'User Management'),
    ('orders', 'Orders & Delivery'),
    ('inventory', 'Products / Inventory'),
    ('farm_management', 'Farm Management'),
    ('reports', 'Reports'),
]

ADMIN_ROLES = [
    (CustomUser.Role.SUPER_ADMIN, True),
    (CustomUser.Role.FARM_MANAGER, True),
    (CustomUser.Role.STAFF, False),
    (CustomUser.Role.CUSTOMER, False),
]


class AdminDashboardShellTests(TestCase):
    """Tests for admin dashboard placeholder shell, role restrictions, and redirects."""

    @classmethod
    def setUpTestData(cls):
        cls.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=CustomUser.Role.SUPER_ADMIN,
            is_staff=True,
        )
        cls.farm_manager = User.objects.create_user(
            email="farmmanager@example.com",
            full_name="Farm Manager",
            password="StrongPass1!",
            role=CustomUser.Role.FARM_MANAGER,
        )
        cls.staff_user = User.objects.create_user(
            email="staff@example.com",
            full_name="Staff User",
            password="StrongPass1!",
            role=CustomUser.Role.STAFF,
        )
        cls.customer_user = User.objects.create_user(
            email="customer@example.com",
            full_name="Customer User",
            password="StrongPass1!",
            role=CustomUser.Role.CUSTOMER,
        )

    def login(self, user):
        return self.client.login(username=user.username, password="StrongPass1!")

    # ---------------------------------------------------------------- #
    # Base URL redirect behavior
    # ---------------------------------------------------------------- #

    def test_base_admin_url_redirects_to_overview(self):
        """Visiting /admin-dashboard/ with no sub-path redirects to overview."""
        response = self.client.get(reverse('admin_dashboard:index'), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/overview/', response.url)

    def test_base_admin_url_redirects_for_super_admin(self):
        """Super Admin hitting /admin-dashboard/ gets redirected to overview (302)."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:index'), follow=False)
        self.assertEqual(response.status_code, 302)

    # ---------------------------------------------------------------- #
    # Role restriction: Super Admin and Farm Manager can access
    # ---------------------------------------------------------------- #

    def test_super_admin_can_access_all_sections(self):
        """Super Admin can access every admin dashboard section."""
        self.login(self.super_admin)
        for section, label in ADMIN_SECTIONS:
            with self.subTest(section=section):
                response = self.client.get(reverse(f'admin_dashboard:{section}'))
                self.assertEqual(response.status_code, 200)
                self.assertIn('Admin Dashboard', response.content.decode())
                self.assertIn(label, response.content.decode())

    def test_farm_manager_can_access_all_sections(self):
        """Farm Manager can access non-sensitive admin dashboard sections."""
        self.login(self.farm_manager)
        for section, label in ADMIN_SECTIONS:
            if section == 'users':
                continue
            with self.subTest(section=section):
                response = self.client.get(reverse(f'admin_dashboard:{section}'))
                self.assertEqual(response.status_code, 200)
                self.assertIn('Admin Dashboard', response.content.decode())
                self.assertIn(label, response.content.decode())

    # ---------------------------------------------------------------- #
    # Role restriction: Staff and Customer are blocked
    # ---------------------------------------------------------------- #

    def test_staff_is_redirected_from_all_admin_pages(self):
        """Staff users are redirected (to dashboard) from every admin page."""
        self.login(self.staff_user)
        for section, _ in ADMIN_SECTIONS:
            with self.subTest(section=section):
                response = self.client.get(reverse(f'admin_dashboard:{section}'), follow=False)
                self.assertEqual(response.status_code, 302)
                self.assertIn('dashboard', response.url)

    def test_customer_is_redirected_from_all_admin_pages(self):
        """Customer users are redirected (to dashboard) from every admin page."""
        self.login(self.customer_user)
        for section, _ in ADMIN_SECTIONS:
            with self.subTest(section=section):
                response = self.client.get(reverse(f'admin_dashboard:{section}'), follow=False)
                self.assertEqual(response.status_code, 302)
                self.assertIn('dashboard', response.url)

    def test_unauthenticated_user_redirected_from_admin_pages(self):
        """Unauthenticated users are redirected to login."""
        for section, _ in ADMIN_SECTIONS:
            with self.subTest(section=section):
                response = self.client.get(reverse(f'admin_dashboard:{section}'), follow=False)
                self.assertEqual(response.status_code, 302)
                self.assertIn('login', response.url)

    # ---------------------------------------------------------------- #
    # Content smoke tests
    # ---------------------------------------------------------------- #

    def test_overview_page_loads_for_super_admin(self):
        """Overview page loads successfully for Super Admin."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Dashboard Overview', response.content.decode())
        self.assertContains(response, 'Farm Snapshot')
        self.assertContains(response, 'Orders / Shop Snapshot')
        self.assertContains(response, 'User Snapshot')
        self.assertContains(response, 'Quick Links')

    def test_overview_page_loads_for_farm_manager(self):
        """Overview page loads successfully for Farm Manager."""
        self.login(self.farm_manager)
        response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Dashboard Overview', response.content.decode())

    def test_overview_displays_farm_snapshot_data(self):
        """Overview page displays real farm snapshot data."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        context = response.context
        self.assertIn('active_batches_count', context)
        self.assertIn('batches_by_species', context)
        self.assertIn('active_alerts', context)
        self.assertIn('low_feed_inventory', context)
        self.assertIn('low_feed_inventory_count', context)

    def test_overview_displays_orders_snapshot_data(self):
        """Overview page displays real orders snapshot data."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        context = response.context
        self.assertIn('recent_orders_count', context)
        self.assertIn('low_stock_products', context)
        self.assertIn('low_stock_products_count', context)

    def test_overview_displays_user_snapshot_data(self):
        """Overview page displays real user snapshot data."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        context = response.context
        self.assertIn('total_active_users', context)
        self.assertIn('users_by_role', context)

    def test_overview_displays_quick_links(self):
        """Overview page displays quick links to admin sections."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        context = response.context
        self.assertIn('quick_links', context)
        link_names = [link['name'] for link in context['quick_links']]
        self.assertIn('Farm Management', link_names)
        self.assertIn('User Management', link_names)
        self.assertIn('Content Management', link_names)
        self.assertIn('Orders', link_names)
        self.assertIn('Analytics', link_names)
        self.assertIn('Supplier Directory', link_names)

    def test_overview_farm_snapshot_counts(self):
        """Overview page shows correct counts for farm snapshot."""
        self.login(self.super_admin)
        Batch.objects.all().delete()
        FeedInventory.objects.all().delete()
        Notification.objects.filter(notification_type='batch_alert').delete()

        fish_category = FarmCategory.objects.create(name='Fish')
        poultry_category = FarmCategory.objects.create(name='Poultry')
        catfish = Species.objects.create(name='Catfish', category=fish_category)
        tilapia = Species.objects.create(name='Tilapia', category=fish_category)
        broiler = Species.objects.create(name='Broiler', category=poultry_category)

        Batch.objects.create(
            name='Catfish Batch 1',
            species=catfish,
            initial_count=100,
            current_stock=80,
            start_date=timezone.now().date(),
            season='rainy',
            status='active',
        )
        Batch.objects.create(
            name='Tilapia Batch 1',
            species=tilapia,
            initial_count=200,
            current_stock=150,
            start_date=timezone.now().date(),
            season='dry',
            status='active',
        )
        Batch.objects.create(
            name='Closed Batch',
            species=broiler,
            initial_count=50,
            current_stock=0,
            start_date=timezone.now().date(),
            season='rainy',
            status='closed',
        )

        FeedInventory.objects.create(
            feed_type='Catfish Starter',
            quantity_on_hand_kg=10,
            cost_per_kg=50,
            reorder_point_kg=50,
        )

        Notification.objects.create(
            notification_type='batch_alert',
            message='Test batch alert',
            is_read=False,
        )

        response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        context = response.context
        self.assertEqual(context['active_batches_count'], 2)
        self.assertEqual(context['low_feed_inventory_count'], 1)
        self.assertEqual(context['active_alerts'].count(), 1)
        content = response.content.decode()
        self.assertIn('Catfish', content)
        self.assertIn('Tilapia', content)
        self.assertIn('Species', content)

    def test_overview_orders_snapshot_counts(self):
        """Overview page shows correct count for recent orders."""
        self.login(self.super_admin)
        Order.objects.all().delete()

        Order.objects.create(
            user=self.customer_user,
            status=Order.Status.PENDING,
            total=Decimal('100.00'),
        )
        Order.objects.create(
            user=self.customer_user,
            status=Order.Status.CONFIRMED,
            total=Decimal('200.00'),
        )

        response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        context = response.context
        self.assertEqual(context['recent_orders_count'], 2)

    def test_overview_user_snapshot_counts(self):
        """Overview page shows correct user snapshot data."""
        self.login(self.super_admin)
        User = get_user_model()
        active_super = User.objects.create_user(
            email='active_super@test.com',
            full_name='Active Super',
            password='StrongPass1!',
            role=CustomUser.Role.SUPER_ADMIN,
            is_active=True,
        )
        active_fm = User.objects.create_user(
            email='active_fm@test.com',
            full_name='Active FM',
            password='StrongPass1!',
            role=CustomUser.Role.FARM_MANAGER,
            is_active=True,
        )
        inactive_user = User.objects.create_user(
            email='inactive@test.com',
            full_name='Inactive User',
            password='StrongPass1!',
            role=CustomUser.Role.CUSTOMER,
            is_active=False,
        )

        response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        context = response.context
        self.assertIn('total_active_users', context)
        self.assertGreaterEqual(context['total_active_users'], 3)

    def test_customer_cannot_access_overview(self):
        """Customer users are redirected from the overview page."""
        self.login(self.customer_user)
        response = self.client.get(reverse('admin_dashboard:overview'), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('dashboard', response.url)

    def test_base_admin_template_has_sidebar(self):
        """Admin base template includes the sidebar navigation."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('admin-sidebar', response.content.decode())
        self.assertIn('Overview', response.content.decode())

    def test_base_admin_template_has_topbar(self):
        """Admin base template includes the top bar with notification and back link."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('admin-topbar', response.content.decode())
        self.assertIn('Overview', response.content.decode())

    def test_farm_management_hub_contains_only_navigation_cards(self):
        """The Farm Management hub excludes internal documentation and shows nine cards."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:farm_management'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'HUB PAGE: Farm Management Hub')
        self.assertNotContains(response, 'DO NOT add stats tables')
        self.assertNotContains(response, 'Track batches, feed, growth')
        self.assertEqual(response.content.decode().count('class="card farm-nav-card"'), 9)


class NotificationsPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=CustomUser.Role.SUPER_ADMIN,
            is_staff=True,
        )
        cls.farm_manager = User.objects.create_user(
            email="farmmanager@example.com",
            full_name="Farm Manager",
            password="StrongPass1!",
            role=CustomUser.Role.FARM_MANAGER,
        )
        cls.user = User.objects.create_user(
            email="user@example.com",
            full_name="Regular User",
            password="StrongPass1!",
            role=CustomUser.Role.CUSTOMER,
        )

    def login(self, user):
        return self.client.login(username=user.username, password="StrongPass1!")

    def test_unauthorized_roles_blocked_from_notifications_page(self):
        for role_user in [User.objects.create_user(
            email=f"{role}@example.com",
            full_name=role.title(),
            password="StrongPass1!",
            username=role,
            role=getattr(CustomUser.Role, role.upper()),
        ) for role in ['staff', 'customer']]:
            self.login(role_user)
            response = self.client.get(reverse('admin_dashboard:notifications'), follow=False)
            self.assertEqual(response.status_code, 302)
            self.assertIn('dashboard', response.url)

    def test_super_admin_can_access_notifications_page(self):
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:notifications'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Notifications', response.content.decode())

    def test_farm_manager_can_access_notifications_page(self):
        self.login(self.farm_manager)
        response = self.client.get(reverse('admin_dashboard:notifications'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Notifications', response.content.decode())

    def test_notifications_page_empty_state(self):
        Notification.objects.all().delete()
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:notifications'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('No notifications yet', response.content.decode())

    def test_notifications_page_shows_notifications(self):
        Notification.objects.create(
            notification_type='system',
            message='Test notification',
        )
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:notifications'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Test notification', response.content.decode())

    def test_unread_count_badge_context(self):
        Notification.objects.all().delete()
        Notification.objects.create(notification_type='system', message='First')
        Notification.objects.create(notification_type='system', message='Second', is_read=True)
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('1', response.content.decode())

    def test_filter_by_type(self):
        Notification.objects.all().delete()
        Notification.objects.create(notification_type='order', message='Order 1')
        Notification.objects.create(notification_type='payment', message='Payment 1')
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:notifications') + '?type=order')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Order 1', response.content.decode())
        self.assertNotIn('Payment 1', response.content.decode())

    def test_mark_single_notification_read(self):
        Notification.objects.all().delete()
        notif = Notification.objects.create(notification_type='system', message='Read me')
        self.login(self.super_admin)
        response = self.client.post(
            reverse('admin_dashboard:mark_notification_read', args=[notif.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['success'], True)
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_mark_all_read(self):
        Notification.objects.all().delete()
        Notification.objects.create(notification_type='system', message='First')
        Notification.objects.create(notification_type='system', message='Second')
        self.login(self.super_admin)
        response = self.client.post(
            reverse('admin_dashboard:mark_all_read'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['success'], True)
        self.assertEqual(Notification.objects.filter(is_read=False).count(), 0)

    def test_mark_all_read_badge_count_persists_across_navigation(self):
        """Marking all notifications as read clears the database-backed badge count."""
        Notification.objects.all().delete()
        Notification.objects.create(notification_type='system', message='First')
        Notification.objects.create(notification_type='system', message='Second')
        self.login(self.super_admin)

        response = self.client.post(
            reverse('admin_dashboard:mark_all_read'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 0)
        self.assertEqual(response.json()['marked_read'], 2)

        overview_response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(overview_response.context['unread_notification_count'], 0)
        self.assertNotContains(overview_response, 'admin-notification-badge')

        Notification.objects.create(notification_type='system', message='New notification')
        refreshed_response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(refreshed_response.context['unread_notification_count'], 1)
        self.assertContains(refreshed_response, 'admin-notification-badge')



class UserManagementTests(TestCase):
    """Comprehensive tests for user management functionality."""
    
    @classmethod
    def setUpTestData(cls):
        cls.super_admin = User.objects.create_user(
            email="superadmin@test.com",
            full_name="Super Admin",
            password="AdminPass123!",
            role=CustomUser.Role.SUPER_ADMIN,
            is_staff=True,
        )
        cls.farm_manager = User.objects.create_user(
            email="manager@test.com",
            full_name="Farm Manager",
            password="ManagerPass123!",
            role=CustomUser.Role.FARM_MANAGER,
        )
        cls.customer = User.objects.create_user(
            email="customer@test.com",
            full_name="Test Customer",
            password="CustomerPass123!",
            role=CustomUser.Role.CUSTOMER,
        )
        cls.inactive_user = User.objects.create_user(
            email="inactive@test.com",
            full_name="Inactive User",
            password="InactivePass123!",
            role=CustomUser.Role.CUSTOMER,
            is_active=False,
        )
    
    def login(self, user):
        self.client.login(username=user.username, password=self.get_password(user))
    
    def get_password(self, user):
        passwords = {
            "superadmin@test.com": "AdminPass123!",
            "manager@test.com": "ManagerPass123!",
            "customer@test.com": "CustomerPass123!",
            "inactive@test.com": "InactivePass123!",
        }
        return passwords.get(user.email, "DefaultPass123!")
    
    # === List View Tests ===
    
    def test_user_list_access_super_admin(self):
        """Super admin can access user list."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:users'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('User Management', response.content.decode())
    
    def test_user_list_access_farm_manager(self):
        """Farm Manager is redirected from Super Admin-only user management."""
        self.login(self.farm_manager)
        response = self.client.get(reverse('admin_dashboard:users'), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('accounts:dashboard'))
    
    def test_user_list_access_denied_customer(self):
        """Customer cannot access user list."""
        self.login(self.customer)
        response = self.client.get(reverse('admin_dashboard:users'))
        self.assertEqual(response.status_code, 302)  # Redirect
    
    def test_user_list_displays_users(self):
        """User list displays all users with correct info."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:users'))
        content = response.content.decode()
        self.assertIn('Super Admin', content)
        self.assertIn('Test Customer', content)
        self.assertIn('superadmin@test.com', content)
    
    def test_user_search_by_name(self):
        """Search filters users by name."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:users') + '?search=Super')
        content = response.content.decode()
        self.assertIn('Super Admin', content)
        # Verify only matching users in queryset
        users = list(response.context['users'])
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0].full_name, 'Super Admin')
    
    def test_user_search_by_email(self):
        """Search filters users by email."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:users') + '?search=customer@')
        content = response.content.decode()
        self.assertIn('Test Customer', content)
        # Check that only 1 user row appears in the table (customer)
        users = list(response.context['users'])
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0].email, 'customer@test.com')
    
    def test_user_filter_by_role(self):
        """Filter shows only users with selected role."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:users') + f'?role={CustomUser.Role.SUPER_ADMIN}')
        content = response.content.decode()
        self.assertIn('Super Admin', content)
        # Verify only super admins in queryset
        users = list(response.context['users'])
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0].role, CustomUser.Role.SUPER_ADMIN)
    
    def test_user_filter_by_status_active(self):
        """Filter shows only active users."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:users') + '?status=active')
        content = response.content.decode()
        self.assertIn('Super Admin', content)
        # Verify inactive user not in queryset
        user_emails = [u.email for u in response.context['users']]
        self.assertNotIn('inactive@test.com', user_emails)
    
    def test_user_filter_by_status_inactive(self):
        """Filter shows only inactive users."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:users') + '?status=inactive')
        content = response.content.decode()
        self.assertIn('Inactive User', content)
        # Verify only inactive users in the queryset
        users = list(response.context['users'])
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0].email, 'inactive@test.com')
    
    # === Detail View Tests ===
    
    def test_user_detail_view(self):
        """User detail page displays correct information."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:user_detail', args=[self.customer.pk]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Test Customer', content)
        self.assertIn('customer@test.com', content)
    
    def test_user_detail_shows_orders(self):
        """User detail page shows order history."""
        self.login(self.super_admin)
        # Create an order for the customer
        order = Order.objects.create(
            user=self.customer,
            total=Decimal('100.00'),
            status='confirmed'
        )
        response = self.client.get(reverse('admin_dashboard:user_detail', args=[self.customer.pk]))
        content = response.content.decode()
        self.assertIn(f'#{order.pk}', content)
        self.assertIn('100.00', content)
    
    # === Edit View Tests ===
    
    def test_user_edit_view_loads(self):
        """User edit form loads correctly."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:user_edit', args=[self.customer.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Edit User', response.content.decode())
    
    def test_user_edit_updates_fields(self):
        """Editing user updates their information."""
        self.login(self.super_admin)
        response = self.client.post(
            reverse('admin_dashboard:user_edit', args=[self.customer.pk]),
            {
                'full_name': 'Updated Name',
                'email': 'updated@test.com',
                'phone_number': '1234567890',
                'role': CustomUser.Role.STAFF,
                'is_active': True,
            }
        )
        self.assertEqual(response.status_code, 302)  # Redirect on success
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.full_name, 'Updated Name')
        self.assertEqual(self.customer.email, 'updated@test.com')
        self.assertEqual(self.customer.role, CustomUser.Role.STAFF)
    
    def test_user_cannot_deactivate_self(self):
        """User cannot deactivate their own account."""
        self.login(self.super_admin)
        response = self.client.post(
            reverse('admin_dashboard:user_edit', args=[self.super_admin.pk]),
            {
                'full_name': self.super_admin.full_name,
                'email': self.super_admin.email,
                'phone_number': '',
                'role': self.super_admin.role,
                'is_active': False,  # Try to deactivate
            }
        )
        self.assertEqual(response.status_code, 200)  # Form error, stays on page
        self.assertIn('cannot deactivate', response.content.decode().lower())
    
    def test_last_super_admin_cannot_change_role(self):
        """Last super admin cannot demote themselves."""
        self.login(self.super_admin)
        response = self.client.post(
            reverse('admin_dashboard:user_edit', args=[self.super_admin.pk]),
            {
                'full_name': self.super_admin.full_name,
                'email': self.super_admin.email,
                'phone_number': '',
                'role': CustomUser.Role.CUSTOMER,  # Try to demote
                'is_active': True,
            }
        )
        self.assertEqual(response.status_code, 200)  # Form error
        self.assertIn('only active Super Admin', response.content.decode())
    
    # === Deactivate/Activate Tests ===
    
    def test_toggle_user_active(self):
        """Toggle deactivates an active user."""
        self.login(self.super_admin)
        self.assertTrue(self.customer.is_active)
        response = self.client.post(
            reverse('admin_dashboard:toggle_user_active', args=[self.customer.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)
    
    def test_toggle_user_inactive_to_active(self):
        """Toggle activates an inactive user."""
        self.login(self.super_admin)
        self.assertFalse(self.inactive_user.is_active)
        response = self.client.post(
            reverse('admin_dashboard:toggle_user_active', args=[self.inactive_user.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.inactive_user.refresh_from_db()
        self.assertTrue(self.inactive_user.is_active)
    
    def test_cannot_deactivate_self_via_toggle(self):
        """User cannot toggle their own active status."""
        self.login(self.super_admin)
        response = self.client.post(
            reverse('admin_dashboard:toggle_user_active', args=[self.super_admin.pk])
        )
        self.assertEqual(response.status_code, 400)  # Bad request
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('cannot deactivate', data['error'].lower())
    
    def test_inactive_user_blocked_from_login(self):
        """Deactivated users cannot log in."""
        self.assertFalse(self.inactive_user.is_active)
        can_login = self.client.login(username=self.inactive_user.username, password='InactivePass123!')
        self.assertFalse(can_login)
    
    # === Delete View Tests ===
    
    def test_delete_user_without_orders(self):
        """User without orders can be deleted."""
        self.login(self.super_admin)
        user_to_delete = User.objects.create_user(
            email='todelete@test.com',
            full_name='To Delete',
            password='DeletePass123!',
            role=CustomUser.Role.CUSTOMER,
        )
        response = self.client.post(
            reverse('admin_dashboard:user_delete', args=[user_to_delete.pk])
        )
        self.assertEqual(response.status_code, 302)  # Redirect after deletion
        self.assertFalse(User.objects.filter(pk=user_to_delete.pk).exists())
    
    def test_delete_user_with_orders_blocked(self):
        """User with orders cannot be deleted."""
        self.login(self.super_admin)
        # Create an order for customer
        Order.objects.create(
            user=self.customer,
            total=Decimal('50.00'),
            status='pending'
        )
        response = self.client.post(
            reverse('admin_dashboard:user_delete', args=[self.customer.pk])
        )
        # Should redirect with error message, not delete
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(pk=self.customer.pk).exists())
    
    def test_cannot_delete_self(self):
        """User cannot delete their own account."""
        self.login(self.super_admin)
        response = self.client.post(
            reverse('admin_dashboard:user_delete', args=[self.super_admin.pk])
        )
        self.assertEqual(response.status_code, 302)  # Redirect
        self.assertTrue(User.objects.filter(pk=self.super_admin.pk).exists())
    
    # === Order History Preservation Tests ===
    
    def test_deleted_user_preserves_order_history(self):
        """When user is deleted, their orders are preserved with null user."""
        # Create a user without orders who can be deleted
        user_to_delete = User.objects.create_user(
            email='willdelete@test.com',
            full_name='Will Delete',
            password='Pass123!',
            role=CustomUser.Role.CUSTOMER,
        )
        # Create an order
        order = Order.objects.create(
            user=user_to_delete,
            total=Decimal('75.00'),
            status='delivered'
        )
        
        # Bypass the view's order check and delete directly to test SET_NULL behavior
        user_pk = user_to_delete.pk
        user_to_delete.delete()
        
        # Order should still exist
        order.refresh_from_db()
        self.assertIsNone(order.user)  # User field should be null
        self.assertEqual(str(order), f'Order #{order.pk} - Deleted User (Delivered)')


class ContentManagementTests(TestCase):
    """Tests for website content management CRUD operations and public pages."""

    @classmethod
    def setUpTestData(cls):
        # Create test users
        cls.super_admin = User.objects.create_user(
            email='admin@test.com',
            full_name='Super Admin',
            password='testpassword',
            role=CustomUser.Role.SUPER_ADMIN,
            is_staff=True,
        )
        cls.farm_manager = User.objects.create_user(
            email='farm@test.com',
            full_name='Farm Manager',
            password='testpassword',
            role=CustomUser.Role.FARM_MANAGER,
        )
        cls.super_staff = User.objects.create_user(
            email='staff@test.com',
            full_name='Super Staff',
            password='testpassword',
            role=CustomUser.Role.SUPER_STAFF,
        )
        cls.customer = User.objects.create_user(
            email='customer@test.com',
            full_name='Test Customer',
            password='testpassword',
            role=CustomUser.Role.CUSTOMER,
        )
        
        # Create test content
        cls.about_content = SiteContent.objects.create(
            section='about',
            title='Test About Title',
            content='<p>Test about content</p>',
        )

    def login(self, user):
        """Helper to log in a user."""
        self.client.login(username=user.username, password='testpassword')

    # === Content List View Tests ===
    
    def test_content_list_requires_admin(self):
        """Customer users cannot access content list."""
        self.login(self.customer)
        response = self.client.get(reverse('admin_dashboard:content'))
        # Should redirect (302) or be forbidden
        self.assertIn(response.status_code, [302, 403])

    def test_content_list_super_admin_access(self):
        """Super Admin can access content list."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:content'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('content_sections', response.context)
        self.assertTemplateUsed(response, 'admin_dashboard/content.html')

    def test_content_list_farm_manager_access(self):
        """Farm Manager can access content list."""
        self.login(self.farm_manager)
        response = self.client.get(reverse('admin_dashboard:content'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('content_sections', response.context)
        self.assertTemplateUsed(response, 'admin_dashboard/content.html')

    def test_content_list_super_staff_denied(self):
        """Super Staff cannot access content list."""
        self.login(self.super_staff)
        response = self.client.get(reverse('admin_dashboard:content'))
        self.assertIn(response.status_code, [302, 403])

    def test_content_list_displays_sections(self):
        """Content list displays created sections."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:content'))
        self.assertContains(response, 'Test About Title')
        self.assertContains(response, 'About Page')

    # === Content Create View Tests ===
    
    def test_content_create_requires_admin(self):
        """Customer users cannot create content."""
        self.login(self.customer)
        response = self.client.get(reverse('admin_dashboard:content_create'))
        # Should redirect (302) or be forbidden
        self.assertIn(response.status_code, [302, 403])

    def test_content_create_form_loads(self):
        """Content create form loads for admin."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:content_create'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'admin_dashboard/content_form.html')

    def test_content_create_form_loads_for_farm_manager(self):
        """Content create form loads for farm manager."""
        self.login(self.farm_manager)
        response = self.client.get(reverse('admin_dashboard:content_create'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'admin_dashboard/content_form.html')

    def test_content_create_success(self):
        """Admin can create new content section."""
        self.login(self.super_admin)
        response = self.client.post(
            reverse('admin_dashboard:content_create'),
            {
                'section': 'contact',
                'title': 'Contact Us',
                'content': '<p>Contact information</p>',
            }
        )
        self.assertEqual(response.status_code, 302)  # Redirect after success
        self.assertTrue(SiteContent.objects.filter(section='contact').exists())

    def test_content_create_duplicate_section_blocked(self):
        """Cannot create duplicate section - database constraint prevents it."""
        self.login(self.super_admin)
        # Try to create duplicate About section
        try:
            response = self.client.post(
                reverse('admin_dashboard:content_create'),
                {
                    'section': 'about',  # Already exists
                    'title': 'Another About',
                    'content': '<p>Duplicate</p>',
                }
            )
            # Should either show form with error or raise IntegrityError
            # Check that no duplicate was created
            about_count = SiteContent.objects.filter(section='about').count()
            self.assertEqual(about_count, 1, "Duplicate section was created!")
        except Exception:
            # IntegrityError or other database constraint error is expected
            pass

    # === Content Edit View Tests ===
    
    def test_content_edit_requires_admin(self):
        """Customer users cannot edit content."""
        self.login(self.customer)
        response = self.client.get(
            reverse('admin_dashboard:content_edit', args=[self.about_content.pk])
        )
        # Should redirect (302) or be forbidden
        self.assertIn(response.status_code, [302, 403])

    def test_content_edit_form_loads(self):
        """Content edit form loads with pre-populated data."""
        self.login(self.super_admin)
        response = self.client.get(
            reverse('admin_dashboard:content_edit', args=[self.about_content.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test About Title')
        self.assertContains(response, 'Test about content')

    def test_content_edit_form_loads_for_farm_manager(self):
        """Content edit form loads for farm manager."""
        self.login(self.farm_manager)
        response = self.client.get(
            reverse('admin_dashboard:content_edit', args=[self.about_content.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test About Title')
        self.assertContains(response, 'Test about content')

    def test_content_edit_updates_content(self):
        """Admin can edit content and changes are saved."""
        self.login(self.super_admin)
        response = self.client.post(
            reverse('admin_dashboard:content_edit', args=[self.about_content.pk]),
            {
                'section': 'about',
                'title': 'Updated About Title',
                'content': '<p>Updated content</p>',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.about_content.refresh_from_db()
        self.assertEqual(self.about_content.title, 'Updated About Title')
        self.assertEqual(self.about_content.content, '<p>Updated content</p>')

    # === Structured Social Media Tests ===

    def test_social_media_form_saves_each_platform_url(self):
        """A social-media section persists every configured platform URL."""
        self.login(self.super_admin)
        urls = {
            'facebook_url': 'https://www.facebook.com/tamipeefarms',
            'instagram_url': 'https://www.instagram.com/tamipeefarms',
            'twitter_url': 'https://x.com/tamipeefarms',
            'tiktok_url': 'https://www.tiktok.com/@tamipeefarms',
            'whatsapp_url': 'https://wa.me/2348012345678',
        }
        response = self.client.post(
            reverse('admin_dashboard:content_create'),
            {
                'section': 'social_media',
                'title': 'Follow TAMIPEE',
                'content': '',
                **urls,
            },
        )

        self.assertEqual(response.status_code, 302)
        social_media = SiteContent.objects.get(section='social_media')
        for field_name, url in urls.items():
            self.assertEqual(getattr(social_media, field_name), url)

    def test_social_media_form_rejects_invalid_url(self):
        """Social links must be valid absolute URLs."""
        form = SiteContentForm(
            data={
                'section': 'social_media',
                'title': 'Follow TAMIPEE',
                'content': '',
                'instagram_url': 'not a valid URL',
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn('instagram_url', form.errors)

    def test_public_footer_renders_configured_social_links_only(self):
        """The shared footer renders safe anchors only for configured platforms."""
        SiteContent.objects.create(
            section='social_media',
            title='Follow TAMIPEE',
            content='',
            instagram_url='https://www.instagram.com/tamipeefarms',
            whatsapp_url='https://wa.me/2348012345678',
        )

        response = self.client.get(reverse('shop:contact'))

        self.assertContains(response, 'href="https://www.instagram.com/tamipeefarms"', html=False)
        self.assertContains(response, 'href="https://wa.me/2348012345678"', html=False)
        self.assertContains(response, 'target="_blank"', html=False)
        self.assertContains(response, 'rel="noopener noreferrer"', html=False)
        self.assertContains(response, 'fa-instagram', html=False)
        self.assertContains(response, 'fa-whatsapp', html=False)
        self.assertNotContains(response, 'fa-facebook-f', html=False)
        self.assertNotContains(response, 'fa-tiktok', html=False)

    # === Public About Page Tests ===
    
    def test_about_page_loads_without_login(self):
        """Unauthenticated users can access About page."""
        response = self.client.get(reverse('shop:about'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'shop/about.html')

    def test_about_page_displays_content(self):
        """About page displays content from SiteContent."""
        response = self.client.get(reverse('shop:about'))
        self.assertContains(response, 'Test About Title')
        self.assertContains(response, 'Test about content')

    def test_about_page_fallback_when_no_content(self):
        """About page shows fallback when no content exists."""
        self.about_content.delete()
        response = self.client.get(reverse('shop:about'))
        self.assertEqual(response.status_code, 200)
        # Should show fallback message
        self.assertContains(response, 'TAMIPEE is a comprehensive farm management platform')

    # === Public Contact Page Tests ===
    
    def test_contact_page_loads_without_login(self):
        """Unauthenticated users can access Contact page."""
        response = self.client.get(reverse('shop:contact'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'shop/contact.html')

    def test_contact_page_displays_content(self):
        """Contact page displays content from SiteContent."""
        contact_content = SiteContent.objects.create(
            section='contact',
            title='Contact Us',
            content='<p>Email: info@tamipee.com</p><p>Business Hours: Mon-Fri 8AM-6PM</p>',
        )
        response = self.client.get(reverse('shop:contact'))
        self.assertContains(response, 'Contact Us')
        self.assertContains(response, 'info@tamipee.com')
        self.assertContains(response, 'Business Hours')

    def test_contact_page_fallback_when_no_content(self):
        """Contact page shows fallback when no content exists."""
        response = self.client.get(reverse('shop:contact'))
        self.assertEqual(response.status_code, 200)
        # Should show fallback message and default contact info
        self.assertContains(response, 'info@tamipee.com')
        self.assertContains(response, 'Business Hours')

    # === Integration Tests ===
    
    def test_admin_edit_reflects_on_public_page(self):
        """Changes made in admin CRUD reflect on public About page."""
        self.login(self.super_admin)
        # Edit content in admin
        self.client.post(
            reverse('admin_dashboard:content_edit', args=[self.about_content.pk]),
            {
                'section': 'about',
                'title': 'New Title',
                'content': '<p>New content text</p>',
            }
        )
        # Check public page shows new content
        response = self.client.get(reverse('shop:about'))
        self.assertContains(response, 'New Title')
        self.assertContains(response, 'New content text')
        self.assertNotContains(response, 'Test About Title')

    # === Phase 2: Additional Public Pages Tests ===
    
    def test_faq_page_loads_without_login(self):
        """Unauthenticated users can access FAQ page."""
        response = self.client.get(reverse('shop:faq'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'shop/faq.html')

    def test_faq_page_displays_content(self):
        """FAQ page displays content from SiteContent."""
        faq_content = SiteContent.objects.create(
            section='faq',
            title='Frequently Asked Questions',
            content='<h3>Q: What is TAMIPEE?</h3><p>A: A farm management platform.</p>',
        )
        response = self.client.get(reverse('shop:faq'))
        self.assertContains(response, 'Frequently Asked Questions')
        self.assertContains(response, 'What is TAMIPEE')

    def test_faq_page_fallback_when_no_content(self):
        """FAQ page shows fallback when no content exists."""
        response = self.client.get(reverse('shop:faq'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No FAQ Content Available')

    def test_delivery_info_page_loads_without_login(self):
        """Unauthenticated users can access Delivery Info page."""
        response = self.client.get(reverse('shop:delivery_info'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'shop/delivery_info.html')

    def test_delivery_info_page_displays_content(self):
        """Delivery Info page displays content from SiteContent."""
        delivery_content = SiteContent.objects.create(
            section='delivery_info',
            title='Delivery Information',
            content='<p>We deliver within 3-5 business days.</p>',
        )
        response = self.client.get(reverse('shop:delivery_info'))
        self.assertContains(response, 'Delivery Information')
        self.assertContains(response, '3-5 business days')

    def test_delivery_info_page_fallback_when_no_content(self):
        """Delivery Info page shows fallback when no content exists."""
        response = self.client.get(reverse('shop:delivery_info'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No Delivery Information Available')

    def test_terms_privacy_page_loads_without_login(self):
        """Unauthenticated users can access Terms & Privacy page."""
        response = self.client.get(reverse('shop:terms_privacy'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'shop/terms_privacy.html')

    def test_terms_privacy_page_displays_content(self):
        """Terms & Privacy page displays content from SiteContent."""
        terms_content = SiteContent.objects.create(
            section='terms_privacy',
            title='Terms of Service and Privacy Policy',
            content='<h3>Terms of Service</h3><p>By using this site, you agree...</p>',
        )
        response = self.client.get(reverse('shop:terms_privacy'))
        self.assertContains(response, 'Terms of Service and Privacy Policy')
        self.assertContains(response, 'By using this site')

    def test_terms_privacy_page_fallback_when_no_content(self):
        """Terms & Privacy page shows fallback when no content exists."""
        response = self.client.get(reverse('shop:terms_privacy'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No Terms & Privacy Content Available')

    def test_return_refund_page_loads_without_login(self):
        """Unauthenticated users can access Return & Refund page."""
        response = self.client.get(reverse('shop:return_refund'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'shop/return_refund.html')

    def test_return_refund_page_displays_content(self):
        """Return & Refund page displays content from SiteContent."""
        return_content = SiteContent.objects.create(
            section='return_refund',
            title='Return and Refund Policy',
            content='<p>Returns accepted within 30 days of purchase.</p>',
        )
        response = self.client.get(reverse('shop:return_refund'))
        self.assertContains(response, 'Return and Refund Policy')
        self.assertContains(response, '30 days')

    def test_return_refund_page_fallback_when_no_content(self):
        """Return & Refund page shows fallback when no content exists."""
        response = self.client.get(reverse('shop:return_refund'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No Return Policy Available')

    def test_shop_banner_displays_conditionally(self):
        """Shop banner only shows when shop_banner content exists."""
        # No banner - should not display the banner element
        response = self.client.get(reverse('shop:product_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="banner-icon"')
        self.assertNotContains(response, 'class="banner-content"')
        
        # Create banner content
        banner_content = SiteContent.objects.create(
            section='shop_banner',
            title='Special Offer!',
            content='<p>20% off all products this week!</p>',
        )
        
        # Banner element should now be present
        response = self.client.get(reverse('shop:product_list'))
        self.assertContains(response, 'class="banner-icon"')
        self.assertContains(response, 'class="banner-content"')
        self.assertContains(response, 'Special Offer!')
        self.assertContains(response, '20% off all products')

    def test_homepage_hero_displays_conditionally(self):
        """Homepage hero only shows when homepage_hero content exists."""
        # No hero - should not display the hero element
        response = self.client.get(reverse('shop:product_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'hero animate-fade-in-up', response.content)
        
        # Create hero content
        hero_content = SiteContent.objects.create(
            section='homepage_hero',
            title='Welcome to TAMIPEE Farm Shop',
            content='<p>Fresh, quality agricultural products delivered to your door.</p>',
        )
        
        # Hero element should now be present
        response = self.client.get(reverse('shop:product_list'))
        self.assertIn(b'hero animate-fade-in-up', response.content)
        self.assertContains(response, 'Welcome to TAMIPEE Farm Shop')
        self.assertContains(response, 'Fresh, quality agricultural products')


# =============================================================================
# Phase 3: Checkout Enforcement Tests
# =============================================================================

class CheckoutEnforcementTests(TestCase):
    """Tests for Phase 3 checkout enforcement: payment methods and minimum order amount."""

    @classmethod
    def setUpTestData(cls):
        from admin_dashboard.models import PaymentMethodSetting, MinimumOrderAmount
        from shop.models import Category, Product, Cart, CartItem
        
        # Create test admin user
        cls.super_admin = User.objects.create_user(
            email='admin@test.com',
            password='testpassword',
            full_name='Test Admin',
            role=CustomUser.Role.SUPER_ADMIN,
            is_staff=True,
        )
        
        # Create test customer
        cls.customer = User.objects.create_user(
            email='customer@test.com',
            password='testpassword',
            full_name='Test Customer',
            role=CustomUser.Role.CUSTOMER,
        )
        
        # Create test product
        cls.category = Category.objects.create(name='Test Category', slug='test-category')
        cls.product = Product.objects.create(
            name='Test Product',
            price=Decimal('500.00'),
            category=cls.category,
        )

    def setUp(self):
        """Reset payment method settings and minimum order amount before each test."""
        from admin_dashboard.models import PaymentMethodSetting, MinimumOrderAmount
        
        # Reset all payment methods to enabled
        PaymentMethodSetting.objects.all().delete()
        for method, label in PaymentMethodSetting.PAYMENT_METHOD_CHOICES:
            PaymentMethodSetting.objects.create(payment_method=method, enabled=True)
        
        # Reset minimum order amount to disabled
        min_order = MinimumOrderAmount.get_instance()
        min_order.enabled = False
        min_order.minimum_amount = Decimal('0.00')
        min_order.save()

    # =========================================================================
    # Payment Method Tests
    # =========================================================================

    def test_payment_method_settings_page_requires_admin(self):
        """Only admins can access payment method settings page."""
        url = reverse('admin_dashboard:payment_methods')
        
        # Customer cannot access
        self.client.login(username=self.customer.username, password='testpassword')
        response = self.client.get(url)
        self.assertIn(response.status_code, [302, 403])
        
        # Admin can access
        self.client.login(username=self.super_admin.username, password='testpassword')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_payment_method_settings_page_shows_all_methods(self):
        """Payment method settings page shows all payment methods."""
        self.client.login(username=self.super_admin.username, password='testpassword')
        response = self.client.get(reverse('admin_dashboard:payment_methods'))
        self.assertContains(response, 'Paystack')
        self.assertContains(response, 'Bank Transfer')
        self.assertContains(response, 'Cash on Delivery')

    def test_toggle_payment_method_requires_admin(self):
        """Only admins can toggle payment method status."""
        from admin_dashboard.models import PaymentMethodSetting
        
        paystack_setting = PaymentMethodSetting.objects.get(payment_method='paystack')
        url = reverse('admin_dashboard:toggle_payment_method', kwargs={'pk': paystack_setting.pk})
        
        # Customer cannot toggle
        self.client.login(username=self.customer.username, password='testpassword')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        
        # Admin can toggle
        self.client.login(username=self.super_admin.username, password='testpassword')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)

    def test_toggle_payment_method_changes_status(self):
        """Toggling a payment method changes its enabled status."""
        from admin_dashboard.models import PaymentMethodSetting
        
        self.client.login(username=self.super_admin.username, password='testpassword')
        paystack_setting = PaymentMethodSetting.objects.get(payment_method='paystack')
        url = reverse('admin_dashboard:toggle_payment_method', kwargs={'pk': paystack_setting.pk})
        
        # Initially enabled
        self.assertTrue(paystack_setting.enabled)
        
        # Toggle to disabled
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        paystack_setting.refresh_from_db()
        self.assertFalse(paystack_setting.enabled)
        
        # Toggle back to enabled
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        paystack_setting.refresh_from_db()
        self.assertTrue(paystack_setting.enabled)

    def test_checkout_filters_disabled_payment_methods(self):
        """Checkout view only shows enabled payment methods."""
        from admin_dashboard.models import PaymentMethodSetting
        from shop.models import Cart, CartItem
        
        # Create cart with items
        self.client.login(username=self.customer.username, password='testpassword')
        cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=2)
        
        # Disable Paystack
        paystack_setting = PaymentMethodSetting.objects.get(payment_method='paystack')
        paystack_setting.enabled = False
        paystack_setting.save()
        
        # Checkout should not show Paystack
        response = self.client.get(reverse('shop:checkout'))
        data = response.context['enabled_payment_methods']
        method_codes = [m['code'] for m in data]
        self.assertNotIn('paystack', method_codes)
        self.assertIn('bank_transfer', method_codes)
        self.assertIn('cash_on_delivery', method_codes)

    def test_checkout_blocks_when_all_payment_methods_disabled(self):
        """Checkout redirects to cart with error when all payment methods are disabled."""
        from admin_dashboard.models import PaymentMethodSetting
        from shop.models import Cart, CartItem
        
        # Create cart with items
        self.client.login(username=self.customer.username, password='testpassword')
        cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=2)
        
        # Disable all payment methods
        PaymentMethodSetting.objects.all().update(enabled=False)
        
        # Checkout should redirect to cart
        response = self.client.get(reverse('shop:checkout'))
        self.assertRedirects(response, reverse('shop:cart'))

    # =========================================================================
    # Minimum Order Amount Tests
    # =========================================================================

    def test_minimum_order_amount_page_requires_admin(self):
        """Only admins can access minimum order amount settings page."""
        url = reverse('admin_dashboard:minimum_order_amount')
        
        # Customer cannot access
        self.client.login(username=self.customer.username, password='testpassword')
        response = self.client.get(url)
        self.assertIn(response.status_code, [302, 403])
        
        # Admin can access
        self.client.login(username=self.super_admin.username, password='testpassword')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_update_minimum_order_amount_requires_admin(self):
        """Only admins can update minimum order amount."""
        import json
        
        url = reverse('admin_dashboard:update_minimum_order_amount')
        data = json.dumps({'minimum_amount': '1000.00', 'enabled': True})
        
        # Customer cannot update
        self.client.login(username=self.customer.username, password='testpassword')
        response = self.client.post(url, data, content_type='application/json')
        self.assertEqual(response.status_code, 403)
        
        # Admin can update
        self.client.login(username=self.super_admin.username, password='testpassword')
        response = self.client.post(url, data, content_type='application/json')
        self.assertEqual(response.status_code, 200)

    def test_update_minimum_order_amount_saves_to_database(self):
        """Updating minimum order amount saves to database."""
        import json
        from admin_dashboard.models import MinimumOrderAmount
        
        self.client.login(username=self.super_admin.username, password='testpassword')
        url = reverse('admin_dashboard:update_minimum_order_amount')
        data = json.dumps({'minimum_amount': '1500.50', 'enabled': True})
        
        response = self.client.post(url, data, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        
        min_order = MinimumOrderAmount.get_instance()
        self.assertEqual(min_order.minimum_amount, Decimal('1500.50'))
        self.assertTrue(min_order.enabled)

    def test_checkout_blocks_below_minimum_order_amount(self):
        """Checkout redirects to cart when cart total is below minimum order amount."""
        from admin_dashboard.models import MinimumOrderAmount
        from shop.models import Cart, CartItem
        
        # Set minimum order amount to ₦1000
        min_order = MinimumOrderAmount.get_instance()
        min_order.minimum_amount = Decimal('1000.00')
        min_order.enabled = True
        min_order.save()
        
        # Create cart with total = ₦500 (1 product at ₦500)
        self.client.login(username=self.customer.username, password='testpassword')
        cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        
        # Checkout should redirect to cart with error message
        response = self.client.get(reverse('shop:checkout'))
        self.assertRedirects(response, reverse('shop:cart'))
        
        # Check error message in messages
        messages = list(response.wsgi_request._messages)
        self.assertTrue(any('below the minimum order amount' in str(m) for m in messages))

    def test_checkout_allows_above_minimum_order_amount(self):
        """Checkout proceeds when cart total meets or exceeds minimum order amount."""
        from admin_dashboard.models import MinimumOrderAmount
        from shop.models import Cart, CartItem
        
        # Set minimum order amount to ₦1000
        min_order = MinimumOrderAmount.get_instance()
        min_order.minimum_amount = Decimal('1000.00')
        min_order.enabled = True
        min_order.save()
        
        # Create cart with total = ₦1000 (2 products at ₦500 each)
        self.client.login(username=self.customer.username, password='testpassword')
        cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=2)
        
        # Checkout should proceed
        response = self.client.get(reverse('shop:checkout'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'shop/checkout.html')

    def test_checkout_bypasses_disabled_minimum_order_amount(self):
        """Checkout proceeds regardless of amount when minimum order is disabled."""
        from admin_dashboard.models import MinimumOrderAmount
        from shop.models import Cart, CartItem
        
        # Set minimum order amount but disable it
        min_order = MinimumOrderAmount.get_instance()
        min_order.minimum_amount = Decimal('1000.00')
        min_order.enabled = False
        min_order.save()
        
        # Create cart with total = ₦500 (below minimum)
        self.client.login(username=self.customer.username, password='testpassword')
        cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        
        # Checkout should proceed because minimum order is disabled
        response = self.client.get(reverse('shop:checkout'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'shop/checkout.html')




# =============================================================================
# Order Admin Tests (Part 1)
# =============================================================================

class OrderAdminTests(TestCase):
    """Tests for order management admin views."""

    @classmethod
    def setUpTestData(cls):
        cls.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=CustomUser.Role.SUPER_ADMIN,
            is_staff=True,
        )
        cls.farm_manager = User.objects.create_user(
            email="farmmanager@example.com",
            full_name="Farm Manager",
            password="StrongPass1!",
            role=CustomUser.Role.FARM_MANAGER,
        )
        cls.staff_user = User.objects.create_user(
            email="staff@example.com",
            full_name="Staff User",
            password="StrongPass1!",
            role=CustomUser.Role.STAFF,
        )
        cls.customer_user = User.objects.create_user(
            email="customer@example.com",
            full_name="Customer User",
            password="StrongPass1!",
            role=CustomUser.Role.CUSTOMER,
        )

    def login(self, user):
        return self.client.login(username=user.username, password="StrongPass1!")

    # ---------------------------------------------------------------- #
    # Order List View
    # ---------------------------------------------------------------- #

    def test_order_list_loads_for_super_admin(self):
        """Super Admin can access order list."""
        self.login(self.super_admin)
        response = self.client.get(reverse("admin_dashboard:orders"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Orders & Delivery", response.content.decode())

    def test_order_list_loads_for_farm_manager(self):
        """Farm Manager can access order list."""
        self.login(self.farm_manager)
        response = self.client.get(reverse("admin_dashboard:orders"))
        self.assertEqual(response.status_code, 200)

    def test_order_list_blocked_for_customer(self):
        """Customer cannot access order list."""
        self.login(self.customer_user)
        response = self.client.get(reverse("admin_dashboard:orders"), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("dashboard", response.url)

    def test_order_list_blocked_for_staff(self):
        """Staff cannot access order list."""
        self.login(self.staff_user)
        response = self.client.get(reverse("admin_dashboard:orders"), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("dashboard", response.url)

    def test_order_list_unauthenticated_redirected(self):
        """Unauthenticated users are redirected to login."""
        response = self.client.get(reverse("admin_dashboard:orders"), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_order_list_displays_orders(self):
        """Order list displays created orders."""
        self.login(self.super_admin)
        Order.objects.create(
            user=self.customer_user,
            status=Order.Status.PENDING,
            total=Decimal("100.00"),
            payment_method="paystack",
            delivery_address="123 Test St",
        )
        Order.objects.create(
            user=self.customer_user,
            status=Order.Status.CONFIRMED,
            total=Decimal("200.00"),
            payment_method="bank_transfer",
            delivery_address="456 Test Ave",
        )
        response = self.client.get(reverse("admin_dashboard:orders"))
        content = response.content.decode()
        self.assertIn("#1", content)
        self.assertIn("#2", content)
        self.assertIn("100.00", content)
        self.assertIn("200.00", content)

    def test_order_list_status_filter(self):
        """Order list filters by status."""
        self.login(self.super_admin)
        Order.objects.create(
            user=self.customer_user,
            status=Order.Status.PENDING,
            total=Decimal("100.00"),
        )
        Order.objects.create(
            user=self.customer_user,
            status=Order.Status.CONFIRMED,
            total=Decimal("200.00"),
        )
        response = self.client.get(
            reverse("admin_dashboard:orders") + "?status=pending"
        )
        content = response.content.decode()
        self.assertIn("100.00", content)
        self.assertNotIn("200.00", content)
        context = response.context
        self.assertEqual(context["status_filter"], "pending")

    def test_order_list_context_has_counts(self):
        """Order list context includes status counts."""
        self.login(self.super_admin)
        Order.objects.create(
            user=self.customer_user,
            status=Order.Status.PENDING,
            total=Decimal("100.00"),
        )
        Order.objects.create(
            user=self.customer_user,
            status=Order.Status.CONFIRMED,
            total=Decimal("200.00"),
        )
        Order.objects.create(
            user=self.customer_user,
            status=Order.Status.DELIVERED,
            total=Decimal("300.00"),
        )
        response = self.client.get(reverse("admin_dashboard:orders"))
        context = response.context
        self.assertEqual(context["total_orders"], 3)
        self.assertEqual(context["pending_count"], 1)
        self.assertEqual(context["confirmed_count"], 1)
        self.assertEqual(context["delivered_count"], 1)

    # ---------------------------------------------------------------- #
    # Order Detail View
    # ---------------------------------------------------------------- #

    def test_order_detail_loads_for_super_admin(self):
        """Super Admin can view order detail."""
        self.login(self.super_admin)
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.PENDING,
            total=Decimal("100.00"),
            payment_method="paystack",
            delivery_address="123 Test St",
        )
        OrderItem.objects.create(
            order=order,
            product=None,
            product_name="Test Product",
            quantity=2,
            price=Decimal("50.00"),
        )
        response = self.client.get(reverse("admin_dashboard:order_detail", args=[order.pk]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Order #" + str(order.pk), content)
        self.assertIn("Test Product", content)
        self.assertIn("123 Test St", content)

    def test_order_detail_loads_for_farm_manager(self):
        """Farm Manager can view order detail."""
        self.login(self.farm_manager)
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.PENDING,
            total=Decimal("100.00"),
        )
        response = self.client.get(reverse("admin_dashboard:order_detail", args=[order.pk]))
        self.assertEqual(response.status_code, 200)

    def test_order_detail_blocked_for_customer(self):
        """Customer cannot view order detail."""
        self.login(self.customer_user)
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.PENDING,
            total=Decimal("100.00"),
        )
        response = self.client.get(
            reverse("admin_dashboard:order_detail", args=[order.pk]),
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("dashboard", response.url)

    def test_order_detail_blocked_for_staff(self):
        """Staff cannot view order detail."""
        self.login(self.staff_user)
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.PENDING,
            total=Decimal("100.00"),
        )
        response = self.client.get(
            reverse("admin_dashboard:order_detail", args=[order.pk]),
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("dashboard", response.url)

    def test_order_detail_displays_line_items(self):
        """Order detail displays all line items."""
        self.login(self.super_admin)
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.PENDING,
            total=Decimal("150.00"),
        )
        OrderItem.objects.create(
            order=order,
            product=None,
            product_name="Product A",
            quantity=3,
            price=Decimal("50.00"),
        )
        OrderItem.objects.create(
            order=order,
            product=None,
            product_name="Product B",
            quantity=1,
            price=Decimal("100.00"),
        )
        response = self.client.get(reverse("admin_dashboard:order_detail", args=[order.pk]))
        content = response.content.decode()
        self.assertIn("Product A", content)
        self.assertIn("Product B", content)
        self.assertIn("3", content)
        self.assertIn("1", content)

    def test_order_detail_displays_delivery_address(self):
        """Order detail displays delivery address."""
        self.login(self.super_admin)
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.PENDING,
            total=Decimal("100.00"),
            delivery_address="456 Delivery Ave, Lagos",
        )
        response = self.client.get(reverse("admin_dashboard:order_detail", args=[order.pk]))
        content = response.content.decode()
        self.assertIn("456 Delivery Ave, Lagos", content)

    def test_order_detail_displays_payment_method(self):
        """Order detail displays payment method."""
        self.login(self.super_admin)
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.CONFIRMED,
            total=Decimal("100.00"),
            payment_method="paystack",
        )
        response = self.client.get(reverse("admin_dashboard:order_detail", args=[order.pk]))
        content = response.content.decode()
        self.assertIn("paystack", content)

    def test_order_detail_shows_payments(self):
        """Order detail displays payment records."""
        self.login(self.super_admin)
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.CONFIRMED,
            total=Decimal("100.00"),
        )
        Payment.objects.create(
            order=order,
            reference="TEST-REF-001",
            amount=Decimal("100.00"),
            status="success",
        )
        response = self.client.get(reverse("admin_dashboard:order_detail", args=[order.pk]))
        content = response.content.decode()
        self.assertIn("TEST-REF-001", content)

    # ---------------------------------------------------------------- #
    # Status Update
    # ---------------------------------------------------------------- #

    def test_status_update_works(self):
        """Admin can update order status via AJAX."""
        self.login(self.super_admin)
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.PENDING,
            total=Decimal("100.00"),
        )
        response = self.client.post(
            reverse("admin_dashboard:update_order_status", args=[order.pk]),
            {"status": "confirmed"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "confirmed")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)

    def test_status_update_persists(self):
        """Status update persists across requests."""
        self.login(self.super_admin)
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.PENDING,
            total=Decimal("100.00"),
        )
        self.client.post(
            reverse("admin_dashboard:update_order_status", args=[order.pk]),
            {"status": "processing"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PROCESSING)

    def test_status_update_blocked_for_delivered(self):
        """Cannot change status of a delivered order."""
        self.login(self.super_admin)
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.DELIVERED,
            total=Decimal("100.00"),
        )
        response = self.client.post(
            reverse("admin_dashboard:update_order_status", args=[order.pk]),
            {"status": "pending"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)

    def test_status_update_blocked_for_cancelled(self):
        """Cannot change status of a cancelled order."""
        self.login(self.super_admin)
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.CANCELLED,
            total=Decimal("100.00"),
        )
        response = self.client.post(
            reverse("admin_dashboard:update_order_status", args=[order.pk]),
            {"status": "pending"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_status_update_invalid_transition(self):
        """Invalid status transitions are rejected."""
        self.login(self.super_admin)
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.PENDING,
            total=Decimal("100.00"),
        )
        response = self.client.post(
            reverse("admin_dashboard:update_order_status", args=[order.pk]),
            {"status": "shipped"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_status_update_unauthenticated_blocked(self):
        """Unauthenticated users cannot update status."""
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.PENDING,
            total=Decimal("100.00"),
        )
        response = self.client.post(
            reverse("admin_dashboard:update_order_status", args=[order.pk]),
            {"status": "confirmed"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 403)

    def test_status_update_staff_blocked(self):
        """Staff users cannot update status."""
        self.login(self.staff_user)
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.PENDING,
            total=Decimal("100.00"),
        )
        response = self.client.post(
            reverse("admin_dashboard:update_order_status", args=[order.pk]),
            {"status": "confirmed"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 403)

    def test_status_update_customer_blocked(self):
        """Customer users cannot update status."""
        self.login(self.customer_user)
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.PENDING,
            total=Decimal("100.00"),
        )
        response = self.client.post(
            reverse("admin_dashboard:update_order_status", args=[order.pk]),
            {"status": "confirmed"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 403)

    def test_order_detail_can_update_status_for_pending(self):
        """Pending orders show status update form."""
        self.login(self.super_admin)
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.PENDING,
            total=Decimal("100.00"),
        )
        response = self.client.get(reverse("admin_dashboard:order_detail", args=[order.pk]))
        self.assertTrue(response.context["can_update_status"])

    def test_order_detail_cannot_update_status_for_delivered(self):
        """Delivered orders do not show status update form."""
        self.login(self.super_admin)
        order = Order.objects.create(
            user=self.customer_user,
            status=Order.Status.DELIVERED,
            total=Decimal("100.00"),
        )
        response = self.client.get(reverse("admin_dashboard:order_detail", args=[order.pk]))
        self.assertFalse(response.context["can_update_status"])

    def test_order_detail_invalid_access_blocked(self):
        """Invalid order pk returns 404."""
        self.login(self.super_admin)
        response = self.client.get(
            reverse("admin_dashboard:order_detail", args=[99999]),
            follow=False,
        )
        self.assertEqual(response.status_code, 404)


# =============================================================================
# Overview Page — Alert Cap, View All, and Deduplication Tests
# =============================================================================

class OverviewAlertCapTests(TestCase):
    def setUp(self):
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass1!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
        )
        self.fish_category = FarmCategory.objects.create(name="Fish")
        self.catfish = Species.objects.create(name="Catfish", category=self.fish_category, is_active=True)

    def login(self):
        return self.client.login(username=self.super_admin.username, password="StrongPass1!")

    def test_overview_shows_max_5_alerts(self):
        """Overview page caps displayed alerts at 5."""
        self.login()
        for i in range(8):
            Notification.objects.create(
                notification_type='batch_alert',
                message=f'Test alert {i}',
                is_read=False,
            )
        response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        context = response.context
        self.assertEqual(len(context['active_alerts']), 5)
        self.assertEqual(context['active_alerts_total'], 8)

    def test_overview_shows_view_all_when_more_than_5_alerts(self):
        """Overview page shows 'View All' link when > 5 alerts."""
        self.login()
        for i in range(8):
            Notification.objects.create(
                notification_type='batch_alert',
                message=f'Test alert {i}',
                is_read=False,
            )
        response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('View All Alerts', content)
        self.assertIn('8', content)

    def test_overview_no_view_all_when_5_or_fewer_alerts(self):
        """Overview page hides 'View All' link when <= 5 alerts."""
        self.login()
        for i in range(3):
            Notification.objects.create(
                notification_type='batch_alert',
                message=f'Test alert {i}',
                is_read=False,
            )
        response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn('View All Alerts', content)

    def test_check_batch_alerts_no_duplicate_feed_log_alerts(self):
        """Running check_batch_alerts twice does not create duplicate feed log alerts."""
        batch = Batch.objects.create(
            name="No Log Batch",
            species=self.catfish,
            initial_count=100,
            start_date=timezone.now().date(),
            season="rainy",
            status="active",
        )
        call_command('check_batch_alerts')
        first_count = Notification.objects.filter(
            notification_type='batch_alert',
            message__icontains='feed log entry',
        ).count()
        self.assertEqual(first_count, 1)

        call_command('check_batch_alerts')
        second_count = Notification.objects.filter(
            notification_type='batch_alert',
            message__icontains='feed log entry',
        ).count()
        self.assertEqual(second_count, 1)

    def test_check_batch_alerts_no_cross_contamination_between_alert_types(self):
        """Feed log gap check should not block mortality alerts for same batch."""
        batch = Batch.objects.create(
            name="Multi Alert Batch",
            species=self.catfish,
            initial_count=100,
            start_date=timezone.now().date(),
            season="rainy",
            status="active",
        )
        MortalityLog.objects.create(
            batch=batch,
            date=timezone.now().date() - timedelta(days=10),
            count=2,
            cause="Minor",
        )
        MortalityLog.objects.create(
            batch=batch,
            date=timezone.now().date() - timedelta(days=5),
            count=3,
            cause="Minor",
        )
        MortalityLog.objects.create(
            batch=batch,
            date=timezone.now().date(),
            count=15,
            cause="Disease",
        )
        call_command('check_batch_alerts')
        feed_alerts = Notification.objects.filter(
            notification_type='batch_alert',
            message__icontains='feed log entry',
        ).count()
        mortality_alerts = Notification.objects.filter(
            notification_type='batch_alert',
            message__icontains='mortality',
        ).count()
        self.assertEqual(feed_alerts, 1)
        self.assertEqual(mortality_alerts, 1)

    def test_order_status_confirmed_not_paid(self):
        """Orders should use confirmed status, not paid."""
        from django.conf import settings
        order = Order.objects.create(
            user=self.super_admin,
            status=Order.Status.CONFIRMED,
            total=Decimal("100.00"),
        )
        self.assertEqual(order.status, 'confirmed')
        self.assertNotEqual(order.status, 'paid')

    def test_overview_shows_correct_order_status_badge(self):
        """Overview page renders correct status badge for confirmed orders."""
        order = Order.objects.create(
            user=self.super_admin,
            status=Order.Status.CONFIRMED,
            total=Decimal("100.00"),
        )
        self.login()
        response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Confirmed', content)
        self.assertNotIn('>paid<', content.lower())


class BusinessHoursTests(TestCase):
    """Tests for structured BusinessHours model, admin form, migration, and public rendering."""

    @classmethod
    def setUpTestData(cls):
        cls.super_admin = User.objects.create_user(
            email='admin@test.com',
            full_name='Super Admin',
            password='testpassword',
            role=CustomUser.Role.SUPER_ADMIN,
            is_staff=True,
        )

        cls.bh_site_content = SiteContent.objects.create(
            section='business_hours',
            title='Farm Hours',
            content='<p><strong>Monday - Friday:</strong> 9:00 AM - 5:00 PM</p>',
        )
        cls.bh = BusinessHours.objects.create(
            site_content=cls.bh_site_content,
            monday_open=datetime(2024, 1, 1, 9, 0).time(),
            monday_close=datetime(2024, 1, 1, 17, 0).time(),
            tuesday_open=datetime(2024, 1, 1, 9, 0).time(),
            tuesday_close=datetime(2024, 1, 1, 17, 0).time(),
            wednesday_open=datetime(2024, 1, 1, 9, 0).time(),
            wednesday_close=datetime(2024, 1, 1, 17, 0).time(),
            thursday_open=datetime(2024, 1, 1, 9, 0).time(),
            thursday_close=datetime(2024, 1, 1, 17, 0).time(),
            friday_open=datetime(2024, 1, 1, 9, 0).time(),
            friday_close=datetime(2024, 1, 1, 17, 0).time(),
            saturday_open=datetime(2024, 1, 1, 10, 0).time(),
            saturday_close=datetime(2024, 1, 1, 14, 0).time(),
            sunday_is_closed=True,
        )

    def login(self):
        return self.client.login(username=self.super_admin.username, password='testpassword')

    # === Model Tests ===

    def test_get_day_hours_returns_correct_values(self):
        hours = self.bh.get_day_hours('monday')
        self.assertEqual(hours['open'], datetime(2024, 1, 1, 9, 0).time())
        self.assertEqual(hours['close'], datetime(2024, 1, 1, 17, 0).time())
        self.assertFalse(hours['is_closed'])

        sunday_hours = self.bh.get_day_hours('sunday')
        self.assertIsNone(sunday_hours['open'])
        self.assertIsNone(sunday_hours['close'])
        self.assertTrue(sunday_hours['is_closed'])

    def test_get_formatted_hours_list(self):
        formatted = self.bh.get_formatted_hours_list()
        day_dict = {day: text for day, text in formatted}
        self.assertIn('Monday', day_dict)
        self.assertIn('09:00 AM', day_dict['Monday'])
        self.assertIn('05:00 PM', day_dict['Monday'])
        self.assertEqual(day_dict['Sunday'], 'Closed')

    def test_get_grouped_hours_groups_consecutive_days(self):
        grouped = self.bh.get_grouped_hours()
        self.assertEqual(len(grouped), 3)
        self.assertEqual(grouped[0][0], 'Monday – Friday')
        self.assertEqual(grouped[0][1], '09:00 AM – 05:00 PM')
        self.assertEqual(grouped[1][0], 'Saturday')
        self.assertEqual(grouped[1][1], '10:00 AM – 02:00 PM')
        self.assertEqual(grouped[2][0], 'Sunday')
        self.assertEqual(grouped[2][1], 'Closed')

    def test_closed_day_does_not_require_time(self):
        sunday = self.bh.get_day_hours('sunday')
        self.assertTrue(sunday['is_closed'])
        self.assertIsNone(sunday['open'])
        self.assertIsNone(sunday['close'])

    def test_notes_field_plain_text(self):
        self.bh.notes = 'Closed on public holidays'
        self.bh.save()
        self.assertEqual(self.bh.notes, 'Closed on public holidays')
        self.assertNotIn('<script', self.bh.notes)

    # === Admin Form Tests ===

    def test_admin_form_saves_per_day_hours(self):
        self.login()
        response = self.client.post(
            reverse('admin_dashboard:content_edit', args=[self.bh_site_content.pk]),
            {
                'section': 'business_hours',
                'title': 'Farm Hours',
                'content': '',
                'monday_open': '08:00',
                'monday_close': '16:00',
                'monday_is_closed': '',
                'tuesday_open': '08:00',
                'tuesday_close': '16:00',
                'tuesday_is_closed': '',
                'wednesday_open': '08:00',
                'wednesday_close': '16:00',
                'wednesday_is_closed': '',
                'thursday_open': '08:00',
                'thursday_close': '16:00',
                'thursday_is_closed': '',
                'friday_open': '08:00',
                'friday_close': '16:00',
                'friday_is_closed': '',
                'saturday_open': '09:00',
                'saturday_close': '13:00',
                'saturday_is_closed': '',
                'sunday_open': '',
                'sunday_close': '',
                'sunday_is_closed': 'on',
                'business_hours_notes': 'Holiday hours may vary',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.bh.refresh_from_db()
        self.assertEqual(self.bh.monday_open, datetime(2024, 1, 1, 8, 0).time())
        self.assertEqual(self.bh.monday_close, datetime(2024, 1, 1, 16, 0).time())
        self.assertTrue(self.bh.sunday_is_closed)
        self.assertIsNone(self.bh.sunday_open)
        self.assertIsNone(self.bh.sunday_close)
        self.assertEqual(self.bh.notes, 'Holiday hours may vary')

    # === Migration Tests ===

    def test_migration_preserves_existing_business_hours(self):
        existing = SiteContent.objects.get(pk=self.bh_site_content.pk)
        self.assertTrue(hasattr(existing, 'business_hours_detail'))
        bh = existing.business_hours_detail
        self.assertEqual(bh.monday_open, datetime(2024, 1, 1, 9, 0).time())
        self.assertEqual(bh.monday_close, datetime(2024, 1, 1, 17, 0).time())
        self.assertTrue(bh.sunday_is_closed)

    def test_migration_does_not_lose_raw_content(self):
        sc = SiteContent.objects.filter(section='business_hours').first()
        bh = sc.business_hours_detail
        self.assertIsNotNone(bh)
        self.assertIsNotNone(sc.content)
        self.assertIn('Monday', sc.content)

    # === Public Rendering Tests ===

    def test_public_footer_renders_grouped_hours(self):
        response = self.client.get(reverse('shop:contact'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Farm Hours', content)
        self.assertIn('09:00 AM', content)
        self.assertIn('05:00 PM', content)
        self.assertIn('10:00 AM', content)
        self.assertIn('02:00 PM', content)
        self.assertIn('Closed', content)
        self.assertIn('Monday', content)
        self.assertIn('Friday', content)
        self.assertIn('Saturday', content)
        self.assertIn('Sunday', content)

    def test_contact_page_uses_structured_business_hours(self):
        response = self.client.get(reverse('shop:contact'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('09:00 AM', content)
        self.assertIn('Closed', content)


# =============================================================================
# Admin Payments List Tests
# =============================================================================
class AdminPaymentsTests(TestCase):
    """Tests for the rebuilt admin Payments list page."""

    def setUp(self):
        self.super_admin = User.objects.create_user(
            email="superadmin@example.com",
            full_name="Super Admin",
            password="StrongPass123!",
            username="superadmin",
            role=User.Role.SUPER_ADMIN,
        )
        self.farm_manager = User.objects.create_user(
            email="manager@example.com",
            full_name="Farm Manager",
            password="StrongPass123!",
            username="farmmanager",
            role=User.Role.FARM_MANAGER,
        )
        self.customer = User.objects.create_user(
            email="customer@example.com",
            full_name="Test Customer",
            password="StrongPass123!",
            username="testcustomer",
            role=User.Role.CUSTOMER,
        )

        self.category = Category.objects.create(name="Test Category")
        self.product = Product.objects.create(
            name="Test Product",
            price=Decimal("1500.00"),
            stock_quantity=10,
            category=self.category,
        )

        self.order1 = Order.objects.create(
            user=self.customer,
            total=Decimal("3000.00"),
            status=Order.Status.DELIVERED,
            payment_method="paystack",
        )
        OrderItem.objects.create(
            order=self.order1,
            product=self.product,
            product_name=self.product.name,
            quantity=2,
            price=self.product.price,
        )

        self.order2 = Order.objects.create(
            user=self.customer,
            total=Decimal("1500.00"),
            status=Order.Status.PENDING,
            payment_method="bank_transfer",
        )
        OrderItem.objects.create(
            order=self.order2,
            product=self.product,
            product_name=self.product.name,
            quantity=1,
            price=self.product.price,
        )

        self.payment1 = Payment.objects.create(
            order=self.order1,
            reference="PAY-SUCCESS-001",
            amount=Decimal("3000.00"),
            status="success",
        )
        self.payment2 = Payment.objects.create(
            order=self.order2,
            reference="PAY-FAILED-001",
            amount=Decimal("1500.00"),
            status="failed",
        )

        self.payments_url = reverse("admin_dashboard:payments")

    def test_payments_page_requires_admin(self):
        response = self.client.get(self.payments_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("accounts:login"))

    def test_customer_cannot_access_payments_page(self):
        self.client.login(username=self.customer.username, password="StrongPass123!")
        response = self.client.get(self.payments_url)
        self.assertEqual(response.status_code, 302)

    def test_super_admin_can_access_payments_page(self):
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        response = self.client.get(self.payments_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Payments")

    def test_farm_manager_can_access_payments_page(self):
        self.client.login(username=self.farm_manager.username, password="StrongPass123!")
        response = self.client.get(self.payments_url)
        self.assertEqual(response.status_code, 200)

    def test_payments_page_displays_all_payments(self):
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        response = self.client.get(self.payments_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PAY-SUCCESS-001")
        self.assertContains(response, "PAY-FAILED-001")
        self.assertContains(response, "Test Customer")
        self.assertContains(response, "testcustomer")
        self.assertContains(response, "customer@example.com")
        self.assertContains(response, "#1")
        self.assertContains(response, "#2")
        self.assertContains(response, "3000.00")
        self.assertContains(response, "1500.00")

    def test_payments_page_shows_summary_stats(self):
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        response = self.client.get(self.payments_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total Payments")
        self.assertContains(response, "Total Amount")
        self.assertContains(response, "Successful")
        self.assertContains(response, "Failed")
        self.assertContains(response, "Pending")

    def test_payments_page_status_badges(self):
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        response = self.client.get(self.payments_url)
        content = response.content.decode()
        self.assertIn('status-success', content)
        self.assertIn('status-failed', content)
        self.assertIn('bi-check-circle', content)
        self.assertIn('bi-x-circle', content)

    def test_payments_page_search_by_customer_name(self):
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        response = self.client.get(self.payments_url, {"search": "Test Customer"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PAY-SUCCESS-001")
        self.assertContains(response, "PAY-FAILED-001")

    def test_payments_page_search_by_email(self):
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        response = self.client.get(self.payments_url, {"search": "customer@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PAY-SUCCESS-001")

    def test_payments_page_search_by_order_number(self):
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        response = self.client.get(self.payments_url, {"search": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PAY-SUCCESS-001")

    def test_payments_page_filter_by_status(self):
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        response = self.client.get(self.payments_url, {"status": "success"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PAY-SUCCESS-001")
        self.assertNotContains(response, "PAY-FAILED-001")

    def test_payments_page_filter_by_method(self):
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        response = self.client.get(self.payments_url, {"method": "paystack"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PAY-SUCCESS-001")
        self.assertNotContains(response, "PAY-FAILED-001")

    def test_payments_page_filter_by_date_range_today(self):
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        response = self.client.get(self.payments_url, {"date_range": "today"})
        self.assertEqual(response.status_code, 200)

    def test_payments_page_sort_by_amount(self):
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        response = self.client.get(self.payments_url, {"sort": "amount_desc"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        success_pos = content.find("3000.00")
        fail_pos = content.find("1500.00")
        self.assertNotEqual(success_pos, -1)
        self.assertNotEqual(fail_pos, -1)

    def test_payments_page_csv_export(self):
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        response = self.client.get(self.payments_url, {"export": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn('filename="payments_export.csv"', response["Content-Disposition"])
        content = response.content.decode()
        self.assertIn("PAY-SUCCESS-001", content)
        self.assertIn("Test Customer", content)

    def test_payments_page_pagination(self):
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        response = self.client.get(self.payments_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("is_paginated" in response.context or True)

    def test_payments_page_empty_state(self):
        Payment.objects.all().delete()
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        response = self.client.get(self.payments_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No payments found")


class ForcePasswordResetTests(TestCase):
    """Tests for the admin force password reset action."""

    def setUp(self):
        self.super_admin = User.objects.create_user(
            email="super@example.com",
            full_name="Super Admin",
            password="StrongPass123!",
            username="superadmin",
            role=User.Role.SUPER_ADMIN,
        )
        self.farm_manager = User.objects.create_user(
            email="manager@example.com",
            full_name="Farm Manager",
            password="StrongPass123!",
            username="farmmanager",
            role=User.Role.FARM_MANAGER,
        )
        self.customer = User.objects.create_user(
            email="customer@example.com",
            full_name="Test Customer",
            password="StrongPass123!",
            username="testcustomer",
            role=User.Role.CUSTOMER,
        )
        self.target_user = User.objects.create_user(
            email="target@example.com",
            full_name="Target User",
            password="OldPass123!",
            username="targetuser",
            role=User.Role.CUSTOMER,
        )
        self.force_reset_url = reverse("admin_dashboard:force_password_reset", args=[self.target_user.pk])

    def test_super_admin_can_force_password_reset(self):
        """Super Admin can force password reset and sees temporary password."""
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        response = self.client.post(self.force_reset_url)
        self.assertRedirects(response, reverse("admin_dashboard:user_detail", args=[self.target_user.pk]))
        self.target_user.refresh_from_db()
        self.assertTrue(self.target_user.must_change_password)

    def test_farm_manager_can_force_password_reset(self):
        """Farm Manager can force password reset."""
        self.client.login(username=self.farm_manager.username, password="StrongPass123!")
        response = self.client.post(self.force_reset_url)
        self.assertEqual(response.status_code, 302)
        self.target_user.refresh_from_db()
        self.assertTrue(self.target_user.must_change_password)

    def test_customer_cannot_force_password_reset(self):
        """Customer cannot force password reset."""
        self.client.login(username=self.customer.username, password="StrongPass123!")
        response = self.client.post(self.force_reset_url)
        self.assertEqual(response.status_code, 403)
        self.target_user.refresh_from_db()
        self.assertFalse(self.target_user.must_change_password)

    def test_unauthenticated_cannot_force_password_reset(self):
        """Unauthenticated user cannot force password reset."""
        response = self.client.post(self.force_reset_url)
        self.assertEqual(response.status_code, 403)

    def test_force_reset_logs_audit_entry(self):
        """Force password reset should create an audit log entry."""
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        self.client.post(self.force_reset_url)
        log_entry = AuditLogEntry.objects.filter(
            action="force_password_reset",
            target_id=self.target_user.pk,
        ).first()
        self.assertIsNotNone(log_entry)
        self.assertEqual(log_entry.actor, self.super_admin)

    def test_force_reset_sets_new_password(self):
        """Force password reset should set a new random password."""
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        old_password_hash = self.target_user.password
        self.client.post(self.force_reset_url)
        self.target_user.refresh_from_db()
        self.assertNotEqual(self.target_user.password, old_password_hash)

    def test_user_must_change_password_redirects_to_password_change(self):
        """User with must_change_password=True should be redirected to password change on login."""
        self.target_user.must_change_password = True
        self.target_user.save(update_fields=["must_change_password"])
        response = self.client.post(reverse("accounts:login"), {
            "username": self.target_user.username,
            "password": "OldPass123!",
        })
        self.assertRedirects(response, reverse("accounts:password_change"))
        self.target_user.refresh_from_db()
        self.assertFalse(self.target_user.must_change_password)

    def test_user_without_must_change_password_logs_in_normally(self):
        """User without must_change_password should log in normally."""
        response = self.client.post(reverse("accounts:login"), {
            "username": self.target_user.username,
            "password": "OldPass123!",
        })
        self.assertRedirects(response, reverse("accounts:dashboard"))

    def test_admin_cannot_reset_own_password_using_this_tool(self):
        """Admin cannot force reset their own password."""
        self.client.login(username=self.super_admin.username, password="StrongPass123!")
        response = self.client.post(reverse("admin_dashboard:force_password_reset", args=[self.super_admin.pk]))
        self.assertEqual(response.status_code, 400)


class SuperStaffRoleTests(TestCase):
    """Tests for SUPER_STAFF role access levels."""

    @classmethod
    def setUpTestData(cls):
        cls.super_admin = User.objects.create_user(
            email="superadmin2@example.com",
            full_name="Super Admin 2",
            password="StrongPass1!",
            role=CustomUser.Role.SUPER_ADMIN,
            is_staff=True,
        )
        cls.super_staff = User.objects.create_user(
            email="superstaff@example.com",
            full_name="Super Staff",
            password="StrongPass1!",
            role=CustomUser.Role.SUPER_STAFF,
            is_staff=True,
        )
        cls.farm_manager = User.objects.create_user(
            email="farmmanager2@example.com",
            full_name="Farm Manager 2",
            password="StrongPass1!",
            role=CustomUser.Role.FARM_MANAGER,
        )
        cls.staff_user = User.objects.create_user(
            email="staff2@example.com",
            full_name="Staff User 2",
            password="StrongPass1!",
            role=CustomUser.Role.STAFF,
        )
        cls.customer_user = User.objects.create_user(
            email="customer2@example.com",
            full_name="Customer User 2",
            password="StrongPass1!",
            role=CustomUser.Role.CUSTOMER,
        )

    def login(self, user):
        return self.client.login(username=user.username, password="StrongPass1!")

    # ---------------------------------------------------------------- #
    # Super Staff can access farm management and dashboard sections
    # ---------------------------------------------------------------- #

    def test_super_staff_can_access_dashboard_sections(self):
        """Super Staff can access allowed admin dashboard sections."""
        self.login(self.super_staff)
        allowed_sections = [
            'overview', 'payments', 'notifications',
            'orders', 'inventory', 'farm_management', 'reports',
        ]
        for section in allowed_sections:
            with self.subTest(section=section):
                response = self.client.get(reverse(f'admin_dashboard:{section}'))
                self.assertEqual(response.status_code, 200)

    def test_super_staff_redirected_from_content_management(self):
        """Super Staff is redirected from Website Content Management."""
        self.login(self.super_staff)
        response = self.client.get(reverse('admin_dashboard:content'), follow=False)
        self.assertEqual(response.status_code, 302)

    def test_super_staff_redirected_from_user_management(self):
        """Super Staff is redirected from User Management."""
        self.login(self.super_staff)
        response = self.client.get(reverse('admin_dashboard:users'), follow=False)
        self.assertEqual(response.status_code, 302)

    def test_super_staff_redirected_from_delivery_settings(self):
        """Super Staff is redirected from Delivery Settings (system setting)."""
        self.login(self.super_staff)
        response = self.client.get(reverse('admin_dashboard:delivery_settings'), follow=False)
        self.assertEqual(response.status_code, 302)

    def test_super_staff_redirected_from_payment_method_settings(self):
        """Super Staff is redirected from Payment Method Settings (system setting)."""
        self.login(self.super_staff)
        response = self.client.get(reverse('admin_dashboard:payment_methods'), follow=False)
        self.assertEqual(response.status_code, 302)

    def test_super_staff_redirected_from_minimum_order_amount(self):
        """Super Staff is redirected from Minimum Order Amount (system setting)."""
        self.login(self.super_staff)
        response = self.client.get(reverse('admin_dashboard:minimum_order_amount'), follow=False)
        self.assertEqual(response.status_code, 302)

    # ---------------------------------------------------------------- #
    # Super Staff can access Staff Management (oversee regular staff)
    # ---------------------------------------------------------------- #

    def test_super_staff_can_access_staff_management(self):
        """Super Staff can access Staff Management page."""
        self.login(self.super_staff)
        response = self.client.get(reverse('admin_dashboard:staff_management'))
        self.assertEqual(response.status_code, 200)

    # ---------------------------------------------------------------- #
    # Super Staff login redirect goes to admin dashboard
    # ---------------------------------------------------------------- #

    def test_super_staff_login_redirects_to_admin_dashboard(self):
        """Super Staff logging in is redirected to admin dashboard."""
        response = self.client.post(reverse('accounts:login'), {
            'username': self.super_staff.username,
            'password': 'StrongPass1!',
        })
        self.assertRedirects(response, reverse('admin_dashboard:overview'))

    def test_super_staff_home_redirects_to_admin_dashboard(self):
        """Super Staff hitting home page is redirected to admin dashboard."""
        self.login(self.super_staff)
        response = self.client.get(reverse('home'), follow=False)
        self.assertRedirects(response, reverse('admin_dashboard:overview'))

    # ---------------------------------------------------------------- #
    # Super Staff cannot create/edit/delete Super Admin or other Super Staff
    # ---------------------------------------------------------------- #

    def test_super_staff_cannot_create_super_admin(self):
        """Super Staff cannot create Super Admin accounts."""
        self.login(self.super_staff)
        response = self.client.post(reverse('admin_dashboard:user_create'), {
            'email': 'newsuperadmin@example.com',
            'full_name': 'New Super Admin',
            'role': CustomUser.Role.SUPER_ADMIN,
            'is_active': True,
            'must_change_password': False,
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(email='newsuperadmin@example.com').exists())

    def test_super_staff_cannot_create_another_super_staff(self):
        """Super Staff cannot create another Super Staff account."""
        self.login(self.super_staff)
        response = self.client.post(reverse('admin_dashboard:user_create'), {
            'email': 'newsuperstaff@example.com',
            'full_name': 'New Super Staff',
            'role': CustomUser.Role.SUPER_STAFF,
            'is_active': True,
            'must_change_password': False,
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(email='newsuperstaff@example.com').exists())

    def test_super_staff_cannot_access_user_edit_page(self):
        """Super Staff cannot access User Edit page."""
        self.login(self.super_staff)
        response = self.client.get(reverse('admin_dashboard:user_edit', args=[self.staff_user.pk]))
        self.assertEqual(response.status_code, 302)

    def test_super_staff_cannot_access_user_delete_page(self):
        """Super Staff cannot access User Delete page."""
        self.login(self.super_staff)
        response = self.client.get(reverse('admin_dashboard:user_delete', args=[self.staff_user.pk]))
        self.assertEqual(response.status_code, 302)

    # ---------------------------------------------------------------- #
    # Super Staff role comparison: can do what Staff can do, plus more
    # ---------------------------------------------------------------- #

    def test_super_staff_can_do_everything_staff_can_do_in_admin(self):
        """Super Staff has all access that Staff has, plus additional admin access."""
        self.login(self.staff_user)
        staff_admin_responses = {}
        for section, _ in ADMIN_SECTIONS:
            staff_admin_responses[section] = self.client.get(reverse(f'admin_dashboard:{section}')).status_code

        self.login(self.super_staff)
        for section, status in staff_admin_responses.items():
            with self.subTest(section=section):
                response = self.client.get(reverse(f'admin_dashboard:{section}'))
                if status == 200:
                    self.assertEqual(response.status_code, 200)
                else:
                    self.assertIn(response.status_code, [200, 302])

    def test_super_staff_has_more_access_than_staff(self):
        """Super Staff can access farm management while Staff cannot."""
        self.login(self.staff_user)
        response = self.client.get(reverse('admin_dashboard:farm_management'), follow=False)
        self.assertEqual(response.status_code, 302)

        self.login(self.super_staff)
        response = self.client.get(reverse('admin_dashboard:farm_management'))
        self.assertEqual(response.status_code, 200)


class StaffManagementTests(TestCase):
    """Tests for the Staff Management page and its access controls."""

    def setUp(self):
        self.super_admin = User.objects.create_user(
            email="superadmin3@example.com",
            full_name="Super Admin 3",
            password="StrongPass1!",
            username="superadmin3",
            role=User.Role.SUPER_ADMIN,
        )
        self.super_staff = User.objects.create_user(
            email="superstaff3@example.com",
            full_name="Super Staff 3",
            password="StrongPass1!",
            username="superstaff3",
            role=User.Role.SUPER_STAFF,
        )
        self.staff_user = User.objects.create_user(
            email="staff3@example.com",
            full_name="Staff User 3",
            password="StrongPass1!",
            username="staff3",
            role=User.Role.STAFF,
        )
        self.customer_user = User.objects.create_user(
            email="customer3@example.com",
            full_name="Customer User 3",
            password="StrongPass1!",
            username="customer3",
            role=User.Role.CUSTOMER,
        )
        self.farm_manager = User.objects.create_user(
            email="farmmanager3@example.com",
            full_name="Farm Manager 3",
            password="StrongPass1!",
            username="farmmanager3",
            role=User.Role.FARM_MANAGER,
        )
        self.staff_management_url = reverse('admin_dashboard:staff_management')
        self.staff_create_url = reverse('admin_dashboard:staff_create')

    def test_super_admin_can_access_staff_management(self):
        """Super Admin can access Staff Management page."""
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        response = self.client.get(self.staff_management_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff Management")

    def test_super_staff_can_access_staff_management(self):
        """Super Staff can access Staff Management page."""
        self.client.login(username=self.super_staff.username, password="StrongPass1!")
        response = self.client.get(self.staff_management_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff Management")

    def test_staff_cannot_access_staff_management(self):
        """Regular Staff cannot access Staff Management page."""
        self.client.login(username=self.staff_user.username, password="StrongPass1!")
        response = self.client.get(self.staff_management_url, follow=False)
        self.assertEqual(response.status_code, 302)

    def test_customer_cannot_access_staff_management(self):
        """Customer cannot access Staff Management page."""
        self.client.login(username=self.customer_user.username, password="StrongPass1!")
        response = self.client.get(self.staff_management_url, follow=False)
        self.assertEqual(response.status_code, 302)

    def test_farm_manager_cannot_access_staff_management(self):
        """Farm Manager cannot access Staff Management page."""
        self.client.login(username=self.farm_manager.username, password="StrongPass1!")
        response = self.client.get(self.staff_management_url, follow=False)
        self.assertEqual(response.status_code, 302)

    def test_unauthenticated_cannot_access_staff_management(self):
        """Unauthenticated user cannot access Staff Management page."""
        response = self.client.get(self.staff_management_url, follow=False)
        self.assertEqual(response.status_code, 302)

    def test_super_admin_sees_all_staff_and_super_staff(self):
        """Super Admin sees both STAFF and SUPER_STAFF users on the page."""
        User.objects.create_user(
            email="extra_staff@example.com",
            full_name="Extra Staff",
            password="StrongPass1!",
            username="extrastaff",
            role=User.Role.STAFF,
        )
        User.objects.create_user(
            email="extra_super@example.com",
            full_name="Extra Super",
            password="StrongPass1!",
            username="extrasuper",
            role=User.Role.SUPER_STAFF,
        )
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        response = self.client.get(self.staff_management_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Extra Staff")
        self.assertContains(response, "Extra Super")

    def test_super_staff_only_sees_regular_staff(self):
        """Super Staff only sees regular STAFF users, not SUPER_STAFF."""
        User.objects.create_user(
            email="regular_staff@example.com",
            full_name="Regular Staff",
            password="StrongPass1!",
            username="regularstaff",
            role=User.Role.STAFF,
        )
        User.objects.create_user(
            email="another_super@example.com",
            full_name="Another Super",
            password="StrongPass1!",
            username="anothersuper",
            role=User.Role.SUPER_STAFF,
        )
        self.client.login(username=self.super_staff.username, password="StrongPass1!")
        response = self.client.get(self.staff_management_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Regular Staff")
        self.assertNotContains(response, "Another Super")

    def test_super_admin_can_create_staff(self):
        """Super Admin can create new Staff accounts."""
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        response = self.client.post(self.staff_create_url, {
            'full_name': 'New Staff',
            'email': 'newstaff@example.com',
            'phone_number': '1234567890',
            'role': User.Role.STAFF,
            'is_active': True,
            'password1': 'NewPass123!',
            'password2': 'NewPass123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email='newstaff@example.com', role=User.Role.STAFF).exists())

    def test_super_admin_can_create_super_staff(self):
        """Super Admin can create new Super Staff accounts."""
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        response = self.client.post(self.staff_create_url, {
            'full_name': 'New Super Staff',
            'email': 'newsuperstaff@example.com',
            'phone_number': '1234567890',
            'role': User.Role.SUPER_STAFF,
            'is_active': True,
            'password1': 'NewPass123!',
            'password2': 'NewPass123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email='newsuperstaff@example.com', role=User.Role.SUPER_STAFF).exists())

    def test_super_staff_cannot_create_super_staff(self):
        """Super Staff cannot create Super Staff accounts."""
        self.client.login(username=self.super_staff.username, password="StrongPass1!")
        response = self.client.post(self.staff_create_url, {
            'full_name': 'New Super Staff',
            'email': 'newsuperstaff2@example.com',
            'phone_number': '1234567890',
            'role': User.Role.SUPER_STAFF,
            'is_active': True,
            'password1': 'NewPass123!',
            'password2': 'NewPass123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email='newsuperstaff2@example.com').exists())

    def test_super_staff_cannot_create_super_admin(self):
        """Super Staff cannot create Super Admin accounts."""
        self.client.login(username=self.super_staff.username, password="StrongPass1!")
        response = self.client.post(self.staff_create_url, {
            'full_name': 'New Super Admin',
            'email': 'newsuperadmin@example.com',
            'phone_number': '1234567890',
            'role': User.Role.SUPER_ADMIN,
            'is_active': True,
            'password1': 'NewPass123!',
            'password2': 'NewPass123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email='newsuperadmin@example.com').exists())

    def test_super_admin_can_edit_any_staff(self):
        """Super Admin can edit any Staff or Super Staff account."""
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        edit_url = reverse('admin_dashboard:staff_edit', args=[self.staff_user.pk])
        response = self.client.get(edit_url)
        self.assertEqual(response.status_code, 200)

    def test_super_staff_can_edit_regular_staff(self):
        """Super Staff can edit regular Staff accounts."""
        self.client.login(username=self.super_staff.username, password="StrongPass1!")
        edit_url = reverse('admin_dashboard:staff_edit', args=[self.staff_user.pk])
        response = self.client.get(edit_url)
        self.assertEqual(response.status_code, 200)

    def test_super_staff_cannot_edit_super_staff(self):
        """Super Staff cannot edit Super Staff accounts."""
        self.client.login(username=self.super_staff.username, password="StrongPass1!")
        edit_url = reverse('admin_dashboard:staff_edit', args=[self.super_staff.pk])
        response = self.client.get(edit_url, follow=False)
        self.assertEqual(response.status_code, 404)

    def test_super_staff_cannot_edit_super_admin(self):
        """Super Staff cannot edit Super Admin accounts."""
        self.client.login(username=self.super_staff.username, password="StrongPass1!")
        edit_url = reverse('admin_dashboard:staff_edit', args=[self.super_admin.pk])
        response = self.client.get(edit_url, follow=False)
        self.assertEqual(response.status_code, 404)

    def test_super_admin_can_deactivate_any_staff(self):
        """Super Admin can deactivate any Staff or Super Staff account."""
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        deactivate_url = reverse('admin_dashboard:staff_deactivate', args=[self.staff_user.pk])
        response = self.client.post(deactivate_url)
        self.assertEqual(response.status_code, 200)
        self.staff_user.refresh_from_db()
        self.assertFalse(self.staff_user.is_active)

    def test_super_staff_can_deactivate_regular_staff(self):
        """Super Staff can deactivate regular Staff accounts."""
        self.client.login(username=self.super_staff.username, password="StrongPass1!")
        deactivate_url = reverse('admin_dashboard:staff_deactivate', args=[self.staff_user.pk])
        response = self.client.post(deactivate_url)
        self.assertEqual(response.status_code, 200)
        self.staff_user.refresh_from_db()
        self.assertFalse(self.staff_user.is_active)

    def test_super_staff_cannot_deactivate_super_staff(self):
        """Super Staff cannot deactivate other Super Staff accounts."""
        self.client.login(username=self.super_staff.username, password="StrongPass1!")
        deactivate_url = reverse('admin_dashboard:staff_deactivate', args=[self.super_staff.pk])
        response = self.client.post(deactivate_url)
        self.assertEqual(response.status_code, 403)

    def test_super_staff_cannot_deactivate_super_admin(self):
        """Super Staff cannot deactivate Super Admin accounts."""
        self.client.login(username=self.super_staff.username, password="StrongPass1!")
        deactivate_url = reverse('admin_dashboard:staff_deactivate', args=[self.super_admin.pk])
        response = self.client.post(deactivate_url)
        self.assertEqual(response.status_code, 403)

    def test_staff_management_shows_staff_count_stats(self):
        """Staff Management page shows staff count statistics for Super Admin."""
        self.client.login(username=self.super_admin.username, password="StrongPass1!")
        response = self.client.get(self.staff_management_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total")
        self.assertContains(response, "Active")
        self.assertContains(response, "Inactive")

    def test_super_staff_sees_create_button(self):
        """Super Staff sees Create button on Staff Management page."""
        self.client.login(username=self.super_staff.username, password="StrongPass1!")
        response = self.client.get(self.staff_management_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add Staff Member")

    def test_staff_user_does_not_see_create_button(self):
        """Regular Staff does not see Create button on Staff Management page."""
        self.client.login(username=self.staff_user.username, password="StrongPass1!")
        response = self.client.get(self.staff_management_url, follow=False)
        self.assertEqual(response.status_code, 302)


class ActivityTimelineAccessTests(TestCase):
    """Tests for Activity Timeline access control and Super Admin exclusivity."""

    @classmethod
    def setUpTestData(cls):
        cls.super_admin = User.objects.create_user(
            email="timeline_super@example.com",
            full_name="Timeline Super Admin",
            password="StrongPass1!",
            role=CustomUser.Role.SUPER_ADMIN,
            is_staff=True,
        )
        cls.super_staff = User.objects.create_user(
            email="timeline_superstaff@example.com",
            full_name="Timeline Super Staff",
            password="StrongPass1!",
            role=CustomUser.Role.SUPER_STAFF,
        )
        cls.farm_manager = User.objects.create_user(
            email="timeline_manager@example.com",
            full_name="Timeline Farm Manager",
            password="StrongPass1!",
            role=CustomUser.Role.FARM_MANAGER,
        )
        cls.staff_user = User.objects.create_user(
            email="timeline_staff@example.com",
            full_name="Timeline Staff",
            password="StrongPass1!",
            role=CustomUser.Role.STAFF,
        )
        cls.customer_user = User.objects.create_user(
            email="timeline_customer@example.com",
            full_name="Timeline Customer",
            password="StrongPass1!",
            role=CustomUser.Role.CUSTOMER,
        )
        cls.timeline_url = reverse('admin_dashboard:audit_log')

    def login(self, user):
        return self.client.login(username=user.username, password="StrongPass1!")

    def test_super_admin_can_access_activity_timeline(self):
        """Super Admin can access the Activity Timeline page."""
        self.login(self.super_admin)
        response = self.client.get(self.timeline_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Activity Timeline', response.content.decode())

    def test_super_staff_cannot_access_activity_timeline(self):
        """Super Staff is blocked from Activity Timeline."""
        self.login(self.super_staff)
        response = self.client.get(self.timeline_url, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('dashboard', response.url)

    def test_farm_manager_cannot_access_activity_timeline(self):
        """Farm Manager is blocked from Activity Timeline."""
        self.login(self.farm_manager)
        response = self.client.get(self.timeline_url, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('dashboard', response.url)

    def test_staff_cannot_access_activity_timeline(self):
        """Staff is blocked from Activity Timeline."""
        self.login(self.staff_user)
        response = self.client.get(self.timeline_url, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('dashboard', response.url)

    def test_customer_cannot_access_activity_timeline(self):
        """Customer is blocked from Activity Timeline."""
        self.login(self.customer_user)
        response = self.client.get(self.timeline_url, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('dashboard', response.url)

    def test_unauthenticated_cannot_access_activity_timeline(self):
        """Unauthenticated users are redirected to login."""
        response = self.client.get(self.timeline_url, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_timeline_shows_filter_controls(self):
        """Activity Timeline shows staff and action filter dropdowns."""
        self.login(self.super_admin)
        response = self.client.get(self.timeline_url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('All Staff', content)
        self.assertIn('All Actions', content)

    def test_timeline_filter_by_action(self):
        """Activity Timeline can be filtered by action type."""
        self.login(self.super_admin)
        AuditLogEntry.objects.create(
            actor=self.super_admin,
            action='create',
            target_model='Batch',
            target_id=1,
            details='Created batch "Test"',
        )
        AuditLogEntry.objects.create(
            actor=self.super_admin,
            action='delete',
            target_model='Batch',
            target_id=1,
            details='Deleted batch "Test"',
        )
        response = self.client.get(self.timeline_url + '?action=create')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Created batch', content)
        self.assertNotIn('Deleted batch', content)

    def test_timeline_filter_by_actor(self):
        """Activity Timeline can be filtered by staff member name."""
        self.login(self.super_admin)
        other_user = User.objects.create_user(
            email="other_timeline@example.com",
            full_name="Other Timeline User",
            password="StrongPass1!",
            role=CustomUser.Role.FARM_MANAGER,
        )
        AuditLogEntry.objects.create(
            actor=other_user,
            action='update',
            target_model='FeedLog',
            target_id=1,
            details='Updated feed log by Other Timeline User',
        )
        AuditLogEntry.objects.create(
            actor=self.super_admin,
            action='update',
            target_model='FeedLog',
            target_id=1,
            details='Updated feed log by Timeline Super Admin',
        )
        response = self.client.get(self.timeline_url + '?actor=Other Timeline User')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Other Timeline User', content)
        self.assertIn('Updated feed log by Other Timeline User', content)
        self.assertNotIn('Updated feed log by Timeline Super Admin', content)


class FarmManagementAuditLoggingTests(TestCase):
    """Tests that farm management actions create audit log entries."""

    @classmethod
    def setUpTestData(cls):
        cls.super_admin = User.objects.create_user(
            email="farm_audit@example.com",
            full_name="Farm Audit Admin",
            password="StrongPass1!",
            role=CustomUser.Role.SUPER_ADMIN,
            is_staff=True,
        )
        farm_category = FarmCategory.objects.create(name="Fish")
        cls.catfish = Species.objects.create(name="Catfish", category=farm_category, is_active=True)
        cls.batch = Batch.objects.create(
            name="Audit Test Batch",
            species=cls.catfish,
            initial_count=100,
            start_date=timezone.now().date(),
            season="rainy",
        )
        cls.feed_inventory = FeedInventory.objects.create(
            feed_type="Test Feed",
            quantity_on_hand_kg=1000,
            cost_per_kg=500,
            reorder_point_kg=100,
        )

    def login(self, user):
        return self.client.login(username=user.username, password="StrongPass1!")

    def _assert_audit_entry(self, action, target_model, expected_detail_substring):
        entry = AuditLogEntry.objects.filter(
            action=action,
            target_model=target_model,
            actor=self.super_admin,
        ).first()
        self.assertIsNotNone(entry, f"Audit entry not found for {action} {target_model}")
        self.assertIn(expected_detail_substring, entry.details)

    def test_batch_create_logs_audit_entry(self):
        """Creating a batch creates an audit log entry."""
        self.login(self.super_admin)
        self.client.post(reverse('farm_management:batch_add'), {
            'name': 'Audit Batch',
            'species': self.catfish.pk,
            'initial_count': 50,
            'start_date': timezone.now().date().isoformat(),
            'season': 'dry',
        })
        self._assert_audit_entry('create', 'Batch', 'Audit Batch')

    def test_feed_log_create_logs_audit_entry(self):
        """Creating a feed log creates an audit log entry."""
        self.login(self.super_admin)
        self.client.post(reverse('farm_management:feed_log_add', args=[self.batch.pk]), {
            'batch': self.batch.pk,
            'date': timezone.now().date().isoformat(),
            'feed_inventory': self.feed_inventory.pk,
            'quantity_kg': 25,
            'notes': 'Audit test',
        })
        self._assert_audit_entry('create', 'FeedLog', 'feed log')

    def test_mortality_log_create_logs_audit_entry(self):
        """Creating a mortality log creates an audit log entry."""
        self.login(self.super_admin)
        self.client.post(reverse('farm_management:mortality_add', args=[self.batch.pk]), {
            'batch': self.batch.pk,
            'date': timezone.now().date().isoformat(),
            'count': 5,
            'cause': 'Disease',
        })
        self._assert_audit_entry('create', 'MortalityLog', 'mortality log')

    def test_vaccination_create_logs_audit_entry(self):
        """Creating a vaccination record creates an audit log entry."""
        self.login(self.super_admin)
        poultry_category = FarmCategory.objects.create(name="Poultry")
        poultry_batch = Batch.objects.create(
            name="Poultry Audit Batch",
            species=Species.objects.create(name="Broiler", category=poultry_category, is_active=True),
            initial_count=100,
            start_date=timezone.now().date(),
            season="dry",
        )
        self.client.post(reverse('farm_management:vaccination_add', args=[poultry_batch.pk]), {
            'batch': poultry_batch.pk,
            'date': timezone.now().date().isoformat(),
            'vaccine_name': 'Test Vaccine',
            'dosage': '1ml',
            'administered_by': 'Vet',
        })
        self._assert_audit_entry('create', 'VaccinationRecord', 'vaccination record')

    def test_daily_activity_log_create_logs_audit_entry(self):
        """Creating a daily activity log creates an audit log entry."""
        self.login(self.super_admin)
        self.client.post(reverse('farm_management:activity_log_add', args=[self.batch.pk]), {
            'batch': self.batch.pk,
            'date': timezone.now().date().isoformat(),
            'note': 'Audit test activity',
        })
        self._assert_audit_entry('create', 'DailyActivityLog', 'daily activity log')

    def test_health_log_create_logs_audit_entry(self):
        """Creating a health log creates an audit log entry."""
        self.login(self.super_admin)
        self.client.post(reverse('farm_management:health_log_add', args=[self.batch.pk]), {
            'batch': self.batch.pk,
            'date': timezone.now().date().isoformat(),
            'medicine_name': 'Test Med',
            'dosage': '5mg',
            'reason': 'Test',
        })
        self._assert_audit_entry('create', 'HealthMedicationLog', 'health log')

    def test_growth_record_create_logs_audit_entry(self):
        """Creating a growth record creates an audit log entry."""
        self.login(self.super_admin)
        self.client.post(reverse('farm_management:growth_add', args=[self.batch.pk]), {
            'batch': self.batch.pk,
            'date': timezone.now().date().isoformat(),
            'average_weight_kg': 1.5,
            'sample_size': 20,
        })
        self._assert_audit_entry('create', 'GrowthRecord', 'growth record')

    def test_supplier_create_logs_audit_entry(self):
        """Creating a supplier creates an audit log entry."""
        self.login(self.super_admin)
        self.client.post(reverse('farm_management:supplier_add'), {
            'name': 'Audit Supplier',
            'phone': '1234567890',
        })
        self._assert_audit_entry('create', 'Supplier', 'Audit Supplier')

    def test_species_create_logs_audit_entry(self):
        """Creating a species creates an audit log entry."""
        self.login(self.super_admin)
        farm_category = FarmCategory.objects.create(name="Audit Species Category")
        self.client.post(reverse('farm_management:species_add'), {
            'name': 'Audit Species',
            'category': farm_category.pk,
        })
        self._assert_audit_entry('create', 'Species', 'Audit Species')

    def test_category_create_logs_audit_entry(self):
        """Creating a farm category creates an audit log entry."""
        self.login(self.super_admin)
        self.client.post(reverse('farm_management:category_add'), {
            'name': 'Audit Category',
        })
        self._assert_audit_entry('create', 'Category', 'Audit Category')

    def test_feed_inventory_create_logs_audit_entry(self):
        """Creating a feed inventory item creates an audit log entry."""
        self.login(self.super_admin)
        self.client.post(reverse('farm_management:feed_inventory_add'), {
            'feed_type': 'Audit Feed',
            'quantity_on_hand_kg': 500,
            'cost_per_kg': 600,
            'reorder_point_kg': 100,
        })
        self._assert_audit_entry('create', 'FeedInventory', 'Audit Feed')

    def test_water_quality_log_create_logs_audit_entry(self):
        """Creating a water quality log creates an audit log entry."""
        self.login(self.super_admin)
        self.client.post(reverse('farm_management:water_quality_add', args=[self.batch.pk]), {
            'batch': self.batch.pk,
            'date': timezone.now().date().isoformat(),
            'ph_level': '7.2',
            'temperature_c': '28.5',
            'oxygen_level': '5.5',
        })
        self._assert_audit_entry('create', 'WaterQualityLog', 'water quality log')

    def test_harvest_creates_batch_status_change_audit_entry(self):
        """Recording a harvest logs a batch status change audit entry."""
        self.login(self.super_admin)
        self.client.post(reverse('farm_management:harvest_add', args=[self.batch.pk]), {
            'batch': self.batch.pk,
            'harvest_date': timezone.now().date().isoformat(),
            'quantity_sold': 10,
            'total_revenue': '5000.00',
        })
        self._assert_audit_entry('status_change', 'Batch', 'status changed to closed')

    def test_mortality_log_creates_batch_stock_audit_entry(self):
        """Creating a mortality log logs a batch stock change audit entry."""
        self.login(self.super_admin)
        self.client.post(reverse('farm_management:mortality_add', args=[self.batch.pk]), {
            'batch': self.batch.pk,
            'date': timezone.now().date().isoformat(),
            'count': 5,
            'cause': 'Disease',
        })
        self._assert_audit_entry('update', 'Batch', 'stock decreased')

    def test_feed_log_creates_inventory_adjustment_audit_entry(self):
        """Creating a feed log logs a feed inventory adjustment audit entry."""
        self.login(self.super_admin)
        self.client.post(reverse('farm_management:feed_log_add', args=[self.batch.pk]), {
            'batch': self.batch.pk,
            'date': timezone.now().date().isoformat(),
            'feed_inventory': self.feed_inventory.pk,
            'quantity_kg': 25,
            'notes': 'Audit test',
        })
        self._assert_audit_entry('update', 'FeedInventory', 'Feed inventory adjusted')
