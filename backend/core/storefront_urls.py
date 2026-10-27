from django.urls import path

from .storefront_views import home

app_name = "storefront"

urlpatterns = [
    path("", home, name="home"),
]
