import urllib.error

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.common.exceptions import ConnectorError
from apps.workspaces.services import create_workspace

from .connectors.postgres_connector import PostgresConnector
from .connectors.rest_api_connector import RestApiConnector
from .models import DataSource

User = get_user_model()


@pytest.fixture
def auth_client(db):
    user = User.objects.create_user(
        username="engineer", password="pw12345678", role=User.Role.ENGINEER
    )
    workspace = create_workspace(user, "Engineer Workspace")
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user, workspace


@pytest.mark.django_db
def test_create_and_list_datasource_scoped_to_owner(auth_client):
    client, user, workspace = auth_client
    other = User.objects.create_user(username="other", password="pw12345678")
    other_workspace = create_workspace(other, "Other Workspace")
    DataSource.objects.create(
        name="not mine",
        source_type=DataSource.SourceType.FILE,
        config={},
        owner=other,
        workspace=other_workspace,
    )

    response = client.post(
        "/api/v1/datasources/",
        {
            "name": "Customers CSV",
            "source_type": "FILE",
            "config": {"path": "sample_data/customers.csv"},
            "workspace": str(workspace.id),
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["owner"] == user.id

    response = client.get("/api/v1/datasources/")
    assert response.status_code == 200
    assert response.data["count"] == 1


@pytest.mark.django_db
def test_viewer_cannot_create_datasource(auth_client):
    client, _, workspace = auth_client
    viewer = User.objects.create_user(
        username="viewer", password="pw12345678", role=User.Role.VIEWER
    )
    client.force_authenticate(user=viewer)

    response = client.post(
        "/api/v1/datasources/",
        {
            "name": "x",
            "source_type": "FILE",
            "config": {},
            "workspace": str(workspace.id),
        },
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_test_connection_action_reports_missing_file(auth_client):
    client, user, workspace = auth_client
    data_source = DataSource.objects.create(
        name="missing",
        source_type=DataSource.SourceType.FILE,
        config={"path": "sample_data/does_not_exist.csv"},
        owner=user,
        workspace=workspace,
    )

    response = client.post(f"/api/v1/datasources/{data_source.id}/test-connection/")
    assert response.status_code == 400
    assert response.data["ok"] is False


@pytest.mark.django_db
def test_config_is_encrypted_at_rest(auth_client):
    """v0.7 acceptance: credentials are encrypted in the DB. Reads the raw column via a plain
    SQL cursor (bypassing the model's decrypting field) to prove the stored bytes aren't
    plaintext JSON."""
    client, user, workspace = auth_client
    data_source = DataSource.objects.create(
        name="Postgres Source",
        source_type=DataSource.SourceType.POSTGRES,
        config={"dsn": "postgresql://user:hunter2@db.internal/prod"},
        owner=user,
        workspace=workspace,
    )

    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT config FROM datasources_datasource WHERE name = %s",
            [data_source.name],
        )
        (raw_value,) = cursor.fetchone()

    assert "hunter2" not in raw_value
    assert "dsn" not in raw_value

    data_source.refresh_from_db()
    assert data_source.config == {"dsn": "postgresql://user:hunter2@db.internal/prod"}


# ---- PostgresConnector --------------------------------------------------------------------------


def test_postgres_connector_test_connection_requires_dsn():
    with pytest.raises(ConnectorError):
        PostgresConnector({}).test_connection()


def test_postgres_connector_test_connection_wraps_connection_errors(monkeypatch):
    import psycopg2

    def fail_connect(dsn):
        raise psycopg2.Error("no route to host")

    monkeypatch.setattr(psycopg2, "connect", fail_connect)

    with pytest.raises(ConnectorError):
        PostgresConnector({"dsn": "postgresql://bad"}).test_connection()


def test_postgres_connector_extract_delegates_to_etl_and_wraps_errors(monkeypatch):
    from apps.etl.exceptions import ExtractError

    monkeypatch.setattr(
        "apps.datasources.connectors.postgres_connector.etl_extract",
        lambda source_type, config: (_ for _ in ()).throw(ExtractError("bad query")),
    )
    with pytest.raises(ConnectorError):
        PostgresConnector({"dsn": "postgresql://x", "query": "SELECT 1"}).extract()


# ---- RestApiConnector ----------------------------------------------------------------------------


def test_rest_api_connector_test_connection_requires_url():
    with pytest.raises(ConnectorError):
        RestApiConnector({}).test_connection()


def test_rest_api_connector_test_connection_wraps_unreachable_url(monkeypatch):
    monkeypatch.setattr(
        "apps.datasources.connectors.rest_api_connector.urllib.request.urlopen",
        lambda request, timeout=10: (_ for _ in ()).throw(
            urllib.error.URLError("down")
        ),
    )
    with pytest.raises(ConnectorError):
        RestApiConnector({"url": "https://api.example.com"}).test_connection()


def test_rest_api_connector_extract_delegates_to_etl_and_wraps_errors(monkeypatch):
    from apps.etl.exceptions import ExtractError

    monkeypatch.setattr(
        "apps.datasources.connectors.rest_api_connector.etl_extract",
        lambda source_type, config: (_ for _ in ()).throw(ExtractError("timed out")),
    )
    with pytest.raises(ConnectorError):
        RestApiConnector({"url": "https://api.example.com"}).extract()


@pytest.mark.django_db
def test_registry_resolves_postgres_and_rest_api_connector_classes():
    from .connectors import get_connector

    assert isinstance(
        get_connector("POSTGRES", {"dsn": "x", "query": "y"}), PostgresConnector
    )
    assert isinstance(get_connector("REST_API", {"url": "x"}), RestApiConnector)
