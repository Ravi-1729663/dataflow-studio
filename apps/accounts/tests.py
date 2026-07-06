import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_register_login_and_me_flow():
    client = APIClient()

    response = client.post(
        "/api/v1/auth/register/",
        {"username": "alice", "email": "alice@example.com", "password": "s3cret-pass"},
    )
    assert response.status_code == 201

    response = client.post(
        "/api/v1/auth/token/", {"username": "alice", "password": "s3cret-pass"}
    )
    assert response.status_code == 200
    access = response.data["access"]

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    response = client.get("/api/v1/auth/me/")
    assert response.status_code == 200
    assert response.data["username"] == "alice"


@pytest.mark.django_db
def test_me_requires_authentication():
    client = APIClient()
    response = client.get("/api/v1/auth/me/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_register_endpoint_returns_429_after_rate_limit_exceeded():
    """v0.7 acceptance: rate limit returns 429. Register/login use the tighter "auth" throttle
    scope (10/min by default) since they're classic brute-force targets."""
    client = APIClient()
    payload = {
        "username": "flood",
        "email": "flood@example.com",
        "password": "s3cret-pass",
    }
    for _ in range(10):
        response = client.post("/api/v1/auth/register/", payload)
        assert response.status_code != 429

    response = client.post("/api/v1/auth/register/", payload)
    assert response.status_code == 429
