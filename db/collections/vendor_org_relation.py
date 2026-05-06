from __future__ import annotations

from datetime import datetime

from pydantic import Field

from db.collections.common import FirestoreBaseModel, MetadataUpdatedOnly


class VendorOrgRelationMetrics(FirestoreBaseModel):
    total_orders: int = Field(alias="totalOrders")
    total_spend: float = Field(alias="totalSpend")


COLLECTION_ID = "vendorOrgRelations"


class VendorOrgRelation(FirestoreBaseModel):
    id: str
    organization_id: str = Field(alias="organizationId")
    vendor_id: str = Field(alias="vendorId")
    relationship_status: str = Field(alias="relationshipStatus")
    preferred_vendor: bool = Field(alias="preferredVendor")
    metrics: VendorOrgRelationMetrics
    last_transaction_at: datetime | None = Field(default=None, alias="lastTransactionAt")
    active: bool
    metadata: MetadataUpdatedOnly
