from __future__ import annotations

import asyncio
from typing import Any

from google.cloud import firestore

from db.collections.workflow_state import COLLECTION_ID, WorkflowStateDoc
from db.firestore.serialization import (
    merge_update_dict,
    model_to_firestore_dict,
    snapshot_to_model_dict,
)


class WorkflowStateRepository:
    def __init__(self, client: firestore.Client) -> None:
        self._collection = client.collection(COLLECTION_ID)

    async def upsert(self, doc: WorkflowStateDoc) -> None:
        def _op() -> None:
            ref = self._collection.document(doc.workflow_id)
            snap = ref.get()
            if snap.exists:
                data = model_to_firestore_dict(
                    doc, include_id_in_body=False, timestamps="update"
                )
                data.pop("metadata", None)
                # Auto-increment stateVersion on every merge write; ignore the
                # caller-supplied value so out-of-order writes only advance it.
                data["stateVersion"] = firestore.Increment(1)
                ref.set(merge_update_dict(data), merge=True)
            else:
                data = model_to_firestore_dict(
                    doc, include_id_in_body=False, timestamps="create"
                )
                data["stateVersion"] = 1
                ref.set(data, merge=False)

        await asyncio.to_thread(_op)

    async def get(self, workflow_id: str) -> WorkflowStateDoc | None:
        def _op() -> WorkflowStateDoc | None:
            snap = self._collection.document(workflow_id).get()
            if not snap.exists:
                return None
            body = snapshot_to_model_dict(snap.id, snap.to_dict())
            return WorkflowStateDoc.model_validate(body)

        return await asyncio.to_thread(_op)

    async def list_by_org(
        self,
        organization_id: str,
        *,
        limit: int = 100,
    ) -> list[WorkflowStateDoc]:
        def _op() -> list[WorkflowStateDoc]:
            query = (
                self._collection
                .where("organizationId", "==", organization_id)
                .limit(limit)
            )
            rows: list[WorkflowStateDoc] = []
            for snap in query.stream():
                body = snapshot_to_model_dict(snap.id, snap.to_dict())
                rows.append(WorkflowStateDoc.model_validate(body))
            rows.sort(key=lambda d: d.started_at, reverse=True)
            return rows

        return await asyncio.to_thread(_op)

    async def update_fields(self, workflow_id: str, patch: dict[str, Any]) -> None:
        def _op() -> None:
            ref = self._collection.document(workflow_id)
            ref.set(merge_update_dict(patch), merge=True)

        await asyncio.to_thread(_op)
