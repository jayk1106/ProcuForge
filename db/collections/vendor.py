from __future__ import annotations

from pydantic import Field

from db.collections.common import Address, Contact, DocumentMetadata, FirestoreBaseModel

COLLECTION_ID = "vendors"


class Vendor(FirestoreBaseModel):
    id: str
    name: str
    categories: list[str]
    contact: Contact
    address: Address
    payment_terms: str = Field(alias="paymentTerms")
    active: bool
    metadata: DocumentMetadata
