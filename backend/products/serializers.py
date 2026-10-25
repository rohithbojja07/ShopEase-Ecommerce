from rest_framework import serializers

from .models import Brand, Category, Product, ProductImage, ProductVariant, SubCategory


class SubCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubCategory
        fields = ("id", "name", "slug")


class CategorySerializer(serializers.ModelSerializer):
    subcategories = SubCategorySerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ("id", "name", "slug", "description", "image", "subcategories")


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ("id", "name", "slug", "logo")


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ("id", "image", "alt_text", "is_primary")


class ProductVariantSerializer(serializers.ModelSerializer):
    final_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    in_stock = serializers.SerializerMethodField()
    low_stock = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = ("id", "sku", "size", "color", "price", "final_price", "in_stock", "low_stock")

    def _inventory(self, obj):
        return getattr(obj, "inventory", None)

    def get_in_stock(self, obj):
        inv = self._inventory(obj)
        return bool(inv and inv.available_stock > 0)

    def get_low_stock(self, obj):
        inv = self._inventory(obj)
        return bool(inv and 0 < inv.available_stock <= inv.low_stock_threshold)


class ProductListSerializer(serializers.ModelSerializer):
    brand = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    min_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    final_min_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.IntegerField(read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id", "name", "slug", "brand", "category", "discount_percent",
            "min_price", "final_min_price", "in_stock", "is_featured", "image", "average_rating", "review_count",
        )

    def get_average_rating(self, obj):
        return round(obj.average_rating, 2) if getattr(obj, "review_count", 0) else None

    def get_brand(self, obj):
        return obj.brand.name if obj.brand else None

    def get_category(self, obj):
        return obj.category.name

    def get_image(self, obj):
        images = list(obj.images.all())
        if not images:
            return None
        primary = next((i for i in images if i.is_primary), images[0])
        request = self.context.get("request")
        url = primary.image.url
        return request.build_absolute_uri(url) if request else url


class ProductDetailSerializer(ProductListSerializer):
    subcategory = serializers.SerializerMethodField()
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + (
            "description", "subcategory", "variants", "images", "view_count",
        )

    def get_subcategory(self, obj):
        return obj.subcategory.name if obj.subcategory else None
