from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from cart.models import Cart
from cart.pricing import calculate_cart, to_json
from core.validation import reject_server_values

from .models import Order, ShippingMethod
from .serializers import OrderDetailSerializer, OrderListSerializer, StatusHistorySerializer
from .services import (
    OrderError,
    address_snapshot,
    cancel_order,
    place_order,
    quote,
    resolve_addresses,
    shipping_options,
)


class CheckoutSerializer(serializers.Serializer):
    shipping_address_id = serializers.IntegerField(min_value=1)
    billing_address_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    shipping_method = serializers.ChoiceField(
        choices=ShippingMethod.choices, default=ShippingMethod.STANDARD
    )


class ShippingOptionsView(APIView):
    """Step 3 of checkout: what each shipping method costs for the current cart."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        data = calculate_cart(cart)
        if not data["items"]:
            raise ValidationError({"detail": "Your cart is empty."})
        options = shipping_options(data["subtotal"])
        for option in options:
            option["total"] = data["taxable_amount"] + data["tax"] + option["fee"]
        return Response(to_json({"options": options}))


class CheckoutSummaryView(APIView):
    """Order summary preview. Changes nothing: no stock is reserved."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        reject_server_values(request.data)
        data = CheckoutSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            shipping, billing = resolve_addresses(
                request.user,
                data.validated_data["shipping_address_id"],
                data.validated_data.get("billing_address_id"),
            )
            cart, _ = Cart.objects.get_or_create(user=request.user)
            quoted = quote(cart, data.validated_data["shipping_method"])
        except OrderError as exc:
            raise ValidationError({"detail": str(exc)})
        if not quoted["items"]:
            raise ValidationError({"detail": "Your cart is empty."})
        return Response(to_json({
            "cart": quoted,
            "shipping_address": address_snapshot(shipping),
            "billing_address": address_snapshot(billing),
        }))


class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status"]
    search_fields = ["order_number"]
    ordering_fields = ["created_at", "total"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        # customers only ever see their own orders
        return (
            Order.objects.filter(user=self.request.user)
            .select_related("shipment")
            .prefetch_related("items", "payments", "history")
        )

    def get_serializer_class(self):
        return OrderListSerializer if self.action == "list" else OrderDetailSerializer

    def _detail(self, order):
        order = self.get_queryset().get(pk=order.pk)
        return OrderDetailSerializer(order, context=self.get_serializer_context()).data

    def create(self, request):
        reject_server_values(request.data)
        data = CheckoutSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            order = place_order(
                request.user,
                data.validated_data["shipping_address_id"],
                data.validated_data.get("billing_address_id"),
                data.validated_data["shipping_method"],
            )
        except OrderError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(self._detail(order), status=201)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        try:
            cancel_order(order, by=request.user, note="Cancelled by customer.")
        except OrderError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(self._detail(order))

    @action(detail=True, methods=["get"])
    def tracking(self, request, pk=None):
        order = self.get_object()
        detail = OrderDetailSerializer(order, context=self.get_serializer_context()).data
        return Response({
            "order_number": order.order_number,
            "status": order.status,
            "shipment": detail["shipment"],
            "timeline": StatusHistorySerializer(order.history.all(), many=True).data,
        })
