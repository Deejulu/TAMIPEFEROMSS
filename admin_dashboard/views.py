import csv
import secrets

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Count, Sum, F
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import ListView, TemplateView, DetailView, UpdateView, DeleteView, CreateView
from datetime import timedelta, datetime

from notifications.models import Notification
from shop.models import Order, Payment, Category, Product, OrderItem
from farm_management.models import Batch, FeedInventory, MortalityLog
from .models import SiteContent, PaymentMethodSetting, MinimumOrderAmount, AuditLogEntry, DeliveryOption
from .forms import UserEditForm, CategoryForm, ProductForm, SiteContentForm, DeliveryOptionForm, StaffCreateForm, StaffEditForm, StaffCreateForm, StaffEditForm
from .mixins import AdminRequiredMixin, SuperAdminRequiredMixin, StaffManagementMixin, ContentManagementMixin

User = get_user_model()


class AdminDashboardShell(AdminRequiredMixin, LoginRequiredMixin, TemplateView):
    """
    Base mixin for all admin dashboard placeholder views.
    Ensures only Super Admin, Super Staff, and Farm Manager can access.
    """


class OverviewView(AdminDashboardShell):
    template_name = 'admin_dashboard/overview.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Overview'

        # --- Farm Snapshot ---
        context['active_batches'] = Batch.objects.filter(status='active')
        context['active_batches_count'] = context['active_batches'].count()
        context['batches_by_species'] = (
            context['active_batches']
            .values('species')
            .annotate(count=Count('id'))
            .order_by('species')
        )
        all_alerts = Notification.objects.filter(
            notification_type='batch_alert',
            is_read=False,
        ).order_by('-created_at')
        context['active_alerts'] = all_alerts[:5]
        context['active_alerts_total'] = all_alerts.count()
        context['low_feed_inventory'] = FeedInventory.objects.filter(
            quantity_on_hand_kg__lte=F('reorder_point_kg'),
        ).order_by('feed_type')[:5]
        context['low_feed_inventory_count'] = FeedInventory.objects.filter(
            quantity_on_hand_kg__lte=F('reorder_point_kg'),
        ).count()

        # --- Orders/Shop Snapshot ---
        week_ago = timezone.now() - timedelta(days=7)
        context['recent_orders_count'] = Order.objects.filter(
            created_at__gte=week_ago,
        ).count()
        low_stock_products = [p for p in Product.objects.filter(is_active=True).order_by('name') if p.is_low_stock]
        context['low_stock_products'] = low_stock_products[:5]
        context['low_stock_products_count'] = len(low_stock_products)

        # --- User Snapshot ---
        context['total_active_users'] = User.objects.filter(is_active=True).count()
        context['users_by_role'] = (
            User.objects.filter(is_active=True)
            .values('role')
            .annotate(count=Count('id'))
            .order_by('role')
        )

        # --- Recent Customer Orders ---
        recent_orders = Order.objects.select_related('user').order_by('-created_at')
        context['recent_customer_orders'] = recent_orders[:5]
        context['recent_orders_total'] = recent_orders.count()

        # --- Quick Links ---
        context['quick_links'] = [
            {
                'name': 'Farm Management',
                'url': reverse('admin_dashboard:farm_management'),
                'icon': 'bi-basket',
                'color': '#2E7D32',
            },
            {
                'name': 'User Management',
                'url': reverse('admin_dashboard:users'),
                'icon': 'bi-people',
                'color': '#1B5E20',
            },
            {
                'name': 'Content Management',
                'url': reverse('admin_dashboard:content'),
                'icon': 'bi-window-stack',
                'color': '#1B5E20',
            },
            {
                'name': 'Orders',
                'url': reverse('admin_dashboard:orders'),
                'icon': 'bi-truck',
                'color': '#1B5E20',
            },
            {
                'name': 'Analytics',
                'url': reverse('farm_management:analytics'),
                'icon': 'bi-bar-chart-line',
                'color': '#1B5E20',
            },
            {
                'name': 'Supplier Directory',
                'url': reverse('farm_management:supplier_list'),
                'icon': 'bi-truck',
                'color': '#1B5E20',
            },
        ]

        return context


