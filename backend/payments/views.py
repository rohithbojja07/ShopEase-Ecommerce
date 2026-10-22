from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.validation import reject_server_values

from .models import PaymentStatus
from .serializers import CreatePaymentSerializer, PaymentSerializer, VerifyPaymentSerializer
from .services import PaymentError, PaymentNotFound, SANDBOX_TOKENS, create_payment, verify_payment


class PaymentCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        reject_server_values(request.data)
        data = CreatePaymentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            payment, created = create_payment(
                request.user, data.validated_data["order_id"], data.validated_data["method"]
            )
        except PaymentNotFound as exc:
            raise NotFound(str(exc))
        except PaymentError as exc:
            raise ValidationError({"detail": str(exc)})
        body = dict(PaymentSerializer(payment).data)
        body["sandbox_tokens"] = list(SANDBOX_TOKENS)
        return Response(body, status=201 if created else 200)


class PaymentVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        reject_server_values(request.data)
        data = VerifyPaymentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            payment = verify_payment(
                request.user,
                data.validated_data["payment_id"],
                data.validated_data["transaction_reference"],
                data.validated_data["token"],
            )
        except PaymentNotFound as exc:
            raise NotFound(str(exc))
        except PaymentError as exc:
            raise ValidationError({"detail": str(exc)})
        order = payment.order
        body = {
            "payment": PaymentSerializer(payment).data,
            "order_number": order.order_number,
            "order_status": order.status,
        }
        ok = payment.status in (PaymentStatus.SUCCESS, PaymentStatus.REFUNDED)
        return Response(body, status=200 if ok else 402)
