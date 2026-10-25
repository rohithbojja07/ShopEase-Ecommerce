from django.contrib import admin
from django.db.models import F

from core.audit import log_action

from .models import Inventory


class StockLevelFilter(admin.SimpleListFilter):
    title = "stock level"
    parameter_name = "stock"

    def lookups(self, request, model_admin):
        return [("low", "Low stock"), ("out", "Out of stock")]

    def queryset(self, request, queryset):
        if self.value() == "low":
            return queryset.filter(
                available_stock__gt=0, available_stock__lte=F("low_stock_threshold")
            )
        if self.value() == "out":
            return queryset.filter(available_stock=0)
        return queryset


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = (
        "sku", "product_name", "available_stock", "reserved_stock",
        "sold_stock", "returned_stock", "low_stock_threshold", "low_stock",
    )
    list_filter = (StockLevelFilter,)
    search_fields = ("variant__sku", "variant__product__name")
    list_select_related = ("variant", "variant__product")
    # only "available" can be corrected by hand; opening stock follows it automatically
    readonly_fields = ("opening_stock", "reserved_stock", "sold_stock", "returned_stock")

    def save_model(self, request, obj, form, change):
        before = None
        if change and "available_stock" in form.changed_data:
            before = Inventory.objects.get(pk=obj.pk).available_stock
            obj.opening_stock += obj.available_stock - before
        super().save_model(request, obj, form, change)
        if before is not None:
            log_action(
                request, "inventory.edited", obj,
                {"available_before": before, "available_after": obj.available_stock},
            )

    @admin.display(ordering="variant__sku")
    def sku(self, obj):
        return obj.variant.sku

    @admin.display(description="Product")
    def product_name(self, obj):
        return obj.variant.product.name

    @admin.display(boolean=True, description="Low stock")
    def low_stock(self, obj):
        return obj.is_low_stock
