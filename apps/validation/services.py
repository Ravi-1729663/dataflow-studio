"""Persists the etl engine's ValidationOutcome as a per-run quality scorecard.

The scoring math lives in apps.etl.validate (framework-agnostic); this module only bridges that
outcome into the ORM — the same "bridge a Django model to the engine" role pipelines.services
plays for execution, extended here to validation results.
"""

import logging

from apps.etl.validate import ValidationOutcome
from apps.pipelines.models import PipelineRun

from .models import QualityScorecard

logger = logging.getLogger("dataflow.validation")


def persist_scorecard(run: PipelineRun, outcome: ValidationOutcome) -> QualityScorecard:
    checks = [
        {
            "rule_type": c.rule_type,
            "passed": c.passed,
            "severity": c.severity,
            "message": c.message,
            "violation_count": c.violation_count,
            "checked_count": c.checked_count,
        }
        for c in outcome.checks
    ]
    scorecard, _ = QualityScorecard.objects.update_or_create(
        run=run,
        defaults={
            "completeness": outcome.completeness,
            "consistency": outcome.consistency,
            "accuracy": outcome.accuracy,
            "overall_score": outcome.overall_score,
            "passed": outcome.passed,
            "checks": checks,
        },
    )
    logger.info(
        "quality scorecard persisted",
        extra={
            "run_id": run.id,
            "overall_score": scorecard.overall_score,
            "passed": scorecard.passed,
        },
    )
    return scorecard
