from decimal import Decimal

from django.conf import settings

from coupons.services import CouponError, check_coupon, money

ZERO = Decimal("0.00")


def _setting(name, default):
    return Decimal(str(getattr(settings, name, default)))


def build_line(item):
    variant = item.variant
    product = variant.product
    inventory = getattr(variant, "inventory", None)
    available = inventory.available_stock if inventory else 0
    quantity = item.quantity

    issue = None
    if not (variant.is_active and product.is_active and product.category.is_active):
        issue = "This item is no longer available."
    elif available <= 0:
        issue = "Out of stock."
    elif quantity > available:
        issue = f"Only {available} left in stock."

    return {
        "variant_id": variant.id,
        "sku": variant.sku,
        "product_id": product.id,
        "category_id": product.category_id,
        "product_name": product.name,
        "size": variant.size,
        "color": variant.color,
        "quantity": quantity,
        "unit_mrp": money(variant.price),
        "unit_price": variant.final_price,
        "line_mrp": money(variant.price * quantity),
        "line_total": money(variant.final_price * quantity),
        "issue": issue,
    }


def build_lines(cart):
    items = cart.items.select_related(
        "variant__product__category", "variant__inventory"
    ).order_by("created_at", "id")
    active, saved = [], []
    for item in items:
        (saved if item.saved_for_later else active).append(build_line(item))
    return active, saved


def calculate_cart(cart):
    active, saved = build_lines(cart)

    subtotal_mrp = sum((line["line_mrp"] for line in active), ZERO)
    subtotal = sum((line["line_total"] for line in active), ZERO)
    product_discount = subtotal_mrp - subtotal

    coupon_info = None
    coupon_discount = ZERO
    if cart.coupon_id:
        try:
            coupon, coupon_discount = check_coupon(cart.coupon.code, cart.user, active, subtotal)
            coupon_info = {"code": coupon.code, "discount": coupon_discount, "message": None}
        except CouponError as exc:
            coupon_info = {"code": cart.coupon.code, "discount": ZERO, "message": str(exc)}

    taxable = subtotal - coupon_discount
    tax_rate = _setting("TAX_RATE_PERCENT", "18")
    tax = money(taxable * tax_rate / Decimal("100"))
    if not active or subtotal >= _setting("FREE_SHIPPING_THRESHOLD", "1000"):
        shipping = ZERO
    else:
        shipping = money(_setting("SHIPPING_FEE", "99"))

    return {
        "items": active,
        "saved_for_later": saved,
        "item_count": sum(line["quantity"] for line in active),
        "subtotal_mrp": subtotal_mrp,
        "product_discount": product_discount,
        "subtotal": subtotal,
        "coupon": coupon_info,
        "coupon_discount": coupon_discount,
        "taxable_amount": taxable,
        "tax_rate_percent": tax_rate,
        "tax": tax,
        "shipping": shipping,
        "total": taxable + tax + shipping,
        "has_issues": any(line["issue"] for line in active),
    }


def to_json(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: to_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json(item) for item in value]
    return value
