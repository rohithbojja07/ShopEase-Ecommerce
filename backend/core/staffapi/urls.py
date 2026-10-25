from rest_framework.routers import SimpleRouter

from .views import (
    AdminBrandViewSet,
    AdminCategoryViewSet,
    AdminInventoryViewSet,
    AdminProductViewSet,
    AdminVariantViewSet,
    AuditLogViewSet,
    StaffCustomerViewSet,
    StaffOrderViewSet,
    StaffReturnViewSet,
)

router = SimpleRouter()
router.register("products", AdminProductViewSet, basename="staff-product")
router.register("variants", AdminVariantViewSet, basename="staff-variant")
router.register("categories", AdminCategoryViewSet, basename="staff-category")
router.register("brands", AdminBrandViewSet, basename="staff-brand")
router.register("inventory", AdminInventoryViewSet, basename="staff-inventory")
router.register("orders", StaffOrderViewSet, basename="staff-order")
router.register("returns", StaffReturnViewSet, basename="staff-return")
router.register("customers", StaffCustomerViewSet, basename="staff-customer")
router.register("audit-logs", AuditLogViewSet, basename="staff-audit")

urlpatterns = router.urls
