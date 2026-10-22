from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """Token that stops working once the email is verified or the email changes."""

    key_salt = "accounts.EmailVerificationTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{user.email}{user.is_email_verified}{timestamp}"


email_verification_token = EmailVerificationTokenGenerator()
