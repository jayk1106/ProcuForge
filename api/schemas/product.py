"""Product catalog DTOs for the create-request picker."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from api.services.product_query import truncate_description
from db.collections.product import Product


class EstimatedPriceRangeDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    currency: str
    min: float
    max: float


class ProductOptionDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    name: str
    brand: str
    description: str
    estimated_price_range: EstimatedPriceRangeDTO = Field(alias="estimatedPriceRange")

    @classmethod
    def from_product(cls, product: Product) -> ProductOptionDTO:
        price = product.estimated_price_range
        return cls(
            id=product.id,
            name=product.name,
            brand=product.brand,
            description=truncate_description(product.description),
            estimatedPriceRange=EstimatedPriceRangeDTO(
                currency=price.currency,
                min=price.range_min,
                max=price.range_max,
            ),
        )
