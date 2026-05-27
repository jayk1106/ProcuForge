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


class BuyerSessionDeliveryState(BaseModel):
    """Nested `delivery` object stored under session state `request`."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    address: str
    city: str
    state: str
    country: str
    pincode: str

    @classmethod
    def from_delivery_location(cls, loc: DeliveryLocation) -> BuyerSessionDeliveryState:
        return cls(
            address=loc.address,
            city=loc.city,
            state=loc.state,
            country=loc.country,
            pincode=loc.pincode,
        )


class WorkflowStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    organization_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Tenant org; falls back to WORKFLOW_DEFAULT_ORGANIZATION_ID when omitted.",
    )
    requester_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Buyer identity; falls back to WORKFLOW_DEFAULT_USER_ID when omitted.",
    )
    purpose: str | None = Field(
        default=None,
        max_length=4000,
        description="Business reason for the purchase; defaults to 'Not specified' in session state.",
    )

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

    @field_validator("organization_id", "requester_id", "purpose", mode="before")
    @classmethod
    def _empty_optional_str_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

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


class BuyerSessionRequestState(BaseModel):
    """Canonical procurement payload under ADK session state key `request`."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=120)
    organization_id: str = Field(min_length=1, max_length=200)
    requester_id: str = Field(min_length=1, max_length=200)
    created_at: str = Field(description="ISO-8601 timestamp in UTC (Z suffix).")
    currency: str
    product_id: str
    quantity: int
    required_by_date: str = Field(description="ISO-8601 calendar date (YYYY-MM-DD).")
    delivery: BuyerSessionDeliveryState
    purpose: str = Field(max_length=4000)
    urgency: str
    budget_ceiling: float = Field(gt=0)
    buyer_notes: list[str] | None = None

    @classmethod
    def from_workflow_start(
        cls,
        *,
        workflow_id: str,
        created_at: datetime,
        body: WorkflowStartRequest,
        organization_id: str,
        requester_id: str,
    ) -> BuyerSessionRequestState:
        created_utc = created_at.astimezone(timezone.utc)
        created_str = created_utc.isoformat().replace("+00:00", "Z")
        short = workflow_id.replace("-", "")[:8].upper()
        d = created_utc.date()
        request_id = f"PR-{d.year}-{d.month:02d}{d.day:02d}-{short}"
        purpose_raw = body.purpose.strip() if body.purpose else ""
        purpose = purpose_raw if purpose_raw else "Not specified"
        return cls(
            request_id=request_id,
            organization_id=organization_id,
            requester_id=requester_id,
            created_at=created_str,
            currency=body.currency,
            product_id=body.product_id,
            quantity=body.quantity,
            required_by_date=body.required_by.isoformat(),
            delivery=BuyerSessionDeliveryState.from_delivery_location(body.delivery_location),
            purpose=purpose,
            urgency=body.urgency.value,
            budget_ceiling=float(body.budget_ceiling),
            buyer_notes=body.buyer_notes,
        )


class WorkflowStartResponse(BaseModel):
    workflow_id: str
    session_id: str
    status: Literal["started"] = "started"
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkflowApproveResponse(BaseModel):
    workflow_id: str
    status: Literal["approved"] = "approved"
    approved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
