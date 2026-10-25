from django.contrib.auth.models import Permission

SUPER_ADMIN = "Super Admin"
PRODUCT_MANAGER = "Product Manager"
ORDER_MANAGER = "Order Manager"
INVENTORY_MANAGER = "Inventory Manager"
CUSTOMER_SUPPORT = "Customer Support"
ROLES = [SUPER_ADMIN, PRODUCT_MANAGER, ORDER_MANAGER, INVENTORY_MANAGER, CUSTOMER_SUPPORT]


def _p(app, models, actions="view"):
    return [f"{app}.{action}_{model}" for model in models.split() for action in actions.split()]


CATALOG = "category subcategory brand product productvariant productimage"
RETURNS = "returnrequest returnitem returnevidence returnevent"

# Super Admin gets every permission. Nobody else can delete anything.
ROLE_PERMISSIONS = {
    PRODUCT_MANAGER: (
        _p("products", CATALOG, "view add change")
        + _p("inventory", "inventory")
        + _p("coupons", "coupon", "view add change")
        + _p("coupons", "couponusage")
        + _p("reviews", "review reviewimage")
        + ["analytics.view_product_analytics"]
    ),
    ORDER_MANAGER: (
        _p("orders", "order", "view change")
        + _p("orders", "orderitem orderstatushistory refund " + RETURNS)
        + _p("orders", "returnrequest", "change")
        + _p("orders", "shipment", "view add change")
        + _p("payments", "payment")
        + _p("accounts", "user")
        + _p("notifications", "notification")
        + ["analytics.view_sales_analytics"]
    ),
    INVENTORY_MANAGER: (
        _p("inventory", "inventory", "view change")
        + _p("products", "product productvariant")
        + ["analytics.view_product_analytics"]
    ),
    CUSTOMER_SUPPORT: (
        _p("accounts", "user", "view change")
        + _p("accounts", "address userprofile")
        + _p("orders", "order orderitem orderstatushistory shipment refund " + RETURNS)
        + _p("payments", "payment")
        + _p("notifications", "notification")
        + _p("coupons", "coupon")
        + _p("reviews", "review", "view change")
        + _p("reviews", "reviewimage")
        + ["analytics.view_customer_analytics"]
    ),
}


def resolve_permissions(codes):
    """Return (found Permission objects, codes that do not exist yet)."""
    found, missing = [], []
    for code in codes:
        app, codename = code.split(".", 1)
        permission = Permission.objects.filter(
            content_type__app_label=app, codename=codename
        ).first()
        if permission:
            found.append(permission)
        else:
            missing.append(code)
    return found, missing
