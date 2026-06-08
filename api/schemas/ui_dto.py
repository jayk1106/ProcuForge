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
    phase: str = ""
    locked: bool = False
    error: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)
    # Compact one-line summary derived from the payload (e.g. "$30.88 · qty 1").
    highlight: str = ""
    round: int | None = None


class VendorThreadSummaryDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    status: str = ""
    quoted_price: float | None = Field(default=None, alias="quotedPrice")
    accepted_price: float | None = Field(default=None, alias="acceptedPrice")
    latest_offer_price: float | None = Field(default=None, alias="latestOfferPrice")
    last_selling_price: float | None = Field(default=None, alias="lastSellingPrice")
    currency: str = "USD"
    po_number: str | None = Field(default=None, alias="poNumber")
    grn_number: str | None = Field(default=None, alias="grnNumber")
    invoice_number: str | None = Field(default=None, alias="invoiceNumber")
    # Promised delivery date from the PO.
    expected_delivery: str | None = Field(default=None, alias="expectedDelivery")
    # Actual goods-received date sourced from the GRN's ``received_at``.
    delivered_on: str | None = Field(default=None, alias="deliveredOn")


class VendorConvoDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    vendor: dict[str, str]
    pr: str
    workflow_id: str = Field(alias="workflowId")
    rfq_id: str = Field(alias="rfqId")
    outcome: str
    product: dict[str, str] = Field(default_factory=dict)
    summary: VendorThreadSummaryDTO = Field(default_factory=VendorThreadSummaryDTO)
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
    thread: list[dict[str, Any]] = Field(default_factory=list)


class ActivityItemDTO(BaseModel):
    ts: str
    ag: str
    det: str


class VendorRelationSummaryDTO(BaseModel):
    """Buyer↔vendor relationship signals surfaced alongside each discovered offer."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    preferred_vendor: bool = Field(default=False, alias="preferredVendor")
    relationship_status: str = Field(default="", alias="relationshipStatus")
    relationship_strength: float | None = Field(default=None, alias="relationshipStrength")
    average_delivery_delay_days: float | None = Field(
        default=None, alias="averageDeliveryDelayDays"
    )
    quality_score: float | None = Field(default=None, alias="qualityScore")
    risk_level: str | None = Field(default=None, alias="riskLevel")
    usually_offers_discount: bool | None = Field(default=None, alias="usuallyOffersDiscount")
    average_discount_percent: float | None = Field(default=None, alias="averageDiscountPercent")


class DiscoveredVendorDTO(BaseModel):
    """A catalog offer the buyer discovered before negotiation begins."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    offer_id: str = Field(alias="offerId")
    vendor_id: str = Field(alias="vendorId")
    name: str
    country: str = "—"
    sku: str = ""
    unit: str = ""
    unit_price: float | None = Field(default=None, alias="unitPrice")
    currency: str = "USD"
    lead_time_days: int | None = Field(default=None, alias="leadTimeDays")
    contracted: bool = False
    availability: str = Field(default="", alias="availabilityStatus")
    minimum_order_qty: int = Field(default=0, alias="minimumOrderQty")
    currency_matches_request: bool = Field(default=True, alias="currencyMatchesRequest")
    vendor_relation: VendorRelationSummaryDTO | None = Field(
        default=None, alias="vendorRelation"
    )


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
    phase_status: dict[str, str] = Field(default_factory=dict, alias="phaseStatus")
    spec_done: bool = Field(default=True, alias="specDone")
    current_phase: str = Field(alias="currentPhase")
    needs_action: bool = Field(alias="needsAction")
    action_label: str | None = Field(default=None, alias="actionLabel")
    discovered_vendors: list[DiscoveredVendorDTO] = Field(
        default_factory=list, alias="discoveredVendors"
    )
    vendors: list[ActiveVendorDTO] = Field(default_factory=list)
    activity: list[ActivityItemDTO] = Field(default_factory=list)
    po: dict[str, Any] | None = None
    grn: dict[str, Any] | None = None
    invoice: dict[str, Any] | None = None
    selected_vendor: dict[str, Any] | None = Field(default=None, alias="selectedVendor")
    approval_required: bool = Field(default=False, alias="approvalRequired")
    pending_approval: dict[str, Any] | None = Field(
        default=None, alias="pendingApproval"
    )
    approved_steps: list[str] = Field(default_factory=list, alias="approvedSteps")
    escalation_context: dict[str, Any] | None = Field(
        default=None, alias="escalationContext"
    )
