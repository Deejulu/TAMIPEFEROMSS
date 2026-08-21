from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import SiteContent, BusinessHours


@receiver(post_save, sender=SiteContent)
@receiver(post_delete, sender=SiteContent)
def invalidate_site_content_cache(sender, **kwargs):
    cache.delete('site_content_context')


@receiver(post_save, sender=BusinessHours)
@receiver(post_delete, sender=BusinessHours)
def invalidate_site_content_cache(sender, **kwargs):
    cache.delete('site_content_context')
