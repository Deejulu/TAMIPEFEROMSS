from django.conf import settings
from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import MortalityLog, FeedLog, HealthMedicationLog, DailyActivityLog, Batch, GrowthRecord, VaccinationRecord, HarvestRecord, FarmExpense
from shop.models import OrderItem


ANALYTICS_CACHE_KEYS = [
    'batch_analytics_context',
    'analytics_monthly_feed_trend',
]


def invalidate_analytics_cache(sender, **kwargs):
    for key in ANALYTICS_CACHE_KEYS:
        cache.delete(key)


def invalidate_expense_summary_cache(sender, **kwargs):
    cache.delete('expense_summary_generation')


@receiver(post_save, sender=Batch)
@receiver(post_delete, sender=Batch)
def invalidate_analytics_on_batch_change(sender, instance, **kwargs):
    invalidate_analytics_cache(sender, **kwargs)


@receiver(post_save, sender=FeedLog)
@receiver(post_delete, sender=FeedLog)
def invalidate_analytics_on_feedlog_change(sender, instance, **kwargs):
    invalidate_analytics_cache(sender, **kwargs)
    invalidate_expense_summary_cache(sender, **kwargs)


@receiver(post_save, sender=GrowthRecord)
@receiver(post_delete, sender=GrowthRecord)
def invalidate_analytics_on_growth_change(sender, instance, **kwargs):
    invalidate_analytics_cache(sender, **kwargs)


@receiver(post_save, sender=MortalityLog)
@receiver(post_delete, sender=MortalityLog)
def invalidate_analytics_on_mortality_change(sender, instance, **kwargs):
    invalidate_analytics_cache(sender, **kwargs)
    invalidate_expense_summary_cache(sender, **kwargs)


@receiver(post_save, sender=VaccinationRecord)
@receiver(post_delete, sender=VaccinationRecord)
def invalidate_analytics_on_vaccination_change(sender, instance, **kwargs):
    invalidate_analytics_cache(sender, **kwargs)


@receiver(post_save, sender=HealthMedicationLog)
@receiver(post_delete, sender=HealthMedicationLog)
def invalidate_analytics_on_health_change(sender, instance, **kwargs):
    invalidate_analytics_cache(sender, **kwargs)


@receiver(post_save, sender=HarvestRecord)
@receiver(post_delete, sender=HarvestRecord)
def invalidate_analytics_on_harvest_change(sender, instance, **kwargs):
    invalidate_analytics_cache(sender, **kwargs)


@receiver(post_save, sender=OrderItem)
@receiver(post_delete, sender=OrderItem)
def invalidate_analytics_on_orderitem_change(sender, instance, **kwargs):
    invalidate_analytics_cache(sender, **kwargs)


@receiver(post_save, sender=FarmExpense)
@receiver(post_delete, sender=FarmExpense)
def invalidate_expense_on_farmexpense_change(sender, instance, **kwargs):
    invalidate_expense_summary_cache(sender, **kwargs)


@receiver(post_save, sender=MortalityLog)
def decrement_linked_product_stock(sender, instance, created, **kwargs):
    if not created:
        return
    batch = instance.batch
    linked_products = batch.linked_products.filter(is_active=True)
    for product in linked_products:
        if product.stock_quantity > 0:
            product.stock_quantity = max(product.stock_quantity - 1, 0)
            product.save(update_fields=['stock_quantity'])
        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                'Product %s linked to batch %s already has zero stock; cannot decrement further.',
                product.pk, batch.pk
            )


@receiver(post_save, sender=FeedLog)
def create_feed_activity_log(sender, instance, created, **kwargs):
    if not created:
        return
    feed_name = instance.feed_inventory.feed_type if instance.feed_inventory else 'feed'
    note = f"Fed {instance.batch.name} — {instance.quantity_kg}kg {feed_name}"
    DailyActivityLog.objects.create(
        batch=instance.batch,
        date=instance.date,
        note=note,
        created_by=instance.recorded_by,
        is_sample=False,
    )


@receiver(post_save, sender=HealthMedicationLog)
def create_medication_activity_log(sender, instance, created, **kwargs):
    if not created:
        return
    note = f"Administered {instance.medicine_name} to {instance.batch.name}"
    DailyActivityLog.objects.create(
        batch=instance.batch,
        date=instance.date,
        note=note,
        created_by=instance.recorded_by,
        is_sample=False,
    )
