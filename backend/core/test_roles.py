from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from core.roles import ROLES
from core.shop_helpers import PASSWORD, make_staff, paid_order, role_permissions, setup_roles
from inventory.models import Inventory
from orders.tests import make_variant

User = get_user_model()


class RoleSetupTests(TestCase):
    def setUp(self):
        setup_roles()

    def test_the_five_roles_exist(self):
        self.assertEqual(set(Group.objects.values_list("name", flat=True)), set(ROLES))

    def test_permissions_differ_by_role(self):
        pm = role_permissions("Product Manager")
        om = role_permissions("Order Manager")
        im = role_permissions("Inventory Manager")
        cs = role_permissions("Customer Support")
        sa = role_permissions("Super Admin")
        self.assertIn("products.add_product", pm)
        self.assertNotIn("orders.change_order", pm)
        self.assertIn("orders.change_order", om)
        self.assertNotIn("products.add_product", om)
        self.assertIn("inventory.change_inventory", im)
        self.assertNotIn("inventory.change_inventory", pm)
        self.assertIn("accounts.change_user", cs)
        self.assertNotIn("accounts.change_user", om)
        self.assertNotIn("orders.change_order", cs)
        self.assertIn("core.view_auditlog", sa)
        self.assertNotIn("core.view_auditlog", om)
        self.assertGreater(len(sa), len(om) + len(pm))

    def test_only_super_admin_can_delete_anything(self):
        for name in ROLES[1:]:
            deletes = [p for p in role_permissions(name) if ".delete_" in p]
            self.assertEqual(deletes, [], name)

    def test_setup_can_be_repeated(self):
        before = {name: role_permissions(name) for name in ROLES}
        setup_roles()
        self.assertEqual(Group.objects.count(), 5)
        self.assertEqual({name: role_permissions(name) for name in ROLES}, before)


