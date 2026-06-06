from __future__ import annotations

from datetime import datetime

from pydantic import Field

from db.collections.common import DocumentMetadata, FirestoreBaseModel

COLLECTION_ID = "rfq_index"


class RfqIndexEntry(FirestoreBaseModel):
    """O(1) lookup from rfq_id to its owning workflow/vendor.

    Written at vendor fan-out time so the vendor-thread detail endpoint and
    WS channel can resolve ``rfq_id -> (workflow_id, vendor_id)`` without
    scanning every buyer session.
    """

    id: str = Field(description="Document id equals rfq_id.")
    rfq_id: str = Field(alias="rfqId")
    workflow_id: str = Field(alias="workflowId")
    vendor_id: str = Field(alias="vendorId")
    organization_id: str = Field(alias="organizationId")
    created_at: datetime = Field(alias="createdAt")
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
