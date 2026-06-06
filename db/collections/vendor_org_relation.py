from __future__ import annotations

from datetime import datetime

from pydantic import Field

from db.collections.common import FirestoreBaseModel, MetadataUpdatedOnly


class VendorOrgRelationMetrics(FirestoreBaseModel):
    total_orders: int = Field(alias="totalOrders")
    total_spend: float = Field(alias="totalSpend")
    average_delivery_delay_days: float | None = Field(default=None, alias="averageDeliveryDelayDays")
    quality_score: float | None = Field(default=None, alias="qualityScore")
    negotiation_score: float | None = Field(default=None, alias="negotiationScore")
    response_speed_score: float | None = Field(default=None, alias="responseSpeedScore")


class VendorOrgPricingInsights(FirestoreBaseModel):
    average_discount_percent: float | None = Field(default=None, alias="averageDiscountPercent")
    usually_offers_discount: bool | None = Field(default=None, alias="usuallyOffersDiscount")


class VendorOrgRiskInsights(FirestoreBaseModel):
    risk_level: str | None = Field(default=None, alias="riskLevel")
    issues_count: int | None = Field(default=None, alias="issuesCount")


COLLECTION_ID = "vendorOrgRelations"


class VendorOrgRelation(FirestoreBaseModel):
    id: str
    organization_id: str = Field(alias="organizationId")
    vendor_id: str = Field(alias="vendorId")
    relationship_status: str = Field(alias="relationshipStatus")
    relationship_strength: float | None = Field(default=None, alias="relationshipStrength")
    preferred_vendor: bool = Field(alias="preferredVendor")
    metrics: VendorOrgRelationMetrics
    pricing_insights: VendorOrgPricingInsights | None = Field(default=None, alias="pricingInsights")
    risk_insights: VendorOrgRiskInsights | None = Field(default=None, alias="riskInsights")
    notes: list[str] | None = None
    active: bool
    metadata: MetadataUpdatedOnly
