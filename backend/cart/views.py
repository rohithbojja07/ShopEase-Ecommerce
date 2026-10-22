from django.db import transaction
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from coupons.services import CouponError, check_coupon
from products.models import ProductVariant
from products.serializers import ProductListSerializer
from products.views import active_products

from .models import Cart, Wishlist, WishlistItem
from .pricing import ZERO, build_lines, calculate_cart, to_json
from .services import add_to_cart, check_quantity, purchasable_variant

# Anything the server calculates. If a client sends one of these, the request is refused.
CLIENT_CALCULATED = {
    "price", "unit_price", "final_price", "total", "subtotal", "discount", "tax", "shipping",
}


def get_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def get_wishlist(user):
    wishlist, _ = Wishlist.objects.get_or_create(user=user)
    return wishlist


def cart_response(cart):
    return Response(to_json(calculate_cart(cart)), status=status.HTTP_200_OK)


def read_id(request, key):
    raw = request.data.get(key) if hasattr(request.data, "get") else None
    if raw is None:
        raw = request.query_params.get(key)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError({key: "A valid integer is required."})
    if value < 1:
        raise ValidationError({key: "A valid integer is required."})
    return value


def preview_coupon(cart, user, code):
    active, _ = build_lines(cart)
    subtotal = sum((line["line_total"] for line in active), ZERO)
    try:
        return check_coupon(code, user, active, subtotal)
    except CouponError as exc:
        raise ValidationError({"code": [str(exc)]})


class AuthenticatedAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        data = request.data
        if hasattr(data, "keys"):
            bad = sorted(CLIENT_CALCULATED & set(data.keys()))
            if bad:
                raise ValidationError({
                    "detail": "These values are calculated by the server and cannot be sent: "
                    + ", ".join(bad) + "."
                })


class AddSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, default=1)


class UpdateSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1)


class VariantIdSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)


class CouponCodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=30)


class ProductIdSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1)


class MoveToCartSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1)
    variant_id = serializers.IntegerField(min_value=1, required=False)
    quantity = serializers.IntegerField(min_value=1, default=1)


# ------------------------------ cart ------------------------------
class CartView(AuthenticatedAPIView):
    def get(self, request):
        return cart_response(get_cart(request.user))


class CartAddView(AuthenticatedAPIView):
    def post(self, request):
        data = AddSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        variant = purchasable_variant(data.validated_data["variant_id"])
        cart = get_cart(request.user)
        add_to_cart(cart, variant, data.validated_data["quantity"])
        return cart_response(cart)


class CartUpdateView(AuthenticatedAPIView):
    def patch(self, request):
        data = UpdateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        cart = get_cart(request.user)
        item = cart.items.filter(variant_id=data.validated_data["variant_id"]).first()
        if item is None:
            raise NotFound("This item is not in your cart.")
        variant = purchasable_variant(item.variant_id)
        check_quantity(variant, data.validated_data["quantity"])
        item.quantity = data.validated_data["quantity"]
        item.save(update_fields=["quantity", "updated_at"])
        return cart_response(cart)


class CartRemoveView(AuthenticatedAPIView):
    def delete(self, request):
        variant_id = read_id(request, "variant_id")
        cart = get_cart(request.user)
        deleted, _ = cart.items.filter(variant_id=variant_id).delete()
        if not deleted:
            raise NotFound("This item is not in your cart.")
        return cart_response(cart)


class SaveForLaterView(AuthenticatedAPIView):
    def post(self, request):
        data = VariantIdSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        cart = get_cart(request.user)
        item = cart.items.filter(variant_id=data.validated_data["variant_id"]).first()
        if item is None:
            raise NotFound("This item is not in your cart.")
        item.saved_for_later = True
        item.save(update_fields=["saved_for_later", "updated_at"])
        return cart_response(cart)