class PaymentsView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    """
    Comprehensive admin payment list with filtering, search, sorting,
    CSV export, pagination, and summary statistics.
    """
    model = Payment
    template_name = 'admin_dashboard/payments.html'
    context_object_name = 'payments'
    paginate_by = 25

    STATUS_CHOICES = [
        ('success', 'Successful'),
        ('pending', 'Pending'),
        ('failed', 'Failed'),
    ]

    METHOD_CHOICES = [
        ('paystack', 'Paystack'),
        ('bank_transfer', 'Bank Transfer'),
        ('cash_on_delivery', 'Cash on Delivery'),
    ]

    def get_queryset(self):
        qs = Payment.objects.select_related('order__user', 'order').all()

        # --- Search ---
        search = self.request.GET.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(order__user__full_name__icontains=search) |
                Q(order__user__username__icontains=search) |
                Q(order__user__email__icontains=search) |
                Q(order__pk__icontains=search) |
                Q(reference__icontains=search)
            )

        # --- Status filter ---
        status_filter = self.request.GET.get('status', '').strip()
        if status_filter and status_filter in dict(self.STATUS_CHOICES):
            qs = qs.filter(status=status_filter)

        # --- Payment method filter ---
        method_filter = self.request.GET.get('method', '').strip()
        if method_filter and method_filter in dict(self.METHOD_CHOICES):
            qs = qs.filter(order__payment_method=method_filter)

        # --- Date range filter ---
        date_range = self.request.GET.get('date_range', '').strip()
        custom_start = self.request.GET.get('start_date', '').strip()
        custom_end = self.request.GET.get('end_date', '').strip()

        now = timezone.now()
        if date_range == 'today':
            qs = qs.filter(created_at__date=now.date())
        elif date_range == 'week':
            week_start = now - timedelta(days=now.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            qs = qs.filter(created_at__gte=week_start)
        elif date_range == 'month':
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            qs = qs.filter(created_at__gte=month_start)
        elif date_range == 'custom' and custom_start:
            start_dt = datetime.strptime(custom_start, '%Y-%m-%d')
            qs = qs.filter(created_at__gte=start_dt)
            if custom_end:
                end_dt = datetime.strptime(custom_end, '%Y-%m-%d')
                end_dt = end_dt.replace(hour=23, minute=59, second=59)
                qs = qs.filter(created_at__lte=end_dt)

        # --- Sorting ---
        sort = self.request.GET.get('sort', '-created_at')
        if sort == 'amount_desc':
            qs = qs.order_by('-amount')
        elif sort == 'amount_asc':
            qs = qs.order_by('amount')
        elif sort == 'customer_asc':
            qs = qs.order_by('order__user__full_name')
        elif sort == 'customer_desc':
            qs = qs.order_by('-order__user__full_name')
        else:
            qs = qs.order_by('-created_at')

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Payments'

        # Preserve filter params for pagination
        params = self.request.GET.copy()
        context['query_params'] = params.urlencode()

        # Filter options
        context['status_choices'] = self.STATUS_CHOICES
        context['method_choices'] = self.METHOD_CHOICES
        context['status_filter'] = self.request.GET.get('status', '')
        context['method_filter'] = self.request.GET.get('method', '')
        context['date_range'] = self.request.GET.get('date_range', '')
        context['custom_start'] = self.request.GET.get('start_date', '')
        context['custom_end'] = self.request.GET.get('end_date', '')
        context['search_query'] = self.request.GET.get('search', '')
        context['current_sort'] = self.request.GET.get('sort', '-created_at')

        # Summary statistics
        all_payments = Payment.objects.select_related('order__user').all()
        context['total_payments'] = all_payments.count()
        context['total_amount'] = all_payments.aggregate(total=Sum('amount'))['total'] or 0
        context['successful_payments'] = all_payments.filter(status='success').count()
        context['failed_payments'] = all_payments.filter(status='failed').count()
        context['pending_payments'] = all_payments.filter(status='pending').count()

        return context

    def dispatch(self, request, *args, **kwargs):
        if request.GET.get('export') == 'csv':
            return self.export_csv()
        return super().dispatch(request, *args, **kwargs)

    def export_csv(self):
        qs = self.get_queryset()
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="payments_export.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Payment ID', 'Reference', 'Customer Name', 'Username', 'Email',
            'Order #', 'Amount (₦)', 'Payment Method', 'Status',
            'Transaction Reference', 'Date & Time', 'Order Status'
        ])

        method_display = dict(self.METHOD_CHOICES)
        for payment in qs:
            writer.writerow([
                payment.pk,
                f"#{payment.pk}",
                payment.order.user.full_name if payment.order and payment.order.user else 'Deleted User',
                payment.order.user.username if payment.order and payment.order.user else '',
                payment.order.user.email if payment.order and payment.order.user else '',
                payment.order.pk if payment.order else '',
                f"{payment.amount:.2f}",
                method_display.get(payment.order.payment_method, payment.order.payment_method) if payment.order else '',
                payment.get_status_display(),
                payment.reference,
                payment.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                payment.order.get_status_display() if payment.order else '',
            ])

        return response


class NotificationsView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    template_name = 'admin_dashboard/notifications.html'
    model = Notification
    context_object_name = 'notifications'
    paginate_by = 20

    def get_queryset(self):
        qs = Notification.objects.all()
        filter_type = self.request.GET.get('type')
        if filter_type:
            qs = qs.filter(notification_type=filter_type)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Notifications'
        context['filter_type'] = self.request.GET.get('type', 'all')
        context['notification_types'] = Notification.NOTIFICATION_TYPES
        context['unread_count'] = Notification.objects.filter(is_read=False).count()
        return context


class ContentManagementView(ContentManagementMixin, LoginRequiredMixin, ListView):
    """
    List view for managing website content sections.
    """
    template_name = 'admin_dashboard/content.html'
    model = SiteContent
    context_object_name = 'content_sections'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Website Content Management'
        return context


class ContentEditView(ContentManagementMixin, LoginRequiredMixin, UpdateView):
    """
    Edit view for updating website content sections.
    """
    template_name = 'admin_dashboard/content_form.html'
    model = SiteContent
    form_class = SiteContentForm
    success_url = reverse_lazy('admin_dashboard:content')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Edit {self.object.get_section_display()}'
        context['form_action'] = 'Edit'
        context['days'] = [
            'monday', 'tuesday', 'wednesday', 'thursday',
            'friday', 'saturday', 'sunday',
        ]
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        log_audit(self.request, 'update', 'SiteContent', self.object.pk, f'Updated content section {self.object.get_section_display()}')
        messages.success(self.request, f'{form.instance.get_section_display()} has been updated successfully.')
        return response


