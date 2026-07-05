"""Exceptions raised by the etl engine. Pure Python — no framework dependency."""


class EtlError(Exception):
    """Base class for all etl engine errors."""


class ExtractError(EtlError):
    """Raised when a source cannot be extracted."""


class ValidationFailed(EtlError):
    """Raised when a blocking validation check fails; stops the run before load."""

    def __init__(self, message: str, violations: list[str]):
        super().__init__(message)
        self.violations = violations


class TransformError(EtlError):
    """Raised when a transform step cannot be applied."""


class LoadError(EtlError):
    """Raised when the caller-supplied loader fails."""
