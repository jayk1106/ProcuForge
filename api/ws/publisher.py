"""The single user-facing publish utility.

Designed to be the one import you need anywhere in the codebase to push
data to WebSocket subscribers of a workflow. Safe from sync or async,
from any thread. Never raises.

Example
-------
>>> from api.ws import publish
>>> publish(workflow_id, "pr_status_changed", {"pr_status": "VENDORS_DISCOVERED"})
"""

from __future__ import annotations

import logging
from typing import Any

from .manager import manager
from .schema import WorkflowEvent

logger = logging.getLogger(__name__)

__all__ = ["publish"]


def publish(
    workflow_id: str,
    event_type: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Fire-and-forget push to all WebSocket subscribers of ``workflow_id``.

    Never raises — failures are logged and swallowed so that callers
    (callbacks, tools, handlers) are unaffected by transport issues.
    Silently no-ops when there are no subscribers or the app loop is not bound.
    """
    if not workflow_id or not event_type:
        return
    try:
        event = WorkflowEvent(
            workflow_id=workflow_id,
            event_type=event_type,
            data=data or {},
        )
        manager.schedule_broadcast(event)
    except Exception:
        logger.exception(
            "ws.publish.failed workflow_id=%s event_type=%s",
            workflow_id,
            event_type,
        )
