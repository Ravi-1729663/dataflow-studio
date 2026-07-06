import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.datasources.models import DataSource

from .models import Workspace, WorkspaceMembership
from .services import add_member, create_workspace, is_member, is_owner

User = get_user_model()


@pytest.fixture
def owner(db):
    return User.objects.create_user(username="owner", password="pw12345678")


@pytest.fixture
def other(db):
    return User.objects.create_user(username="other", password="pw12345678")


@pytest.mark.django_db
def test_create_workspace_makes_owner_the_first_member(owner):
    workspace = create_workspace(owner, "Acme")

    assert workspace.slug == "acme"
    assert is_member(workspace, owner)
    assert is_owner(workspace, owner)


@pytest.mark.django_db
def test_create_workspace_disambiguates_duplicate_slugs(owner, other):
    first = create_workspace(owner, "Acme")
    second = create_workspace(other, "Acme")

    assert first.slug != second.slug


@pytest.mark.django_db
def test_add_and_remove_member(owner, other):
    workspace = create_workspace(owner, "Acme")

    add_member(workspace, other)
    assert is_member(workspace, other)
    assert not is_owner(workspace, other)

    workspace.memberships.get(user=other).delete()
    assert not is_member(workspace, other)


@pytest.mark.django_db
def test_a_user_in_one_workspace_cannot_see_another_workspaces_datasource(owner, other):
    """The core v0.7 acceptance criterion: workspace A cannot see workspace B's resources."""
    workspace_a = create_workspace(owner, "Workspace A")
    workspace_b = create_workspace(other, "Workspace B")
    DataSource.objects.create(
        name="B's source",
        source_type=DataSource.SourceType.FILE,
        config={"path": "x.csv"},
        owner=other,
        workspace=workspace_b,
    )

    client = APIClient()
    client.force_authenticate(user=owner)
    response = client.get("/api/v1/datasources/")

    assert response.status_code == 200
    assert response.data["count"] == 0
    assert is_member(workspace_a, owner)
    assert not is_member(workspace_b, owner)


@pytest.mark.django_db
def test_workspace_list_api_scoped_to_membership(owner, other):
    mine = create_workspace(owner, "Mine")
    create_workspace(other, "Theirs")

    client = APIClient()
    client.force_authenticate(user=owner)
    response = client.get("/api/v1/workspaces/")

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == str(mine.id)


@pytest.mark.django_db
def test_create_workspace_via_api_records_audit_entry(owner):
    client = APIClient()
    client.force_authenticate(user=owner)

    response = client.post("/api/v1/workspaces/", {"name": "New Co"}, format="json")

    assert response.status_code == 201
    assert AuditLog.objects.filter(action="workspace.created", target="New Co").exists()


@pytest.mark.django_db
def test_only_owner_can_add_members(owner, other):
    workspace = create_workspace(owner, "Acme")
    add_member(workspace, other)
    third = User.objects.create_user(username="third", password="pw12345678")

    client = APIClient()
    client.force_authenticate(user=other)  # a MEMBER, not the OWNER
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/members/",
        {"username": third.username},
        format="json",
    )

    assert response.status_code == 403
    assert not is_member(workspace, third)


@pytest.mark.django_db
def test_owner_can_add_and_remove_a_member_via_api(owner, other):
    workspace = create_workspace(owner, "Acme")

    client = APIClient()
    client.force_authenticate(user=owner)
    response = client.post(
        f"/api/v1/workspaces/{workspace.id}/members/",
        {"username": other.username},
        format="json",
    )
    assert response.status_code == 201
    assert is_member(workspace, other)

    membership = WorkspaceMembership.objects.get(workspace=workspace, user=other)
    response = client.delete(f"/api/v1/workspaces/{workspace.id}/members/{other.id}/")
    assert response.status_code == 204
    assert not is_member(workspace, other)
    assert not WorkspaceMembership.objects.filter(pk=membership.pk).exists()


@pytest.mark.django_db
def test_deleting_a_workspace_preserves_the_audit_trail(owner):
    workspace = create_workspace(owner, "Acme")
    workspace_id = workspace.id

    client = APIClient()
    client.force_authenticate(user=owner)
    response = client.delete(f"/api/v1/workspaces/{workspace_id}/")

    assert response.status_code == 204
    entry = AuditLog.objects.get(action="workspace.deleted", target="Acme")
    assert entry.workspace_id is None  # SET_NULL survives the cascade
    assert not Workspace.objects.filter(pk=workspace_id).exists()
