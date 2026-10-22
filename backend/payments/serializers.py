from rest_framework import serializers

from .models import Payment, PaymentMethod


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "id", "order", "user", "amount", "method", "status",
            "transaction_reference", "failure_reason", "paid_at", "created_at",
        )
        read_only_fields = fields


class CreatePaymentSerializer(serializers.Serializer):
    order_id = serializers.IntegerField(min_value=1)
    method = serializers.ChoiceField(choices=PaymentMethod.choices, default=PaymentMethod.CARD)


class VerifyPaymentSerializer(serializers.Serializer):
    payment_id = serializers.IntegerField(min_value=1)
    transaction_reference = serializers.CharField(max_length=40)
    token = serializers.CharField(max_length=40)
