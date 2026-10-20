from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import TimeStampedModel

from .validators import validate_image_extension, validate_image_size

IMAGE_VALIDATORS = [validate_image_extension, validate_image_size]


class Category(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="categories/", blank=True, null=True, validators=IMAGE_VALIDATORS
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class SubCategory(TimeStampedModel):
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="subcategories"
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "subcategories"
        ordering = ["category__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "slug"], name="unique_subcategory_slug_per_category"
            ),
        ]

    def __str__(self):
        return f"{self.category.name} / {self.name}"


class Brand(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    logo = models.ImageField(
        upload_to="brands/", blank=True, null=True, validators=IMAGE_VALIDATORS
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products"
    )
    subcategory = models.ForeignKey(
        SubCategory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="products",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="products",
    )
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)  # soft delete flag
    view_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active", "category"]),
            models.Index(fields=["is_active", "is_featured"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if (
            self.subcategory_id
            and self.category_id
            and self.subcategory.category_id != self.category_id
        ):
            raise ValidationError(
                {"subcategory": "Subcategory does not belong to the selected category."}
            )

    def soft_delete(self):
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])


class ProductVariant(TimeStampedModel):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="variants"
    )
    sku = models.CharField(max_length=50, unique=True)
    size = models.CharField(max_length=20, blank=True)
    color = models.CharField(max_length=30, blank=True)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["product_id", "size", "color"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "size", "color"], name="unique_variant_per_product"
            ),
            models.CheckConstraint(
                condition=models.Q(price__gt=0), name="variant_price_positive"
            ),
        ]

    def __str__(self):
        return f"{self.product.name} ({self.sku})"

    @property
    def final_price(self):
        discount = self.product.discount_percent
        amount = self.price * (Decimal("100") - discount) / Decimal("100")
        return amount.quantize(Decimal("0.01"))


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="products/%Y/%m/", validators=IMAGE_VALIDATORS)
    alt_text = models.CharField(max_length=150, blank=True)
    is_primary = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"Image of {self.product.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_primary:
            ProductImage.objects.filter(
                product=self.product, is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
