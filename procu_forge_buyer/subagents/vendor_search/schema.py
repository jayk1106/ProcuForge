"""Session.state shape for vendor lines available for the current procurement product."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VendorOffer(BaseModel):
    """One supplier line item for the requested product (catalog + commercial terms)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(description="Backing vendor-product record id.")
    vendor_id: str = Field(alias="vendorId")
    product_id: str = Field(alias="productId")
    vendor_sku: str = Field(alias="vendorSku")
    unit_price: float = Field(alias="unitPrice")
    currency: str
    lead_time_days: int = Field(alias="leadTimeDays")
    contracted: bool
    availability_status: str = Field(alias="availabilityStatus")


class ProductVendorOffers(BaseModel):
    """Vendors and terms currently associated with `request.product_id` in this workflow."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    product_id: str = Field(alias="productId")
    offers: list[VendorOffer]
