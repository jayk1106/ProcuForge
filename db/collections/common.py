from __future__ import annotations

from datetime import datetime
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field

Specifications: TypeAlias = dict[str, str | int | float | bool]

FIRESTORE_MODEL_CONFIG = ConfigDict(
    extra="ignore",
    populate_by_name=True,
    serialize_by_alias=True,
)


class FirestoreBaseModel(BaseModel):
    model_config = FIRESTORE_MODEL_CONFIG


class Address(FirestoreBaseModel):
    address: str = ""
    country: str
    state: str
    city: str
    pincode: str = ""


class Contact(FirestoreBaseModel):
    email: str
    phone: str
    website: str


class DocumentMetadata(FirestoreBaseModel):
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")


class MetadataUpdatedOnly(FirestoreBaseModel):
    updated_at: datetime | None = Field(default=None, alias="updatedAt")


class EstimatedPriceRange(FirestoreBaseModel):
    currency: str
    range_min: float = Field(alias="min")
    range_max: float = Field(alias="max")
