from __future__ import annotations

import asyncio
from typing import Any

from google.cloud import firestore

from db.collections.workflow_index import COLLECTION_ID, WorkflowIndexEntry
from db.firestore.serialization import (
    merge_update_dict,
    model_to_firestore_dict,
    snapshot_to_model_dict,
)


class WorkflowIndexRepository:
    def __init__(self, client: firestore.Client) -> None:
        self._collection = client.collection(COLLECTION_ID)

    async def upsert(self, entry: WorkflowIndexEntry) -> None:
        def _op() -> None:
            ref = self._collection.document(entry.workflow_id)
            snap = ref.get()
            if snap.exists:
                data = model_to_firestore_dict(entry, include_id_in_body=False, timestamps="update")
                data.pop("metadata", None)
                ref.set(merge_update_dict(data), merge=True)
            else:
                data = model_to_firestore_dict(entry, include_id_in_body=False, timestamps="create")
                ref.set(data, merge=False)

        await asyncio.to_thread(_op)

    async def get(self, workflow_id: str) -> WorkflowIndexEntry | None:
        def _op() -> WorkflowIndexEntry | None:
            snap = self._collection.document(workflow_id).get()
            if not snap.exists:
                return None
            body = snapshot_to_model_dict(snap.id, snap.to_dict())
            return WorkflowIndexEntry.model_validate(body)

        return await asyncio.to_thread(_op)

    async def list_by_org(
        self,
        organization_id: str,
        *,
        limit: int = 100,
    ) -> list[WorkflowIndexEntry]:
        def _op() -> list[WorkflowIndexEntry]:
            query = self._collection.where("organizationId", "==", organization_id).limit(limit)
            rows: list[WorkflowIndexEntry] = []
            for snap in query.stream():
                body = snapshot_to_model_dict(snap.id, snap.to_dict())
                rows.append(WorkflowIndexEntry.model_validate(body))
            rows.sort(key=lambda e: e.started_at, reverse=True)
            return rows

        return await asyncio.to_thread(_op)

    async def update_fields(self, workflow_id: str, patch: dict[str, Any]) -> None:
        def _op() -> None:
            ref = self._collection.document(workflow_id)
            ref.set(merge_update_dict(patch), merge=True)

        await asyncio.to_thread(_op)
