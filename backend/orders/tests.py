import threading
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Address
from cart.models import Cart, CartItem
from coupons.models import Coupon, CouponUsage
from inventory.models import Inventory
from payments.models import Payment
from products.models import Category, Product, ProductVariant

from .models import Order
from .services import CheckoutError, OrderError, place_order, set_status

User = get_user_model()
PASSWORD = "Str0ng!Pass#2026"


def make_variant(name, price, stock, discount="0"):
    category, _ = Category.objects.get_or_create(slug="gadgets", defaults={"name": "Gadgets"})
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
    return variant


def make_address(user, kind="SHIPPING", **extra):
    data = dict(
        user=user, address_type=kind, full_name="Test User", phone="9876543210",
        line1="12 Main Road", city="Hyderabad", state="Telangana",
        postal_code="500001", is_default=False,
    )
    data.update(extra)
    return Address.objects.create(**data)


def fill_cart(user, variant, quantity):
    cart, _ = Cart.objects.get_or_create(user=user)
    CartItem.objects.create(cart=cart, variant=variant, quantity=quantity)
    return cart


def make_coupon(code="SAVE10", **extra):
    data = {
        "code": code,
        "discount_type": Coupon.DiscountType.PERCENT,
        "value": Decimal("10"),
        "valid_until": timezone.now() + timedelta(days=30),
    }
    data.update(extra)
    return Coupon.objects.create(**data)


def stock_of(variant):
    return Inventory.objects.get(variant=variant)


class FlowTestCase(APITestCase):
    def setUp(self):
        cache.clear()  # reset rate limiting between tests
        self.alice = User.objects.create_user(email="alice@example.com", password=PASSWORD)
        self.bob = User.objects.create_user(email="bob@example.com", password=PASSWORD)
        # 1000 with 10% off = 900 each
        self.phone_v = make_variant("Test Phone", "1000.00", 5, "10")
        self.laptop_v = make_variant("Test Laptop", "50000.00", 3)
        self.cable_v = make_variant("Test Cable", "200.00", 20)
        self.ship = make_address(self.alice)
        self.bill = make_address(self.alice, "BILLING", line1="99 Billing Street")
        self.client.force_authenticate(self.alice)

    def checkout_body(self, **extra):
        body = {"shipping_address_id": self.ship.id, "shipping_method": "STANDARD"}
        body.update(extra)
        return body

    def place_for(self, user, variant, quantity=1, **extra):
        self.client.force_authenticate(user)
        address = Address.objects.filter(user=user, address_type="SHIPPING").first() or make_address(user)
        fill_cart(user, variant, quantity)
        body = {"shipping_address_id": address.id, "shipping_method": "STANDARD"}
        body.update(extra)
        return self.client.post("/api/orders/", body, format="json")

    def place(self, variant=None, quantity=2, **extra):
        return self.place_for(self.alice, variant or self.phone_v, quantity, **extra)

    def pay(self, order_data, token="tok_success"):
        created = self.client.post(
            "/api/payment/create/", {"order_id": order_data["id"], "method": "CARD"}, format="json"
        )
        self.assertIn(created.status_code, (200, 201))
        body = {
            "payment_id": created.data["id"],
            "transaction_reference": created.data["transaction_reference"],
            "token": token,
        }
        return self.client.post("/api/payment/verify/", body, format="json")


