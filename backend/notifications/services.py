import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction

from .models import Notification

logger = logging.getLogger(__name__)

# status -> (title, kind). Return and refund events are sent by the returns code.
ORDER_EVENTS = {
    "PLACED": ("Order placed", Notification.Kind.ORDER),
    "CONFIRMED": ("Order confirmed", Notification.Kind.ORDER),
    "PACKED": ("Order packed", Notification.Kind.ORDER),
    "SHIPPED": ("Order shipped", Notification.Kind.SHIPMENT),
    "OUT_FOR_DELIVERY": ("Out for delivery", Notification.Kind.SHIPMENT),
    "DELIVERED": ("Order delivered", Notification.Kind.SHIPMENT),
    "CANCELLED": ("Order cancelled", Notification.Kind.ORDER),
}


def _send_email(user, title, message):
    try:
        name = user.first_name or user.email
        send_mail(
            title,
            f"Hello {name},\n\n{message}\n",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )
    except Exception:  # a mail problem must never break an order
        logger.exception("Could not send notification email to user %s", user.pk)


def notify(user, kind, title, message, order=None, send_email=True):
    """Save an in-app notification and email it once the transaction is committed."""
    notification = Notification.objects.create(
        user=user, kind=kind, title=title, message=message[:500], order=order
    )
    if send_email and user.email:
        transaction.on_commit(lambda: _send_email(user, title, message))
    return notification


def notify_order_event(order, status, note=""):
    status = getattr(status, "value", status)
    if status not in ORDER_EVENTS:
        return None
    title, kind = ORDER_EVENTS[status]
    if status == "PLACED" and not note.startswith("Order placed"):
        title, kind = "Payment update", Notification.Kind.PAYMENT
    message = (
        f"Order {order.order_number}: {note}" if note else f"Order {order.order_number}: {title}."
    )
    return notify(order.user, kind, title, message, order=order)
