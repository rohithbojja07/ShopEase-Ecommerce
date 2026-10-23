from django.conf import settings
from products.validators import validate_image_extension, validate_image_size
from rest_framework import serializers

from .models import ReturnEvent, ReturnEvidence, ReturnItem, ReturnReason, ReturnRequest


class ReturnItemInput(serializers.Serializer):
    order_item_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1)


class CreateReturnSerializer(serializers.Serializer):
    order_id = serializers.IntegerField(min_value=1)
    reason = serializers.ChoiceField(choices=ReturnReason.choices)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    items = ReturnItemInput(many=True, required=False)


class EvidenceUploadSerializer(serializers.Serializer):
    images = serializers.ListField(
        child=serializers.ImageField(validators=[validate_image_extension, validate_image_size]),
        allow_empty=False,
        max_length=getattr(settings, "MAX_RETURN_EVIDENCE_IMAGES", 5),
    )


class ReturnItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="order_item.product_name", read_only=True)
    sku = serializers.CharField(source="order_item.sku", read_only=True)

    class Meta:
        model = ReturnItem
        fields = ("order_item", "product_name", "sku", "quantity")


class ReturnEvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReturnEvidence
        fields = ("id", "image", "created_at")


class ReturnEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReturnEvent
        fields = ("status", "note", "created_at")


class ReturnSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    reason_label = serializers.CharField(source="get_reason_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    items = ReturnItemSerializer(many=True, read_only=True)
    evidence = ReturnEvidenceSerializer(many=True, read_only=True)
    events = ReturnEventSerializer(many=True, read_only=True)
    refund = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    can_add_evidence = serializers.SerializerMethodField()

    class Meta:
        model = ReturnRequest
        fields = (
            "id", "return_number", "order", "order_number", "reason", "reason_label",
            "description", "status", "status_label", "refund_amount", "admin_note",
            "items", "evidence", "events", "refund", "can_cancel", "can_add_evidence",
            "created_at",
        )
        read_only_fields = fields

    def get_refund(self, obj):
        refund = getattr(obj, "refund", None)
        if refund is None:
            return None
        return {
            "amount": str(refund.amount),
            "transaction_reference": refund.transaction_reference,
            "processed_at": refund.processed_at,
        }

    def get_can_cancel(self, obj):
        return obj.status == "REQUESTED"

    def get_can_add_evidence(self, obj):
        return obj.status == "REQUESTED"
