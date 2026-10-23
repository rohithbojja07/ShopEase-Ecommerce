from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "user",
        "rating",
        "is_approved",
        "created_at",
    )
    list_filter = ("rating", "is_approved", "created_at")
    search_fields = ("product__name", "user__email", "title", "comment")
    list_editable = ("is_approved",)
    readonly_fields = ("created_at", "updated_at")
