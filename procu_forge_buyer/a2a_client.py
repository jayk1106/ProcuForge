"""Shared A2A client for buyer-side communication with the vendor agent."""

from __future__ import annotations

import os
from uuid import uuid4

import httpx
from a2a.client import Client as A2AClient
from a2a.client.card_resolver import A2ACardResolver
from a2a.client.client import ClientConfig as A2AClientConfig
from a2a.client.client_factory import ClientFactory as A2AClientFactory
from a2a.types import Message, Part, Role, TaskArtifactUpdateEvent, TextPart
from a2a.types import TransportProtocol as A2ATransport
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH

VENDOR_AGENT_CARD_URL = os.getenv(
    "VENDOR_A2A_AGENT_CARD_URL",
    f"http://127.0.0.1:8001{AGENT_CARD_WELL_KNOWN_PATH}",
)

_httpx_client: httpx.AsyncClient | None = None
_a2a_client: A2AClient | None = None


async def get_a2a_client() -> A2AClient:
    """Lazy-initialise and cache the A2A client for the vendor agent."""
    global _httpx_client, _a2a_client
    if _a2a_client is not None:
        return _a2a_client

    _httpx_client = httpx.AsyncClient(timeout=httpx.Timeout(600.0))
    base_url = VENDOR_AGENT_CARD_URL.rsplit(AGENT_CARD_WELL_KNOWN_PATH, 1)[0]

    card = await A2ACardResolver(
        httpx_client=_httpx_client, base_url=base_url
    ).get_agent_card(relative_card_path=AGENT_CARD_WELL_KNOWN_PATH)

    factory = A2AClientFactory(
        config=A2AClientConfig(
            httpx_client=_httpx_client,
            streaming=False,
            polling=False,
            supported_transports=[A2ATransport.jsonrpc, A2ATransport.http_json],
        )
    )
    _a2a_client = factory.create(card)
    return _a2a_client


async def call_vendor(message_json: str, rfq_id: str) -> str:
    """Send one A2A message to the vendor, using rfq_id as context_id."""
    client = await get_a2a_client()

    a2a_message = Message(
        message_id=str(uuid4()),
        role=Role.user,
        context_id=rfq_id,
        parts=[Part(root=TextPart(text=message_json))],
    )

    last_text = ""
    async for event in client.send_message(request=a2a_message):
        if isinstance(event, tuple):
            task, update = event
            if isinstance(update, TaskArtifactUpdateEvent):
                for part in update.artifact.parts:
                    if hasattr(part, "root") and hasattr(part.root, "text"):
                        last_text = part.root.text
            elif update is None and task and task.status and task.status.message:
                for part in task.status.message.parts:
                    if hasattr(part, "root") and hasattr(part.root, "text"):
                        last_text = part.root.text
        elif isinstance(event, Message):
            for part in event.parts:
                if hasattr(part, "root") and hasattr(part.root, "text"):
                    last_text = part.root.text

    return last_text


__all__ = ["VENDOR_AGENT_CARD_URL", "get_a2a_client", "call_vendor"]
