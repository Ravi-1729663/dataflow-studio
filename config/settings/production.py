"""Production settings: Postgres + async Celery, DEBUG forced off."""

from .base import *  # noqa: F401,F403

DEBUG = False

# WhiteNoise serves static files (admin/Swagger UI) straight from gunicorn once `collectstatic`
# has actually run (baked into the Docker image at build time — see Dockerfile). Kept out of
# base.py: local dev/tests never run collectstatic and don't need it, since `runserver` already
# serves static files itself, and WhiteNoise warns loudly at startup when STATIC_ROOT is missing.
MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE[2:],  # noqa: F405
]
