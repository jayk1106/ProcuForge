from __future__ import annotations

from datetime import datetime

from pydantic import Field

from db.collections.common import DocumentMetadata, FirestoreBaseModel

COLLECTION_ID = "workflow_index"


class WorkflowIndexEntry(FirestoreBaseModel):
    """Thin Firestore index for listing buyer workflows in the UI."""

    id: str = Field(description="Document id equals workflow_id (UUID).")
    workflow_id: str = Field(alias="workflowId")
    request_id: str = Field(alias="requestId")
    organization_id: str = Field(alias="organizationId")
    product_id: str = Field(alias="productId")
    product_name: str = Field(alias="productName")
    requester_id: str = Field(alias="requesterId")
    pr_status: str = Field(alias="prStatus")
    started_at: datetime = Field(alias="startedAt")
    updated_at: datetime = Field(alias="updatedAt")
    vendor_count: int = Field(default=0, alias="vendorCount")
    needs_action: bool = Field(default=False, alias="needsAction")
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
