"""Typed payloads exchanged with a deployed Agent Engine app."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Feedback(BaseModel):
    """User feedback for a single agent invocation.

    Logged as a structured entry by ``AgentEngineApp.register_feedback`` so it
    can be queried later in Cloud Logging.
    """

    score: int | float = Field(
        ..., description="Numeric rating supplied by the user (e.g. 1-5 or 0/1)."
    )
    text: str | None = Field(
        default="", description="Optional free-text comment from the user."
    )
    invocation_id: str = Field(
        ..., description="Invocation ID the feedback refers to."
    )
    user_id: str | None = Field(
        default="", description="Optional identifier of the user giving feedback."
    )
    log_type: str = Field(
        default="feedback",
        description="Discriminator used when querying structured logs.",
    )
