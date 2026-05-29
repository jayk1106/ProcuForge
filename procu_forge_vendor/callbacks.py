"""Lifecycle callbacks for procu_forge_vendor."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from communication.schema import MessageType

from .communication_status import VendorThreadStatus, get_status, set_status
from .state_keys import (
    ACCEPTED_PRICE_KEY,
    COMMUNICATION_KEY,
    GRN_KEY,
    LATEST_OFFER_PRICE_KEY,
    PO_KEY,
    PRODUCT_KEY,
    RFQ_ID_KEY,
    ROUND_KEY,
    SEEN_MESSAGE_IDS_CAP,
    SEEN_MESSAGE_IDS_KEY,
    VENDOR_ID_KEY,
)


logger = logging.getLogger(__name__)

_PRICE_EPSILON = 0.01

# Message types that carry a payload.response_deadline (per
# docs/buyer_vendor_communication_reference.md).
_DEADLINE_BEARING_TYPES: set[str] = {
    str(MessageType.RFQ),
    str(MessageType.COUNTER_OFFER),
    str(MessageType.ACCEPT),
    str(MessageType.WALKAWAY),
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_envelope(text: str) -> dict[str, Any] | None:
    try:
        msg = json.loads(text)
        return msg if isinstance(msg, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _event_tag(event: Any) -> str:
    text = ""
    if event.content and event.content.parts:
        for part in event.content.parts:
            if part.text:
                text = part.text
                break
    env = _parse_envelope(text)
    if env:
        return (
            f"{event.author}/"
            f"{env.get('message_type', '?')}"
            f"(r{env.get('round', '?')})"
        )
    snippet = text[:60].replace("\n", " ")
    return f"{event.author}/{snippet!r}" if snippet else f"{event.author}/-"


def _state_summary(state: dict[str, Any]) -> str:
    product = state.get(PRODUCT_KEY) or {}
    comms = state.get(COMMUNICATION_KEY) or []
    return (
        f"vendor_id={state.get(VENDOR_ID_KEY)!r} "
        f"rfq_id={state.get(RFQ_ID_KEY)!r} "
        f"round={state.get(ROUND_KEY)!r} "
        f"product_id={product.get('id')!r} "
        f"product_price={product.get('price')!r} "
        f"comms={len(comms)}"
    )


def _initial_state_from_rfq(envelope: dict[str, Any]) -> dict[str, Any]:
    """Build the canonical vendor state skeleton from an incoming RFQ envelope.

    Only called when ``message_type == "RFQ"``. Currency and listed price are
    populated later by the quote agent from the vendor-product record.
    """
    payload: dict[str, Any] = envelope.get("payload") or {}
    item: dict[str, Any] = payload.get("item") or {}
    return {
        VENDOR_ID_KEY: envelope.get("vendor_id", ""),
        RFQ_ID_KEY: envelope.get("rfq_id", ""),
        ROUND_KEY: 0,
        PRODUCT_KEY: {
            "id": item.get("product_id") or item.get("id", ""),
            "sku": item.get("sku", ""),
            "unit": item.get("unit", "unit"),
            "quantity": int(item.get("quantity") or 1),
        },
        COMMUNICATION_KEY: [envelope],
    }


def _ack_reply(text: str) -> types.Content:
    return types.Content(role="model", parts=[types.Part(text=text)])


def _deadline_violation(deadline_raw: Any) -> dict[str, Any] | None:
    """Return an error dict when ``deadline_raw`` is in the past, else ``None``.

    Accepts ISO-8601 strings, including the trailing ``Z`` form. Silently
    ignores malformed values (treats them as no deadline) so a broken
    timestamp never wedges the thread.
    """
    if not isinstance(deadline_raw, str) or not deadline_raw:
        return None
    iso = deadline_raw.replace("Z", "+00:00")
    try:
        deadline = datetime.fromisoformat(iso)
    except ValueError:
        logger.warning("vendor_deadline_unparseable  raw=%r", deadline_raw)
        return None
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if now <= deadline:
        return None
    return {
        "ok": False,
        "error": "response_deadline_exceeded",
        "deadline": deadline_raw,
        "now": now.isoformat().replace("+00:00", "Z"),
    }


def _record_message_id(state: Any, message_id: str | None) -> bool:
    """Append ``message_id`` to the bounded seen-list.

    Returns ``True`` when the id is fresh, ``False`` when it was already
    seen (duplicate). Missing / empty ids are always treated as fresh
    (envelope dedup is best-effort).
    """
    if not message_id:
        return True
    seen = list(state.get(SEEN_MESSAGE_IDS_KEY) or [])
    if message_id in seen:
        return False
    seen.append(message_id)
    if len(seen) > SEEN_MESSAGE_IDS_CAP:
        seen = seen[-SEEN_MESSAGE_IDS_CAP:]
    state[SEEN_MESSAGE_IDS_KEY] = seen
    return True


def _validate_po(payload: dict[str, Any], state: Any) -> dict[str, Any] | None:
    """Verify an inbound PO matches the negotiated state.

    Returns an error dict to ack with when validation fails, or ``None``
    when the PO is good to persist.
    """
    details: list[str] = []

    rfq_reference = payload.get("rfq_reference")
    expected_rfq = state.get(RFQ_ID_KEY)
    if expected_rfq and rfq_reference != expected_rfq:
        details.append(
            f"rfq_reference={rfq_reference!r} does not match rfq_id={expected_rfq!r}"
        )

    product = state.get(PRODUCT_KEY) or {}
    expected_product_id = product.get("id")
    expected_sku = product.get("sku")
    expected_currency = product.get("currency")

    currency = payload.get("currency")
    if expected_currency and currency and currency != expected_currency:
        details.append(
            f"currency={currency!r} does not match negotiated currency={expected_currency!r}"
        )

    accepted_price = state.get(ACCEPTED_PRICE_KEY)
    if accepted_price is None:
        accepted_price = state.get(LATEST_OFFER_PRICE_KEY)

    line_items = payload.get("line_items") or []
    if not isinstance(line_items, list) or not line_items:
        details.append("line_items missing or empty")
    else:
        line_total_sum = 0.0
        for idx, item in enumerate(line_items):
            if not isinstance(item, dict):
                details.append(f"line_items[{idx}] is not an object")
                continue
            sku = item.get("sku")
            product_id = item.get("product_id")
            if expected_sku and sku and sku != expected_sku:
                details.append(
                    f"line_items[{idx}].sku={sku!r} does not match negotiated sku={expected_sku!r}"
                )
            if (
                expected_product_id
                and product_id
                and product_id != expected_product_id
            ):
                details.append(
                    f"line_items[{idx}].product_id={product_id!r} does not match "
                    f"negotiated product_id={expected_product_id!r}"
                )
            try:
                unit_price = float(item.get("unit_price") or 0)
                total_price = float(item.get("total_price") or 0)
            except (TypeError, ValueError):
                details.append(f"line_items[{idx}] has non-numeric prices")
                continue
            if accepted_price is not None and unit_price > 0:
                if abs(unit_price - float(accepted_price)) > _PRICE_EPSILON:
                    details.append(
                        f"line_items[{idx}].unit_price={unit_price} does not match "
                        f"agreed price={accepted_price}"
                    )
            line_total_sum += total_price

        try:
            total_amount = float(payload.get("total_amount") or 0)
        except (TypeError, ValueError):
            details.append("total_amount is non-numeric")
            total_amount = 0.0
        if abs(total_amount - line_total_sum) > _PRICE_EPSILON:
            details.append(
                f"total_amount={total_amount} does not equal sum(line_items.total_price)={round(line_total_sum, 2)}"
            )

    if not details:
        return None
    logger.warning("vendor_po_validation_failed  details=%s", details)
    return {
        "ok": False,
        "error": "po_validation_failed",
        "details": details,
    }


def _validate_grn(payload: dict[str, Any], state: Any) -> dict[str, Any] | None:
    """Verify an inbound GRN matches the prior PO.

    Returns an error dict when validation fails, or ``None`` when the GRN
    is good to persist.
    """
    details: list[str] = []

    po = state.get(PO_KEY) or {}
    expected_po_number = po.get("po_number")
    po_number = payload.get("po_number")
    if expected_po_number and po_number != expected_po_number:
        details.append(
            f"po_number={po_number!r} does not match prior PO po_number={expected_po_number!r}"
        )

    po_skus = {
        (item.get("sku") or "").strip()
        for item in (po.get("line_items") or [])
        if isinstance(item, dict)
    }
    po_skus.discard("")

    line_items = payload.get("line_items") or []
    if not isinstance(line_items, list) or not line_items:
        details.append("line_items missing or empty")
    else:
        for idx, item in enumerate(line_items):
            if not isinstance(item, dict):
                details.append(f"line_items[{idx}] is not an object")
                continue
            sku = (item.get("sku") or "").strip()
            if not sku:
                details.append(f"line_items[{idx}].sku missing")
                continue
            if po_skus and sku not in po_skus:
                details.append(
                    f"line_items[{idx}].sku={sku!r} not present in PO line_items"
                )

    if not details:
        return None
    logger.warning("vendor_grn_validation_failed  details=%s", details)
    return {
        "ok": False,
        "error": "grn_validation_failed",
        "details": details,
    }


# ── callback ──────────────────────────────────────────────────────────────────

def before_agent_callback(callback_context: CallbackContext) -> types.Content | None:
    """Validate the inbound envelope, advance status, and short-circuit
    no-response message types (RFQ_CLOSED, buyer WALKAWAY, PROCESS_COMPLETE)
    before any subagent dispatch.
    """
    req_type = callback_context.state.get("type")
    if req_type == "error":
        return _ack_reply(
            callback_context.state.get("message") or "Validation failed"
        )

    body = callback_context.state.get("temp:request_body")
    if not body:
        return _ack_reply("No request body found in state.")

    # Clear any stale outbound envelope from a previous turn so subagent
    # after-callbacks never re-emit it on a turn where the LLM stayed silent.
    callback_context.state["temp:response_body"] = None

    # Idempotency: drop duplicate envelopes (same message_id seen recently).
    message_id = body.get("message_id")
    if not _record_message_id(callback_context.state, message_id):
        logger.info("vendor_duplicate_message_dropped  message_id=%s", message_id)
        return _ack_reply(
            json.dumps(
                {
                    "ok": True,
                    "duplicate": True,
                    "message_id": message_id,
                }
            )
        )

    message_type = body.get("message_type")
    payload = body.get("payload") or {}

    if message_type in _DEADLINE_BEARING_TYPES:
        deadline_err = _deadline_violation(payload.get("response_deadline"))
        if deadline_err:
            logger.warning(
                "vendor_deadline_exceeded  message_type=%s deadline=%s",
                message_type,
                deadline_err.get("deadline"),
            )
            return _ack_reply(json.dumps(deadline_err))

    communications = callback_context.state.get(COMMUNICATION_KEY)

    if message_type == MessageType.RFQ:
        initial_val = _initial_state_from_rfq(body)
        callback_context.state.update(initial_val)
        set_status(callback_context.state, VendorThreadStatus.RFQ_RECEIVED)
        return None

    if not communications:
        return _ack_reply("No session found. Please start a new session.")

    communications.append(body)
    callback_context.state[COMMUNICATION_KEY] = communications

    incoming_round = body.get("round")
    if incoming_round is not None:
        try:
            callback_context.state[ROUND_KEY] = int(incoming_round)
        except (TypeError, ValueError):
            logger.warning("vendor_round_unparseable  raw=%r", incoming_round)

    if message_type == MessageType.COUNTER_OFFER:
        set_status(callback_context.state, VendorThreadStatus.NEGOTIATION_IN_PROGRESS)
        return None

    if message_type == MessageType.ACCEPT:
        unit_price = payload.get("unit_price")
        if unit_price is not None:
            try:
                callback_context.state[ACCEPTED_PRICE_KEY] = float(unit_price)
            except (TypeError, ValueError):
                logger.warning(
                    "vendor_accept_unit_price_unparseable  raw=%r", unit_price
                )
        set_status(callback_context.state, VendorThreadStatus.ACCEPTED)
        return None

    if message_type == MessageType.WALKAWAY:
        # Buyer walkaway closes the RFQ immediately; no LLM delegation per
        # design decision (vendor never counter-walks a buyer walkaway).
        set_status(callback_context.state, VendorThreadStatus.BUYER_WALKED_AWAY)
        set_status(callback_context.state, VendorThreadStatus.RFQ_CLOSED)
        return _ack_reply(
            json.dumps(
                {
                    "ok": True,
                    "message": "Buyer WALKAWAY acknowledged; thread closed.",
                    "status": str(VendorThreadStatus.RFQ_CLOSED),
                }
            )
        )

    if message_type == MessageType.RFQ_CLOSED:
        set_status(callback_context.state, VendorThreadStatus.RFQ_CLOSED)
        return _ack_reply(
            json.dumps(
                {
                    "ok": True,
                    "message": "RFQ_CLOSED acknowledged; thread closed.",
                    "status": str(VendorThreadStatus.RFQ_CLOSED),
                }
            )
        )

    if message_type == MessageType.PO:
        po_error = _validate_po(payload, callback_context.state)
        if po_error:
            return _ack_reply(json.dumps(po_error))
        callback_context.state[PO_KEY] = payload
        set_status(callback_context.state, VendorThreadStatus.PO_RECEIVED)
        return None

    if message_type == MessageType.GRN_CREATED:
        grn_error = _validate_grn(payload, callback_context.state)
        if grn_error:
            return _ack_reply(json.dumps(grn_error))
        callback_context.state[GRN_KEY] = payload
        set_status(callback_context.state, VendorThreadStatus.GRN_RECEIVED)
        return None

    if message_type == MessageType.PROCESS_COMPLETE:
        current = get_status(callback_context.state)
        if current != VendorThreadStatus.INVOICE_SUBMITTED:
            logger.warning(
                "vendor_process_complete_out_of_order  current=%s", current
            )
            return _ack_reply(
                json.dumps(
                    {
                        "ok": False,
                        "error": "process_complete_out_of_order",
                        "current_status": str(current) if current else None,
                    }
                )
            )
        set_status(callback_context.state, VendorThreadStatus.COMPLETE)
        return _ack_reply(
            json.dumps(
                {
                    "ok": True,
                    "message": "PROCESS_COMPLETE acknowledged; thread complete.",
                    "status": str(VendorThreadStatus.COMPLETE),
                }
            )
        )

    return None


__all__ = ["before_agent_callback"]
