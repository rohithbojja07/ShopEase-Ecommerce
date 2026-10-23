import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import Address
from cart.models import Cart
from cart.pricing import calculate_cart
from coupons.models import CouponUsage
from coupons.services import CouponError, money, redeem_coupon
from inventory.services import InsufficientStock, release_many, reserve_many, restock_many
from payments.models import PaymentStatus

from .models import (
    CANCELLABLE_STATUSES,
    Order,
    OrderItem,
    OrderStatus,
    OrderStatusHistory,
    Shipment,
    ShippingMethod,
)

ZERO = Decimal("0.00")
_S = OrderStatus

# Which status changes are allowed. Anything else is refused.
TRANSITIONS = {
    _S.PLACED.value: {_S.CONFIRMED.value, _S.CANCELLED.value},
    _S.CONFIRMED.value: {_S.PACKED.value, _S.CANCELLED.value},
    _S.PACKED.value: {_S.SHIPPED.value, _S.CANCELLED.value},
    _S.SHIPPED.value: {_S.OUT_FOR_DELIVERY.value},
    _S.OUT_FOR_DELIVERY.value: {_S.DELIVERED.value},
    _S.DELIVERED.value: {_S.RETURN_REQUESTED.value},
}

DEFAULT_NOTES = {
    _S.CONFIRMED.value: "Payment received. Order confirmed.",
    _S.PACKED.value: "Your order has been packed.",
    _S.SHIPPED.value: "Your order has been shipped.",
    _S.OUT_FOR_DELIVERY.value: "Your order is out for delivery.",
    _S.DELIVERED.value: "Your order has been delivered.",
}

ADDRESS_FIELDS = (
    "full_name", "phone", "line1", "line2", "city", "state", "postal_code", "country",
)


class OrderError(Exception):
    """A problem with an order, with a message that is safe to show."""


class CheckoutError(OrderError):
    """A problem found while placing an order."""


# ----------------------------- shipping and quotes -----------------------------
def _setting(name, default):
    return Decimal(str(getattr(settings, name, default)))


def delivery_days(method):
    if method == ShippingMethod.EXPRESS:
        return int(getattr(settings, "EXPRESS_DELIVERY_DAYS", 2))
    return int(getattr(settings, "STANDARD_DELIVERY_DAYS", 5))


def shipping_fee(method, subtotal):
    if method == ShippingMethod.EXPRESS:
        return money(_setting("EXPRESS_SHIPPING_FEE", "199"))
    if subtotal >= _setting("FREE_SHIPPING_THRESHOLD", "1000"):
        return ZERO
    return money(_setting("SHIPPING_FEE", "99"))


def shipping_options(subtotal):
    return [
        {
            "method": method.value,
            "label": method.label,
            "fee": shipping_fee(method, subtotal),
            "estimated_days": delivery_days(method),
        }
        for method in ShippingMethod
    ]


def quote(cart, method):
    """The cart pricing plus the chosen shipping method. All numbers come from the database."""
    if method not in ShippingMethod.values:
        raise CheckoutError("Choose a valid shipping method.")
    data = calculate_cart(cart)
    fee = shipping_fee(method, data["subtotal"]) if data["items"] else ZERO
    data["shipping"] = fee
    data["total"] = data["taxable_amount"] + data["tax"] + fee
    data["shipping_method"] = method
    return data


# ---------------------------------- addresses ----------------------------------
def address_snapshot(address):
    return {field: getattr(address, field) for field in ADDRESS_FIELDS}


def _address(user, address_id, kind, label):
    address = Address.objects.filter(pk=address_id, user=user).first()
    if address is None:
        raise CheckoutError(f"Choose one of your saved {label} addresses.")
    if address.address_type != kind:
        raise CheckoutError(f"The selected address is not a {label} address.")
    return address


def resolve_addresses(user, shipping_address_id, billing_address_id=None):
    shipping = _address(user, shipping_address_id, Address.AddressType.SHIPPING, "shipping")
    if billing_address_id:
        billing = _address(user, billing_address_id, Address.AddressType.BILLING, "billing")
    else:
        billing = shipping  # billing defaults to the shipping address
    return shipping, billing


# ------------------------------------ helpers ------------------------------------
def _new_order_number():
    while True:
        number = f"ORD-{timezone.now():%Y%m%d}-{secrets.token_hex(3).upper()}"
        if not Order.objects.filter(order_number=number).exists():
            return number


def _new_tracking_number():
    while True:
        number = "TRK" + "".join(secrets.choice("0123456789") for _ in range(10))
        if not Shipment.objects.filter(tracking_number=number).exists():
            return number


def record_history(order, status, note="", by=None, notify=True):
    entry = OrderStatusHistory.objects.create(
        order=order, status=getattr(status, "value", status), note=note, changed_by=by
    )
    if notify:
        # imported here to avoid an import cycle between the two apps
        from notifications.services import notify_order_event

        notify_order_event(order, entry.status, note)
    return entry


