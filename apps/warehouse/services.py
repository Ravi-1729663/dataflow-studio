"""Idempotent load helpers for the warehouse gold layer. This is the `loader` the etl engine calls."""

import logging

from .models import Customer

logger = logging.getLogger("dataflow.warehouse")


def upsert_customers(rows: list[dict]) -> dict:
    """Upsert on ``external_id``, keeping re-runs of the same source idempotent."""
    created = 0
    updated = 0
    for row in rows:
        _, was_created = Customer.objects.update_or_create(
            external_id=str(row["customer_id"]),
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
