from django.urls import path

from core import staff_views

app_name = "staff_portal"

urlpatterns = [
    path("login/", staff_views.staff_login, name="login"),
    path("logout/", staff_views.staff_logout, name="logout"),
    path("", staff_views.dashboard, name="dashboard"),
    path("products/", staff_views.products_page, name="products"),
    path("inventory/", staff_views.inventory_page, name="inventory"),
    path("orders/", staff_views.orders_page, name="orders"),
    path("customers/", staff_views.customers_page, name="customers"),
    path("returns/", staff_views.returns_page, name="returns"),
    path("audit-logs/", staff_views.audit_logs_page, name="audit_logs"),
]
