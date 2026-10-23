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


# ---------------------------- Returns and refunds ----------------------------
from products.validators import validate_image_extension, validate_image_size  # noqa: E402

RETURN_IMAGE_VALIDATORS = [validate_image_extension, validate_image_size]


class ReturnReason(models.TextChoices):
    DEFECTIVE = "DEFECTIVE", "Defective or damaged"
    WRONG_ITEM = "WRONG_ITEM", "Wrong item received"
    NOT_AS_DESCRIBED = "NOT_AS_DESCRIBED", "Not as described"
    NO_LONGER_NEEDED = "NO_LONGER_NEEDED", "Changed my mind"
    OTHER = "OTHER", "Other"


class ReturnStatus(models.TextChoices):
    REQUESTED = "REQUESTED", "Requested"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    RECEIVED = "RECEIVED", "Received"
    REFUNDED = "REFUNDED", "Refunded"
    CANCELLED = "CANCELLED", "Cancelled"


# a rejected or withdrawn return does not block a new request
BLOCKING_RETURN_STATUSES = ["REQUESTED", "APPROVED", "RECEIVED", "REFUNDED"]


class ReturnRequest(TimeStampedModel):
    return_number = models.CharField(max_length=30, unique=True)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="returns")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="returns"
    )
    reason = models.CharField(max_length=20, choices=ReturnReason.choices)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=12, choices=ReturnStatus.choices, default=ReturnStatus.REQUESTED
    )
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2)
    restock_items = models.BooleanField(
        default=True,
        help_text="Untick for damaged items that must not go back into sellable stock.",
    )
    admin_note = models.CharField(
        max_length=200, blank=True, help_text="Required to reject a return."
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["status"], name="return_status_idx")]
        constraints = [
            # the database allows only one active return per order
            models.UniqueConstraint(
                fields=["order"],
                condition=Q(status__in=BLOCKING_RETURN_STATUSES),
                name="one_active_return_per_order",
            ),
            models.CheckConstraint(
                condition=Q(refund_amount__gte=0), name="return_refund_not_negative"
            ),
        ]

    def __str__(self):
        return self.return_number


class ReturnItem(models.Model):
    return_request = models.ForeignKey(
        ReturnRequest, on_delete=models.CASCADE, related_name="items"
    )
    order_item = models.ForeignKey(
        OrderItem, on_delete=models.PROTECT, related_name="return_lines"
    )
    quantity = models.PositiveIntegerField()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["return_request", "order_item"], name="one_line_per_item_in_return"
            ),
            models.CheckConstraint(condition=Q(quantity__gte=1), name="return_quantity_min_1"),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.order_item.sku}"


class ReturnEvidence(models.Model):
    return_request = models.ForeignKey(
        ReturnRequest, on_delete=models.CASCADE, related_name="evidence"
    )
    image = models.ImageField(upload_to="returns/%Y/%m/", validators=RETURN_IMAGE_VALIDATORS)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name_plural = "return evidence"

    def __str__(self):
        return f"Evidence for {self.return_request.return_number}"


class ReturnEvent(models.Model):
    """One row per status change: this is the return tracking timeline."""

    return_request = models.ForeignKey(
        ReturnRequest, on_delete=models.CASCADE, related_name="events"
    )
    status = models.CharField(max_length=12, choices=ReturnStatus.choices)
    note = models.CharField(max_length=200, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.return_request.return_number}: {self.status}"


class Refund(TimeStampedModel):
    return_request = models.OneToOneField(
        ReturnRequest, on_delete=models.PROTECT, related_name="refund"
    )
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="refunds")
    payment = models.ForeignKey(
        "payments.Payment", on_delete=models.PROTECT, related_name="refunds"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_reference = models.CharField(max_length=40, unique=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    processed_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.transaction_reference} ({self.amount})"