class MoveToCartView(AuthenticatedAPIView):
    def post(self, request):
        data = VariantIdSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        cart = get_cart(request.user)
        item = cart.items.filter(
            variant_id=data.validated_data["variant_id"], saved_for_later=True
        ).first()
        if item is None:
            raise NotFound("This item is not saved for later.")
        check_quantity(purchasable_variant(item.variant_id), item.quantity)
        item.saved_for_later = False
        item.save(update_fields=["saved_for_later", "updated_at"])
        return cart_response(cart)


class CartCouponView(AuthenticatedAPIView):
    def post(self, request):
        data = CouponCodeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        cart = get_cart(request.user)
        coupon, _ = preview_coupon(cart, request.user, data.validated_data["code"])
        cart.coupon = coupon
        cart.save(update_fields=["coupon", "updated_at"])
        return cart_response(cart)

    def delete(self, request):
        cart = get_cart(request.user)
        cart.coupon = None
        cart.save(update_fields=["coupon", "updated_at"])
        return cart_response(cart)


class CouponValidateView(AuthenticatedAPIView):
    """Preview a coupon against the current cart without applying it."""

    def post(self, request):
        data = CouponCodeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        cart = get_cart(request.user)
        coupon, discount = preview_coupon(cart, request.user, data.validated_data["code"])
        return Response({
            "valid": True,
            "code": coupon.code,
            "description": coupon.description,
            "discount": str(discount),
        })


# ----------------------------- wishlist -----------------------------
class WishlistView(AuthenticatedAPIView):
    def get(self, request):
        wishlist = get_wishlist(request.user)
        ids = list(wishlist.items.order_by("-created_at").values_list("product_id", flat=True))
        found = {p.id: p for p in active_products().filter(id__in=ids)}
        ordered = [found[i] for i in ids if i in found]
        data = ProductListSerializer(ordered, many=True, context={"request": request}).data
        return Response({"count": len(ordered), "results": data})


class WishlistAddView(AuthenticatedAPIView):
    def post(self, request):
        data = ProductIdSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        product = active_products().filter(pk=data.validated_data["product_id"]).first()
        if product is None:
            raise NotFound("This product is not available.")
        wishlist = get_wishlist(request.user)
        _, created = WishlistItem.objects.get_or_create(wishlist=wishlist, product_id=product.id)
        if created:
            return Response({"detail": "Added to wishlist."}, status=status.HTTP_201_CREATED)
        return Response({"detail": "Already in your wishlist."}, status=status.HTTP_200_OK)


class WishlistRemoveView(AuthenticatedAPIView):
    def delete(self, request):
        product_id = read_id(request, "product_id")
        wishlist = get_wishlist(request.user)
        deleted, _ = wishlist.items.filter(product_id=product_id).delete()
        if not deleted:
            raise NotFound("This product is not in your wishlist.")
        return Response({"detail": "Removed from wishlist."})


class WishlistMoveToCartView(AuthenticatedAPIView):
    def post(self, request):
        data = MoveToCartSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        product_id = data.validated_data["product_id"]
        wishlist = get_wishlist(request.user)
        entry = wishlist.items.filter(product_id=product_id).first()
        if entry is None:
            raise NotFound("This product is not in your wishlist.")

        variant_id = data.validated_data.get("variant_id")
        if variant_id:
            variant = purchasable_variant(variant_id)
            if variant.product_id != product_id:
                raise ValidationError({"variant_id": "This variant belongs to a different product."})
        else:
            variant = (
                ProductVariant.objects.select_related("product__category", "inventory")
                .filter(
                    product_id=product_id,
                    is_active=True,
                    product__is_active=True,
                    product__category__is_active=True,
                    inventory__available_stock__gt=0,
                )
                .order_by("price")
                .first()
            )
            if variant is None:
                raise ValidationError({"detail": "No variant of this product is in stock."})

        cart = get_cart(request.user)
        with transaction.atomic():
            add_to_cart(cart, variant, data.validated_data["quantity"])
            entry.delete()
        return cart_response(cart)
