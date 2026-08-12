from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .constants import SECURITY_QUESTIONS


class CustomUserManager(BaseUserManager):
    """
    Custom manager for CustomUser model.
    Uses email as the unique identifier instead of username.
    Supports automatic username generation for admin-created users.
    """

    def create_user(self, email, full_name, password=None, username=None, **extra_fields):
        """
        Create and save a regular user with the given email, full_name, and password.

        If no username is provided, one will be generated automatically from
        the full_name. This ensures the username field is never null.
        """
        if not email:
            raise ValueError(_("The Email field must be set"))
        if not full_name:
            raise ValueError(_("The Full Name field must be set"))

        email = self.normalize_email(email)

        # Generate username if not provided
        if not username:
            from .utils import generate_unique_username
            name_parts = full_name.strip().split()
            first_name = name_parts[0] if name_parts else ""
            last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
            username = generate_unique_username(first_name, last_name)

        user = self.model(
            email=email,
            full_name=full_name,
            username=username,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, full_name, password=None, **extra_fields):
        """
        Create and save a superuser with the given email, full_name, and password.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", CustomUser.Role.SUPER_ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self.create_user(email, full_name, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """
    Custom User Model for farm_proc_tamipee.

    Uses email as the unique identifier instead of username.
    Supports role-based access control.
    Username is auto-generated during signup but editable later.
    """

    class Role(models.TextChoices):
        SUPER_ADMIN = "SUPER_ADMIN", _("Super Admin")
        SUPER_STAFF = "SUPER_STAFF", _("Super Staff")
        FARM_MANAGER = "FARM_MANAGER", _("Farm Manager")
        STAFF = "STAFF", _("Staff")
        CUSTOMER = "CUSTOMER", _("Customer")

    username = models.CharField(
        _("username"),
        max_length=150,
        unique=True,
        help_text=_(
            "Required. 150 characters or fewer. Auto-generated from your name."
        ),
        error_messages={
            "unique": _("A user with that username already exists."),
        },
    )
    email = models.EmailField(
        _("email address"),
        unique=True,
        max_length=255,
        error_messages={
            "unique": _("A user with this email address already exists."),
        },
    )
    full_name = models.CharField(_("full name"), max_length=255)
    phone_number = models.CharField(_("phone number"), max_length=20, blank=True)
    default_delivery_address = models.TextField(
        _("default delivery address"),
        blank=True,
        default="",
        help_text=_("Used to prefill delivery details during checkout."),
    )
    role = models.CharField(
        _("role"),
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
        help_text=_("Determines the user's permissions and access level."),
    )
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )
    is_superuser = models.BooleanField(
        _("superuser status"),
        default=False,
        help_text=_(
            "Designates that this user has all permissions without "
            "explicitly assigning them."
        ),
    )
    email_verified = models.BooleanField(
        _("email verified"),
        default=False,
        help_text=_("Designates whether the user has verified their email address."),
    )
    profile_picture = models.ImageField(
        _("profile picture"),
        upload_to="profile_pictures/",
        blank=True,
        null=True,
    )
    must_change_password = models.BooleanField(
        _("must change password"),
        default=False,
        help_text=_("Requires the user to change their password on next login."),
    )

    objects = CustomUserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email", "full_name"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.full_name} ({self.email})"

    def get_full_name(self):
        """Return the full name of the user."""
        return self.full_name

    def get_short_name(self):
        """Return the short name (first word of full name) of the user."""
        return self.full_name.split()[0] if self.full_name else self.email

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)

    @property
    def role_display(self):
        """Return the display name of the user's role."""
        return self.get_role_display()


class SecurityQuestion(models.Model):
    """
    Security question/answer pair for a user.

    Each user must have exactly three security questions during signup.
    Answers are stored hashed using Django's password hashing utilities.
    Questions are selected from a fixed list of 10 predefined questions.
    """

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="security_questions",
        verbose_name=_("user"),
    )
    question = models.CharField(
        _("security question"),
        max_length=50,
        choices=SECURITY_QUESTIONS,
        help_text=_("Select a security question from the predefined list."),
    )
    hashed_answer = models.CharField(
        _("hashed answer"),
        max_length=255,
        help_text=_("The answer to the security question, stored securely hashed."),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("security question")
        verbose_name_plural = _("security questions")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "question"],
                name="unique_user_security_question",
            ),
        ]

    def __str__(self):
        return f"{self.user.full_name} - {self.get_question_display()}"


class SavedCard(models.Model):
    """
    Saved payment card for a user.

    Stores the last 4 digits, expiry date, and default status.
    Used for quick payment selection on the payment page.
    """

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="saved_cards",
        verbose_name=_("user"),
    )
    last4 = models.CharField(_("last 4 digits"), max_length=4)
    expiry = models.CharField(_("expiry date"), max_length=5)
    icon = models.CharField(_("card icon"), max_length=10, default="💳")
    is_default = models.BooleanField(_("default card"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("saved card")
        verbose_name_plural = _("saved cards")
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"•••• {self.last4}"


class Transaction(models.Model):
    """
    Payment transaction record.

    Tracks payment reference, amount, status, and method.
    Used for transaction history and receipt generation.
    """

    STATUS_CHOICES = [
        ("success", _("Successful")),
        ("pending", _("Pending")),
        ("failed", _("Failed")),
    ]

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name=_("user"),
    )
    reference = models.CharField(_("reference"), max_length=50, unique=True)
    amount = models.DecimalField(_("amount"), max_digits=10, decimal_places=2)
    currency = models.CharField(_("currency"), max_length=3, default="NGN")
    status = models.CharField(
        _("status"), max_length=10, choices=STATUS_CHOICES, default="pending"
    )
    payment_method = models.CharField(_("payment method"), max_length=20)
    date = models.DateTimeField(_("date"), auto_now_add=True)
    description = models.CharField(_("description"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("transaction")
        verbose_name_plural = _("transactions")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.reference} - ₦{self.amount} ({self.status})"
