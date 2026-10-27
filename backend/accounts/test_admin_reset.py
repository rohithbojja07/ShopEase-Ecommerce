import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()
OLD = "Str0ng!Pass#2026"
NEW = "Br4nd!New#Pass2026"


class AdminPasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(email="boss@example.com", password=OLD)

    def test_login_page_has_the_forgot_link(self):
        self.assertContains(self.client.get("/admin/login/"), "/admin/password_reset/")

    def test_unknown_email_looks_the_same_and_sends_nothing(self):
        response = self.client.post("/admin/password_reset/", {"email": "nobody@example.com"})
        self.assertRedirects(response, "/admin/password_reset/done/")
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_by_email_works_and_ends_old_api_sessions(self):
        RefreshToken.for_user(self.user)  # an old API login
        response = self.client.post("/admin/password_reset/", {"email": "boss@example.com"})
        self.assertRedirects(response, "/admin/password_reset/done/")
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r"http://testserver(/reset/[^/\s]+/[^/\s]+/)", mail.outbox[0].body).group(1)
        page = self.client.get(link, follow=True)
        self.assertEqual(page.status_code, 200)
        done = self.client.post(
            page.request["PATH_INFO"], {"new_password1": NEW, "new_password2": NEW}
        )
        self.assertRedirects(done, "/reset/done/")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))
        self.assertTrue(BlacklistedToken.objects.filter(token__user=self.user).exists())

    def test_weak_new_password_is_refused(self):
        self.client.post("/admin/password_reset/", {"email": "boss@example.com"})
        link = re.search(r"http://testserver(/reset/[^/\s]+/[^/\s]+/)", mail.outbox[0].body).group(1)
        page = self.client.get(link, follow=True)
        self.client.post(page.request["PATH_INFO"], {"new_password1": "12345678", "new_password2": "12345678"})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))
