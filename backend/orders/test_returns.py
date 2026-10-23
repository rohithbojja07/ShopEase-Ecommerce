import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APITestCase

from cart.models import Cart, CartItem
from notifications.models import Notification
from payments.models import Payment
from payments.services import create_payment, verify_payment
from products.validators import validate_image_extension, validate_image_size

from .models import Order, Refund, ReturnRequest
from .returns import (
    ReturnError,
    approve_refund,
    approve_return,
    mark_received,
    reject_return,
    request_return,
)
from .services import place_order, set_status
from .tests import make_address, make_coupon, make_variant, stock_of

User = get_user_model()
PASSWORD = "Str0ng!Pass#2026"
TEMP_MEDIA = tempfile.mkdtemp()


def tearDownModule():
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


def png(name="proof.png"):
    buffer = BytesIO()
    Image.new("RGB", (10, 10), "white").save(buffer, "PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def delivered_order(user, lines, coupon=None):
    """Place, pay for and deliver an order. lines = [(variant, quantity), ...]"""
    address = (
        user.addresses.filter(address_type="SHIPPING").first() or make_address(user)
    )
    cart, _ = Cart.objects.get_or_create(user=user)
    for variant, quantity in lines:
        CartItem.objects.create(cart=cart, variant=variant, quantity=quantity)
    if coupon:
        cart.coupon = coupon
        cart.save()
    order = place_order(user, address.id)
    payment, _ = create_payment(user, order.id, "CARD")
    verify_payment(user, payment.id, payment.transaction_reference, "tok_success")
    order = Order.objects.get(pk=order.pk)
    for step in ("PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"):
        set_status(order, step)
    return Order.objects.get(pk=order.pk)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ReturnTestCase(APITestCase):
    def setUp(self):
        cache.clear()  # reset rate limiting between tests
        self.alice = User.objects.create_user(email="alice@example.com", password=PASSWORD)
        self.bob = User.objects.create_user(email="bob@example.com", password=PASSWORD)
        self.staff = User.objects.create_superuser(email="staff@example.com", password=PASSWORD)
        # phone: 1000 with 10% off = 900. cable: 200.
        self.phone_v = make_variant("Test Phone", "1000.00", 5, "10")
        self.cable_v = make_variant("Test Cable", "200.00", 20)
        # subtotal 2000, tax 360, free shipping, total 2360
        self.order = delivered_order(self.alice, [(self.phone_v, 2), (self.cable_v, 1)])
        self.phone_item = self.order.items.get(sku="TEST-PHONE")
        self.cable_item = self.order.items.get(sku="TEST-CABLE")
        self.client.force_authenticate(self.alice)

    def request_api(self, **extra):
        body = {"order_id": self.order.id, "reason": "DEFECTIVE", "description": "Broken"}
        body.update(extra)
        return self.client.post("/api/returns/", body, format="json")

    def make_return(self, items=None):
        return request_return(self.alice, self.order.id, "DEFECTIVE", "Broken", items)

    def refunded_return(self, items=None):
        ret = self.make_return(items)
        approve_return(ret, self.staff)
        mark_received(ret, self.staff)
        return approve_refund(ret, self.staff)


class ReturnRequestTests(ReturnTestCase):
    def test_return_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.request_api().status_code, 401)

    def test_whole_order_return_by_default(self):
        response = self.request_api()
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data
        self.assertTrue(data["return_number"].startswith("RET-"))
        self.assertEqual(data["status"], "REQUESTED")
        self.assertEqual(data["refund_amount"], "2360.00")
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(len(data["events"]), 1)
        self.assertIsNone(data["refund"])
        self.assertTrue(data["can_cancel"])
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "RETURN_REQUESTED")

    def test_partial_return_refund_is_a_share_of_what_was_paid(self):
        response = self.request_api(items=[{"order_item_id": self.cable_item.id, "quantity": 1}])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["refund_amount"], "236.00")  # 200 of 2000, plus its tax

    def test_refund_amount_includes_the_coupon_discount(self):
        coupon = make_coupon("SAVE10")
        order = delivered_order(self.bob, [(self.phone_v, 2)], coupon=coupon)
        self.client.force_authenticate(self.bob)
        response = self.client.post(
            "/api/returns/", {"order_id": order.id, "reason": "OTHER"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["refund_amount"], "1911.60")  # what bob actually paid

    def test_client_cannot_choose_the_refund_amount(self):
        response = self.request_api(refund_amount=99999)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ReturnRequest.objects.count(), 0)

    def test_only_delivered_orders_can_be_returned(self):
        Order.objects.filter(pk=self.order.pk).update(status="SHIPPED")
        self.assertEqual(self.request_api().status_code, 400)

    def test_return_window_closes(self):
        Order.objects.filter(pk=self.order.pk).update(
            delivered_at=timezone.now() - timedelta(days=8)
        )
        response = self.request_api()
        self.assertEqual(response.status_code, 400)
        self.assertIn("window", response.data["detail"])

    def test_only_one_active_return_per_order(self):
        self.assertEqual(self.request_api().status_code, 201)
        self.assertEqual(self.request_api().status_code, 400)
        self.assertEqual(ReturnRequest.objects.count(), 1)

    def test_cannot_return_someone_elses_order(self):
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.request_api().status_code, 404)

    def test_item_and_quantity_validation(self):
        too_many = self.request_api(items=[{"order_item_id": self.phone_item.id, "quantity": 3}])
        self.assertEqual(too_many.status_code, 400)
        unknown = self.request_api(items=[{"order_item_id": 999999, "quantity": 1}])
        self.assertEqual(unknown.status_code, 400)
        twice = self.request_api(items=[
            {"order_item_id": self.phone_item.id, "quantity": 1},
            {"order_item_id": self.phone_item.id, "quantity": 1},
        ])
        self.assertEqual(twice.status_code, 400)
        self.assertEqual(ReturnRequest.objects.count(), 0)

    def test_invalid_reason_is_rejected(self):
        self.assertEqual(self.request_api(reason="BECAUSE").status_code, 400)

    def test_returns_are_private(self):
        ret = self.make_return()
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.get("/api/returns/").data["count"], 0)
        self.assertEqual(self.client.get(f"/api/returns/{ret.id}/").status_code, 404)
        self.assertEqual(self.client.post(f"/api/returns/{ret.id}/cancel/").status_code, 404)

    def test_customer_can_list_and_track_their_return(self):
        ret = self.make_return()
        listing = self.client.get("/api/returns/")
        self.assertEqual(listing.data["count"], 1)
        detail = self.client.get(f"/api/returns/{ret.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["order_number"], self.order.order_number)
        self.assertEqual(detail.data["events"][0]["status"], "REQUESTED")

    def test_customer_can_withdraw_a_return_and_request_again(self):
        ret = self.make_return()
        response = self.client.post(f"/api/returns/{ret.id}/cancel/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "CANCELLED")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "DELIVERED")
        self.assertEqual(self.request_api().status_code, 201)

    def test_customer_cannot_withdraw_an_approved_return(self):
        ret = self.make_return()
        approve_return(ret, self.staff)
        self.assertEqual(self.client.post(f"/api/returns/{ret.id}/cancel/").status_code, 400)


class EvidenceTests(ReturnTestCase):
    def upload(self, ret, files):
        return self.client.post(
            f"/api/returns/{ret.id}/evidence/", {"images": files}, format="multipart"
        )

    def test_upload_evidence_images(self):
        ret = self.make_return()
        response = self.upload(ret, [png("a.png"), png("b.png")])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data["evidence"]), 2)
        self.assertTrue(response.data["evidence"][0]["image"].startswith("http"))

    def test_at_most_five_images(self):
        ret = self.make_return()
        self.assertEqual(self.upload(ret, [png(f"{i}.png") for i in range(5)]).status_code, 201)
        self.assertEqual(self.upload(ret, [png("extra.png")]).status_code, 400)

    def test_fake_images_are_rejected(self):
        ret = self.make_return()
        fake = SimpleUploadedFile("proof.png", b"this is not an image", content_type="image/png")
        self.assertEqual(self.upload(ret, [fake]).status_code, 400)
        wrong_type = SimpleUploadedFile("proof.txt", png().read(), content_type="text/plain")
        self.assertEqual(self.upload(ret, [wrong_type]).status_code, 400)
        self.assertEqual(ret.evidence.count(), 0)

    def test_upload_needs_images(self):
        ret = self.make_return()
        response = self.client.post(f"/api/returns/{ret.id}/evidence/", {}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_no_evidence_after_review_starts(self):
        ret = self.make_return()
        approve_return(ret, self.staff)
        self.assertEqual(self.upload(ret, [png()]).status_code, 400)

    def test_cannot_upload_to_someone_elses_return(self):
        ret = self.make_return()
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.upload(ret, [png()]).status_code, 404)

    def test_size_limit_is_ten_megabytes(self):
        class FakeFile:
            def __init__(self, size):
                self.size = size

        validate_image_size(FakeFile(10 * 1024 * 1024))  # exactly 10 MB is fine
        with self.assertRaises(DjangoValidationError):
            validate_image_size(FakeFile(10 * 1024 * 1024 + 1))

    def test_extension_whitelist(self):
        validate_image_extension(SimpleUploadedFile("photo.JPG", b"x"))
        with self.assertRaises(DjangoValidationError):
            validate_image_extension(SimpleUploadedFile("run.exe", b"x"))


