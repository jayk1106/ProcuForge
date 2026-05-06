from __future__ import annotations

from pydantic import Field

from db.collections.common import Address, DocumentMetadata, FirestoreBaseModel

COLLECTION_ID = "organisations"


class OrganisationSettings(FirestoreBaseModel):
    approval_required: bool = Field(alias="approvalRequired")
    multi_vendor_quotes_required: bool = Field(alias="multiVendorQuotesRequired")
    default_payment_terms: str = Field(alias="defaultPaymentTerms")


class Organisation(FirestoreBaseModel):
    id: str
    name: str
    size: str
    currency: str
    settings: OrganisationSettings
    address: Address
    active: bool
    metadata: DocumentMetadata
