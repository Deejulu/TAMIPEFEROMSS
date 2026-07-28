import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'farm_proc_tamipee.settings')
django.setup()

from accounts.models import CustomUser
from django.db import IntegrityError

try:
    user = CustomUser.objects.create_user(
        email='admin@test.com',
        username='admin_test',
        full_name='Admin Test',
        password='admin123',
        role='SUPER_ADMIN'
    )
    user.is_active = True
    user.save()
    print('Super admin created successfully')
    print(f'Email: admin@test.com')
    print(f'Password: admin123')
except IntegrityError:
    print('User already exists - updating...')
    user = CustomUser.objects.get(email='admin@test.com')
    user.role = 'SUPER_ADMIN'
    user.is_active = True
    user.set_password('admin123')
    user.save()
    print('User updated successfully')
    print(f'Email: admin@test.com')
    print(f'Password: admin123')
