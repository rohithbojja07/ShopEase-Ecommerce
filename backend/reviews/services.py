from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError as DjangoValidationError

from orders.models import OrderItem, OrderStatus
from .models import Review, ReviewImage
from PIL import Image, UnidentifiedImageError

MAX_REVIEW_IMAGES = 5


class ReviewError(Exception):
    """A review problem with a safe message for the API."""


def purchased_item(user, product_id):
    return (
        OrderItem.objects.filter(
            order__user=user,
            order__status=OrderStatus.DELIVERED,
            variant__product_id=product_id,
        )
        .order_by("-order__delivered_at", "-id")
        .first()
    )


def eligibility(user, product_id):
    if Review.objects.filter(user=user, product_id=product_id).exists():
        return False, "You have already reviewed this product."

    if purchased_item(user, product_id) is None:
        return False, "Only customers who have received this product can review it."

    return True, ""


def create_review(user, product, rating, title, body):
    allowed, reason = eligibility(user, product.id)
    if not allowed:
        raise ReviewError(reason)

    try:
        with transaction.atomic():
            item = purchased_item(user, product.id)
            if item is None:
                raise ReviewError(
                    "Only customers who have received this product can review it."
                )

            review = Review.objects.create(
                product=product,
                user=user,
                order_item=item,
                rating=rating,
                title=title,
                comment=body,
                status=Review.Status.PUBLISHED,
                is_approved=True,
            )
            return review

    except IntegrityError as exc:
        raise ReviewError("You have already reviewed this product.") from exc


def add_images(review, files):
    files = list(files)

    if review.images.count() + len(files) > MAX_REVIEW_IMAGES:
        raise ReviewError(
            f"A review can have at most {MAX_REVIEW_IMAGES} images."
        )

    created = []

    try:
        with transaction.atomic():
            for image in files:
                # Check the file contents, not just its extension or content type.
                try:
                    image.seek(0)
                    with Image.open(image) as opened_image:
                        opened_image.verify()
                    image.seek(0)
                except (UnidentifiedImageError, OSError, ValueError) as exc:
                    raise ReviewError(
                        "One or more images are invalid. Upload valid image files."
                    ) from exc

                review_image = ReviewImage(review=review, image=image)
                review_image.full_clean()
                review_image.save()
                created.append(review_image)
    except DjangoValidationError as exc:
        raise ReviewError(
            "One or more images are invalid. Upload valid image files."
        ) from exc

    return created
