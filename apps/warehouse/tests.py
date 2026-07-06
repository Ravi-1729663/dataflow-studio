import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from .models import Customer
from .services import get_dataframe, upsert_customers, upsert_customers_scd2

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
    response = client.get("/api/v1/warehouse/customers/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_customers_endpoint_returns_data_with_jwt():
    user = User.objects.create_user(username="viewer", password="pw12345678")
    Customer.objects.create(external_id="1", first_name="Ada", email="ada@example.com")

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get("/api/v1/warehouse/customers/")
    assert response.status_code == 200
    assert response.data["count"] == 1


@pytest.mark.django_db
def test_viewer_sees_masked_email():
    viewer = User.objects.create_user(
        username="viewer", password="pw12345678", role=User.Role.VIEWER
    )
    Customer.objects.create(external_id="1", first_name="Ada", email="ada@example.com")

    client = APIClient()
    client.force_authenticate(user=viewer)
    response = client.get("/api/v1/warehouse/customers/")

    assert response.status_code == 200
    assert response.data["results"][0]["email"] == "a***@example.com"


@pytest.mark.django_db
def test_engineer_sees_unmasked_email():
    engineer = User.objects.create_user(
        username="engineer", password="pw12345678", role=User.Role.ENGINEER
    )
    Customer.objects.create(external_id="1", first_name="Ada", email="ada@example.com")

    client = APIClient()
    client.force_authenticate(user=engineer)
    response = client.get("/api/v1/warehouse/customers/")

    assert response.status_code == 200
    assert response.data["results"][0]["email"] == "ada@example.com"


# ---- SCD Type 2 -----------------------------------------------------------------------------


@pytest.mark.django_db
def test_scd2_first_load_creates_one_current_row():
    rows = [
        {
            "customer_id": "1",
            "first_name": "Ada",
            "email": "ada@example.com",
            "country": "UK",
        }
    ]

    result = upsert_customers_scd2(rows)

    assert result == {"created": 1, "updated": 0}
    customer = Customer.objects.get(external_id="1")
    assert customer.is_current is True
    assert customer.valid_to is None


@pytest.mark.django_db
def test_scd2_unchanged_reload_is_a_no_op():
    rows = [
        {
            "customer_id": "1",
            "first_name": "Ada",
            "email": "ada@example.com",
            "country": "UK",
        }
    ]
    upsert_customers_scd2(rows)

    result = upsert_customers_scd2(rows)

    assert result == {"created": 0, "updated": 0}
    assert Customer.objects.filter(external_id="1").count() == 1


@pytest.mark.django_db
def test_scd2_changed_attribute_closes_old_row_and_creates_a_new_current_one():
    upsert_customers_scd2(
        [
            {
                "customer_id": "1",
                "first_name": "Ada",
                "email": "ada@example.com",
                "country": "UK",
            }
        ]
    )
    original = Customer.objects.get(external_id="1", is_current=True)

    result = upsert_customers_scd2(
        [
            {
                "customer_id": "1",
                "first_name": "Ada",
                "email": "ada@example.com",
                "country": "US",
            }
        ]
    )

    assert result == {"created": 0, "updated": 1}
    versions = Customer.objects.filter(external_id="1").order_by("valid_from")
    assert versions.count() == 2

    old, new = versions
    assert old.id == original.id
    assert old.is_current is False
    assert old.valid_to is not None
    assert old.country == "UK"
    assert new.is_current is True
    assert new.valid_to is None
    assert new.country == "US"


@pytest.mark.django_db
def test_scd2_only_one_current_row_per_external_id_is_enforced():
    upsert_customers_scd2(
        [
            {
                "customer_id": "1",
                "first_name": "Ada",
                "email": "ada@example.com",
                "country": "UK",
            }
        ]
    )
    with pytest.raises(Exception):  # IntegrityError, backend-specific
        Customer.objects.create(
            external_id="1", first_name="Ada", email="ada2@example.com", is_current=True
        )


@pytest.mark.django_db
def test_get_dataframe_only_includes_current_rows():
    upsert_customers_scd2(
        [
            {
                "customer_id": "1",
                "first_name": "Ada",
                "email": "ada@example.com",
                "country": "UK",
            }
        ]
    )
    upsert_customers_scd2(
        [
            {
                "customer_id": "1",
                "first_name": "Ada",
                "email": "ada@example.com",
                "country": "US",
            }
        ]
    )

    df = get_dataframe()

    assert len(df) == 1
    assert df.iloc[0]["country"] == "US"
