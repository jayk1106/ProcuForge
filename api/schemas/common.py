from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"] = Field(
        default="ok",
        description="Overall health indicator.",
    )
    environment: str = Field(description="Runtime environment name (e.g. development).")
    version: str = Field(description="API version string.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Server time in UTC when the response was produced.",
    )


class PingResponse(BaseModel):
    message: Literal["pong"] = "pong"


class EchoRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2048, description="Text to echo back.")
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata to round-trip alongside the message.",
    )


class EchoResponse(BaseModel):
    message: str
    metadata: dict[str, Any] | None = None
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
