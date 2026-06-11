from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from db.collections.common import DocumentMetadata, FirestoreBaseModel

COLLECTION_ID = "workflow_state"


class WorkflowStateDoc(FirestoreBaseModel):
    """Canonical Firestore mirror of a buyer workflow session.

    Top-level fields are denormalized from ``state`` so list-page queries can
    filter and sort without touching the nested blob. ``state`` carries the
    full buyer ADK session state and is the source the detail page DTO is
    built from.
    """

    id: str = Field(description="Document id equals workflow_id (UUID).")
    workflow_id: str = Field(alias="workflowId")
    request_id: str = Field(alias="requestId")
    organization_id: str = Field(alias="organizationId")
    product_id: str = Field(alias="productId")
    product_name: str = Field(alias="productName")
    requester_id: str = Field(alias="requesterId")
    pr_status: str = Field(alias="prStatus")
    phase_group: str = Field(default="IN_PROGRESS", alias="phaseGroup")
    started_at: datetime = Field(alias="startedAt")
    updated_at: datetime = Field(alias="updatedAt")
    vendor_count: int = Field(default=0, alias="vendorCount")
    needs_action: bool = Field(default=False, alias="needsAction")
    state_version: int = Field(default=0, alias="stateVersion")
    state: dict[str, Any] = Field(default_factory=dict)
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
