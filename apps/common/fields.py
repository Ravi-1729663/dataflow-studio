"""Custom model fields shared across apps. EncryptedJSONField is what makes
DataSource.config Fernet-encrypted at rest (CLAUDE.md's "credentials are encrypted with Fernet").
"""

import json
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

logger = logging.getLogger("dataflow.common")


def _fernet() -> Fernet:
    key = settings.FERNET_KEY
    return Fernet(key.encode() if isinstance(key, str) else key)


class EncryptedJSONField(models.TextField):
    """Stores a JSON-serializable value Fernet-encrypted at rest, transparent to callers — reads
    back a plain dict/list, exactly like JSONField. The underlying column is opaque ciphertext
    (a TextField, not a JSON column), since the DB should never see the plaintext."""

    def get_prep_value(self, value):
        if value is None:
            return value
        plaintext = json.dumps(value).encode()
        return _fernet().encrypt(plaintext).decode()

    def from_db_value(self, value, expression, connection):
        if not value:
            return {}
        try:
            plaintext = _fernet().decrypt(value.encode())
        except InvalidToken:
            logger.warning(
                "EncryptedJSONField decryption failed — returning {} instead of raising. "
                "Likely a stale row written before this column was encrypted, or FERNET_KEY "
                "changed since it was written.",
                extra={"column_preview": value[:16]},
            )
            return {}
        return json.loads(plaintext)

    def to_python(self, value):
        if value is None or isinstance(value, (dict, list)):
            return value
        try:
            plaintext = _fernet().decrypt(value.encode())
            return json.loads(plaintext)
        except InvalidToken:
            return value
