"""Extraction step: turns a plain source spec into a pandas DataFrame. No Django imports.

Postgres/REST extraction live here (not just in apps.datasources.connectors) so the engine stays
usable and testable with zero Django ever loaded — apps.datasources.connectors delegates to these
same functions for its "test connection"/CRUD-facing classes rather than re-implementing them.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from .exceptions import ExtractError


def extract(source_type: str, config: dict) -> pd.DataFrame:
    """Extract raw data for a source spec.

    ``source_type`` is a plain string (e.g. "file"); ``config`` is a plain dict, never an ORM
    object, so this function stays usable outside of Django entirely.
    """
    if source_type == "file":
        return _extract_file(config)
    if source_type == "postgres":
        return _extract_postgres(config)
    if source_type == "rest_api":
        return _extract_rest_api(config)
    raise ExtractError(f"Unsupported source_type: {source_type!r}")


def _extract_file(config: dict) -> pd.DataFrame:
    path = config.get("path")
    if not path:
        raise ExtractError("file source config requires a 'path'")
    try:
        return pd.read_csv(path)
    except FileNotFoundError as exc:
        raise ExtractError(f"file not found: {path}") from exc
    except pd.errors.EmptyDataError as exc:
        raise ExtractError(f"file is empty: {path}") from exc
    except pd.errors.ParserError as exc:
        raise ExtractError(f"could not parse file: {path}") from exc


def _extract_postgres(config: dict) -> pd.DataFrame:
    dsn = config.get("dsn")
    query = config.get("query")
    if not dsn or not query:
        raise ExtractError("postgres source config requires 'dsn' and 'query'")

    try:
        import psycopg2
    except (
        ImportError
    ) as exc:  # pragma: no cover - psycopg2-binary is a project dependency
        raise ExtractError("psycopg2 is required for postgres sources") from exc

    try:
        with psycopg2.connect(dsn) as conn, conn.cursor() as cursor:
            cursor.execute(query, config.get("params"))
            columns = [d[0] for d in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
    except psycopg2.Error as exc:
        raise ExtractError(f"postgres query failed: {exc}") from exc

    return pd.DataFrame(rows, columns=columns)


def _extract_rest_api(config: dict) -> pd.DataFrame:
    """Paginates a JSON REST API, respecting a rate limit and retrying transient failures.

    ``config`` shape::

        {
            "url": "https://api.example.com/items",
            "headers": {...},
            "params": {...},
            "results_path": "data",           # key holding the list of records in each response
            "pagination": {
                "page_param": "page", "start_page": 1,
                "size_param": "page_size", "page_size": 100,
                "max_pages": 100,
            },
            "rate_limit": {"requests_per_second": 5},
            "retries": {"max_attempts": 3, "backoff_base_seconds": 1},
        }
    """
    url = config.get("url")
    if not url:
        raise ExtractError("rest_api source config requires a 'url'")

    pagination = config.get("pagination", {})
    page_param = pagination.get("page_param", "page")
    size_param = pagination.get("size_param")
    page_size = pagination.get("page_size")
    max_pages = pagination.get("max_pages", 100)
    results_path = config.get("results_path")
    requests_per_second = config.get("rate_limit", {}).get("requests_per_second")
    min_interval = 1.0 / requests_per_second if requests_per_second else 0

    records: list[dict] = []
    page = pagination.get("start_page", 1)
    for _ in range(max_pages):
        params = dict(config.get("params", {}))
        params[page_param] = page
        if size_param and page_size:
            params[size_param] = page_size

        started = time.monotonic()
        payload = _fetch_json(
            url, params, config.get("headers", {}), config.get("retries", {})
        )
        page_records = payload[results_path] if results_path else payload
        if not isinstance(page_records, list):
            raise ExtractError(
                f"expected a list of records at results_path={results_path!r}, "
                f"got {type(page_records).__name__}"
            )
        if not page_records:
            break
        records.extend(page_records)
        page += 1

        if min_interval:
            elapsed = time.monotonic() - started
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)

    return pd.DataFrame(records)


def _fetch_json(url: str, params: dict, headers: dict, retry_config: dict):
    max_attempts = retry_config.get("max_attempts", 3)
    backoff_base = retry_config.get("backoff_base_seconds", 1)

    query = urllib.parse.urlencode(params)
    full_url = f"{url}?{query}" if query else url

    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            request = urllib.request.Request(full_url, headers=headers)
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt < max_attempts:
                time.sleep(backoff_base * (2 ** (attempt - 1)))

    raise ExtractError(
        f"failed to fetch {full_url} after {max_attempts} attempt(s): {last_exc}"
    )
