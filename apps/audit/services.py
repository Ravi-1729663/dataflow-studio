"""Records sensitive actions. Called from the app that performs the action (accounts, datasources,
pipelines, workspaces, ...) — the same "bridge a side-effect into a model" role every services.py
in this project already plays; audit logging is just one more thing that happens alongside a
sensitive write, never a reason to fail the request it's recording."""

import logging

from .models import AuditLog

logger = logging.getLogger("dataflow.audit")


def record(
    actor, action: str, workspace=None, target: str = "", metadata: dict | None = None
) -> AuditLog:
    entry = AuditLog.objects.create(
        actor=actor if actor is not None and actor.is_authenticated else None,
        workspace=workspace,
        action=action,
        target=target,
        metadata=metadata or {},
    )
    logger.info(
        "audit event recorded",
        extra={
            "actor": str(actor) if actor else None,
            "action": action,
            "target": target,
        },
    )
    return entry
