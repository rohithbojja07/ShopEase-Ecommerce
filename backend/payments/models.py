from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"
    REFUNDED = "REFUNDED", "Refunded"
    CANCELLED = "CANCELLED", "Cancelled"


class PaymentMethod(models.TextChoices):
    CARD = "CARD", "Card (sandbox)"
    UPI = "UPI", "UPI (sandbox)"
    NETBANKING = "NETBANKING", "Net banking (sandbox)"


class Payment(TimeStampedModel):
    order = models.ForeignKey(
        "orders.Order", on_delete=models.PROTECT, related_name="payments"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(
        max_length=15, choices=PaymentMethod.choices, default=PaymentMethod.CARD
    )
    status = models.CharField(
        max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    transaction_reference = models.CharField(max_length=40, unique=True)
    failure_reason = models.CharField(max_length=200, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["order", "status"], name="payment_order_status_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gte=0), name="payment_amount_not_negative"),
            # the database allows only one open payment per order
            models.UniqueConstraint(
                fields=["order"],
                condition=Q(status="PENDING"),
                name="one_pending_payment_per_order",
            ),
        ]

    def __str__(self):
        return f"{self.transaction_reference} ({self.status})"
