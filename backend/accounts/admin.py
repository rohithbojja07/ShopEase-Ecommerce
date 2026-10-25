from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from core.audit import log_action

from .emails import revoke_all_tokens
from .models import Address, User, UserProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "is_staff", "is_active", "last_login")
    list_filter = ("is_active", "is_staff", "is_email_verified")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "is_email_verified")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )
    actions = ["block_customers", "unblock_customers"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        # only a Super Admin can even see staff accounts
        return queryset if request.user.is_superuser else queryset.filter(is_staff=False)

    def has_change_permission(self, request, obj=None):
        # editing accounts, roles and permissions is for Super Admins only
        return request.user.is_superuser

    def has_block_permission(self, request):
        return request.user.has_perm("accounts.change_user")

    @admin.action(description="Block selected customers", permissions=["block"])
    def block_customers(self, request, queryset):
        count = 0
        for user in queryset.filter(is_staff=False, is_active=True):
            user.is_active = False
            user.save(update_fields=["is_active"])
            revoke_all_tokens(user)
            log_action(request, "user.blocked", user, {"via": "admin site"})
            count += 1
        self.message_user(request, f"{count} customer(s) blocked.")

    @admin.action(description="Unblock selected customers", permissions=["block"])
    def unblock_customers(self, request, queryset):
        count = 0
        for user in queryset.filter(is_staff=False, is_active=False):
            user.is_active = True
            user.save(update_fields=["is_active"])
            log_action(request, "user.unblocked", user, {"via": "admin site"})
            count += 1
        self.message_user(request, f"{count} customer(s) unblocked.")


admin.site.register(UserProfile)
admin.site.register(Address)
