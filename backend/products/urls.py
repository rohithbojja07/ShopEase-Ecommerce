from rest_framework.routers import SimpleRouter

from .views import BrandViewSet, CategoryViewSet, ProductViewSet

router = SimpleRouter()
router.register("products", ProductViewSet, basename="product")
router.register("categories", CategoryViewSet, basename="category")
router.register("brands", BrandViewSet, basename="brand")

urlpatterns = router.urls
