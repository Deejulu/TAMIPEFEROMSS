from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class SiteContent(models.Model):
    """
    Model for managing website content sections.
    Each section has a unique key and content field.
    """
    
    SECTION_CHOICES = [
        ('about', _('About Page')),
        ('contact', _('Contact Page')),
        ('faq', _('FAQ (Frequently Asked Questions)')),
        ('delivery_info', _('Delivery Information')),
        ('terms_privacy', _('Terms & Privacy Policy')),
        ('return_refund', _('Return & Refund Policy')),
        ('homepage_hero', _('Homepage Hero Text')),
        ('shop_banner', _('Shop Announcement Banner')),
        ('business_hours', _('Business Hours')),
        ('social_media', _('Social Media Links')),
    ]
    
    section = models.CharField(
        _("section"),
        max_length=50,
        choices=SECTION_CHOICES,
        unique=True,
        help_text=_("The section of the website this content belongs to")
    )
    title = models.CharField(
        _("title"),
        max_length=200,
        help_text=_("Title for this section")
    )
    content = models.TextField(
        _("content"),
        blank=True,
        help_text=_("Main content for this section (HTML allowed)")
    )
    facebook_url = models.URLField(_("Facebook URL"), blank=True)
    instagram_url = models.URLField(_("Instagram URL"), blank=True)
    twitter_url = models.URLField(_("Twitter/X URL"), blank=True)
    tiktok_url = models.URLField(_("TikTok URL"), blank=True)
    whatsapp_url = models.URLField(_("WhatsApp URL"), blank=True)
    is_sample = models.BooleanField(_("sample data"), default=False)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    
    class Meta:
        verbose_name = _("site content")
        verbose_name_plural = _("site contents")
        ordering = ['section']
    
    def __str__(self):
        return f"{self.get_section_display()}"

    @property
    def social_links(self):
        """Return configured social media links in their display order."""
        links = [
            {"name": "Facebook", "url": self.facebook_url, "icon": "fa-facebook-f"},
            {"name": "Instagram", "url": self.instagram_url, "icon": "fa-instagram"},
            {"name": "Twitter/X", "url": self.twitter_url, "icon": "fa-x-twitter"},
            {"name": "TikTok", "url": self.tiktok_url, "icon": "fa-tiktok"},
            {"name": "WhatsApp", "url": self.whatsapp_url, "icon": "fa-whatsapp"},
        ]
        return [link for link in links if link["url"]]
    
    @classmethod
    def get_section_content(cls, section_key):
        """
        Get content for a specific section, returns fallback if not found.
        """
        try:
            return cls.objects.get(section=section_key)
        except cls.DoesNotExist:
            return None


