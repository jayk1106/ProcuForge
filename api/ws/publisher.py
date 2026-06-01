"""The single user-facing publish utility.

Designed to be the one import you need anywhere in the codebase to push
data to WebSocket subscribers of a workflow (and, optionally, a vendor
thread channel) and to durably append the event to the Firestore event log.

Safe from sync or async, from any thread. Never raises. Firestore failures
do not block the in-memory WS broadcast.

Example
-------
>>> from api.ws import publish
>>> publish(workflow_id, "pr_status_changed", {"pr_status": "VENDORS_DISCOVERED"})
>>> publish(workflow_id, "vendor_quote_received",
...         {"price": 12.5}, vendor_thread_id=rfq_id, author="vendor")
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from .manager import manager
from .schema import WorkflowEvent

logger = logging.getLogger(__name__)

__all__ = ["publish"]


_events_repo = None


def _get_events_repo():
    global _events_repo
    if _events_repo is None:
        from db.firestore.client import get_firestore_client
        from db.firestore.repositories.workflow_events import WorkflowEventsRepository

        _events_repo = WorkflowEventsRepository(get_firestore_client())
    return _events_repo


def publish(
    workflow_id: str,
    event_type: str,
    data: dict[str, Any] | None = None,
    *,
    vendor_thread_id: str | None = None,
    author: str | None = None,
) -> None:
    """Fire-and-forget push to WS subscribers + durable Firestore append.

    Never raises — failures are logged and swallowed so that callers
    (callbacks, tools, handlers) are unaffected by transport issues.
    """
    if not workflow_id or not event_type:
        return
    try:
        event = WorkflowEvent(
            workflow_id=workflow_id,
            event_type=event_type,
            vendor_thread_id=vendor_thread_id,
            author=author,
            data=data or {},
        )
    except Exception:
        logger.exception(
            "ws.publish.envelope_failed workflow_id=%s event_type=%s",
            workflow_id,
            event_type,
        )
        return

    _schedule_persist(event)

    try:
        manager.schedule_broadcast(event)
    except Exception:
        logger.exception(
            "ws.publish.broadcast_failed workflow_id=%s event_type=%s",
            workflow_id,
            event_type,
        )


def _schedule_persist(event: WorkflowEvent) -> None:
    """Schedule the Firestore append on the bound loop. No-op if loop unbound."""
    loop = manager._loop  # noqa: SLF001 — intentional reuse of the bound loop
    if loop is None:
        # Pre-startup callers (rare); skip persistence rather than blocking.
        return

    coro = _persist_event(event)
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    try:
        if running is loop:
            loop.create_task(coro)
        else:
            asyncio.run_coroutine_threadsafe(coro, loop)
    except Exception:
        logger.exception(
            "ws.publish.persist_schedule_failed workflow_id=%s event_type=%s",
            event.workflow_id,
            event.event_type,
        )


async def _persist_event(event: WorkflowEvent) -> None:
    try:
        from db.collections.workflow_event import WorkflowEventDoc

        doc = WorkflowEventDoc(
            id=uuid.uuid4().hex,
            workflow_id=event.workflow_id,
            vendor_thread_id=event.vendor_thread_id,
            event_type=event.event_type,
            author=event.author,
            ts=event.timestamp,
            payload=event.data,
        )
        await _get_events_repo().append(doc)
    except Exception:
        logger.exception(
            "ws.publish.persist_failed workflow_id=%s event_type=%s",
            event.workflow_id,
            event.event_type,
        )
