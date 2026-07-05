"""Validation step: a small pluggable rule library over a DataFrame, plus the scoring math behind
a per-run quality scorecard. Framework-agnostic — apps/validation persists these results, but the
checks and scoring have zero Django dependency so they stay fast to unit test (per CLAUDE.md: pure
ETL/validation logic gets fast tests with no DB).

``spec`` shape:
    {
        "rules": [
            {"type": "required_columns", "columns": ["email"], "severity": "blocking"},
            {"type": "not_null", "columns": ["email"]},
            {"type": "unique", "columns": ["email"]},
            {"type": "no_duplicate_rows", "severity": "warning"},
            {"type": "column_type", "column": "customer_id", "expected_type": "int"},
            {"type": "range", "column": "age", "min": 0, "max": 120},
            {"type": "allowed_values", "column": "country", "values": ["US", "UK"]},
            {"type": "freshness", "column": "signup_date", "max_age_days": 365},
            {"type": "business_rule", "name": "positive_amount", "expression": "amount > 0"},
        ]
    }
``severity`` defaults to "blocking" when omitted. A blocking violation raises ``ValidationFailed``
(carrying the full outcome); a warning is recorded but does not stop the run.

Business-rule ``expression`` strings run through ``DataFrame.eval`` — this only resolves against
the frame's own columns (no access to Python builtins/globals), and pipeline config is only
writable by the pipeline's owner over an authenticated endpoint, so the trust boundary is the
same as any other owner-authored pipeline config.
"""

from dataclasses import dataclass, field

import pandas as pd

from .exceptions import ValidationFailed

BLOCKING = "blocking"
WARNING = "warning"


@dataclass
class CheckResult:
    rule_type: str
    passed: bool
    severity: str
    message: str
    violation_count: int = 0
    checked_count: int = 0


@dataclass
class ValidationOutcome:
    checks: list[CheckResult] = field(default_factory=list)
    completeness: float = 100.0
    consistency: float = 100.0
    accuracy: float = 100.0
    overall_score: float = 100.0

    @property
    def blocking_violations(self) -> list[str]:
        return [
            c.message for c in self.checks if not c.passed and c.severity == BLOCKING
        ]

    @property
    def warnings(self) -> list[str]:
        return [
            c.message for c in self.checks if not c.passed and c.severity == WARNING
        ]

    @property
    def passed(self) -> bool:
        return not self.blocking_violations


def _check_required_columns(df: pd.DataFrame, rule: dict) -> CheckResult:
    columns = rule.get("columns", [])
    missing = [c for c in columns if c not in df.columns]
    return CheckResult(
        rule_type="required_columns",
        passed=not missing,
        severity=rule.get("severity", BLOCKING),
        message=(
            f"missing required columns: {missing}"
            if missing
            else "all required columns present"
        ),
        violation_count=len(missing),
        checked_count=len(columns) or 1,
    )


def _check_not_null(df: pd.DataFrame, rule: dict) -> CheckResult:
    columns = [c for c in rule.get("columns", []) if c in df.columns]
    violation_count = int(sum(df[c].isna().sum() for c in columns)) if columns else 0
    checked_count = len(df) * len(columns)
    return CheckResult(
        rule_type="not_null",
        passed=violation_count == 0,
        severity=rule.get("severity", BLOCKING),
        message=(
            f"{violation_count} null value(s) in {columns}"
            if violation_count
            else f"no nulls in {columns}"
        ),
        violation_count=violation_count,
        checked_count=checked_count or 1,
    )


def _check_unique(df: pd.DataFrame, rule: dict) -> CheckResult:
    columns = [c for c in rule.get("columns", []) if c in df.columns]
    violation_count = (
        int(sum(df[c].duplicated().sum() for c in columns)) if columns else 0
    )
    return CheckResult(
        rule_type="unique",
        passed=violation_count == 0,
        severity=rule.get("severity", BLOCKING),
        message=(
            f"{violation_count} duplicate value(s) in {columns}"
            if violation_count
            else f"no duplicates in {columns}"
        ),
        violation_count=violation_count,
        checked_count=(len(df) * len(columns)) or 1,
    )


