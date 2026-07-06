"""Workspace creation and membership management — the only place that touches
WorkspaceMembership directly, so "who can see what" stays enforced in one place."""

from django.contrib.auth import get_user_model
from django.utils.text import slugify

from .models import Workspace, WorkspaceMembership

User = get_user_model()


def create_workspace(owner: User, name: str) -> Workspace:
    """Creates a workspace and makes ``owner`` its first (OWNER-role) member."""
    base_slug = slugify(name) or "workspace"
    slug = base_slug
    suffix = 1
    while Workspace.objects.filter(slug=slug).exists():
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    workspace = Workspace.objects.create(name=name, slug=slug)
    WorkspaceMembership.objects.create(
        workspace=workspace, user=owner, role=WorkspaceMembership.Role.OWNER
    )
    return workspace


def is_member(workspace: Workspace, user: User) -> bool:
    return WorkspaceMembership.objects.filter(workspace=workspace, user=user).exists()


def is_owner(workspace: Workspace, user: User) -> bool:
    return WorkspaceMembership.objects.filter(
        workspace=workspace, user=user, role=WorkspaceMembership.Role.OWNER
    ).exists()


def add_member(
    workspace: Workspace, user: User, role: str = WorkspaceMembership.Role.MEMBER
) -> WorkspaceMembership:
    membership, _ = WorkspaceMembership.objects.update_or_create(
        workspace=workspace, user=user, defaults={"role": role}
    )
    return membership


def remove_member(workspace: Workspace, user: User) -> None:
    WorkspaceMembership.objects.filter(workspace=workspace, user=user).delete()
