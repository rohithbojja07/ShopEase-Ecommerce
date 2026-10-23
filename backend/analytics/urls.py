from django.urls import path

from .views import (
    DashboardView,
    OrderStatusAnalyticsView,
    SalesAnalyticsView,
    TopProductsView,
)

urlpatterns = [
    path("analytics/dashboard/", DashboardView.as_view(), name="analytics-dashboard"),
    path("analytics/sales/", SalesAnalyticsView.as_view(), name="analytics-sales"),
    path("analytics/top-products/", TopProductsView.as_view(), name="analytics-top-products"),
    path("analytics/order-status/", OrderStatusAnalyticsView.as_view(), name="analytics-order-status"),
]
