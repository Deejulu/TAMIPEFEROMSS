

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
