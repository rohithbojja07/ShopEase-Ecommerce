from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    AddressViewSet,
    ChangePasswordView,
    LogoutView,
    MeView,
    RegisterView,
)

router = SimpleRouter()
router.register("addresses", AddressViewSet, basename="address")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/profile/", MeView.as_view(), name="profile"),
    path("auth/change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("", include(router.urls)),
]
