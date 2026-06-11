"""Session.state shape for vendor lines available for the current procurement product."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VendorRelationSummary(BaseModel):
    """Buyer↔vendor relationship signals for ranking and downstream negotiation."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    preferred_vendor: bool = Field(alias="preferredVendor")
    relationship_status: str = Field(alias="relationshipStatus")
    relationship_strength: float | None = Field(default=None, alias="relationshipStrength")
    average_delivery_delay_days: float | None = Field(
        default=None, alias="averageDeliveryDelayDays"
    )
    quality_score: float | None = Field(default=None, alias="qualityScore")
    risk_level: str | None = Field(default=None, alias="riskLevel")
    usually_offers_discount: bool | None = Field(default=None, alias="usuallyOffersDiscount")
    average_discount_percent: float | None = Field(default=None, alias="averageDiscountPercent")


class VendorOffer(BaseModel):
    """One supplier line item for the requested product (catalog + commercial terms)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(description="Backing vendor-product record id.")
    vendor_id: str = Field(alias="vendorId")
    product_id: str = Field(alias="productId")
    vendor_sku: str = Field(alias="vendorSku")
    unit: str = Field(description="Sell unit for unit_price (e.g. piece, kg, liter, hour).")
    unit_price: float = Field(alias="unitPrice")
    currency: str
    lead_time_days: int = Field(alias="leadTimeDays")
    contracted: bool
    availability_status: str = Field(alias="availabilityStatus")
    minimum_order_qty: int = Field(default=0, alias="minimumOrderQty")
    currency_matches_request: bool = Field(default=True, alias="currencyMatchesRequest")
    vendor_relation: VendorRelationSummary | None = Field(default=None, alias="vendorRelation")


class ProductVendorOffers(BaseModel):
    """Vendors and terms currently associated with `request.product_id` in this workflow."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    product_id: str = Field(alias="productId")
    offers: list[VendorOffer]
