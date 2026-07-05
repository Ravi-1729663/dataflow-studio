import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from .models import DataSource

User = get_user_model()


@pytest.fixture
def auth_client(db):
    user = User.objects.create_user(
        username="engineer", password="pw12345678", role=User.Role.ENGINEER
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
def test_create_and_list_datasource_scoped_to_owner(auth_client):
    client, user = auth_client
    other = User.objects.create_user(username="other", password="pw12345678")
    DataSource.objects.create(
        name="not mine", source_type=DataSource.SourceType.FILE, config={}, owner=other
    )

    response = client.post(
        "/api/datasources/",
        {
            "name": "Customers CSV",
            "source_type": "FILE",
            "config": {"path": "sample_data/customers.csv"},
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["owner"] == user.id

    response = client.get("/api/datasources/")
    assert response.status_code == 200
    assert response.data["count"] == 1


@pytest.mark.django_db
def test_viewer_cannot_create_datasource(auth_client):
    client, _ = auth_client
    viewer = User.objects.create_user(
        username="viewer", password="pw12345678", role=User.Role.VIEWER
    )
    client.force_authenticate(user=viewer)

    response = client.post(
        "/api/datasources/",
        {"name": "x", "source_type": "FILE", "config": {}},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_test_connection_action_reports_missing_file(auth_client):
    client, user = auth_client
    data_source = DataSource.objects.create(
        name="missing",
        source_type=DataSource.SourceType.FILE,
        config={"path": "sample_data/does_not_exist.csv"},
        owner=user,
    )

    response = client.post(f"/api/datasources/{data_source.id}/test-connection/")
    assert response.status_code == 400
    assert response.data["ok"] is False
