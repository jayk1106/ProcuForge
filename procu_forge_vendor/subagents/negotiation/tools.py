from __future__ import annotations

import uuid
from typing import Any

from google.adk.tools.base_tool import ToolContext

from communication import A2AMessageBuilder
from communication.payload_builder import BUYER_AGENT, VENDOR_AGENT
from procu_forge_vendor.pricing import quote_valid_until
from procu_forge_vendor.state_keys import (
    COMMUNICATION_KEY,
    PRODUCT_KEY,
    RFQ_ID_KEY,
    ROUND_KEY,
    VENDOR_ID_KEY,
)


def evaluate_counter_offer(
    proposed_unit_price: float,
    *,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Evaluate a buyer counter-offer and return the vendor's pricing decision.

    Reads product details and round from session state. Returns a decision dict
    the LLM should review before calling send_counter_response.

    Args:
        proposed_unit_price: Buyer's offered unit price.

    Returns:
        Decision dict with accepted, counter_offer_unit_price or agreed_unit_price,
        best_and_final, message, and negotiation_round.
    """
    product = tool_context.state.get(PRODUCT_KEY) or {}
    currency = product.get("currency") or "USD"
    product_id = product.get("id") or "UNKNOWN"
    quantity = int(product.get("quantity") or 1)

    catalog_price = float(product.get("listed_unit_price") or 0)
    if catalog_price <= 0:
        return {
            "ok": False,
            "error": (
                "listed_unit_price is 0 in session state — "
                "ensure lookup_product was called on the opening RFQ turn."
            ),
        }

    floor = round(catalog_price * 0.88, 2)
    # Vendor ask defaults to last quoted price; for round 0 that is the opening quote.
    opening_quote_price = round(catalog_price * 0.95, 2)
    negotiation_round = int(tool_context.state.get(ROUND_KEY) or 0)

    if proposed_unit_price >= floor:
        return {
            "ok": True,
            "accepted": True,
            "agreed_unit_price": round(min(proposed_unit_price, opening_quote_price), 2),
            "currency": currency,
            "product_id": product_id,
            "quantity": quantity,
            "negotiation_round": negotiation_round,
            "message": "We can accept your proposal. Please confirm to finalise.",
            "best_and_final": False,
        }

    if negotiation_round >= 2:
        return {
            "ok": True,
            "accepted": False,
            "counter_offer_unit_price": floor,
            "currency": currency,
            "product_id": product_id,
            "quantity": quantity,
            "negotiation_round": negotiation_round,
            "message": "This is our best and final offer on this line item.",
            "best_and_final": True,
        }

    midpoint = round((proposed_unit_price + opening_quote_price) / 2.0, 2)
    counter = max(min(midpoint, opening_quote_price), floor)
    return {
        "ok": True,
        "accepted": False,
        "counter_offer_unit_price": counter,
        "currency": currency,
        "product_id": product_id,
        "quantity": quantity,
        "negotiation_round": negotiation_round,
        "message": "We appreciate the proposal. We can move to the counter shown.",
        "best_and_final": False,
    }


def send_counter_response(
    unit_price: float,
    accepted: bool,
    *,
    best_and_final: bool = False,
    message: str | None = None,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Build a COUNTER_RESPONSE envelope and record it in the communication log.

    Must be called after evaluate_counter_offer with the price the LLM decided to send.

    Args:
        unit_price: The unit price to send in the response.
        accepted: Whether the vendor is accepting the buyer's proposed price.
        best_and_final: Whether this is the vendor's final offer.
        message: Optional explanatory message.

    Returns the complete A2A COUNTER_RESPONSE envelope dict.
    Return this response exactly and completely as your reply.
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
        return {"ok": False, "error": "product.id missing — call evaluate_counter_offer first"}

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

    envelope = builder.get_counter_response_payload(
        unit_price=unit_price,
        negotiation_round=negotiation_round,
        accepted=accepted,
        best_and_final=best_and_final,
        message=message,
    )

    new_round = negotiation_round + 1
    tool_context.state[ROUND_KEY] = new_round

    comms = list(tool_context.state.get(COMMUNICATION_KEY) or [])
    comms.append(envelope)
    tool_context.state[COMMUNICATION_KEY] = comms

    return envelope


def send_accept_confirmation(
    agreed_unit_price: float,
    *,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Issue a vendor confirmation when both sides have agreed on a price.

    Args:
        agreed_unit_price: The final agreed unit price.

    Returns a confirmation payload with vendor_confirmation_id and totals.
    Record this response in the communication log and return it verbatim.
    """
    vendor_id: str = tool_context.state.get(VENDOR_ID_KEY) or ""
    rfq_id: str = tool_context.state.get(RFQ_ID_KEY) or ""
    product_state: dict[str, Any] = dict(tool_context.state.get(PRODUCT_KEY) or {})
    quantity = int(product_state.get("quantity") or 1)
    currency = product_state.get("currency") or "USD"

    confirmation_id = str(uuid.uuid4())
    line_total = round(agreed_unit_price * quantity, 2)

    result = {
        "vendor_confirmation_id": confirmation_id,
        "rfq_id": rfq_id,
        "vendor_id": vendor_id,
        "agreed_unit_price": agreed_unit_price,
        "quantity": quantity,
        "currency": currency,
        "line_total": line_total,
        "status": "confirmed",
        "message": "Offer accepted. Confirmation reference issued.",
    }

    comms = list(tool_context.state.get(COMMUNICATION_KEY) or [])
    comms.append({"type": "ACCEPT_CONFIRMATION", "payload": result})
    tool_context.state[COMMUNICATION_KEY] = comms

    return result
