from django.contrib.auth import get_user_model
from products.models import Product
from reviews.models import Review

User = get_user_model()

demo_reviews = [
    (5, "Great product", "Good overall experience and useful features."),
    (4, "Good value", "Works well for everyday use."),
    (5, "Satisfied with my purchase", "Happy with the product and its performance."),
]

users = list(User.objects.order_by("id"))

if not users:
    print("ERROR: No users exist. Create test users before generating reviews.")
else:
    created_count = 0
    skipped_count = 0

    for product in Product.objects.order_by("id"):
        product_created = 0

        for rating, title, comment in demo_reviews:
            # Find a user who has not already reviewed this product.
            reviewer = next(
                (
                    user for user in users
                    if not Review.objects.filter(
                        product_id=product.id,
                        user_id=user.id,
                    ).exists()
                ),
                None,
            )

            if reviewer is None:
                print(
                    f"SKIPPED: {product.name} has no unused reviewer accounts "
                    "available for additional reviews."
                )
                break

            review = Review(
                product=product,
                user=reviewer,
                rating=rating,
                title=title,
                comment=comment,
                is_approved=True,
                status=Review.Status.PUBLISHED,
            )
            review.save()

            created_count += 1
            product_created += 1

        if product_created:
            print(f"CREATED: {product_created} demo review(s) for {product.name}")

    print(f"\nFinished. New demo reviews created: {created_count}")
    print("Existing reviews were preserved.")
