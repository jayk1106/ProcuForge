"""Event envelope sent to WebSocket subscribers and persisted to Firestore."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class WorkflowEvent(BaseModel):
    """Envelope for a single push to clients subscribed to a workflow_id.

    When ``vendor_thread_id`` is set, the event is also fanned out to
    subscribers of that vendor thread (key ``vt:{vendor_thread_id}`` in the
    connection manager).
    """

    workflow_id: str
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    vendor_thread_id: str | None = None
    author: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
