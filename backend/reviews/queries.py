from django.db.models import Avg, Count, FloatField, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from .models import Review


def rating_annotations():
    published = Review.objects.filter(
        product_id=OuterRef("pk"),
        status=Review.Status.PUBLISHED,
        is_approved=True,
    ).order_by()

    average = (
        published.values("product_id")
        .annotate(value=Avg("rating"))
        .values("value")[:1]
    )

    count = (
        published.values("product_id")
        .annotate(value=Count("id"))
        .values("value")[:1]
    )

    return {
        "average_rating": Coalesce(
            Subquery(average, output_field=FloatField()),
            Value(0.0),
            output_field=FloatField(),
        ),
        "review_count": Coalesce(
            Subquery(count, output_field=IntegerField()),
            Value(0),
            output_field=IntegerField(),
        ),
    }
