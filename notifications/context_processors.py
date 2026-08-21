from django.core.cache import cache
from django.db.models import Count

from .models import Notification


def unread_notification_count(request):
    cache_key = 'unread_notification_count'
    count = cache.get(cache_key)
    if count is None:
        count = Notification.objects.filter(is_read=False).count()
        cache.set(cache_key, count, 60)
    return {
        'unread_notification_count': count
    }
