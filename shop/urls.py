from django.urls import path
from . import views

app_name = "shop"

urlpatterns = [
    path("", views.product_list, name="product_list"),
    path("cart/", views.cart_view, name="cart"),
    path("add/<int:product_id>/", views.add_to_cart, name="add_to_cart"),
    path("remove/<int:item_id>/", views.remove_from_cart, name="remove_from_cart"),
    path("update/<int:item_id>/", views.update_cart_item, name="update_cart_item"),
    path("checkout/", views.checkout, name="checkout"),
    path("paystack-callback/", views.paystack_callback, name="paystack_callback"),
    path("about/", views.about_page, name="about"),
    path("contact/", views.contact_page, name="contact"),
    path("faq/", views.faq_page, name="faq"),
    path("delivery/", views.delivery_info_page, name="delivery_info"),
    path("terms/", views.terms_privacy_page, name="terms_privacy"),
    path("returns/", views.return_refund_page, name="return_refund"),
]
