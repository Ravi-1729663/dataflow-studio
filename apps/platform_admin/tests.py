import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditLog

from .models import PlatformConfig

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
def test_non_admin_cannot_list_users(engineer):
    client = APIClient()
    client.force_authenticate(user=engineer)

    response = client.get("/api/v1/admin/users/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_can_list_and_update_a_users_role(admin, engineer):
    client = APIClient()
    client.force_authenticate(user=admin)

    response = client.get("/api/v1/admin/users/")
    assert response.status_code == 200
    assert response.data["count"] == 2  # admin + engineer

    response = client.patch(
        f"/api/v1/admin/users/{engineer.id}/", {"role": "ANALYST"}, format="json"
    )
    assert response.status_code == 200
    engineer.refresh_from_db()
    assert engineer.role == "ANALYST"
    assert AuditLog.objects.filter(
        action="user.updated", target=engineer.username
    ).exists()


@pytest.mark.django_db
def test_admin_can_manage_platform_config(admin):
    client = APIClient()
    client.force_authenticate(user=admin)

    response = client.post(
        "/api/v1/admin/config/",
        {"key": "max_upload_mb", "value": "50"},
        format="json",
    )
    assert response.status_code == 201
    assert PlatformConfig.objects.filter(key="max_upload_mb", value="50").exists()


@pytest.mark.django_db
def test_non_admin_cannot_manage_platform_config(engineer):
    client = APIClient()
    client.force_authenticate(user=engineer)

    response = client.get("/api/v1/admin/config/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_system_health_is_admin_only_and_reports_counts(admin, engineer):
    client = APIClient()
    client.force_authenticate(user=engineer)
    assert client.get("/api/v1/admin/health/").status_code == 403

    client.force_authenticate(user=admin)
    response = client.get("/api/v1/admin/health/")
    assert response.status_code == 200
    assert response.data["status"] == "ok"
    assert "counts" in response.data
    assert response.data["counts"]["users"] == 2
