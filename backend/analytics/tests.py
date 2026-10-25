from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase

from core.shop_helpers import PASSWORD, make_staff, paid_order, placed_order
from orders.returns import approve_refund, approve_return, mark_received, request_return
from orders.services import cancel_order
from orders.test_returns import delivered_order
from orders.tests import make_variant
from products.models import Product
from reviews.models import Review

User = get_user_model()


class AnalyticsTestCase(APITestCase):
    """Scenario with known numbers.

    alice: delivered order, 3 phones (900 each) + 1 cable (200) = 2900 + 522 tax = 3422.00
    bob:   paid order, 1 cable = 200 + 36 tax + 99 shipping = 335.00 (CONFIRMED)
           placed but unpaid order, 1 phone = 1161.00 (PLACED)
    carol: paid order, 1 cable, then cancelled and refunded
    """

    def setUp(self):
        cache.clear()  # reset rate limiting between tests
        call_command("setup_roles", stdout=StringIO())
        self.alice = User.objects.create_user(email="alice@example.com", password=PASSWORD)
        self.bob = User.objects.create_user(email="bob@example.com", password=PASSWORD)
        self.carol = User.objects.create_user(email="carol@example.com", password=PASSWORD)
        self.root = make_staff("root@example.com", "Super Admin")
        self.pm = make_staff("pm@example.com", "Product Manager")
        self.om = make_staff("orders@example.com", "Order Manager")
        self.cs = make_staff("support@example.com", "Customer Support")
        self.phone_v = make_variant("Stat Phone", "1000.00", 10, "10")
        self.cable_v = make_variant("Stat Cable", "200.00", 20)
        self.dead_v = make_variant("Dead Stock", "500.00", 5)
        self.alice_order = delivered_order(self.alice, [(self.phone_v, 3), (self.cable_v, 1)])
        paid_order(self.bob, self.cable_v, 1)
        placed_order(self.bob, self.phone_v, 1)
        cancel_order(paid_order(self.carol, self.cable_v, 1))

    def get(self, user, path):
        self.client.force_authenticate(user)
        return self.client.get(path)

    def refund_alices_cable(self):
        item = self.alice_order.items.get(sku="STAT-CABLE")
        ret = request_return(self.alice, self.alice_order.id, "DEFECTIVE", "Broken", [{"order_item_id": item.id, "quantity": 1}])
        approve_return(ret, self.root)
        mark_received(ret, self.root)
        approve_refund(ret, self.root)


class AnalyticsAccessTests(AnalyticsTestCase):
    URLS = ["dashboard", "sales", "products", "customers"]

    def test_anonymous_users_get_401_and_customers_get_403(self):
        for name in self.URLS:
            with self.subTest(name):
                self.client.force_authenticate(None)
                self.assertEqual(self.client.get(f"/api/admin/analytics/{name}/").status_code, 401)
                self.assertEqual(self.get(self.alice, f"/api/admin/analytics/{name}/").status_code, 403)

    def test_each_role_sees_only_its_own_analytics(self):
        expected = {
            self.root: {"dashboard", "sales", "products", "customers"},
            self.om: {"dashboard", "sales"},
            self.pm: {"products"},
            self.cs: {"customers"},
        }
        for user, allowed in expected.items():
            for name in self.URLS:
                status = 200 if name in allowed else 403
                with self.subTest(user=user.email, area=name):
                    self.assertEqual(self.get(user, f"/api/admin/analytics/{name}/").status_code, status)


class DashboardTests(AnalyticsTestCase):
    def test_dashboard_numbers(self):
        data = self.get(self.om, "/api/admin/analytics/dashboard/").data
        self.assertEqual(data["revenue"], "3757.00")           # 3422 + 335, carol's refunded payment excluded
        self.assertEqual(data["todays_revenue"], "3757.00")
        self.assertEqual(data["monthly_revenue"], "3757.00")
        self.assertEqual(data["total_sales"], 5)                # alice 4 units + bob 1 unit
        self.assertEqual(data["total_orders"], 4)
        self.assertEqual(data["total_customers"], 3)            # staff are not customers
        self.assertEqual(data["total_products"], 3)
        self.assertEqual(data["pending_orders"], 2)             # bob unpaid + bob paid
        self.assertEqual(data["cancelled_orders"], 1)
        self.assertEqual(data["returned_orders"], 0)

    def test_low_stock_is_reported(self):
        data = self.get(self.om, "/api/admin/analytics/dashboard/").data
        self.assertEqual(data["low_stock_variants"], 1)          # only the dead stock item (5 <= 5)
        self.assertEqual(data["low_stock_products"], 1)
        self.assertEqual(data["low_stock_items"][0]["sku"], "DEAD-STOCK")

    def test_a_partial_refund_lowers_revenue(self):
        self.refund_alices_cable()                               # 236.00 back to alice
        data = self.get(self.om, "/api/admin/analytics/dashboard/").data
        self.assertEqual(data["revenue"], "3521.00")
        self.assertEqual(data["todays_revenue"], "3521.00")

    def test_a_full_return_counts_as_a_returned_order(self):
        order = delivered_order(self.carol, [(self.dead_v, 1)])
        ret = request_return(self.carol, order.id, "OTHER")
        approve_return(ret, self.root)
        data = self.get(self.om, "/api/admin/analytics/dashboard/").data
        self.assertEqual(data["returned_orders"], 1)


