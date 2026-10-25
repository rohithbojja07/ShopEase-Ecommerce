from rest_framework import serializers

from products.models import Product
from .models import Review, ReviewImage, ReviewVote


class ReviewImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewImage
        fields = ("id", "image", "created_at")
        read_only_fields = ("id", "created_at")


class ReviewSerializer(serializers.ModelSerializer):
    reviewer = serializers.CharField(read_only=True)
    verified_purchase = serializers.BooleanField(read_only=True)
    images = ReviewImageSerializer(many=True, read_only=True)

    class Meta:
        model = Review
        fields = (
            "id",
            "product",
            "user",
            "rating",
            "title",
            "comment",
            "reviewer",
            "verified_purchase",
            "status",
            "is_approved",
            "images",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "product",
            "user",
            "reviewer",
            "verified_purchase",
            "status",
            "is_approved",
            "images",
            "created_at",
            "updated_at",
        )


class ReviewCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1)
    rating = serializers.IntegerField(min_value=1, max_value=5)
    title = serializers.CharField(max_length=150, allow_blank=False, trim_whitespace=True)
    body = serializers.CharField(required=False, allow_blank=True)
    images = serializers.ListField(
        child=serializers.ImageField(),
        required=False,
        allow_empty=True,
        max_length=5,
        write_only=True,
    )

    def validate_product_id(self, value):
        if value <= 0:
            raise serializers.ValidationError("A valid product ID is required.")
        return value

class ReviewVoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewVote
        fields = ("helpful",)


class PublicReviewSerializer(serializers.ModelSerializer):
    reviewer = serializers.CharField(read_only=True)
    verified_purchase = serializers.BooleanField(read_only=True)
    helpful_count = serializers.IntegerField(read_only=True)
    not_helpful_count = serializers.IntegerField(read_only=True)
    my_vote = serializers.SerializerMethodField()

    def get_my_vote(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        vote = obj.votes.filter(user=request.user).first()
        return vote.helpful if vote else None

    class Meta:
        model = Review
        fields = (
            "id",
            "product",
            "rating",
            "title",
            "comment",
            "reviewer",
            "verified_purchase",
            "helpful_count",
            "not_helpful_count",
            "my_vote",
            "created_at",
        )


class StaffReviewSerializer(serializers.ModelSerializer):
    customer = serializers.EmailField(source="user.email", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    reviewer = serializers.CharField(read_only=True)

    class Meta:
        model = Review
        fields = (
            "id",
            "product",
            "product_name",
            "user",
            "customer",
            "reviewer",
            "rating",
            "title",
            "comment",
            "body",
            "status",
            "is_approved",
            "moderation_note",
            "moderated_by",
            "moderated_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
