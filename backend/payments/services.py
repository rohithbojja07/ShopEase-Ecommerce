import uuid

from django.db import transaction
from django.utils import timezone

from inventory.services import confirm_sale_many
from orders.models import Order, OrderStatus
from orders.services import cancel_order, record_history, set_status

from .models import Payment, PaymentStatus

# Sandbox "tokens" stand in for a card form. A real gateway would give you a signed
# payment id to verify instead. Real card numbers never touch this server.
SANDBOX_TOKENS = {
    "tok_success": PaymentStatus.SUCCESS,
    "tok_declined": PaymentStatus.FAILED,
    "tok_cancelled": PaymentStatus.CANCELLED,
}
EXPIRED_MESSAGE = "This order expired and was cancelled. Please place a new order."


class PaymentError(Exception):
    """A payment problem with a message that is safe to show."""


class PaymentNotFound(PaymentError):
    pass


def _new_reference():
    return f"SBX-{uuid.uuid4().hex[:16].upper()}"


def create_payment(user, order_id, method):
    """Start a payment for the order's own total. Returns (payment, created)."""
    expired = False
    created = False
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_id, user=user).first()
        if order is None:
            raise PaymentNotFound("Order not found.")
        if order.status != OrderStatus.PLACED:
            raise PaymentError(
                f"This order cannot be paid ({order.get_status_display().lower()})."
            )
        if order.is_expired:
            cancel_order(order, note="Payment window expired.")
            expired = True
        else:
            payment = order.payments.filter(status=PaymentStatus.PENDING).first()
            if payment is None:
                payment = Payment.objects.create(
                    order=order,
                    user=user,
                    amount=order.total,  # always the order's total, never a client value
                    method=method,
                    transaction_reference=_new_reference(),
                )
                created = True
    if expired:
        raise PaymentError(EXPIRED_MESSAGE)
    return payment, created


def verify_payment(user, payment_id, reference, token):
    """Finish a sandbox payment. Safe to call twice: the second call changes nothing."""
    if token not in SANDBOX_TOKENS:
        raise PaymentError("Unknown sandbox token. Use tok_success, tok_declined or tok_cancelled.")

    expired = False
    with transaction.atomic():
        order_id = (
            Payment.objects.filter(pk=payment_id, user=user)
            .values_list("order_id", flat=True)
            .first()
        )
        if order_id is None:
            raise PaymentNotFound("Payment not found.")
        # always lock the order first, then the payment (same order everywhere: no deadlocks)
        order = Order.objects.select_for_update().get(pk=order_id)
        payment = Payment.objects.select_for_update().get(pk=payment_id)

        if payment.transaction_reference != reference:
            raise PaymentError("Transaction reference does not match.")
        if payment.status != PaymentStatus.PENDING:
            return payment  # already processed
        if order.status != OrderStatus.PLACED:
            raise PaymentError("This order can no longer be paid.")

        if order.is_expired:
            cancel_order(order, note="Payment window expired.")
            expired = True
        else:
            outcome = SANDBOX_TOKENS[token]
            if outcome == PaymentStatus.SUCCESS:
                payment.status = PaymentStatus.SUCCESS
                payment.paid_at = timezone.now()
                payment.save(update_fields=["status", "paid_at", "updated_at"])
                confirm_sale_many([(i.variant_id, i.quantity) for i in order.items.all()])
                set_status(order, OrderStatus.CONFIRMED, note="Payment received. Order confirmed.")
            elif outcome == PaymentStatus.FAILED:
                payment.status = PaymentStatus.FAILED
                payment.failure_reason = "Payment declined by the sandbox gateway."
                payment.save(update_fields=["status", "failure_reason", "updated_at"])
                record_history(order, OrderStatus.PLACED, "Payment attempt failed. You can try again.")
            else:
                payment.status = PaymentStatus.CANCELLED
                payment.failure_reason = "Payment cancelled by the customer."
                payment.save(update_fields=["status", "failure_reason", "updated_at"])
                record_history(order, OrderStatus.PLACED, "Payment cancelled. You can try again.")
    if expired:
        raise PaymentError(EXPIRED_MESSAGE)
    return payment
