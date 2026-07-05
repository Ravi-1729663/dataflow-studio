import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from rest_framework.test import APIClient

from apps.datasources.models import DataSource
from apps.etl.exceptions import EtlError
from apps.pipelines.models import Pipeline, PipelineRun
from apps.pipelines.services import execute_pipeline
from apps.pipelines.tasks import run_pipeline_task

from .channels import EmailChannel
from .models import NotificationLog, NotificationPreference
from .services import get_or_create_preference

User = get_user_model()

VALID_SLACK_URL = "https://hooks.slack.com/services/T000/B000/xxxxxxxxxxxxxxxxxxxxxxxx"


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="engineer", password="pw12345678", email="engineer@example.com"
    )


@pytest.fixture
def pipeline(user, tmp_path, settings):
    settings.BASE_DIR = tmp_path
    (tmp_path / "customers.csv").write_text("customer_id,email\n1,a@x.com\n")
    source = DataSource.objects.create(
        name="CSV",
        source_type=DataSource.SourceType.FILE,
        config={"path": "customers.csv"},
        owner=user,
    )
    return Pipeline.objects.create(
        name="Ingest",
        source=source,
        owner=user,
        config={"validation": {"rules": []}, "transform": {}, "target": "customers"},
    )


@pytest.mark.django_db
def test_run_success_sends_email_by_default(pipeline, user):
    run = execute_pipeline(pipeline)

    assert len(mail.outbox) == 1
    assert "succeeded" in mail.outbox[0].subject.lower()
    log = NotificationLog.objects.get(run=run, channel=NotificationLog.Channel.EMAIL)
    assert log.event == NotificationLog.Event.RUN_SUCCEEDED
    assert log.success is True


@pytest.mark.django_db
def test_run_failure_sends_an_alert(pipeline, user):
    pipeline.config["validation"] = {
        "rules": [{"type": "required_columns", "columns": ["does_not_exist"]}]
    }
    pipeline.save()

    run = execute_pipeline(pipeline)

    assert len(mail.outbox) == 1
    assert "failed" in mail.outbox[0].subject.lower()
    log = NotificationLog.objects.get(run=run, channel=NotificationLog.Channel.EMAIL)
    assert log.event == NotificationLog.Event.RUN_FAILED
    assert log.success is True


@pytest.mark.django_db
def test_disabling_email_preference_stops_notifications(pipeline, user):
    preference = get_or_create_preference(user)
    preference.email_enabled = False
    preference.save()

    execute_pipeline(pipeline)

    assert len(mail.outbox) == 0
    assert NotificationLog.objects.count() == 0


@pytest.mark.django_db
def test_slack_channel_used_when_enabled_and_configured(pipeline, user, monkeypatch):
    preference = get_or_create_preference(user)
    preference.slack_enabled = True
    preference.slack_webhook_url = VALID_SLACK_URL
    preference.save()

    sent = {}

    def fake_urlopen(request, timeout=5):
        sent["url"] = request.full_url
        sent["body"] = request.data

    monkeypatch.setattr(
        "apps.notifications.channels.urllib.request.urlopen", fake_urlopen
    )

    run = execute_pipeline(pipeline)

    assert sent["url"] == VALID_SLACK_URL
    assert b"succeeded" in sent["body"]
    log = NotificationLog.objects.get(run=run, channel=NotificationLog.Channel.SLACK)
    assert log.success is True


@pytest.mark.django_db
def test_channel_delivery_failure_is_logged_and_does_not_break_the_run(
    pipeline, user, monkeypatch
):
    monkeypatch.setattr(
        "apps.notifications.channels.EmailChannel.send",
        lambda self, subject, body, preference: (_ for _ in ()).throw(
            RuntimeError("smtp down")
        ),
    )

    run = execute_pipeline(pipeline)

    assert (
        run.status == PipelineRun.Status.SUCCEEDED
    )  # notification failure never breaks the run
    log = NotificationLog.objects.get(run=run, channel=NotificationLog.Channel.EMAIL)
    assert log.success is False
    assert "smtp down" in log.error


@pytest.mark.django_db
def test_retrying_run_sends_a_retry_notification(pipeline, user, monkeypatch):
    def always_fails(**kwargs):
        raise EtlError("transient failure")

    monkeypatch.setattr("apps.pipelines.services.engine.run", always_fails)

    run_pipeline_task.apply(kwargs={"pipeline_id": str(pipeline.id)})

    retry_emails = [m for m in mail.outbox if "retrying" in m.subject.lower()]
    assert len(retry_emails) == 3  # MAX_RETRIES
    assert (
        NotificationLog.objects.filter(event=NotificationLog.Event.RUN_RETRYING).count()
        == 3
    )
    assert (
        NotificationLog.objects.filter(event=NotificationLog.Event.RUN_FAILED).count()
        == 1
    )


@pytest.mark.django_db
def test_email_channel_raises_when_owner_has_no_email(pipeline, user):
    user.email = ""
    user.save()
    preference = get_or_create_preference(user)

    with pytest.raises(ValueError):
        EmailChannel().send("subject", "body", preference)


@pytest.mark.django_db
def test_slack_webhook_url_validation_rejects_non_slack_urls(user):
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.patch(
        "/api/notifications/preference/",
        {"slack_enabled": True, "slack_webhook_url": "https://evil.example.com/steal"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_notification_preference_get_and_update(user):
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/notifications/preference/")
    assert response.status_code == 200
    assert response.data["email_enabled"] is True

    response = client.patch(
        "/api/notifications/preference/", {"email_enabled": False}, format="json"
    )
    assert response.status_code == 200
    assert response.data["email_enabled"] is False
    assert NotificationPreference.objects.get(owner=user).email_enabled is False


@pytest.mark.django_db
def test_notification_log_api_scoped_to_owner(pipeline, user):
    other = User.objects.create_user(username="other", password="pw12345678")
    execute_pipeline(pipeline)

    client = APIClient()
    client.force_authenticate(user=other)
    response = client.get("/api/notifications/logs/")

    assert response.status_code == 200
    assert response.data["count"] == 0