class ContentCreateView(ContentManagementMixin, LoginRequiredMixin, CreateView):
    """
    Create view for adding new website content sections.
    """
    template_name = 'admin_dashboard/content_form.html'
    model = SiteContent
    form_class = SiteContentForm
    success_url = reverse_lazy('admin_dashboard:content')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Content Section'
        context['form_action'] = 'Create'
        context['days'] = [
            'monday', 'tuesday', 'wednesday', 'thursday',
            'friday', 'saturday', 'sunday',
        ]
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        log_audit(self.request, 'create', 'SiteContent', self.object.pk, f'Created content section {self.object.get_section_display()}')
        messages.success(self.request, f'{form.instance.get_section_display()} has been created successfully.')
        return response


class UserManagementView(SuperAdminRequiredMixin, LoginRequiredMixin, ListView):
    """
    User management list view with search and filter capabilities.
    """
    template_name = 'admin_dashboard/users.html'
    model = User
    context_object_name = 'users'
    paginate_by = 20

    def get_queryset(self):
        """
        Get filtered and searched user list.
        """
        qs = User.objects.all().annotate(
            order_count=Count('orders'),
            total_spent=Sum('orders__total')
        )
        
        # Search by name or email
        search_query = self.request.GET.get('search', '').strip()
        if search_query:
            qs = qs.filter(
                Q(full_name__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(username__icontains=search_query)
            )
        
        # Filter by role
        role_filter = self.request.GET.get('role', '')
        if role_filter and role_filter in dict(User.Role.choices):
            qs = qs.filter(role=role_filter)
        
        # Filter by status
        status_filter = self.request.GET.get('status', '')
        if status_filter == 'active':
            qs = qs.filter(is_active=True)
        elif status_filter == 'inactive':
            qs = qs.filter(is_active=False)
        
        return qs.order_by('-date_joined')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'User Management'
        context['search_query'] = self.request.GET.get('search', '')
        context['role_filter'] = self.request.GET.get('role', '')
        context['status_filter'] = self.request.GET.get('status', '')
        context['user_roles'] = User.Role.choices
        context['total_users'] = User.objects.count()
        context['active_users'] = User.objects.filter(is_active=True).count()
        context['inactive_users'] = User.objects.filter(is_active=False).count()
        return context


class OrderListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    """
    Paginated list of all orders with status filtering.
    """
    template_name = 'admin_dashboard/orders.html'
    model = Order
    context_object_name = 'orders'
    paginate_by = 20

    def get_queryset(self):
        qs = Order.objects.select_related('user').all()
        status_filter = self.request.GET.get('status', '')
        if status_filter and status_filter in dict(Order.Status.choices):
            qs = qs.filter(status=status_filter)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Orders & Delivery'
        context['status_filter'] = self.request.GET.get('status', '')
        context['status_choices'] = Order.Status.choices
        context['total_orders'] = Order.objects.count()
        context['pending_count'] = Order.objects.filter(status=Order.Status.PENDING).count()
        context['confirmed_count'] = Order.objects.filter(status=Order.Status.CONFIRMED).count()
        context['processing_count'] = Order.objects.filter(status=Order.Status.PROCESSING).count()
        context['shipped_count'] = Order.objects.filter(status=Order.Status.SHIPPED).count()
        context['delivered_count'] = Order.objects.filter(status=Order.Status.DELIVERED).count()
        context['cancelled_count'] = Order.objects.filter(status=Order.Status.CANCELLED).count()
        return context


class OrderDetailView(AdminRequiredMixin, LoginRequiredMixin, DetailView):
    """
    Full order details with status update capability.
    """
    template_name = 'admin_dashboard/order_detail.html'
    model = Order
    context_object_name = 'order'
    pk_url_kwarg = 'pk'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        context['page_title'] = f'Order #{order.pk}'
        context['line_items'] = order.items.select_related('product').all()
        context['payments'] = order.payments.all()
        context['status_choices'] = Order.Status.choices
        context['can_update_status'] = order.status != Order.Status.DELIVERED and order.status != Order.Status.CANCELLED
        return context


@require_POST
def update_order_status(request, pk):
    """
    Update an order's status via AJAX.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False}, status=403)
    if request.user.role not in (
        request.user.Role.SUPER_ADMIN,
        request.user.Role.FARM_MANAGER,
    ):
        return JsonResponse({'success': False}, status=403)

    order = get_object_or_404(Order, pk=pk)
    new_status = request.POST.get('status', '')

    if new_status not in dict(Order.Status.choices):
        return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)

    if order.status == Order.Status.DELIVERED and new_status != Order.Status.DELIVERED:
        return JsonResponse({'success': False, 'error': 'Delivered orders cannot be changed'}, status=400)

    if order.status == Order.Status.CANCELLED and new_status != Order.Status.CANCELLED:
        return JsonResponse({'success': False, 'error': 'Cancelled orders cannot be changed'}, status=400)

    valid_transitions = {
        Order.Status.PENDING: [Order.Status.CONFIRMED, Order.Status.PROCESSING, Order.Status.CANCELLED],
        Order.Status.CONFIRMED: [Order.Status.PROCESSING, Order.Status.CANCELLED],
        Order.Status.PROCESSING: [Order.Status.AWAITING_DELIVERY, Order.Status.CANCELLED],
        Order.Status.AWAITING_DELIVERY: [Order.Status.SHIPPED, Order.Status.CANCELLED],
        Order.Status.SHIPPED: [Order.Status.DELIVERED, Order.Status.CANCELLED],
        Order.Status.DELIVERED: [],
        Order.Status.CANCELLED: [],
    }

    current = order.status
    if new_status not in valid_transitions.get(current, []):
        return JsonResponse({
            'success': False,
            'error': f'Cannot transition from {current} to {new_status}',
        }, status=400)

    order.status = new_status
    order.save(update_fields=['status'])
    log_audit(request, 'status_change', 'Order', order.pk, f'Changed order status from {current} to {new_status}')

    return JsonResponse({
        'success': True,
        'status': order.status,
        'status_display': order.get_status_display(),
    })


class InventoryView(AdminDashboardShell):
    template_name = 'admin_dashboard/inventory.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Products / Inventory'
        return context


class FarmManagementView(AdminDashboardShell):
    template_name = 'admin_dashboard/farm_management.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Farm Management'
        return context


class ReportsView(AdminDashboardShell):
    template_name = 'admin_dashboard/reports.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Reports'
        return context


class DeliverySettingsView(SuperAdminRequiredMixin, LoginRequiredMixin, TemplateView):
    """Configure the delivery choices presented during customer checkout."""

    template_name = "admin_dashboard/delivery_settings.html"
    defaults = (
        (DeliveryOption.Code.SAME_DAY, 1),
        (DeliveryOption.Code.STANDARD, 3),
        (DeliveryOption.Code.ECONOMY, 7),
    )

    def _options(self):
        for code, days in self.defaults:
            DeliveryOption.objects.get_or_create(
                code=code,
                defaults={"estimated_days": days},
            )
        return DeliveryOption.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Delivery Settings"
        context["options"] = self._options()
        context["forms"] = [
            (option, DeliveryOptionForm(prefix=str(option.pk), instance=option))
            for option in context["options"]
        ]
        return context

    def post(self, request, *args, **kwargs):
        options = self._options()
        forms = [
            (option, DeliveryOptionForm(request.POST, prefix=str(option.pk), instance=option))
            for option in options
        ]
        if all(form.is_valid() for _, form in forms):
            for _, form in forms:
                form.save()
            messages.success(request, "Delivery settings updated successfully.")
            return redirect("admin_dashboard:delivery_settings")
        context = self.get_context_data()
        context["forms"] = forms
        return self.render_to_response(context)


# ===== User Management Views =====

class UserDetailView(SuperAdminRequiredMixin, LoginRequiredMixin, DetailView):
    """
    Detailed view of a single user with their orders and payment history.
    """
    template_name = 'admin_dashboard/user_detail.html'
    model = User
    context_object_name = 'viewed_user'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.object
        
        # Get user's orders
        orders = user.orders.all().order_by('-created_at')
        
        # Get user's payments through their orders
        payments = Payment.objects.filter(order__user=user).order_by('-created_at')
        
        context['page_title'] = f'User: {user.full_name}'
        context['orders'] = orders
        context['payments'] = payments
        context['total_orders'] = orders.count()
        context['total_spent'] = sum(order.total for order in orders)
        context['can_delete'] = orders.count() == 0  # Can only delete if no order history
        return context


class UserCreateView(SuperAdminRequiredMixin, LoginRequiredMixin, CreateView):
    """
    Create a new user.
    """
    template_name = 'admin_dashboard/user_create.html'
    context_object_name = 'form'
    success_url = reverse_lazy('admin_dashboard:users')
    
    def get_form_class(self):
        from .forms import UserCreateForm
        return UserCreateForm
    
    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, f'User {self.object.full_name} ({self.object.email}) created successfully.')
        return HttpResponseRedirect(self.get_success_url())
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Create User'
        return context


class UserEditView(SuperAdminRequiredMixin, LoginRequiredMixin, UpdateView):
    """
    Edit an existing user.
    """
    template_name = 'admin_dashboard/user_edit.html'
    model = User
    form_class = UserEditForm
    context_object_name = 'viewed_user'
    
    def get_success_url(self):
        return reverse('admin_dashboard:user_detail', kwargs={'pk': self.object.pk})
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request_user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        log_audit(self.request, 'update', 'User', self.object.pk, f'Updated user {self.object.full_name} ({self.object.email})')
        messages.success(self.request, f'User {self.object.full_name} updated successfully.')
        return response
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Edit User: {self.object.full_name}'
        return context


class UserDeleteView(SuperAdminRequiredMixin, LoginRequiredMixin, DeleteView):
    """
    Delete a user (only if they have no order history).
    """
    template_name = 'admin_dashboard/user_confirm_delete.html'
    model = User
    context_object_name = 'viewed_user'
    success_url = reverse_lazy('admin_dashboard:users')
    
    def get_queryset(self):
        return super().get_queryset()
    
    def post(self, request, *args, **kwargs):
        user = self.get_object()
        if user == request.user:
            messages.error(request, 'You cannot delete your own account.')
            return redirect(self.success_url)
        if user.orders.exists():
            messages.error(request, f'User {user.full_name} ({user.email}) has order history and cannot be deleted.')
            return redirect(self.success_url)
        response = super().post(request, *args, **kwargs)
        log_audit(request, 'delete', 'User', user.pk, f'Deleted user {user.full_name} ({user.email})')
        messages.success(request, f'User {user.full_name} ({user.email}) deleted successfully.')
        return response
    
    def delete(self, request, *args, **kwargs):
        user = self.get_object()
        if user == request.user:
            messages.error(request, 'You cannot delete your own account.')
            return redirect(self.success_url)
        if user.orders.exists():
            messages.error(request, f'User {user.full_name} ({user.email}) has order history and cannot be deleted.')
            return redirect(self.success_url)
        messages.success(request, f'User {user.full_name} ({user.email}) deleted successfully.')
        return super().delete(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Delete User: {self.object.full_name}'
        return context


@require_POST
def toggle_user_active(request, pk):
    """
    Toggle a user's active status via AJAX.
    Only Super Admin can toggle user active status.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False}, status=403)
    if request.user.role != User.Role.SUPER_ADMIN:
        return JsonResponse({'success': False}, status=403)
    
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        return JsonResponse({'success': False, 'error': 'You cannot deactivate your own account.'}, status=400)
    user.is_active = not user.is_active
    user.save()
    log_audit(request, 'toggle', 'User', user.pk, f'Set user {user.full_name} active={user.is_active}')
    
    return JsonResponse({
        'success': True,
        'is_active': user.is_active
    })