# ----------------------------------- placing -----------------------------------
@transaction.atomic
def place_order(user, shipping_address_id, billing_address_id=None,
                shipping_method=ShippingMethod.STANDARD):
    """Checkout. Everything below succeeds together or nothing is saved."""
    shipping, billing = resolve_addresses(user, shipping_address_id, billing_address_id)

    cart, _ = Cart.objects.get_or_create(user=user)
    # lock the cart row: a double click waits here and then finds the cart empty
    cart = Cart.objects.select_for_update().get(pk=cart.pk)
    data = quote(cart, shipping_method)

    if not data["items"]:
        raise CheckoutError("Your cart is empty.")
    problems = [f"{line['product_name']}: {line['issue']}" for line in data["items"] if line["issue"]]
    if problems:
        raise CheckoutError("Please fix your cart first. " + " ".join(problems))
    coupon = data["coupon"]
    if coupon and coupon["message"]:
        raise CheckoutError(f"Coupon {coupon['code']}: {coupon['message']}")

    try:
        reserve_many([(line["variant_id"], line["quantity"]) for line in data["items"]])
    except InsufficientStock as exc:
        raise CheckoutError(
            "Sorry, an item in your cart just went out of stock. Please review your cart."
        ) from exc

    window = int(getattr(settings, "ORDER_PAYMENT_WINDOW_MINUTES", 30))
    order = Order.objects.create(
        order_number=_new_order_number(),
        user=user,
        shipping_method=shipping_method,
        shipping_address=address_snapshot(shipping),
        billing_address=address_snapshot(billing),
        subtotal_mrp=data["subtotal_mrp"],
        product_discount=data["product_discount"],
        subtotal=data["subtotal"],
        coupon_code=coupon["code"] if coupon else "",
        coupon_discount=data["coupon_discount"],
        tax=data["tax"],
        shipping_fee=data["shipping"],
        total=data["total"],
        expires_at=timezone.now() + timedelta(minutes=window),
    )
    OrderItem.objects.bulk_create([
        OrderItem(
            order=order,
            variant_id=line["variant_id"],
            product_name=line["product_name"],
            sku=line["sku"],
            size=line["size"],
            color=line["color"],
            unit_mrp=line["unit_mrp"],
            unit_price=line["unit_price"],
            quantity=line["quantity"],
            line_total=line["line_total"],
        )
        for line in data["items"]
    ])

    if coupon:
        try:
            _, discount = redeem_coupon(
                coupon["code"], user, data["items"], data["subtotal"], order.order_number
            )
        except CouponError as exc:
            raise CheckoutError(f"Coupon {coupon['code']}: {exc}") from exc
        if discount != data["coupon_discount"]:
            raise CheckoutError("Prices changed while you were checking out. Please review your cart.")

    cart.items.filter(saved_for_later=False).delete()
    cart.coupon = None
    cart.save(update_fields=["coupon", "updated_at"])
    record_history(order, OrderStatus.PLACED, "Order placed. Waiting for payment.", by=user)
    return order


# ------------------------------- status changes -------------------------------
@transaction.atomic
def cancel_order(order, by=None, note=""):
    """Cancel an order and put its stock back. Paid orders are refunded (sandbox)."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status not in CANCELLABLE_STATUSES:
        raise OrderError("This order can no longer be cancelled.")

    items = [(item.variant_id, item.quantity) for item in order.items.all()]
    now = timezone.now()
    paid = order.payments.filter(status=PaymentStatus.SUCCESS).exists()
    if paid:
        restock_many(items)  # sold -> available
        order.payments.filter(status=PaymentStatus.SUCCESS).update(
            status=PaymentStatus.REFUNDED, updated_at=now
        )
    else:
        release_many(items)  # reserved -> available
    order.payments.filter(status=PaymentStatus.PENDING).update(
        status=PaymentStatus.CANCELLED, updated_at=now
    )
    CouponUsage.objects.filter(order_reference=order.order_number).delete()

    order.status = OrderStatus.CANCELLED.value
    order.cancelled_at = now
    order.save(update_fields=["status", "cancelled_at", "updated_at"])
    record_history(order, OrderStatus.CANCELLED, note or "Order cancelled.", by)
    return order


def _update_shipment(order, new_status, now):
    if new_status == OrderStatus.SHIPPED.value:
        days = delivery_days(order.shipping_method)
        Shipment.objects.get_or_create(
            order=order,
            defaults={
                "tracking_number": _new_tracking_number(),
                "status": Shipment.ShipmentStatus.SHIPPED,
                "shipped_at": now,
                "expected_delivery": (now + timedelta(days=days)).date(),
            },
        )
    elif new_status in (OrderStatus.OUT_FOR_DELIVERY.value, OrderStatus.DELIVERED.value):
        shipment = getattr(order, "shipment", None)
        if shipment:
            shipment.status = new_status
            if new_status == OrderStatus.DELIVERED.value:
                shipment.delivered_at = now
            shipment.save()


@transaction.atomic
def set_status(order, new_status, by=None, note=""):
    """Move an order to its next status. Only allowed changes go through."""
    new_status = getattr(new_status, "value", new_status)
    if new_status not in OrderStatus.values:
        raise OrderError("Unknown order status.")
    order = Order.objects.select_for_update().get(pk=order.pk)
    if new_status == OrderStatus.CANCELLED.value:
        return cancel_order(order, by=by, note=note or "Order cancelled.")
    if new_status not in TRANSITIONS.get(order.status, set()):
        raise OrderError(
            f"An order that is {order.get_status_display().lower()} cannot be moved to "
            f"{OrderStatus(new_status).label.lower()}."
        )
    now = timezone.now()
    order.status = new_status
    fields = ["status", "updated_at"]
    if new_status == OrderStatus.DELIVERED.value:
        order.delivered_at = now
        fields.append("delivered_at")
    order.save(update_fields=fields)
    _update_shipment(order, new_status, now)
    record_history(order, new_status, note or DEFAULT_NOTES.get(new_status, ""), by)
    return order
