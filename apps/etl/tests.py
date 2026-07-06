"""Unit tests for the framework-agnostic etl engine. No Django, no DB."""

import csv
import json
import urllib.error
import urllib.parse
from pathlib import Path

import pandas as pd
import pytest

from apps.etl import engine
from apps.etl.exceptions import ExtractError, TransformError, ValidationFailed
from apps.etl.extract import extract
from apps.etl.incremental import compute_watermark, filter_incremental
from apps.etl.transform import transform
from apps.etl.validate import validate


@pytest.fixture
def customers_csv(tmp_path: Path) -> str:
    path = tmp_path / "customers.csv"
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["customer_id", "first_name", "email"])
        writer.writerow(["1", "Ada", "ada@example.com"])
        writer.writerow(["2", "Grace", "grace@example.com"])
    return str(path)


def test_extract_file_reads_csv(customers_csv):
    df = extract("file", {"path": customers_csv})
    assert len(df) == 2
    assert list(df.columns) == ["customer_id", "first_name", "email"]


def test_extract_file_missing_path_raises():
    with pytest.raises(ExtractError):
        extract("file", {})


def test_extract_unsupported_type_raises():
    with pytest.raises(ExtractError):
        extract("carrier_pigeon", {})


# ---- postgres ---------------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, rows, columns, error=None):
        self._rows = rows
        self.description = [(c,) for c in columns]
        self._error = error

    def execute(self, query, params=None):
        if self._error:
            raise self._error

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def test_extract_postgres_runs_query_and_returns_dataframe(monkeypatch):
    import psycopg2

    cursor = _FakeCursor(rows=[(1, "Ada"), (2, "Grace")], columns=["id", "name"])
    monkeypatch.setattr(psycopg2, "connect", lambda dsn: _FakeConnection(cursor))

    df = extract(
        "postgres", {"dsn": "postgresql://x", "query": "SELECT * FROM customers"}
    )

    assert list(df.columns) == ["id", "name"]
    assert len(df) == 2


def test_extract_postgres_missing_config_raises():
    with pytest.raises(ExtractError):
        extract("postgres", {"dsn": "postgresql://x"})


def test_extract_postgres_query_error_raises_extract_error(monkeypatch):
    import psycopg2

    cursor = _FakeCursor(rows=[], columns=[], error=psycopg2.Error("connection reset"))
    monkeypatch.setattr(psycopg2, "connect", lambda dsn: _FakeConnection(cursor))

    with pytest.raises(ExtractError):
        extract("postgres", {"dsn": "postgresql://x", "query": "SELECT 1"})


# ---- rest_api -----------------------------------------------------------------------------------


class _FakeHttpResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _page_param(request, name="page"):
    query = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
    return int(query[name][0])


def test_extract_rest_api_paginates_until_an_empty_page(monkeypatch):
    pages = {1: [{"id": 1}, {"id": 2}], 2: [{"id": 3}], 3: []}
    seen_pages = []

    def fake_urlopen(request, timeout=10):
        page = _page_param(request)
        seen_pages.append(page)
        return _FakeHttpResponse(json.dumps(pages[page]).encode())

    monkeypatch.setattr("apps.etl.extract.urllib.request.urlopen", fake_urlopen)

    df = extract("rest_api", {"url": "https://api.example.com/items"})

    assert len(df) == 3
    assert seen_pages == [1, 2, 3]


def test_extract_rest_api_stops_at_max_pages(monkeypatch):
    def fake_urlopen(request, timeout=10):
        return _FakeHttpResponse(json.dumps([{"id": 1}]).encode())  # never runs dry

    monkeypatch.setattr("apps.etl.extract.urllib.request.urlopen", fake_urlopen)

    df = extract(
        "rest_api",
        {"url": "https://api.example.com/items", "pagination": {"max_pages": 3}},
    )

    assert len(df) == 3


