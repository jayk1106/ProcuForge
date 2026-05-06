from __future__ import annotations

from db.collections.common import DocumentMetadata, FirestoreBaseModel

COLLECTION_ID = "categories"


class Category(FirestoreBaseModel):
    id: str
    name: str
    description: str
    active: bool
    metadata: DocumentMetadata
