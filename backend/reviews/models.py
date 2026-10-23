from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import TimeStampedModel
from products.models import Product


class Review(TimeStampedModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_reviews",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    title = models.CharField(max_length=150, blank=True)
    comment = models.TextField(blank=True)
    is_approved = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "user"],
                name="unique_review_per_product_user",
            ),
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name="review_rating_between_1_and_5",
            ),
        ]
        indexes = [
            models.Index(fields=["product", "is_approved"]),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.rating}/5"
