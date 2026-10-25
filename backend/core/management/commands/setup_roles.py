from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from core.roles import ROLE_PERMISSIONS, ROLES, SUPER_ADMIN, resolve_permissions


class Command(BaseCommand):
    help = "Create the five staff roles and give each its permissions (safe to run again)."

    def handle(self, *args, **options):
        for name in ROLES:
            group, _ = Group.objects.get_or_create(name=name)
            if name == SUPER_ADMIN:
                permissions, missing = list(Permission.objects.all()), []
            else:
                permissions, missing = resolve_permissions(ROLE_PERMISSIONS[name])
            group.permissions.set(permissions)
            note = f" ({len(missing)} not available yet)" if missing else ""
            self.stdout.write(f"{name}: {len(permissions)} permissions{note}")
