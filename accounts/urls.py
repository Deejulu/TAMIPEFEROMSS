from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views

from . import views
from .forms import CustomAuthenticationForm

app_name = "accounts"

urlpatterns = [
    # User registration
    path("signup/", views.SignUpView.as_view(), name="signup"),

    # Authentication views (using custom login view for role-based redirect)
    path(
        "login/",
        views.CustomLoginView.as_view(
            template_name="accounts/login.html",
            authentication_form=CustomAuthenticationForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),

    # Dashboard (must be authenticated)
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path(
        "dashboard/orders/",
        views.CustomerOrderListView.as_view(),
        name="order_list",
    ),
    path(
        "dashboard/orders/<int:pk>/",
        views.CustomerOrderDetailView.as_view(),
        name="order_detail",
    ),
    path(
        "dashboard/payments/",
        views.CustomerPaymentHistoryView.as_view(),
        name="payment_history",
    ),
    path(
        "dashboard/payments/<int:pk>/receipt/",
        views.CustomerPaymentReceiptView.as_view(),
        name="payment_receipt",
    ),

    # Email Verification
    path("verify-email/<token>/", views.verify_email, name="verify_email"),
    path(
        "resend-verification/",
        views.ResendVerificationView.as_view(),
        name="resend_verification",
    ),

    # Profile
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("profile/edit/", views.ProfileEditView.as_view(), name="profile_edit"),

    # Security Questions
    path(
        "security-questions/",
        views.ChangeSecurityQuestionsView.as_view(),
        name="change_security_questions",
    ),

    # Security Question Recovery
    path(
        "recover/",
        views.SecurityQuestionRecoveryView.as_view(),
        name="security_recovery",
    ),
    path(
        "recover/reset/",
        views.RecoveryPasswordResetView.as_view(),
        name="security_recovery_reset",
    ),

    # Password Reset (Django built-in views)
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
            email_template_name="registration/password_reset_email.html",
            subject_template_name="registration/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),

    # Password Change (Django built-in view)
    path(
        "password-change/",
        views.CustomPasswordChangeView.as_view(),
        name="password_change",
    ),
    path(
        "password-change/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="registration/password_change_done.html",
        ),
        name="password_change_done",
    ),
    path(
        "payment/",
        views.payment_page,
        name="payment",
    ),
    path(
        "payment/process/",
        views.process_payment,
        name="process_payment",
    ),
    path(
        "payment/cards/add/",
        views.add_saved_card,
        name="add_saved_card",
    ),
    path(
        "payment/success/",
        views.payment_success,
        name="payment_success",
    ),
    path(
        "payment/cancel/",
        views.payment_cancel,
        name="payment_cancel",
    ),
]
