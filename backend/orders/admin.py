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
