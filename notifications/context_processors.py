from django.db.models import Count

from .models import Notification


def unread_notification_count(request):
    return {
        'unread_notification_count': Notification.objects.filter(is_read=False).count()
    }
