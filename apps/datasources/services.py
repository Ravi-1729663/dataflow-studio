"""Business logic for datasources. Bridges DataSource models to the connectors package."""

import uuid
from pathlib import Path

from django.core.files.storage import default_storage

from .connectors import get_connector
from .models import DataSource

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_UPLOAD_EXTENSIONS = {".csv"}


def test_connection(data_source: DataSource) -> None:
    """Raises ``apps.common.exceptions.ConnectorError`` if the source is unreachable."""
    connector = get_connector(data_source.source_type, data_source.config)
    connector.test_connection()


def save_uploaded_file(uploaded_file) -> str:
    """Saves an uploaded CSV under ``MEDIA_ROOT`` and returns a path usable directly as a FILE
    data source's ``config.path`` — relative to ``BASE_DIR`` (``MEDIA_ROOT`` is ``BASE_DIR /
    "media"``), which ``apps.pipelines.services._build_extract_spec`` already resolves, so
    nothing else needs to change to support it.

    Local disk, not object storage — a convenience for local/single-instance use, not a
    durability guarantee. On a platform with an ephemeral filesystem (e.g. Render's free tier),
    an upload does not survive a restart/redeploy; point the S3 connector at a real bucket
    instead if uploads need to actually persist.
    """
    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError(f"unsupported file type {extension!r} — only .csv is accepted")
    if uploaded_file.size > MAX_UPLOAD_SIZE_BYTES:
        raise ValueError(
            f"file too large — max {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB"
        )

    filename = f"uploads/{uuid.uuid4().hex}{extension}"
    saved_path = default_storage.save(filename, uploaded_file)
    return f"media/{saved_path}"