@require_POST
def mark_notification_read(request, pk):
    """
    Mark a notification as read via AJAX.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False}, status=403)
    if request.user.role not in (
        request.user.Role.SUPER_ADMIN,
        request.user.Role.FARM_MANAGER,
    ):
        return JsonResponse({'success': False}, status=403)
    
    notification = get_object_or_404(Notification, pk=pk)
    notification.is_read = True
    notification.save()
    
    return JsonResponse({
        'success': True,
        'unread_count': Notification.objects.filter(is_read=False).count(),
    })


@require_POST
def mark_all_read(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False}, status=403)
    if request.user.role not in (
        request.user.Role.SUPER_ADMIN,
        request.user.Role.FARM_MANAGER,
    ):
        return JsonResponse({'success': False}, status=403)
    updated_count = Notification.objects.filter(is_read=False).update(is_read=True)
    return JsonResponse({
        'success': True,
        'marked_read': updated_count,
        'unread_count': Notification.objects.filter(is_read=False).count(),
    })


@require_POST
def force_password_reset(request, pk):
    """
    Force a password reset for a user by generating a secure temporary password.
    Only available to Super Admin and Farm Manager roles.
    Logs the action in the audit log.
    The temporary password is shown to the admin ONE TIME via messages.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=403)
    if request.user.role not in (
        request.user.Role.SUPER_ADMIN,
        request.user.Role.FARM_MANAGER,
    ):
        return JsonResponse({'success': False, 'error': 'Insufficient permissions'}, status=403)

    target_user = get_object_or_404(User, pk=pk)
    if target_user == request.user:
        return JsonResponse({'success': False, 'error': 'You cannot reset your own password using this tool.'}, status=400)

    temp_password = secrets.token_urlsafe(10)
    target_user.set_password(temp_password)
    target_user.must_change_password = True
    target_user.save(update_fields=['password', 'must_change_password'])

    log_audit(
        request,
        'force_password_reset',
        'User',
        target_user.pk,
        f'Forced password reset for {target_user.full_name} ({target_user.email})',
    )

    messages.success(
        request,
        f'Password reset for {target_user.full_name}. '
        f'Temporary password: <code style="user-select: all;">{temp_password}</code> '
        f'— share this with the user directly. It will not be shown again.',
    )
    return redirect('admin_dashboard:user_detail', pk=target_user.pk)


