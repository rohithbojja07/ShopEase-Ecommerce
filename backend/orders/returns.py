import secrets
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from coupons.services import money
from inventory.services import restock_many
from notifications.models import Notification
from notifications.services import notify
from payments.models import Payment, PaymentStatus

from .models import (
    BLOCKING_RETURN_STATUSES,
    Order,
    OrderStatus,
    Refund,
    ReturnEvent,
    ReturnEvidence,
    ReturnItem,
    ReturnRequest,
    ReturnStatus,
)
from .services import record_history


class ReturnError(Exception):
    """A return problem with a message that is safe to show."""


class ReturnNotFound(ReturnError):
    pass


def window_days():
    return int(getattr(settings, "RETURN_WINDOW_DAYS", 7))


def max_evidence():
    return int(getattr(settings, "MAX_RETURN_EVIDENCE_IMAGES", 5))


def _new_return_number():
    while True:
        number = f"RET-{timezone.now():%Y%m%d}-{secrets.token_hex(3).upper()}"
        if not ReturnRequest.objects.filter(return_number=number).exists():
            return number


def _event(ret, status, note="", by=None):
    return ReturnEvent.objects.create(
        return_request=ret, status=getattr(status, "value", status), note=note, changed_by=by
    )


def _set_order_status(order, status, note, by=None):
    status = getattr(status, "value", status)
    order.status = status
    order.save(update_fields=["status", "updated_at"])
    # the returns code sends its own notifications, so the history entry stays quiet
    record_history(order, status, note, by=by, notify=False)


def _lock(ret):
    return ReturnRequest.objects.select_for_update().get(pk=ret.pk)


def _lock_order(ret):
    return Order.objects.select_for_update().get(pk=ret.order_id)


def _require(ret, status, verb):
    if ret.status != status:
        raise ReturnError(f"A return that is {ret.get_status_display().lower()} cannot be {verb}.")


def _tell(ret, kind, title, message):
    return notify(ret.user, kind, title, message, order=ret.order)


# ------------------------------- customer side -------------------------------
@transaction.atomic
def request_return(user, order_id, reason, description="", items=None):
    order = Order.objects.select_for_update().filter(pk=order_id, user=user).first()
    if order is None:
        raise ReturnNotFound("Order not found.")
    if order.status != OrderStatus.DELIVERED:
        raise ReturnError("Only delivered orders can be returned.")
    days = window_days()
    if order.delivered_at is None or timezone.now() > order.delivered_at + timedelta(days=days):
        raise ReturnError(f"The {days}-day return window for this order has ended.")
    if order.returns.filter(status__in=BLOCKING_RETURN_STATUSES).exists():
        raise ReturnError("This order already has a return request.")

    order_items = {item.id: item for item in order.items.all()}
    if not items:
        chosen = {item_id: item.quantity for item_id, item in order_items.items()}
    else:
        chosen = {}
        for entry in items:
            item_id, quantity = entry["order_item_id"], entry["quantity"]
            if item_id in chosen:
                raise ReturnError("Each item can be listed only once.")
            item = order_items.get(item_id)
            if item is None:
                raise ReturnError("One of the items does not belong to this order.")
            if quantity > item.quantity:
                raise ReturnError(
                    f"You can return at most {item.quantity} of {item.product_name}."
                )
            chosen[item_id] = quantity

    # the refund is the returned items' share of what was paid (shipping excluded)
    returned_subtotal = sum(
        (order_items[item_id].unit_price * quantity for item_id, quantity in chosen.items()),
        Decimal("0"),
    )
    net_paid = order.total - order.shipping_fee
    refund_amount = min(money(net_paid * returned_subtotal / order.subtotal), money(net_paid))

    ret = ReturnRequest.objects.create(
        return_number=_new_return_number(),
        order=order,
        user=user,
        reason=reason,
        description=description or "",
        refund_amount=refund_amount,
    )
    ReturnItem.objects.bulk_create([
        ReturnItem(return_request=ret, order_item_id=item_id, quantity=quantity)
        for item_id, quantity in chosen.items()
    ])
    _event(ret, ReturnStatus.REQUESTED, "Return requested.", by=user)
    _set_order_status(order, OrderStatus.RETURN_REQUESTED, "Return requested.", by=user)
    _tell(
        ret, Notification.Kind.RETURN, "Return request received",
        f"Your return {ret.return_number} for order {order.order_number} was received. "
        "We will review it soon.",
    )
    return ret


@transaction.atomic
def add_evidence(ret, files):
    ret = _lock(ret)
    if ret.status != ReturnStatus.REQUESTED:
        raise ReturnError("Evidence can only be added while the return is waiting for review.")
    if ret.evidence.count() + len(files) > max_evidence():
        raise ReturnError(f"You can upload at most {max_evidence()} images per return.")
    return [ReturnEvidence.objects.create(return_request=ret, image=f) for f in files]


