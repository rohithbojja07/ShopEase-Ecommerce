from django.shortcuts import render


def cart_page(request):
    return render(request, "storefront/cart.html")
