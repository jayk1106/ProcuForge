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
from a2a.types import Message, Part, Role, TaskArtifactUpdateEvent, TextPart
from a2a.types import TransportProtocol as A2ATransport
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH
from google.adk.tools.base_tool import ToolContext

from communication import A2AMessageBuilder, MessageType
from procu_forge_buyer.state_keys import NEGOTIATION_CONFIG_KEY, VENDOR_OFFERS_KEY

_LOG = logging.getLogger(__name__)

# ── vendor A2A client (lazy-initialised) ─────────────────────────────────────

VENDOR_AGENT_CARD_URL = os.getenv(
    "VENDOR_A2A_AGENT_CARD_URL",
    f"http://127.0.0.1:8001{AGENT_CARD_WELL_KNOWN_PATH}",
)

_httpx_client: httpx.AsyncClient | None = None
_a2a_client: A2AClient | None = None


async def _get_a2a_client() -> A2AClient:
    """Lazy-initialise and cache the A2A client for the vendor agent."""
    global _httpx_client, _a2a_client
    if _a2a_client is not None:
        return _a2a_client

    _httpx_client = httpx.AsyncClient(timeout=httpx.Timeout(600.0))
    parsed = VENDOR_AGENT_CARD_URL
    base_url = parsed.rsplit(AGENT_CARD_WELL_KNOWN_PATH, 1)[0]

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


# ── A2A call ──────────────────────────────────────────────────────────────────

async def _call_vendor(message_json: str, rfq_id: str) -> str:
    """Send one A2A message to the vendor, using rfq_id as context_id.

    The vendor's custom request_converter maps context_id → session_id, so
    every turn of the same negotiation thread reuses the same vendor session.
    """
    client = await _get_a2a_client()

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


# ── logging helpers ───────────────────────────────────────────────────────────

def _comm_tag(entry: Any) -> str:
    if isinstance(entry, dict):
        return (
            f"{entry.get('message_type', '?')}("
            f"r{entry.get('round', '?')}, "
            f"id={str(entry.get('message_id', ''))[:8]})"
        )
    if isinstance(entry, str):
        return f"vendor_text({len(entry)}chars)"
    return repr(entry)[:60]


def _log_before_vendor_call(
    config: dict[str, Any],
    message_type: MessageType,
    negotiation_round: int,
    payload: dict[str, Any],
) -> None:
    comms = config.get("communications") or []
    _LOG.info(
        "a2a_call_start  rfq_id=%s vendor_id=%s round=%d message_type=%s "
        "prior_comms=%d prior=[%s]",
        config.get("rfq_id"),
        config.get("vendor_id"),
        negotiation_round,
        str(message_type),
        len(comms),
        ", ".join(_comm_tag(c) for c in comms),
    )
    _LOG.debug(
        "a2a_payload  rfq_id=%s payload=%s",
        config.get("rfq_id"),
        json.dumps(payload, default=str),
    )


def _log_after_vendor_call(
    config: dict[str, Any],
    negotiation_round: int,
    reply: str,
) -> None:
    _LOG.info(
        "a2a_call_end  rfq_id=%s vendor_id=%s round=%d reply_chars=%d",
        config.get("rfq_id"),
        config.get("vendor_id"),
        negotiation_round,
        len(reply),
    )
    _LOG.debug(
        "a2a_reply  rfq_id=%s reply=%s",
        config.get("rfq_id"),
        reply[:2000],
    )


# ── state / config helpers ────────────────────────────────────────────────────

