from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from products.models import Category, Product
from coupons.models import Coupon, CouponUsage
from coupons.services import CouponError, check_coupon, redeem_coupon

User = get_user_model()


class CouponServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="alice@example.com",
            password="TestPass123!",
        )
        self.other_user = User.objects.create_user(
            email="bob@example.com",
            password="TestPass123!",
        )

        self.category = Category.objects.create(
            name="Electronics",
            slug="electronics",
        )
        self.product = Product.objects.create(
            name="Test Phone",
            slug="test-phone",
            category=self.category,
        )

        self.subtotal = Decimal("1000.00")
        self.lines = [{
            "product_id": self.product.id,
            "category_id": self.category.id,
            "line_total": Decimal("1000.00"),
        }]

    def make_coupon(self, code="SAVE10", **overrides):
        data = {
            "code": code,
            "discount_type": Coupon.DiscountType.PERCENT,
            "value": Decimal("10.00"),
            "valid_from": timezone.now() - timedelta(days=1),
            "valid_until": timezone.now() + timedelta(days=30),
            "min_order_value": Decimal("0.00"),
            "per_user_limit": 1,
            "is_active": True,
        }
        data.update(overrides)
        return Coupon.objects.create(**data)

    def assert_coupon_error(self, code, user=None, lines=None, subtotal=None):
        with self.assertRaises(CouponError):
            check_coupon(
                code,
                user or self.user,
                lines if lines is not None else self.lines,
                subtotal if subtotal is not None else self.subtotal,
            )

    def test_percentage_coupon_calculates_discount(self):
        self.make_coupon("SAVE10")
        coupon, discount = check_coupon(
            "SAVE10", self.user, self.lines, self.subtotal
        )
        self.assertEqual(coupon.code, "SAVE10")
        self.assertEqual(discount, Decimal("100.00"))

    def test_coupon_code_is_normalized(self):
        self.make_coupon("SAVE10")
        coupon, discount = check_coupon(
            "  save10  ", self.user, self.lines, self.subtotal
        )
        self.assertEqual(coupon.code, "SAVE10")
        self.assertEqual(discount, Decimal("100.00"))

    def test_unknown_coupon_is_rejected(self):
        self.assert_coupon_error("DOESNOTEXIST")

    def test_inactive_coupon_is_rejected(self):
        self.make_coupon("INACTIVE", is_active=False)
        self.assert_coupon_error("INACTIVE")

    def test_coupon_not_yet_active_is_rejected(self):
        self.make_coupon(
            "FUTURE",
            valid_from=timezone.now() + timedelta(days=2),
        )
        self.assert_coupon_error("FUTURE")

    def test_expired_coupon_is_rejected(self):
        expired_time = timezone.now() - timedelta(days=1)
        self.make_coupon(
            "EXPIRED",
            valid_from=expired_time - timedelta(days=30),
            valid_until=expired_time,
        )
        self.assert_coupon_error("EXPIRED")

    def test_usage_limit_is_enforced(self):
        coupon = self.make_coupon("LIMITED", usage_limit=1)
        CouponUsage.objects.create(coupon=coupon, user=self.other_user)
        self.assert_coupon_error("LIMITED")

    def test_per_user_limit_is_enforced(self):
        coupon = self.make_coupon("ONEUSE", per_user_limit=1)
        CouponUsage.objects.create(coupon=coupon, user=self.user)
        self.assert_coupon_error("ONEUSE")

    def test_minimum_order_value_is_enforced(self):
        self.make_coupon(
            "MINIMUM",
            min_order_value=Decimal("1500.00"),
        )
        self.assert_coupon_error(
            "MINIMUM",
            subtotal=Decimal("1000.00"),
        )

    def test_private_coupon_rejects_other_user(self):
        self.make_coupon("PRIVATE", user=self.user)
        self.assert_coupon_error("PRIVATE", user=self.other_user)

    def test_fixed_coupon_calculates_discount(self):
        self.make_coupon(
            "FLAT200",
            discount_type=Coupon.DiscountType.FIXED,
            value=Decimal("200.00"),
        )
        _, discount = check_coupon(
            "FLAT200", self.user, self.lines, self.subtotal
        )
        self.assertEqual(discount, Decimal("200.00"))

    def test_fixed_discount_cannot_exceed_eligible_amount(self):
        self.make_coupon(
            "FLATBIG",
            discount_type=Coupon.DiscountType.FIXED,
            value=Decimal("1500.00"),
        )
        _, discount = check_coupon(
            "FLATBIG", self.user, self.lines, self.subtotal
        )
        self.assertEqual(discount, Decimal("1000.00"))

    def test_percentage_coupon_respects_max_discount(self):
        self.make_coupon(
            "CAPPED",
            value=Decimal("50.00"),
            max_discount=Decimal("100.00"),
        )
        _, discount = check_coupon(
            "CAPPED", self.user, self.lines, self.subtotal
        )
        self.assertEqual(discount, Decimal("100.00"))

    def test_product_restricted_coupon_rejects_other_products(self):
        coupon = self.make_coupon("PRODUCTONLY")
        coupon.products.set([self.product])
        other_product = Product.objects.create(
            name="Other Phone",
            slug="other-phone",
            category=self.category,
        )
        other_lines = [{
            "product_id": other_product.id,
            "category_id": self.category.id,
            "line_total": Decimal("500.00"),
        }]
        self.assert_coupon_error(
            "PRODUCTONLY",
            lines=other_lines,
            subtotal=Decimal("500.00"),
        )

    def test_category_restricted_coupon_only_discounts_eligible_items(self):
        coupon = self.make_coupon("CATEGORYONLY")
        coupon.categories.add(self.category)
        _, discount = check_coupon(
            "CATEGORYONLY", self.user, self.lines, self.subtotal
        )
        self.assertEqual(discount, Decimal("100.00"))

    def test_redeem_coupon_records_usage(self):
        coupon = self.make_coupon("REDEEM10")
        redeemed_coupon, discount = redeem_coupon(
            "REDEEM10",
            self.user,
            self.lines,
            self.subtotal,
            order_reference="TEST-ORDER-001",
        )
        self.assertEqual(redeemed_coupon, coupon)
        self.assertEqual(discount, Decimal("100.00"))

        usage = CouponUsage.objects.get(coupon=coupon, user=self.user)
        self.assertEqual(usage.order_reference, "TEST-ORDER-001")
        self.assertEqual(usage.discount_amount, Decimal("100.00"))

    def test_redeemed_coupon_cannot_be_reused_by_same_user(self):
        self.make_coupon("REDEEMONCE")
        redeem_coupon(
            "REDEEMONCE",
            self.user,
            self.lines,
            self.subtotal,
            order_reference="TEST-ORDER-002",
        )
        self.assert_coupon_error("REDEEMONCE")
