"""Callbacks for negotiator_agent: lifecycle logs, A2A tool validation, send/receive logs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from functools import partial
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.context import Context
from google.adk.tools.base_tool import BaseTool

from ...callbacks import (
    _plan_summary,
    _product_id,
    _request_id,
    managed_log_after_handler,
    managed_log_before_handler,
)
from ...communication_validate import CommunicationSchemaError, validate_communication_message
from ...pr_status_transitions import (
    _targeted_vendor_ids,
    pr_status_line,
    transition_after_negotiation,
    transition_to_negotiation_in_progress,
)
from ...state_keys import (
    NEGOTIATION_CONFIG_KEY,
    NEGOTIATOR_COMMS_SNAPSHOT_KEY,
    NEGOTIATOR_STALL_STREAK_KEY,
    PLANNER_PLAN_KEY,
)

logger = logging.getLogger(__name__)

VENDOR_A2A_TOOL_NAME = "negotiate_with_vendor"
_MAX_LOG_CHARS = 8_000


def _trunc(text: str, limit: int = _MAX_LOG_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _envelope_teaser(data: dict[str, Any]) -> str:
    return (
        f"message_type={data.get('message_type')!s} "
        f"message_id={data.get('message_id')!s} "
        f"rfq_id={data.get('rfq_id')!s} "
        f"vendor_id={data.get('vendor_id')!s} "
        f"from_agent={data.get('from_agent')!s} "
        f"to_agent={data.get('to_agent')!s} "
        f"round={data.get('round')!s}"
    )


def _negotiation_progress_line(st: dict[str, Any]) -> str:
    """Compact ``done X/Y targeted=[…]`` snapshot for the negotiator log span."""
    targeted = _targeted_vendor_ids(st)
    nego = st.get(NEGOTIATION_CONFIG_KEY) or {}
    if not targeted:
        return "targeted=0 done=0"
    done_ids = [
        vid
        for vid in targeted
        if isinstance(nego.get(vid), dict) and nego[vid].get("done")
    ]
    return "targeted=%d done=%d done_ids=%s remaining=%s" % (
        len(targeted),
        len(done_ids),
        ",".join(done_ids) or "-",
        ",".join(vid for vid in targeted if vid not in done_ids) or "-",
    )


def _negotiator_before(ctx: CallbackContext, st: dict[str, Any]) -> str:
    return (
        "negotiator_agent start session_id=%s request_id=%s product_id=%s plan=%s %s %s"
        % (
            ctx.session.id,
            _request_id(st) or "",
            _product_id(st) or "",
            _plan_summary(st.get(PLANNER_PLAN_KEY)),
            pr_status_line(st),
            _negotiation_progress_line(st),
        )
    )


def _negotiator_after(ctx: CallbackContext, st: dict[str, Any]) -> str:
    return (
        "negotiator_agent end session_id=%s request_id=%s product_id=%s plan=%s %s %s"
        % (
            ctx.session.id,
            _request_id(st) or "",
            _product_id(st) or "",
            _plan_summary(st.get(PLANNER_PLAN_KEY)),
            pr_status_line(st),
            _negotiation_progress_line(st),
        )
    )


log_negotiator_before_agent = partial(
    managed_log_before_handler, span="NEGOTIATOR", detail_line=_negotiator_before
)
log_negotiator_after_agent = partial(
    managed_log_after_handler,
    span="NEGOTIATOR",
    detail_line=_negotiator_after,
    trailing_lines=None,
)


def _comms_snapshot(state: dict[str, Any]) -> dict[str, int]:
    """Return {vendor_id: len(communications)} for all targeted vendors."""
    targeted = _targeted_vendor_ids(state)
    nego = state.get(NEGOTIATION_CONFIG_KEY) or {}
    return {
        vid: len((nego.get(vid) or {}).get("communications") or [])
        for vid in targeted
    }


def negotiator_before_agent_with_transition(callback_context: CallbackContext) -> None:
    """Flip ``pr_status`` to ``NEGOTIATION_IN_PROGRESS``, snapshot comms, then emit start span."""
    state = callback_context.state
    transition_to_negotiation_in_progress(state)
    state[NEGOTIATOR_COMMS_SNAPSHOT_KEY] = _comms_snapshot(state)
    log_negotiator_before_agent(callback_context)
    return None


def _force_close_stalled_vendors(
    callback_context: CallbackContext,
    targeted: list[str],
    streak: int,
) -> None:
    """Force-walkaway all not-done vendors when the stall guard fires."""
    state = callback_context.state
    nego: dict[str, Any] = dict(state.get(NEGOTIATION_CONFIG_KEY) or {})
    not_done = [
        vid
        for vid in targeted
        if not (isinstance(nego.get(vid), dict) and nego[vid].get("done"))
    ]
    if not not_done:
        return
    logger.warning(
        "negotiator_stall_force_close session_id=%s stall_streak=%d vendors=%s",
        callback_context.session.id,
        streak,
        ",".join(not_done),
    )
    ts = datetime.now(timezone.utc).isoformat()
    for vid in not_done:
        config: dict[str, Any] = dict(nego.get(vid) or {})
        comms: list[Any] = list(config.get("communications") or [])
        comms.append({
            "message_type": "WALKAWAY",
            "from_agent": "buyer_negotiator",
            "vendor_id": vid,
            "round": config.get("round"),
            "timestamp": ts,
            "payload": {"reason": "BUYER_CANCELLED", "note": "force_closed_by_stall_guard"},
        })
        config["communications"] = comms
        config["done"] = True
        nego[vid] = config
    state[NEGOTIATION_CONFIG_KEY] = nego


def negotiator_after_agent_with_transition(callback_context: CallbackContext) -> None:
    """Detect stalls, optionally force-close, advance ``pr_status``, then emit end span."""
    state = callback_context.state
    targeted = _targeted_vendor_ids(state)

    # Compare current comms lengths to the snapshot taken before this turn.
    snapshot = state.get(NEGOTIATOR_COMMS_SNAPSHOT_KEY) or {}
    nego = state.get(NEGOTIATION_CONFIG_KEY) or {}
    progress = any(
        len((nego.get(vid) or {}).get("communications") or []) > snapshot.get(vid, 0)
        for vid in targeted
    )

    if progress:
        state[NEGOTIATOR_STALL_STREAK_KEY] = 0
    else:
        streak: int = int(state.get(NEGOTIATOR_STALL_STREAK_KEY) or 0) + 1
        state[NEGOTIATOR_STALL_STREAK_KEY] = streak
        if streak >= 2:
            _force_close_stalled_vendors(callback_context, targeted, streak)

    transition_after_negotiation(state)
    log_negotiator_after_agent(callback_context)
    return None


def negotiator_before_tool(
    tool: BaseTool, args: dict[str, Any], tool_context: Context
) -> dict[str, Any] | str | None:
    if tool.name != VENDOR_A2A_TOOL_NAME:
        return None
    data = args.get("communication_data") or {}
    logger.info(
        "a2a_call_begin session_id=%s vendor_id=%s message_type=%s price=%s",
        tool_context.session.id,
        data.get("vendor_id"),
        data.get("message_type"),
        data.get("price"),
    )
    return None


def negotiator_after_tool(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: Context,
    tool_response: Any,
) -> dict[str, Any] | str | None:
    if tool.name != VENDOR_A2A_TOOL_NAME:
        return None

    if not isinstance(tool_response, dict):
        logger.warning(
            "a2a_call_end session_id=%s unexpected response type=%s",
            tool_context.session.id,
            type(tool_response).__name__,
        )
        return None

    vendor_reply = tool_response.get("vendor_reply") or ""
    rfq_id = tool_response.get("rfq_id", "?")
    round_num = tool_response.get("round", "?")

    # Try to validate the vendor reply if it looks like a JSON envelope.
    reply_str = vendor_reply if isinstance(vendor_reply, str) else json.dumps(vendor_reply, default=str)
    stripped = reply_str.strip()
    validation_note = ""
    if stripped.startswith("{"):
        try:
            inbound = json.loads(stripped)
            if isinstance(inbound, dict):
                try:
                    validate_communication_message(inbound)
                    validation_note = " schema=ok"
                except CommunicationSchemaError as e:
                    validation_note = f" schema=mismatch({e.errors[:3]})"
        except json.JSONDecodeError:
            pass

    logger.info(
        "a2a_call_end session_id=%s rfq_id=%s round=%s vendor_reply_chars=%d%s",
        tool_context.session.id,
        rfq_id,
        round_num,
        len(reply_str),
        validation_note,
    )
    return None


__all__ = [
    "VENDOR_A2A_TOOL_NAME",
    "log_negotiator_after_agent",
    "log_negotiator_before_agent",
    "negotiator_after_agent_with_transition",
    "negotiator_after_tool",
    "negotiator_before_agent_with_transition",
    "negotiator_before_tool",
]
