from __future__ import annotations

import uuid
from typing import Any

from procu_forge_vendor.pricing import quoted_unit_price


def respond_to_counter_offer(
    product_id: str,
    proposed_unit_price: float,
    quantity: int,
    currency: str = "USD",
    *,
    current_vendor_ask: float | None = None,
    negotiation_round: int = 0,
) -> dict[str, Any]:
    """Respond to a buyer counter-offer with accept, counter, or best-and-final.

    Args:
        product_id: Product id (must match RFQ).
        proposed_unit_price: Buyer's offered unit price.
        quantity: Units on the line.
        currency: Currency code.
        current_vendor_ask: Vendor's current asking unit price; defaults to initial quote.
        negotiation_round: 0 = first counter from buyer after quote, then increment.

    Returns:
        Status dict with accepted flag, counter_offer_unit_price if any, and message.
    """
    initial = quoted_unit_price(product_id, quantity)
    floor = round(initial * 0.88, 2)
    vendor_ask = current_vendor_ask if current_vendor_ask is not None else initial

    if proposed_unit_price >= floor:
        return {
            "accepted": True,
            "agreed_unit_price": round(min(proposed_unit_price, vendor_ask), 2),
            "currency": currency,
            "product_id": product_id,
            "quantity": quantity,
            "message": (
                "We can accept your proposal at this level. "
                "Please confirm so we can finalize."
            ),
            "best_and_final": False,
        }

    # After two negotiation rounds from buyer, hold best and final at floor
    if negotiation_round >= 2:
        return {
            "accepted": False,
            "counter_offer_unit_price": floor,
            "currency": currency,
            "product_id": product_id,
            "quantity": quantity,
            "message": (
                "This is our best and final offer on this line item based on current margins."
            ),
            "best_and_final": True,
        }

    midpoint = round((proposed_unit_price + vendor_ask) / 2.0, 2)
    counter = max(midpoint, floor)
    counter = min(counter, vendor_ask)

    return {
        "accepted": False,
        "counter_offer_unit_price": counter,
        "currency": currency,
        "product_id": product_id,
        "quantity": quantity,
        "message": (
            "We appreciate the proposal. We can move to the counter-offer shown."
        ),
        "best_and_final": False,
    }


def accept_offer(quote_id: str, agreed_unit_price: float, quantity: int) -> dict[str, Any]:
    """Confirm acceptance and emit a synthetic order/reference id.

    Args:
        quote_id: Quote identifier from generate_quote.
        agreed_unit_price: Final agreed unit price.
        quantity: Final quantity.

    Returns:
        Confirmation payload with vendor_confirmation_id and totals.
    """
    confirmation_id = str(uuid.uuid4())
    line_total = round(agreed_unit_price * quantity, 2)
    return {
        "vendor_confirmation_id": confirmation_id,
        "quote_id": quote_id,
        "agreed_unit_price": agreed_unit_price,
        "quantity": quantity,
        "line_total": line_total,
        "status": "confirmed_mock",
        "message": "Offer accepted. Confirmation reference issued.",
    }
