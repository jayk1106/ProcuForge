"""A2A tools for the buyer's purchase_manager_agent.

Sends PO, GRN_CREATED, and PROCESS_COMPLETE messages to the vendor
and records vendor responses in session state.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, timedelta
from typing import Any

from google.adk.tools.base_tool import ToolContext

from communication import A2AMessageBuilder
from communication.payload_builder import BUYER_AGENT, VENDOR_AGENT
from procu_forge_buyer.a2a_client import call_vendor
from procu_forge_buyer.state_keys import (
    GRN_KEY,
    INVOICE_KEY,
    NEGOTIATION_CONFIG_KEY,
    PO_KEY,
    PROCESS_COMPLETE_KEY,
    SELECTED_VENDOR_KEY,
)

_LOG = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_agreed_price(communications: list[Any]) -> float | None:
    """Walk communications in reverse to find the last ACCEPT envelope's unit_price."""
    for item in reversed(communications):
        env: dict[str, Any] | None = None
        if isinstance(item, dict):
            env = item
        elif isinstance(item, str):
            try:
                parsed = json.loads(item)
                if isinstance(parsed, dict):
                    env = parsed
            except json.JSONDecodeError:
                pass
        if env and env.get("message_type") == "ACCEPT":
            price = env.get("payload", {}).get("unit_price")
            result = _to_float(price)
            if result is not None:
                return result
    return None


def _get_vendor_config(state: dict[str, Any]) -> tuple[str, dict[str, Any]] | str:
    """Return (vendor_id, negotiation_config) or an error string."""
    selected = state.get(SELECTED_VENDOR_KEY)
    if not isinstance(selected, dict):
        return "selected_vendor missing from state"
    vendor_id = str(selected.get("vendor") or "").strip()
    if not vendor_id:
        return "selected_vendor.vendor is empty"

    nego = state.get(NEGOTIATION_CONFIG_KEY) or {}
    config = nego.get(vendor_id)
    if not isinstance(config, dict) or not config.get("rfq_id"):
        return f"no negotiation_config for vendor {vendor_id!r}"
    return vendor_id, config


def _parse_vendor_reply(reply: str) -> dict[str, Any] | None:
    stripped = reply.strip()
    if not stripped.startswith("{"):
        return None
    try:
        result = json.loads(stripped)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None


def _make_builder(config: dict[str, Any], vendor_id: str) -> A2AMessageBuilder:
    product = config.get("product") or {}
    return A2AMessageBuilder(
        rfq_id=config["rfq_id"],
        vendor_id=vendor_id,
        product_id=str(product.get("id") or ""),
        sku=str(product.get("sku") or ""),
        quantity=int(product.get("quantity") or 1),
        unit=str(product.get("unit") or ""),
        currency=str(product.get("currency") or "USD"),
    )


# ── tools ─────────────────────────────────────────────────────────────────────

async def send_po(tool_context: ToolContext) -> dict[str, Any]:
    """Build and send a Purchase Order to the vendor via A2A.

    Reads vendor and product data from negotiation_config and selected_vendor.
    Stores the outbound PO envelope in state["po"].
    Returns the PO envelope and the vendor's PO_ACKNOWLEDGED response.
    """
    result = _get_vendor_config(dict(tool_context.state))
    if isinstance(result, str):
        return {"ok": False, "error": result}
    vendor_id, config = result

    product = config.get("product") or {}
    communications = config.get("communications") or []

    agreed_price = _extract_agreed_price(communications) or _to_float(product.get("price"))
    if agreed_price is None:
        return {"ok": False, "error": "Could not determine agreed price from negotiation_config"}

    quantity = int(product.get("quantity") or 1)
    po_number = f"PO-{uuid.uuid4().hex[:8].upper()}"
    delivery_date = (date.today() + timedelta(days=14)).isoformat()

    line_items = [
        {
            "sku": product.get("sku") or "",
            "product_id": product.get("id") or "",
            "quantity": quantity,
            "unit_price": round(agreed_price, 2),
            "total_price": round(agreed_price * quantity, 2),
        }
    ]
    total_amount = round(agreed_price * quantity, 2)

    builder = _make_builder(config, vendor_id)
    envelope = builder.get_po_payload(
        po_number=po_number,
        rfq_reference=config["rfq_id"],
        line_items=line_items,
        total_amount=total_amount,
        delivery_date=delivery_date,
    )

    _LOG.info(
        "purchase_manager send_po  vendor_id=%s po_number=%s total_amount=%s",
        vendor_id, po_number, total_amount,
    )

    tool_context.state[PO_KEY] = {
        "po_number": po_number,
        "rfq_reference": config["rfq_id"],
        "line_items": line_items,
        "total_amount": total_amount,
        "delivery_date": delivery_date,
        "agreed_price": agreed_price,
        "vendor_id": vendor_id,
    }

    reply = await call_vendor(json.dumps(envelope), config["rfq_id"])
    _LOG.info("purchase_manager po_reply  vendor_id=%s reply_chars=%d", vendor_id, len(reply))

    ack = _parse_vendor_reply(reply)
    return {"ok": True, "po_sent": envelope, "po_acknowledged": ack or reply}


