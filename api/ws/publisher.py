"""WebSocket publish API.

Two public entry points, both fire-and-forget and safe from any thread:

- ``record_event(workflow_id, event_type, data, ...)`` — durably append a
  granular event to the Firestore event log. Used for the activity feed and
  audit history. No WebSocket side-effect.

- ``broadcast_state(channel, factory, *, reason, ...)`` — push the latest
  DTO snapshot for a channel to subscribed WebSocket clients. The connection
  manager debounces, dedupes by payload hash, and skips work entirely when
  no subscribers are listening.

Both functions never raise; failures are logged.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from .manager import StateFactory, manager
from .schema import WorkflowEvent

logger = logging.getLogger(__name__)

__all__ = ["broadcast_state", "record_event"]


_events_repo = None


def _get_events_repo():
    global _events_repo
    if _events_repo is None:
        from db.firestore.client import get_firestore_client
        from db.firestore.repositories.workflow_events import WorkflowEventsRepository

        _events_repo = WorkflowEventsRepository(get_firestore_client())
    return _events_repo


def record_event(
    workflow_id: str,
    event_type: str,
    data: dict[str, Any] | None = None,
    *,
    vendor_thread_id: str | None = None,
    author: str | None = None,
) -> None:
    """Append a granular event to the Firestore event log. Never raises.

    Powers the activity feed (``ui_mappers._activity_detail_for_event``) and
    serves as the audit trail. Does not push anything to WebSocket clients —
    real-time UI updates go through :func:`broadcast_state` instead.
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
            "ws.record_event.envelope_failed workflow_id=%s event_type=%s",
            workflow_id,
            event_type,
        )
        return

    _schedule_persist(event)


def broadcast_state(
    channel: str,
    factory: StateFactory,
    *,
    reason: str,
    workflow_id: str | None = None,
    vendor_thread_id: str | None = None,
) -> None:
    """Schedule a ``state_changed`` push on ``channel``. Never raises.

    Thin wrapper around :meth:`ConnectionManager.broadcast_state`. The
    factory is invoked only if the channel has subscribers and the debounce
    window allows it — so unwatched workflows pay no DTO-build cost.
    """
    try:
        manager.broadcast_state(
            channel,
            factory,
            reason=reason,
            workflow_id=workflow_id,
            vendor_thread_id=vendor_thread_id,
        )
    except Exception:
        logger.exception(
            "ws.broadcast_state.failed channel=%s reason=%s",
            channel,
            reason,
        )


def _schedule_persist(event: WorkflowEvent) -> None:
    """Schedule the Firestore append on the bound loop. No-op if loop unbound."""
    loop = manager._loop  # noqa: SLF001 — intentional reuse of the bound loop
    if loop is None:
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
            "ws.record_event.persist_schedule_failed workflow_id=%s event_type=%s",
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
        logger.debug(
            "ws.record_event.persisted workflow_id=%s event_type=%s",
            event.workflow_id,
            event.event_type,
        )
    except Exception:
        logger.exception(
            "ws.record_event.persist_failed workflow_id=%s event_type=%s",
            event.workflow_id,
            event.event_type,
        )
