"""Event envelope sent to WebSocket subscribers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class WorkflowEvent(BaseModel):
    """Envelope for a single push to clients subscribed to a workflow_id."""

    workflow_id: str
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any] = Field(default_factory=dict)
