from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class StaffPortalAuthenticationTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.login_url = reverse("staff_portal:login")
        self.dashboard_url = reverse("staff_portal:dashboard")
        self.password = "Test-Staff-Password-2026!"

    def create_user(self, email, *, is_staff=False, is_superuser=False, active=True):
        return self.User.objects.create_user(
            email=email,
            password=self.password,
            is_staff=is_staff,
            is_superuser=is_superuser,
            is_active=active,
        )

    def test_valid_staff_can_login(self):
        user = self.create_user("staff@example.com", is_staff=True, is_superuser=True)
        response = self.client.post(
            self.login_url,
            {"email": user.email, "password": self.password},
        )
        self.assertRedirects(response, self.dashboard_url)
        self.assertIn("_auth_user_id", self.client.session)

    def test_customer_cannot_login_to_staff_portal(self):
        user = self.create_user("customer@example.com")
        response = self.client.post(
            self.login_url,
            {"email": user.email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "You do not have access to the staff portal.")

    def test_staff_without_role_cannot_login(self):
        user = self.create_user("norole@example.com", is_staff=True)
        response = self.client.post(
            self.login_url,
            {"email": user.email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "No staff role is assigned to this account.")

    def test_invalid_password_is_rejected(self):
        user = self.create_user("invalid@example.com", is_staff=True, is_superuser=True)
        response = self.client.post(
            self.login_url,
            {"email": user.email, "password": "Wrong-Password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "Invalid email or password.")

    def test_inactive_staff_cannot_login(self):
        user = self.create_user(
            "inactive@example.com",
            is_staff=True,
            is_superuser=True,
            active=False,
        )
        response = self.client.post(
            self.login_url,
            {"email": user.email, "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post(self):
        response = self.client.get(reverse("staff_portal:logout"))
        self.assertEqual(response.status_code, 405)

    def test_post_logout_ends_session(self):
        self.create_user("logout@example.com", is_staff=True, is_superuser=True)
        self.client.login(email="logout@example.com", password=self.password)
        self.assertIn("_auth_user_id", self.client.session)

        response = self.client.post(reverse("staff_portal:logout"))

        self.assertRedirects(response, self.login_url)
        self.assertNotIn("_auth_user_id", self.client.session)
