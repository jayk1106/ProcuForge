"""Lifecycle callbacks for procu_forge_vendor."""

from __future__ import annotations

import json
import logging
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

logger = logging.getLogger(__name__)


def _parse_envelope(text: str) -> dict[str, Any] | None:
    try:
        msg = json.loads(text)
        return msg if isinstance(msg, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _event_tag(event: Any) -> str:
    """One-line label for a session event used in history logging."""
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


def log_vendor_before_agent(
    callback_context: CallbackContext,
) -> types.Content | None:
    """Log inbound message and session history before the vendor agent runs.

    Fires on every turn. When the vendor session is being reused (prior_events > 0)
    the history line shows all previous buyer/vendor turns — useful for confirming
    that session threading via rfq_id is working correctly.
    """
    session = callback_context.session
    events = list(session.events or [])

    # Most-recent event is the inbound message for this turn.
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

    if prior_count > 0:
        history = [_event_tag(e) for e in events[:-1]]
        logger.info(
            "vendor_session_history  session_id=%s history=[%s]",
            session.id,
            ", ".join(history),
        )

    return None


__all__ = ["log_vendor_before_agent"]
