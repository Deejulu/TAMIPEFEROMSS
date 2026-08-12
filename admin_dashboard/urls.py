from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = 'admin_dashboard'

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='admin_dashboard:overview', permanent=False), name='index'),
    path('overview/', views.OverviewView.as_view(), name='overview'),
    path('payments/', views.PaymentsView.as_view(), name='payments'),
    path('notifications/', views.NotificationsView.as_view(), name='notifications'),
    path('notifications/<int:pk>/mark-read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_read, name='mark_all_read'),
    path('content/', views.ContentManagementView.as_view(), name='content'),
    path('content/create/', views.ContentCreateView.as_view(), name='content_create'),
    path('content/<int:pk>/edit/', views.ContentEditView.as_view(), name='content_edit'),
    path('content/delivery-settings/', views.DeliverySettingsView.as_view(), name='delivery_settings'),
    
    # User Management URLs
    path('users/', views.UserManagementView.as_view(), name='users'),
    path('users/create/', views.UserCreateView.as_view(), name='user_create'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user_detail'),
    path('users/<int:pk>/edit/', views.UserEditView.as_view(), name='user_edit'),
    path('users/<int:pk>/delete/', views.UserDeleteView.as_view(), name='user_delete'),
    path('users/<int:pk>/toggle-active/', views.toggle_user_active, name='toggle_user_active'),
    path('users/<int:pk>/force-password-reset/', views.force_password_reset, name='force_password_reset'),
    
    # Staff Management URLs
    path('staff-management/', views.StaffManagementView.as_view(), name='staff_management'),
    path('staff-management/create/', views.StaffCreateView.as_view(), name='staff_create'),
    path('staff-management/<int:pk>/edit/', views.StaffEditView.as_view(), name='staff_edit'),
    path('staff-management/<int:pk>/deactivate/', views.deactivate_staff, name='staff_deactivate'),
    
    path('orders/', views.OrderListView.as_view(), name='orders'),
    path('orders/<int:pk>/', views.OrderDetailView.as_view(), name='order_detail'),
    path('orders/<int:pk>/update-status/', views.update_order_status, name='update_order_status'),
    path('inventory/', views.ProductListView.as_view(), name='inventory'),
    path('products/', views.ProductListView.as_view(), name='product_list'),
    path('products/categories/', views.CategoryListView.as_view(), name='product_categories'),
    path('products/categories/add/', views.CategoryCreateView.as_view(), name='product_category_add'),
    path('products/categories/<int:pk>/edit/', views.CategoryUpdateView.as_view(), name='product_category_edit'),
    path('products/categories/<int:pk>/delete/', views.CategoryDeleteView.as_view(), name='product_category_delete'),
    path('products/add/', views.ProductCreateView.as_view(), name='product_add'),
    path('products/<int:pk>/edit/', views.ProductUpdateView.as_view(), name='product_edit'),
    path('products/<int:pk>/delete/', views.ProductDeleteView.as_view(), name='product_delete'),
    path('products/populate-sample-data/', views.populate_sample_data, name='populate_sample_data'),
    path('products/delete-sample-data/', views.delete_sample_data, name='delete_sample_data'),
    path('content/populate-sample-data/', views.populate_site_sample_data, name='content_populate_sample_data'),
    path('content/delete-sample-data/', views.delete_site_sample_data, name='content_delete_sample_data'),
    
    # Checkout Enforcement URLs
    path('payment-methods/', views.PaymentMethodSettingsView.as_view(), name='payment_methods'),
    path('payment-methods/<int:pk>/toggle/', views.toggle_payment_method, name='toggle_payment_method'),
    path('minimum-order-amount/', views.MinimumOrderAmountView.as_view(), name='minimum_order_amount'),
    path('minimum-order-amount/update/', views.update_minimum_order_amount, name='update_minimum_order_amount'),
    
    path('farm-management/', views.FarmManagementView.as_view(), name='farm_management'),
    path('reports/', views.ReportsView.as_view(), name='reports'),
    path('audit-log/', views.AuditLogView.as_view(), name='audit_log'),
    path('website-content/', views.WebsiteContentHubView.as_view(), name='website_content'),
    path('shop-orders/', views.ShopOrdersHubView.as_view(), name='shop_orders'),
]
