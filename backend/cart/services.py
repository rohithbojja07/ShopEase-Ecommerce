from django.conf import settings
from rest_framework.exceptions import NotFound, ValidationError

from products.models import ProductVariant

from .models import CartItem


def max_quantity():
    return int(getattr(settings, "MAX_CART_QUANTITY", 10))


def purchasable_variant(variant_id):
    variant = (
        ProductVariant.objects.select_related("product__category", "inventory")
        .filter(
            pk=variant_id,
            is_active=True,
            product__is_active=True,
            product__category__is_active=True,
        )
        .first()
    )
    if variant is None:
        raise NotFound("This item is not available.")
    return variant


def check_quantity(variant, quantity):
    if quantity > max_quantity():
        raise ValidationError({"quantity": f"You can buy at most {max_quantity()} of one item."})
    inventory = getattr(variant, "inventory", None)
    available = inventory.available_stock if inventory else 0
    if available <= 0:
        raise ValidationError({"quantity": "Out of stock."})
    if quantity > available:
        raise ValidationError({"quantity": f"Only {available} in stock."})


def add_to_cart(cart, variant, quantity):
    existing = cart.items.filter(variant=variant).first()
    current = existing.quantity if existing and not existing.saved_for_later else 0
    new_quantity = current + quantity
    check_quantity(variant, new_quantity)
    item, _ = CartItem.objects.update_or_create(
        cart=cart,
        variant=variant,
        defaults={"quantity": new_quantity, "saved_for_later": False},
    )
    return item
