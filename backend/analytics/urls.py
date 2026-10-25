from django.urls import path

from .views import (
    CustomersAnalyticsView,
    DashboardView,
    OrderStatusAnalyticsView,
    ProductsAnalyticsView,
    SalesAnalyticsView,
    TopProductsView,
)

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="analytics-dashboard"),
    path("sales/", SalesAnalyticsView.as_view(), name="analytics-sales"),
    path("products/", ProductsAnalyticsView.as_view(), name="analytics-products"),
    path("customers/", CustomersAnalyticsView.as_view(), name="analytics-customers"),
    path("top-products/", TopProductsView.as_view(), name="analytics-top-products"),
    path("order-status/", OrderStatusAnalyticsView.as_view(), name="analytics-order-status"),
]
