"""Exceptions raised by the etl engine. Pure Python — no framework dependency."""


class EtlError(Exception):
    """Base class for all etl engine errors."""


class ExtractError(EtlError):
    """Raised when a source cannot be extracted."""


class ValidationFailed(EtlError):
    """Raised when a blocking validation check fails; stops the run before load.

    Carries the full ``ValidationOutcome`` (from ``apps.etl.validate``) so callers can still
    persist a quality scorecard for a run that failed validation, not just for successful ones.
    Left untyped here to avoid a circular import with ``validate.py``.
    """

    def __init__(self, message: str, violations: list[str], outcome=None):
        super().__init__(message)
        self.violations = violations
        self.outcome = outcome


class TransformError(EtlError):
    """Raised when a transform step cannot be applied."""


class LoadError(EtlError):
    """Raised when the caller-supplied loader fails."""
