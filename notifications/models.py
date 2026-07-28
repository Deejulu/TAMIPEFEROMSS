from django.db import models
from django.utils.translation import gettext_lazy as _


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('order', 'New Order'),
        ('payment', 'Payment Received'),
        ('low_stock', 'Low Stock Alert'),
        ('user', 'New User Registered'),
        ('system', 'System'),
        ('batch_alert', 'Batch Alert'),
    ]

    notification_type = models.CharField(_("type"), max_length=20, choices=NOTIFICATION_TYPES)
    message = models.CharField(_("message"), max_length=255)
    is_read = models.BooleanField(_("read"), default=False)
    related_object_id = models.PositiveIntegerField(_("related object id"), blank=True, null=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_notification_type_display()}: {self.message[:50]}"
