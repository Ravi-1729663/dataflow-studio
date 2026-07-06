from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel


class Customer(BaseModel):
    """The demo gold-layer table: one row per customer version ingested from a pipeline.

    Supports both load strategies (see pipelines.loaders): a plain Type-1 upsert (``target:
    "customers"``) always has exactly one row per ``external_id``, permanently ``is_current``.
    SCD Type 2 (``target: "customers_scd2"``) keeps every version — a changed row closes out the
    old one (``valid_to``/``is_current=False``) and inserts a new current one — so ``external_id``
    is intentionally *not* globally unique; only one row per ``external_id`` may be current at a
    time (enforced by the partial unique constraint below).
    """

    external_id = models.CharField(max_length=64)
    first_name = models.CharField(max_length=200)
    last_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField()
    signup_date = models.DateField(null=True, blank=True)
    country = models.CharField(max_length=100, blank=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_to = models.DateTimeField(null=True, blank=True)
    is_current = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["external_id"],
                condition=models.Q(is_current=True),
                name="unique_current_customer_per_external_id",
            )
        ]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} <{self.email}>"
