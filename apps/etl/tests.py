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


def test_validate_passes_when_clean():
    df = pd.DataFrame({"email": ["a@example.com", "b@example.com"]})
    validate(
        df, {"required_columns": ["email"], "not_null": ["email"], "unique": ["email"]}
    )


def test_validate_raises_on_missing_column():
    df = pd.DataFrame({"email": ["a@example.com"]})
    with pytest.raises(ValidationFailed):
        validate(df, {"required_columns": ["email", "customer_id"]})


def test_validate_raises_on_nulls_and_duplicates():
    df = pd.DataFrame({"email": ["a@example.com", None, "a@example.com"]})
    with pytest.raises(ValidationFailed) as exc_info:
        validate(df, {"not_null": ["email"], "unique": ["email"]})
    assert len(exc_info.value.violations) == 2


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
            "required_columns": ["email"],
            "not_null": ["email"],
            "unique": ["email"],
        },
        transform_spec={"select": ["customer_id", "email"]},
        loader=loader,
    )

    assert result.rows_extracted == 2
    assert result.rows_loaded == 2
    assert result.load_result == {"created": 2, "updated": 0}
    assert loaded["rows"] == [
        {"customer_id": 1, "email": "ada@example.com"},
        {"customer_id": 2, "email": "grace@example.com"},
    ]


def test_engine_run_raises_on_blocking_validation_failure(customers_csv):
    def loader(rows):
        raise AssertionError("loader must not be called when validation fails")

    with pytest.raises(ValidationFailed):
        engine.run(
            extract_spec={"type": "file", "path": customers_csv},
            validation_spec={"required_columns": ["missing_column"]},
            transform_spec={},
            loader=loader,
        )
