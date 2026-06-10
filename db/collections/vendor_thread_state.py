from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from db.collections.common import DocumentMetadata, FirestoreBaseModel

COLLECTION_ID = "vendor_thread_state"


class VendorThreadStateDoc(FirestoreBaseModel):
    """Canonical Firestore mirror of one buyer↔vendor negotiation thread.

    The thread is keyed by ``rfq_id``. ``state`` holds the full vendor ADK
    session state (when known) plus a derived ``buyerOverride`` block that
    carries the buyer-side escalate/walk-away verdict so the detail page can
    render the final view from one document.
    """

    id: str = Field(description="Document id equals rfq_id.")
    rfq_id: str = Field(alias="rfqId")
    workflow_id: str = Field(alias="workflowId")
    request_id: str = Field(default="", alias="requestId")
    vendor_id: str = Field(alias="vendorId")
    vendor_name: str = Field(default="", alias="vendorName")
    vendor_country: str = Field(default="", alias="vendorCountry")
    organization_id: str = Field(alias="organizationId")
    status: str = ""
    needs_action: bool = Field(default=False, alias="needsAction")
    last_offer_price: float | None = Field(default=None, alias="lastOfferPrice")
    last_offer_currency: str = Field(default="USD", alias="lastOfferCurrency")
    round: int = 0
    message_count: int = Field(default=0, alias="messageCount")
    done: bool = False
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    state_version: int = Field(default=0, alias="stateVersion")
    state: dict[str, Any] = Field(default_factory=dict)
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
