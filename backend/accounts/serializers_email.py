from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from .tokens import email_verification_token

User = get_user_model()


def get_user_from_uid(uid):
    try:
        pk = force_str(urlsafe_base64_decode(uid))
        return User.objects.get(pk=pk, is_active=True)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class UidTokenSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    token_generator = None

    def validate(self, attrs):
        user = get_user_from_uid(attrs["uid"])
        if user is None or not self.token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError("Invalid or expired link.")
        attrs["user"] = user
        return attrs


class PasswordResetConfirmSerializer(UidTokenSerializer):
    token_generator = default_token_generator
    new_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        try:
            validate_password(attrs["new_password"], attrs["user"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})
        return attrs


class VerifyEmailSerializer(UidTokenSerializer):
    token_generator = email_verification_token
