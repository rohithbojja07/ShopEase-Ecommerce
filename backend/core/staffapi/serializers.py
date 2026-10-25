from django.contrib.auth import get_user_model
from django.utils.text import slugify
from rest_framework import serializers

from accounts.serializers import AddressSerializer
from core.models import AuditLog
from inventory.models import Inventory
from orders.serializers import OrderDetailSerializer, OrderListSerializer
from orders.serializers_returns import ReturnSerializer
from products.models import Brand, Category, Product, ProductImage, ProductVariant

User = get_user_model()
STAFF_STATUS_CHOICES = ["PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"]


def unique_slug(model, text):
    base = slugify(text)[:100] or "item"
    slug, number = base, 2
    while model.objects.filter(slug=slug).exists():
        slug = f"{base}-{number}"
        number += 1
    return slug


class SlugFromNameMixin:
    """A new record without a slug gets one made from its name."""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is None and not attrs.get("slug"):
            attrs["slug"] = unique_slug(self.Meta.model, attrs.get("name", ""))
        return attrs


class AdminCategorySerializer(SlugFromNameMixin, serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug", "description", "is_active")
        extra_kwargs = {"slug": {"required": False}}


class AdminBrandSerializer(SlugFromNameMixin, serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ("id", "name", "slug", "is_active")
        extra_kwargs = {"slug": {"required": False}}


class AdminProductSerializer(SlugFromNameMixin, serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = (
            "id", "name", "slug", "description", "category", "subcategory", "brand",
            "discount_percent", "is_featured", "is_active", "view_count", "created_at",
        )
        read_only_fields = ("id", "view_count", "created_at")
        extra_kwargs = {"slug": {"required": False}}

    def validate(self, attrs):
        attrs = super().validate(attrs)
        category = attrs.get("category", getattr(self.instance, "category", None))
        subcategory = attrs.get("subcategory", getattr(self.instance, "subcategory", None))
        if subcategory and category and subcategory.category_id != category.id:
            raise serializers.ValidationError(
                {"subcategory": "Subcategory does not belong to the selected category."}
            )
        return attrs


class AdminVariantSerializer(serializers.ModelSerializer):
    final_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    available_stock = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = (
            "id", "product", "sku", "size", "color", "price",
            "final_price", "is_active", "available_stock",
        )
        extra_kwargs = {
            "size": {"required": False, "default": ""},
            "color": {"required": False, "default": ""},
        }

    def get_available_stock(self, obj):
        inventory = getattr(obj, "inventory", None)
        return inventory.available_stock if inventory else 0


class AdminImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ("id", "image", "alt_text", "is_primary", "sort_order")


class AdminInventorySerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="variant.sku", read_only=True)
    product = serializers.CharField(source="variant.product.name", read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Inventory
        fields = (
            "id", "variant", "sku", "product", "opening_stock", "available_stock",
            "reserved_stock", "sold_stock", "returned_stock", "low_stock_threshold",
            "is_low_stock",
        )
        # only the threshold can be edited here. Stock changes go through /adjust/.
        read_only_fields = (
            "id", "variant", "opening_stock", "available_stock",
            "reserved_stock", "sold_stock", "returned_stock",
        )


class StockAdjustSerializer(serializers.Serializer):
    quantity = serializers.IntegerField()
    reason = serializers.CharField(max_length=200)

    def validate_quantity(self, value):
        if value == 0:
            raise serializers.ValidationError("The quantity cannot be zero.")
        return value


class OrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=STAFF_STATUS_CHOICES)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class ReturnNoteSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class StaffOrderListSerializer(OrderListSerializer):
    customer = serializers.EmailField(source="user.email", read_only=True)

    class Meta(OrderListSerializer.Meta):
        fields = OrderListSerializer.Meta.fields + ("customer",)


class StaffOrderDetailSerializer(OrderDetailSerializer):
    customer = serializers.EmailField(source="user.email", read_only=True)

    class Meta(OrderDetailSerializer.Meta):
        fields = OrderDetailSerializer.Meta.fields + ("customer",)


class StaffReturnSerializer(ReturnSerializer):
    customer = serializers.EmailField(source="user.email", read_only=True)

    class Meta(ReturnSerializer.Meta):
        fields = ReturnSerializer.Meta.fields + ("customer", "restock_items")
        read_only_fields = fields


class CustomerListSerializer(serializers.ModelSerializer):
    order_count = serializers.IntegerField(read_only=True)
    total_paid = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total_refunded = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    net_spent = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = User
        fields = (
            "id", "email", "first_name", "last_name", "is_active", "is_email_verified",
            "date_joined", "last_login", "order_count", "total_paid", "total_refunded",
            "net_spent",
        )
        read_only_fields = fields


class CustomerDetailSerializer(CustomerListSerializer):
    addresses = AddressSerializer(many=True, read_only=True)
    recent_orders = serializers.SerializerMethodField()

    class Meta(CustomerListSerializer.Meta):
        fields = CustomerListSerializer.Meta.fields + ("addresses", "recent_orders")
        read_only_fields = fields

    def get_recent_orders(self, obj):
        orders = obj.orders.prefetch_related("items", "payments").order_by("-created_at", "-id")[:5]
        return StaffOrderListSerializer(orders, many=True).data


class AuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = (
            "id", "actor", "actor_email", "action", "target_type", "target_id",
            "target_repr", "details", "ip_address", "created_at",
        )
        read_only_fields = fields

    def get_actor_email(self, obj):
        return obj.actor.email if obj.actor else None
