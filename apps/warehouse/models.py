from django.db import models

from apps.common.models import BaseModel


class Customer(BaseModel):
    """The demo gold-layer table: one row per customer ingested from a pipeline."""

    external_id = models.CharField(max_length=64, unique=True)
    first_name = models.CharField(max_length=200)
    last_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(unique=True)
    signup_date = models.DateField(null=True, blank=True)
    country = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} <{self.email}>"
