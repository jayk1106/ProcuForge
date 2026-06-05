"""A2A tools for the buyer's purchase_manager_agent.

Sends PO, GRN_CREATED, and PROCESS_COMPLETE messages to the vendor and records
vendor responses in session state only after validated A2A acks. All send tools
are retry-safe: when a previous attempt left a record in state without a vendor
ack, the tool rebuilds the same envelope (reusing the minted po_number /
grn_number) and re-calls the vendor.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import date, timedelta
from typing import Any, Protocol

from google.adk.tools.base_tool import ToolContext

from communication import A2AMessageBuilder
from procu_forge_buyer.a2a_client import call_vendor
from procu_forge_buyer.pr_status import PrStatus
from procu_forge_buyer.purchase_a2a import (
    parse_vendor_envelope,
    validate_invoice_submitted,
    validate_po_acknowledged,
    validate_process_complete_ack,
    vendor_error,
)
from procu_forge_buyer.state_keys import (
    GRN_KEY,
    INVOICE_KEY,
    INVOICE_VENDOR_ACK_KEY,
    NEGOTIATION_CONFIG_KEY,
    PO_KEY,
    PO_VENDOR_ACK_KEY,
    PR_STATUS_KEY,
    PROCESS_COMPLETE_KEY,
    PROCESS_COMPLETE_VENDOR_ACK_KEY,
    REQUEST_KEY,
    RFQ_CLOSED_LOSERS_KEY,
    SELECTED_VENDOR_KEY,
)

_LOG = logging.getLogger(__name__)


def _broadcast_vendor_thread(
    tool_context: ToolContext,
    config: dict[str, Any],
    *,
    reason: str,
) -> None:
    """Fire-and-forget vt:{rfq_id} state push. Swallows all errors."""
    try:
        from api.services.vendor_thread_query import build_vendor_convo
        from api.ws import broadcast_state, vendor_thread_channel

        rfq_id = str(config.get("rfq_id") or "")
        if not rfq_id:
            return
        workflow_id = tool_context.session.id
        broadcast_state(
            vendor_thread_channel(rfq_id),
            lambda rid=rfq_id: build_vendor_convo(rid),
            reason=reason,
            workflow_id=workflow_id,
            vendor_thread_id=rfq_id,
        )
    except Exception:
        _LOG.exception(
            "purchase_manager.broadcast_failed reason=%s rfq_id=%s",
            reason,
            config.get("rfq_id"),
        )


class _StateReader(Protocol):
    """Minimal session-state interface (plain dict or ADK ``State``)."""

    def get(self, key: str, default: Any = None) -> Any: ...


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


def _get_vendor_config(state: _StateReader) -> tuple[str, dict[str, Any]] | str:
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


def _purchase_ack_snapshot(state: _StateReader) -> dict[str, bool]:
    return {
        "po_vendor_ack": bool(state.get(PO_VENDOR_ACK_KEY)),
        "invoice_vendor_ack": bool(state.get(INVOICE_VENDOR_ACK_KEY)),
        "process_complete_vendor_ack": bool(state.get(PROCESS_COMPLETE_VENDOR_ACK_KEY)),
    }


def _selected_vendor_id(state: _StateReader) -> str:
    selected = state.get(SELECTED_VENDOR_KEY)
    if isinstance(selected, dict):
        return str(selected.get("vendor") or "").strip()
    return ""


def _losing_vendor_ids(state: _StateReader) -> list[str]:
    selected_vendor_id = _selected_vendor_id(state)
    if not selected_vendor_id:
        return []
    nego = state.get(NEGOTIATION_CONFIG_KEY) or {}
    if not isinstance(nego, dict):
        return []
    return [vid for vid in nego if vid != selected_vendor_id]


def _rfq_closed_losers(state: _StateReader) -> dict[str, bool]:
    raw = state.get(RFQ_CLOSED_LOSERS_KEY) or {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): bool(v) for k, v in raw.items() if v}


def _all_losing_vendors_notified(state: _StateReader) -> bool:
    losing = _losing_vendor_ids(state)
    if not losing:
        return True
    closed = _rfq_closed_losers(state)
    return all(vid in closed for vid in losing)


def purchase_progress_snapshot(state: _StateReader) -> dict[str, Any]:
    """Serializable snapshot for stall detection and logging."""
    return {
        "pr_status": state.get(PR_STATUS_KEY),
        "acks": _purchase_ack_snapshot(state),
        "rfq_closed_losers": sorted(_rfq_closed_losers(state).keys()),
    }


def _purchase_made_progress(before: dict[str, Any], after: dict[str, Any]) -> bool:
    if before.get("pr_status") != after.get("pr_status"):
        return True
    before_acks = before.get("acks") or {}
    after_acks = after.get("acks") or {}
    if any(after_acks.get(k) and not before_acks.get(k) for k in after_acks):
        return True
    before_closed = set(before.get("rfq_closed_losers") or [])
    after_closed = set(after.get("rfq_closed_losers") or [])
    return len(after_closed) > len(before_closed)


def _build_po_envelope(
    builder: A2AMessageBuilder,
    *,
    po_record: dict[str, Any],
) -> dict[str, Any]:
    """Build a PO envelope from a stored PO record (used for first send + retry)."""
    return builder.get_po_payload(
        po_number=str(po_record["po_number"]),
        rfq_reference=str(po_record["rfq_reference"]),
        line_items=list(po_record.get("line_items") or []),
        total_amount=float(po_record.get("total_amount") or 0.0),
        delivery_date=str(po_record.get("delivery_date") or ""),
    )


def _build_grn_envelope(
    builder: A2AMessageBuilder,
    *,
    grn_record: dict[str, Any],
) -> dict[str, Any]:
    """Build a GRN_CREATED envelope from a stored GRN record (first send + retry)."""
    return builder.get_grn_created_payload(
        grn_number=str(grn_record["grn_number"]),
        po_number=str(grn_record["po_number"]),
        received_at=str(grn_record.get("received_at") or ""),
        line_items=list(grn_record.get("line_items") or []),
    )


# ── tools ─────────────────────────────────────────────────────────────────────

def build_purchase_progress(state: _StateReader) -> dict[str, Any]:
    """Synchronous progress payload — used by the instruction provider and tests."""
    result = _get_vendor_config(state)
    rfq_id = None
    vendor_id = None
    if isinstance(result, tuple):
        vendor_id, config = result
        rfq_id = config.get("rfq_id")

    acks = _purchase_ack_snapshot(state)
    po = state.get(PO_KEY) if isinstance(state.get(PO_KEY), dict) else {}
    grn = state.get(GRN_KEY) if isinstance(state.get(GRN_KEY), dict) else {}
    invoice = state.get(INVOICE_KEY) if isinstance(state.get(INVOICE_KEY), dict) else {}
    losing = _losing_vendor_ids(state)
    closed = _rfq_closed_losers(state)

    return {
        "pr_status": state.get(PR_STATUS_KEY),
        "selected_vendor": (state.get(SELECTED_VENDOR_KEY) or {}).get("vendor")
        if isinstance(state.get(SELECTED_VENDOR_KEY), dict)
        else None,
        "rfq_id": rfq_id,
        "vendor_id": vendor_id,
        "rfq_closed": {
            "losing_vendor_ids": losing,
            "notified_vendor_ids": sorted(closed.keys()),
            "all_notified": _all_losing_vendors_notified(state),
        },
        "steps": {
            "po": {
                "sent": bool(po.get("po_number")),
                "vendor_confirmed": acks["po_vendor_ack"],
                "po_number": po.get("po_number"),
            },
            "grn_to_invoice": {
                "grn_sent": bool(grn.get("grn_number")),
                "vendor_confirmed": acks["invoice_vendor_ack"],
                "grn_number": grn.get("grn_number"),
                "invoice_number": invoice.get("invoice_number"),
            },
            "process_complete": {
                "vendor_confirmed": acks["process_complete_vendor_ack"],
            },
        },
    }


async def send_po(tool_context: ToolContext) -> dict[str, Any]:
    """Notify losing vendors (RFQ_CLOSED) **and** send the PO to the winner.

    The two former tools (``send_rfq_closed_to_losing_vendors`` and ``send_po``)
    are collapsed here so the agent only needs one action to advance from
    ``VENDOR_SELECTED`` through ``PO_ACKNOWLEDGED``.

    Retry-safe: if a PO record exists in state without a vendor ack, the same
    envelope (same ``po_number``) is rebuilt and re-sent. RFQ_CLOSED is
    idempotent per loser (tracked via ``rfq_closed_losers``).
    """
    result = _get_vendor_config(tool_context.state)
    if isinstance(result, str):
        return {"ok": False, "error": result}
    vendor_id, config = result

    rfq_closed_result = await _notify_losing_vendors(tool_context.state)

    if tool_context.state.get(PO_VENDOR_ACK_KEY):
        po = dict(tool_context.state.get(PO_KEY) or {})
        return {
            "ok": True,
            "note": "already_acknowledged",
            "po_number": po.get("po_number"),
            "rfq_closed": rfq_closed_result,
        }

    existing_po = tool_context.state.get(PO_KEY)
    if isinstance(existing_po, dict) and existing_po.get("po_number"):
        po_record = dict(existing_po)
        _LOG.info(
            "purchase_manager send_po retry  vendor_id=%s po_number=%s",
            vendor_id,
            po_record.get("po_number"),
        )
    else:
        product = config.get("product") or {}
        communications = config.get("communications") or []
        selected = dict(tool_context.state.get(SELECTED_VENDOR_KEY) or {})
        agreed_price = (
            _to_float(selected.get("final_price"))
            or _extract_agreed_price(communications)
        )
        if agreed_price is None:
            return {
                "ok": False,
                "error": "agreed_price_unresolved",
                "detail": "selected_vendor.final_price and last ACCEPT envelope both missing",
            }

        quantity = int(product.get("quantity") or 1)
        request = dict(tool_context.state.get(REQUEST_KEY) or {})
        required_by = request.get("required_by_date") or request.get("required_by")
        delivery_date = required_by if required_by else (date.today() + timedelta(days=14)).isoformat()
        po_number = f"PO-{uuid.uuid4().hex[:8].upper()}"
        line_items = [
            {
                "sku": product.get("sku") or "",
                "product_id": product.get("id") or "",
                "quantity": quantity,
                "unit_price": round(agreed_price, 2),
                "total_price": round(agreed_price * quantity, 2),
            }
        ]
        po_record = {
            "po_number": po_number,
            "rfq_reference": config["rfq_id"],
            "line_items": line_items,
            "total_amount": round(agreed_price * quantity, 2),
            "delivery_date": delivery_date,
            "agreed_price": agreed_price,
            "vendor_id": vendor_id,
        }
        # Persist before A2A so retries reuse the same po_number.
        tool_context.state[PO_KEY] = po_record

    builder = _make_builder(config, vendor_id)
    envelope = _build_po_envelope(builder, po_record=po_record)

    _LOG.info(
        "purchase_manager send_po  vendor_id=%s po_number=%s total_amount=%s",
        vendor_id,
        po_record["po_number"],
        po_record.get("total_amount"),
    )

    _LOG.debug("purchase_manager send_po envelope %s", envelope)

    try:
        reply = await call_vendor(json.dumps(envelope), config["rfq_id"])
    except Exception as exc:
        _LOG.exception(
            "purchase_manager send_po a2a_failed  vendor_id=%s rfq_id=%s",
            vendor_id,
            config["rfq_id"],
        )
        return {"ok": False, "error": f"vendor A2A call failed: {exc}"}

    _LOG.debug("purchase_manager send_po reply_chars=%d", len(reply or ""))

    ack_env = parse_vendor_envelope(reply)
    if ack_env is None:
        return {
            "ok": False,
            "error": "vendor reply was not parseable JSON",
            "vendor_reply": reply[:500] if isinstance(reply, str) else reply,
            "po_number": po_record["po_number"],
        }

    validation_err = validate_po_acknowledged(ack_env, expected_po_number=po_record["po_number"])
    if validation_err:
        return {
            "ok": False,
            "error": validation_err,
            "vendor_reply": ack_env,
            "po_number": po_record["po_number"],
        }

    tool_context.state[PO_VENDOR_ACK_KEY] = ack_env
    _broadcast_vendor_thread(tool_context, config, reason="po_sent")
    return {
        "ok": True,
        "po_sent": envelope,
        "po_acknowledged": ack_env,
        "rfq_closed": rfq_closed_result,
    }


async def send_grn_created(tool_context: ToolContext) -> dict[str, Any]:
    """Send GRN_CREATED; persist invoice only after INVOICE_SUBMITTED.

    Retry-safe: GRN record (with minted ``grn_number``) is persisted before the
    A2A call so retries reuse the same identifier. Vendor matches GRN by
    ``po_number`` so the resend is idempotent.
    """
    result = _get_vendor_config(tool_context.state)
    if isinstance(result, str):
        return {"ok": False, "error": result}
    vendor_id, config = result

    if not tool_context.state.get(PO_VENDOR_ACK_KEY):
        return {"ok": False, "error": "PO not vendor-confirmed — send_po must succeed first"}

    if tool_context.state.get(INVOICE_VENDOR_ACK_KEY):
        invoice = dict(tool_context.state.get(INVOICE_KEY) or {})
        return {
            "ok": True,
            "note": "invoice_already_confirmed",
            "invoice_number": invoice.get("invoice_number"),
        }

    po = dict(tool_context.state.get(PO_KEY) or {})
    po_number = po.get("po_number") or ""
    if not po_number:
        return {"ok": False, "error": "po_number missing from state['po']"}

    existing_grn = tool_context.state.get(GRN_KEY)
    if isinstance(existing_grn, dict) and existing_grn.get("grn_number"):
        grn_record = dict(existing_grn)
        _LOG.info(
            "purchase_manager send_grn retry  vendor_id=%s grn_number=%s po_number=%s",
            vendor_id,
            grn_record.get("grn_number"),
            po_number,
        )
    else:
        grn_record = {
            "grn_number": f"GRN-{uuid.uuid4().hex[:8].upper()}",
            "po_number": po_number,
            "received_at": f"{date.today().isoformat()}T12:00:00Z",
            "line_items": [
                {"sku": item.get("sku") or "", "unit_quantity": item.get("quantity") or 0}
                for item in (po.get("line_items") or [])
            ],
        }
        # Persist before A2A so retries reuse the same grn_number.
        tool_context.state[GRN_KEY] = grn_record

    builder = _make_builder(config, vendor_id)
    envelope = _build_grn_envelope(builder, grn_record=grn_record)

    _LOG.info(
        "purchase_manager send_grn  vendor_id=%s grn_number=%s po_number=%s",
        vendor_id,
        grn_record["grn_number"],
        po_number,
    )

    _LOG.debug("purchase_manager send_grn envelope %s", envelope)
    try:
        reply = await call_vendor(json.dumps(envelope), config["rfq_id"])
    except Exception as exc:
        _LOG.exception(
            "purchase_manager send_grn a2a_failed  vendor_id=%s rfq_id=%s",
            vendor_id,
            config["rfq_id"],
        )
        return {"ok": False, "error": f"vendor A2A call failed: {exc}"}

    _LOG.debug("purchase_manager send_grn reply_chars=%d", len(reply or ""))
    inv_env = parse_vendor_envelope(reply)
    if inv_env is None:
        return {
            "ok": False,
            "error": "vendor reply was not parseable JSON — expected INVOICE_SUBMITTED",
            "vendor_reply": reply[:500] if isinstance(reply, str) else reply,
        }

    invoice_payload, validation_err = validate_invoice_submitted(
        inv_env,
        expected_po_number=po_number,
        expected_grn_number=grn_record["grn_number"],
    )
    if validation_err or invoice_payload is None:
        return {
            "ok": False,
            "error": validation_err or "invalid INVOICE_SUBMITTED envelope",
            "vendor_reply": inv_env,
        }

    tool_context.state[INVOICE_KEY] = invoice_payload
    tool_context.state[INVOICE_VENDOR_ACK_KEY] = inv_env
    _broadcast_vendor_thread(tool_context, config, reason="grn_sent")

    return {
        "ok": True,
        "grn_sent": envelope,
        "invoice_received": invoice_payload,
    }


async def send_process_complete(tool_context: ToolContext) -> dict[str, Any]:
    """Send PROCESS_COMPLETE; persist only after vendor ok=true ack.

    No new identifier is minted — references existing po/grn/invoice numbers —
    so this tool is naturally retry-safe.
    """
    result = _get_vendor_config(tool_context.state)
    if isinstance(result, str):
        return {"ok": False, "error": result}
    vendor_id, config = result

    if not tool_context.state.get(INVOICE_VENDOR_ACK_KEY):
        return {"ok": False, "error": "invoice not vendor-confirmed — send_grn_created must succeed first"}

    if tool_context.state.get(PROCESS_COMPLETE_VENDOR_ACK_KEY):
        pc = dict(tool_context.state.get(PROCESS_COMPLETE_KEY) or {})
        return {"ok": True, "note": "already_complete", "process_complete": pc}

    po_number = (tool_context.state.get(PO_KEY) or {}).get("po_number") or ""
    grn_number = (tool_context.state.get(GRN_KEY) or {}).get("grn_number") or ""
    invoice_number = (tool_context.state.get(INVOICE_KEY) or {}).get("invoice_number") or ""

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
        vendor_id,
        po_number,
        grn_number,
        invoice_number,
    )

    try:
        reply = await call_vendor(json.dumps(envelope), config["rfq_id"])
    except Exception as exc:
        _LOG.exception(
            "purchase_manager send_process_complete a2a_failed  vendor_id=%s rfq_id=%s",
            vendor_id,
            config["rfq_id"],
        )
        return {"ok": False, "error": f"vendor A2A call failed: {exc}"}

    pc_env = parse_vendor_envelope(reply)
    if pc_env is None:
        return {
            "ok": False,
            "error": "vendor reply was not parseable JSON",
            "vendor_reply": reply[:500] if isinstance(reply, str) else reply,
        }

    validation_err = validate_process_complete_ack(pc_env)
    if validation_err:
        return {"ok": False, "error": validation_err, "vendor_reply": pc_env}

    tool_context.state[PROCESS_COMPLETE_KEY] = {
        "po_number": po_number,
        "grn_number": grn_number,
        "invoice_number": invoice_number,
    }
    tool_context.state[PROCESS_COMPLETE_VENDOR_ACK_KEY] = pc_env
    _broadcast_vendor_thread(tool_context, config, reason="process_complete")

    return {"ok": True, "process_complete_sent": envelope, "vendor_reply": pc_env}


def _parse_rfq_closed_reply(reply: str) -> tuple[dict[str, Any] | None, str | None]:
    """Return (parsed_ack, error) when a vendor accepted RFQ_CLOSED."""
    parsed = parse_vendor_envelope(reply)
    if parsed is None:
        if not (reply or "").strip():
            return None, "empty vendor reply"
        return None, "vendor reply was not parseable JSON"
    err = vendor_error(parsed)
    if err:
        return None, err
    if parsed.get("ok") is True:
        return parsed, None
    message = str(parsed.get("message") or "")
    if "RFQ_CLOSED" in message.upper():
        return parsed, None
    if parsed.get("message_type") == "RFQ_CLOSED":
        return parsed, None
    return None, "vendor did not acknowledge RFQ_CLOSED"


async def _call_rfq_closed_with_retry(envelope_json: str, rfq_id: str) -> tuple[str, dict[str, Any] | None, str | None]:
    """Call vendor for RFQ_CLOSED; retry once on empty reply."""
    reply = await call_vendor(envelope_json, rfq_id)
    parsed, err = _parse_rfq_closed_reply(reply)
    if parsed is not None or (reply or "").strip():
        return reply, parsed, err
    await asyncio.sleep(0.5)
    reply = await call_vendor(envelope_json, rfq_id)
    parsed, err = _parse_rfq_closed_reply(reply)
    return reply, parsed, err


async def _notify_losing_vendors(state: Any) -> dict[str, Any]:
    """Send RFQ_CLOSED to every losing vendor that hasn't yet been notified.

    Called from inside ``send_po``. Idempotent per vendor: a vendor is marked
    closed when its reply is a successful RFQ_CLOSED ack (full envelope or
    vendor short-circuit ``ok: true``). ``state`` is the live ADK session state.
    """
    selected_vendor_id = _selected_vendor_id(state)
    if not selected_vendor_id:
        return {"ok": False, "error": "selected_vendor missing from state"}

    losing_vendor_ids = _losing_vendor_ids(state)
    if not losing_vendor_ids:
        return {"ok": True, "closed": {}, "note": "no losing vendors to notify"}

    if _all_losing_vendors_notified(state):
        return {
            "ok": True,
            "closed": {},
            "note": "all_losing_vendors_already_notified",
            "notified_vendor_ids": sorted(_rfq_closed_losers(state).keys()),
        }

    nego: dict[str, Any] = dict(state.get(NEGOTIATION_CONFIG_KEY) or {})
    closed_map: dict[str, bool] = dict(_rfq_closed_losers(state))
    results: dict[str, Any] = {}
    pending = [vid for vid in losing_vendor_ids if not closed_map.get(vid)]

    for vendor_id in pending:
        config = nego.get(vendor_id) or {}
        rfq_id = config.get("rfq_id") or ""
        if not rfq_id:
            results[vendor_id] = {"ok": False, "error": "no rfq_id in negotiation_config"}
            continue
        try:
            builder = _make_builder(config, vendor_id)
            envelope = builder.get_rfq_closed_payload(
                outcome="NOT_SELECTED",
                reason="ANOTHER_VENDOR_SELECTED",
            )
            reply, parsed, err = await _call_rfq_closed_with_retry(
                json.dumps(envelope),
                rfq_id,
            )
        except Exception as exc:  # noqa: BLE001
            _LOG.warning(
                "purchase_manager rfq_closed_failed  vendor_id=%s error=%s",
                vendor_id,
                exc,
            )
            results[vendor_id] = {"ok": False, "error": str(exc)}
            continue

        if parsed is None:
            results[vendor_id] = {
                "ok": False,
                "error": err or "RFQ_CLOSED not acknowledged",
                "vendor_reply": reply[:500] if isinstance(reply, str) else reply,
            }
            continue

        closed_map[vendor_id] = True
        state[RFQ_CLOSED_LOSERS_KEY] = closed_map
        results[vendor_id] = {"ok": True, "reply": parsed}
        _LOG.info(
            "purchase_manager rfq_closed_sent  vendor_id=%s rfq_id=%s",
            vendor_id,
            rfq_id,
        )

    for vendor_id in losing_vendor_ids:
        if vendor_id not in results and closed_map.get(vendor_id):
            results[vendor_id] = {"ok": True, "note": "already_closed", "skipped": True}

    all_ok = (
        all(
            isinstance(r, dict) and (r.get("ok") or r.get("skipped"))
            for r in results.values()
        )
        if results
        else True
    )
    return {
        "ok": all_ok,
        "closed": results,
        "notified_vendor_ids": sorted(closed_map.keys()),
        "all_notified": _all_losing_vendors_notified(state),
    }


__all__ = [
    "build_purchase_progress",
    "purchase_progress_snapshot",
    "_purchase_made_progress",
    "_notify_losing_vendors",
    "send_po",
    "send_grn_created",
    "send_process_complete",
    "_get_vendor_config",
    "_all_losing_vendors_notified",
    "_purchase_ack_snapshot",
]
