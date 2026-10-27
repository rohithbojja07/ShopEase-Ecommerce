from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from accounts.emails import revoke_all_tokens
from core.audit import log_action


class Command(BaseCommand):
    help = "Change the login email of an account (for when you cannot log in)."

    def add_arguments(self, parser):
        parser.add_argument("old_email")
        parser.add_argument("new_email")

    def handle(self, *args, **options):
        User = get_user_model()
        old = options["old_email"].strip()
        new = User.objects.normalize_email(options["new_email"].strip())
        try:
            validate_email(new)
        except ValidationError:
            raise CommandError("The new email address is not valid.")
        user = User.objects.filter(email__iexact=old).first()
        if user is None:
            raise CommandError(f"No account with the email {old}.")
        if User.objects.filter(email__iexact=new).exclude(pk=user.pk).exists():
            raise CommandError(f"{new} is already used by another account.")
        user.email = new
        user.is_email_verified = False
        user.save(update_fields=["email", "is_email_verified"])
        revoke_all_tokens(user)
        log_action(None, "user.email_changed", user, {"from": old, "to": new})
        self.stdout.write(self.style.SUCCESS(f"Email changed from {old} to {new}."))
