"""Lifecycle callbacks for procu_forge_vendor."""

from __future__ import annotations

import json
import logging
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from .state_keys import (
    COMMUNICATION_KEY,
    PRODUCT_KEY,
    ROUND_KEY,
    RFQ_ID_KEY,
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


# ── callback ──────────────────────────────────────────────────────────────────

def log_vendor_before_agent(
    callback_context: CallbackContext,
) -> types.Content | None:
    """Log inbound message, session history, and current state before each turn.

    Also appends non-RFQ incoming messages (counter-offer, accept, walk-away) to
    ``state[communication]`` so the communication log tracks every buyer message.
    The RFQ itself is already in the list via state_delta seeded by the converter.
    """
    session = callback_context.session
    state = callback_context.state
    events = list(session.events or [])

    # ── inbound message ───────────────────────────────────────────────────────
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

    # ── state summary ─────────────────────────────────────────────────────────
    logger.info("vendor_state  %s", _state_summary(dict(state)))

    # ── session history (turn 2+) ─────────────────────────────────────────────
    if prior_count > 0:
        history = [_event_tag(e) for e in events[:-1]]
        logger.info(
            "vendor_session_history  session_id=%s history=[%s]",
            session.id,
            ", ".join(history),
        )

    # ── track non-RFQ buyer messages in communication list ────────────────────
    # RFQ is already seeded by state_delta in rfq_request_converter.
    # Counter-offers, accepts, and walk-aways arrive on subsequent turns.
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


__all__ = ["log_vendor_before_agent"]