# =============================================================================
# Staff Management Views
# =============================================================================

class StaffManagementView(StaffManagementMixin, LoginRequiredMixin, ListView):
    """
    List all Staff and Super Staff accounts.
    Super Admin sees all STAFF and SUPER_STAFF users.
    Super Staff sees only regular STAFF users.
    """
    template_name = 'admin_dashboard/staff_management.html'
    model = User
    context_object_name = 'staff_members'
    paginate_by = 20

    def get_queryset(self):
        qs = User.objects.select_related().all()
        if self.request.user.role == User.Role.SUPER_STAFF:
            qs = qs.filter(role=User.Role.STAFF)
        else:
            qs = qs.filter(role__in=[User.Role.STAFF, User.Role.SUPER_STAFF])
        return qs.order_by('-date_joined')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Staff Management'
        context['is_super_admin'] = self.request.user.role == User.Role.SUPER_ADMIN
        context['total_staff'] = self.get_queryset().count()
        context['active_staff'] = self.get_queryset().filter(is_active=True).count()
        context['inactive_staff'] = self.get_queryset().filter(is_active=False).count()
        return context


class StaffCreateView(StaffManagementMixin, LoginRequiredMixin, CreateView):
    """
    Create a new Staff or Super Staff account.
    Super Admin can create both STAFF and SUPER_STAFF.
    Super Staff can only create STAFF accounts.
    """
    template_name = 'admin_dashboard/staff_form.html'
    form_class = StaffCreateForm
    success_url = reverse_lazy('admin_dashboard:staff_management')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request_user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        self.object = form.save()
        log_audit(self.request, 'create', 'User', self.object.pk, 
                  f'Created staff account: {self.object.full_name} ({self.object.email}) with role {self.object.get_role_display()}')
        messages.success(self.request, f'Staff account created: {self.object.full_name} ({self.object.email})')
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Staff Member'
        context['is_super_admin'] = self.request.user.role == User.Role.SUPER_ADMIN
        return context


