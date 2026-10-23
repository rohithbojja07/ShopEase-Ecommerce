from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from orders.models import Order, OrderItem, OrderStatus
from payments.models import Payment, PaymentStatus
from products.models import Category, Product, ProductVariant


class AnalyticsAPITests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.staff = User.objects.create_user(
            email="analytics_staff@example.com",
            password="TestPassword123!",
            is_staff=True,
        )
        self.customer = User.objects.create_user(
            email="analytics_customer@example.com",
            password="TestPassword123!",
            is_staff=False,
        )

        self.staff_client = APIClient()
        self.staff_client.force_authenticate(user=self.staff)

        self.customer_client = APIClient()
        self.customer_client.force_authenticate(user=self.customer)

        self.category = Category.objects.create(
            name="Analytics Test Category",
            slug="analytics-test-category",
        )
        self.product = Product.objects.create(
            name="Analytics Test Product",
            slug="analytics-test-product",
            category=self.category,
            is_active=True,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku=f"ANALYTICS-{uuid4().hex[:10]}",
            price=Decimal("90.00"),
        )

        self.order = Order.objects.create(
            order_number=f"AN-{uuid4().hex[:12]}",
            user=self.customer,
            status=OrderStatus.DELIVERED,
            shipping_address={"city": "Test City"},
            billing_address={"city": "Test City"},
            subtotal=Decimal("180.00"),
            total=Decimal("180.00"),
            expires_at=timezone.now() + timedelta(days=1),
        )

        OrderItem.objects.create(
            order=self.order,
            variant=self.variant,
            product_name=self.product.name,
            sku=self.variant.sku,
            unit_mrp=Decimal("100.00"),
            unit_price=Decimal("90.00"),
            quantity=2,
            line_total=Decimal("180.00"),
        )

        Payment.objects.create(
            order=self.order,
            user=self.customer,
            amount=Decimal("180.00"),
            status=PaymentStatus.SUCCESS,
            transaction_reference=f"PAY-{uuid4().hex[:12]}",
            paid_at=timezone.now(),
        )

    def test_staff_can_access_dashboard(self):
        response = self.staff_client.get("/api/analytics/dashboard/")
        self.assertEqual(response.status_code, 200)

    def test_customer_cannot_access_dashboard(self):
        response = self.customer_client.get("/api/analytics/dashboard/")
        self.assertEqual(response.status_code, 403)

    def test_dashboard_returns_expected_totals(self):
        response = self.staff_client.get("/api/analytics/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_customers"], 1)
        self.assertEqual(response.data["total_products"], 1)
        self.assertEqual(response.data["total_orders"], 1)
        self.assertEqual(response.data["successful_payments"], 1)
        self.assertEqual(Decimal(str(response.data["total_revenue"])),
                         Decimal("180.00"))
        self.assertEqual(response.data["delivered_orders"], 1)

    def test_invalid_sales_days_are_rejected(self):
        for days in ("abc", "0", "366"):
            with self.subTest(days=days):
                response = self.staff_client.get(
                    "/api/analytics/sales/",
                    {"days": days},
                )
                self.assertEqual(response.status_code, 400)

    def test_valid_sales_request_returns_successful_payment(self):
        response = self.staff_client.get(
            "/api/analytics/sales/",
            {"days": 7},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["period_days"], 7)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(
            Decimal(str(response.data["results"][0]["revenue"])),
            Decimal("180.00"),
        )
        self.assertEqual(
            response.data["results"][0]["successful_payments"], 1
        )

    def test_invalid_top_products_limit_is_rejected(self):
        for limit in ("abc", "0", "101"):
            with self.subTest(limit=limit):
                response = self.staff_client.get(
                    "/api/analytics/top-products/",
                    {"limit": limit},
                )
                self.assertEqual(response.status_code, 400)

    def test_top_products_returns_delivered_product(self):
        response = self.staff_client.get(
            "/api/analytics/top-products/",
            {"limit": 10},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(
            response.data["results"][0]["product_name"],
            self.product.name,
        )
        self.assertEqual(response.data["results"][0]["units_sold"], 2)

    def test_order_status_endpoint_returns_all_statuses(self):
        response = self.staff_client.get(
            "/api/analytics/order-status/"
        )

        self.assertEqual(response.status_code, 200)
        results = response.data["results"]
        self.assertTrue(
            any(
                item["status"] == OrderStatus.DELIVERED
                and item["count"] == 1
                for item in results
            )
        )

    def test_customer_cannot_access_other_analytics_endpoints(self):
        endpoints = (
            "/api/analytics/sales/",
            "/api/analytics/top-products/",
            "/api/analytics/order-status/",
        )

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.customer_client.get(endpoint)
                self.assertEqual(response.status_code, 403)
