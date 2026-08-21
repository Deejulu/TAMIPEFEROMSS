import re
from io import StringIO, BytesIO

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse

from django.urls import reverse_lazy, reverse
from django.http import HttpResponseRedirect
from django.views.generic import CreateView, TemplateView, RedirectView, UpdateView, FormView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import get_user_model, login as auth_login
from django.utils.translation import gettext_lazy as _
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.core.signing import SignatureExpired, BadSignature
from django.contrib.auth.views import PasswordChangeView, LoginView
from django.core.management import call_command
from django.views.generic import ListView
from django.db.models import Q

from shop.models import Order, Payment

from .forms import CustomSignupForm, ProfileEditForm, ChangeSecurityQuestionsForm, SecurityQuestionRecoveryForm, RecoveryPasswordResetForm
from .tokens import verify_token, build_verification_url
from .models import SavedCard, Transaction
from .constants import SECURITY_QUESTIONS

User = get_user_model()


class CustomLoginView(LoginView):
    """
    Custom login view that redirects users based on their role:
    - Super Admin / Farm Manager -> admin_dashboard:overview
    - Staff / Customer -> accounts:dashboard
    Also checks if the user must change their password.
    """

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.request.user
        if user.must_change_password:
            user.must_change_password = False
            user.save(update_fields=['must_change_password'])
            messages.warning(
                self.request,
                _("Your password has been reset by an administrator. Please change it now.")
            )
            return redirect('accounts:password_change')
        if user.role in (User.Role.SUPER_ADMIN, User.Role.SUPER_STAFF, User.Role.FARM_MANAGER):
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
        if user.role in (User.Role.SUPER_ADMIN, User.Role.SUPER_STAFF, User.Role.FARM_MANAGER):
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
            if user.role in (User.Role.SUPER_ADMIN, User.Role.SUPER_STAFF, User.Role.FARM_MANAGER):
                return reverse_lazy("admin_dashboard:overview")
            return reverse_lazy("accounts:dashboard")
        return reverse_lazy("accounts:login")


class SignUpView(CreateView):
    """
    User registration view.

    Uses the CustomSignupForm to handle new user signups.
    All new users are automatically assigned the CUSTOMER role.
    On successful registration the user is automatically logged in and shown
    the one-time credentials page (see `render_signup_credentials`), which
    lets them download their username, password and security questions.

    `sensitive_post_parameters` is applied so that if this view ever raises,
    Django's error reporting redacts the raw password and security answers
    instead of including them in a traceback, email, or log record.
    """
    form_class = CustomSignupForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy("accounts:dashboard")

    @method_decorator(sensitive_post_parameters(
        "password1",
        "password2",
        "security_answer_1",
        "security_answer_2",
        "security_answer_3",
    ))
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """
        Called when the form is submitted with valid data.

        Saves the user, logs them in, and returns the one-time credentials
        page instead of redirecting, so the raw password (available only in
        this request) can be offered as a download exactly once.
        """
        self.object = form.save()
        user = self.object

        # Auto-login the user after successful signup
        auth_login(self.request, user)

        # Send verification email only if user provided an email
        if user.email:
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

        # Render the one-time credentials page. The raw password is read
        # straight from the submitted form and is never persisted.
        return render_signup_credentials(
            self.request,
            user=user,
            raw_password=form.cleaned_data.get("password1", ""),
            question_keys=[
                form.cleaned_data.get("security_question_1", ""),
                form.cleaned_data.get("security_question_2", ""),
                form.cleaned_data.get("security_question_3", ""),
            ],
            form=form,
            next_url=str(self.success_url),
            continue_label=_("Continue to My Dashboard"),
        )


def build_credentials_file_text(username, raw_password, question_labels):
    """
    Build the plain-text credentials file offered once at signup.

    Contains the username, the raw password, and the security QUESTIONS only.
    Security answers are hashed on save and are deliberately never included.
    """
    lines = [
        "TAMIPEE - YOUR ACCOUNT CREDENTIALS",
        "=" * 52,
        "",
        "KEEP THIS FILE SAFE. Your password is shown here in plain text",
        "and CANNOT be retrieved again after you leave this page.",
        "",
        "-" * 52,
        "LOGIN DETAILS",
        "-" * 52,
        f"Username: {username}",
        f"Password: {raw_password}",
        "",
        "-" * 52,
        "YOUR SECURITY QUESTIONS (for account recovery)",
        "-" * 52,
    ]
    for index, label in enumerate(question_labels, start=1):
        lines.append(f"{index}. {label}")

    lines += [
        "",
        "Your ANSWERS are not stored in this file. They are saved securely",
        "hashed and cannot be displayed by anyone, including support staff.",
        "",
        "-" * 52,
        "IMPORTANT",
        "-" * 52,
        "- Store this file somewhere private and secure.",
        "- Do not share your password or answers with anyone.",
        "- TAMIPEE will never ask you to reveal your password or answers.",
        "- Change your password if you think it has been exposed.",
        "",
    ]
    return "\n".join(lines)


