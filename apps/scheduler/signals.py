from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.pipelines.models import Pipeline

from .services import sync_schedule


@receiver(post_save, sender=Pipeline)
def sync_pipeline_schedule(sender, instance: Pipeline, **kwargs):
    """Keep the beat entry in lockstep with every Pipeline save: create, edit schedule/is_active,
    clone, pause, resume — whatever the call site (API, admin, seed_demo), this always fires.
    """
    sync_schedule(instance)
