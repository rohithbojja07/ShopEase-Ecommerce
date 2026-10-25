import shutil
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from core.models import AuditLog
from core.shop_helpers import PASSWORD, make_staff, paid_order
from inventory.models import Inventory
from inventory.services import reserve_many
from orders.models import Order, ReturnRequest
from orders.returns import request_return
from orders.test_returns import delivered_order, png
from orders.tests import make_variant
from products.models import Brand, Category, Product, SubCategory

User = get_user_model()
TEMP_MEDIA = tempfile.mkdtemp()

LISTS = [
    "products", "variants", "categories", "brands", "inventory",
    "orders", "returns", "customers", "audit-logs",
]
ALLOWED = {
    "Super Admin": set(LISTS),
    "Product Manager": {"products", "variants", "categories", "brands", "inventory"},
    "Order Manager": {"orders", "returns", "customers"},
    "Inventory Manager": {"products", "variants", "inventory"},
    "Customer Support": {"orders", "returns", "customers"},
}


def tearDownModule():
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class StaffAPITestCase(APITestCase):
    def setUp(self):
        cache.clear()  # reset rate limiting between tests
        call_command("setup_roles", stdout=StringIO())
        self.customer = User.objects.create_user(email="cust@example.com", password=PASSWORD)
        self.staff = {
            "Super Admin": make_staff("root@example.com", "Super Admin"),
            "Product Manager": make_staff("pm@example.com", "Product Manager"),
            "Order Manager": make_staff("orders@example.com", "Order Manager"),
            "Inventory Manager": make_staff("stock@example.com", "Inventory Manager"),
            "Customer Support": make_staff("support@example.com", "Customer Support"),
        }
        self.root = self.staff["Super Admin"]
        self.pm = self.staff["Product Manager"]
        self.om = self.staff["Order Manager"]
        self.im = self.staff["Inventory Manager"]
        self.cs = self.staff["Customer Support"]

    def login(self, user):
        self.client.force_authenticate(user)


class AccessControlTests(StaffAPITestCase):
    def test_anonymous_users_get_401(self):
        for name in LISTS:
            with self.subTest(name):
                self.assertEqual(self.client.get(f"/api/admin/{name}/").status_code, 401)

    def test_customers_are_refused_everywhere(self):
        self.login(self.customer)
        for name in LISTS:
            with self.subTest(name):
                self.assertEqual(self.client.get(f"/api/admin/{name}/").status_code, 403)
        self.assertEqual(self.client.post("/api/admin/products/", {"name": "Hack"}, format="json").status_code, 403)
        self.assertEqual(self.client.post("/api/admin/customers/1/block/").status_code, 403)
        self.assertEqual(self.client.delete("/api/admin/products/1/").status_code, 403)

    def test_staff_without_a_role_are_refused(self):
        user = User.objects.create_user(email="norole@example.com", password=PASSWORD, is_staff=True)
        self.login(user)
        for name in LISTS:
            with self.subTest(name):
                self.assertEqual(self.client.get(f"/api/admin/{name}/").status_code, 403)

    def test_each_role_reaches_only_its_own_area(self):
        for role, user in self.staff.items():
            self.login(user)
            for name in LISTS:
                expected = 200 if name in ALLOWED[role] else 403
                with self.subTest(role=role, area=name):
                    self.assertEqual(self.client.get(f"/api/admin/{name}/").status_code, expected)

    def test_a_blocked_staff_account_loses_access(self):
        self.pm.is_active = False
        self.pm.save()
        self.login(self.pm)
        self.assertEqual(self.client.get("/api/admin/products/").status_code, 403)