def test_extract_rest_api_retries_transient_errors_then_succeeds(monkeypatch):
    attempts = {"n": 0}

    def flaky_urlopen(request, timeout=10):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise urllib.error.URLError("temporary")
        return _FakeHttpResponse(json.dumps([]).encode())

    monkeypatch.setattr("apps.etl.extract.urllib.request.urlopen", flaky_urlopen)
    monkeypatch.setattr("apps.etl.extract.time.sleep", lambda seconds: None)

    df = extract(
        "rest_api",
        {"url": "https://api.example.com/items", "retries": {"max_attempts": 3}},
    )

    assert attempts["n"] == 2
    assert df.empty


def test_extract_rest_api_raises_after_exhausting_retries(monkeypatch):
    def always_fails(request, timeout=10):
        raise urllib.error.URLError("down")

    monkeypatch.setattr("apps.etl.extract.urllib.request.urlopen", always_fails)
    monkeypatch.setattr("apps.etl.extract.time.sleep", lambda seconds: None)

    with pytest.raises(ExtractError):
        extract(
            "rest_api",
            {"url": "https://api.example.com/items", "retries": {"max_attempts": 2}},
        )


def test_extract_rest_api_respects_rate_limit(monkeypatch):
    pages = {1: [{"id": 1}], 2: []}
    sleeps = []

    def fake_urlopen(request, timeout=10):
        return _FakeHttpResponse(json.dumps(pages[_page_param(request)]).encode())

    monkeypatch.setattr("apps.etl.extract.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "apps.etl.extract.time.sleep", lambda seconds: sleeps.append(seconds)
    )
    monkeypatch.setattr("apps.etl.extract.time.monotonic", lambda: 0.0)

    extract(
        "rest_api",
        {
            "url": "https://api.example.com/items",
            "rate_limit": {"requests_per_second": 10},
        },
    )

    assert sleeps == [pytest.approx(0.1)]


def test_extract_rest_api_unexpected_results_shape_raises():
    def fake_urlopen(request, timeout=10):
        return _FakeHttpResponse(json.dumps({"not": "a list"}).encode())

    import apps.etl.extract as extract_module

    original = extract_module.urllib.request.urlopen
    extract_module.urllib.request.urlopen = fake_urlopen
    try:
        with pytest.raises(ExtractError):
            extract("rest_api", {"url": "https://api.example.com/items"})
    finally:
        extract_module.urllib.request.urlopen = original


# ---- incremental --------------------------------------------------------------------------------


def test_filter_incremental_keeps_only_rows_after_the_watermark():
    df = pd.DataFrame(
        {"updated_at": ["2024-01-01", "2024-01-05", "2024-01-10"], "v": [1, 2, 3]}
    )
    result = filter_incremental(df, "updated_at", "2024-01-04")
    assert list(result["v"]) == [2, 3]


def test_filter_incremental_no_watermark_returns_everything():
    df = pd.DataFrame({"updated_at": ["2024-01-01"], "v": [1]})
    assert len(filter_incremental(df, "updated_at", None)) == 1


def test_filter_incremental_missing_column_returns_everything():
    df = pd.DataFrame({"v": [1, 2]})
    assert len(filter_incremental(df, "updated_at", "2024-01-01")) == 2


def test_filter_incremental_grace_period_tolerates_late_arrivals():
    df = pd.DataFrame({"updated_at": ["2024-01-04T23:59:00"], "v": [1]})
    watermark = "2024-01-05T00:00:00"

    assert len(filter_incremental(df, "updated_at", watermark)) == 0
    assert len(filter_incremental(df, "updated_at", watermark, grace_seconds=3600)) == 1


def test_filter_incremental_non_date_column_uses_string_comparison():
    df = pd.DataFrame({"seq": ["a1", "a2", "a3"], "v": [1, 2, 3]})
    result = filter_incremental(df, "seq", "a1")
    assert list(result["v"]) == [2, 3]


def test_compute_watermark_returns_the_max_value():
    df = pd.DataFrame({"updated_at": ["2024-01-01", "2024-01-10", "2024-01-05"]})
    assert compute_watermark(df, "updated_at") == "2024-01-10"