class ReturnWorkflowTests(ReturnTestCase):
    def test_full_return_and_refund(self):
        ret = self.refunded_return()
        self.assertEqual(ret.status, "REFUNDED")
        refund = Refund.objects.get(return_request=ret)
        self.assertEqual(refund.amount, Decimal("2360.00"))
        self.assertTrue(refund.transaction_reference.startswith("RFD-"))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "REFUNDED")
        self.assertEqual(self.order.payment_status, "REFUNDED")
        self.assertEqual(Payment.objects.get(order=self.order).status, "REFUNDED")

    def test_full_refund_restocks_and_keeps_stock_consistent(self):
        self.refunded_return()
        phone = stock_of(self.phone_v)
        self.assertEqual((phone.available_stock, phone.sold_stock, phone.returned_stock), (5, 0, 2))
        cable = stock_of(self.cable_v)
        self.assertEqual((cable.available_stock, cable.sold_stock, cable.returned_stock), (20, 0, 1))
        for inv in (phone, cable):
            total = inv.available_stock + inv.reserved_stock + inv.sold_stock
            self.assertEqual(total, inv.opening_stock)

    def test_partial_refund_keeps_the_order_delivered_and_paid(self):
        ret = self.refunded_return(items=[{"order_item_id": self.cable_item.id, "quantity": 1}])
        self.assertEqual(Refund.objects.get(return_request=ret).amount, Decimal("236.00"))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "DELIVERED")
        self.assertEqual(self.order.payment_status, "SUCCESS")
        cable = stock_of(self.cable_v)
        self.assertEqual((cable.available_stock, cable.sold_stock), (20, 0))
        phone = stock_of(self.phone_v)
        self.assertEqual((phone.available_stock, phone.sold_stock), (3, 2))  # untouched
        with self.assertRaises(ReturnError):
            self.make_return()  # an order gets one return only

    def test_defective_items_can_be_kept_out_of_sellable_stock(self):
        ret = self.make_return()
        ReturnRequest.objects.filter(pk=ret.pk).update(restock_items=False)
        approve_return(ret, self.staff)
        mark_received(ret, self.staff)
        approve_refund(ret, self.staff)
        phone = stock_of(self.phone_v)
        self.assertEqual((phone.available_stock, phone.sold_stock, phone.returned_stock), (3, 2, 0))

    def test_order_statuses_follow_the_return(self):
        ret = self.make_return()
        statuses = []
        for step in (approve_return, mark_received, approve_refund):
            step(ret, self.staff)
            self.order.refresh_from_db()
            statuses.append(self.order.status)
        self.assertEqual(statuses, ["RETURN_REQUESTED", "RETURNED", "REFUNDED"])
        timeline = [row.status for row in self.order.history.all()]
        self.assertEqual(timeline[-3:], ["RETURN_REQUESTED", "RETURNED", "REFUNDED"])

    def test_steps_cannot_be_skipped_or_repeated(self):
        ret = self.make_return()
        with self.assertRaises(ReturnError):
            mark_received(ret, self.staff)  # not approved yet
        with self.assertRaises(ReturnError):
            approve_refund(ret, self.staff)  # not received yet
        approve_return(ret, self.staff)
        with self.assertRaises(ReturnError):
            approve_return(ret, self.staff)  # already approved
        self.assertEqual(Refund.objects.count(), 0)

    def test_refund_cannot_be_paid_twice(self):
        ret = self.refunded_return()
        with self.assertRaises(ReturnError):
            approve_refund(ret, self.staff)
        self.assertEqual(Refund.objects.count(), 1)
        self.assertEqual(stock_of(self.phone_v).returned_stock, 2)

    def test_rejection_needs_a_reason(self):
        ret = self.make_return()
        with self.assertRaises(ReturnError):
            reject_return(ret, self.staff, "   ")
        ret.refresh_from_db()
        self.assertEqual(ret.status, "REQUESTED")

    def test_rejection_returns_the_order_to_delivered_and_allows_a_new_request(self):
        ret = self.make_return()
        reject_return(ret, self.staff, "Item shows signs of misuse.")
        ret.refresh_from_db()
        self.assertEqual(ret.status, "REJECTED")
        self.assertEqual(ret.admin_note, "Item shows signs of misuse.")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "DELIVERED")
        self.assertEqual(self.request_api().status_code, 201)

    def test_customer_sees_the_refund_in_the_return(self):
        ret = self.refunded_return()
        detail = self.client.get(f"/api/returns/{ret.id}/").data
        self.assertEqual(detail["status"], "REFUNDED")
        self.assertEqual(detail["refund"]["amount"], "2360.00")
        self.assertEqual(
            [event["status"] for event in detail["events"]],
            ["REQUESTED", "APPROVED", "RECEIVED", "REFUNDED"],
        )

    def test_return_events_notify_the_customer(self):
        ret = self.make_return()
        reject_return(ret, self.staff, "Not eligible.")
        titles = list(
            Notification.objects.filter(user=self.alice, kind="RETURN")
            .order_by("id").values_list("title", flat=True)
        )
        self.assertEqual(titles, ["Return request received", "Return rejected"])
        self.refunded_return()
        self.assertTrue(
            Notification.objects.filter(user=self.alice, title="Refund processed").exists()
        )


