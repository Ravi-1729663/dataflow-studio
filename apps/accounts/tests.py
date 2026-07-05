import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_register_login_and_me_flow():
    client = APIClient()

    response = client.post(
        "/api/auth/register/",
        {"username": "alice", "email": "alice@example.com", "password": "s3cret-pass"},
    )
    assert response.status_code == 201

    response = client.post(
        "/api/auth/token/", {"username": "alice", "password": "s3cret-pass"}
    )
    assert response.status_code == 200
    access = response.data["access"]

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    response = client.get("/api/auth/me/")
    assert response.status_code == 200
    assert response.data["username"] == "alice"


@pytest.mark.django_db
def test_me_requires_authentication():
    client = APIClient()
    response = client.get("/api/auth/me/")
    assert response.status_code == 401
