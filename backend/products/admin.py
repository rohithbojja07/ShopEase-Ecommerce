from django.contrib import admin

from .models import Brand, Category, Product, ProductImage, ProductVariant, SubCategory


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("name", "category__name")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "brand",
        "discount_percent",
        "is_featured",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "is_featured", "category", "brand")
    search_fields = ("name", "description", "variants__sku")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("view_count",)
    inlines = [ProductVariantInline, ProductImageInline]
    actions = ["deactivate_products", "activate_products"]

    def has_delete_permission(self, request, obj=None):
        # soft delete only: products are deactivated, never removed
        return False

    @admin.action(description="Deactivate selected products (soft delete)", permissions=["change"])
    def deactivate_products(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} product(s) deactivated.")

    @admin.action(description="Activate selected products", permissions=["change"])
    def activate_products(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"{count} product(s) activated.")
