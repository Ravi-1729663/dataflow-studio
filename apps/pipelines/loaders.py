"""Maps a Pipeline's ``target`` to a warehouse loader callable. The only bridge from etl to warehouse."""

from apps.common.exceptions import PipelineExecutionError
from apps.warehouse.services import upsert_customers, upsert_customers_scd2

_TARGETS = {
    "customers": upsert_customers,
    "customers_scd2": upsert_customers_scd2,
}


def get_loader(target: str):
    try:
        return _TARGETS[target]
    except KeyError as exc:
        raise PipelineExecutionError(
            f"no loader registered for target={target!r}"
        ) from exc