class CreateStaffTests(TestCase):
    def setUp(self):
        setup_roles()

    def test_creates_a_staff_account_with_one_role(self):
        user = make_staff("pm@example.com", "Product Manager")
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(list(user.groups.values_list("name", flat=True)), ["Product Manager"])

    def test_super_admin_is_a_superuser(self):
        self.assertTrue(make_staff("boss@example.com", "Super Admin").is_superuser)

    def test_changing_the_role_replaces_the_old_one(self):
        make_staff("move@example.com", "Product Manager")
        user = make_staff("move@example.com", "Order Manager")
        self.assertEqual(list(user.groups.values_list("name", flat=True)), ["Order Manager"])

    def test_unknown_role_and_weak_password_are_refused(self):
        with self.assertRaises(CommandError):
            call_command("create_staff", "x@example.com", role="Boss", password=PASSWORD, stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("create_staff", "x@example.com", role="Product Manager", password="12345678", stdout=StringIO())
        self.assertFalse(User.objects.filter(email="x@example.com").exists())


class AdminSiteTests(TestCase):
    def setUp(self):
        setup_roles()
        self.customer = User.objects.create_user(email="cust@example.com", password=PASSWORD)
        self.root = make_staff("boss@example.com", "Super Admin")
        self.pm = make_staff("pm@example.com", "Product Manager")
        self.om = make_staff("orders@example.com", "Order Manager")
        self.im = make_staff("stock@example.com", "Inventory Manager")
        self.cs = make_staff("support@example.com", "Customer Support")

    def get(self, user, path):
        self.client.force_login(user)
        return self.client.get(path)

    def test_roles_only_see_their_own_pages(self):
        self.assertEqual(self.get(self.pm, "/admin/products/product/").status_code, 200)
        self.assertEqual(self.get(self.pm, "/admin/orders/order/").status_code, 403)
        self.assertEqual(self.get(self.om, "/admin/orders/order/").status_code, 200)
        self.assertEqual(self.get(self.om, "/admin/products/product/").status_code, 403)
        self.assertEqual(self.get(self.im, "/admin/inventory/inventory/").status_code, 200)
        self.assertEqual(self.get(self.im, "/admin/orders/order/").status_code, 403)

    def test_staff_without_a_role_see_nothing(self):
        user = User.objects.create_user(email="norole@example.com", password=PASSWORD, is_staff=True)
        self.assertEqual(self.get(user, "/admin/products/product/").status_code, 403)
        self.assertEqual(self.get(user, "/admin/accounts/user/").status_code, 403)

    def test_customers_cannot_open_the_admin_site(self):
        self.assertEqual(self.get(self.customer, "/admin/").status_code, 302)

    def test_only_the_super_admin_manages_groups_and_the_audit_log(self):
        self.assertEqual(self.get(self.pm, "/admin/auth/group/").status_code, 403)
        self.assertEqual(self.get(self.root, "/admin/auth/group/").status_code, 200)
        self.assertEqual(self.get(self.om, "/admin/core/auditlog/").status_code, 403)
        self.assertEqual(self.get(self.root, "/admin/core/auditlog/").status_code, 200)

    def test_support_sees_customers_but_never_staff(self):
        response = self.get(self.cs, "/admin/accounts/user/")
        self.assertContains(response, "cust@example.com")
        self.assertNotContains(response, "boss@example.com")
        self.assertNotContains(response, "pm@example.com")
        staff_page = self.get(self.cs, f"/admin/accounts/user/{self.root.id}/change/")
        self.assertEqual(staff_page.status_code, 302)  # not found for them

    def test_support_cannot_edit_accounts_or_promote_anyone(self):
        self.client.force_login(self.cs)
        url = f"/admin/accounts/user/{self.customer.id}/change/"
        response = self.client.post(url, {"email": "cust@example.com", "is_superuser": "on", "is_staff": "on"})
        self.assertEqual(response.status_code, 403)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_superuser)
        self.assertFalse(self.customer.is_staff)

    def test_support_can_block_and_unblock_customers(self):
        self.client.force_login(self.cs)
        self.client.post("/admin/accounts/user/", {"action": "block_customers", "_selected_action": [self.customer.pk]}, follow=True)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)
        self.client.post("/admin/accounts/user/", {"action": "unblock_customers", "_selected_action": [self.customer.pk]}, follow=True)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)

    def test_roles_without_the_permission_cannot_block(self):
        self.client.force_login(self.om)
        self.client.post("/admin/accounts/user/", {"action": "block_customers", "_selected_action": [self.customer.pk]}, follow=True)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)

    def test_order_actions_need_the_change_permission(self):
        order = paid_order(self.customer, make_variant("Role Phone", "1000.00", 10))
        data = {"action": "mark_packed", "_selected_action": [order.pk]}
        self.client.force_login(self.cs)  # view-only on orders
        self.client.post("/admin/orders/order/", data, follow=True)
        order.refresh_from_db()
        self.assertEqual(order.status, "CONFIRMED")
        self.client.force_login(self.om)
        self.client.post("/admin/orders/order/", data, follow=True)
        order.refresh_from_db()
        self.assertEqual(order.status, "PACKED")

    def test_hand_edited_stock_keeps_the_totals_consistent(self):
        variant = make_variant("Admin Phone", "1000.00", 10)
        inv = Inventory.objects.get(variant=variant)
        self.client.force_login(self.im)
        url = f"/admin/inventory/inventory/{inv.id}/change/"
        self.client.post(url, {"variant": variant.id, "available_stock": 15, "low_stock_threshold": 5})
        inv.refresh_from_db()
        self.assertEqual((inv.available_stock, inv.opening_stock), (15, 15))
        self.client.post(url, {"variant": variant.id, "available_stock": 4, "low_stock_threshold": 5})
        inv.refresh_from_db()
        self.assertEqual((inv.available_stock, inv.opening_stock), (4, 4))
        self.assertEqual(inv.available_stock + inv.reserved_stock + inv.sold_stock, inv.opening_stock)
