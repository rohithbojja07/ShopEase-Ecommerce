import logging

from django.shortcuts import redirect, render
from django.views import View

from .emails import send_verification_email
from .serializers import RegisterSerializer

logger = logging.getLogger(__name__)


class CreateAccountPageView(View):
    template_name = "accounts/create_account.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        data = {
            "first_name": request.POST.get("first_name", "").strip(),
            "email": request.POST.get("email", "").strip().lower(),
            "phone": request.POST.get("phone", "").strip(),
            "password": request.POST.get("password", ""),
            "password2": request.POST.get("password2", ""),
        }

        serializer = RegisterSerializer(data=data)

        if not serializer.is_valid():
            errors = [
                str(message)
                for messages in serializer.errors.values()
                for message in messages
            ]
            return render(request, self.template_name, {
                "errors": errors,
                "form_data": data,
            })

        user = serializer.save()

        try:
            send_verification_email(user)
        except Exception:
            logger.exception(
                "Could not send verification email to user %s",
                user.pk,
            )

        return render(request, self.template_name, {
            "success": (
                "Your account was created. Check your email "
                "for the verification link."
            )
        })
