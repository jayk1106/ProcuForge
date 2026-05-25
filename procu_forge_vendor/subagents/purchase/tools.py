from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from google.adk.tools.base_tool import ToolContext

from communication import A2AMessageBuilder
from communication.payload_builder import BUYER_AGENT, VENDOR_AGENT
from procu_forge_vendor.state_keys import (
    GRN_KEY,
    LATEST_OFFER_PRICE_KEY,
    PO_KEY,
    PRODUCT_KEY,
    RFQ_ID_KEY,
    VENDOR_ID_KEY,
)


def _builder(tool_context: ToolContext) -> A2AMessageBuilder:
    product = dict(tool_context.state.get(PRODUCT_KEY) or {})
    return A2AMessageBuilder(
        rfq_id=tool_context.state.get(RFQ_ID_KEY) or "",
        vendor_id=tool_context.state.get(VENDOR_ID_KEY) or "",
        product_id=product.get("id") or "",
        sku=product.get("sku") or "",
        quantity=int(product.get("quantity") or 1),
        unit=product.get("unit") or "",
        currency=product.get("currency") or "USD",
        from_agent=VENDOR_AGENT,
        to_agent=BUYER_AGENT,
    )


def acknowledge_po(tool_context: ToolContext) -> dict[str, Any]:
    """Acknowledge an incoming purchase order.

    Reads the PO payload from state["po"] (set by before_agent_callback when
    the PO message arrived). Builds a slim PO_ACKNOWLEDGED envelope
    (``{ "po_number": ... }``) and writes it to state["temp:response_body"]
    for the after_agent_callback to send.

    Returns the complete PO_ACKNOWLEDGED envelope dict.
    Return it exactly and completely as your reply.
    """
    if not tool_context.state.get(VENDOR_ID_KEY):
        return {"ok": False, "error": "vendor_id not found in session state"}

    po = dict(tool_context.state.get(PO_KEY) or {})
    if not po:
        return {"ok": False, "error": "No PO found in state — ensure a PO message was received"}

    po_number = po.get("po_number") or ""
    if not po_number:
        return {"ok": False, "error": "po_number missing from PO payload"}

    builder = _builder(tool_context)
    envelope = builder.get_po_acknowledged_payload(po_number=po_number)

    tool_context.state["temp:response_body"] = envelope
    return envelope


def submit_invoice(tool_context: ToolContext) -> dict[str, Any]:
    """Build and submit an invoice based on the received GRN.

    Reads GRN payload from state["grn"] and the agreed unit price from
    state["latest_offer_price"]. Generates an invoice number, computes
    line totals from GRN ``unit_quantity`` values, and builds an
    INVOICE_SUBMITTED envelope written to state["temp:response_body"].

    Returns the complete INVOICE_SUBMITTED envelope dict.
    Return it exactly and completely as your reply.
    """
    if not tool_context.state.get(VENDOR_ID_KEY):
        return {"ok": False, "error": "vendor_id not found in session state"}

    grn = dict(tool_context.state.get(GRN_KEY) or {})
    if not grn:
        return {"ok": False, "error": "No GRN found in state — ensure a GRN_CREATED message was received"}

    po = dict(tool_context.state.get(PO_KEY) or {})
    po_number = grn.get("po_number") or po.get("po_number") or ""
    if not po_number:
        return {"ok": False, "error": "po_number could not be resolved from GRN or PO state"}

    agreed_unit_price = tool_context.state.get(LATEST_OFFER_PRICE_KEY)
    if not agreed_unit_price:
        product = dict(tool_context.state.get(PRODUCT_KEY) or {})
        agreed_unit_price = float(product.get("listed_unit_price") or 0)
    if not agreed_unit_price:
        return {"ok": False, "error": "agreed_unit_price not found — negotiation state missing"}

    rfq_id = tool_context.state.get(RFQ_ID_KEY) or "unknown"
    invoice_number = f"INV-{rfq_id}-{uuid.uuid4().hex[:8].upper()}"
    today = date.today()
    invoice_date = today.isoformat()
    due_date = (today + timedelta(days=30)).isoformat()

    line_items: list[dict[str, Any]] = []
    for grn_item in grn.get("line_items") or []:
        qty = int(grn_item.get("unit_quantity") or 0)
        if qty <= 0:
            continue
        total_price = round(agreed_unit_price * qty, 2)
        line_items.append({
            "sku": grn_item.get("sku") or "",
            "quantity": qty,
            "unit_price": round(agreed_unit_price, 2),
            "total_price": total_price,
        })

    if not line_items:
        return {"ok": False, "error": "No line items in GRN — nothing to invoice"}

    total_amount = round(sum(item["total_price"] for item in line_items), 2)

    builder = _builder(tool_context)
    envelope = builder.get_invoice_submitted_payload(
        invoice_number=invoice_number,
        po_number=po_number,
        invoice_date=invoice_date,
        line_items=line_items,
        total_amount=total_amount,
        grn_reference=grn.get("grn_number"),
        due_date=due_date,
    )

    tool_context.state["temp:response_body"] = envelope
    return envelope


__all__ = ["acknowledge_po", "submit_invoice"]
