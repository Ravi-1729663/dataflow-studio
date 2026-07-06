import urllib.error
import urllib.request

import pandas as pd

from apps.common.exceptions import ConnectorError
from apps.etl.exceptions import ExtractError
from apps.etl.extract import extract as etl_extract

from .base import Connector


class RestApiConnector(Connector):
    """Paginates a JSON REST API. See apps.etl.extract._extract_rest_api for the config shape
    (pagination/rate_limit/retries) — this class only adds a cheap, single-request connectivity
    probe on top of that shared, framework-agnostic extraction logic."""

    def test_connection(self) -> None:
        url = self.config.get("url")
        if not url:
            raise ConnectorError("rest_api connector config requires a 'url'")
        try:
            request = urllib.request.Request(
                url, headers=self.config.get("headers", {})
            )
            urllib.request.urlopen(
                request, timeout=10
            ).close()  # noqa: S310 - owner-configured
        except urllib.error.URLError as exc:
            raise ConnectorError(f"could not reach {url}: {exc}") from exc

    def extract(self) -> pd.DataFrame:
        try:
            return etl_extract("rest_api", self.config)
        except ExtractError as exc:
            raise ConnectorError(str(exc)) from exc
