from .analytics_dashboard_views import analytics_dashboard_page
from django.urls import path
from .storefront_views import (
    home,
    product_detail,
    login_page,
    register_page,
    checkout_page,
    cart_page,
    my_orders_page,
    my_addresses_page,
    wishlist_page,
    order_confirmation_page,
)

app_name = "storefront"

urlpatterns = [
    path('admin/analytics-dashboard/', analytics_dashboard_page, name='analytics_dashboard'),
    path("", home, name="home"),
    path("login/", login_page, name="login"),
    path("register/", register_page, name="register"),
    path("products/<int:product_id>/", product_detail, name="product_detail"),
    path("cart/", cart_page, name="cart"),
    path("checkout/", checkout_page, name="checkout"),
    path("my-orders/", my_orders_page, name="my_orders"),
    path("my-addresses/", my_addresses_page, name="my_addresses"),
    path("wishlist/", wishlist_page, name="wishlist"),
    path("order-confirmation/", order_confirmation_page, name="order_confirmation"),
]