def _check_no_duplicate_rows(df: pd.DataFrame, rule: dict) -> CheckResult:
    violation_count = int(df.duplicated().sum())
    return CheckResult(
        rule_type="no_duplicate_rows",
        passed=violation_count == 0,
        severity=rule.get("severity", BLOCKING),
        message=(
            f"{violation_count} fully duplicate row(s)"
            if violation_count
            else "no duplicate rows"
        ),
        violation_count=violation_count,
        checked_count=len(df) or 1,
    )


def _check_column_type(df: pd.DataFrame, rule: dict) -> CheckResult:
    column = rule.get("column")
    expected_type = rule.get("expected_type")
    severity = rule.get("severity", BLOCKING)
    if column not in df.columns:
        return CheckResult(
            "column_type", False, severity, f"column {column!r} missing", 1, 1
        )

    if expected_type in ("int", "float"):
        coerced = pd.to_numeric(df[column], errors="coerce")
        violation_count = int(coerced.isna().sum() - df[column].isna().sum())
    else:
        violation_count = 0

    return CheckResult(
        rule_type="column_type",
        passed=violation_count == 0,
        severity=severity,
        message=(
            f"{violation_count} value(s) in {column!r} are not {expected_type}"
            if violation_count
            else f"{column!r} matches {expected_type}"
        ),
        violation_count=violation_count,
        checked_count=len(df) or 1,
    )


def _check_range(df: pd.DataFrame, rule: dict) -> CheckResult:
    column = rule.get("column")
    severity = rule.get("severity", BLOCKING)
    if column not in df.columns:
        return CheckResult("range", False, severity, f"column {column!r} missing", 1, 1)

    values = pd.to_numeric(df[column], errors="coerce")
    minimum, maximum = rule.get("min"), rule.get("max")
    out_of_range = pd.Series(False, index=df.index)
    if minimum is not None:
        out_of_range |= values < minimum
    if maximum is not None:
        out_of_range |= values > maximum
    violation_count = int(out_of_range.sum())

    return CheckResult(
        rule_type="range",
        passed=violation_count == 0,
        severity=severity,
        message=(
            f"{violation_count} value(s) in {column!r} outside [{minimum}, {maximum}]"
            if violation_count
            else f"{column!r} within range"
        ),
        violation_count=violation_count,
        checked_count=len(df) or 1,
    )


def _check_allowed_values(df: pd.DataFrame, rule: dict) -> CheckResult:
    column = rule.get("column")
    severity = rule.get("severity", BLOCKING)
    if column not in df.columns:
        return CheckResult(
            "allowed_values", False, severity, f"column {column!r} missing", 1, 1
        )

    allowed = set(rule.get("values", []))
    violation_count = int((~df[column].isin(allowed)).sum())

    return CheckResult(
        rule_type="allowed_values",
        passed=violation_count == 0,
        severity=severity,
        message=(
            f"{violation_count} value(s) in {column!r} not in {sorted(allowed)}"
            if violation_count
            else f"{column!r} values all allowed"
        ),
        violation_count=violation_count,
        checked_count=len(df) or 1,
    )


def _check_freshness(df: pd.DataFrame, rule: dict) -> CheckResult:
    column = rule.get("column")
    max_age_days = rule.get("max_age_days")
    severity = rule.get("severity", WARNING)
    if column not in df.columns:
        return CheckResult(
            "freshness", False, severity, f"column {column!r} missing", 1, 1
        )

    dates = pd.to_datetime(df[column], errors="coerce")
    if dates.isna().all():
        return CheckResult(
            "freshness",
            False,
            severity,
            f"no parseable dates in {column!r}",
            len(df),
            len(df) or 1,
        )

    newest = dates.max()
    age_days = (pd.Timestamp.now(tz=newest.tz) - newest).days
    stale = max_age_days is not None and age_days > max_age_days

    return CheckResult(
        rule_type="freshness",
        passed=not stale,
        severity=severity,
        message=(
            f"newest {column!r} is {age_days} day(s) old (max {max_age_days})"
            if stale
            else f"{column!r} is fresh"
        ),
        violation_count=1 if stale else 0,
        checked_count=1,
    )


