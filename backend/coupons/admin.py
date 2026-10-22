from django.contrib import admin

from .models import Coupon, CouponUsage


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        "code", "discount_type", "value", "min_order_value",
        "valid_until", "usage_limit", "times_used", "is_active",
    )
    list_filter = ("is_active", "discount_type")
    search_fields = ("code", "description")
    filter_horizontal = ("categories", "products")
    autocomplete_fields = ("user",)

    @admin.display(description="Used")
    def times_used(self, obj):
        return obj.usages.count()


@admin.register(CouponUsage)
class CouponUsageAdmin(admin.ModelAdmin):
    list_display = ("coupon", "user", "order_reference", "discount_amount", "used_at")
    search_fields = ("coupon__code", "user__email", "order_reference")
    readonly_fields = ("coupon", "user", "order_reference", "discount_amount", "used_at")

    def has_add_permission(self, request):
        return False
