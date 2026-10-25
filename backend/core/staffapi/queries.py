from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import (
    Count, DecimalField, ExpressionWrapper, F, IntegerField, OuterRef, Subquery, Sum, Value,
)
from django.db.models.functions import Coalesce

from orders.models import Order, Refund
from payments.models import Payment

MONEY = DecimalField(max_digits=14, decimal_places=2)
ZERO = Value(Decimal("0.00"), output_field=MONEY)


def customers_queryset():
    """Customers only (never staff), with order count and net spending."""
    User = get_user_model()
    orders = (
        Order.objects.filter(user=OuterRef("pk")).exclude(status="CANCELLED")
        .order_by().values("user").annotate(n=Count("pk")).values("n")
    )
    paid = (
        Payment.objects.filter(user=OuterRef("pk"), status="SUCCESS")
        .order_by().values("user").annotate(s=Sum("amount")).values("s")
    )
    refunded = (
        Refund.objects.filter(order__user=OuterRef("pk"), payment__status="SUCCESS")
        .order_by().values("order__user").annotate(s=Sum("amount")).values("s")
    )
    return (
        User.objects.filter(is_staff=False)
        .annotate(
            order_count=Coalesce(Subquery(orders, output_field=IntegerField()), Value(0)),
            total_paid=Coalesce(Subquery(paid, output_field=MONEY), ZERO),
            total_refunded=Coalesce(Subquery(refunded, output_field=MONEY), ZERO),
        )
        .annotate(
            net_spent=ExpressionWrapper(F("total_paid") - F("total_refunded"), output_field=MONEY)
        )
    )