class CheckoutTests(FlowTestCase):
    def test_checkout_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post("/api/orders/", {}, format="json").status_code, 401)

    def test_place_order_creates_order_and_reserves_stock(self):
        response = self.place(quantity=2)
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data
        self.assertTrue(data["order_number"].startswith("ORD-"))
        self.assertEqual(data["status"], "PLACED")
        self.assertEqual(data["payment_status"], "PENDING")
        self.assertEqual(data["subtotal_mrp"], "2000.00")
        self.assertEqual(data["product_discount"], "200.00")
        self.assertEqual(data["subtotal"], "1800.00")
        self.assertEqual(data["tax"], "324.00")
        self.assertEqual(data["shipping_fee"], "0.00")
        self.assertEqual(data["total"], "2124.00")
        self.assertEqual(data["items"][0]["unit_price"], "900.00")
        self.assertEqual(len(data["timeline"]), 1)
        inv = stock_of(self.phone_v)
        self.assertEqual((inv.available_stock, inv.reserved_stock), (3, 2))
        self.assertEqual(Cart.objects.get(user=self.alice).items.count(), 0)

    def test_express_shipping_fee(self):
        response = self.place(variant=self.cable_v, quantity=1, shipping_method="EXPRESS")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["shipping_fee"], "199.00")
        self.assertEqual(response.data["total"], "435.00")

    def test_empty_cart_is_rejected(self):
        response = self.client.post("/api/orders/", self.checkout_body(), format="json")
        self.assertEqual(response.status_code, 400)

    def test_unavailable_stock_is_rejected_and_nothing_changes(self):
        fill_cart(self.alice, self.phone_v, 3)
        Inventory.objects.filter(variant=self.phone_v).update(available_stock=1)
        response = self.client.post("/api/orders/", self.checkout_body(), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        inv = stock_of(self.phone_v)
        self.assertEqual((inv.available_stock, inv.reserved_stock), (1, 0))

    def test_inactive_product_blocks_checkout(self):
        fill_cart(self.alice, self.phone_v, 1)
        Product.objects.filter(slug="test-phone").update(is_active=False)
        response = self.client.post("/api/orders/", self.checkout_body(), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_cannot_use_another_users_address(self):
        fill_cart(self.alice, self.phone_v, 1)
        bobs = make_address(self.bob)
        response = self.client.post(
            "/api/orders/", self.checkout_body(shipping_address_id=bobs.id), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Cart.objects.get(user=self.alice).items.count(), 1)

    def test_shipping_address_must_be_a_shipping_type(self):
        fill_cart(self.alice, self.phone_v, 1)
        response = self.client.post(
            "/api/orders/", self.checkout_body(shipping_address_id=self.bill.id), format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_billing_defaults_to_shipping_address(self):
        fill_cart(self.alice, self.phone_v, 1)
        response = self.client.post("/api/orders/", self.checkout_body(), format="json")
        self.assertEqual(response.data["billing_address"]["line1"], "12 Main Road")

    def test_separate_billing_address(self):
        fill_cart(self.alice, self.phone_v, 1)
        response = self.client.post(
            "/api/orders/", self.checkout_body(billing_address_id=self.bill.id), format="json"
        )
        self.assertEqual(response.data["billing_address"]["line1"], "99 Billing Street")

    def test_client_cannot_send_prices(self):
        fill_cart(self.alice, self.phone_v, 1)
        response = self.client.post("/api/orders/", self.checkout_body(total=1), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Cart.objects.get(user=self.alice).items.count(), 1)

    def test_coupon_is_redeemed_and_cart_coupon_cleared(self):
        coupon = make_coupon("SAVE10")
        cart = fill_cart(self.alice, self.phone_v, 2)
        cart.coupon = coupon
        cart.save()
        response = self.client.post("/api/orders/", self.checkout_body(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["coupon_code"], "SAVE10")
        self.assertEqual(response.data["coupon_discount"], "180.00")
        self.assertEqual(response.data["tax"], "291.60")
        self.assertEqual(response.data["total"], "1911.60")
        usage = CouponUsage.objects.get(coupon=coupon, user=self.alice)
        self.assertEqual(usage.order_reference, response.data["order_number"])
        self.assertIsNone(Cart.objects.get(user=self.alice).coupon_id)

    def test_coupon_usage_limit_blocks_checkout(self):
        coupon = make_coupon("ONCE", usage_limit=1)
        CouponUsage.objects.create(coupon=coupon, user=self.bob)
        cart = fill_cart(self.alice, self.phone_v, 2)
        cart.coupon = coupon
        cart.save()
        response = self.client.post("/api/orders/", self.checkout_body(), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(stock_of(self.phone_v).available_stock, 5)

    def test_order_keeps_the_price_paid_after_a_price_change(self):
        order = self.place(quantity=1).data
        ProductVariant.objects.filter(pk=self.phone_v.pk).update(price=Decimal("9999.00"))
        detail = self.client.get(f"/api/orders/{order['id']}/").data
        self.assertEqual(detail["items"][0]["unit_price"], "900.00")
        self.assertEqual(detail["total"], order["total"])

    def test_double_submit_creates_only_one_order(self):
        fill_cart(self.alice, self.phone_v, 1)
        first = self.client.post("/api/orders/", self.checkout_body(), format="json")
        second = self.client.post("/api/orders/", self.checkout_body(), format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(Order.objects.count(), 1)

    def test_shipping_options(self):
        fill_cart(self.alice, self.cable_v, 1)
        response = self.client.get("/api/checkout/shipping-options/")
        self.assertEqual(response.status_code, 200)
        options = {o["method"]: o for o in response.data["options"]}
        self.assertEqual(options["STANDARD"]["fee"], "99.00")
        self.assertEqual(options["STANDARD"]["total"], "335.00")
        self.assertEqual(options["EXPRESS"]["fee"], "199.00")
        self.assertEqual(options["EXPRESS"]["total"], "435.00")

    def test_summary_changes_nothing(self):
        fill_cart(self.alice, self.phone_v, 2)
        response = self.client.post("/api/checkout/summary/", self.checkout_body(), format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["cart"]["total"], "2124.00")
        self.assertEqual(response.data["shipping_address"]["city"], "Hyderabad")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(stock_of(self.phone_v).reserved_stock, 0)
        self.assertEqual(Cart.objects.get(user=self.alice).items.count(), 1)


class PaymentTests(FlowTestCase):
    def test_create_payment_uses_the_order_total_and_is_idempotent(self):
        order = self.place().data
        body = {"order_id": order["id"], "method": "UPI"}
        first = self.client.post("/api/payment/create/", body, format="json")
        second = self.client.post("/api/payment/create/", body, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(first.data["amount"], "2124.00")
        self.assertEqual(first.data["status"], "PENDING")
        self.assertTrue(first.data["transaction_reference"].startswith("SBX-"))
        self.assertEqual(Payment.objects.count(), 1)

    def test_successful_payment_confirms_order_and_sells_stock(self):
        order = self.place(quantity=2).data
        response = self.pay(order)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["payment"]["status"], "SUCCESS")
        self.assertEqual(response.data["order_status"], "CONFIRMED")
        inv = stock_of(self.phone_v)
        self.assertEqual((inv.available_stock, inv.reserved_stock, inv.sold_stock), (3, 0, 2))
        detail = self.client.get(f"/api/orders/{order['id']}/").data
        self.assertEqual(detail["payment_status"], "SUCCESS")
        self.assertEqual(detail["timeline"][-1]["status"], "CONFIRMED")

    def test_declined_payment_keeps_order_open_and_can_be_retried(self):
        order = self.place(quantity=2).data
        declined = self.pay(order, "tok_declined")
        self.assertEqual(declined.status_code, 402)
        self.assertEqual(Payment.objects.get().status, "FAILED")
        self.assertEqual(Order.objects.get(pk=order["id"]).status, "PLACED")
        self.assertEqual(stock_of(self.phone_v).reserved_stock, 2)  # still held for the customer
        retry = self.pay(order)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(Order.objects.get(pk=order["id"]).status, "CONFIRMED")
        self.assertEqual(Payment.objects.count(), 2)

    def test_cancelled_payment(self):
        order = self.place().data
        response = self.pay(order, "tok_cancelled")
        self.assertEqual(response.status_code, 402)
        self.assertEqual(Payment.objects.get().status, "CANCELLED")
        self.assertEqual(Order.objects.get(pk=order["id"]).status, "PLACED")

    def test_verifying_twice_does_not_sell_twice(self):
        order = self.place(quantity=2).data
        self.assertEqual(self.pay(order).status_code, 200)
        payment = Payment.objects.get(order_id=order["id"])
        again = self.client.post(
            "/api/payment/verify/",
            {
                "payment_id": payment.id,
                "transaction_reference": payment.transaction_reference,
                "token": "tok_success",
            },
            format="json",
        )
        self.assertEqual(again.status_code, 200)
        self.assertEqual(stock_of(self.phone_v).sold_stock, 2)

    def test_wrong_reference_is_rejected(self):
        order = self.place().data
        created = self.client.post(
            "/api/payment/create/", {"order_id": order["id"]}, format="json"
        )
        response = self.client.post(
            "/api/payment/verify/",
            {"payment_id": created.data["id"], "transaction_reference": "SBX-WRONG", "token": "tok_success"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Payment.objects.get().status, "PENDING")

    def test_unknown_token_is_rejected(self):
        order = self.place().data
        response = self.pay(order, "tok_hacked")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.get(pk=order["id"]).status, "PLACED")

    def test_cannot_pay_someone_elses_order(self):
        order = self.place().data
        self.client.force_authenticate(self.bob)
        response = self.client.post("/api/payment/create/", {"order_id": order["id"]}, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Payment.objects.count(), 0)

    def test_cannot_verify_someone_elses_payment(self):
        order = self.place().data
        created = self.client.post(
            "/api/payment/create/", {"order_id": order["id"]}, format="json"
        )
        self.client.force_authenticate(self.bob)
        response = self.client.post(
            "/api/payment/verify/",
            {
                "payment_id": created.data["id"],
                "transaction_reference": created.data["transaction_reference"],
                "token": "tok_success",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Order.objects.get(pk=order["id"]).status, "PLACED")

    def test_client_cannot_choose_the_amount(self):
        order = self.place().data
        response = self.client.post(
            "/api/payment/create/", {"order_id": order["id"], "amount": 1}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Payment.objects.count(), 0)

    def test_paying_after_the_window_cancels_the_order(self):
        order = self.place(quantity=2).data
        created = self.client.post(
            "/api/payment/create/", {"order_id": order["id"]}, format="json"
        )
        Order.objects.filter(pk=order["id"]).update(expires_at=timezone.now() - timedelta(minutes=1))
        response = self.client.post(
            "/api/payment/verify/",
            {
                "payment_id": created.data["id"],
                "transaction_reference": created.data["transaction_reference"],
                "token": "tok_success",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.get(pk=order["id"]).status, "CANCELLED")
        inv = stock_of(self.phone_v)
        self.assertEqual((inv.available_stock, inv.reserved_stock), (5, 0))
        self.assertEqual(Payment.objects.get().status, "CANCELLED")

    def test_cannot_pay_a_cancelled_order(self):
        order = self.place().data
        self.client.post(f"/api/orders/{order['id']}/cancel/")
        response = self.client.post("/api/payment/create/", {"order_id": order["id"]}, format="json")
        self.assertEqual(response.status_code, 400)


class CancellationTests(FlowTestCase):
    def test_cancel_unpaid_order_releases_stock_and_coupon(self):
        coupon = make_coupon("SAVE10")
        cart = fill_cart(self.alice, self.phone_v, 2)
        cart.coupon = coupon
        cart.save()
        order = self.client.post("/api/orders/", self.checkout_body(), format="json").data
        self.assertEqual(CouponUsage.objects.count(), 1)
        response = self.client.post(f"/api/orders/{order['id']}/cancel/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "CANCELLED")
        inv = stock_of(self.phone_v)
        self.assertEqual((inv.available_stock, inv.reserved_stock), (5, 0))
        self.assertEqual(CouponUsage.objects.count(), 0)

    def test_cancel_paid_order_restocks_and_refunds(self):
        order = self.place(quantity=2).data
        self.pay(order)
        response = self.client.post(f"/api/orders/{order['id']}/cancel/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "CANCELLED")
        self.assertEqual(response.data["payment_status"], "REFUNDED")
        inv = stock_of(self.phone_v)
        self.assertEqual((inv.available_stock, inv.sold_stock), (5, 0))

    def test_cannot_cancel_after_shipping(self):
        order = self.place().data
        self.pay(order)
        obj = Order.objects.get(pk=order["id"])
        set_status(obj, "PACKED")
        set_status(obj, "SHIPPED")
        response = self.client.post(f"/api/orders/{order['id']}/cancel/")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.get(pk=order["id"]).status, "SHIPPED")

    def test_other_user_cannot_cancel(self):
        order = self.place().data
        self.client.force_authenticate(self.bob)
        response = self.client.post(f"/api/orders/{order['id']}/cancel/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Order.objects.get(pk=order["id"]).status, "PLACED")

    def test_expire_command_cancels_only_unpaid_overdue_orders(self):
        unpaid = self.place(variant=self.phone_v, quantity=1).data
        paid = self.place(variant=self.cable_v, quantity=1).data
        self.pay(paid)
        Order.objects.update(expires_at=timezone.now() - timedelta(minutes=5))
        call_command("expire_unpaid_orders", stdout=StringIO())
        self.assertEqual(Order.objects.get(pk=unpaid["id"]).status, "CANCELLED")
        self.assertEqual(Order.objects.get(pk=paid["id"]).status, "CONFIRMED")
        self.assertEqual(stock_of(self.phone_v).available_stock, 5)

    def test_stock_stays_consistent_through_buy_cancel_and_buy_again(self):
        first = self.place(quantity=2).data
        self.pay(first)
        self.client.post(f"/api/orders/{first['id']}/cancel/")
        second = self.place(quantity=3).data
        self.pay(second)
        inv = stock_of(self.phone_v)
        self.assertEqual(inv.available_stock + inv.reserved_stock + inv.sold_stock, inv.opening_stock)
        self.assertEqual((inv.available_stock, inv.sold_stock), (2, 3))


class OrderHistoryTests(FlowTestCase):
    def test_history_is_private_and_paginated(self):
        order = self.place().data
        listing = self.client.get("/api/orders/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(listing.data["results"][0]["order_number"], order["order_number"])
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.get("/api/orders/").data["count"], 0)
        self.assertEqual(self.client.get(f"/api/orders/{order['id']}/").status_code, 404)

    def test_history_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/orders/").status_code, 401)

    def test_detail_has_everything_the_customer_needs(self):
        order = self.place().data
        detail = self.client.get(f"/api/orders/{order['id']}/").data
        for key in (
            "items", "timeline", "payments", "shipping_address", "billing_address",
            "subtotal", "tax", "shipping_fee", "total", "expires_at", "can_cancel",
        ):
            self.assertIn(key, detail)
        self.assertTrue(detail["can_cancel"])

    def test_filter_orders_by_status(self):
        first = self.place(variant=self.phone_v, quantity=1).data
        self.pay(first)
        self.place(variant=self.cable_v, quantity=1)
        response = self.client.get("/api/orders/?status=CONFIRMED")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], first["id"])

    def test_status_flow_builds_timeline_and_shipment(self):
        order = self.place().data
        self.assertEqual(self.pay(order).status_code, 200)
        obj = Order.objects.get(pk=order["id"])
        for step in ("PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"):
            set_status(obj, step)
        response = self.client.get(f"/api/orders/{order['id']}/tracking/")
        self.assertEqual(response.status_code, 200)
        shipment = response.data["shipment"]
        self.assertTrue(shipment["tracking_number"].startswith("TRK"))
        self.assertEqual(shipment["status"], "DELIVERED")
        self.assertIsNotNone(shipment["delivered_at"])
        self.assertIsNotNone(shipment["expected_delivery"])
        self.assertEqual(
            [event["status"] for event in response.data["timeline"]],
            ["PLACED", "CONFIRMED", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"],
        )

    def test_status_cannot_skip_steps(self):
        order = self.place().data
        self.pay(order)
        obj = Order.objects.get(pk=order["id"])
        with self.assertRaises(OrderError):
            set_status(obj, "DELIVERED")
        with self.assertRaises(OrderError):
            set_status(obj, "SHIPPED")
        self.assertEqual(Order.objects.get(pk=order["id"]).status, "CONFIRMED")


class CheckoutConcurrencyTests(TransactionTestCase):
    """Real database transactions running in parallel threads."""

    def test_last_item_can_only_be_bought_once(self):
        variant = make_variant("Last Phone", "1000.00", 1)
        buyers = []
        for index in range(6):
            user = User.objects.create_user(email=f"buyer{index}@example.com", password=PASSWORD)
            address = make_address(user)
            fill_cart(user, variant, 1)
            buyers.append((user, address.id))

        outcomes = []

        def attempt(user, address_id):
            try:
                place_order(user, address_id, None, "STANDARD")
                outcomes.append("ok")
            except CheckoutError:
                outcomes.append("sold_out")
            except Exception as exc:  # anything else is a real problem
                outcomes.append(f"error: {exc}")
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt, args=buyer) for buyer in buyers]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(outcomes.count("ok"), 1, outcomes)
        self.assertEqual(outcomes.count("sold_out"), 5, outcomes)
        self.assertEqual(Order.objects.count(), 1)
        inv = stock_of(variant)
        self.assertEqual((inv.available_stock, inv.reserved_stock), (0, 1))
