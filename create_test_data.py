import os
import sys
import django
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'farm_proc_tamipee.settings')
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from accounts.models import CustomUser
from shop.models import Order, Payment, Category, Product

# Get or create a test customer
customer, created = CustomUser.objects.get_or_create(
    email='test.customer@example.com',
    defaults={
        'full_name': 'Test Customer',
        'username': 'testcustomer',
        'role': 'CUSTOMER',
        'is_active': True,
    }
)

if created:
    customer.set_password('testpass123')
    customer.save()
    print(f"Created new customer: {customer.email}")
else:
    print(f"Using existing customer: {customer.email}")

# Get or create default category and products
category, _ = Category.objects.get_or_create(
    name='Test Products',
    defaults={'description': 'Test category for sample data'}
)

products = []
for i in range(3):
    product, _ = Product.objects.get_or_create(
        name=f'Test Product {i+1}',
        category=category,
        defaults={
            'description': f'Sample product {i+1}',
            'price': Decimal(str(1000 + i*500)),
            'stock_quantity': 100
        }
    )
    products.append(product)

# Create 3 orders with different statuses
statuses = ['paid', 'shipped', 'delivered']
base_date = timezone.now() - timedelta(days=30)

for idx, status in enumerate(statuses):
    order = Order.objects.create(
        user=customer,
        total=Decimal(str(1500 + idx*1000)),
        status=status
    )
    order.created_at = base_date + timedelta(days=idx*10)
    order.save(update_fields=['created_at'])
    
    # Create payment for each order
    payment_status = 'success' if status != 'cancelled' else 'failed'
    payment = Payment.objects.create(
        order=order,
        amount=order.total,
        status=payment_status,
        reference=f'TEST-REF-{idx+1:04d}'
    )
    payment.created_at = order.created_at + timedelta(hours=1)
    payment.save(update_fields=['created_at'])
    
    print(f"Created Order #{order.pk} (${order.total}, {status}) with Payment #{payment.pk}")

print(f"\nCustomer ID: {customer.pk}")
print(f"Total Orders: {Order.objects.filter(user=customer).count()}")
print(f"Total Spent: ${Order.objects.filter(user=customer, status__in=['paid', 'shipped', 'delivered']).aggregate(total=django.db.models.Sum('total'))['total'] or 0}")
print(f"\nVisit: http://127.0.0.1:8000/admin-dashboard/users/{customer.pk}/")
