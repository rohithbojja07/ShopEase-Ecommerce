from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "kind", "title", "is_read")
    list_filter = ("kind", "is_read")
    search_fields = ("user__email", "title", "message")
    readonly_fields = [field.name for field in Notification._meta.fields]

    def has_add_permission(self, request):
        return False
