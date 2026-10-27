from django.shortcuts import render

from products.views import active_products


def home(request):
    products = active_products()[:12]
    return render(request, "storefront/home.html", {"products": products})
