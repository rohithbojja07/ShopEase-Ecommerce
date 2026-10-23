from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    order_number = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ("id", "kind", "title", "message", "order", "order_number", "is_read", "created_at")
        read_only_fields = fields

    def get_order_number(self, obj):
        return obj.order.order_number if obj.order else None
