from rest_framework import serializers

from apps.accounts.models import User

from .models import Customer


def _mask_email(email: str) -> str:
    """user@example.com -> u***@example.com"""
    local, _, domain = email.partition("@")
    if not local:
        return email
    return f"{local[0]}***@{domain}" if domain else f"{local[0]}***"


class CustomerSerializer(serializers.ModelSerializer):
    email = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = (
            "id",
            "external_id",
            "first_name",
            "last_name",
            "email",
            "signup_date",
            "country",
            "valid_from",
            "valid_to",
            "is_current",
            "created_at",
            "updated_at",
        )
        read_only_fields = tuple(f for f in fields if f != "email")

    def get_email(self, obj) -> str:
        """PII masking (v0.7): only engineers/admins — the roles that build and operate the
        pipelines touching raw customer data — see the real address. Analysts/viewers querying
        the served gold layer see a masked version."""
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "role", None) in (
            User.Role.ADMIN,
            User.Role.ENGINEER,
        ):
            return obj.email
        return _mask_email(obj.email)
