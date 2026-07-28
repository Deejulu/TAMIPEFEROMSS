import re
from io import StringIO

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse

from django.urls import reverse_lazy, reverse
from django.http import HttpResponseRedirect
from django.views.generic import CreateView, TemplateView, RedirectView, UpdateView, FormView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.core.signing import SignatureExpired, BadSignature
from django.contrib.auth.views import PasswordChangeView, LoginView
from django.core.management import call_command

from .forms import CustomSignupForm, ProfileEditForm, ChangeSecurityQuestionsForm, SecurityQuestionRecoveryForm, RecoveryPasswordResetForm
from .tokens import verify_token, build_verification_url
from .models import SavedCard, Transaction

User = get_user_model()


class CustomLoginView(LoginView):
    """
    Custom login view that redirects users based on their role:
    - Super Admin / Farm Manager -> admin_dashboard:overview
    - Staff / Customer -> accounts:dashboard
    """

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.request.user
        if user.role in (User.Role.SUPER_ADMIN, User.Role.FARM_MANAGER):
            try:
                call_command(
                    'check_batch_alerts',
                    stdout=StringIO(),
                    stderr=StringIO(),
                )
            except Exception:
                pass
        return response

    def get_success_url(self):
        user = self.request.user
        if user.role in (User.Role.SUPER_ADMIN, User.Role.FARM_MANAGER):
            return reverse_lazy("admin_dashboard:overview")
        return reverse_lazy("accounts:dashboard")


