from apps.common.exceptions import ConnectorError
from apps.etl.exceptions import ExtractError
from apps.etl.extract import extract as etl_extract

from .base import Connector


class S3Connector(Connector):
    """Reads a CSV object from an S3-compatible bucket. Config: {"bucket": ..., "key": ...,
    "endpoint_url": (optional — set this to target MinIO or another S3-compatible store instead
    of real AWS), "aws_access_key_id": ..., "aws_secret_access_key": ..., "region_name":
    (optional)}.
    """

    def _client(self):
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - boto3 is a project dependency
            raise ConnectorError("boto3 is required for s3 sources") from exc

        client_kwargs = {
            k: self.config[k]
            for k in (
                "endpoint_url",
                "aws_access_key_id",
                "aws_secret_access_key",
                "region_name",
            )
            if self.config.get(k)
        }
        return boto3.client("s3", **client_kwargs)

    def test_connection(self) -> None:
        bucket = self.config.get("bucket")
        key = self.config.get("key")
        if not bucket or not key:
            raise ConnectorError("s3 connector config requires 'bucket' and 'key'")

        from botocore.exceptions import BotoCoreError, ClientError

        try:
            self._client().head_object(Bucket=bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise ConnectorError(f"could not reach s3://{bucket}/{key}: {exc}") from exc

    def extract(self):
        """Delegates to apps.etl.extract, which owns the actual (framework-agnostic) read
        logic — this class only adds the connectivity probe above."""
        try:
            return etl_extract("s3", self.config)
        except ExtractError as exc:
            raise ConnectorError(str(exc)) from exc