class ReturnAdminTests(ReturnTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(None)
        self.client.force_login(self.staff)

    def run_action(self, action, ret):
        return self.client.post(
            "/admin/orders/returnrequest/",
            {"action": action, "_selected_action": [ret.id]},
            follow=True,
        )

    def test_admin_pages_open(self):
        ret = self.make_return()
        self.assertEqual(self.client.get("/admin/orders/returnrequest/").status_code, 200)
        self.assertEqual(
            self.client.get(f"/admin/orders/returnrequest/{ret.id}/change/").status_code, 200
        )

    def test_admin_actions_run_the_whole_workflow(self):
        ret = self.make_return()
        for action, expected in (
            ("approve_returns", "APPROVED"),
            ("mark_returns_received", "RECEIVED"),
            ("approve_refunds", "REFUNDED"),
        ):
            self.assertEqual(self.run_action(action, ret).status_code, 200)
            ret.refresh_from_db()
            self.assertEqual(ret.status, expected)
        self.assertEqual(Refund.objects.count(), 1)

    def test_admin_reject_needs_a_note(self):
        ret = self.make_return()
        self.run_action("reject_returns", ret)
        ret.refresh_from_db()
        self.assertEqual(ret.status, "REQUESTED")  # no note, so nothing happened
        ReturnRequest.objects.filter(pk=ret.pk).update(admin_note="Not covered by policy.")
        self.run_action("reject_returns", ret)
        ret.refresh_from_db()
        self.assertEqual(ret.status, "REJECTED")

    def test_regular_customers_cannot_open_the_admin(self):
        self.client.logout()
        self.client.force_login(self.alice)
        response = self.client.get("/admin/orders/returnrequest/")
        self.assertNotEqual(response.status_code, 200)