async def send_grn_created(tool_context: ToolContext) -> dict[str, Any]:
    """Send GRN_CREATED to the vendor via A2A and return the INVOICE_SUBMITTED response.

    Reads PO data from state["po"]. Stores the GRN envelope in state["grn"]
    and the vendor's invoice payload in state["invoice"].
    """
    result = _get_vendor_config(dict(tool_context.state))
    if isinstance(result, str):
        return {"ok": False, "error": result}
    vendor_id, config = result

    po = dict(tool_context.state.get(PO_KEY) or {})
    if not po:
        return {"ok": False, "error": "No PO in state — send_po must succeed first"}
    po_number = po.get("po_number") or ""
    if not po_number:
        return {"ok": False, "error": "po_number missing from state['po']"}

    grn_number = f"GRN-{uuid.uuid4().hex[:8].upper()}"
    received_at = f"{date.today().isoformat()}T12:00:00Z"
    grn_line_items = [
        {"sku": item.get("sku") or "", "unit_quantity": item.get("quantity") or 0}
        for item in (po.get("line_items") or [])
    ]

    builder = _make_builder(config, vendor_id)
    envelope = builder.get_grn_created_payload(
        grn_number=grn_number,
        po_number=po_number,
        received_at=received_at,
        line_items=grn_line_items,
    )

    _LOG.info(
        "purchase_manager send_grn  vendor_id=%s grn_number=%s po_number=%s",
        vendor_id, grn_number, po_number,
    )

    tool_context.state[GRN_KEY] = {
        "grn_number": grn_number,
        "po_number": po_number,
        "received_at": received_at,
        "line_items": grn_line_items,
    }

    reply = await call_vendor(json.dumps(envelope), config["rfq_id"])
    _LOG.info("purchase_manager grn_reply  vendor_id=%s reply_chars=%d", vendor_id, len(reply))

    invoice = _parse_vendor_reply(reply)
    if isinstance(invoice, dict):
        tool_context.state[INVOICE_KEY] = invoice.get("payload") or invoice

    return {"ok": True, "grn_sent": envelope, "invoice_received": invoice or reply}


async def send_process_complete(tool_context: ToolContext) -> dict[str, Any]:
    """Send PROCESS_COMPLETE to the vendor to close the procurement thread.

    Reads PO, GRN, and invoice data from state.
    """
    result = _get_vendor_config(dict(tool_context.state))
    if isinstance(result, str):
        return {"ok": False, "error": result}
    vendor_id, config = result

    po = dict(tool_context.state.get(PO_KEY) or {})
    grn = dict(tool_context.state.get(GRN_KEY) or {})
    invoice = dict(tool_context.state.get(INVOICE_KEY) or {})

    po_number = po.get("po_number") or ""
    grn_number = grn.get("grn_number") or ""
    invoice_number = invoice.get("invoice_number") or ""

    if not po_number:
        return {"ok": False, "error": "po_number missing — send_po must succeed first"}
    if not grn_number:
        return {"ok": False, "error": "grn_number missing — send_grn_created must succeed first"}
    if not invoice_number:
        return {"ok": False, "error": "invoice_number missing — invoice not yet received from vendor"}

    builder = _make_builder(config, vendor_id)
    envelope = builder.get_process_complete_payload(
        po_number=po_number,
        grn_number=grn_number,
        invoice_number=invoice_number,
    )

    _LOG.info(
        "purchase_manager send_process_complete  vendor_id=%s po=%s grn=%s inv=%s",
        vendor_id, po_number, grn_number, invoice_number,
    )

    reply = await call_vendor(json.dumps(envelope), config["rfq_id"])
    _LOG.info(
        "purchase_manager process_complete_reply  vendor_id=%s reply_chars=%d",
        vendor_id, len(reply),
    )

    tool_context.state[PROCESS_COMPLETE_KEY] = {
        "po_number": po_number,
        "grn_number": grn_number,
        "invoice_number": invoice_number,
    }

    return {"ok": True, "process_complete_sent": envelope, "vendor_reply": reply}


__all__ = ["send_po", "send_grn_created", "send_process_complete"]
