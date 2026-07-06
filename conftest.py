import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _fast_pipeline_retries(settings):
    """Pipeline retry backoff would otherwise really sleep between attempts (see
    apps/pipelines/tasks.py) — zero it out so the whole suite stays fast."""
    settings.PIPELINE_RETRY_BACKOFF_BASE_SECONDS = 0


@pytest.fixture(autouse=True)
def _reset_throttle_cache():
    """DRF's rate-limit throttles (v0.7) count hits in Django's cache, which persists across the
    whole test session (unlike the DB, it isn't wrapped in a per-test rollback) — without this,
    unrelated tests reusing the same low user PKs would accumulate hits and start seeing
    unexpected 429s."""
    cache.clear()
    yield
    cache.clear()
