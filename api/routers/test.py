from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.dependencies import get_current_admin
from api.schemas.common import EchoRequest, EchoResponse, PingResponse
from procu_forge_buyer.a2a_client import call_vendor

router = APIRouter(
    prefix="/test",
    tags=["test"],
    dependencies=[Depends(get_current_admin)],
)
logger = logging.getLogger(__name__)


class WsBroadcastRequest(BaseModel):
    channel: str = Field(description="Raw channel key. Workflow page: <workflow_id>. Vendor page: vt:<rfq_id>.")
    reason: str = Field(default="test_script", description="Logged as the broadcast reason tag.")
    payload: dict[str, Any] = Field(description="Object delivered verbatim as the `data` field of the state_changed envelope.")
    workflow_id: str | None = None
    vendor_thread_id: str | None = None


@router.post(
    "/ws-broadcast",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Debug: schedule a state_changed broadcast on the given channel.",
)
async def ws_broadcast(req: WsBroadcastRequest) -> dict:
    """Push an arbitrary payload to subscribers of ``channel`` as a state_changed event.

    Dev-only helper that bypasses the agent loop and exercises the WS layer
    directly. Subject to the same debounce + hash dedupe as production
    broadcasts, so identical payloads back-to-back will collapse — vary at
    least one field per call (e.g. a nonce) to see every event.
    """
    from api.ws import broadcast_state

    payload = req.payload
    broadcast_state(
        req.channel,
        lambda: payload,
        reason=req.reason,
        workflow_id=req.workflow_id,
        vendor_thread_id=req.vendor_thread_id,
    )
    return {
        "scheduled": True,
        "channel": req.channel,
        "reason": req.reason,
        "workflow_id": req.workflow_id,
        "vendor_thread_id": req.vendor_thread_id,
    }


@router.get(
    "/ping",
    response_model=PingResponse,
    status_code=status.HTTP_200_OK,
    summary="Ping the API",
)
async def ping() -> PingResponse:
    return PingResponse()


@router.post(
    "/echo",
    response_model=EchoResponse,
    status_code=status.HTTP_200_OK,
    summary="Echo a payload back to the caller",
)
async def echo(payload: EchoRequest) -> EchoResponse:
    return EchoResponse(message=payload.message, metadata=payload.metadata)


@router.post(
    "/vendor/trigger",
    status_code=status.HTTP_200_OK,
    summary="Send a raw envelope to vendor A2A",
)
async def trigger_vendor(envelope: dict) -> dict:
    """Proxy one raw envelope to vendor A2A using rfq_id as context.

    Request body is the exact JSON envelope sent as A2A message text.
    """
    context_id = str(envelope.get("rfq_id") or uuid4())
    logger.info(
        "vendor_trigger request context_id=%s message_type=%s rfq_id=%s",
        context_id,
        envelope.get("message_type"),
        envelope.get("rfq_id"),
    )

    try:
        raw_reply = await call_vendor(
            message_json=json.dumps(envelope),
            rfq_id=context_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"vendor A2A call failed: {exc}",
        ) from exc

    parsed_reply: dict | None = None
    if raw_reply:
        try:
            maybe = json.loads(raw_reply)
            if isinstance(maybe, dict):
                parsed_reply = maybe
        except json.JSONDecodeError:
            parsed_reply = None
    else:
        logger.warning("vendor_trigger empty_reply context_id=%s", context_id)

    logger.info(
        "vendor_trigger reply context_id=%s raw_reply=%r parsed=%s",
        context_id,
        raw_reply,
        parsed_reply is not None,
    )

    return {
        "context_id": context_id,
        "vendor_raw_reply": raw_reply,
        "vendor_reply": parsed_reply,
    }
