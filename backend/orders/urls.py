from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import CheckoutSummaryView, OrderViewSet, ShippingOptionsView

router = SimpleRouter()
router.register("orders", OrderViewSet, basename="order")

urlpatterns = [
    path("checkout/shipping-options/", ShippingOptionsView.as_view(), name="shipping-options"),
    path("checkout/summary/", CheckoutSummaryView.as_view(), name="checkout-summary"),
] + router.urls
