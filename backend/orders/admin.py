from django.contrib import admin, messages

from .models import Order, OrderItem, OrderStatusHistory, Shipment
from .services import OrderError, set_status


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = (
        "variant", "product_name", "sku", "size", "color",
        "unit_mrp", "unit_price", "quantity", "line_total",
    )

    def has_add_permission(self, request, obj=None):
        return False


class StatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    can_delete = False
    readonly_fields = ("status", "note", "changed_by", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


class ShipmentInline(admin.StackedInline):
    """Staff can correct the carrier, tracking number and delivery date here."""

    model = Shipment
    extra = 0
    max_num = 1
    can_delete = False


def _status_action(target, label):
    def action(modeladmin, request, queryset):
        done = 0
        for order in queryset:
            try:
                set_status(order, target, by=request.user)
                done += 1
            except OrderError as exc:
                modeladmin.message_user(
                    request, f"{order.order_number}: {exc}", level=messages.ERROR
                )
        if done:
            modeladmin.message_user(request, f"{done} order(s) updated.")

    action.short_description = label
    action.__name__ = f"mark_{target.lower()}"
    return action


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "user", "status", "payment_state", "total", "created_at")
    list_filter = ("status", "shipping_method", "created_at")
    search_fields = ("order_number", "user__email")
    date_hierarchy = "created_at"
    list_select_related = ("user",)
    inlines = [OrderItemInline, StatusHistoryInline, ShipmentInline]
    readonly_fields = (
        "order_number", "user", "status", "shipping_method", "shipping_address",
        "billing_address", "subtotal_mrp", "product_discount", "subtotal",
        "coupon_code", "coupon_discount", "tax", "shipping_fee", "total",
        "expires_at", "cancelled_at", "delivered_at", "created_at", "updated_at",
    )
    actions = [
        _status_action("PACKED", "Mark as packed"),
        _status_action("SHIPPED", "Mark as shipped"),
        _status_action("OUT_FOR_DELIVERY", "Mark as out for delivery"),
        _status_action("DELIVERED", "Mark as delivered"),
        _status_action("CANCELLED", "Cancel (restocks and refunds)"),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("payments")

    @admin.display(description="Payment")
    def payment_state(self, obj):
        return obj.payment_status

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ------------------------------ returns and refunds ------------------------------
from .models import ReturnEvent, ReturnEvidence, ReturnItem, ReturnRequest, Refund  # noqa: E402
from .returns import (  # noqa: E402
    ReturnError,
    approve_refund,
    approve_return,
    mark_received,
    reject_return,
)


class ReturnItemInline(admin.TabularInline):
    model = ReturnItem
    extra = 0
    can_delete = False
    readonly_fields = ("order_item", "quantity")

    def has_add_permission(self, request, obj=None):
        return False


class ReturnEvidenceInline(admin.TabularInline):
    model = ReturnEvidence
    extra = 0
    can_delete = False
    readonly_fields = ("image", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


class ReturnEventInline(admin.TabularInline):
    model = ReturnEvent
    extra = 0
    can_delete = False
    readonly_fields = ("status", "note", "changed_by", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


def _return_action(function, label, name):
    def action(modeladmin, request, queryset):
        done = 0
        for ret in queryset:
            try:
                function(ret, request.user)
                done += 1
            except ReturnError as exc:
                modeladmin.message_user(
                    request, f"{ret.return_number}: {exc}", level=messages.ERROR
                )
        if done:
            modeladmin.message_user(request, f"{done} return(s) updated.")

    action.short_description = label
    action.__name__ = name
    return action


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = (
        "return_number", "order", "user", "reason", "status", "refund_amount", "created_at",
    )
    list_filter = ("status", "reason")
    search_fields = ("return_number", "order__order_number", "user__email")
    list_select_related = ("order", "user")
    date_hierarchy = "created_at"
    inlines = [ReturnItemInline, ReturnEvidenceInline, ReturnEventInline]
    # only admin_note and restock_items can be edited; everything else changes via actions
    readonly_fields = (
        "return_number", "order", "user", "reason", "description", "status",
        "refund_amount", "reviewed_by", "reviewed_at", "created_at", "updated_at",
    )
    actions = [
        _return_action(approve_return, "Approve return", "approve_returns"),
        _return_action(
            lambda ret, user: reject_return(ret, user, ret.admin_note),
            "Reject return (write the reason in Admin note first)",
            "reject_returns",
        ),
        _return_action(mark_received, "Mark items as received", "mark_returns_received"),
        _return_action(approve_refund, "Approve refund (restocks items)", "approve_refunds"),
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("transaction_reference", "return_request", "order", "amount", "processed_at")
    search_fields = ("transaction_reference", "return_request__return_number", "order__order_number")
    readonly_fields = [field.name for field in Refund._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
