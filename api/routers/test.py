from __future__ import annotations

import json
import logging
import os
from uuid import uuid4

import httpx
from a2a.client import Client as A2AClient
from a2a.client.card_resolver import A2ACardResolver
from a2a.client.client import ClientConfig as A2AClientConfig
from a2a.client.client_factory import ClientFactory as A2AClientFactory
from a2a.types import Message, Part, Role, TaskArtifactUpdateEvent, TextPart
from a2a.types import TransportProtocol as A2ATransport
from fastapi import APIRouter, HTTPException, status
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH

from api.schemas.common import EchoRequest, EchoResponse, PingResponse

router = APIRouter(prefix="/test", tags=["test"])
logger = logging.getLogger(__name__)

VENDOR_AGENT_CARD_URL = os.getenv(
    "VENDOR_A2A_AGENT_CARD_URL",
    f"http://127.0.0.1:8001{AGENT_CARD_WELL_KNOWN_PATH}",
)

_httpx_client: httpx.AsyncClient | None = None
_a2a_client: A2AClient | None = None


def _extract_part_text(part: object) -> str | None:
    root = getattr(part, "root", None)
    text = getattr(root, "text", None) or getattr(part, "text", None)
    if isinstance(text, str) and text:
        return text
    return None


async def _get_vendor_a2a_client() -> A2AClient:
    """Lazy-init and cache a direct A2A client for the vendor agent."""
    global _httpx_client, _a2a_client
    if _a2a_client is not None:
        return _a2a_client

    _httpx_client = httpx.AsyncClient(timeout=httpx.Timeout(600.0))
    base_url = VENDOR_AGENT_CARD_URL.rsplit(AGENT_CARD_WELL_KNOWN_PATH, 1)[0]
    card = await A2ACardResolver(
        httpx_client=_httpx_client,
        base_url=base_url,
    ).get_agent_card(relative_card_path=AGENT_CARD_WELL_KNOWN_PATH)

    _a2a_client = A2AClientFactory(
        config=A2AClientConfig(
            httpx_client=_httpx_client,
            streaming=False,
            polling=False,
            supported_transports=[A2ATransport.jsonrpc, A2ATransport.http_json],
        )
    ).create(card)
    return _a2a_client


async def _call_vendor(message_json: str, context_id: str) -> str:
    """Send one payload to vendor A2A and return the latest text reply."""
    client = await _get_vendor_a2a_client()
    a2a_message = Message(
        message_id=str(uuid4()),
        role=Role.user,
        context_id=context_id,
        parts=[Part(root=TextPart(text=message_json))],
    )

    last_text = ""
    async for event in client.send_message(request=a2a_message):
        if isinstance(event, tuple):
            task, update = event
            if isinstance(update, TaskArtifactUpdateEvent):
                for part in update.artifact.parts:
                    text = _extract_part_text(part)
                    if text:
                        last_text = text
            elif update is None and task and task.status and task.status.message:
                for part in task.status.message.parts:
                    text = _extract_part_text(part)
                    if text:
                        last_text = text
        elif isinstance(event, Message):
            for part in event.parts:
                text = _extract_part_text(part)
                if text:
                    last_text = text

    return last_text


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
        raw_reply = await _call_vendor(
            message_json=json.dumps(envelope),
            context_id=context_id,
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
