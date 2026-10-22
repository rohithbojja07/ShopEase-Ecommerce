from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase

from cart.models import WishlistItem
from coupons.models import Coupon, CouponUsage
from coupons.services import INVALID, CouponError, redeem_coupon
from inventory.models import Inventory
from products.models import Category, Product, ProductVariant

User = get_user_model()
PASSWORD = "Str0ng!Pass#2026"


def make_product(name, category, price, stock, discount="0"):
    product = Product.objects.create(
        name=name,
        slug=name.lower().replace(" ", "-"),
        category=category,
        discount_percent=Decimal(discount),
    )
    variant = ProductVariant.objects.create(
        product=product, sku=name.upper().replace(" ", "-"), price=Decimal(price)
    )
    Inventory.objects.filter(variant=variant).update(opening_stock=stock, available_stock=stock)
    return product, variant


def make_coupon(code="SAVE10", **extra):
    data = {
        "code": code,
        "discount_type": Coupon.DiscountType.PERCENT,
        "value": Decimal("10"),
        "valid_until": timezone.now() + timedelta(days=30),
    }
    data.update(extra)
    return Coupon.objects.create(**data)


class ShopTestCase(APITestCase):
    def setUp(self):
        cache.clear()  # reset rate limiting between tests
        self.alice = User.objects.create_user(email="alice@example.com", password=PASSWORD)
        self.bob = User.objects.create_user(email="bob@example.com", password=PASSWORD)
        self.phones = Category.objects.create(name="Phones", slug="phones")
        self.laptops = Category.objects.create(name="Laptops", slug="laptops")
        # price 1000 with 10% off = 900 each
        self.phone, self.phone_v = make_product("Test Phone", self.phones, "1000.00", 5, "10")
        self.laptop, self.laptop_v = make_product("Test Laptop", self.laptops, "50000.00", 3)
        self.cable, self.cable_v = make_product("Test Cable", self.phones, "200.00", 20)
        self.client.force_authenticate(self.alice)

    def add(self, variant, quantity=1, **extra):
        body = {"variant_id": variant.id, "quantity": quantity, **extra}
        return self.client.post("/api/cart/add/", body, format="json")

    def cart(self):
        return self.client.get("/api/cart/").data

    def apply(self, code):
        return self.client.post("/api/cart/coupon/", {"code": code}, format="json")


