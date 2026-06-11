from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from google.cloud import firestore

from db.collections.vendor_thread_state import COLLECTION_ID, VendorThreadStateDoc
from db.firestore.pagination import decode_cursor, encode_cursor
from db.firestore.serialization import (
    merge_update_dict,
    model_to_firestore_dict,
    snapshot_to_model_dict,
)


class VendorThreadStateRepository:
    def __init__(self, client: firestore.Client) -> None:
        self._collection = client.collection(COLLECTION_ID)

    async def upsert(self, doc: VendorThreadStateDoc) -> None:
        def _op() -> None:
            ref = self._collection.document(doc.rfq_id)
            snap = ref.get()
            if snap.exists:
                data = model_to_firestore_dict(
                    doc, include_id_in_body=False, timestamps="update"
                )
                data.pop("metadata", None)
                data["stateVersion"] = firestore.Increment(1)
                ref.set(merge_update_dict(data), merge=True)
            else:
                data = model_to_firestore_dict(
                    doc, include_id_in_body=False, timestamps="create"
                )
                data["stateVersion"] = 1
                ref.set(data, merge=False)

        await asyncio.to_thread(_op)

    async def get(self, rfq_id: str) -> VendorThreadStateDoc | None:
        def _op() -> VendorThreadStateDoc | None:
            snap = self._collection.document(rfq_id).get()
            if not snap.exists:
                return None
            body = snapshot_to_model_dict(snap.id, snap.to_dict())
            return VendorThreadStateDoc.model_validate(body)

        return await asyncio.to_thread(_op)

    async def list_by_org(
        self,
        organization_id: str,
        *,
        limit: int = 25,
        cursor: str | None = None,
    ) -> tuple[list[VendorThreadStateDoc], str | None]:
        """Cursor-paginated list ordered by ``updatedAt`` DESC."""
        def _op() -> tuple[list[VendorThreadStateDoc], str | None]:
            query = (
                self._collection
                .where("organizationId", "==", organization_id)
                .order_by("updatedAt", direction=firestore.Query.DESCENDING)
                .order_by("__name__", direction=firestore.Query.ASCENDING)
            )

            if cursor:
                decoded = decode_cursor(cursor)
                if decoded and len(decoded) == 2:
                    updated_at_iso, doc_id = decoded
                    try:
                        updated_at = datetime.fromisoformat(str(updated_at_iso))
                    except ValueError:
                        updated_at = None
                    if updated_at is not None:
                        query = query.start_after({"updatedAt": updated_at, "__name__": str(doc_id)})

            query = query.limit(limit + 1)

            rows: list[VendorThreadStateDoc] = []
            for snap in query.stream():
                body = snapshot_to_model_dict(snap.id, snap.to_dict())
                rows.append(VendorThreadStateDoc.model_validate(body))

            has_more = len(rows) > limit
            if has_more:
                rows = rows[:limit]
            next_cursor: str | None = None
            if has_more and rows:
                last = rows[-1]
                next_cursor = encode_cursor([last.updated_at.isoformat(), last.id])
            return rows, next_cursor

        return await asyncio.to_thread(_op)

    async def list_by_workflow(self, workflow_id: str) -> list[VendorThreadStateDoc]:
        def _op() -> list[VendorThreadStateDoc]:
            query = self._collection.where("workflowId", "==", workflow_id)
            rows: list[VendorThreadStateDoc] = []
            for snap in query.stream():
                body = snapshot_to_model_dict(snap.id, snap.to_dict())
                rows.append(VendorThreadStateDoc.model_validate(body))
            rows.sort(key=lambda d: d.created_at)
            return rows

        return await asyncio.to_thread(_op)

    async def update_fields(self, rfq_id: str, patch: dict[str, Any]) -> None:
        def _op() -> None:
            ref = self._collection.document(rfq_id)
            ref.set(merge_update_dict(patch), merge=True)

        await asyncio.to_thread(_op)
