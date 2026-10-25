import django_filters
from django.db.models import Exists, OuterRef

from inventory.models import Inventory

from .models import Product, ProductVariant


class ProductFilter(django_filters.FilterSet):
    category = django_filters.CharFilter(field_name="category__slug", lookup_expr="iexact")
    subcategory = django_filters.CharFilter(field_name="subcategory__slug", lookup_expr="iexact")
    brand = django_filters.CharFilter(field_name="brand__slug", lookup_expr="iexact")
    # price filters use the final price (after the product discount)
    min_price = django_filters.NumberFilter(field_name="final_min_price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="final_min_price", lookup_expr="lte")
    color = django_filters.CharFilter(method="filter_color")
    size = django_filters.CharFilter(method="filter_size")
    in_stock = django_filters.BooleanFilter(method="filter_in_stock")
    featured = django_filters.BooleanFilter(field_name="is_featured")
    min_rating = django_filters.NumberFilter(field_name="average_rating", lookup_expr="gte")

    class Meta:
        model = Product
        fields = []

    def filter_color(self, queryset, name, value):
        variants = ProductVariant.objects.filter(
            product=OuterRef("pk"), is_active=True, color__iexact=value
        )
        return queryset.filter(Exists(variants))

    def filter_size(self, queryset, name, value):
        variants = ProductVariant.objects.filter(
            product=OuterRef("pk"), is_active=True, size__iexact=value
        )
        return queryset.filter(Exists(variants))

    def filter_in_stock(self, queryset, name, value):
        stocked = Inventory.objects.filter(
            variant__product=OuterRef("pk"),
            variant__is_active=True,
            available_stock__gt=0,
        )
        return queryset.filter(Exists(stocked)) if value else queryset.exclude(Exists(stocked))
