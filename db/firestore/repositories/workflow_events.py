from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime

from google.api_core import exceptions as gcp_exceptions
from google.cloud import firestore

logger = logging.getLogger(__name__)

from db.collections.workflow_event import COLLECTION_ID, WorkflowEventDoc
from db.firestore.serialization import (
    model_to_firestore_dict,
    snapshot_to_model_dict,
)


class WorkflowEventsRepository:
    """Append-only event log for the buyer + vendor agent runtimes.

    Layout: ``workflow_events/{workflow_id}/events/{event_id}``.
    """

    def __init__(self, client: firestore.Client) -> None:
        self._client = client
        self._root = client.collection(COLLECTION_ID)

    def _events_ref(self, workflow_id: str) -> firestore.CollectionReference:
        return self._root.document(workflow_id).collection("events")

    async def append(self, doc: WorkflowEventDoc) -> None:
        def _op() -> None:
            event_id = doc.id or uuid.uuid4().hex
            ref = self._events_ref(doc.workflow_id).document(event_id)
            body = model_to_firestore_dict(
                doc.model_copy(update={"id": event_id}),
                include_id_in_body=False,
                timestamps="create",
            )
            ref.set(body, merge=False)

        await asyncio.to_thread(_op)

    async def list_for_workflow(
        self,
        workflow_id: str,
        *,
        after_ts: datetime | None = None,
        limit: int = 500,
    ) -> list[WorkflowEventDoc]:
        def _op() -> list[WorkflowEventDoc]:
            query: firestore.Query = self._events_ref(workflow_id).order_by("ts")
            if after_ts is not None:
                query = query.where("ts", ">", after_ts)
            query = query.limit(limit)
            rows: list[WorkflowEventDoc] = []
            for snap in query.stream():
                body = snapshot_to_model_dict(snap.id, snap.to_dict())
                rows.append(WorkflowEventDoc.model_validate(body))
            return rows

        return await asyncio.to_thread(_op)

    async def list_for_vendor_thread(
        self,
        workflow_id: str,
        vendor_thread_id: str,
        *,
        after_ts: datetime | None = None,
        limit: int = 500,
    ) -> list[WorkflowEventDoc]:
        try:
            return await self._list_for_vendor_thread_indexed(
                workflow_id,
                vendor_thread_id,
                after_ts=after_ts,
                limit=limit,
            )
        except gcp_exceptions.FailedPrecondition as exc:
            # Composite index (vendorThreadId + ts) may not exist yet; same pattern
            # as workflow detail, which loads all workflow events then filters.
            logger.warning(
                "workflow_events.index_missing workflow_id=%s vendor_thread_id=%s: %s",
                workflow_id,
                vendor_thread_id,
                exc,
            )
            rows = await self.list_for_workflow(
                workflow_id,
                after_ts=after_ts,
                limit=limit,
            )
            return [r for r in rows if r.vendor_thread_id == vendor_thread_id][:limit]

    async def _list_for_vendor_thread_indexed(
        self,
        workflow_id: str,
        vendor_thread_id: str,
        *,
        after_ts: datetime | None = None,
        limit: int = 500,
    ) -> list[WorkflowEventDoc]:
        def _op() -> list[WorkflowEventDoc]:
            query: firestore.Query = (
                self._events_ref(workflow_id)
                .where("vendorThreadId", "==", vendor_thread_id)
                .order_by("ts")
            )
            if after_ts is not None:
                query = query.where("ts", ">", after_ts)
            query = query.limit(limit)
            rows: list[WorkflowEventDoc] = []
            for snap in query.stream():
                body = snapshot_to_model_dict(snap.id, snap.to_dict())
                rows.append(WorkflowEventDoc.model_validate(body))
            return rows

        return await asyncio.to_thread(_op)