class CartTests(ShopTestCase):
    def test_cart_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/cart/").status_code, 401)

    def test_empty_cart_has_zero_totals(self):
        cart = self.cart()
        self.assertEqual(cart["items"], [])
        self.assertEqual(cart["total"], "0.00")
        self.assertEqual(cart["shipping"], "0.00")

    def test_totals_are_calculated_by_the_server(self):
        self.add(self.phone_v, 2)
        cart = self.cart()
        self.assertEqual(cart["items"][0]["unit_price"], "900.00")
        self.assertEqual(cart["subtotal_mrp"], "2000.00")
        self.assertEqual(cart["product_discount"], "200.00")
        self.assertEqual(cart["subtotal"], "1800.00")
        self.assertEqual(cart["tax"], "324.00")
        self.assertEqual(cart["shipping"], "0.00")
        self.assertEqual(cart["total"], "2124.00")

    def test_shipping_fee_below_free_shipping_threshold(self):
        self.add(self.cable_v, 1)
        cart = self.cart()
        self.assertEqual(cart["subtotal"], "200.00")
        self.assertEqual(cart["tax"], "36.00")
        self.assertEqual(cart["shipping"], "99.00")
        self.assertEqual(cart["total"], "335.00")

    def test_client_cannot_send_prices(self):
        response = self.add(self.phone_v, 1, price=1)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.cart()["items"], [])
        self.add(self.phone_v, 1)
        tampered = self.client.patch(
            "/api/cart/update/",
            {"variant_id": self.phone_v.id, "quantity": 1, "total": 1},
            format="json",
        )
        self.assertEqual(tampered.status_code, 400)
        self.assertEqual(self.cart()["total"], "1161.00")

    def test_cannot_add_more_than_stock(self):
        self.assertEqual(self.add(self.phone_v, 6).status_code, 400)
        self.assertEqual(self.cart()["items"], [])

    def test_stock_limit_counts_what_is_already_in_cart(self):
        self.assertEqual(self.add(self.phone_v, 3).status_code, 200)
        self.assertEqual(self.add(self.phone_v, 3).status_code, 400)
        self.assertEqual(self.cart()["items"][0]["quantity"], 3)

    def test_out_of_stock_item_cannot_be_added(self):
        Inventory.objects.filter(variant=self.phone_v).update(available_stock=0)
        self.assertEqual(self.add(self.phone_v, 1).status_code, 400)

    def test_max_quantity_per_item(self):
        self.assertEqual(self.add(self.cable_v, 11).status_code, 400)
        self.assertEqual(self.add(self.cable_v, 10).status_code, 200)

    def test_increase_and_decrease_quantity(self):
        self.add(self.phone_v, 3)
        down = self.client.patch(
            "/api/cart/update/", {"variant_id": self.phone_v.id, "quantity": 1}, format="json"
        )
        self.assertEqual(down.data["items"][0]["quantity"], 1)
        up = self.client.patch(
            "/api/cart/update/", {"variant_id": self.phone_v.id, "quantity": 4}, format="json"
        )
        self.assertEqual(up.data["items"][0]["quantity"], 4)

    def test_remove_item(self):
        self.add(self.phone_v, 1)
        response = self.client.delete(
            "/api/cart/remove/", {"variant_id": self.phone_v.id}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["items"], [])

    def test_save_for_later_and_move_back(self):
        self.add(self.phone_v, 2)
        saved = self.client.post(
            "/api/cart/save-for-later/", {"variant_id": self.phone_v.id}, format="json"
        )
        self.assertEqual(saved.data["items"], [])
        self.assertEqual(len(saved.data["saved_for_later"]), 1)
        self.assertEqual(saved.data["total"], "0.00")
        back = self.client.post(
            "/api/cart/move-to-cart/", {"variant_id": self.phone_v.id}, format="json"
        )
        self.assertEqual(back.data["items"][0]["quantity"], 2)

    def test_inactive_product_cannot_be_added(self):
        Product.objects.filter(pk=self.phone.pk).update(is_active=False)
        self.assertEqual(self.add(self.phone_v, 1).status_code, 404)

    def test_carts_are_private(self):
        self.add(self.phone_v, 1)
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.cart()["items"], [])
        response = self.client.patch(
            "/api/cart/update/", {"variant_id": self.phone_v.id, "quantity": 2}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_cart_flags_item_when_stock_drops(self):
        self.add(self.phone_v, 3)
        Inventory.objects.filter(variant=self.phone_v).update(available_stock=1)
        cart = self.cart()
        self.assertTrue(cart["has_issues"])
        self.assertEqual(cart["items"][0]["issue"], "Only 1 left in stock.")


class CouponTests(ShopTestCase):
    def test_percentage_coupon_and_lowercase_code(self):
        make_coupon("SAVE10")
        self.add(self.phone_v, 2)
        response = self.apply("save10")
        self.assertEqual(response.status_code, 200)
        cart = response.data
        self.assertEqual(cart["coupon"]["discount"], "180.00")
        self.assertEqual(cart["tax"], "291.60")
        self.assertEqual(cart["total"], "1911.60")

    def test_max_discount_cap(self):
        make_coupon("BIG50", value=Decimal("50"), max_discount=Decimal("100"))
        self.add(self.phone_v, 2)
        self.assertEqual(self.apply("BIG50").data["coupon"]["discount"], "100.00")

    def test_fixed_coupon_never_exceeds_cart(self):
        make_coupon("FLAT500", discount_type="FIXED", value=Decimal("500"))
        make_coupon("FLAT5000", discount_type="FIXED", value=Decimal("5000"))
        self.add(self.phone_v, 2)
        self.assertEqual(self.apply("FLAT500").data["coupon"]["discount"], "500.00")
        self.assertEqual(self.apply("FLAT5000").data["coupon"]["discount"], "1800.00")

    def test_expired_coupon_is_rejected(self):
        now = timezone.now()
        make_coupon("OLD", valid_from=now - timedelta(days=60), valid_until=now - timedelta(days=1))
        self.add(self.phone_v, 1)
        response = self.apply("OLD")
        self.assertEqual(response.status_code, 400)
        self.assertIn("expired", response.data["code"][0])

    def test_coupon_not_active_yet_is_rejected(self):
        now = timezone.now()
        make_coupon("SOON", valid_from=now + timedelta(days=1), valid_until=now + timedelta(days=10))
        self.add(self.phone_v, 1)
        self.assertEqual(self.apply("SOON").status_code, 400)

    def test_unknown_and_inactive_coupons_give_the_same_message(self):
        make_coupon("OFF", is_active=False)
        self.add(self.phone_v, 1)
        unknown = self.apply("NOSUCHCODE")
        inactive = self.apply("OFF")
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(unknown.data["code"], [INVALID])
        self.assertEqual(inactive.data["code"], [INVALID])

    def test_minimum_order_value(self):
        make_coupon("BIGSPEND", min_order_value=Decimal("5000"))
        self.add(self.phone_v, 2)
        response = self.apply("BIGSPEND")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Minimum", response.data["code"][0])

    def test_total_usage_limit(self):
        coupon = make_coupon("ONCE", usage_limit=1)
        CouponUsage.objects.create(coupon=coupon, user=self.bob)
        self.add(self.phone_v, 1)
        response = self.apply("ONCE")
        self.assertEqual(response.status_code, 400)
        self.assertIn("usage limit", response.data["code"][0])

    def test_per_user_limit(self):
        coupon = make_coupon("MINE")
        CouponUsage.objects.create(coupon=coupon, user=self.alice)
        self.add(self.phone_v, 1)
        self.assertEqual(self.apply("MINE").status_code, 400)
        self.client.force_authenticate(self.bob)
        self.add(self.phone_v, 1)
        self.assertEqual(self.apply("MINE").status_code, 200)

    def test_user_specific_coupon(self):
        make_coupon("VIP", user=self.alice)
        self.client.force_authenticate(self.bob)
        self.add(self.phone_v, 1)
        response = self.apply("VIP")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], [INVALID])  # looks the same as an unknown code
        self.client.force_authenticate(self.alice)
        self.add(self.phone_v, 1)
        self.assertEqual(self.apply("VIP").status_code, 200)

    def test_category_specific_coupon(self):
        coupon = make_coupon("LAP10")
        coupon.categories.add(self.laptops)
        self.add(self.phone_v, 1)
        response = self.apply("LAP10")
        self.assertEqual(response.status_code, 400)
        self.assertIn("does not apply", response.data["code"][0])
        self.add(self.laptop_v, 1)
        # 10% of the laptop (50000) only; the phone is not eligible
        self.assertEqual(self.apply("LAP10").data["coupon"]["discount"], "5000.00")

    def test_product_specific_coupon(self):
        coupon = make_coupon("PH20", value=Decimal("20"))
        coupon.products.add(self.phone)
        self.add(self.phone_v, 2)
        self.add(self.cable_v, 1)
        # 20% of the phones (1800) only
        self.assertEqual(self.apply("PH20").data["coupon"]["discount"], "360.00")

    def test_coupon_stops_applying_when_the_cart_changes(self):
        make_coupon("BIGSPEND", min_order_value=Decimal("1500"))
        self.add(self.phone_v, 2)
        self.assertEqual(self.apply("BIGSPEND").status_code, 200)
        cart = self.client.patch(
            "/api/cart/update/", {"variant_id": self.phone_v.id, "quantity": 1}, format="json"
        ).data
        self.assertEqual(cart["coupon"]["discount"], "0.00")
        self.assertIn("Minimum", cart["coupon"]["message"])

    def test_remove_coupon(self):
        make_coupon("SAVE10")
        self.add(self.phone_v, 2)
        self.apply("SAVE10")
        cart = self.client.delete("/api/cart/coupon/").data
        self.assertIsNone(cart["coupon"])
        self.assertEqual(cart["total"], "2124.00")

    def test_validate_endpoint_previews_without_applying(self):
        make_coupon("SAVE10")
        self.add(self.phone_v, 2)
        response = self.client.post("/api/coupons/validate/", {"code": "SAVE10"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["discount"], "180.00")
        self.assertIsNone(self.cart()["coupon"])

    def test_redeeming_a_coupon_twice_fails(self):
        make_coupon("SAVE10")
        lines = [{
            "product_id": self.phone.id,
            "category_id": self.phones.id,
            "line_total": Decimal("1800.00"),
        }]
        coupon, discount = redeem_coupon("SAVE10", self.alice, lines, Decimal("1800.00"), "ORD-1")
        self.assertEqual(discount, Decimal("180.00"))
        self.assertEqual(CouponUsage.objects.filter(coupon=coupon, user=self.alice).count(), 1)
        with self.assertRaises(CouponError):
            redeem_coupon("SAVE10", self.alice, lines, Decimal("1800.00"), "ORD-2")

    def test_database_rejects_percentage_over_100(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_coupon("BAD", value=Decimal("150"))

    def test_code_is_stored_in_upper_case(self):
        self.assertEqual(make_coupon("mixed Case").code, "MIXED CASE")


class WishlistTests(ShopTestCase):
    def wish(self, product):
        return self.client.post("/api/wishlist/add/", {"product_id": product.id}, format="json")

    def test_add_and_list(self):
        self.assertEqual(self.wish(self.phone).status_code, 201)
        data = self.client.get("/api/wishlist/").data
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["name"], "Test Phone")

    def test_duplicates_are_prevented(self):
        self.wish(self.phone)
        self.assertEqual(self.wish(self.phone).status_code, 200)
        self.assertEqual(WishlistItem.objects.count(), 1)

    def test_remove(self):
        self.wish(self.phone)
        response = self.client.delete(
            "/api/wishlist/remove/", {"product_id": self.phone.id}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/wishlist/").data["count"], 0)

    def test_move_to_cart(self):
        self.wish(self.phone)
        response = self.client.post(
            "/api/wishlist/move-to-cart/", {"product_id": self.phone.id}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["items"][0]["sku"], "TEST-PHONE")
        self.assertEqual(self.client.get("/api/wishlist/").data["count"], 0)

    def test_move_to_cart_blocked_when_out_of_stock(self):
        self.wish(self.phone)
        Inventory.objects.filter(variant=self.phone_v).update(available_stock=0)
        response = self.client.post(
            "/api/wishlist/move-to-cart/", {"product_id": self.phone.id}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/api/wishlist/").data["count"], 1)

    def test_wishlists_are_private(self):
        self.wish(self.phone)
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.get("/api/wishlist/").data["count"], 0)

    def test_inactive_product_cannot_be_wishlisted(self):
        Product.objects.filter(pk=self.phone.pk).update(is_active=False)
        self.assertEqual(self.wish(self.phone).status_code, 404)
