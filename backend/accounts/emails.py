from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from .tokens import email_verification_token


def _uid(user):
    return urlsafe_base64_encode(force_bytes(user.pk))


def _send(user, subject, intro, link):
    name = user.first_name or user.email
    body = "\n".join([
        f"Hello {name},",
        "",
        intro,
        link,
        "",
        "The link expires in 24 hours. If you did not request this, ignore this email.",
    ])
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])


def send_password_reset_email(user):
    token = default_token_generator.make_token(user)
    link = f"{settings.SITE_URL}/reset-password/{_uid(user)}/{token}/"
    _send(user, "Reset your password", "Use this link to choose a new password:", link)


def send_verification_email(user):
    token = email_verification_token.make_token(user)
    link = f"{settings.SITE_URL}/verify-email/{_uid(user)}/{token}/"
    _send(user, "Verify your email address", "Use this link to verify your email:", link)


def revoke_all_tokens(user):
    """Blacklist every refresh token the user has, so old logins stop working."""
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)
