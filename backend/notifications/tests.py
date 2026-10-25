from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from rest_framework.test import APITestCase

from orders.services import cancel_order, place_order
from orders.test_returns import delivered_order
from orders.tests import fill_cart, make_address, make_variant
from payments.services import create_payment, verify_payment

from .models import Notification

User = get_user_model()
PASSWORD = "Str0ng!Pass#2026"


class NotificationAPITests(APITestCase):
    def setUp(self):
        cache.clear()  # reset rate limiting between tests
        self.alice = User.objects.create_user(email="alice@example.com", password=PASSWORD)
        self.bob = User.objects.create_user(email="bob@example.com", password=PASSWORD)
        for index in range(3):
            Notification.objects.create(
                user=self.alice, kind="ORDER", title=f"Title {index}", message="Hello"
            )
        self.bobs = Notification.objects.create(
            user=self.bob, kind="ORDER", title="Bob only", message="Private"
        )
        self.client.force_authenticate(self.alice)

    def test_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/notifications/").status_code, 401)

    def test_list_is_private_and_newest_first(self):
        data = self.client.get("/api/notifications/").data
        self.assertEqual(data["count"], 3)
        self.assertEqual(data["results"][0]["title"], "Title 2")
        self.assertNotIn("Bob only", [item["title"] for item in data["results"]])

    def test_unread_count_and_mark_one_read(self):
        self.assertEqual(self.client.get("/api/notifications/unread-count/").data["unread"], 3)
        first = Notification.objects.filter(user=self.alice).first()
        response = self.client.post(f"/api/notifications/{first.id}/read/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_read"])
        self.assertEqual(self.client.get("/api/notifications/unread-count/").data["unread"], 2)

    def test_mark_all_read(self):
        response = self.client.post("/api/notifications/read-all/")
        self.assertEqual(response.data["marked_read"], 3)
        self.assertEqual(self.client.get("/api/notifications/unread-count/").data["unread"], 0)
        self.bobs.refresh_from_db()
        self.assertFalse(self.bobs.is_read)  # someone else's notification is untouched

    def test_cannot_read_someone_elses_notification(self):
        response = self.client.post(f"/api/notifications/{self.bobs.id}/read/")
        self.assertEqual(response.status_code, 404)
        self.bobs.refresh_from_db()
        self.assertFalse(self.bobs.is_read)

    def test_filter_by_read_state(self):
        first = Notification.objects.filter(user=self.alice).first()
        self.client.post(f"/api/notifications/{first.id}/read/")
        unread = self.client.get("/api/notifications/?is_read=false").data
        self.assertEqual(unread["count"], 2)


class NotificationEventTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user(
            email="alice@example.com", password=PASSWORD, first_name="Alice"
        )
        self.variant = make_variant("Notify Phone", "1000.00", 10)
        self.address = make_address(self.alice)

    def titles(self):
        return list(
            Notification.objects.filter(user=self.alice).order_by("id")
            .values_list("title", flat=True)
        )

    def test_placing_an_order_notifies_and_emails(self):
        fill_cart(self.alice, self.variant, 1)
        with self.captureOnCommitCallbacks(execute=True):
            order = place_order(self.alice, self.address.id)
        self.assertEqual(self.titles(), ["Order placed"])
        self.assertIn(order.order_number, Notification.objects.get().message)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Order placed")
        self.assertEqual(mail.outbox[0].to, ["alice@example.com"])

    def test_failed_payment_gets_its_own_title(self):
        fill_cart(self.alice, self.variant, 1)
        order = place_order(self.alice, self.address.id)
        payment, _ = create_payment(self.alice, order.id, "CARD")
        verify_payment(self.alice, payment.id, payment.transaction_reference, "tok_declined")
        self.assertEqual(self.titles(), ["Order placed", "Payment update"])

    def test_every_lifecycle_step_creates_one_notification(self):
        delivered_order(self.alice, [(self.variant, 1)])
        self.assertEqual(
            self.titles(),
            [
                "Order placed", "Order confirmed", "Order packed",
                "Order shipped", "Out for delivery", "Order delivered",
            ],
        )

    def test_cancellation_notifies(self):
        fill_cart(self.alice, self.variant, 1)
        order = place_order(self.alice, self.address.id)
        cancel_order(order, by=self.alice)
        self.assertEqual(self.titles()[-1], "Order cancelled")

    def test_a_mail_failure_never_breaks_the_order(self):
        fill_cart(self.alice, self.variant, 1)
        with mock.patch("notifications.services.send_mail", side_effect=Exception("smtp down")):
            with self.captureOnCommitCallbacks(execute=True):
                order = place_order(self.alice, self.address.id)
        self.assertEqual(order.status, "PLACED")
        self.assertEqual(self.titles(), ["Order placed"])
