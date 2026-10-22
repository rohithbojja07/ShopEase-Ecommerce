from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from .models import Coupon, CouponUsage

TWO_PLACES = Decimal("0.01")
INVALID = "This coupon code is not valid."


def money(value):
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


class CouponError(Exception):
    """Raised with a message that is safe to show to the customer."""


def _eligible_amount(coupon, lines):
    category_ids = set(coupon.categories.values_list("id", flat=True))
    product_ids = set(coupon.products.values_list("id", flat=True))
    if not category_ids and not product_ids:
        return sum((line["line_total"] for line in lines), Decimal("0"))
    total = Decimal("0")
    for line in lines:
        if line["product_id"] in product_ids or line["category_id"] in category_ids:
            total += line["line_total"]
    return total


def check_coupon(code, user, lines, subtotal):
    """Validate a coupon for this user and cart. Returns (coupon, discount).

    lines: dicts with product_id, category_id and line_total (price after the
    product discount). subtotal is the cart total before the coupon.
    """
    code = (code or "").strip().upper()
    coupon = Coupon.objects.filter(code=code, is_active=True).first()
    if coupon is None:
        raise CouponError(INVALID)
    if coupon.user_id and coupon.user_id != user.id:
        raise CouponError(INVALID)  # private coupons look unknown to everyone else

    now = timezone.now()
    if now < coupon.valid_from:
        raise CouponError("This coupon is not active yet.")
    if now > coupon.valid_until:
        raise CouponError("This coupon has expired.")
    if coupon.usage_limit is not None and coupon.usages.count() >= coupon.usage_limit:
        raise CouponError("This coupon has reached its usage limit.")
    if coupon.usages.filter(user=user).count() >= coupon.per_user_limit:
        raise CouponError("You have already used this coupon.")
    if subtotal < coupon.min_order_value:
        raise CouponError(
            f"Minimum order value for this coupon is {money(coupon.min_order_value)}."
        )

    eligible = _eligible_amount(coupon, lines)
    if eligible <= 0:
        raise CouponError("This coupon does not apply to the items in your cart.")

    if coupon.discount_type == Coupon.DiscountType.PERCENT:
        discount = eligible * coupon.value / Decimal("100")
        if coupon.max_discount is not None:
            discount = min(discount, coupon.max_discount)
    else:
        discount = min(coupon.value, eligible)
    return coupon, min(money(discount), money(eligible))


@transaction.atomic
def redeem_coupon(code, user, lines, subtotal, order_reference=""):
    """Used when an order is placed: lock, re-check, then record the usage.

    The row lock makes two simultaneous orders unable to both take the last use.
    """
    code = (code or "").strip().upper()
    Coupon.objects.select_for_update().filter(code=code).first()
    coupon, discount = check_coupon(code, user, lines, subtotal)
    CouponUsage.objects.create(
        coupon=coupon, user=user, order_reference=order_reference, discount_amount=discount
    )
    return coupon, discount
