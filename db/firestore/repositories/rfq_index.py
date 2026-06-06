from __future__ import annotations

import asyncio

from google.cloud import firestore

from db.collections.rfq_index import COLLECTION_ID, RfqIndexEntry
from db.firestore.serialization import (
    merge_update_dict,
    model_to_firestore_dict,
    snapshot_to_model_dict,
)


class RfqIndexRepository:
    def __init__(self, client: firestore.Client) -> None:
        self._collection = client.collection(COLLECTION_ID)

    async def upsert(self, entry: RfqIndexEntry) -> None:
        def _op() -> None:
            ref = self._collection.document(entry.rfq_id)
            snap = ref.get()
            if snap.exists:
                data = model_to_firestore_dict(
                    entry, include_id_in_body=False, timestamps="update"
                )
                data.pop("metadata", None)
                ref.set(merge_update_dict(data), merge=True)
            else:
                data = model_to_firestore_dict(
                    entry, include_id_in_body=False, timestamps="create"
                )
                ref.set(data, merge=False)

        await asyncio.to_thread(_op)

    async def get(self, rfq_id: str) -> RfqIndexEntry | None:
        def _op() -> RfqIndexEntry | None:
            snap = self._collection.document(rfq_id).get()
            if not snap.exists:
                return None
            body = snapshot_to_model_dict(snap.id, snap.to_dict())
            return RfqIndexEntry.model_validate(body)

        return await asyncio.to_thread(_op)

    async def list_by_workflow(self, workflow_id: str) -> list[RfqIndexEntry]:
        def _op() -> list[RfqIndexEntry]:
            query = self._collection.where("workflowId", "==", workflow_id)
            rows: list[RfqIndexEntry] = []
            for snap in query.stream():
                body = snapshot_to_model_dict(snap.id, snap.to_dict())
                rows.append(RfqIndexEntry.model_validate(body))
            rows.sort(key=lambda e: e.created_at)
            return rows

        return await asyncio.to_thread(_op)
