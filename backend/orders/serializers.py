from rest_framework import serializers

from payments.serializers import PaymentSerializer

from .models import Order, OrderItem, OrderStatusHistory, Shipment


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = (
            "id", "product_name", "sku", "size", "color",
            "unit_mrp", "unit_price", "quantity", "line_total",
        )


class StatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ("status", "note", "created_at")


class ShipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shipment
        fields = (
            "carrier", "tracking_number", "status",
            "shipped_at", "expected_delivery", "delivered_at",
        )


class OrderListSerializer(serializers.ModelSerializer):
    payment_status = serializers.CharField(read_only=True)
    item_count = serializers.SerializerMethodField()
    items_preview = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id", "order_number", "status", "payment_status", "total",
            "item_count", "items_preview", "created_at",
        )

    def get_item_count(self, obj):
        return sum(item.quantity for item in obj.items.all())

    def get_items_preview(self, obj):
        return [item.product_name for item in list(obj.items.all())[:3]]


class OrderDetailSerializer(OrderListSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    timeline = StatusHistorySerializer(source="history", many=True, read_only=True)
    shipment = serializers.SerializerMethodField()
    can_cancel = serializers.BooleanField(read_only=True)

    class Meta(OrderListSerializer.Meta):
        fields = OrderListSerializer.Meta.fields + (
            "shipping_method", "shipping_address", "billing_address",
            "subtotal_mrp", "product_discount", "subtotal",
            "coupon_code", "coupon_discount", "tax", "shipping_fee",
            "expires_at", "cancelled_at", "delivered_at", "can_cancel",
            "items", "payments", "shipment", "timeline",
        )

    def get_shipment(self, obj):
        shipment = getattr(obj, "shipment", None)
        return ShipmentSerializer(shipment).data if shipment else None