class StaffEditView(StaffManagementMixin, LoginRequiredMixin, UpdateView):
    """
    Edit an existing Staff or Super Staff account.
    Super Admin can edit any staff account.
    Super Staff can only edit regular Staff accounts.
    """
    template_name = 'admin_dashboard/staff_form.html'
    model = User
    form_class = StaffEditForm
    context_object_name = 'viewed_user'

    def get_queryset(self):
        qs = User.objects.select_related().all()
        if self.request.user.role == User.Role.SUPER_STAFF:
            qs = qs.filter(role=User.Role.STAFF)
        else:
            qs = qs.filter(role__in=[User.Role.STAFF, User.Role.SUPER_STAFF])
        return qs

    def get_success_url(self):
        return reverse('admin_dashboard:staff_management')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request_user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        log_audit(self.request, 'update', 'User', self.object.pk, 
                  f'Updated staff account: {self.object.full_name} ({self.object.email}) role={self.object.get_role_display()}')
        messages.success(self.request, f'Staff account updated: {self.object.full_name}')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Edit Staff: {self.object.full_name}'
        context['is_super_admin'] = self.request.user.role == User.Role.SUPER_ADMIN
        return context


@require_POST
def deactivate_staff(request, pk):
    """
    Deactivate a staff account (soft disable).
    Super Admin can deactivate any staff.
    Super Staff can only deactivate regular Staff.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=403)
    if request.user.role not in (User.Role.SUPER_ADMIN, User.Role.SUPER_STAFF):
        return JsonResponse({'success': False, 'error': 'Insufficient permissions'}, status=403)

    target_user = get_object_or_404(User, pk=pk)
    
    # Super Staff cannot deactivate Super Staff or Super Admin
    if request.user.role == User.Role.SUPER_STAFF:
        if target_user.role in (User.Role.SUPER_STAFF, User.Role.SUPER_ADMIN):
            return JsonResponse({'success': False, 'error': 'You cannot deactivate this user.'}, status=403)
    
    # Cannot deactivate self
    if target_user == request.user:
        return JsonResponse({'success': False, 'error': 'You cannot deactivate your own account.'}, status=400)
    
    # Check if user has orders (similar to delete protection)
    if target_user.orders.exists():
        return JsonResponse({'success': False, 'error': 'Cannot deactivate user with order history. Please contact support.'}, status=400)

    target_user.is_active = not target_user.is_active
    target_user.save()
    
    action = 'activate' if target_user.is_active else 'deactivate'
    log_audit(request, action, 'User', target_user.pk, 
              f'{action.capitalize()}d staff account: {target_user.full_name} ({target_user.email})')
    
    return JsonResponse({
        'success': True,
        'is_active': target_user.is_active,
        'message': f'Staff account {action}d successfully.'
    })


# =============================================================================
# Product / Inventory Management Views
# =============================================================================

class ProductListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    template_name = 'admin_dashboard/product_list.html'
    model = Product
    context_object_name = 'products'
    paginate_by = 20

    def get_queryset(self):
        qs = Product.objects.select_related('category').all()
        category_filter = self.request.GET.get('category', '')
        if category_filter:
            qs = qs.filter(category__slug=category_filter)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Products / Inventory'
        context['categories'] = Category.objects.annotate(
            product_count=Count('products')
        ).order_by('name')
        context['selected_category'] = self.request.GET.get('category', '')
        context['total_products'] = Product.objects.count()
        context['total_categories'] = Category.objects.count()
        context['is_super_admin'] = self.request.user.role == User.Role.SUPER_ADMIN
        return context


class CategoryListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    template_name = 'admin_dashboard/category_list.html'
    model = Category
    context_object_name = 'categories'
    paginate_by = 20

    def get_queryset(self):
        return Category.objects.annotate(
            product_count=Count('products')
        ).order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Manage Categories'
        context['total_categories'] = Category.objects.count()
        return context


class CategoryCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = 'admin_dashboard/category_form.html'
    model = Category
    form_class = CategoryForm

    def get_success_url(self):
        log_audit(self.request, 'create', 'Category', self.object.pk, f'Created category "{self.object.name}"')
        messages.success(self.request, f'Category "{self.object.name}" created successfully.')
        return reverse('admin_dashboard:product_categories')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Category'
        return context


class CategoryUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = 'admin_dashboard/category_form.html'
    model = Category
    form_class = CategoryForm

    def get_success_url(self):
        log_audit(self.request, 'update', 'Category', self.object.pk, f'Updated category "{self.object.name}"')
        messages.success(self.request, f'Category "{self.object.name}" updated successfully.')
        return reverse('admin_dashboard:product_categories')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Edit Category: {self.object.name}'
        return context


class CategoryDeleteView(AdminRequiredMixin, LoginRequiredMixin, DeleteView):
    template_name = 'admin_dashboard/category_confirm_delete.html'
    model = Category
    context_object_name = 'category'
    success_url = reverse_lazy('admin_dashboard:product_categories')

    def delete(self, request, *args, **kwargs):
        category = self.get_object()
        log_audit(request, 'delete', 'Category', category.pk, f'Deleted category "{category.name}"')
        messages.success(request, f'Category "{category.name}" deleted successfully.')
        return super().delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Delete Category: {self.object.name}'
        return context


class ProductCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    template_name = 'admin_dashboard/product_form.html'
    model = Product
    form_class = ProductForm

    def get_success_url(self):
        log_audit(self.request, 'create', 'Product', self.object.pk, f'Created product "{self.object.name}"')
        messages.success(self.request, f'Product "{self.object.name}" created successfully.')
        return reverse('admin_dashboard:product_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Add Product'
        return context


class ProductUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    template_name = 'admin_dashboard/product_form.html'
    model = Product
    form_class = ProductForm

    def get_success_url(self):
        log_audit(self.request, 'update', 'Product', self.object.pk, f'Updated product "{self.object.name}"')
        messages.success(self.request, f'Product "{self.object.name}" updated successfully.')
        return reverse('admin_dashboard:product_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Edit Product: {self.object.name}'
        return context


class ProductDeleteView(AdminRequiredMixin, LoginRequiredMixin, DeleteView):
    template_name = 'admin_dashboard/product_confirm_delete.html'
    model = Product
    context_object_name = 'product'
    success_url = reverse_lazy('admin_dashboard:product_list')

    def delete(self, request, *args, **kwargs):
        product = self.get_object()
        log_audit(request, 'delete', 'Product', product.pk, f'Deleted product "{product.name}"')
        messages.success(request, f'Product "{product.name}" deleted.')
        return super().delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Delete Product: {self.object.name}'
        return context


# =============================================================================
# Sample Data Management Views
# =============================================================================

@require_POST
def populate_sample_data(request):
    """
    Populate database with sample products and categories.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False}, status=403)
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, 'Only Super Admins can populate sample data.')
        return JsonResponse({'success': False, 'error': 'Only Super Admins can populate sample data.'}, status=403)

    sample_categories = [
        {"name": "Vegetables", "description": "Fresh farm vegetables"},
        {"name": "Fruits", "description": "Seasonal fresh fruits"},
        {"name": "Grains", "description": "Rice, maize, and other grains"},
    ]

    sample_products = [
        {"name": "Fresh Tomatoes", "category": "Vegetables", "price": 1200, "stock_quantity": 50},
        {"name": "Fresh Pepper", "category": "Vegetables", "price": 800, "stock_quantity": 40},
        {"name": "Fresh Okra", "category": "Vegetables", "price": 600, "stock_quantity": 30},
        {"name": "Mango", "category": "Fruits", "price": 1500, "stock_quantity": 25},
        {"name": "Orange", "category": "Fruits", "price": 1000, "stock_quantity": 35},
        {"name": "Banana", "category": "Fruits", "price": 700, "stock_quantity": 45},
        {"name": "Rice (50kg)", "category": "Grains", "price": 45000, "stock_quantity": 20},
        {"name": "Maize (100kg)", "category": "Grains", "price": 38000, "stock_quantity": 15},
    ]

    category_map = {}
    for cat_data in sample_categories:
        cat, created = Category.objects.get_or_create(
            name=cat_data["name"],
            defaults={"description": cat_data["description"], "is_sample_data": True},
        )
        category_map[cat_data["name"]] = cat

    categories_count = 0
    products_count = 0
    for prod_data in sample_products:
        cat = category_map[prod_data["category"]]
        product, created = Product.objects.get_or_create(
            name=prod_data["name"],
            defaults={
                "category": cat,
                "price": prod_data["price"],
                "stock_quantity": prod_data["stock_quantity"],
                "is_sample_data": True,
            },
        )
        if created:
            products_count += 1

    categories_count = Category.objects.filter(is_sample_data=True).count()

    messages.success(request, f'Sample data populated: {categories_count} categories and {products_count} products created.')

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'categories_created': categories_count,
            'products_created': products_count,
            'message': f'Sample data populated: {categories_count} categories and {products_count} products created.',
        })

    return redirect('admin_dashboard:product_list')


