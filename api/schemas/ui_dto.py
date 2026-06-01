"""Response DTOs aligned with web/src/types."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkflowRowDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    request_id: str = Field(alias="requestId")
    product: str
    requested_by: str = Field(alias="requestedBy")
    requested_at: str = Field(alias="requestedAt")
    phase: Literal["RFQ", "NEG", "PO", "GRN", "INV", "DONE"]
    current_state: str = Field(alias="currentState")
    vendors: int
    days: int
    needs_action: bool = Field(alias="needsAction")
    action_label: str | None = Field(default=None, alias="actionLabel")
    walked: bool = False


class VendorThreadRowDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str = Field(description="rfq_id — used for /vendors/:id routing")
    vendor_id: str = Field(alias="vendorId")
    name: str
    country: str
    tier: str = "Tier-2"
    pr: str = Field(description="Parent workflow request_id or workflow_id")
    workflow_id: str = Field(alias="workflowId")
    last: str
    state: str
    unread: int = 0
    msgs: int = 0
    round: int | None = None
    latest_price: float | None = Field(default=None, alias="latestPrice")
    done: bool = False


class VendorThreadMessageDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    ts: str
    from_agent: str = Field(alias="from")
    to_agent: str = Field(alias="to")
    type: str
    phase: str
    locked: bool = False
    error: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


class VendorConvoDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    vendor: dict[str, str]
    pr: str
    workflow_id: str = Field(alias="workflowId")
    rfq_id: str = Field(alias="rfqId")
    outcome: str
    messages: list[VendorThreadMessageDTO]


class ActiveVendorDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str = Field(description="vendor_id for display")
    rfq_id: str = Field(alias="rfqId")
    name: str
    country: str
    round: str
    state: str
    status: Literal["NEGOTIATING", "WON", "LOST", "WALKED_AWAY"]
    latest: float | None = None
    delta: float | None = None
    moq: int = 1
    lead: str = "—"
    escalated: bool = False
    thread: list[dict[str, str]] = Field(default_factory=list)


class ActivityItemDTO(BaseModel):
    ts: str
    ag: str
    det: str


class WorkflowDetailDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    request_id: str = Field(alias="requestId")
    title: str
    requester: str
    cost_center: str = Field(alias="costCenter")
    opened: str
    target: float
    need_by: str = Field(alias="needBy")
    spec: str
    pr_status: str = Field(alias="prStatus")
    phase_durations: dict[str, str | None] = Field(alias="phaseDurations")
    current_phase: str = Field(alias="currentPhase")
    needs_action: bool = Field(alias="needsAction")
    action_label: str | None = Field(default=None, alias="actionLabel")
    vendors: list[ActiveVendorDTO] = Field(default_factory=list)
    activity: list[ActivityItemDTO] = Field(default_factory=list)
    po: dict[str, Any] | None = None
    grn: dict[str, Any] | None = None
    invoice: dict[str, Any] | None = None
    selected_vendor: dict[str, Any] | None = Field(default=None, alias="selectedVendor")
