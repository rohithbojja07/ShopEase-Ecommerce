from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import AddressViewSet, ChangePasswordView, LogoutView, MeView
from .views_email import (
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
    SendVerificationEmailView,
    VerifyEmailView,
)

router = SimpleRouter()
router.register("addresses", AddressViewSet, basename="address")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/profile/", MeView.as_view(), name="profile"),
    path("auth/change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("auth/password-reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path("auth/password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("auth/verify-email/send/", SendVerificationEmailView.as_view(), name="verify-email-send"),
    path("auth/verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("", include(router.urls)),
]
