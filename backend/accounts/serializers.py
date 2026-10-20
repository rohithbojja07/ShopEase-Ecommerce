from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from .models import Address, UserProfile

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "password", "password2")
        read_only_fields = ("id",)

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password2": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password2")
        return User.objects.create_user(**validated_data)


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ("phone", "date_of_birth", "avatar")


class MeSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer()

    class Meta:
        model = User
        fields = (
            "id", "email", "first_name", "last_name",
            "is_email_verified", "date_joined", "profile",
        )
        read_only_fields = ("id", "email", "is_email_verified", "date_joined")

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", {})
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if profile_data:
            profile, _ = UserProfile.objects.get_or_create(user=instance)
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            profile.save()
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = (
            "id", "address_type", "full_name", "phone", "line1", "line2",
            "city", "state", "postal_code", "country", "is_default", "created_at",
        )
        read_only_fields = ("id", "created_at")

    def _clear_other_defaults(self, user, address_type, exclude_id=None):
        qs = Address.objects.filter(user=user, address_type=address_type, is_default=True)
        if exclude_id:
            qs = qs.exclude(pk=exclude_id)
        qs.update(is_default=False)

    @transaction.atomic
    def create(self, validated_data):
        user = self.context["request"].user
        if validated_data.get("is_default"):
            self._clear_other_defaults(user, validated_data["address_type"])
        return Address.objects.create(user=user, **validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        address_type = validated_data.get("address_type", instance.address_type)
        if validated_data.get("is_default"):
            self._clear_other_defaults(instance.user, address_type, instance.pk)
        return super().update(instance, validated_data)
