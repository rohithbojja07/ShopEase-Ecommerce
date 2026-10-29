import logging

from django.contrib import messages
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import user_passes_test
from django.views.decorators.csrf import csrf_protect

User = get_user_model()
logger = logging.getLogger(__name__)


@csrf_protect
@require_http_methods(["GET", "POST"])
def forgot_password_page(request):
    if request.method == "GET":
        return render(request, "accounts/forgot_password.html")

    email = request.POST.get("email", "").strip().lower()
    password = request.POST.get("password", "")
    password2 = request.POST.get("password2", "")

    if not email or not password or not password2:
        return render(request, "accounts/forgot_password.html", {
            "error": "Please fill in all fields.",
            "email": email,
        })

    if password != password2:
        return render(request, "accounts/forgot_password.html", {
            "error": "Passwords do not match.",
            "email": email,
        })

    user = User.objects.filter(email__iexact=email, is_active=True).first()

    if user is None:
        return render(request, "accounts/forgot_password.html", {
            "error": "No active account was found for that email.",
            "email": email,
        })

    try:
        password_validation.validate_password(password, user)
    except ValidationError as exc:
        return render(request, "accounts/forgot_password.html", {
            "errors": exc.messages,
            "email": email,
        })

    user.set_password(password)
    user.save(update_fields=["password"])

    try:
        from accounts.tokens import revoke_all_tokens
        revoke_all_tokens(user)
    except (ImportError, AttributeError):
        logger.info("Token revocation helper unavailable for user %s", user.pk)

    return render(request, "accounts/forgot_password.html", {
        "success": "Password changed successfully. You can now sign in."
    })
