from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from google.adk.tools.base_tool import ToolContext

from communication import A2AMessageBuilder
from communication.payload_builder import BUYER_AGENT, VENDOR_AGENT
from procu_forge_vendor.state_keys import (
    GRN_KEY,
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


def submit_invoice(tool_context: ToolContext) -> dict[str, Any]:
    """Build and submit an invoice based on the received GRN.

    Joins GRN line items (``sku`` + ``unit_quantity``) against the PO's
    ``line_items`` (``unit_price`` per sku). The PO is the contractual source of
    truth for pricing; the GRN is the source of truth for received quantity.
    Returns ``{"ok": false, ...}`` when a GRN sku is not present in the PO so
    the discrepancy is surfaced rather than invoiced at the wrong price.
    """
    if not tool_context.state.get(VENDOR_ID_KEY):
        return {"ok": False, "error": "vendor_id not found in session state"}

    grn = dict(tool_context.state.get(GRN_KEY) or {})
    if not grn:
        return {"ok": False, "error": "No GRN found in state — ensure a GRN_CREATED message was received"}

    po = dict(tool_context.state.get(PO_KEY) or {})
    if not po:
        return {"ok": False, "error": "No PO found in state — cannot price invoice without PO"}

    po_number = grn.get("po_number") or po.get("po_number") or ""
    if not po_number:
        return {"ok": False, "error": "po_number could not be resolved from GRN or PO state"}

    po_line_index: dict[str, dict[str, Any]] = {}
    for po_item in po.get("line_items") or []:
        sku = (po_item.get("sku") or "").strip()
        if sku:
            po_line_index[sku] = po_item
    if not po_line_index:
        return {"ok": False, "error": "PO has no line_items — cannot price invoice"}

    rfq_id = tool_context.state.get(RFQ_ID_KEY) or "unknown"
    invoice_number = f"INV-{rfq_id}-{uuid.uuid4().hex[:8].upper()}"
    today = date.today()
    invoice_date = today.isoformat()
    due_date = (today + timedelta(days=30)).isoformat()

    line_items: list[dict[str, Any]] = []
    unknown_skus: list[str] = []
    for grn_item in grn.get("line_items") or []:
        sku = (grn_item.get("sku") or "").strip()
        qty = int(grn_item.get("unit_quantity") or 0)
        if not sku or qty <= 0:
            continue
        po_item = po_line_index.get(sku)
        if po_item is None:
            unknown_skus.append(sku)
            continue
        unit_price = float(po_item.get("unit_price") or 0)
        if unit_price <= 0:
            return {
                "ok": False,
                "error": f"PO line item for sku={sku!r} has no unit_price",
            }
        total_price = round(unit_price * qty, 2)
        line_items.append({
            "sku": sku,
            "quantity": qty,
            "unit_price": round(unit_price, 2),
            "total_price": total_price,
        })

    if unknown_skus:
        return {
            "ok": False,
            "error": "GRN contains sku(s) not present in PO",
            "unknown_skus": unknown_skus,
        }

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
    return {
        "ok": True,
        "message_type": envelope.get("message_type"),
        "message_id": envelope.get("message_id"),
    }


__all__ = ["submit_invoice"]
