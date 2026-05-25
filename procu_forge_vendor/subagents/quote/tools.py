from __future__ import annotations

from typing import Any

from google.adk.tools.base_tool import ToolContext

from communication import A2AMessageBuilder
from communication.payload_builder import BUYER_AGENT, VENDOR_AGENT
from db.firestore.client import get_firestore_client
from db.firestore.repositories.vendor_products import VendorProductRepository
from procu_forge_vendor.pricing import quote_valid_until
from procu_forge_vendor.state_keys import (
    PRODUCT_KEY,
    RFQ_ID_KEY,
    VENDOR_ID_KEY,
)


async def quote_product(tool_context: ToolContext) -> dict[str, Any]:
    """Fetch vendor product details from Firestore and return a QUOTE envelope.

    All inputs are read from session state seeded by the incoming RFQ:
      - state["vendor_id"]         -> which vendor to look up
      - state["rfq_id"]            -> envelope thread identifier
      - state["product"]["id"]     -> product to quote
      - state["product"]["quantity"] -> requested units
      - state["product"]["currency"] -> preferred currency (fallback to DB record)

    Returns a complete A2A QUOTE envelope dict, or ``{"ok": False, "error": ...}``.
    The agent must forward this payload verbatim as its response.
    """
    vendor_id: str = tool_context.state.get(VENDOR_ID_KEY) or ""
    rfq_id: str = tool_context.state.get(RFQ_ID_KEY) or ""
    product_state: dict[str, Any] = dict(tool_context.state.get(PRODUCT_KEY) or {})

    if not vendor_id:
        return {"ok": False, "error": "vendor_id not found in session state"}
    if not rfq_id:
        return {"ok": False, "error": "rfq_id not found in session state"}

    product_id: str = product_state.get("id") or ""
    quantity: int = int(product_state.get("quantity") or 1)
    currency: str = product_state.get("currency") or "USD"

    if not product_id:
        return {"ok": False, "error": "product.id not found in session state"}

    repo = VendorProductRepository(get_firestore_client())
    vp = await repo.get_by_product_and_vendor(product_id, vendor_id)

    if vp is None:
        return {
            "ok": False,
            "error": (
                f"No active vendor-product record found: "
                f"product_id={product_id!r} vendor_id={vendor_id!r}"
            ),
        }

    resolved_currency = vp.pricing.currency or currency
    product_state.update(
        {
            "id": product_id,
            "sku": vp.vendor_sku,
            "currency": resolved_currency,
            "unit": vp.unit,
            "listed_unit_price": vp.pricing.unit_price,
            "quantity": quantity,
            "lead_time_days": vp.lead_time_days,
            "availability_status": vp.availability_status,
            "minimum_order_qty": vp.pricing.minimum_order_qty,
        }
    )
    tool_context.state[PRODUCT_KEY] = product_state

    # 5% opening discount off the listed catalog price.
    unit_price = vp.pricing.unit_price * (1 - 0.05)

    builder = A2AMessageBuilder(
        rfq_id=rfq_id,
        vendor_id=vendor_id,
        product_id=product_id,
        sku=vp.vendor_sku,
        quantity=quantity,
        unit=vp.unit,
        currency=resolved_currency,
        from_agent=VENDOR_AGENT,
        to_agent=BUYER_AGENT,
    )

    envelope = builder.get_quote_payload(
        unit_price=unit_price,
        negotiation_round=0,
        response_deadline=quote_valid_until(),
    )

    tool_context.state["temp:response_body"] = envelope
    return envelope
