"""Orchestrates extract -> clean -> validate -> transform -> load and reports metrics + step
logs.

Framework-agnostic: every argument is a plain dict/dataclass or callable. No Django imports.
"""

import time
from dataclasses import dataclass, field
from typing import Callable

from . import clean as clean_step
from . import extract as extract_step
from . import incremental as incremental_step
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
    clean_stats: dict = field(default_factory=dict)
    duration_seconds: float = 0.0
    # Raw/transformed DataFrames, exposed so a caller (pipelines app) can snapshot medallion
    # (bronze/silver) layers. repr=False keeps them out of log lines.
    raw_df: object = field(default=None, repr=False)
    transformed_df: object = field(default=None, repr=False)
    # The watermark to persist for the next incremental run, or None if incremental wasn't
    # configured (or the batch was empty, in which case the caller should keep the old one).
    new_watermark: str | None = None


def run(
    extract_spec: dict,
    validation_spec: dict,
    transform_spec: dict,
    loader: Callable[[list[dict]], dict],
    incremental_spec: dict | None = None,
) -> EngineResult:
    """Run one pipeline pass. Raises an ``EtlError`` subclass on any step failure — a
    ``ValidationFailed`` still carries its ``ValidationOutcome`` so the caller can persist a
    quality scorecard even for a blocked run.

    ``incremental_spec``, if given as ``{"column": ..., "watermark": ..., "grace_seconds": ...}``,
    filters the extracted batch down to new/changed rows before validation even sees it — so a
    run's bronze layer and quality scorecard reflect only what's new this time.
    """
    started = time.monotonic()
    step_logs: list[str] = []

    raw_df = extract_step.extract(extract_spec.get("type"), extract_spec)
    rows_extracted = len(raw_df)
    step_logs.append(
        f"extracted {rows_extracted} row(s) from {extract_spec.get('type')}"
    )

    new_watermark = None
    if incremental_spec and incremental_spec.get("column"):
        column = incremental_spec["column"]
        watermark = incremental_spec.get("watermark")
        before = len(raw_df)
        raw_df = incremental_step.filter_incremental(
            raw_df, column, watermark, incremental_spec.get("grace_seconds", 0)
        )
        new_watermark = incremental_step.compute_watermark(raw_df, column) or watermark
        step_logs.append(
            f"incremental filter on {column!r}: {len(raw_df)}/{before} new/changed row(s) "
            f"(watermark {watermark!r} -> {new_watermark!r})"
        )

    clean_spec = transform_spec.get("clean")
    clean_stats: dict = {}
    if clean_spec:
        rows_before_clean = len(raw_df)
        raw_df, clean_stats = clean_step.clean(raw_df, clean_spec)
        step_logs.append(
            f"cleaned: {clean_stats}, {len(raw_df)}/{rows_before_clean} row(s) kept"
        )

    outcome = validate_step.validate(raw_df, validation_spec)
    step_logs.append(f"validation passed: overall_score={outcome.overall_score}")

    transformed_df = transform_step.transform(raw_df, transform_spec)
    step_logs.append(
        f"transformed to {len(transformed_df)} row(s), {len(transformed_df.columns)} column(s)"
    )

    load_result = load_step.load(transformed_df, loader)
    step_logs.append(f"loaded: {load_result}")

    return EngineResult(
        rows_extracted=rows_extracted,
        rows_loaded=len(transformed_df),
        step_logs=step_logs,
        load_result=load_result,
        validation=outcome,
        clean_stats=clean_stats,
        duration_seconds=time.monotonic() - started,
        raw_df=raw_df,
        transformed_df=transformed_df,
        new_watermark=new_watermark,
    )


__all__ = ["run", "EngineResult", "EtlError"]
