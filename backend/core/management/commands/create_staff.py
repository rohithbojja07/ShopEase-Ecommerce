import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from core.roles import ROLES, SUPER_ADMIN


class Command(BaseCommand):
    help = "Create or update a staff account with exactly one role."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--role", required=True, choices=ROLES)
        parser.add_argument("--password", default=None)
        parser.add_argument("--first-name", dest="first_name", default="")

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            group = Group.objects.get(name=options["role"])
        except Group.DoesNotExist:
            raise CommandError("Roles do not exist yet. Run: python manage.py setup_roles")

        email = User.objects.normalize_email(options["email"]).strip()
        user = User.objects.filter(email__iexact=email).first()
        created = user is None
        password = options["password"]
        if created and not password:
            password = getpass.getpass("Password: ")
        if password:
            try:
                validate_password(password, user)
            except ValidationError as exc:
                raise CommandError(" ".join(exc.messages))

        if created:
            user = User(email=email)
        if options["first_name"]:
            user.first_name = options["first_name"]
        user.is_staff = True
        user.is_superuser = options["role"] == SUPER_ADMIN
        user.is_active = True
        if password:
            user.set_password(password)
        user.save()
        user.groups.set([group])
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} {email} as {options['role']}."))
