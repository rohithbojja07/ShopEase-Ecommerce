from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.validation import reject_server_values

from .models import ReturnRequest
from .returns import ReturnError, ReturnNotFound, add_evidence, cancel_return, request_return
from .serializers_returns import (
    CreateReturnSerializer,
    EvidenceUploadSerializer,
    ReturnSerializer,
)


class ReturnViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ReturnSerializer
    filterset_fields = ["status"]
    ordering_fields = ["created_at"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        # customers only ever see their own returns
        return (
            ReturnRequest.objects.filter(user=self.request.user)
            .select_related("order", "refund")
            .prefetch_related("items__order_item", "evidence", "events")
        )

    def _detail(self, ret):
        fresh = self.get_queryset().get(pk=ret.pk)
        return ReturnSerializer(fresh, context=self.get_serializer_context()).data

    def create(self, request):
        reject_server_values(request.data)
        data = CreateReturnSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            ret = request_return(
                request.user,
                data.validated_data["order_id"],
                data.validated_data["reason"],
                data.validated_data.get("description", ""),
                data.validated_data.get("items"),
            )
        except ReturnNotFound as exc:
            raise NotFound(str(exc))
        except ReturnError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(self._detail(ret), status=201)

    @action(detail=True, methods=["post"])
    def evidence(self, request, pk=None):
        ret = self.get_object()
        data = EvidenceUploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            add_evidence(ret, data.validated_data["images"])
        except ReturnError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(self._detail(ret), status=201)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        ret = self.get_object()
        try:
            cancel_return(ret, by=request.user)
        except ReturnError as exc:
            raise ValidationError({"detail": str(exc)})
        return Response(self._detail(ret))
