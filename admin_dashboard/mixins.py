from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from django.contrib.auth import get_user_model

User = get_user_model()


class AdminRequiredMixin(UserPassesTestMixin):
    """
    Mixin that restricts access to Super Admin and Farm Manager roles only.
    Redirects unauthorized users to the login page with an error message.
    """

    login_url = reverse_lazy('accounts:login')
    permission_denied_message = _(
        "You do not have permission to access the admin dashboard. "
        "Only Super Admins and Farm Managers can access this area."
    )

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        return self.request.user.role in (
            User.Role.SUPER_ADMIN,
            User.Role.FARM_MANAGER,
        )

    def handle_no_permission(self):
        from django.contrib import messages
        messages.error(self.request, self.permission_denied_message)
        if self.request.user.is_authenticated:
            return redirect('accounts:dashboard')
        return redirect('accounts:login')
