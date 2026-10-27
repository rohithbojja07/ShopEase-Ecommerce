from django.contrib.auth import views as auth_views

from .emails import revoke_all_tokens


class AdminPasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    """Django's "choose a new password" page, plus: old API logins stop working."""

    def form_valid(self, form):
        response = super().form_valid(form)
        revoke_all_tokens(form.user)
        return response
