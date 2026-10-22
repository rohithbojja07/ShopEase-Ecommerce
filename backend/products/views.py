from decimal import Decimal

from django.db.models import (
    DecimalField, Exists, ExpressionWrapper, F, OuterRef, Prefetch, Subquery, Value,
)
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from inventory.models import Inventory

from .filters import ProductFilter
from .models import Brand, Category, Product, ProductVariant, SubCategory
from .serializers import (
    BrandSerializer,
    CategorySerializer,
    ProductDetailSerializer,
    ProductListSerializer,
)


def active_products():
    """Only active products that have at least one active variant."""
    cheapest = (
        ProductVariant.objects.filter(product=OuterRef("pk"), is_active=True)
        .order_by("price")
        .values("price")[:1]
    )
    stocked = Inventory.objects.filter(
        variant__product=OuterRef("pk"),
        variant__is_active=True,
        available_stock__gt=0,
    )
    return (
        Product.objects.filter(is_active=True, category__is_active=True)
        .select_related("category", "subcategory", "brand")
        .prefetch_related(
            "images",
            Prefetch(
                "variants",
                queryset=ProductVariant.objects.filter(is_active=True).select_related("inventory"),
            ),
        )
        .annotate(min_price=Subquery(cheapest), in_stock=Exists(stocked))
        .filter(min_price__isnull=False)
        .annotate(
            final_min_price=ExpressionWrapper(
                F("min_price")
                * (Value(Decimal("100")) - F("discount_percent"))
                / Value(Decimal("100")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
    )


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    filterset_class = ProductFilter
    search_fields = [
        "name", "description", "brand__name", "category__name", "subcategory__name",
    ]
    ordering_fields = ["name", "created_at", "final_min_price", "view_count"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        return active_products()

    def get_serializer_class(self):
        return ProductDetailSerializer if self.action == "retrieve" else ProductListSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # atomic counter update (used for "most viewed products" analytics later)
        Product.objects.filter(pk=instance.pk).update(view_count=F("view_count") + 1)
        instance.view_count += 1
        return Response(self.get_serializer(instance).data)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = CategorySerializer
    pagination_class = None
    search_fields = ["name"]

    def get_queryset(self):
        return Category.objects.filter(is_active=True).prefetch_related(
            Prefetch("subcategories", queryset=SubCategory.objects.filter(is_active=True))
        )


class BrandViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = BrandSerializer
    pagination_class = None
    search_fields = ["name"]

    def get_queryset(self):
        return Brand.objects.filter(is_active=True)
