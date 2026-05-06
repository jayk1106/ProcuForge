from __future__ import annotations

from pydantic import Field

from db.collections.common import Address, DocumentMetadata, FirestoreBaseModel

COLLECTION_ID = "organisations"

class Organisation(FirestoreBaseModel):
    id: str
    name: str
    address: Address
    active: bool
    metadata: DocumentMetadata
