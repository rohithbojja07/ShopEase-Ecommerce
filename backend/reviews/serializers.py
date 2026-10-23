from rest_framework import serializers

from products.models import Product
from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Review
        fields = (
            "id",
            "product",
            "user",
            "user_email",
            "rating",
            "title",
            "comment",
            "is_approved",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "user",
            "user_email",
            "is_approved",
            "created_at",
            "updated_at",
        )

    def validate_product(self, product):
        if not product.is_active or not product.category.is_active:
            raise serializers.ValidationError(
                "Reviews cannot be submitted for inactive products."
            )
        return product
