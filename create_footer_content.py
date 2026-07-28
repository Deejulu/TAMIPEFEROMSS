#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'farm_proc_tamipee.settings')
django.setup()

from admin_dashboard.models import SiteContent

# Create Business Hours content
business_hours, created = SiteContent.objects.get_or_create(
    section='business_hours',
    defaults={
        'title': 'Business Hours',
        'content': '''<p><strong>Monday - Friday:</strong> 9:00 AM - 5:00 PM</p>
<p><strong>Saturday:</strong> 10:00 AM - 2:00 PM</p>
<p><strong>Sunday:</strong> Closed</p>'''
    }
)
print(f'Business Hours: {"created" if created else "already exists"}')

# Create Social Media content
social_media, created = SiteContent.objects.get_or_create(
    section='social_media',
    defaults={
        'title': 'Connect With Us',
        'content': '''<p><a href="https://facebook.com/tamipee" style="color: #FFC107;"><i class="bi bi-facebook"></i> Facebook</a></p>
<p><a href="https://twitter.com/tamipee" style="color: #FFC107;"><i class="bi bi-twitter"></i> Twitter</a></p>
<p><a href="https://instagram.com/tamipee" style="color: #FFC107;"><i class="bi bi-instagram"></i> Instagram</a></p>'''
    }
)
print(f'Social Media: {"created" if created else "already exists"}')

print('Footer content created successfully!')
