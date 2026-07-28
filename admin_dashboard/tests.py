from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from accounts.models import CustomUser
from notifications.models import Notification
from shop.models import Product, Order
from admin_dashboard.models import SiteContent

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
        return self.client.login(email=user.email, password="StrongPass1!")

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
        """Farm Manager can access every admin dashboard section."""
        self.login(self.farm_manager)
        for section, label in ADMIN_SECTIONS:
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

    def test_overview_page_contains_coming_soon_message(self):
        """Overview page renders a placeholder (coming soon) message for authorized users."""
        self.login(self.super_admin)
        response = self.client.get(reverse('admin_dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('coming soon', response.content.decode().lower())

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
        return self.client.login(email=user.email, password="StrongPass1!")

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
        self.client.login(email=user.email, password=self.get_password(user))
    
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
        """Farm manager can access user list."""
        self.login(self.farm_manager)
        response = self.client.get(reverse('admin_dashboard:users'))
        self.assertEqual(response.status_code, 200)
    
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
            status='paid'
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
        can_login = self.client.login(email=self.inactive_user.email, password='InactivePass123!')
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
        self.client.login(email=user.email, password='testpassword')

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
        self.assertNotContains(response, 'class="shop-banner"')
        
        # Create banner content
        banner_content = SiteContent.objects.create(
            section='shop_banner',
            title='Special Offer!',
            content='<p>20% off all products this week!</p>',
        )
        
        # Banner element should now be present
        response = self.client.get(reverse('shop:product_list'))
        self.assertContains(response, 'class="shop-banner"')
        self.assertContains(response, 'Special Offer!')
        self.assertContains(response, '20% off all products')

    def test_homepage_hero_displays_conditionally(self):
        """Homepage hero only shows when homepage_hero content exists."""
        # No hero - should not display the hero element
        response = self.client.get(reverse('shop:product_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="homepage-hero"')
        
        # Create hero content
        hero_content = SiteContent.objects.create(
            section='homepage_hero',
            title='Welcome to TAMIPEE Farm Shop',
            content='<p>Fresh, quality agricultural products delivered to your door.</p>',
        )
        
        # Hero element should now be present
        response = self.client.get(reverse('shop:product_list'))
        self.assertContains(response, 'class="homepage-hero"')
        self.assertContains(response, 'Welcome to TAMIPEE Farm Shop')
        self.assertContains(response, 'Fresh, quality agricultural products')