@require_POST
def delete_sample_data(request):
    """
    Delete all sample data (products and categories marked as sample).
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False}, status=403)
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, 'Only Super Admins can delete sample data.')
        return JsonResponse({'success': False, 'error': 'Only Super Admins can delete sample data.'}, status=403)

    # Delete sample products
    deleted_products, _ = Product.objects.filter(is_sample_data=True).delete()
    
    # Delete sample categories
    deleted_categories, _ = Category.objects.filter(is_sample_data=True).delete()

    messages.success(request, f'Sample data deleted: {deleted_categories} categories and {deleted_products} products removed.')
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'categories_deleted': deleted_categories,
            'products_deleted': deleted_products,
            'message': f'Sample data deleted: {deleted_categories} categories and {deleted_products} products removed.',
        })
    return redirect('admin_dashboard:product_list')


@require_POST
def populate_site_sample_data(request):
    """
    Populate the entire site with sample data via management command.
    Restricted to Super Admin only.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False}, status=403)
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, 'Only Super Admins can populate sample data.')
        return JsonResponse({'success': False, 'error': 'Only Super Admins can populate sample data.'}, status=403)

    from django.core.management import call_command
    from io import StringIO
    output = StringIO()
    call_command('populate_sample', stdout=output)
    output_text = output.getvalue()
    messages.success(request, 'Full site sample data populated successfully.')
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': 'Full site sample data populated successfully.',
            'output': output_text,
        })
    return redirect('admin_dashboard:content')


