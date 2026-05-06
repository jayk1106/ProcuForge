from __future__ import annotations

from pydantic import Field

from db.collections.common import DocumentMetadata, FirestoreBaseModel

COLLECTION_ID = "users"


class User(FirestoreBaseModel):
    id: str
    organization_id: str = Field(alias="organizationId")
    name: str
    email: str
    role: str
    active: bool
    metadata: DocumentMetadata
