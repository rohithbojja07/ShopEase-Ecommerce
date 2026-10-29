from reviews.models import Review

for r in Review.objects.filter(product_id=37).values(
    "id", "product_id", "rating", "is_approved", "status"
):
    print(r)
