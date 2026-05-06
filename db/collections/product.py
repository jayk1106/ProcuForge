from __future__ import annotations

from pydantic import Field

from db.collections.common import (
    DocumentMetadata,
    EstimatedPriceRange,
    FirestoreBaseModel,
    Specifications,
)

COLLECTION_ID = "products"


class Product(FirestoreBaseModel):
    id: str
    category_id: str = Field(alias="categoryId")
    name: str
    brand: str
    type: str
    description: str
    specifications: Specifications
    estimated_price_range: EstimatedPriceRange = Field(alias="estimatedPriceRange")
    active: bool
    metadata: DocumentMetadata
