from django.contrib import admin

from .models import Review, ReviewImage, ReviewVote


class ReviewImageInline(admin.TabularInline):
    model = ReviewImage
    extra = 0


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "product",
        "user",
        "rating",
        "status",
        "is_approved",
        "created_at",
    )
    list_filter = ("status", "is_approved", "rating", "created_at")
    search_fields = (
        "product__name",
        "user__email",
        "title",
        "comment",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "moderated_at",
    )
    inlines = [ReviewImageInline]


@admin.register(ReviewVote)
class ReviewVoteAdmin(admin.ModelAdmin):
    list_display = ("id", "review", "user", "helpful", "created_at")
    list_filter = ("helpful", "created_at")
    search_fields = ("user__email", "review__title")


@admin.register(ReviewImage)
class ReviewImageAdmin(admin.ModelAdmin):
    list_display = ("id", "review", "created_at")
    list_filter = ("created_at",)
