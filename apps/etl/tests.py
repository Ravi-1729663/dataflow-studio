"""Unit tests for the framework-agnostic etl engine. No Django, no DB."""

import csv
from pathlib import Path

import pandas as pd
import pytest

from apps.etl import engine
from apps.etl.exceptions import ExtractError, TransformError, ValidationFailed
from apps.etl.extract import extract
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
        extract("rest_api", {})


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