def test_compute_watermark_empty_dataframe_returns_none():
    df = pd.DataFrame({"updated_at": []})
    assert compute_watermark(df, "updated_at") is None


def test_engine_run_incremental_only_loads_new_rows_and_advances_watermark(tmp_path):
    path = tmp_path / "customers.csv"
    path.write_text(
        "customer_id,email,updated_at\n"
        "1,ada@example.com,2024-01-01\n"
        "2,grace@example.com,2024-01-02\n"
    )
    loaded = []

    result = engine.run(
        extract_spec={"type": "file", "path": str(path)},
        validation_spec={},
        transform_spec={},
        loader=lambda rows: loaded.append(rows) or {"created": len(rows), "updated": 0},
        incremental_spec={"column": "updated_at", "watermark": "2024-01-01"},
    )

    assert (
        result.rows_extracted == 2
    )  # raw pull from the source, before incremental filtering
    assert (
        result.rows_loaded == 1
    )  # only the row after the watermark actually got loaded
    assert result.new_watermark == "2024-01-02"
    assert len(loaded[0]) == 1
    assert loaded[0][0]["email"] == "grace@example.com"


def test_engine_run_without_incremental_spec_loads_everything(customers_csv):
    result = engine.run(
        extract_spec={"type": "file", "path": customers_csv},
        validation_spec={},
        transform_spec={},
        loader=lambda rows: {"created": len(rows), "updated": 0},
    )
    assert result.rows_extracted == 2
    assert result.new_watermark is None


def test_validate_passes_when_clean_and_scores_100():
    df = pd.DataFrame({"email": ["a@example.com", "b@example.com"]})
    outcome = validate(
        df,
        {
            "rules": [
                {"type": "required_columns", "columns": ["email"]},
                {"type": "not_null", "columns": ["email"]},
                {"type": "unique", "columns": ["email"]},
            ]
        },
    )
    assert outcome.passed
    assert outcome.completeness == 100.0
    assert outcome.consistency == 100.0
    assert outcome.accuracy == 100.0
    assert outcome.overall_score == 100.0


def test_validate_raises_on_missing_required_column():
    df = pd.DataFrame({"email": ["a@example.com"]})
    with pytest.raises(ValidationFailed) as exc_info:
        validate(
            df,
            {
                "rules": [
                    {"type": "required_columns", "columns": ["email", "customer_id"]}
                ]
            },
        )
    assert "customer_id" in exc_info.value.violations[0]
    assert exc_info.value.outcome is not None


def test_validate_raises_on_nulls_and_duplicates_and_carries_outcome():
    df = pd.DataFrame({"email": ["a@example.com", None, "a@example.com"]})
    with pytest.raises(ValidationFailed) as exc_info:
        validate(
            df,
            {
                "rules": [
                    {"type": "not_null", "columns": ["email"]},
                    {"type": "unique", "columns": ["email"]},
                ]
            },
        )
    assert len(exc_info.value.violations) == 2
    outcome = exc_info.value.outcome
    assert outcome.completeness < 100.0
    assert outcome.consistency < 100.0


def test_warning_severity_does_not_block_but_lowers_score():
    df = pd.DataFrame({"email": ["a@example.com", "a@example.com"]})
    outcome = validate(
        df, {"rules": [{"type": "unique", "columns": ["email"], "severity": "warning"}]}
    )
    assert outcome.passed
    assert outcome.warnings
    assert outcome.consistency < 100.0


