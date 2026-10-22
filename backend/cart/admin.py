from django.contrib import admin

from .models import Cart, CartItem, Wishlist


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    can_delete = False
    readonly_fields = ("variant", "quantity", "saved_for_later")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "item_count", "coupon", "updated_at")
    search_fields = ("user__email",)
    inlines = [CartItemInline]

    @admin.display(description="Items")
    def item_count(self, obj):
        return obj.items.count()


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ("user", "item_count")
    search_fields = ("user__email",)

    @admin.display(description="Items")
    def item_count(self, obj):
        return obj.items.count()
