from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from core.audit import log_action
from core.permissions import StaffPermission
from .models import Review
from .serializers import StaffReviewSerializer
from .views import review_queryset


class StaffReviewViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [StaffPermission]
    serializer_class = StaffReviewSerializer

    permission_map = {
        "list": "reviews.view_review",
        "retrieve": "reviews.view_review",
        "hide": "reviews.change_review",
        "publish": "reviews.change_review",
    }

    filterset_fields = ["status", "rating", "product"]
    search_fields = ["title", "comment", "user__email"]
    ordering_fields = ["created_at", "rating"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        return review_queryset(self.request.user)

    def _moderate(self, request, new_status, note, audit_action):
        review = self.get_object()

        review.status = new_status
        review.is_approved = new_status == Review.Status.PUBLISHED
        review.moderation_note = note
        review.moderated_by = request.user
        review.moderated_at = timezone.now()

        review.save(
            update_fields=[
                "status",
                "is_approved",
                "moderation_note",
                "moderated_by",
                "moderated_at",
                "updated_at",
            ]
        )

        log_action(request, audit_action, review, {"note": note})

        return Response(
            self.get_serializer(review).data
        )

    @action(detail=True, methods=["post"])
    def hide(self, request, pk=None):
        note = request.data.get("note", "")
        if not isinstance(note, str) or not note.strip():
            raise ValidationError({"note": "A moderation note is required."})
        if len(note.strip()) > 200:
            raise ValidationError({"note": "The note cannot exceed 200 characters."})

        return self._moderate(
            request,
            Review.Status.HIDDEN,
            note.strip(),
            "review_hidden",
        )

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        note = request.data.get("note", "")
        if not isinstance(note, str) or len(note) > 200:
            raise ValidationError({"note": "The note cannot exceed 200 characters."})

        return self._moderate(
            request,
            Review.Status.PUBLISHED,
            note.strip(),
            "review_published",
        )


router = SimpleRouter()
router.register("reviews", StaffReviewViewSet, basename="staff-review")
urlpatterns = router.urls
