import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.workspaces.services import create_workspace

from .models import AuditLog
from .services import record

User = get_user_model()


@pytest.fixture
def admin(db):
    return User.objects.create_user(
        username="admin", password="pw12345678", role=User.Role.ADMIN
    )


@pytest.fixture
def engineer(db):
    return User.objects.create_user(
        username="engineer", password="pw12345678", role=User.Role.ENGINEER
    )


@pytest.mark.django_db
def test_record_creates_an_entry(engineer):
    workspace = create_workspace(engineer, "Acme")

    entry = record(
        engineer, "datasource.created", workspace=workspace, target="Sales CSV"
    )

    assert entry.actor == engineer
    assert entry.workspace == workspace
    assert entry.action == "datasource.created"
    assert entry.target == "Sales CSV"


@pytest.mark.django_db
def test_record_with_unauthenticated_actor_stores_null_actor():
    from django.contrib.auth.models import AnonymousUser

    entry = record(AnonymousUser(), "user.logged_in", target="nobody")

    assert entry.actor is None


@pytest.mark.django_db
def test_audit_log_api_is_admin_only(engineer):
    client = APIClient()
    client.force_authenticate(user=engineer)

    response = client.get("/api/v1/audit/logs/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_audit_log_api_lists_entries_for_admin(admin, engineer):
    workspace = create_workspace(engineer, "Acme")
    record(engineer, "datasource.created", workspace=workspace, target="Sales CSV")

    client = APIClient()
    client.force_authenticate(user=admin)
    response = client.get("/api/v1/audit/logs/")

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["action"] == "datasource.created"


@pytest.mark.django_db
def test_registering_a_user_is_audited():
    client = APIClient()
    response = client.post(
        "/api/v1/auth/register/",
        {"username": "newbie", "email": "newbie@example.com", "password": "pw12345678"},
        format="json",
    )

    assert response.status_code == 201
    assert AuditLog.objects.filter(action="user.registered", target="newbie").exists()


@pytest.mark.django_db
def test_logging_in_is_audited():
    User.objects.create_user(username="alice", password="s3cret-pass")
    client = APIClient()

    response = client.post(
        "/api/v1/auth/token/", {"username": "alice", "password": "s3cret-pass"}
    )

    assert response.status_code == 200
    assert AuditLog.objects.filter(action="user.logged_in", target="alice").exists()
