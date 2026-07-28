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
        help_text=_("Main content for this section (HTML allowed)")
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    
    class Meta:
        verbose_name = _("site content")
        verbose_name_plural = _("site contents")
        ordering = ['section']
    
    def __str__(self):
        return f"{self.get_section_display()}"
    
    @classmethod
    def get_section_content(cls, section_key):
        """
        Get content for a specific section, returns fallback if not found.
        """
        try:
            return cls.objects.get(section=section_key)
        except cls.DoesNotExist:
            return None


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
