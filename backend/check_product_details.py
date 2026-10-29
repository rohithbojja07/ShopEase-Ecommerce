from products.models import Product

for p in Product.objects.order_by("id"):
    print(
        f"ID={p.id} | {p.name} | "
        f"Features={len(p.key_features or [])} | "
        f"Specifications={len(p.specifications or {})}"
    )
