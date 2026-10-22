from django.urls import path

from .views import (
    CartAddView,
    CartCouponView,
    CartRemoveView,
    CartUpdateView,
    CartView,
    CouponValidateView,
    MoveToCartView,
    SaveForLaterView,
    WishlistAddView,
    WishlistMoveToCartView,
    WishlistRemoveView,
    WishlistView,
)

urlpatterns = [
    path("cart/", CartView.as_view(), name="cart"),
    path("cart/add/", CartAddView.as_view(), name="cart-add"),
    path("cart/update/", CartUpdateView.as_view(), name="cart-update"),
    path("cart/remove/", CartRemoveView.as_view(), name="cart-remove"),
    path("cart/save-for-later/", SaveForLaterView.as_view(), name="cart-save-for-later"),
    path("cart/move-to-cart/", MoveToCartView.as_view(), name="cart-move-to-cart"),
    path("cart/coupon/", CartCouponView.as_view(), name="cart-coupon"),
    path("coupons/validate/", CouponValidateView.as_view(), name="coupon-validate"),
    path("wishlist/", WishlistView.as_view(), name="wishlist"),
    path("wishlist/add/", WishlistAddView.as_view(), name="wishlist-add"),
    path("wishlist/remove/", WishlistRemoveView.as_view(), name="wishlist-remove"),
    path("wishlist/move-to-cart/", WishlistMoveToCartView.as_view(), name="wishlist-move-to-cart"),
]
