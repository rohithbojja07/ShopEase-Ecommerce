from products.models import Product
from reviews.models import Review

for product in Product.objects.order_by("id"):
    count = Review.objects.filter(
        product=product,
        is_approved=True,
        status=Review.Status.PUBLISHED,
    ).count()

    print(f"{product.name}: {count} published review(s)")
