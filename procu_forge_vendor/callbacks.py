"""Lifecycle callbacks for procu_forge_vendor."""

from __future__ import annotations

import json
import logging
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from communication.schema import MessageType

from .communication_status import VendorThreadStatus, set_status
from .state_keys import (
    COMMUNICATION_KEY,
    GRN_KEY,
    PO_KEY,
    PRODUCT_KEY,
    RFQ_ID_KEY,
    ROUND_KEY,
    VENDOR_ID_KEY,
)


logger = logging.getLogger(__name__)


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

    Only called when ``message_type == "RFQ"``. The product.price field is a
    stub; the quote agent fills authoritative pricing from the catalog.
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
            "currency": payload.get("currency") or "USD",
            "unit": item.get("unit", "unit"),
            "price": 0.0,
            "quantity": int(item.get("quantity") or 1),
        },
        COMMUNICATION_KEY: [envelope],
    }


def _ack_reply(text: str) -> types.Content:
    return types.Content(role="model", parts=[types.Part(text=text)])


# ── callback ──────────────────────────────────────────────────────────────────

def before_agent_callback(callback_context: CallbackContext) -> types.Content | None:
    """Validate the inbound envelope, advance status, and short-circuit
    no-response message types (RFQ_CLOSED, PROCESS_COMPLETE) before any
    subagent dispatch.
    """
    req_type = callback_context.state.get("type")
    if req_type == "error":
        return _ack_reply(
            callback_context.state.get("message") or "Validation failed"
        )

    body = callback_context.state.get("temp:request_body")
    if not body:
        return _ack_reply("No request body found in state.")

    message_type = body.get("message_type")
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
    payload = body.get("payload") or {}

    if message_type == MessageType.COUNTER_OFFER:
        set_status(callback_context.state, VendorThreadStatus.NEGOTIATION_IN_PROGRESS)
        return None

    if message_type == MessageType.ACCEPT:
        set_status(callback_context.state, VendorThreadStatus.ACCEPTED)
        return None

    if message_type == MessageType.WALKAWAY:
        set_status(callback_context.state, VendorThreadStatus.BUYER_WALKED_AWAY)
        return None

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
        callback_context.state[PO_KEY] = payload
        set_status(callback_context.state, VendorThreadStatus.PO_RECEIVED)
        return None

    if message_type == MessageType.GRN_CREATED:
        callback_context.state[GRN_KEY] = payload
        set_status(callback_context.state, VendorThreadStatus.GRN_RECEIVED)
        return None

    if message_type == MessageType.PROCESS_COMPLETE:
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


def log_vendor_before_agent(
    callback_context: CallbackContext,
) -> types.Content | None:
    """Log inbound message, session history, and current state before each turn.

    Also appends non-RFQ incoming messages to ``state[communication]`` so the
    communication log tracks every buyer message. The RFQ itself is already in
    the list via state_delta seeded by the converter.
    """
    session = callback_context.session
    state = callback_context.state
    events = list(session.events or [])

    current_text = ""
    if events:
        last = events[-1]
        if last.content and last.content.parts:
            for part in last.content.parts:
                if part.text:
                    current_text = part.text
                    break

    env = _parse_envelope(current_text)
    msg_type = env.get("message_type", "?") if env else "?"
    rfq_id = env.get("rfq_id", "?") if env else "?"
    round_num = env.get("round", "?") if env else "?"
    prior_count = max(0, len(events) - 1)

    logger.info(
        "vendor_before_agent  session_id=%s prior_events=%d"
        "  message_type=%s rfq_id=%s round=%s",
        session.id,
        prior_count,
        msg_type,
        rfq_id,
        round_num,
    )

    logger.info("vendor_state  %s", _state_summary(dict(state)))

    if prior_count > 0:
        history = [_event_tag(e) for e in events[:-1]]
        logger.info(
            "vendor_session_history  session_id=%s history=[%s]",
            session.id,
            ", ".join(history),
        )

    if env and msg_type not in ("RFQ", "?") and prior_count > 0:
        comms: list[Any] = list(state.get(COMMUNICATION_KEY) or [])
        comms.append(env)
        state[COMMUNICATION_KEY] = comms
        logger.info(
            "vendor_comms_appended  session_id=%s message_type=%s comms_total=%d",
            session.id,
            msg_type,
            len(comms),
        )

    return None


__all__ = ["log_vendor_before_agent", "before_agent_callback"]
