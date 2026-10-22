from django.urls import path

from .views import PaymentCreateView, PaymentVerifyView

urlpatterns = [
    path("payment/create/", PaymentCreateView.as_view(), name="payment-create"),
    path("payment/verify/", PaymentVerifyView.as_view(), name="payment-verify"),
]
