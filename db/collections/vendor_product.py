from __future__ import annotations

from pydantic import Field

from db.collections.common import FirestoreBaseModel, MetadataUpdatedOnly


class VendorProductPricing(FirestoreBaseModel):
    currency: str
    unit_price: float = Field(alias="unitPrice")
    minimum_order_qty: int = Field(alias="minimumOrderQty")


COLLECTION_ID = "vendorProducts"


class VendorProduct(FirestoreBaseModel):
    id: str
    vendor_id: str = Field(alias="vendorId")
    product_id: str = Field(alias="productId")
    vendor_sku: str = Field(alias="vendorSku")
    unit: str
    pricing: VendorProductPricing
    lead_time_days: int = Field(alias="leadTimeDays")
    contracted: bool
    availability_status: str = Field(alias="availabilityStatus")
    active: bool
    metadata: MetadataUpdatedOnly
