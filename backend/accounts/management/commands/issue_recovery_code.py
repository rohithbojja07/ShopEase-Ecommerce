import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import PasswordRecoveryCode

User = get_user_model()


class Command(BaseCommand):
    help = "Issue a one-time password recovery code."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, **options):
        email = options["email"].strip()
        user = User.objects.filter(
            email__iexact=email, is_active=True
        ).first()

        if user is None:
            raise CommandError("No active account found for that email.")

        raw_code = secrets.token_hex(16)
        code_hash = hashlib.sha256(
            raw_code.encode("utf-8")
        ).hexdigest()

        PasswordRecoveryCode.objects.update_or_create(
            user=user,
            defaults={
                "code_hash": code_hash,
                "expires_at": timezone.now() + timedelta(minutes=20),
                "used_at": None,
            },
        )

        self.stdout.write(self.style.SUCCESS(
            f"Recovery code for {user.email}: {raw_code}"
        ))
        self.stdout.write(
            "Expires in 20 minutes. It can be used only once."
        )
