import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from rest_framework.test import APITestCase

User = get_user_model()
PASSWORD = "Str0ng!Pass#2026"
NEW_PASSWORD = "Br4nd!New#Pass2026"
LINK = re.compile(r"/(?:reset-password|verify-email)/([^/\s]+)/([^/\s]+)/")


def register_payload(email="bob@example.com", password=PASSWORD):
    return {
        "email": email,
        "first_name": "Bob",
        "last_name": "Builder",
        "password": password,
        "password2": password,
    }


ADDRESS = {
    "address_type": "SHIPPING",
    "full_name": "Alice Test",
    "phone": "9876543210",
    "line1": "12 Main Road",
    "city": "Hyderabad",
    "state": "Telangana",
    "postal_code": "500001",
    "is_default": True,
}


class AccountAPITests(APITestCase):
    def setUp(self):
        cache.clear()  # reset rate limiting between tests
        self.user = User.objects.create_user(
            email="alice@example.com", password=PASSWORD, first_name="Alice"
        )

    def login(self, email="alice@example.com", password=PASSWORD):
        return self.client.post(
            "/api/auth/login/", {"email": email, "password": password}, format="json"
        )

    def authenticate(self, login_response):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}")

    def link_parts(self):
        match = LINK.search(mail.outbox[-1].body)
        self.assertIsNotNone(match, "no link found in the email")
        return match.group(1), match.group(2)

    # ---------- registration and login ----------
    def test_register_sends_verification_email(self):
        response = self.client.post("/api/auth/register/", register_payload(), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("password", response.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["bob@example.com"])
        self.assertFalse(User.objects.get(email="bob@example.com").is_email_verified)

    def test_register_rejects_weak_password(self):
        response = self.client.post(
            "/api/auth/register/", register_payload(password="12345678"), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)

    def test_register_rejects_duplicate_email_ignoring_case(self):
        response = self.client.post(
            "/api/auth/register/", register_payload(email="ALICE@example.com"), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_login_and_protected_profile(self):
        self.assertEqual(self.login(password="wrong-password").status_code, 401)
        self.assertEqual(self.client.get("/api/auth/profile/").status_code, 401)
        self.authenticate(self.login())
        response = self.client.get("/api/auth/profile/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], "alice@example.com")

    def test_logout_blacklists_the_refresh_token(self):
        login = self.login()
        self.authenticate(login)
        out = self.client.post(
            "/api/auth/logout/", {"refresh": login.data["refresh"]}, format="json"
        )
        self.assertEqual(out.status_code, 205)
        self.client.credentials()
        again = self.client.post(
            "/api/auth/token/refresh/", {"refresh": login.data["refresh"]}, format="json"
        )
        self.assertEqual(again.status_code, 401)

    # ---------- authorization ----------
    def test_addresses_are_private_to_their_owner(self):
        User.objects.create_user(email="bob@example.com", password=PASSWORD)
        self.authenticate(self.login())
        created = self.client.post("/api/addresses/", ADDRESS, format="json")
        self.assertEqual(created.status_code, 201)
        address_id = created.data["id"]

        self.client.credentials()
        self.authenticate(self.login("bob@example.com"))
        self.assertEqual(self.client.get("/api/addresses/").data["count"], 0)
        self.assertEqual(self.client.get(f"/api/addresses/{address_id}/").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/addresses/{address_id}/").status_code, 404)

    # ---------- password reset ----------
    def test_password_reset_full_flow(self):
        response = self.client.post(
            "/api/auth/password-reset/", {"email": "alice@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        uid, token = self.link_parts()
        body = {"uid": uid, "token": token, "new_password": NEW_PASSWORD}

        done = self.client.post("/api/auth/password-reset/confirm/", body, format="json")
        self.assertEqual(done.status_code, 200)
        self.assertEqual(self.login(password=NEW_PASSWORD).status_code, 200)
        self.assertEqual(self.login().status_code, 401)  # old password is dead

        reuse = self.client.post("/api/auth/password-reset/confirm/", body, format="json")
        self.assertEqual(reuse.status_code, 400)  # a link works only once

    def test_password_reset_does_not_reveal_unknown_emails(self):
        response = self.client.post(
            "/api/auth/password-reset/", {"email": "nobody@example.com"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_rejects_bad_token(self):
        self.client.post("/api/auth/password-reset/", {"email": "alice@example.com"}, format="json")
        uid, _ = self.link_parts()
        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            {"uid": uid, "token": "bad-token", "new_password": NEW_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_password_reset_rejects_weak_new_password(self):
        self.client.post("/api/auth/password-reset/", {"email": "alice@example.com"}, format="json")
        uid, token = self.link_parts()
        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            {"uid": uid, "token": token, "new_password": "12345678"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("new_password", response.data)

    def test_password_reset_revokes_existing_refresh_tokens(self):
        login = self.login()
        self.client.post("/api/auth/password-reset/", {"email": "alice@example.com"}, format="json")
        uid, token = self.link_parts()
        self.client.post(
            "/api/auth/password-reset/confirm/",
            {"uid": uid, "token": token, "new_password": NEW_PASSWORD},
            format="json",
        )
        refresh = self.client.post(
            "/api/auth/token/refresh/", {"refresh": login.data["refresh"]}, format="json"
        )
        self.assertEqual(refresh.status_code, 401)

    # ---------- email verification ----------
    def test_email_verification_flow(self):
        self.client.post("/api/auth/register/", register_payload(), format="json")
        uid, token = self.link_parts()
        response = self.client.post(
            "/api/auth/verify-email/", {"uid": uid, "token": token}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.get(email="bob@example.com").is_email_verified)
        again = self.client.post(
            "/api/auth/verify-email/", {"uid": uid, "token": token}, format="json"
        )
        self.assertEqual(again.status_code, 400)  # link is used up

    def test_sending_verification_email_requires_login(self):
        response = self.client.post("/api/auth/verify-email/send/")
        self.assertEqual(response.status_code, 401)

    def test_logged_in_user_can_request_a_verification_email(self):
        self.authenticate(self.login())
        response = self.client.post("/api/auth/verify-email/send/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.User_verified = User.objects.filter(pk=self.user.pk).update(is_email_verified=True)
        again = self.client.post("/api/auth/verify-email/send/")
        self.assertEqual(again.status_code, 400)
