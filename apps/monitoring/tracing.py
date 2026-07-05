"""OpenTelemetry tracing: a tracer provider with a console exporter (no external collector
required — swap in an OTLP exporter via env vars for a real deployment), plus helpers to carry
trace context from the API into a Celery task so a run's trace spans both processes.

Deliberately hand-rolled rather than the django/celery auto-instrumentation packages: propagating
context through a plain dict carried as a task kwarg is a few lines with opentelemetry-api alone,
and avoids pulling in and version-pinning several more contrib packages for this project's scope.
"""

from opentelemetry import propagate, trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

_provider = TracerProvider(
    resource=Resource.create({"service.name": "dataflow-studio"})
)
_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(_provider)

tracer = trace.get_tracer("dataflow")


def inject_context() -> dict:
    """Capture the current trace context so it can be carried across a Celery task boundary."""
    carrier: dict = {}
    propagate.inject(carrier)
    return carrier


def extract_context(carrier: dict | None):
    """Rebuild a trace context from a carrier produced by ``inject_context``. ``None``/empty
    (e.g. a cron-triggered run with no inbound request) yields an empty context, so the resulting
    span simply starts a new trace instead of erroring."""
    return propagate.extract(carrier or {})