def render_signup_credentials(
    request,
    user,
    raw_password,
    question_keys,
    form=None,
    next_url=None,
    template_name="accounts/signup_credentials.html",
    is_admin_created=False,
    continue_label=None,
):
    """
    Render the one-time credentials page for a newly created account.

    The raw password is embedded in this single HTML response only, so the
    browser can build the .txt download client-side (JS Blob). It is never
    written to the database, the session, a cookie, or a log file, and the
    response is marked no-store so it is not cached anywhere.

    After the response body is rendered, the raw password is scrubbed from
    the form's cleaned_data so it does not linger in memory for the rest of
    the request (e.g. if a later error report walks local variables).
    """
    question_lookup = dict(SECURITY_QUESTIONS)
    question_labels = [
        question_lookup.get(key, key) for key in question_keys if key
    ]

    file_text = build_credentials_file_text(
        user.username, raw_password, question_labels
    )
    filename = f"tamipee-credentials-{user.username}.txt"

    # render() renders the template to bytes immediately, so the raw password
    # is fully consumed by the time this call returns.
    response = render(
        request,
        template_name,
        {
            "new_username": user.username,
            "new_full_name": user.full_name,
            "account_id": user.account_id,
            "raw_password": raw_password,
            "question_labels": question_labels,
            "credentials_file_text": file_text,
            "credentials_filename": filename,
            "next_url": next_url or reverse("accounts:dashboard"),
            "is_admin_created": is_admin_created,
            "continue_label": continue_label,
        },
    )

    # Never cache or store this response anywhere.
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    response["Referrer-Policy"] = "no-referrer"

    # Discard the raw password from the form so it is not retained after this
    # point. The only remaining copy is the response body already on its way
    # to the user who just typed it.
    if form is not None:
        for field in ("password1", "password2"):
            if field in getattr(form, "cleaned_data", {}):
                form.cleaned_data[field] = ""
    raw_password = ""

    return response


class DashboardView(LoginRequiredMixin, TemplateView):
    """
    User dashboard view.

    Requires the user to be authenticated (LoginRequiredMixin).
    Displays user profile information and provides navigation to
    profile management pages.
    """
    template_name = "accounts/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["recent_orders"] = (
            self.request.user.orders.prefetch_related("items").order_by("-created_at")[:3]
        )
        return context


class CustomerOrderListView(LoginRequiredMixin, ListView):
    """Display the authenticated customer's order history."""

    template_name = "accounts/order_list.html"
    context_object_name = "orders"

    def get_queryset(self):
        return self.request.user.orders.prefetch_related("items").order_by("-created_at")


class CustomerOrderDetailView(LoginRequiredMixin, DetailView):
    """Display one order only when it belongs to the authenticated customer."""

    template_name = "accounts/order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return (
            self.request.user.orders.prefetch_related("items__product", "payments")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["timeline_progress"] = self.object.timeline_progress
        return context


class CustomerPaymentHistoryView(LoginRequiredMixin, ListView):
    """Display the authenticated customer's payment history."""

    template_name = "accounts/payment_history.html"
    context_object_name = "payments"

    def get_queryset(self):
        return Payment.objects.filter(
            order__user=self.request.user
        ).select_related("order").order_by("-created_at")


class CustomerPaymentReceiptView(LoginRequiredMixin, DetailView):
    """Display a printable receipt for one of the customer's successful payments."""

    template_name = "accounts/payment_receipt.html"
    context_object_name = "payment"

    def get_queryset(self):
        return Payment.objects.filter(
            order__user=self.request.user,
            status="success",
        ).select_related("order", "order__delivery_option").prefetch_related("order__items")


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
        # Process profile photo if uploaded
        profile_picture = form.cleaned_data.get('profile_picture')
        if profile_picture:
            from accounts.utils import process_profile_photo
            processed = process_profile_photo(profile_picture)
            form.instance.profile_picture = processed
        
        # Handle photo removal
        if form.cleaned_data.get('remove_profile_picture') and self.object.profile_picture:
            self.object.profile_picture.delete(save=False)
            self.object.profile_picture = None
        
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

    Step 1: User enters their username.
    Step 2: User answers their three security questions.

    If all answers are correct, the user is stored in session
    and redirected to the password reset step.

    Rate limiting: after 5 failed answer attempts for the same username,
    the recovery session is cleared and the user must start over.
    """

    form_class = SecurityQuestionRecoveryForm
    template_name = "accounts/security_recovery.html"
    success_url = reverse_lazy("accounts:security_recovery_reset")
    MAX_FAILED_ATTEMPTS = 5

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
        Also pass attempt info for display.
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

        context["failed_attempts"] = self.request.session.get("recovery_failed_attempts", 0)
        context["max_attempts"] = self.MAX_FAILED_ATTEMPTS
        context["locked"] = self.request.session.get("recovery_locked", False)
        return context

    def _clear_recovery_session(self):
        """Clear all recovery-related session data."""
        self.request.session.pop("recovery_user_id", None)
        self.request.session.pop("recovery_verified_user_id", None)
        self.request.session.pop("recovery_failed_attempts", None)
        self.request.session.pop("recovery_locked", None)

    def _increment_failed_attempts(self):
        """Increment failed attempt counter and lock if threshold reached."""
        attempts = self.request.session.get("recovery_failed_attempts", 0) + 1
        self.request.session["recovery_failed_attempts"] = attempts
        if attempts >= self.MAX_FAILED_ATTEMPTS:
            self.request.session["recovery_locked"] = True
            self._clear_recovery_session()

    def form_valid(self, form):
        """
        If username step: store user in session and re-render with questions.
        If answers step: verify and redirect to password reset.
        """
        if form.user and not self.request.session.get("recovery_user_id"):
            self.request.session["recovery_user_id"] = form.user.pk
            self.request.session["recovery_failed_attempts"] = 0
            self.request.session["recovery_locked"] = False
            messages.success(
                self.request,
                _("Please answer your security questions to verify your identity."),
            )
            return self.render_to_response(
                self.get_context_data(form=form)
            )

        if form.user and self.request.session.get("recovery_user_id"):
            self.request.session["recovery_verified_user_id"] = form.user.pk
            self.request.session.pop("recovery_failed_attempts", None)
            self.request.session.pop("recovery_locked", None)
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
        self.request.session.pop("recovery_failed_attempts", None)
        self.request.session.pop("recovery_locked", None)
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
