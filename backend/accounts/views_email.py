import logging

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .emails import (
    revoke_all_tokens,
    send_password_reset_email,
    send_verification_email,
)
from .serializers_email import (
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    VerifyEmailSerializer,
)
from .views import RegisterView as BaseRegisterView

logger = logging.getLogger(__name__)
User = get_user_model()


class RegisterView(BaseRegisterView):
    """Register, then send the verification email."""

    def perform_create(self, serializer):
        user = serializer.save()
        try:
            send_verification_email(user)
        except Exception:  # a mail problem must not block registration
            logger.exception("Could not send verification email to user %s", user.pk)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_sensitive"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(
            email__iexact=serializer.validated_data["email"], is_active=True
        ).first()
        if user:
            try:
                send_password_reset_email(user)
            except Exception:
                logger.exception("Could not send reset email to user %s", user.pk)
        # same answer whether or not the email exists (no account enumeration)
        return Response(
            {"detail": "If an account with that email exists, a reset link has been sent."}
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_sensitive"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        revoke_all_tokens(user)  # log the user out everywhere
        return Response({"detail": "Password has been reset."})


class SendVerificationEmailView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_sensitive"

    def post(self, request):
        if request.user.is_email_verified:
            return Response(
                {"detail": "Email is already verified."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        send_verification_email(request.user)
        return Response({"detail": "Verification email sent."})


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_sensitive"

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])
        return Response({"detail": "Email verified."})
