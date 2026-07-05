import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from .models import Customer
from .services import upsert_customers

User = get_user_model()


@pytest.mark.django_db
def test_upsert_customers_is_idempotent():
    rows = [{"customer_id": "1", "first_name": "Ada", "email": "ada@example.com"}]

    result = upsert_customers(rows)
    assert result == {"created": 1, "updated": 0}

    result = upsert_customers(rows)
    assert result == {"created": 0, "updated": 1}
    assert Customer.objects.count() == 1


@pytest.mark.django_db
def test_customers_endpoint_requires_jwt():
    client = APIClient()
    response = client.get("/api/warehouse/customers/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_customers_endpoint_returns_data_with_jwt():
    user = User.objects.create_user(username="viewer", password="pw12345678")
    Customer.objects.create(external_id="1", first_name="Ada", email="ada@example.com")

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get("/api/warehouse/customers/")
    assert response.status_code == 200
    assert response.data["count"] == 1
