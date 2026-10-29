from reviews.models import Review

print("Total reviews:", Review.objects.count())

for r in Review.objects.select_related("product", "user").order_by("-id"):
    print(
        f"Review ID={r.id} | Product ID={r.product_id} | "
        f"Product={r.product.name} | Rating={r.rating} | "
        f"Approved={r.is_approved} | Status={r.status}"
    )
