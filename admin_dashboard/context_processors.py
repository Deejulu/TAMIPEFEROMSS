"""
Context processors for admin_dashboard app.
Provides site-wide content like business hours and social media links.
"""

from django.core.cache import cache

from .models import SiteContent


def site_content(request):
    cache_key = 'site_content_context'
    cached = cache.get(cache_key)
    if cached is None:
        business_hours = SiteContent.get_section_content('business_hours')
        business_hours_detail = None
        if business_hours:
            try:
                business_hours_detail = business_hours.business_hours_detail
            except SiteContent.business_hours_detail.RelatedObjectDoesNotExist:
                business_hours_detail = None

        social_media = SiteContent.get_section_content('social_media')

        cached = {
            'business_hours_content': business_hours,
            'business_hours_detail': business_hours_detail,
            'social_media_content': social_media,
        }
        cache.set(cache_key, cached, 300)

    return cached
