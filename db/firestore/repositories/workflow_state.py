from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from google.cloud import firestore

from db.collections.workflow_state import COLLECTION_ID, WorkflowStateDoc
from db.firestore.pagination import decode_cursor, encode_cursor
from db.firestore.serialization import (
    merge_update_dict,
    model_to_firestore_dict,
    snapshot_to_model_dict,
)

_VALID_PHASE_GROUPS = {"IN_PROGRESS", "DONE", "WALKED"}


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
        limit: int = 25,
        cursor: str | None = None,
        status_filter: str | None = None,
    ) -> tuple[list[WorkflowStateDoc], str | None]:
        """Cursor-paginated list ordered by ``startedAt`` DESC.

        ``status_filter`` accepts ``"IN_PROGRESS" | "DONE" | "WALKED"``
        (filters on the denormalized ``phaseGroup`` field) or
        ``"NEEDS_ACTION"`` (filters on the ``needsAction`` boolean).
        ``cursor`` is an opaque token issued by a prior call; pass ``None``
        for the first page. Returns ``(items, next_cursor)``.
        """
        def _op() -> tuple[list[WorkflowStateDoc], str | None]:
            query = self._collection.where("organizationId", "==", organization_id)

            if status_filter == "NEEDS_ACTION":
                query = query.where("needsAction", "==", True)
            elif status_filter in _VALID_PHASE_GROUPS:
                query = query.where("phaseGroup", "==", status_filter)

            query = (
                query
                .order_by("startedAt", direction=firestore.Query.DESCENDING)
                .order_by("__name__", direction=firestore.Query.ASCENDING)
            )

            if cursor:
                decoded = decode_cursor(cursor)
                if decoded and len(decoded) == 2:
                    started_at_iso, doc_id = decoded
                    try:
                        started_at = datetime.fromisoformat(str(started_at_iso))
                    except ValueError:
                        started_at = None
                    if started_at is not None:
                        query = query.start_after({"startedAt": started_at, "__name__": str(doc_id)})

            query = query.limit(limit + 1)

            rows: list[WorkflowStateDoc] = []
            for snap in query.stream():
                body = snapshot_to_model_dict(snap.id, snap.to_dict())
                rows.append(WorkflowStateDoc.model_validate(body))

            has_more = len(rows) > limit
            if has_more:
                rows = rows[:limit]
            next_cursor: str | None = None
            if has_more and rows:
                last = rows[-1]
                next_cursor = encode_cursor([last.started_at.isoformat(), last.id])
            return rows, next_cursor

        return await asyncio.to_thread(_op)

    async def update_fields(self, workflow_id: str, patch: dict[str, Any]) -> None:
        def _op() -> None:
            ref = self._collection.document(workflow_id)
            ref.set(merge_update_dict(patch), merge=True)

        await asyncio.to_thread(_op)