class CatalogManagementTests(StaffAPITestCase):
    def setUp(self):
        super().setUp()
        self.category = Category.objects.create(name="Tablets", slug="tablets")
        self.brand = Brand.objects.create(name="Acme", slug="acme")
        self.login(self.pm)

    def create_product(self, name="Acme Tab", **extra):
        body = {"name": name, "category": self.category.id, "brand": self.brand.id}
        body.update(extra)
        return self.client.post("/api/admin/products/", body, format="json")

    def create_variant(self, product_id, sku="TAB-1", price="1000.00", **extra):
        body = {"product": product_id, "sku": sku, "price": price}
        body.update(extra)
        return self.client.post("/api/admin/variants/", body, format="json")

    def test_category_and_brand_get_automatic_slugs(self):
        category = self.client.post("/api/admin/categories/", {"name": "Smart Speakers"}, format="json")
        self.assertEqual(category.status_code, 201, category.data)
        self.assertEqual(category.data["slug"], "smart-speakers")
        brand = self.client.post("/api/admin/brands/", {"name": "Zed Audio"}, format="json")
        self.assertEqual(brand.data["slug"], "zed-audio")

    def test_product_slugs_are_unique(self):
        first = self.create_product()
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data["slug"], "acme-tab")
        self.assertEqual(self.create_product().data["slug"], "acme-tab-2")

    def test_subcategory_must_belong_to_the_category(self):
        other = Category.objects.create(name="Phones", slug="phones")
        sub = SubCategory.objects.create(category=other, name="Android", slug="android")
        response = self.create_product(subcategory=sub.id)
        self.assertEqual(response.status_code, 400)
        self.assertIn("subcategory", response.data)

    def test_creating_a_variant_creates_its_inventory(self):
        product = self.create_product().data
        response = self.create_variant(product["id"])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["available_stock"], 0)
        self.assertEqual(response.data["final_price"], "1000.00")
        self.assertTrue(Inventory.objects.filter(variant_id=response.data["id"]).exists())

    def test_variant_rules(self):
        product = self.create_product().data
        self.assertEqual(self.create_variant(product["id"]).status_code, 201)
        self.assertEqual(self.create_variant(product["id"], sku="TAB-1", size="x").status_code, 400)
        self.assertEqual(self.create_variant(product["id"], sku="TAB-2", price="0").status_code, 400)
        self.assertEqual(self.create_variant(product["id"], sku="TAB-3").status_code, 400)

    def test_update_is_written_to_the_audit_log(self):
        product = self.create_product().data
        response = self.client.patch(
            f"/api/admin/products/{product['id']}/",
            {"discount_percent": "12.50", "is_featured": True}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["discount_percent"], "12.50")
        entry = AuditLog.objects.filter(action="product.updated").first()
        self.assertEqual(entry.actor, self.pm)
        self.assertEqual(entry.target_type, "Product")

    def test_delete_is_a_soft_delete(self):
        product = self.create_product().data
        self.create_variant(product["id"])
        public = APIClient()
        url = f"/api/products/{product['id']}/"
        self.assertEqual(public.get(url).status_code, 200)
        response = self.client.delete(f"/api/admin/products/{product['id']}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Product.objects.get(pk=product["id"]).is_active)  # still in the database
        self.assertEqual(public.get(url).status_code, 404)                 # hidden from shoppers
        self.assertFalse(self.client.get(f"/api/admin/products/{product['id']}/").data["is_active"])
        self.assertEqual(self.client.post(f"/api/admin/products/{product['id']}/activate/").status_code, 200)
        self.assertEqual(public.get(url).status_code, 200)

    def test_other_roles_cannot_change_the_catalog(self):
        for user in (self.om, self.im, self.cs, self.customer):
            self.login(user)
            self.assertEqual(self.create_product(name="Nope").status_code, 403)
        self.assertFalse(Product.objects.filter(name="Nope").exists())

    def test_image_upload_checks_the_file(self):
        product = self.create_product().data
        url = f"/api/admin/products/{product['id']}/images/"
        ok = self.client.post(url, {"image": png("front.png"), "alt_text": "front", "is_primary": True}, format="multipart")
        self.assertEqual(ok.status_code, 201, ok.data)
        fake = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
        self.assertEqual(self.client.post(url, {"image": fake}, format="multipart").status_code, 400)
        self.login(self.im)
        self.assertEqual(self.client.post(url, {"image": png("other.png")}, format="multipart").status_code, 403)


class InventoryManagementTests(StaffAPITestCase):
    def setUp(self):
        super().setUp()
        self.variant = make_variant("Stock Phone", "1000.00", 10)
        self.inv = Inventory.objects.get(variant=self.variant)
        self.url = f"/api/admin/inventory/{self.inv.id}/"
        self.login(self.im)

    def adjust(self, quantity, reason="Stock count"):
        return self.client.post(f"{self.url}adjust/", {"quantity": quantity, "reason": reason}, format="json")

    def state(self):
        self.inv.refresh_from_db()
        return (self.inv.opening_stock, self.inv.available_stock, self.inv.reserved_stock, self.inv.sold_stock)

    def test_adding_and_removing_stock(self):
        self.assertEqual(self.adjust(5).status_code, 200)
        self.assertEqual(self.state(), (15, 15, 0, 0))
        self.assertEqual(self.adjust(-3).status_code, 200)
        self.assertEqual(self.state(), (12, 12, 0, 0))

    def test_invalid_adjustments_are_refused(self):
        self.assertEqual(self.adjust(-11).status_code, 400)
        self.assertEqual(self.adjust(0).status_code, 400)
        response = self.client.post(f"{self.url}adjust/", {"quantity": 2}, format="json")
        self.assertEqual(response.status_code, 400)  # a reason is required
        self.assertEqual(self.state(), (10, 10, 0, 0))

    def test_totals_stay_consistent_while_stock_is_reserved(self):
        reserve_many([(self.variant.id, 3)])
        self.assertEqual(self.adjust(2).status_code, 200)
        opening, available, reserved, sold = self.state()
        self.assertEqual((available, reserved), (9, 3))
        self.assertEqual(available + reserved + sold, opening)

    def test_only_the_threshold_can_be_edited_directly(self):
        response = self.client.patch(self.url, {"low_stock_threshold": 12, "available_stock": 999}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["low_stock_threshold"], 12)
        self.assertEqual(self.state()[1], 10)

    def test_low_stock_filter(self):
        self.assertEqual(self.client.get("/api/admin/inventory/?low_stock=true").data["count"], 0)
        self.client.patch(self.url, {"low_stock_threshold": 10}, format="json")
        self.assertEqual(self.client.get("/api/admin/inventory/?low_stock=true").data["count"], 1)

    def test_permissions_and_audit_trail(self):
        self.adjust(5, "Delivery from supplier")
        entry = AuditLog.objects.get(action="inventory.adjusted")
        self.assertEqual(entry.actor, self.im)
        self.assertEqual(entry.details["reason"], "Delivery from supplier")
        self.login(self.pm)  # can look, cannot change
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.adjust(5).status_code, 403)
        self.login(self.customer)
        self.assertEqual(self.adjust(5).status_code, 403)


