from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import CheckoutSummaryView, OrderViewSet, ShippingOptionsView
from .views_returns import ReturnViewSet

router = SimpleRouter()
router.register("orders", OrderViewSet, basename="order")
router.register("returns", ReturnViewSet, basename="return")

urlpatterns = [
    path("checkout/shipping-options/", ShippingOptionsView.as_view(), name="shipping-options"),
    path("checkout/summary/", CheckoutSummaryView.as_view(), name="checkout-summary"),
] + router.urls