def test_column_type_range_and_allowed_values_checks():
    df = pd.DataFrame({"age": [25, "oops", 200], "country": ["US", "UK", "XX"]})
    outcome = validate(
        df,
        {
            "rules": [
                {
                    "type": "column_type",
                    "column": "age",
                    "expected_type": "int",
                    "severity": "warning",
                },
                {
                    "type": "range",
                    "column": "age",
                    "min": 0,
                    "max": 120,
                    "severity": "warning",
                },
                {
                    "type": "allowed_values",
                    "column": "country",
                    "values": ["US", "UK"],
                    "severity": "warning",
                },
            ]
        },
    )
    messages = {c.rule_type: c for c in outcome.checks}
    assert messages["column_type"].violation_count == 1
    assert messages["range"].violation_count == 1
    assert messages["allowed_values"].violation_count == 1
    assert outcome.accuracy < 100.0


def test_business_rule_check_blocks_by_default():
    df = pd.DataFrame({"amount": [10, -5, 3]})
    with pytest.raises(ValidationFailed) as exc_info:
        validate(
            df,
            {
                "rules": [
                    {
                        "type": "business_rule",
                        "name": "positive_amount",
                        "expression": "amount > 0",
                    }
                ]
            },
        )
    assert "positive_amount" in exc_info.value.violations[0]


def test_freshness_check_flags_stale_data_as_a_warning_by_default():
    df = pd.DataFrame({"signup_date": ["2000-01-01", "2000-06-01"]})
    outcome = validate(
        df,
        {"rules": [{"type": "freshness", "column": "signup_date", "max_age_days": 30}]},
    )
    assert outcome.passed  # freshness defaults to a warning, not blocking
    assert outcome.warnings
    assert any(c.rule_type == "freshness" and not c.passed for c in outcome.checks)


def test_freshness_check_can_be_made_blocking():
    df = pd.DataFrame({"signup_date": ["2000-01-01"]})
    with pytest.raises(ValidationFailed):
        validate(
            df,
            {
                "rules": [
                    {
                        "type": "freshness",
                        "column": "signup_date",
                        "max_age_days": 30,
                        "severity": "blocking",
                    }
                ]
            },
        )


def test_unknown_rule_type_is_reported_as_a_failed_check():
    df = pd.DataFrame({"a": [1]})
    with pytest.raises(ValidationFailed) as exc_info:
        validate(df, {"rules": [{"type": "does_not_exist"}]})
    assert "unknown rule type" in exc_info.value.violations[0]


def test_transform_renames_casts_and_selects():
    df = pd.DataFrame({"cust_id": [1, 2], "extra": ["x", "y"]})
    result = transform(
        df, {"rename": {"cust_id": "customer_id"}, "select": ["customer_id"]}
    )
    assert list(result.columns) == ["customer_id"]


def test_transform_missing_select_column_raises():
    df = pd.DataFrame({"a": [1]})
    with pytest.raises(TransformError):
        transform(df, {"select": ["b"]})


def test_engine_run_end_to_end(customers_csv):
    loaded = {}

    def loader(rows):
        loaded["rows"] = rows
        return {"created": len(rows), "updated": 0}

    result = engine.run(
        extract_spec={"type": "file", "path": customers_csv},
        validation_spec={
            "rules": [
                {"type": "required_columns", "columns": ["email"]},
                {"type": "not_null", "columns": ["email"]},
                {"type": "unique", "columns": ["email"]},
            ]
        },
        transform_spec={"select": ["customer_id", "email"]},
        loader=loader,
    )

    assert result.rows_extracted == 2
    assert result.rows_loaded == 2
    assert result.load_result == {"created": 2, "updated": 0}
    assert result.validation.overall_score == 100.0
    assert loaded["rows"] == [
        {"customer_id": 1, "email": "ada@example.com"},
        {"customer_id": 2, "email": "grace@example.com"},
    ]


def test_engine_run_raises_on_blocking_validation_failure(customers_csv):
    def loader(rows):
        raise AssertionError("loader must not be called when validation fails")

    with pytest.raises(ValidationFailed) as exc_info:
        engine.run(
            extract_spec={"type": "file", "path": customers_csv},
            validation_spec={
                "rules": [{"type": "required_columns", "columns": ["missing_column"]}]
            },
            transform_spec={},
            loader=loader,
        )
    assert exc_info.value.outcome is not None
