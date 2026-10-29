from django.urls import resolve

paths = [
    "/", "/login/", "/cart/", "/checkout/",
    "/api/cart/", "/api/cart/add/",
    "/api/cart/update/", "/api/cart/remove/",
    "/api/cart/coupon/", "/api/coupons/validate/",
    "/api/checkout/summary/", "/api/checkout/shipping-options/",
    "/api/orders/", "/api/payment/create/", "/api/payment/verify/",
    "/api/addresses/",
]

for path in paths:
    try:
        match = resolve(path)
        print("OK:", path, "->", match.func)
    except Exception as error:
        print("MISSING:", path, "->", type(error).__name__)
