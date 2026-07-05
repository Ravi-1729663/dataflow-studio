"""Validation step: minimal structural checks. The full rule library lands in apps/validation (v0.3).

``spec`` shape:
    {
        "required_columns": ["email", "customer_id"],
        "not_null": ["email"],
        "unique": ["email"],
    }
Any violation is blocking for v0.1 — there is no warning tier yet.
"""

import pandas as pd

from .exceptions import ValidationFailed


def validate(df: pd.DataFrame, spec: dict) -> None:
    violations: list[str] = []

    required_columns = spec.get("required_columns", [])
    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        violations.append(f"missing required columns: {missing}")

    not_null = [c for c in spec.get("not_null", []) if c in df.columns]
    for column in not_null:
        null_count = int(df[column].isna().sum())
        if null_count:
            violations.append(f"column {column!r} has {null_count} null value(s)")

    unique = [c for c in spec.get("unique", []) if c in df.columns]
    for column in unique:
        dup_count = int(df[column].duplicated().sum())
        if dup_count:
            violations.append(f"column {column!r} has {dup_count} duplicate value(s)")

    if violations:
        raise ValidationFailed(
            f"validation failed: {'; '.join(violations)}", violations
        )
