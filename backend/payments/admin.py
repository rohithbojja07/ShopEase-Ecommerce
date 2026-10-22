from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "transaction_reference", "order", "user", "amount", "method", "status", "paid_at",
    )
    list_filter = ("status", "method")
    search_fields = ("transaction_reference", "order__order_number", "user__email")
    readonly_fields = (
        "order", "user", "amount", "method", "status", "transaction_reference",
        "failure_reason", "paid_at", "created_at", "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
