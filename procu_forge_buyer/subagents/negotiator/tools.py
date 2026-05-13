from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH, RemoteA2aAgent
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.base_tool import ToolContext

from procu_forge_buyer.schema import MessageType
from procu_forge_buyer.state_keys import NEGOTIATION_CONFIG_KEY, VENDOR_OFFERS_KEY

VENDOR_AGENT_CARD_URL = os.getenv(
    "VENDOR_A2A_AGENT_CARD_URL",
    f"http://127.0.0.1:8001/a2a/procu_forge_vendor{AGENT_CARD_WELL_KNOWN_PATH}",
)

vendor_remote_agent = RemoteA2aAgent(
    name="procu_forge_vendor",
    description="External vendor agent reachable over A2A; issues quotes and negotiates.",
    agent_card=VENDOR_AGENT_CARD_URL,
)

vendor_remote_agent_tool = AgentTool(agent=vendor_remote_agent)


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
    """Build a fresh per-vendor negotiation config from ``vendor_offers``.

    Returns the config dict on success or an error message string on failure.
    """
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


def _build_item(
    product: dict[str, Any],
    *,
    price: Any,
    walkaway_reason: Any,
    message_type: MessageType,
) -> dict[str, Any]:
    quantity = _to_quantity(product.get("quantity"))
    unit_price = _to_float(price)

    item: dict[str, Any] = {
        "product_id": str(product.get("id") or ""),
        "sku": str(product.get("sku") or ""),
        "quantity": quantity,
        "unit": str(product.get("unit") or ""),
        "currency": str(product.get("currency") or ""),
        "reason": None,
    }

    if message_type == MessageType.WALKAWAY:
        if unit_price is not None:
            item["last_unit_price"] = unit_price
            item["last_total_price"] = unit_price * quantity
        item["reason"] = (
            walkaway_reason.strip()
            if isinstance(walkaway_reason, str)
            else walkaway_reason
        )
    elif message_type in (MessageType.COUNTER_OFFER, MessageType.ACCEPT):
        if unit_price is not None:
            item["unit_price"] = unit_price
            item["total_price"] = unit_price * quantity

    return item


def _build_communication_payload(
    *,
    rfq_id: str,
    vendor_id: str,
    message_type: MessageType,
    round: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "message_id": str(uuid4()),
        "rfq_id": rfq_id,
        "vendor_id": vendor_id,
        "from_agent": "buyer_negotiator",
        "to_agent": "vendor",
        "message_type": str(message_type),
        "round": round,
        "timestamp": datetime.now().isoformat(),
        "payload": payload,
    }


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
    if not isinstance(state.get(NEGOTIATION_CONFIG_KEY), dict):
        state[NEGOTIATION_CONFIG_KEY] = {}
    nego = state[NEGOTIATION_CONFIG_KEY]

    config = nego.get(vendor_id)
    if not isinstance(config, dict) or not config.get("rfq_id"):
        result = _init_vendor_config(state, vendor_id)
        if isinstance(result, str):
            return {"ok": False, "error": result}
        config = result
        nego[vendor_id] = config

    round = config.get("round")
    if message_type == MessageType.RFQ:
        if round is not None:
            return {"ok": False, "error": f"RFQ already sent for vendor_id={vendor_id!r}"}
        round = 0
    else:
        if round is None:
            return {"ok": False, "error": "send RFQ before other message types"}
        round = int(round) + 1

    now = datetime.now(timezone.utc)
    communication_payload = _build_communication_payload(
        rfq_id=config["rfq_id"],
        vendor_id=vendor_id,
        message_type=message_type,
        round=round,
        payload={
            "item": _build_item(
                config.get("product") or {},
                price=price,
                walkaway_reason=walkaway_reason,
                message_type=message_type,
            ),
            "required_by": (now + timedelta(days=10)).date().isoformat(),
            "response_deadline": (now + timedelta(days=1))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        },
    )

    print("sending payload", communication_payload)
    config["communications"].append(communication_payload)

    reply = await vendor_remote_agent_tool.run_async(
        args={"request": json.dumps(communication_payload)},
        tool_context=tool_context,
    )

    config["round"] = round
    config["communications"].append(reply)
    nego[vendor_id] = config

    print("reply", vendor_id, config["rfq_id"], round, reply)

    return config
