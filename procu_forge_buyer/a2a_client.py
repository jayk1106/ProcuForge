"""Shared A2A client for buyer-side communication with the vendor agent."""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from uuid import uuid4

import httpx
from a2a.client import Client as A2AClient
from a2a.client.card_resolver import A2ACardResolver
from a2a.client.client import ClientConfig as A2AClientConfig
from a2a.client.client_factory import ClientFactory as A2AClientFactory
from a2a.types import (
    Artifact,
    DataPart,
    Message,
    Part,
    Role,
    Task,
    TaskArtifactUpdateEvent,
    TextPart,
)
from a2a.types import TransportProtocol as A2ATransport
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH

VENDOR_AGENT_CARD_URL = os.getenv(
    "VENDOR_A2A_AGENT_CARD_URL",
    f"http://127.0.0.1:8001{AGENT_CARD_WELL_KNOWN_PATH}",
)

_LOG = logging.getLogger(__name__)

_httpx_client: httpx.AsyncClient | None = None
_a2a_client: A2AClient | None = None

# ADK A2A part metadata keys (see google.adk.a2a.converters.part_converter).
_ADK_METADATA_PREFIX = "adk/"
_FUNCTION_RESPONSE_TYPE = f"{_ADK_METADATA_PREFIX}type"
_FUNCTION_RESPONSE_VALUE = "function_response"


def _is_procurement_envelope(data: Any) -> bool:
    return (
        isinstance(data, dict)
        and "message_type" in data
        and "rfq_id" in data
        and "payload" in data
    )


def _text_from_part(part: Part | object) -> str | None:
    """Extract a text candidate from an A2A Part (TextPart or DataPart)."""
    root = getattr(part, "root", part)

    if isinstance(root, TextPart):
        text = root.text
        return text if isinstance(text, str) and text else None

    if isinstance(root, DataPart):
        metadata = root.metadata or {}
        is_function_response = metadata.get(_FUNCTION_RESPONSE_TYPE) == _FUNCTION_RESPONSE_VALUE
        data = root.data
        if isinstance(data, str) and data:
            return data
        if isinstance(data, dict):
            if _is_procurement_envelope(data):
                return json.dumps(data)
            if is_function_response:
                response = data.get("response")
                if isinstance(response, str) and response:
                    return response
                if isinstance(response, dict):
                    return json.dumps(response)
            return json.dumps(data)
    return None


def _texts_from_parts(parts: list[Part] | None) -> list[str]:
    if not parts:
        return []
    texts: list[str] = []
    for part in parts:
        text = _text_from_part(part)
        if text:
            texts.append(text)
    return texts


def _texts_from_message(message: Message | None) -> list[str]:
    if not message:
        return []
    return _texts_from_parts(message.parts)


def _texts_from_artifact(artifact: Artifact | None) -> list[str]:
    if not artifact:
        return []
    return _texts_from_parts(artifact.parts)


def _texts_from_task(task: Task | None) -> list[str]:
    """Collect text candidates from status.message then artifacts (final artifact last)."""
    if not task:
        return []
    texts: list[str] = []
    if task.status and task.status.message:
        texts.extend(_texts_from_message(task.status.message))
    for artifact in task.artifacts or []:
        texts.extend(_texts_from_artifact(artifact))
    return texts


def _select_envelope(candidates: list[str]) -> str:
    """Return the last valid procurement envelope JSON string, or last non-empty text."""
    last_non_empty = ""
    last_envelope = ""
    for candidate in candidates:
        if not candidate:
            continue
        last_non_empty = candidate
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if _is_procurement_envelope(parsed):
            last_envelope = candidate
    return last_envelope or last_non_empty


def extract_reply_from_task_event(
    task: Task | None,
    update: TaskArtifactUpdateEvent | None = None,
) -> list[str]:
    """Collect reply text candidates from a blocking A2A (task, update) event."""
    candidates: list[str] = []
    if isinstance(update, TaskArtifactUpdateEvent):
        candidates.extend(_texts_from_artifact(update.artifact))
    candidates.extend(_texts_from_task(task))
    return candidates


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

    candidates: list[str] = []
    last_task: Task | None = None
    async for event in client.send_message(request=a2a_message):
        if isinstance(event, tuple):
            task, update = event
            last_task = task
            candidates.extend(extract_reply_from_task_event(task, update))
        elif isinstance(event, Message):
            candidates.extend(_texts_from_message(event))

    reply = _select_envelope(candidates)
    if not reply:
        task_state = (
            last_task.status.state if last_task and last_task.status else None
        )
        artifact_count = len(last_task.artifacts or []) if last_task else 0
        if candidates:
            _LOG.debug("a2a_call_no_envelope  raw_candidates=%d", len(candidates))
        _LOG.warning(
            "a2a_call_empty_reply  rfq_id=%s task_state=%s artifact_count=%s",
            rfq_id,
            task_state,
            artifact_count,
        )
    else:
        _LOG.debug("a2a_call_reply  rfq_id=%s reply_chars=%d", rfq_id, len(reply))

    return reply


__all__ = [
    "VENDOR_AGENT_CARD_URL",
    "call_vendor",
    "extract_reply_from_task_event",
    "get_a2a_client",
    "_select_envelope",
    "_text_from_part",
    "_texts_from_task",
]