class HomeRedirectView(RedirectView):
    """
    Root URL redirect view.

    Redirects authenticated users based on role:
    - Super Admin / Farm Manager -> admin_dashboard:overview
    - Staff / Customer -> accounts:dashboard
    Unauthenticated users -> accounts:login
    """

    def get_redirect_url(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            user = self.request.user
            if user.role in (User.Role.SUPER_ADMIN, User.Role.FARM_MANAGER):
                return reverse_lazy("admin_dashboard:overview")
            return reverse_lazy("accounts:dashboard")
        return reverse_lazy("accounts:login")


class SignUpView(CreateView):
    """
    User registration view.

    Uses the CustomUserCreationForm to handle new user signups.
    All new users are automatically assigned the CUSTOMER role.
    On successful registration, a verification email is sent and
    the user is redirected to the login page with a success message.
    """
    form_class = CustomSignupForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy("accounts:login")

    def form_valid(self, form):
        """
        Called when the form is submitted with valid data.
        Sends verification email and adds a success message.
        """
        response = super().form_valid(form)

        # Send verification email
        user = self.object
        verification_url = build_verification_url(self.request, user)
        try:
            user.email_user(
                subject=_("Verify your email address"),
                message=_(
                    f"Hi {user.full_name},\n\n"
                    f"Please verify your email address by clicking the link below:\n"
                    f"{verification_url}\n\n"
                    f"This link will expire in 24 hours.\n\n"
                     f"Thank you,\nTeam"
                ),
                fail_silently=False,
            )
        except Exception:
            pass  # Email sending failure should not block registration

        messages.success(
            self.request,
            _("Account created successfully! "
              "Please check your email to verify your account."),
        )
        return response


class DashboardView(LoginRequiredMixin, TemplateView):
    """
    User dashboard view.

    Requires the user to be authenticated (LoginRequiredMixin).
    Displays user profile information and provides navigation to
    profile management pages.
    """
    template_name = "accounts/dashboard.html"


def verify_email(request, token):
    """
    Verify a user's email address using a signed token.

    Handles:
    - Successful verification
    - Expired tokens (24h expiry)
    - Invalid/tampered tokens
    - Already verified accounts
    """
    try:
        user_pk = verify_token(token)
        user = User.objects.get(pk=user_pk)

        if user.email_verified:
            messages.info(
                request,
                _("Your email address is already verified."),
            )
        else:
            user.email_verified = True
            user.save(update_fields=["email_verified"])
            messages.success(
                request,
                _("Your email address has been verified successfully!"),
            )

        return HttpResponseRedirect(reverse("accounts:dashboard"))

    except (SignatureExpired, BadSignature, User.DoesNotExist):
        messages.error(
            request,
            _("The verification link is invalid or has expired. "
              "Please request a new verification email."),
        )
        return HttpResponseRedirect(reverse("accounts:resend_verification"))


class ResendVerificationView(LoginRequiredMixin, TemplateView):
    """
    View to resend the email verification link.

    Only accessible to authenticated users who are not yet verified.
    Already verified users are redirected to dashboard with a message.
    """
    template_name = "accounts/resend_verification.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.email_verified:
            messages.info(request, _("Your email is already verified."))
            return HttpResponseRedirect(reverse("accounts:dashboard"))
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        verification_url = build_verification_url(request, request.user)
        try:
            request.user.email_user(
                subject=_("Verify your email address"),
                message=_(
                    f"Hi {request.user.full_name},\n\n"
                    f"Please verify your email address by clicking the link below:\n"
                    f"{verification_url}\n\n"
                    f"This link will expire in 24 hours.\n\n"
                     f"Thank you,\nTeam"
                ),
                fail_silently=False,
            )
            messages.success(
                request,
                _("A new verification email has been sent. "
                  "Please check your inbox."),
            )
        except Exception:
            messages.error(
                request,
                _("Could not send verification email. Please try again later."),
            )
        return HttpResponseRedirect(reverse("accounts:dashboard"))


class ProfileView(LoginRequiredMixin, DetailView):
    """
    User profile display view.

    Shows the authenticated user's profile information.
    """
    model = User
    template_name = "accounts/profile.html"
    context_object_name = "profile_user"

    def get_object(self, queryset=None):
        return self.request.user


class ProfileEditView(LoginRequiredMixin, UpdateView):
    """
    Edit profile view.

    Allows the user to update their:
    - Full name
    - Phone number
    - Username
    - Profile picture

    Email changes are not allowed in this phase.
    """
    model = User
    form_class = ProfileEditForm
    template_name = "accounts/profile_edit.html"

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return reverse("accounts:profile")

    def form_valid(self, form):
        messages.success(self.request, _("Your profile has been updated."))
        return super().form_valid(form)


class ChangeSecurityQuestionsView(LoginRequiredMixin, FormView):
    """
    Update security questions view.

    Requires the user's current password before allowing changes.
    All three questions are replaced with new ones.
    """
    form_class = ChangeSecurityQuestionsForm
    template_name = "accounts/change_security_questions.html"

    def get_success_url(self):
        return reverse("accounts:profile")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(
            self.request,
            _("Your security questions have been updated."),
        )
        return super().form_valid(form)


class CustomPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    """
    Change password view using Django's built-in PasswordChangeView.

    Requires:
    - Current password
    - New password (with password validators)
    - Confirm new password
    """
    template_name = "registration/password_change_form.html"
    success_url = reverse_lazy("accounts:password_change_done")

    def form_valid(self, form):
        messages.success(
            self.request,
            _("Your password has been changed successfully."),
        )
        return super().form_valid(form)


class SecurityQuestionRecoveryView(FormView):
    """
    Account recovery via security questions.

    Step 1: User enters email address.
    Step 2: User answers their three security questions.

    If all answers are correct, the user is stored in session
    and redirected to the password reset step.
    """

    form_class = SecurityQuestionRecoveryForm
    template_name = "accounts/security_recovery.html"
    success_url = reverse_lazy("accounts:security_recovery_reset")

    def get_form_kwargs(self):
        """
        Pass the recovery user from session to the form if available.
        """
        kwargs = super().get_form_kwargs()
        recovery_user_id = self.request.session.get("recovery_user_id")
        if recovery_user_id:
            try:
                kwargs["user"] = User.objects.get(pk=recovery_user_id)
            except User.DoesNotExist:
                pass
        return kwargs

    def get_context_data(self, **kwargs):
        """
        Add security questions to context when user is in session.
        """
        context = super().get_context_data(**kwargs)
        recovery_user_id = self.request.session.get("recovery_user_id")
        if recovery_user_id:
            try:
                user = User.objects.get(pk=recovery_user_id)
                context["security_questions"] = list(
                    user.security_questions.all().order_by("id")
                )
            except User.DoesNotExist:
                pass
        return context

    def form_valid(self, form):
        """
        If email step: store user in session and re-render with questions.
        If answers step: store verified user in session and redirect.
        """
        if form.user and not self.request.session.get("recovery_user_id"):
            self.request.session["recovery_user_id"] = form.user.pk
            messages.success(
                self.request,
                _("Please answer your security questions to verify your identity."),
            )
            return self.render_to_response(
                self.get_context_data(form=form)
            )

        if form.user and self.request.session.get("recovery_user_id"):
            self.request.session["recovery_verified_user_id"] = form.user.pk
            messages.success(
                self.request,
                _("Identity verified! Please set a new password."),
            )
            return super().form_valid(form)

        return self.render_to_response(self.get_context_data(form=form))


class RecoveryPasswordResetView(FormView):
    """
    Password reset after successful security question recovery.

    Requires the user to have completed the security question step.
    The verified user is retrieved from session and their password is updated.
    """

    form_class = RecoveryPasswordResetForm
    template_name = "accounts/security_recovery_reset.html"
    success_url = reverse_lazy("accounts:login")

    def dispatch(self, request, *args, **kwargs):
        """
        Ensure the user completed the security question step.
        """
        recovery_verified_user_id = request.session.get(
            "recovery_verified_user_id"
        )
        if not recovery_verified_user_id:
            messages.error(
                request,
                _("Please complete the security question verification first."),
            )
            return HttpResponseRedirect(
                reverse("accounts:security_recovery")
            )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        """
        Pass the verified user to the form.
        """
        kwargs = super().get_form_kwargs()
        recovery_verified_user_id = self.request.session.get(
            "recovery_verified_user_id"
        )
        if recovery_verified_user_id:
            try:
                kwargs["user"] = User.objects.get(
                    pk=recovery_verified_user_id
                )
            except User.DoesNotExist:
                pass
        return kwargs

    def form_valid(self, form):
        """
        Save the new password and clear recovery session data.
        """
        form.save()
        self.request.session.pop("recovery_user_id", None)
        self.request.session.pop("recovery_verified_user_id", None)
        messages.success(
            self.request,
            _("Your password has been reset successfully. Please log in."),
        )
        return super().form_valid(form)


@login_required
def payment_page(request):
    """
    Display the payment page with saved cards and transaction history.
    """
    saved_cards = SavedCard.objects.filter(user=request.user).order_by('-is_default', '-created_at')

    payment_methods = [
        {'id': 'card', 'name': 'Card', 'icon': '💳'},
        {'id': 'bank', 'name': 'Bank Transfer', 'icon': '🏦'},
        {'id': 'ussd', 'name': 'USSD', 'icon': '📱'},
        {'id': 'qr', 'name': 'QR Code', 'icon': '📷'},
    ]

    transactions = Transaction.objects.filter(
        user=request.user
    ).order_by('-date')[:50]

    context = {
        'user': request.user,
        'saved_cards': saved_cards,
        'payment_methods': payment_methods,
        'transactions': transactions,
        'plan_name': request.GET.get('plan', 'Premium Farm Management'),
        'billing_period': request.GET.get('period', 'Monthly'),
        'amount': request.GET.get('amount', '49,000.00'),
    }
    return render(request, 'accounts/payment.html', context)


@login_required
def add_saved_card(request):
    """
    Save a new payment card for the user.

    Only the last 4 digits and expiry date are persisted. The full card
    number and CVV are never stored or logged, in line with PCI-DSS
    guidance for merchants who are not a certified card data processor.
    """
    if request.method != 'POST':
        return redirect('accounts:payment')

    card_number = request.POST.get('cardNumber', '')
    expiry = request.POST.get('expiry', '').strip()
    cvv = request.POST.get('cvv', '').strip()
    make_default = bool(request.POST.get('makeDefault'))

    digits_only = re.sub(r'\D', '', card_number)

    if len(digits_only) < 13 or len(digits_only) > 19:
        messages.error(request, _('Please enter a valid card number.'))
        return redirect('accounts:payment')

    if not re.match(r'^(0[1-9]|1[0-2])/\d{2}$', expiry):
        messages.error(request, _('Please enter a valid expiry date (MM/YY).'))
        return redirect('accounts:payment')

    if not re.match(r'^\d{3,4}$', cvv):
        messages.error(request, _('Please enter a valid CVV.'))
        return redirect('accounts:payment')

    last4 = digits_only[-4:]
    is_first_card = not SavedCard.objects.filter(user=request.user).exists()

    if make_default or is_first_card:
        SavedCard.objects.filter(user=request.user).update(is_default=False)

    SavedCard.objects.create(
        user=request.user,
        last4=last4,
        expiry=expiry,
        is_default=make_default or is_first_card,
    )

    messages.success(request, _('Card saved successfully.'))
    return redirect('accounts:payment')


@login_required
def process_payment(request):
    """
    Process the payment submission.
    """
    if request.method != 'POST':
        return redirect('accounts:payment')

    payment_method = request.POST.get('paymentMethod', 'card')
    card_number = request.POST.get('cardNumber', '')

    if not card_number or len(card_number.replace(' ', '')) < 16:
        messages.error(request, 'Invalid card number.')
        return redirect('accounts:payment')

    messages.success(request, 'Payment processed successfully!')
    return redirect('accounts:payment_success')


@login_required
def payment_success(request):
    """
    Payment success page.
    """
    return render(request, 'accounts/payment_success.html')


@login_required
def payment_cancel(request):
    """
    Payment cancellation page.
    """
    return render(request, 'accounts/payment_cancel.html')
