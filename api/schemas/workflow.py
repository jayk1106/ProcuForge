from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Urgency(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    emergency = "emergency"


class DeliveryLocation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    address: str = Field(min_length=1, max_length=500)
    city: str = Field(min_length=1, max_length=120)
    state: str = Field(min_length=1, max_length=120)
    country: str = Field(min_length=2, max_length=120)
    pincode: str = Field(min_length=3, max_length=20)


class WorkflowStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    product_id: str = Field(min_length=1, max_length=200, description="Firestore product document id.")
    quantity: int = Field(gt=0, le=1_000_000, description="Units to procure.")
    required_by: date = Field(description="Date by which delivery is required (today or later).")
    delivery_location: DeliveryLocation
    urgency: Urgency
    buyer_notes: list[str] | None = Field(
        default=None,
        max_length=50,
        description="Optional learnings/notes from past iterations.",
    )
    budget_ceiling: Decimal = Field(
        gt=0,
        max_digits=18,
        decimal_places=2,
        description="Top cap for spend (in `currency`).",
    )
    currency: str = Field(
        min_length=3,
        max_length=3,
        pattern=r"^[A-Za-z]{3}$",
        description="ISO 4217 currency code.",
    )

    @field_validator("currency", mode="after")
    @classmethod
    def _normalize_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("required_by", mode="after")
    @classmethod
    def _required_by_not_in_past(cls, value: date) -> date:
        today = datetime.now(timezone.utc).date()
        if value < today:
            raise ValueError("required_by must be today or a future date")
        return value

    @field_validator("buyer_notes", mode="after")
    @classmethod
    def _strip_blank_notes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [note.strip() for note in value if note and note.strip()]
        return cleaned or None


class WorkflowStartResponse(BaseModel):
    workflow_id: str
    session_id: str
    status: Literal["started"] = "started"
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
