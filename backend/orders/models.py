from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import TimeStampedModel


class OrderStatus(models.TextChoices):
    PLACED = "PLACED", "Placed"
    CONFIRMED = "CONFIRMED", "Confirmed"
    PACKED = "PACKED", "Packed"
    SHIPPED = "SHIPPED", "Shipped"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY", "Out for delivery"
    DELIVERED = "DELIVERED", "Delivered"
    CANCELLED = "CANCELLED", "Cancelled"
    RETURN_REQUESTED = "RETURN_REQUESTED", "Return requested"
    RETURNED = "RETURNED", "Returned"
    REFUNDED = "REFUNDED", "Refunded"


CANCELLABLE_STATUSES = (
    OrderStatus.PLACED.value,
    OrderStatus.CONFIRMED.value,
    OrderStatus.PACKED.value,
)


class ShippingMethod(models.TextChoices):
    STANDARD = "STANDARD", "Standard"
    EXPRESS = "EXPRESS", "Express"


class Order(TimeStampedModel):
    order_number = models.CharField(max_length=30, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders"
    )
    status = models.CharField(
        max_length=20, choices=OrderStatus.choices, default=OrderStatus.PLACED
    )
    shipping_method = models.CharField(
        max_length=10, choices=ShippingMethod.choices, default=ShippingMethod.STANDARD
    )
    # copies of the addresses at order time, so later edits never change old orders
    shipping_address = models.JSONField()
    billing_address = models.JSONField()

    subtotal_mrp = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    product_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    coupon_code = models.CharField(max_length=30, blank=True)
    coupon_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    expires_at = models.DateTimeField()
    cancelled_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="order_user_recent_idx"),
            models.Index(fields=["status"], name="order_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(total__gte=0), name="order_total_not_negative"),
        ]

    def __str__(self):
        return self.order_number

    @property
    def is_expired(self):
        return self.status == OrderStatus.PLACED and timezone.now() > self.expires_at

    @property
    def can_cancel(self):
        return self.status in CANCELLABLE_STATUSES

    @property
    def payment_status(self):
        statuses = [payment.status for payment in self.payments.all()]
        for wanted in ("REFUNDED", "SUCCESS"):
            if wanted in statuses:
                return wanted
        return statuses[-1] if statuses else "PENDING"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(
        "products.ProductVariant", on_delete=models.PROTECT, related_name="order_items"
    )
    # snapshot of what the customer bought and paid for
    product_name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50)
    size = models.CharField(max_length=20, blank=True)
    color = models.CharField(max_length=30, blank=True)
    unit_mrp = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField()
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=1), name="order_item_quantity_min_1"),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.sku}"


class OrderStatusHistory(models.Model):
    """One row per status change: this is the order tracking timeline."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="history")
    status = models.CharField(max_length=20, choices=OrderStatus.choices)
    note = models.CharField(max_length=200, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name_plural = "order status history"

    def __str__(self):
        return f"{self.order.order_number}: {self.status}"


class Shipment(TimeStampedModel):
    class ShipmentStatus(models.TextChoices):
        SHIPPED = "SHIPPED", "Shipped"
        OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY", "Out for delivery"
        DELIVERED = "DELIVERED", "Delivered"

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="shipment")
    carrier = models.CharField(max_length=60, default="Sandbox Express")
    tracking_number = models.CharField(max_length=40, unique=True)
    status = models.CharField(
        max_length=20, choices=ShipmentStatus.choices, default=ShipmentStatus.SHIPPED
    )
    shipped_at = models.DateTimeField(default=timezone.now)
    expected_delivery = models.DateField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.tracking_number} ({self.status})"
