from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        ORDER = "ORDER", "Order"
        PAYMENT = "PAYMENT", "Payment"
        SHIPMENT = "SHIPMENT", "Shipment"
        RETURN = "RETURN", "Return"
        REFUND = "REFUND", "Refund"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    title = models.CharField(max_length=120)
    message = models.CharField(max_length=500)
    order = models.ForeignKey(
        "orders.Order", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="notifications",
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"], name="notif_user_unread_idx"),
        ]

    def __str__(self):
        return f"{self.title} -> {self.user_id}"
