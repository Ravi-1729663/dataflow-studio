"""Maps a Pipeline's ``target`` to a warehouse loader callable. The only bridge from etl to warehouse."""

from apps.common.exceptions import PipelineExecutionError
from apps.warehouse.services import upsert_customers

_TARGETS = {
    "customers": upsert_customers,
}


def get_loader(target: str):
    try:
        return _TARGETS[target]
    except KeyError as exc:
        raise PipelineExecutionError(
            f"no loader registered for target={target!r}"
        ) from exc