class BusinessHours(models.Model):
    """
    Structured business hours for the business_hours section of SiteContent.
    Uses a OneToOneField to SiteContent so the structured data lives
    alongside the generic content record but with its own dedicated fields.
    """

    site_content = models.OneToOneField(
        SiteContent,
        on_delete=models.CASCADE,
        related_name='business_hours_detail',
        verbose_name=_("site content"),
        help_text=_("The SiteContent record this business hours data belongs to"),
    )

    DAY_CHOICES = [
        ('monday', _('Monday')),
        ('tuesday', _('Tuesday')),
        ('wednesday', _('Wednesday')),
        ('thursday', _('Thursday')),
        ('friday', _('Friday')),
        ('saturday', _('Saturday')),
        ('sunday', _('Sunday')),
    ]

    monday_open = models.TimeField(_("Monday open"), null=True, blank=True)
    monday_close = models.TimeField(_("Monday close"), null=True, blank=True)
    monday_is_closed = models.BooleanField(_("Monday closed"), default=False)

    tuesday_open = models.TimeField(_("Tuesday open"), null=True, blank=True)
    tuesday_close = models.TimeField(_("Tuesday close"), null=True, blank=True)
    tuesday_is_closed = models.BooleanField(_("Tuesday closed"), default=False)

    wednesday_open = models.TimeField(_("Wednesday open"), null=True, blank=True)
    wednesday_close = models.TimeField(_("Wednesday close"), null=True, blank=True)
    wednesday_is_closed = models.BooleanField(_("Wednesday closed"), default=False)

    thursday_open = models.TimeField(_("Thursday open"), null=True, blank=True)
    thursday_close = models.TimeField(_("Thursday close"), null=True, blank=True)
    thursday_is_closed = models.BooleanField(_("Thursday closed"), default=False)

    friday_open = models.TimeField(_("Friday open"), null=True, blank=True)
    friday_close = models.TimeField(_("Friday close"), null=True, blank=True)
    friday_is_closed = models.BooleanField(_("Friday closed"), default=False)

    saturday_open = models.TimeField(_("Saturday open"), null=True, blank=True)
    saturday_close = models.TimeField(_("Saturday close"), null=True, blank=True)
    saturday_is_closed = models.BooleanField(_("Saturday closed"), default=False)

    sunday_open = models.TimeField(_("Sunday open"), null=True, blank=True)
    sunday_close = models.TimeField(_("Sunday close"), null=True, blank=True)
    sunday_is_closed = models.BooleanField(_("Sunday closed"), default=False)

    notes = models.TextField(
        _("notes"),
        blank=True,
        help_text=_("Special hours, holiday notices, or other remarks"),
    )

    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("business hours")
        verbose_name_plural = _("business hours")

    def __str__(self):
        return f"Business Hours for {self.site_content.get_section_display()}"

    def get_day_hours(self, day_key):
        """Return a dict with open, close, is_closed for a given day key."""
        day_map = {
            'monday': ('monday_open', 'monday_close', 'monday_is_closed'),
            'tuesday': ('tuesday_open', 'tuesday_close', 'tuesday_is_closed'),
            'wednesday': ('wednesday_open', 'wednesday_close', 'wednesday_is_closed'),
            'thursday': ('thursday_open', 'thursday_close', 'thursday_is_closed'),
            'friday': ('friday_open', 'friday_close', 'friday_is_closed'),
            'saturday': ('saturday_open', 'saturday_close', 'saturday_is_closed'),
            'sunday': ('sunday_open', 'sunday_close', 'sunday_is_closed'),
        }
        open_field, close_field, closed_field = day_map.get(day_key, (None, None, None))
        if not open_field:
            return None
        return {
            'open': getattr(self, open_field),
            'close': getattr(self, close_field),
            'is_closed': getattr(self, closed_field),
        }

    def get_formatted_hours_list(self):
        """Return a list of (day_label, hours_text) tuples for rendering."""
        from django.utils import timezone as dj_timezone
        day_labels = [
            ('monday', _('Monday')),
            ('tuesday', _('Tuesday')),
            ('wednesday', _('Wednesday')),
            ('thursday', _('Thursday')),
            ('friday', _('Friday')),
            ('saturday', _('Saturday')),
            ('sunday', _('Sunday')),
        ]
        result = []
        for day_key, day_label in day_labels:
            hours = self.get_day_hours(day_key)
            if hours is None:
                continue
            if hours['is_closed']:
                result.append((day_label, _('Closed')))
            elif hours['open'] and hours['close']:
                result.append((day_label, f"{hours['open'].strftime('%I:%M %p')} – {hours['close'].strftime('%I:%M %p')}"))
            elif hours['open']:
                result.append((day_label, f"{hours['open'].strftime('%I:%M %p')} –"))
            elif hours['close']:
                result.append((day_label, f"– {hours['close'].strftime('%I:%M %p')}"))
            else:
                result.append((day_label, _('Hours not set')))
        return result

    def get_grouped_hours(self):
        """
        Return a list of (day_range_or_label, hours_text) tuples,
        grouping consecutive days with identical hours.
        """
        day_labels = [
            ('monday', _('Monday')),
            ('tuesday', _('Tuesday')),
            ('wednesday', _('Wednesday')),
            ('thursday', _('Thursday')),
            ('friday', _('Friday')),
            ('saturday', _('Saturday')),
            ('sunday', _('Sunday')),
        ]
        hours_list = []
        for day_key, day_label in day_labels:
            hours = self.get_day_hours(day_key)
            if hours is None:
                continue
            if hours['is_closed']:
                hours_text = _('Closed')
            elif hours['open'] and hours['close']:
                hours_text = f"{hours['open'].strftime('%I:%M %p')} – {hours['close'].strftime('%I:%M %p')}"
            else:
                hours_text = _('Hours not set')
            hours_list.append((day_key, day_label, hours_text))

        if not hours_list:
            return []

        grouped = []
        current_group = [hours_list[0]]

        for i in range(1, len(hours_list)):
            prev = hours_list[i - 1]
            curr = hours_list[i]
            if curr[2] == prev[2] and curr[0] == self._next_day(prev[0]):
                current_group.append(curr)
            else:
                grouped.append(current_group)
                current_group = [curr]
        grouped.append(current_group)

        result = []
        for group in grouped:
            if len(group) == 1:
                result.append((group[0][1], group[0][2]))
            else:
                range_label = f"{group[0][1]} – {group[-1][1]}"
                result.append((range_label, group[0][2]))

        return result

    def _next_day(self, day_key):
        day_order = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        idx = day_order.index(day_key)
        return day_order[(idx + 1) % 7]


