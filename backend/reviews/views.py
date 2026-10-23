from django.db.models import Avg, Count
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Review
from .serializers import ReviewSerializer


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = Review.objects.select_related(
            "product", "product__category", "user"
        )

        if self.action == "list" or self.action == "retrieve":
            queryset = queryset.filter(is_approved=True)
        elif self.request.user.is_authenticated and not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)

        product_id = self.request.query_params.get("product")
        if product_id:
            queryset = queryset.filter(product_id=product_id)

        return queryset

    def perform_create(self, serializer):
        product = serializer.validated_data["product"]

        if Review.objects.filter(
            product=product, user=self.request.user
        ).exists():
            raise ValidationError(
                {"product": "You have already reviewed this product."}
            )

        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        if not self.request.user.is_staff:
            if serializer.instance.user_id != self.request.user.id:
                raise permissions.PermissionDenied(
                    "You can only update your own review."
                )
        serializer.save()

    def perform_destroy(self, instance):
        if not self.request.user.is_staff:
            if instance.user_id != self.request.user.id:
                raise permissions.PermissionDenied(
                    "You can only delete your own review."
                )
        instance.delete()

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[permissions.AllowAny],
        url_path="summary",
    )
    def summary(self, request):
        product_id = request.query_params.get("product")

        if not product_id:
            raise ValidationError(
                {"product": "Provide a product ID, e.g. ?product=1"}
            )

        stats = Review.objects.filter(
            product_id=product_id,
            is_approved=True,
        ).aggregate(
            average_rating=Avg("rating"),
            review_count=Count("id"),
        )

        return Response({
            "product": product_id,
            "average_rating": round(stats["average_rating"], 2)
            if stats["average_rating"] is not None else None,
            "review_count": stats["review_count"],
        })
