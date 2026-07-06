"""Load helpers for the warehouse gold layer. These are the `loader` callables the etl engine
calls — see pipelines.loaders for how a pipeline's ``target`` picks one."""

import logging
from itertools import islice

import pandas as pd
from django.db import transaction
from django.utils import timezone

from .models import Customer

logger = logging.getLogger("dataflow.warehouse")

_GOLD_COLUMNS = [
    "external_id",
    "first_name",
    "last_name",
    "email",
    "signup_date",
    "country",
    "valid_from",
    "valid_to",
    "is_current",
]
# Batch tuning: chunk large row sets into one transaction each, instead of either a single
# giant transaction (holds locks for the whole run) or a bare transaction per row (commit
# overhead dominates at scale).
DEFAULT_BATCH_SIZE = 500


def _chunked(rows: list[dict], size: int):
    it = iter(rows)
    while chunk := list(islice(it, size)):
        yield chunk


def upsert_customers(rows: list[dict], batch_size: int = DEFAULT_BATCH_SIZE) -> dict:
    """Type 1: always overwrite in place on ``external_id``, no history kept. Idempotent, so
    re-running the same source never double-loads."""
    created = 0
    updated = 0
    for chunk in _chunked(rows, batch_size):
        with transaction.atomic():
            for row in chunk:
                _, was_created = Customer.objects.update_or_create(
                    external_id=str(row["customer_id"]),
                    is_current=True,
                    defaults={
                        "first_name": row.get("first_name", ""),
                        "last_name": row.get("last_name", ""),
                        "email": row["email"],
                        "signup_date": row.get("signup_date") or None,
                        "country": row.get("country", ""),
                    },
                )
                created += was_created
                updated += not was_created

    logger.info(
        "customers upserted", extra={"created_count": created, "updated_count": updated}
    )
    return {"created": created, "updated": updated}


def upsert_customers_scd2(
    rows: list[dict], batch_size: int = DEFAULT_BATCH_SIZE
) -> dict:
    """Slowly Changing Dimension Type 2: a changed tracked attribute closes out the current row
    (``valid_to``/``is_current=False``) and inserts a new current one, preserving full history.
    A row identical to the current version is a no-op — re-running the same source never creates
    spurious history."""
    created = 0
    changed = 0
    now = timezone.now()

    for chunk in _chunked(rows, batch_size):
        with transaction.atomic():
            for row in chunk:
                external_id = str(row["customer_id"])
                incoming = {
                    "first_name": row.get("first_name", ""),
                    "last_name": row.get("last_name", ""),
                    "email": row["email"],
                    "country": row.get("country", ""),
                }
                current = Customer.objects.filter(
                    external_id=external_id, is_current=True
                ).first()

                if current is None:
                    Customer.objects.create(
                        external_id=external_id,
                        signup_date=row.get("signup_date") or None,
                        valid_from=now,
                        is_current=True,
                        **incoming,
                    )
                    created += 1
                    continue

                if all(
                    getattr(current, field) == value
                    for field, value in incoming.items()
                ):
                    continue  # identical to the current version -- nothing to record

                current.valid_to = now
                current.is_current = False
                current.save(update_fields=["valid_to", "is_current", "updated_at"])
                Customer.objects.create(
                    external_id=external_id,
                    signup_date=current.signup_date,
                    valid_from=now,
                    is_current=True,
                    **incoming,
                )
                changed += 1

    logger.info(
        "customers upserted (scd2)",
        extra={"created_count": created, "changed_count": changed},
    )
    return {"created": created, "updated": changed}


def get_dataframe() -> pd.DataFrame:
    """Snapshot of the served gold table's *current* rows, used to write the metadata app's gold
    medallion layer — the dataset's Parquet gold layer mirrors what this API serves by default.
    """
    return pd.DataFrame(
        list(Customer.objects.filter(is_current=True).values(*_GOLD_COLUMNS))
    )
