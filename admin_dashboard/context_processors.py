"""
Context processors for admin_dashboard app.
Provides site-wide content like business hours and social media links.
"""

from .models import SiteContent


def site_content(request):
    """
    Makes business hours and social media content available in all templates.
    """
    business_hours = SiteContent.get_section_content('business_hours')
    business_hours_detail = None
    if business_hours:
        try:
            business_hours_detail = business_hours.business_hours_detail
        except SiteContent.business_hours_detail.RelatedObjectDoesNotExist:
            business_hours_detail = None

    social_media = SiteContent.get_section_content('social_media')

    return {
        'business_hours_content': business_hours,
        'business_hours_detail': business_hours_detail,
        'social_media_content': social_media,
    }
