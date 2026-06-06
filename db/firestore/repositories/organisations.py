from __future__ import annotations

import asyncio

from google.cloud import firestore

from db.collections.organisation import COLLECTION_ID, Organisation
from db.firestore.serialization import snapshot_to_model_dict


class OrganisationRepository:
    def __init__(self, client: firestore.Client) -> None:
        self._collection = client.collection(COLLECTION_ID)

    async def get(self, org_id: str) -> Organisation | None:
        def _op() -> Organisation | None:
            snap = self._collection.document(org_id).get()
            if not snap.exists:
                return None
            body = snapshot_to_model_dict(snap.id, snap.to_dict())
            return Organisation.model_validate(body)

        return await asyncio.to_thread(_op)
