import urllib.error
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.common.exceptions import ConnectorError
from apps.workspaces.services import create_workspace

from . import services
from .connectors.postgres_connector import PostgresConnector
from .connectors.rest_api_connector import RestApiConnector
from .connectors.s3_connector import S3Connector
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


# ---- file upload ----------------------------------------------------------------------------


@pytest.mark.django_db
def test_upload_saves_csv_and_returns_a_usable_path(auth_client, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    client, _, _ = auth_client
    csv_file = SimpleUploadedFile(
        "customers.csv", b"customer_id,email\n1,a@x.com\n", content_type="text/csv"
    )

    response = client.post(
        "/api/v1/datasources/upload/", {"file": csv_file}, format="multipart"
    )

    assert response.status_code == 201
    path = response.data["path"]
    assert path.startswith("media/uploads/")
    assert path.endswith(".csv")
    assert (tmp_path / Path(path).relative_to("media")).exists()


@pytest.mark.django_db
def test_upload_rejects_non_csv_files(auth_client, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    client, _, _ = auth_client
    bad_file = SimpleUploadedFile("data.txt", b"not a csv", content_type="text/plain")

    response = client.post(
        "/api/v1/datasources/upload/", {"file": bad_file}, format="multipart"
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_upload_rejects_oversized_files(auth_client, tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = tmp_path
    monkeypatch.setattr(services, "MAX_UPLOAD_SIZE_BYTES", 10)
    client, _, _ = auth_client
    big_file = SimpleUploadedFile("big.csv", b"x" * 100, content_type="text/csv")

    response = client.post(
        "/api/v1/datasources/upload/", {"file": big_file}, format="multipart"
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_upload_requires_a_file(auth_client):
    client, _, _ = auth_client
    response = client.post("/api/v1/datasources/upload/", {}, format="multipart")
    assert response.status_code == 400


@pytest.mark.django_db
def test_viewer_cannot_upload(auth_client):
    client, _, _ = auth_client
    viewer = User.objects.create_user(
        username="viewer2", password="pw12345678", role=User.Role.VIEWER
    )
    client.force_authenticate(user=viewer)
    csv_file = SimpleUploadedFile(
        "customers.csv", b"a,b\n1,2\n", content_type="text/csv"
    )

    response = client.post(
        "/api/v1/datasources/upload/", {"file": csv_file}, format="multipart"
    )

    assert response.status_code == 403


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


# ---- S3Connector ----------------------------------------------------------------------------


def test_s3_connector_test_connection_requires_bucket_and_key():
    with pytest.raises(ConnectorError):
        S3Connector({}).test_connection()


def test_s3_connector_test_connection_wraps_client_errors(monkeypatch):
    import boto3
    from botocore.exceptions import ClientError

    class _FailingClient:
        def head_object(self, Bucket, Key):
            raise ClientError(
                {"Error": {"Code": "404", "Message": "not found"}}, "HeadObject"
            )

    monkeypatch.setattr(boto3, "client", lambda service, **kwargs: _FailingClient())

    with pytest.raises(ConnectorError):
        S3Connector({"bucket": "b", "key": "missing.csv"}).test_connection()


def test_s3_connector_extract_delegates_to_etl_and_wraps_errors(monkeypatch):
    from apps.etl.exceptions import ExtractError

    monkeypatch.setattr(
        "apps.datasources.connectors.s3_connector.etl_extract",
        lambda source_type, config: (_ for _ in ()).throw(
            ExtractError("no such bucket")
        ),
    )
    with pytest.raises(ConnectorError):
        S3Connector({"bucket": "b", "key": "k.csv"}).extract()


@pytest.mark.django_db
def test_registry_resolves_postgres_rest_api_and_s3_connector_classes():
    from .connectors import get_connector

    assert isinstance(
        get_connector("POSTGRES", {"dsn": "x", "query": "y"}), PostgresConnector
    )
    assert isinstance(get_connector("REST_API", {"url": "x"}), RestApiConnector)
    assert isinstance(get_connector("S3", {"bucket": "b", "key": "k"}), S3Connector)
