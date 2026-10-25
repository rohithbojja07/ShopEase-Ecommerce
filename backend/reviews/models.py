from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel
from products.models import Product
from products.validators import validate_image_extension, validate_image_size


REVIEW_IMAGE_VALIDATORS = [validate_image_extension, validate_image_size]


class Review(TimeStampedModel):
    class Status(models.TextChoices):
        PUBLISHED = "PUBLISHED", "Published"
        HIDDEN = "HIDDEN", "Hidden"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="product_reviews")
    order_item = models.ForeignKey(
        "orders.OrderItem", on_delete=models.PROTECT,
        related_name="reviews", null=True, blank=True,
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title = models.CharField(max_length=150)
    comment = models.TextField(blank=True)
    is_approved = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PUBLISHED, db_index=True)
    moderation_note = models.CharField(max_length=200, blank=True)
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="moderated_product_reviews",
    )
    moderated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "user"], name="unique_review_per_product_user"),
            models.CheckConstraint(condition=Q(rating__gte=1, rating__lte=5), name="review_rating_between_1_and_5"),
        ]
        indexes = [
            models.Index(fields=["product", "is_approved"], name="reviews_rev_product_99e47c_idx"),
            models.Index(fields=["product", "status"], name="review_product_status_idx"),
        ]

    @property
    def body(self):
        return self.comment

    @body.setter
    def body(self, value):
        self.comment = value

    @property
    def reviewer(self):
        first = (self.user.first_name or "").strip()
        last = (self.user.last_name or "").strip()
        if first and last:
            return f"{first} {last[0]}."
        return first or last or "Customer"

    @property
    def verified_purchase(self):
        return self.order_item_id is not None

    @property
    def helpful_count(self):
        return self.votes.filter(helpful=True).count()

    @property
    def not_helpful_count(self):
        return self.votes.filter(helpful=False).count()

    def __str__(self):
        return f"{self.product.name} - {self.rating}/5"


class ReviewImage(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(
        upload_to="reviews/%Y/%m/", validators=REVIEW_IMAGE_VALIDATORS
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"Image for review {self.review_id}"


class ReviewVote(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_votes")
    helpful = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["review", "user"], name="unique_review_vote_per_user"),
        ]
        indexes = [
            models.Index(fields=["review", "helpful"], name="review_vote_count_idx"),
        ]

    def __str__(self):
        return f"Vote by {self.user_id} on review {self.review_id}"