def _check_business_rule(df: pd.DataFrame, rule: dict) -> CheckResult:
    name = rule.get("name", "business_rule")
    expression = rule["expression"]
    severity = rule.get("severity", BLOCKING)
    try:
        mask = df.eval(expression)
    except (
        Exception
    ) as exc:  # noqa: BLE001 - any eval failure is reported as a check failure
        return CheckResult(
            name,
            False,
            severity,
            f"could not evaluate {expression!r}: {exc}",
            len(df),
            len(df) or 1,
        )

    violation_count = int((~mask.fillna(False)).sum())
    return CheckResult(
        rule_type=name,
        passed=violation_count == 0,
        severity=severity,
        message=(
            f"{violation_count} row(s) violate {name!r} ({expression})"
            if violation_count
            else f"all rows satisfy {name!r}"
        ),
        violation_count=violation_count,
        checked_count=len(df) or 1,
    )


_CHECKS = {
    "required_columns": _check_required_columns,
    "not_null": _check_not_null,
    "unique": _check_unique,
    "no_duplicate_rows": _check_no_duplicate_rows,
    "column_type": _check_column_type,
    "range": _check_range,
    "allowed_values": _check_allowed_values,
    "freshness": _check_freshness,
    "business_rule": _check_business_rule,
}

_STRUCTURAL_RULE_TYPES = {"required_columns", "not_null", "unique", "no_duplicate_rows"}


def _score(violation_count: int, checked_count: int) -> float:
    if checked_count <= 0:
        return 100.0
    return max(0.0, 100.0 * (1 - violation_count / checked_count))


def validate(df: pd.DataFrame, spec: dict) -> ValidationOutcome:
    """Run every configured rule, compute a quality scorecard, and raise on blocking violations.

    completeness/consistency are computed from the raw data unconditionally (so a scorecard is
    meaningful even with an empty rule set); accuracy is derived from whichever domain-specific
    rules (type/range/allowed_values/business_rule) were actually configured.
    """
    checks: list[CheckResult] = []
    for rule in spec.get("rules", []):
        rule_type = rule.get("type")
        check_fn = _CHECKS.get(rule_type)
        if check_fn is None:
            checks.append(
                CheckResult(
                    rule_type or "unknown",
                    False,
                    rule.get("severity", BLOCKING),
                    f"unknown rule type: {rule_type!r}",
                )
            )
            continue
        checks.append(check_fn(df, rule))

    completeness = _score(int(df.isna().sum().sum()), df.size)
    consistency = _score(int(df.duplicated().sum()), len(df))

    accuracy_checks = [c for c in checks if c.rule_type not in _STRUCTURAL_RULE_TYPES]
    if accuracy_checks:
        accuracy = sum(
            _score(c.violation_count, c.checked_count) for c in accuracy_checks
        ) / len(accuracy_checks)
    else:
        accuracy = 100.0

    overall_score = (completeness + consistency + accuracy) / 3

    outcome = ValidationOutcome(
        checks=checks,
        completeness=round(completeness, 2),
        consistency=round(consistency, 2),
        accuracy=round(accuracy, 2),
        overall_score=round(overall_score, 2),
    )

    if outcome.blocking_violations:
        raise ValidationFailed(
            f"validation failed: {'; '.join(outcome.blocking_violations)}",
            outcome.blocking_violations,
            outcome=outcome,
        )

    return outcome
