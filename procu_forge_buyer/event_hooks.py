"""Side-effects emitted by the buyer agent into the FastAPI event/WS layer.

These helpers are fire-and-forget: failures are logged but never propagate
back into the agent loop, so a transient Firestore outage cannot break
negotiation. The functions are safe to call from async tool code.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from procu_forge_buyer.state_keys import REQUEST_KEY

logger = logging.getLogger(__name__)


def _organization_id_from_state(state: dict) -> str:
    request = state.get(REQUEST_KEY)
    if not isinstance(request, dict):
        return ""
    return str(request.get("organization_id") or request.get("organizationId") or "")


async def record_vendor_thread_initiated(
    *,
    workflow_id: str,
    rfq_id: str,
    vendor_id: str,
    state: dict,
) -> None:
    """Upsert the rfq_index entry and publish a 'vendor_thread_initiated' event."""
    if not workflow_id or not rfq_id or not vendor_id:
        return

    organization_id = _organization_id_from_state(state)

    try:
        from db.collections.rfq_index import RfqIndexEntry
        from db.firestore.client import get_firestore_client
        from db.firestore.repositories.rfq_index import RfqIndexRepository

        repo = RfqIndexRepository(get_firestore_client())
        entry = RfqIndexEntry(
            id=rfq_id,
            rfqId=rfq_id,
            workflowId=workflow_id,
            vendorId=vendor_id,
            organizationId=organization_id,
            createdAt=datetime.now(timezone.utc),
        )
        await repo.upsert(entry)
    except Exception:
        logger.exception(
            "buyer.event_hooks.rfq_index_upsert_failed workflow_id=%s rfq_id=%s",
            workflow_id,
            rfq_id,
        )

    try:
        from api.services.vendor_thread_query import build_vendor_convo
        from api.ws import broadcast_state, record_event, vendor_thread_channel

        record_event(
            workflow_id,
            "vendor_thread_initiated",
            {"vendor_id": vendor_id, "rfq_id": rfq_id},
            vendor_thread_id=rfq_id,
            author="buyer",
        )
        broadcast_state(
            vendor_thread_channel(rfq_id),
            lambda: build_vendor_convo(rfq_id),
            reason="thread_initiated",
            workflow_id=workflow_id,
            vendor_thread_id=rfq_id,
        )
    except Exception:
        logger.exception(
            "buyer.event_hooks.publish_failed workflow_id=%s rfq_id=%s",
            workflow_id,
            rfq_id,
        )


def publish_vendor_message(
    *,
    workflow_id: str,
    rfq_id: str,
    vendor_id: str,
    direction: str,
    message_type: str,
    round_num: int | None,
    payload: dict | None = None,
) -> None:
    """Publish an A2A message event (buyer↔vendor) without raising on failure.

    ``direction`` is one of ``"outbound"`` (buyer→vendor) or ``"inbound"``
    (vendor→buyer).
    """
    if not workflow_id or not rfq_id:
        return
    try:
        from api.ws import record_event

        record_event(
            workflow_id,
            f"vendor_message_{direction}",
            {
                "vendor_id": vendor_id,
                "rfq_id": rfq_id,
                "message_type": message_type,
                "round": round_num,
                "payload": payload or {},
            },
            vendor_thread_id=rfq_id,
            author="buyer",
        )
    except Exception:
        logger.exception(
            "buyer.event_hooks.publish_message_failed workflow_id=%s rfq_id=%s",
            workflow_id,
            rfq_id,
        )
