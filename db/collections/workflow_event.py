from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from db.collections.common import DocumentMetadata, FirestoreBaseModel

COLLECTION_ID = "workflow_events"


class WorkflowEventDoc(FirestoreBaseModel):
    """Durable record of a single event broadcast to WS subscribers.

    Stored at ``workflow_events/{workflow_id}/events/{event_id}`` so the per-
    workflow read is a cheap subcollection scan. ``vendor_thread_id`` is set
    when the event is scoped to a single vendor negotiation thread; the
    composite index on ``(vendor_thread_id, ts)`` powers the per-thread read.
    """

    id: str = Field(description="Document id (event uuid).")
    workflow_id: str = Field(alias="workflowId")
    vendor_thread_id: str | None = Field(default=None, alias="vendorThreadId")
    event_type: str = Field(alias="eventType")
    author: str | None = None
    ts: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
