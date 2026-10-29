from django.db.models import F, Q
from rest_framework import mixins, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.emails import revoke_all_tokens
from core.audit import log_action
from core.models import AuditLog
from core.permissions import StaffPermission, crud_permissions
from inventory.models import Inventory
from inventory.services import adjust_stock
from orders.models import Order, ReturnRequest
from orders.returns import (
    ReturnError, approve_refund, approve_return, mark_received, reject_return,
)
from orders.services import OrderError, set_status
from products.models import Brand, Category, Product, ProductVariant

from .queries import customers_queryset
from .serializers import (
    AdminBrandSerializer,
    AdminCategorySerializer,
    AdminImageSerializer,
    AdminInventorySerializer,
    AdminProductSerializer,
    AdminVariantSerializer,
    AuditLogSerializer,
    CustomerDetailSerializer,
    CustomerListSerializer,
    OrderStatusSerializer,
    ReturnNoteSerializer,
    StaffOrderDetailSerializer,
    StaffOrderListSerializer,
    StaffReturnSerializer,
    StockAdjustSerializer,
)


class AuditedModelViewSet(viewsets.ModelViewSet):
    """Staff CRUD. DELETE never removes data: it deactivates the record."""

    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [StaffPermission]
    audit_name = "record"

    def perform_create(self, serializer):
        obj = serializer.save()
        log_action(self.request, f"{self.audit_name}.created", obj, {"data": serializer.data})

    def perform_update(self, serializer):
        obj = serializer.save()
        log_action(
            self.request, f"{self.audit_name}.updated", obj,
            {"changed": list(serializer.validated_data)},
        )

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        log_action(self.request, f"{self.audit_name}.deactivated", instance)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        obj = self.get_object()
        obj.is_active = True
        obj.save(update_fields=["is_active", "updated_at"])
        log_action(request, f"{self.audit_name}.activated", obj)
        return Response(self.get_serializer(obj).data)


class AdminProductViewSet(AuditedModelViewSet):
    queryset = Product.objects.select_related("category", "subcategory", "brand")
    serializer_class = AdminProductSerializer
    audit_name = "product"
    permission_map = {
        **crud_permissions("products", "product"),
        "activate": "products.change_product",
        "images": "products.change_product",
    }
    filterset_fields = ["is_active", "is_featured", "category", "subcategory", "brand"]
    search_fields = ["name", "description", "slug"]
    ordering_fields = ["name", "created_at", "view_count"]
    ordering = ["-created_at", "-id"]

    @action(detail=True, methods=["post"])
    def images(self, request, pk=None):
        product = self.get_object()
        serializer = AdminImageSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        image = serializer.save(product=product)
        log_action(request, "product.image_added", product, {"image_id": image.id})
        return Response(serializer.data, status=201)


class AdminVariantViewSet(AuditedModelViewSet):
    queryset = ProductVariant.objects.select_related("product", "inventory")
    serializer_class = AdminVariantSerializer
    audit_name = "variant"
    permission_map = {
        **crud_permissions("products", "productvariant"),
        "activate": "products.change_productvariant",
    }
    filterset_fields = ["is_active", "product"]
    search_fields = ["sku", "product__name", "color", "size"]
    ordering_fields = ["sku", "price"]
    ordering = ["product_id", "sku"]


class AdminCategoryViewSet(AuditedModelViewSet):
    queryset = Category.objects.all()
    serializer_class = AdminCategorySerializer
    audit_name = "category"
    permission_map = {
        **crud_permissions("products", "category"),
        "activate": "products.change_category",
    }
    filterset_fields = ["is_active"]
    search_fields = ["name"]
    ordering = ["name"]


class AdminBrandViewSet(AuditedModelViewSet):
    queryset = Brand.objects.all()
    serializer_class = AdminBrandSerializer
    audit_name = "brand"
    permission_map = {
        **crud_permissions("products", "brand"),
        "activate": "products.change_brand",
    }
    filterset_fields = ["is_active"]
    search_fields = ["name"]
    ordering = ["name"]


class AdminInventoryViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [StaffPermission]
    serializer_class = AdminInventorySerializer
    http_method_names = ["get", "patch", "post", "head", "options"]
    permission_map = {
        "list": "inventory.view_inventory",
        "retrieve": "inventory.view_inventory",
        "partial_update": "inventory.change_inventory",
        "adjust": "inventory.change_inventory",
    }
    search_fields = ["variant__sku", "variant__product__name"]
    ordering_fields = ["available_stock", "updated_at"]
    ordering = ["available_stock", "id"]

    def get_queryset(self):
        queryset = Inventory.objects.select_related("variant__product")
        if self.request.query_params.get("low_stock") in ("1", "true", "True"):
            queryset = queryset.filter(available_stock__lte=F("low_stock_threshold"))
        return queryset

    def perform_update(self, serializer):
        obj = serializer.save()
        log_action(
            self.request, "inventory.updated", obj, {"changed": list(serializer.validated_data)}
        )

    @action(detail=True, methods=["post"])
    def adjust(self, request, pk=None):
        inventory = self.get_object()
        data = StockAdjustSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            adjust_stock(inventory.variant_id, data.validated_data["quantity"])
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})
        log_action(request, "inventory.adjusted", inventory, dict(data.validated_data))
        inventory.refresh_from_db()
        return Response(self.get_serializer(inventory).data)


class StaffOrderViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [StaffPermission]
    permission_map = {
        "list": "orders.view_order",
        "retrieve": "orders.view_order",
        "status": "orders.change_order",
    }
    filterset_fields = ["status", "shipping_method", "user"]
    search_fields = ["order_number", "user__email"]
    ordering_fields = ["created_at", "total"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        return Order.objects.select_related("user", "shipment").prefetch_related(
            "items", "payments", "history"
        )

    def get_serializer_class(self):
        return StaffOrderListSerializer if self.action == "list" else StaffOrderDetailSerializer

    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        """Move an order forward. Returns and refunds have their own endpoints."""
        order = self.get_object()
        data = OrderStatusSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            set_status(
                order, data.validated_data["status"], by=request.user,
                note=data.validated_data["note"],
            )
        except OrderError as exc:
            raise ValidationError({"detail": str(exc)})
        log_action(request, "order.status_changed", order, {"to": data.validated_data["status"]})
        fresh = self.get_queryset().get(pk=order.pk)
        return Response(StaffOrderDetailSerializer(fresh, context=self.get_serializer_context()).data)


class StaffReturnViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [StaffPermission]
    serializer_class = StaffReturnSerializer
    permission_map = {
        "list": "orders.view_returnrequest",
        "retrieve": "orders.view_returnrequest",
        "approve": "orders.change_returnrequest",
        "reject": "orders.change_returnrequest",
        "receive": "orders.change_returnrequest",
        "refund": "orders.change_returnrequest",
    }
    filterset_fields = ["status", "reason"]
    search_fields = ["return_number", "order__order_number", "user__email"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        return ReturnRequest.objects.select_related("order", "user", "refund").prefetch_related(
            "items__order_item", "evidence", "events"
        )

    def _step(self, request, function, audit, *args):
        ret = self.get_object()
        try:
            function(ret, request.user, *args)
        except ReturnError as exc:
            raise ValidationError({"detail": str(exc)})
        log_action(request, audit, ret)
        fresh = self.get_queryset().get(pk=ret.pk)
        return Response(self.get_serializer(fresh).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._step(request, approve_return, "return.approved")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        data = ReturnNoteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return self._step(request, reject_return, "return.rejected", data.validated_data["note"])

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        return self._step(request, mark_received, "return.received")

    @action(detail=True, methods=["post"])
    def refund(self, request, pk=None):
        return self._step(request, approve_refund, "return.refunded")


class StaffCustomerViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [StaffPermission]
    permission_map = {
        "list": "accounts.view_user",
        "retrieve": "accounts.view_user",
        "activity": "accounts.view_user",
        "orders": ["accounts.view_user", "orders.view_order"],
        "block": "accounts.change_user",
        "unblock": "accounts.change_user",
    }
    filterset_fields = ["is_active", "is_email_verified"]
    search_fields = ["email", "first_name", "last_name"]
    ordering_fields = ["date_joined", "last_login", "order_count", "net_spent", "email"]
    ordering = ["-date_joined", "-id"]

    def get_queryset(self):
        return customers_queryset()  # staff accounts are never in this list

    def get_serializer_class(self):
        return CustomerDetailSerializer if self.action == "retrieve" else CustomerListSerializer

    def _fresh(self, user):
        return CustomerListSerializer(self.get_queryset().get(pk=user.pk)).data

    @action(detail=True, methods=["post"])
    def block(self, request, pk=None):
        user = self.get_object()
        reason = str(request.data.get("reason", "") or "").strip()[:200]
        if user.is_active:
            user.is_active = False
            user.save(update_fields=["is_active"])
            revoke_all_tokens(user)  # old refresh tokens stop working at once
            log_action(request, "user.blocked", user, {"reason": reason})
        return Response(self._fresh(user))

    @action(detail=True, methods=["post"])
    def unblock(self, request, pk=None):
        user = self.get_object()
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
            log_action(request, "user.unblocked", user)
        return Response(self._fresh(user))

    @action(detail=True, methods=["get"])
    def orders(self, request, pk=None):
        customer = self.get_object()
        queryset = (
            Order.objects.filter(user=customer)
            .prefetch_related("items", "payments").select_related("user")
            .order_by("-created_at", "-id")
        )
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(StaffOrderListSerializer(page, many=True).data)

    @action(detail=True, methods=["get"])
    def activity(self, request, pk=None):
        user = self.get_object()
        entries = AuditLog.objects.filter(
            Q(target_type="User", target_id=str(user.pk)) | Q(actor=user)
        ).select_related("actor")[:50]
        return Response({
            "last_login": user.last_login,
            "date_joined": user.date_joined,
            "is_active": user.is_active,
            "orders": Order.objects.filter(user=user).count(),
            "returns": ReturnRequest.objects.filter(user=user).count(),
            "recent_actions": AuditLogSerializer(entries, many=True).data,
        })


class AuditLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [StaffPermission]
    serializer_class = AuditLogSerializer
    permission_map = {"list": "core.view_auditlog", "retrieve": "core.view_auditlog"}
    queryset = AuditLog.objects.select_related("actor")
    filterset_fields = ["action", "actor", "target_type"]
    search_fields = ["action", "target_repr", "actor__email"]
    ordering = ["-created_at", "-id"]

