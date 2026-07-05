"""Orchestrates extract -> validate -> transform -> load and reports metrics + step logs.

Framework-agnostic: every argument is a plain dict/dataclass or callable. No Django imports.
"""

import time
from dataclasses import dataclass, field
from typing import Callable

from . import extract as extract_step
from . import load as load_step
from . import transform as transform_step
from . import validate as validate_step
from .exceptions import EtlError


@dataclass
class EngineResult:
    rows_extracted: int
    rows_loaded: int
    step_logs: list[str] = field(default_factory=list)
    load_result: dict = field(default_factory=dict)
    validation: object = (
        None  # validate_step.ValidationOutcome, left untyped to avoid import noise
    )
    duration_seconds: float = 0.0


def run(
    extract_spec: dict,
    validation_spec: dict,
    transform_spec: dict,
    loader: Callable[[list[dict]], dict],
) -> EngineResult:
    """Run one pipeline pass. Raises an ``EtlError`` subclass on any step failure — a
    ``ValidationFailed`` still carries its ``ValidationOutcome`` so the caller can persist a
    quality scorecard even for a blocked run."""
    started = time.monotonic()
    step_logs: list[str] = []

    df = extract_step.extract(extract_spec.get("type"), extract_spec)
    rows_extracted = len(df)
    step_logs.append(
        f"extracted {rows_extracted} row(s) from {extract_spec.get('type')}"
    )

    outcome = validate_step.validate(df, validation_spec)
    step_logs.append(f"validation passed: overall_score={outcome.overall_score}")

    df = transform_step.transform(df, transform_spec)
    step_logs.append(f"transformed to {len(df)} row(s), {len(df.columns)} column(s)")

    load_result = load_step.load(df, loader)
    step_logs.append(f"loaded: {load_result}")

    return EngineResult(
        rows_extracted=rows_extracted,
        rows_loaded=len(df),
        step_logs=step_logs,
        load_result=load_result,
        validation=outcome,
        duration_seconds=time.monotonic() - started,
    )


__all__ = ["run", "EngineResult", "EtlError"]