@transaction.atomic
def cancel_return(ret, by=None):
    ret = _lock(ret)
    _require(ret, ReturnStatus.REQUESTED, "cancelled")
    order = _lock_order(ret)
    ret.status = ReturnStatus.CANCELLED
    ret.save(update_fields=["status", "updated_at"])
    _event(ret, ReturnStatus.CANCELLED, "Return request withdrawn.", by=by)
    _set_order_status(order, OrderStatus.DELIVERED, "Return request withdrawn.", by=by)
    return ret


# --------------------------------- admin side ---------------------------------
@transaction.atomic
def approve_return(ret, by=None):
    ret = _lock(ret)
    _require(ret, ReturnStatus.REQUESTED, "approved")
    order = _lock_order(ret)
    ret.status = ReturnStatus.APPROVED
    ret.reviewed_by = by
    ret.reviewed_at = timezone.now()
    ret.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    _event(ret, ReturnStatus.APPROVED, "Return approved.", by=by)
    record_history(
        order, OrderStatus.RETURN_REQUESTED,
        "Return approved. Please send the items back.", by=by, notify=False,
    )
    _tell(
        ret, Notification.Kind.RETURN, "Return approved",
        f"Your return {ret.return_number} was approved. Please send the items back to us.",
    )
    return ret


@transaction.atomic
def reject_return(ret, by=None, note=""):
    note = (note or "").strip()
    if not note:
        raise ReturnError("Add a note explaining the reason before rejecting.")
    ret = _lock(ret)
    _require(ret, ReturnStatus.REQUESTED, "rejected")
    order = _lock_order(ret)
    ret.status = ReturnStatus.REJECTED
    ret.admin_note = note[:200]
    ret.reviewed_by = by
    ret.reviewed_at = timezone.now()
    ret.save(update_fields=["status", "admin_note", "reviewed_by", "reviewed_at", "updated_at"])
    _event(ret, ReturnStatus.REJECTED, f"Return rejected: {ret.admin_note}", by=by)
    _set_order_status(order, OrderStatus.DELIVERED, "Return request rejected.", by=by)
    _tell(
        ret, Notification.Kind.RETURN, "Return rejected",
        f"Your return {ret.return_number} was rejected. Reason: {ret.admin_note}",
    )
    return ret


@transaction.atomic
def mark_received(ret, by=None):
    ret = _lock(ret)
    _require(ret, ReturnStatus.APPROVED, "marked as received")
    order = _lock_order(ret)
    ret.status = ReturnStatus.RECEIVED
    ret.save(update_fields=["status", "updated_at"])
    _event(ret, ReturnStatus.RECEIVED, "Returned items received.", by=by)
    _set_order_status(order, OrderStatus.RETURNED, "Returned items received.", by=by)
    _tell(
        ret, Notification.Kind.RETURN, "Return received",
        f"We received the items for return {ret.return_number}. Your refund is being processed.",
    )
    return ret


@transaction.atomic
def approve_refund(ret, by=None):
    ret = _lock(ret)
    _require(ret, ReturnStatus.RECEIVED, "refunded")
    order = _lock_order(ret)
    payment = (
        Payment.objects.select_for_update()
        .filter(order=order, status=PaymentStatus.SUCCESS)
        .first()
    )
    if payment is None:
        raise ReturnError("No successful payment was found for this order.")

    lines = list(ret.items.select_related("order_item"))
    if ret.restock_items:
        try:
            restock_many([(line.order_item.variant_id, line.quantity) for line in lines], returned=True)
        except ValueError as exc:
            raise ReturnError(str(exc)) from exc

    Refund.objects.create(
        return_request=ret,
        order=order,
        payment=payment,
        amount=ret.refund_amount,
        transaction_reference=f"RFD-{uuid.uuid4().hex[:16].upper()}",
        approved_by=by,
    )
    ordered = {item.id: item.quantity for item in order.items.all()}
    returned = {line.order_item_id: line.quantity for line in lines}
    if ordered == returned:  # everything was returned
        payment.status = PaymentStatus.REFUNDED
        payment.save(update_fields=["status", "updated_at"])
        _set_order_status(
            order, OrderStatus.REFUNDED, f"Refund of {ret.refund_amount} processed.", by=by
        )
    else:  # partial return: the order stays delivered and the payment stays successful
        _set_order_status(
            order, OrderStatus.DELIVERED,
            f"Partial refund of {ret.refund_amount} processed.", by=by,
        )

    ret.status = ReturnStatus.REFUNDED
    ret.save(update_fields=["status", "updated_at"])
    _event(ret, ReturnStatus.REFUNDED, f"Refund of {ret.refund_amount} processed.", by=by)
    _tell(
        ret, Notification.Kind.REFUND, "Refund processed",
        f"Your refund of {ret.refund_amount} for return {ret.return_number} has been processed "
        "(sandbox).",
    )
    return ret
