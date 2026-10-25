from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import ProductReviewListView, ReviewEligibilityView, ReviewViewSet

router = SimpleRouter()
router.register("reviews", ReviewViewSet, basename="review")

urlpatterns = [
    path(
        "products/<int:product_id>/reviews/",
        ProductReviewListView.as_view(),
        name="product-reviews",
    ),
    path(
        "reviews/eligibility/",
        ReviewEligibilityView.as_view(),
        name="review-eligibility",
    ),
] + router.urls