class SalesSeriesTests(AnalyticsTestCase):
    def series(self, query=""):
        return self.get(self.om, f"/api/admin/analytics/sales/{query}").data["series"]

    def test_default_lengths_and_empty_periods_are_zero(self):
        for period, length in (("daily", 30), ("weekly", 12), ("monthly", 12), ("yearly", 5)):
            with self.subTest(period):
                series = self.series(f"?period={period}")
                self.assertEqual(len(series), length)
                self.assertEqual(series[0]["revenue"], "0.00")
                self.assertEqual(series[0]["orders"], 0)

    def test_the_current_period_holds_todays_sales(self):
        for period in ("daily", "weekly", "monthly", "yearly"):
            with self.subTest(period):
                last = self.series(f"?period={period}")[-1]
                self.assertEqual(last["revenue"], "3757.00")
                self.assertEqual(last["orders"], 2)             # alice and bob's paid orders

    def test_daily_series_ends_today_and_supports_buckets(self):
        series = self.series("?period=daily&buckets=7")
        self.assertEqual(len(series), 7)
        self.assertEqual(series[-1]["period"], timezone.localdate().isoformat())
        self.assertEqual(series[0]["period"], (timezone.localdate() - timedelta(days=6)).isoformat())

    def test_refunds_reduce_the_period_revenue(self):
        self.refund_alices_cable()
        self.assertEqual(self.series("?period=daily")[-1]["revenue"], "3521.00")

    def test_bad_period_is_refused(self):
        self.assertEqual(self.get(self.om, "/api/admin/analytics/sales/?period=hourly").status_code, 400)
        self.assertEqual(self.get(self.om, "/api/admin/analytics/sales/?buckets=abc").status_code, 400)


class ProductAnalyticsTests(AnalyticsTestCase):
    def setUp(self):
        super().setUp()
        for name, views in (("Stat Phone", 50), ("Stat Cable", 10), ("Dead Stock", 5)):
            Product.objects.filter(name=name).update(view_count=views)
        phone = Product.objects.get(name="Stat Phone")
        cable = Product.objects.get(name="Stat Cable")
        Review.objects.create(product=phone, user=self.alice, rating=5, title="Great")
        Review.objects.create(product=cable, user=self.alice, rating=5, title="Great")
        Review.objects.create(product=cable, user=self.bob, rating=3, title="Fine")

    def stats(self, query=""):
        return self.get(self.pm, f"/api/admin/analytics/products/{query}").data

    def test_best_and_lowest_selling(self):
        data = self.stats()
        self.assertEqual([p["name"] for p in data["best_selling"]], ["Stat Phone", "Stat Cable", "Dead Stock"])
        self.assertEqual(data["best_selling"][0]["units_sold"], 3)
        self.assertEqual(data["best_selling"][0]["revenue"], "2700.00")
        self.assertEqual(data["best_selling"][1]["units_sold"], 2)   # carol's cancelled cable is not counted
        self.assertEqual(data["lowest_selling"][0]["name"], "Dead Stock")
        self.assertEqual(data["lowest_selling"][0]["units_sold"], 0)

    def test_most_viewed(self):
        self.assertEqual([p["name"] for p in self.stats()["most_viewed"]], ["Stat Phone", "Stat Cable", "Dead Stock"])

    def test_highest_rated_needs_reviews(self):
        rated = self.stats()["highest_rated"]
        self.assertEqual([p["name"] for p in rated], ["Stat Phone", "Stat Cable"])
        self.assertEqual((rated[0]["average_rating"], rated[0]["review_count"]), (5.0, 1))
        self.assertEqual((rated[1]["average_rating"], rated[1]["review_count"]), (4.0, 2))

    def test_hidden_reviews_do_not_count(self):
        Review.objects.filter(user=self.alice, product__name="Stat Phone").update(status="HIDDEN")
        names = [p["name"] for p in self.stats()["highest_rated"]]
        self.assertEqual(names, ["Stat Cable"])

    def test_limit_and_min_reviews(self):
        self.assertEqual(len(self.stats("?limit=1")["best_selling"]), 1)
        two_or_more = self.stats("?min_reviews=2")["highest_rated"]
        self.assertEqual([p["name"] for p in two_or_more], ["Stat Cable"])
        self.assertEqual(self.get(self.pm, "/api/admin/analytics/products/?limit=x").status_code, 400)


class CustomerAnalyticsTests(AnalyticsTestCase):
    def stats(self, query=""):
        return self.get(self.cs, f"/api/admin/analytics/customers/{query}").data

    def test_new_and_returning_customers(self):
        data = self.stats()
        self.assertEqual(data["total_customers"], 3)
        self.assertEqual(data["new_this_month"], 3)
        self.assertEqual(len(data["new_customers"]), 30)
        self.assertEqual(data["new_customers"][-1]["count"], 3)       # all three registered today
        self.assertEqual(data["returning_customers"], 1)              # only bob has 2 orders
        self.assertEqual(data["repeat_rate_percent"], 33.3)

    def test_order_frequency(self):
        data = self.stats()
        self.assertEqual(data["order_frequency"], {"0": 1, "1": 1, "2": 1, "3": 0, "4+": 0})
        self.assertEqual(data["average_orders_per_customer"], 1.0)    # 3 active orders / 3 customers

    def test_top_customers_by_net_spending(self):
        top = self.stats()["top_customers"]
        self.assertEqual([c["email"] for c in top], ["alice@example.com", "bob@example.com"])
        self.assertEqual(top[0]["net_spent"], "3422.00")
        self.assertEqual(top[1]["net_spent"], "335.00")                # carol spent nothing after her refund

    def test_refunds_reduce_net_spending(self):
        self.refund_alices_cable()
        top = self.stats()["top_customers"]
        self.assertEqual(top[0]["net_spent"], "3186.00")

    def test_days_parameter(self):
        self.assertEqual(len(self.stats("?days=7")["new_customers"]), 7)
        self.assertEqual(self.get(self.cs, "/api/admin/analytics/customers/?days=x").status_code, 400)