def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_quantity(value: Any) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _get(d: dict[str, Any], *keys: str) -> Any:
    """Return the first non-None value from ``d`` for any of ``keys``."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def _init_vendor_config(state: dict[str, Any], vendor_id: str) -> dict[str, Any] | str:
    """Build a fresh per-vendor negotiation config from ``vendor_offers``."""
    block = state.get(VENDOR_OFFERS_KEY)
    if not isinstance(block, dict):
        return "vendor_offers is missing or invalid in session state"

    product_id = _get(block, "productId", "product_id")
    offers = block.get("offers")
    if not product_id or not isinstance(offers, list):
        return "vendor_offers.productId or offers is invalid"

    offer = next(
        (
            o
            for o in offers
            if isinstance(o, dict)
            and str(_get(o, "vendorId", "vendor_id") or "").strip() == vendor_id
        ),
        None,
    )
    if offer is None:
        return f"no offer for vendor_id={vendor_id!r}"

    unit_price = _to_float(_get(offer, "unitPrice", "unit_price"))
    if unit_price is None:
        return "offer has no valid unit price"

    request = state.get("request") if isinstance(state.get("request"), dict) else {}

    return {
        "target_price": unit_price,
        "vendor_id": vendor_id,
        "rfq_id": str(uuid4()),
        "round": 0,
        "product": {
            "id": str(product_id),
            "sku": str(_get(offer, "vendorSku", "vendor_sku") or ""),
            "currency": str(offer.get("currency") or ""),
            "unit": str(offer.get("unit") or ""),
            "price": unit_price,
            "quantity": _to_quantity(request.get("quantity")),
        },
        "communications": [],
    }


# ── tool ──────────────────────────────────────────────────────────────────────

async def negotiate_with_vendor(
    communication_data: dict[str, Any],
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Negotiate with a single vendor over A2A.

    Required: ``vendor_id``, ``message_type`` (RFQ | COUNTER_OFFER | ACCEPT | WALKAWAY).
    Conditional: ``price`` for COUNTER_OFFER/ACCEPT, ``walkaway_reason`` for WALKAWAY.
    """
    vendor_id = str(communication_data.get("vendor_id") or "").strip()
    if not vendor_id:
        return {"ok": False, "error": "vendor_id must be a non-empty string"}

    try:
        message_type = MessageType(str(communication_data.get("message_type") or "").strip())
    except ValueError:
        return {
            "ok": False,
            "error": "message_type must be one of RFQ, COUNTER_OFFER, ACCEPT, WALKAWAY",
        }

    price = communication_data.get("price")
    walkaway_reason = communication_data.get("walkaway_reason")

    if message_type == MessageType.WALKAWAY and not (
        isinstance(walkaway_reason, str) and walkaway_reason.strip()
    ):
        return {"ok": False, "error": "walkaway_reason is required for WALKAWAY"}

    if message_type in (MessageType.COUNTER_OFFER, MessageType.ACCEPT) and _to_float(price) is None:
        return {"ok": False, "error": f"numeric price is required for {message_type.value}"}

    state = tool_context.state
    # Copy the top-level negotiation dict so mutations are detected by ADK state.
    nego: dict[str, Any] = dict(state.get(NEGOTIATION_CONFIG_KEY) or {})

    config = nego.get(vendor_id)
    if not isinstance(config, dict) or not config.get("rfq_id"):
        result = _init_vendor_config(state, vendor_id)
        if isinstance(result, str):
            return {"ok": False, "error": result}
        config = result
        nego[vendor_id] = config
        state[NEGOTIATION_CONFIG_KEY] = nego  # write-back so ADK persists the new rfq_id

    round = config.get("round")
    if message_type == MessageType.RFQ:
        if round is not None:
            return {"ok": False, "error": f"RFQ already sent for vendor_id={vendor_id!r}"}
        round = 0
    else:
        if round is None:
            return {"ok": False, "error": "send RFQ before other message types"}
        round = int(round) + 1

    product = config.get("product") or {}
    builder = A2AMessageBuilder(
        rfq_id=config["rfq_id"],
        vendor_id=vendor_id,
        product_id=str(product.get("id") or ""),
        sku=str(product.get("sku") or ""),
        quantity=_to_quantity(product.get("quantity")),
        unit=str(product.get("unit") or ""),
        currency=str(product.get("currency") or ""),
    )

    if message_type == MessageType.RFQ:
        communication_payload = builder.get_rfq_payload(negotiation_round=round)
    elif message_type == MessageType.COUNTER_OFFER:
        communication_payload = builder.get_counter_offer_payload(float(price), round)
    elif message_type == MessageType.ACCEPT:
        communication_payload = builder.get_accept_payload(float(price), round)
    else:
        communication_payload = builder.get_walkaway_payload(
            walkaway_reason, round, last_unit_price=_to_float(price)
        )

    _log_before_vendor_call(config, message_type, round, communication_payload)
    config["communications"].append(communication_payload)

    reply = await _call_vendor(
        message_json=json.dumps(communication_payload),
        rfq_id=config["rfq_id"],
    )

    config["round"] = round
    config["communications"].append(reply)
    nego[vendor_id] = config
    state[NEGOTIATION_CONFIG_KEY] = nego  # write-back so ADK persists updated round + comms

    _log_after_vendor_call(config, round, reply)

    return config
