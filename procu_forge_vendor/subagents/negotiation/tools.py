from __future__ import annotations

from typing import Any, Literal

from google.adk.tools.base_tool import ToolContext

from communication import A2AMessageBuilder
from communication.payload_builder import BUYER_AGENT, VENDOR_AGENT
from procu_forge_vendor.state_keys import (
    COMMUNICATION_KEY,
    LAST_SELLING_PRICE_KEY,
    LATEST_BUYER_PRICE_KEY,
    LATEST_OFFER_PRICE_KEY,
    PRODUCT_KEY,
    RFQ_ID_KEY,
    ROUND_KEY,
    VENDOR_ID_KEY,
)

_MAX_ROUNDS = 3


def get_negotiation_context(tool_context: ToolContext) -> dict[str, Any]:
    """Return pricing context the LLM needs to decide how to respond to the buyer.

    Fetches (or computes and caches) last_selling_price from state.
    Returns all price anchors, the current round, and both sides' latest offers
    so the LLM can make an informed accept / counter / walkaway decision.
    """
    product_state = dict(tool_context.state.get(PRODUCT_KEY) or {})
    listed_unit_price = float(product_state.get("listed_unit_price") or 0)

    if listed_unit_price <= 0:
        return {
            "ok": False,
            "error": "listed_unit_price is 0 in state — ensure the quote agent ran first.",
        }

    last_selling_price = tool_context.state.get(LAST_SELLING_PRICE_KEY)
    if last_selling_price is None:
        last_selling_price = round(listed_unit_price * 0.90, 2)
        tool_context.state[LAST_SELLING_PRICE_KEY] = last_selling_price

    return {
        "ok": True,
        "last_selling_price": last_selling_price,
        "listed_unit_price": listed_unit_price,
        "currency": product_state.get("currency") or "USD",
        "negotiation_round": int(tool_context.state.get(ROUND_KEY) or 0),
        "max_rounds": _MAX_ROUNDS,
        "latest_offer_price": tool_context.state.get(LATEST_OFFER_PRICE_KEY),
        "latest_buyer_price": tool_context.state.get(LATEST_BUYER_PRICE_KEY),
    }


def send_response(
    response_type: Literal["ACCEPT", "COUNTER_RESPONSE", "WALKAWAY"],
    *,
    vendor_unit_price: float | None = None,
    buyer_proposed_price: float | None = None,
    best_and_final: bool = False,
    walkaway_reason: str = "MAX_ROUNDS_REACHED",
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Build the A2A envelope for the response type the LLM has chosen and record it.

    Args:
        response_type: One of "ACCEPT", "COUNTER_RESPONSE", or "WALKAWAY".
        vendor_unit_price: Required for ACCEPT and COUNTER_RESPONSE — the price
            the vendor is offering or agreeing to.
        buyer_proposed_price: The price the buyer proposed this round (records
            in state as latest_buyer_price when provided).
        best_and_final: Mark this counter as the vendor's final offer.
        walkaway_reason: Human-readable reason string for WALKAWAY envelopes.

    Returns the complete A2A envelope dict — return it exactly as your reply.
    """
    vendor_id: str = tool_context.state.get(VENDOR_ID_KEY) or ""
    rfq_id: str = tool_context.state.get(RFQ_ID_KEY) or ""
    product_state: dict[str, Any] = dict(tool_context.state.get(PRODUCT_KEY) or {})

    if not vendor_id:
        return {"ok": False, "error": "vendor_id not found in session state"}
    if not rfq_id:
        return {"ok": False, "error": "rfq_id not found in session state"}

    product_id: str = product_state.get("id") or ""
    if not product_id:
        return {"ok": False, "error": "product.id missing — ensure quote agent ran first"}

    if response_type in ("ACCEPT", "COUNTER_RESPONSE") and vendor_unit_price is None:
        return {"ok": False, "error": f"vendor_unit_price is required for {response_type}"}

    negotiation_round = int(tool_context.state.get(ROUND_KEY) or 0)

    builder = A2AMessageBuilder(
        rfq_id=rfq_id,
        vendor_id=vendor_id,
        product_id=product_id,
        sku=product_state.get("sku") or "",
        quantity=int(product_state.get("quantity") or 1),
        unit=product_state.get("unit") or "",
        currency=product_state.get("currency") or "USD",
        from_agent=VENDOR_AGENT,
        to_agent=BUYER_AGENT,
    )

    if response_type == "ACCEPT":
        envelope = builder.get_accept_payload(
            unit_price=vendor_unit_price,
            negotiation_round=negotiation_round,
        )
    elif response_type == "COUNTER_RESPONSE":
        envelope = builder.get_counter_response_payload(
            unit_price=vendor_unit_price,
            negotiation_round=negotiation_round,
            best_and_final=best_and_final,
        )
    elif response_type == "WALKAWAY":
        latest_offer = tool_context.state.get(LATEST_OFFER_PRICE_KEY)
        envelope = builder.get_walkaway_payload(
            walkaway_reason=walkaway_reason,
            negotiation_round=negotiation_round,
            last_unit_price=latest_offer,
        )
    else:
        return {"ok": False, "error": f"unknown response_type: {response_type!r}"}

    if buyer_proposed_price is not None:
        tool_context.state[LATEST_BUYER_PRICE_KEY] = buyer_proposed_price
    if vendor_unit_price is not None:
        tool_context.state[LATEST_OFFER_PRICE_KEY] = vendor_unit_price

    tool_context.state[ROUND_KEY] = negotiation_round + 1

    comms = list(tool_context.state.get(COMMUNICATION_KEY) or [])
    comms.append(envelope)
    tool_context.state[COMMUNICATION_KEY] = comms

    return envelope
