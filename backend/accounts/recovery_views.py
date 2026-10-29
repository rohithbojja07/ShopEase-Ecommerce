import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views import View
from django.views.decorators.debug import sensitive_post_parameters
from django.utils.decorators import method_decorator

from accounts.emails import revoke_all_tokens, send_password_reset_email

logger = logging.getLogger(__name__)
User = get_user_model()


class ForgotPasswordPageView(View):
    template_name = "accounts/forgot_password.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        email = request.POST.get("email", "").strip()

        if not email:
            return render(request, self.template_name, {
                "error": "Enter your registered email address."
            })

        user = User.objects.filter(
            email__iexact=email,
            is_active=True,
        ).first()

        if user:
            try:
                send_password_reset_email(user)
            except Exception:
                logger.exception(
                    "Password reset email could not be sent for account %s",
                    user.pk,
                )

        return render(request, self.template_name, {
            "success": (
                "If an active account exists for that email, "
                "a password reset link has been sent."
            )
        })


@method_decorator(sensitive_post_parameters(), name="dispatch")
class StaffPasswordResetConfirmPageView(View):
    template_name = "accounts/reset_password_confirm.html"

    def get_user(self, uidb64):
        try:
            user_id = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=user_id, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return None

        return user

    def get(self, request, uidb64, token):
        user = self.get_user(uidb64)

        if user is None or not default_token_generator.check_token(user, token):
            return render(request, self.template_name, {
                "error": "This password reset link is invalid or has expired."
            })

        return render(request, self.template_name, {
            "uidb64": uidb64,
            "token": token,
        })

    def post(self, request, uidb64, token):
        user = self.get_user(uidb64)

        if user is None or not default_token_generator.check_token(user, token):
            return render(request, self.template_name, {
                "error": "This password reset link is invalid or has expired."
            })

        password = request.POST.get("new_password", "")
        confirm = request.POST.get("confirm_password", "")

        context = {"uidb64": uidb64, "token": token}

        if not password or not confirm:
            context["error"] = "Fill in both password fields."
            return render(request, self.template_name, context)

        if password != confirm:
            context["error"] = "The passwords do not match."
            return render(request, self.template_name, context)

        try:
            validate_password(password, user)
        except ValidationError as exc:
            context["error"] = " ".join(exc.messages)
            return render(request, self.template_name, context)

        user.set_password(password)
        user.save(update_fields=["password"])
        revoke_all_tokens(user)

        return render(request, self.template_name, {
            "success": "Password reset successfully. You can now sign in.",
        })