class CustomerManagementTests(StaffAPITestCase):
    def setUp(self):
        super().setUp()
        self.variant = make_variant("Cust Phone", "1000.00", 10, "10")
        delivered_order(self.customer, [(self.variant, 2)])  # 1800 + 324 tax = 2124
        self.url = f"/api/admin/customers/{self.customer.id}/"
        self.creds = {"email": "cust@example.com", "password": PASSWORD}

    def test_customer_list_has_orders_and_spending_but_no_staff(self):
        self.login(self.cs)
        results = self.client.get("/api/admin/customers/").data["results"]
        self.assertEqual([row["email"] for row in results], ["cust@example.com"])
        self.assertEqual(results[0]["order_count"], 1)
        self.assertEqual(results[0]["net_spent"], "2124.00")
        self.assertEqual(self.client.get("/api/admin/customers/?search=nobody").data["count"], 0)

    def test_customer_detail_and_orders(self):
        self.login(self.om)
        detail = self.client.get(self.url).data
        self.assertEqual(len(detail["recent_orders"]), 1)
        self.assertIn("addresses", detail)
        self.assertEqual(self.client.get(f"{self.url}orders/").data["count"], 1)

    def test_blocking_locks_the_customer_out(self):
        shopper = APIClient()
        login = shopper.post("/api/auth/login/", self.creds, format="json")
        self.assertEqual(login.status_code, 200)
        shopper.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        self.assertEqual(shopper.get("/api/cart/").status_code, 200)

        self.login(self.cs)
        blocked = self.client.post(f"{self.url}block/", {"reason": "Fraud check"}, format="json")
        self.assertEqual(blocked.status_code, 200, blocked.data)
        self.assertFalse(blocked.data["is_active"])

        self.assertEqual(shopper.get("/api/cart/").status_code, 401)  # the old access token stops working
        self.assertEqual(APIClient().post("/api/auth/login/", self.creds, format="json").status_code, 401)
        refresh = APIClient().post("/api/auth/token/refresh/", {"refresh": login.data["refresh"]}, format="json")
        self.assertEqual(refresh.status_code, 401)

        self.assertEqual(self.client.post(f"{self.url}unblock/").status_code, 200)
        self.assertEqual(APIClient().post("/api/auth/login/", self.creds, format="json").status_code, 200)

    def test_staff_accounts_cannot_be_blocked_through_this_api(self):
        self.login(self.cs)
        self.assertEqual(self.client.post(f"/api/admin/customers/{self.pm.id}/block/").status_code, 404)
        self.pm.refresh_from_db()
        self.assertTrue(self.pm.is_active)

    def test_only_the_right_roles_can_block(self):
        for user in (self.om, self.pm, self.im, self.customer):
            self.login(user)
            self.assertEqual(self.client.post(f"{self.url}block/").status_code, 403)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)

    def test_activity_shows_staff_actions_on_the_account(self):
        self.login(self.cs)
        self.client.post(f"{self.url}block/", {"reason": "Chargeback"}, format="json")
        activity = self.client.get(f"{self.url}activity/").data
        self.assertFalse(activity["is_active"])
        self.assertEqual(activity["orders"], 1)
        self.assertIn("user.blocked", [entry["action"] for entry in activity["recent_actions"]])


class AuditTrailTests(StaffAPITestCase):
    def test_super_admin_can_read_the_audit_log(self):
        self.login(self.pm)
        self.client.post("/api/admin/categories/", {"name": "Audit Cat"}, format="json")
        self.login(self.root)
        response = self.client.get("/api/admin/audit-logs/?action=category.created")
        self.assertEqual(response.status_code, 200)
        entry = response.data["results"][0]
        self.assertEqual(entry["actor_email"], "pm@example.com")
        self.assertEqual(entry["target_type"], "Category")

    def test_nobody_else_can_read_it(self):
        for user in (self.pm, self.om, self.im, self.cs, self.customer):
            self.login(user)
            self.assertEqual(self.client.get("/api/admin/audit-logs/").status_code, 403)

    def test_the_log_cannot_be_changed_through_the_api(self):
        self.login(self.root)
        self.assertIn(self.client.post("/api/admin/audit-logs/", {}, format="json").status_code, (403, 405))
        self.assertIn(self.client.delete("/api/admin/audit-logs/1/").status_code, (403, 404, 405))
