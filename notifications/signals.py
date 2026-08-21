from django.conf import settings
from django.core.cache import cache
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver

from accounts.models import CustomUser
from shop.models import Order, Payment

from .models import Notification


@receiver(pre_save, sender=Payment)
def capture_payment_previous_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._previous_status = sender.objects.get(pk=instance.pk).status
        except sender.DoesNotExist:
            instance._previous_status = None
    else:
        instance._previous_status = None


@receiver(post_save, sender=Order)
def notify_new_order(sender, instance, created, **kwargs):
    if getattr(settings, 'TESTING', False):
        return
    if created:
        Notification.objects.create(
            notification_type='order',
            message=f"New order #{instance.id} placed by {instance.user.full_name}",
            related_object_id=instance.id,
        )


@receiver(post_save, sender=Payment)
def notify_payment_received(sender, instance, created, **kwargs):
    if getattr(settings, 'TESTING', False):
        return
    if instance.status == 'success' and getattr(instance, '_previous_status', None) != 'success':
        Notification.objects.create(
            notification_type='payment',
            message=f"Payment of ₦{instance.amount} received for Order #{instance.order.id}",
            related_object_id=instance.order.id,
        )


@receiver(post_save, sender=CustomUser)
def notify_new_user(sender, instance, created, **kwargs):
    if getattr(settings, 'TESTING', False):
        return
    if created:
        Notification.objects.create(
            notification_type='user',
            message=f"New user registered: {instance.full_name} ({instance.get_role_display()})",
            related_object_id=instance.id,
        )


@receiver(post_save, sender=Notification)
@receiver(post_delete, sender=Notification)
def invalidate_notification_count_cache(sender, **kwargs):
    cache.delete('unread_notification_count')
