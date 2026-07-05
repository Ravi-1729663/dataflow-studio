import pytest


@pytest.fixture(autouse=True)
def _fast_pipeline_retries(settings):
    """Pipeline retry backoff would otherwise really sleep between attempts (see
    apps/pipelines/tasks.py) — zero it out so the whole suite stays fast."""
    settings.PIPELINE_RETRY_BACKOFF_BASE_SECONDS = 0
