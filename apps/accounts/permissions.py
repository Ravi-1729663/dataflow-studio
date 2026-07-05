"""RBAC permission classes built on the User.role field."""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import User


class IsAdmin(BasePermission):
    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.ADMIN
        )


class IsEngineerOrAdmin(BasePermission):
    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (User.Role.ENGINEER, User.Role.ADMIN)
        )


class IsEngineerOrAdminOrReadOnly(BasePermission):
    """Any authenticated user can read; only engineers/admins can write."""

    def has_permission(self, request, view) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role in (User.Role.ENGINEER, User.Role.ADMIN)
