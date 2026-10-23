
from decimal import Decimal
from datetime import timedelta

from django.utils import timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from orders.models import Order, OrderStatus
from payments.models import Payment, PaymentMethod, PaymentStatus


User = get_user_model()


class PaymentSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="payment_owner@example.com",
            password="TestPassword123!"
        )
        cls.other_user = User.objects.create_user(
            email="payment_other@example.com",
            password="TestPassword123!"
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def create_order(self, user=None, status=OrderStatus.PLACED):
        user = user or self.user

        test_address = {
            "full_name": "Test User",
            "phone": "9999999999",
            "address_line1": "123 Test Street",
            "address_line2": "",
            "city": "Hyderabad",
            "state": "Telangana",
            "postal_code": "500001",
            "country": "India",
        }

        return Order.objects.create(
            user=user,
            status=status,
            total=Decimal("500.00"),
            shipping_address=test_address,
            billing_address=test_address.copy(),
            expires_at=timezone.now() + timedelta(hours=1),
        )

    def test_unauthenticated_payment_creation_is_rejected(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            "/api/payment/create/",
            {"order_id": 1, "method": PaymentMethod.CARD},
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_user_cannot_create_payment_for_another_users_order(self):
        order = self.create_order(user=self.other_user)

        response = self.client.post(
            "/api/payment/create/",
            {"order_id": order.pk, "method": PaymentMethod.CARD},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Payment.objects.filter(order=order).exists())

    def test_client_cannot_supply_payment_amount(self):
        order = self.create_order()

        response = self.client.post(
            "/api/payment/create/",
            {
                "order_id": order.pk,
                "method": PaymentMethod.CARD,
                "amount": "1.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.filter(order=order).exists())

    def test_cancelled_order_cannot_be_paid(self):
        order = self.create_order(status=OrderStatus.CANCELLED)

        response = self.client.post(
            "/api/payment/create/",
            {"order_id": order.pk, "method": PaymentMethod.CARD},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.filter(order=order).exists())

    def test_wrong_transaction_reference_is_rejected(self):
        order = self.create_order()
        payment = Payment.objects.create(
            order=order,
            user=self.user,
            amount=order.total,
            method=PaymentMethod.CARD,
            transaction_reference="SBX-TEST-REFERENCE",
        )

        response = self.client.post(
            "/api/payment/verify/",
            {
                "payment_id": payment.pk,
                "transaction_reference": "SBX-WRONG-REFERENCE",
                "token": "tok_success",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.PENDING)

    def test_user_cannot_verify_another_users_payment(self):
        order = self.create_order(user=self.other_user)
        payment = Payment.objects.create(
            order=order,
            user=self.other_user,
            amount=order.total,
            method=PaymentMethod.CARD,
            transaction_reference="SBX-OTHER-REFERENCE",
        )

        response = self.client.post(
            "/api/payment/verify/",
            {
                "payment_id": payment.pk,
                "transaction_reference": payment.transaction_reference,
                "token": "tok_success",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.PENDING)

    @patch("payments.services.confirm_sale_many")
    def test_repeated_successful_verification_does_not_repeat_sale(
        self, confirm_sale_mock
    ):
        order = self.create_order()
        payment = Payment.objects.create(
            order=order,
            user=self.user,
            amount=order.total,
            method=PaymentMethod.CARD,
            transaction_reference="SBX-IDEMPOTENCY-TEST",
        )

        payload = {
            "payment_id": payment.pk,
            "transaction_reference": payment.transaction_reference,
            "token": "tok_success",
        }

        first_response = self.client.post(
            "/api/payment/verify/", payload, format="json"
        )
        self.assertEqual(first_response.status_code, 200)

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.SUCCESS)

        second_response = self.client.post(
            "/api/payment/verify/", payload, format="json"
        )
        self.assertEqual(second_response.status_code, 200)

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.SUCCESS)
        confirm_sale_mock.assert_called_once()
