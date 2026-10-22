from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


class Cart(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart"
    )
    coupon = models.ForeignKey(
        "coupons.Coupon", null=True, blank=True, on_delete=models.SET_NULL, related_name="carts"
    )

    def __str__(self):
        return f"Cart of {self.user.email}"


class CartItem(TimeStampedModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(
        "products.ProductVariant", on_delete=models.CASCADE, related_name="cart_items"
    )
    quantity = models.PositiveIntegerField(default=1)
    saved_for_later = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cart", "variant"], name="one_row_per_variant_in_cart"),
            models.CheckConstraint(condition=Q(quantity__gte=1), name="cart_quantity_at_least_1"),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.variant.sku}"


class Wishlist(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist"
    )

    def __str__(self):
        return f"Wishlist of {self.user.email}"


class WishlistItem(TimeStampedModel):
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "products.Product", on_delete=models.CASCADE, related_name="wishlist_items"
    )

    class Meta:
        constraints = [
            # the database itself blocks duplicate wishlist entries
            models.UniqueConstraint(fields=["wishlist", "product"], name="no_duplicate_wishlist_items"),
        ]

    def __str__(self):
        return f"{self.product.name} in wishlist {self.wishlist_id}"