class PaymentMethodSetting(models.Model):
    """
    Model for managing which payment methods are enabled/disabled.
    Admin can toggle payment methods on/off.
    """
    
    PAYMENT_METHOD_CHOICES = [
        ('paystack', _('Paystack (Card Payment)')),
        ('bank_transfer', _('Bank Transfer')),
        ('cash_on_delivery', _('Cash on Delivery')),
    ]
    
    payment_method = models.CharField(
        _("payment method"),
        max_length=50,
        choices=PAYMENT_METHOD_CHOICES,
        unique=True,
        help_text=_("The payment method to enable/disable")
    )
    enabled = models.BooleanField(
        _("enabled"),
        default=True,
        help_text=_("Whether this payment method is available to customers")
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    
    class Meta:
        verbose_name = _("payment method setting")
        verbose_name_plural = _("payment method settings")
        ordering = ['payment_method']
    
    def __str__(self):
        status = "Enabled" if self.enabled else "Disabled"
        return f"{self.get_payment_method_display()} - {status}"
    
    @classmethod
    def is_enabled(cls, payment_method):
        """
        Check if a specific payment method is enabled.
        Returns True if no setting exists (default enabled).
        """
        try:
            setting = cls.objects.get(payment_method=payment_method)
            return setting.enabled
        except cls.DoesNotExist:
            return True  # Default to enabled if no setting exists


class DeliveryOption(models.Model):
    """A customer-selectable delivery service configured by an administrator."""

    class Code(models.TextChoices):
        SAME_DAY = "same_day", _("Same Day Delivery")
        STANDARD = "standard", _("Standard Delivery")
        ECONOMY = "economy", _("Economy Delivery")

    code = models.CharField(_("code"), max_length=30, choices=Code.choices, unique=True)
    enabled = models.BooleanField(_("enabled"), default=True)
    price = models.DecimalField(_("delivery price"), max_digits=10, decimal_places=2, default=0)
    estimated_days = models.PositiveSmallIntegerField(_("estimated delivery days"), default=3)
    notes = models.TextField(_("delivery notes"), blank=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("delivery option")
        verbose_name_plural = _("delivery options")
        ordering = ["estimated_days", "price"]

    def __str__(self):
        return f"{self.get_code_display()} ({self.estimated_days} days)"


class MinimumOrderAmount(models.Model):
    """
    Model for managing minimum order amount requirement.
    Only one instance should exist (singleton pattern).
    """
    
    minimum_amount = models.DecimalField(
        _("minimum amount"),
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text=_("Minimum order amount in Naira (₦). Set to 0 to disable.")
    )
    enabled = models.BooleanField(
        _("enabled"),
        default=True,
        help_text=_("Whether to enforce minimum order amount")
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    
    class Meta:
        verbose_name = _("minimum order amount")
        verbose_name_plural = _("minimum order amount")
    
    def __str__(self):
        if self.enabled and self.minimum_amount > 0:
            return f"Minimum Order: ₦{self.minimum_amount:,.2f}"
        return "Minimum Order: Disabled"
    
    def save(self, *args, **kwargs):
        """
        Ensure only one instance exists (singleton).
        """
        if not self.pk and MinimumOrderAmount.objects.exists():
            # If this is a new instance and one already exists, update the existing one
            existing = MinimumOrderAmount.objects.first()
            self.pk = existing.pk
        super().save(*args, **kwargs)
    
    @classmethod
    def get_instance(cls):
        """
        Get or create the singleton instance.
        """
        instance, created = cls.objects.get_or_create(
            pk=1,
            defaults={'minimum_amount': 0.00, 'enabled': False}
        )
        return instance


class AuditLogEntry(models.Model):
    ACTION_CHOICES = [
        ('create', _('Created')),
        ('update', _('Updated')),
        ('delete', _('Deleted')),
        ('login', _('Login')),
        ('logout', _('Logout')),
        ('status_change', _('Status Changed')),
        ('toggle', _('Toggled')),
        ('other', _('Other')),
    ]

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        verbose_name=_("actor"),
    )
    action = models.CharField(
        _("action"),
        max_length=20,
        choices=ACTION_CHOICES,
    )
    target_model = models.CharField(
        _("target model"),
        max_length=100,
        blank=True,
    )
    target_id = models.PositiveIntegerField(
        _("target ID"),
        null=True,
        blank=True,
    )
    details = models.TextField(_("details"), blank=True)
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    timestamp = models.DateTimeField(_("timestamp"), auto_now_add=True)

    class Meta:
        verbose_name = _("audit log entry")
        verbose_name_plural = _("audit log entries")
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.get_action_display()} {self.target_model} #{self.target_id} by {self.actor or 'system'}"