@require_POST
def delete_site_sample_data(request):
    """
    Delete all sample data across the entire site via management command.
    Restricted to Super Admin only.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False}, status=403)
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, 'Only Super Admins can delete sample data.')
        return JsonResponse({'success': False, 'error': 'Only Super Admins can delete sample data.'}, status=403)

    from django.core.management import call_command
    from io import StringIO
    output = StringIO()
    call_command('delete_sample', stdout=output)
    output_text = output.getvalue()
    messages.success(request, 'All sample data deleted successfully.')
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': 'All sample data deleted successfully.',
            'output': output_text,
        })
    return redirect('admin_dashboard:content')


# =============================================================================
# Checkout Enforcement Views
# =============================================================================

class PaymentMethodSettingsView(SuperAdminRequiredMixin, LoginRequiredMixin, ListView):
    """
    List view for managing payment method settings.
    """
    template_name = 'admin_dashboard/payment_method_settings.html'
    model = None  # Set in get_queryset
    context_object_name = 'payment_methods'

    def get_queryset(self):
        # Ensure all payment methods have a setting entry
        for method, label in PaymentMethodSetting.PAYMENT_METHOD_CHOICES:
            PaymentMethodSetting.objects.get_or_create(
                payment_method=method,
                defaults={'enabled': True}
            )
        return PaymentMethodSetting.objects.all().order_by('payment_method')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Payment Method Settings'
        return context


class MinimumOrderAmountView(SuperAdminRequiredMixin, LoginRequiredMixin, TemplateView):
    """
    View for managing minimum order amount setting (singleton).
    """
    template_name = 'admin_dashboard/minimum_order_amount.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Minimum Order Amount'
        context['min_order'] = MinimumOrderAmount.get_instance()
        return context


@require_POST
def toggle_payment_method(request, pk):
    """
    Toggle a payment method's enabled status.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=403)
    if request.user.role != request.user.Role.SUPER_ADMIN:
        return JsonResponse({'success': False, 'error': 'Insufficient permissions'}, status=403)
    
    try:
        setting = get_object_or_404(PaymentMethodSetting, pk=pk)
        setting.enabled = not setting.enabled
        setting.save()
        status_text = "enabled" if setting.enabled else "disabled"
        log_audit(request, 'toggle', 'PaymentMethodSetting', setting.pk, f'{setting.get_payment_method_display()} {status_text}')
        messages.success(request, f'{setting.get_payment_method_display()} has been {status_text}.')
        return JsonResponse({'success': True, 'enabled': setting.enabled})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@require_POST
def update_minimum_order_amount(request):
    """
    Update the minimum order amount setting.
    """
    import json
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=403)
    if request.user.role != request.user.Role.SUPER_ADMIN:
        return JsonResponse({'success': False, 'error': 'Insufficient permissions'}, status=403)
    
    try:
        data = json.loads(request.body)
        min_order = MinimumOrderAmount.get_instance()
        
        if 'minimum_amount' in data:
            min_order.minimum_amount = data['minimum_amount']
        if 'enabled' in data:
            min_order.enabled = data['enabled']
        
        min_order.save()
        log_audit(request, 'update', 'MinimumOrderAmount', min_order.pk, f'Updated minimum order amount to {min_order.minimum_amount} (enabled={min_order.enabled})')
        messages.success(request, 'Minimum order amount updated successfully.')
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_audit(request, action, target_model, target_id, details=''):
    if not request.user.is_authenticated:
        return
    AuditLogEntry.objects.create(
        actor=request.user,
        action=action,
        target_model=target_model,
        target_id=target_id,
        details=details,
        ip_address=get_client_ip(request),
    )


class AuditLogView(SuperAdminRequiredMixin, LoginRequiredMixin, ListView):
    template_name = 'admin_dashboard/audit_log.html'
    model = AuditLogEntry
    context_object_name = 'audit_logs'
    paginate_by = 50

    def get_queryset(self):
        qs = AuditLogEntry.objects.select_related('actor').all()
        action_filter = self.request.GET.get('action', '')
        if action_filter and action_filter in dict(AuditLogEntry.ACTION_CHOICES):
            qs = qs.filter(action=action_filter)
        actor_filter = self.request.GET.get('actor', '')
        if actor_filter:
            qs = qs.filter(actor__full_name__icontains=actor_filter)
        return qs.order_by('-timestamp')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Activity Timeline'
        context['action_choices'] = AuditLogEntry.ACTION_CHOICES
        context['action_filter'] = self.request.GET.get('action', '')
        context['actor_filter'] = self.request.GET.get('actor', '')
        from django.contrib.auth import get_user_model
        User = get_user_model()
        context['staff_users'] = User.objects.filter(
            role__in=(User.Role.SUPER_ADMIN, User.Role.SUPER_STAFF, User.Role.FARM_MANAGER, User.Role.STAFF)
        ).order_by('full_name')
        return context


class WebsiteContentHubView(AdminDashboardShell):
    template_name = 'admin_dashboard/website_content_hub.html'


class ShopOrdersHubView(AdminDashboardShell):
    template_name = 'admin_dashboard/shop_orders_hub.html'
