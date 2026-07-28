"""
Context processors for admin_dashboard app.
Provides site-wide content like business hours and social media links.
"""

from .models import SiteContent


def site_content(request):
    """
    Makes business hours and social media content available in all templates.
    """
    return {
        'business_hours_content': SiteContent.get_section_content('business_hours'),
        'social_media_content': SiteContent.get_section_content('social_media'),
    }
