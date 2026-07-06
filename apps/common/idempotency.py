"""Idempotency-Key support for POST endpoints with side effects (v0.7): a client that retries a
request (e.g. after a network timeout) after a request already succeeded gets the original
response replayed instead of triggering the action a second time."""

import functools
import logging

from rest_framework.response import Response

from .models import IdempotencyKey

logger = logging.getLogger("dataflow.common")


def idempotent(action_name: str):
    """Decorator for a DRF viewset action. Opt-in: does nothing unless the caller sends an
    ``Idempotency-Key`` header. Only successful (2xx) responses are cached — a client should be
    able to retry after a failure without being stuck replaying it."""

    def decorator(view_method):
        @functools.wraps(view_method)
        def wrapper(self, request, *args, **kwargs):
            key = request.headers.get("Idempotency-Key")
            if not key:
                return view_method(self, request, *args, **kwargs)

            endpoint = f"{action_name}:{kwargs.get('pk', '')}"
            existing = IdempotencyKey.objects.filter(
                key=key, user=request.user, endpoint=endpoint
            ).first()
            if existing:
                logger.info(
                    "idempotent replay",
                    extra={"endpoint": endpoint, "idempotency_key": key},
                )
                return Response(existing.response_body, status=existing.response_status)

            response = view_method(self, request, *args, **kwargs)
            if 200 <= response.status_code < 300:
                IdempotencyKey.objects.create(
                    key=key,
                    user=request.user,
                    endpoint=endpoint,
                    response_status=response.status_code,
                    response_body=response.data,
                )
            return response

        return wrapper

    return decorator
