from django.conf import settings
from .models import Notification


LOW_STOCK_THRESHOLD = getattr(settings, 'LOW_STOCK_THRESHOLD', 10)


def maybe_notify_low_stock(product, previous_stock, current_stock):
    threshold = getattr(settings, 'LOW_STOCK_THRESHOLD', 10)
    if previous_stock > threshold and current_stock <= threshold:
        if Notification.objects.filter(
            notification_type='low_stock',
            related_object_id=product.pk,
            is_read=False
        ).exists():
            return
        Notification.objects.create(
            notification_type='low_stock',
            message=f"{product.name} is low on stock ({current_stock} units left)",
            related_object_id=product.pk,
        )
