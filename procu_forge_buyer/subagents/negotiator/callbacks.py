"""Callbacks for negotiator_agent: lifecycle logs, A2A tool validation, send/receive logs."""

from __future__ import annotations

import json
import logging
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
from ...pr_status_transitions import pr_status_line, transition_after_negotiation
from ...state_keys import PLANNER_PLAN_KEY

logger = logging.getLogger(__name__)

VENDOR_A2A_TOOL_NAME = "procu_forge_vendor"
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


def _negotiator_before(ctx: CallbackContext, st: dict[str, Any]) -> str:
    return (
        "negotiator_agent start session_id=%s request_id=%s product_id=%s plan=%s %s"
        % (
            ctx.session.id,
            _request_id(st) or "",
            _product_id(st) or "",
            _plan_summary(st.get(PLANNER_PLAN_KEY)),
            pr_status_line(st),
        )
    )


def _negotiator_after(ctx: CallbackContext, st: dict[str, Any]) -> str:
    return (
        "negotiator_agent end session_id=%s request_id=%s product_id=%s plan=%s %s"
        % (
            ctx.session.id,
            _request_id(st) or "",
            _product_id(st) or "",
            _plan_summary(st.get(PLANNER_PLAN_KEY)),
            pr_status_line(st),
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


def negotiator_after_agent_with_transition(callback_context: CallbackContext) -> None:
    """Advance ``pr_status`` after negotiation, then emit the NEGOTIATOR end span."""
    transition_after_negotiation(callback_context.state)
    log_negotiator_after_agent(callback_context)
    return None


def negotiator_before_tool(
    tool: BaseTool, args: dict[str, Any], tool_context: Context
) -> dict[str, Any] | str | None:
    if tool.name != VENDOR_A2A_TOOL_NAME:
        return None
    raw = args.get("request")
    if not isinstance(raw, str):
        err = f"procu_forge_vendor requires string `request` (JSON envelope), got {type(raw).__name__}"
        logger.error("a2a_send_invalid type session_id=%s %s", tool_context.session.id, err)
        return (
            "[communication_schema_error] "
            + err
            + " Fix: pass a single JSON object string with schema_version, message_id, "
            "rfq_id, vendor_id, from_agent, to_agent, message_type, timestamp, payload."
        )
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(
            "a2a_send_invalid_json session_id=%s error=%s body=%s",
            tool_context.session.id,
            e,
            _trunc(raw),
        )
        return (
            "[communication_schema_error] `request` is not valid JSON: "
            f"{e!s}. Body (truncated): {_trunc(raw)}"
        )
    if not isinstance(msg, dict):
        logger.error(
            "a2a_send_invalid_root session_id=%s type=%s",
            tool_context.session.id,
            type(msg).__name__,
        )
        return (
            "[communication_schema_error] JSON root must be an object (envelope), "
            f"not {type(msg).__name__}."
        )
    try:
        validate_communication_message(msg)
    except CommunicationSchemaError as e:
        logger.error(
            "a2a_send_schema_rejected session_id=%s %s errors=%s body=%s",
            tool_context.session.id,
            e,
            e.errors,
            _trunc(raw),
        )
        detail = "; ".join(e.errors[:12])
        if len(e.errors) > 12:
            detail += f"; ... ({len(e.errors) - 12} more)"
        return (
            "[communication_schema_error] Outbound message failed validation: "
            f"{e!s}. Details: {detail}"
        )
    logger.info(
        "a2a_send session_id=%s tool=%s %s",
        tool_context.session.id,
        tool.name,
        _envelope_teaser(msg),
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
    if isinstance(tool_response, dict):
        text = json.dumps(tool_response, default=str, ensure_ascii=False)
    elif tool_response is None:
        text = ""
    else:
        text = str(tool_response)
    logger.info(
        "a2a_receive session_id=%s tool=%s chars=%d body=%s",
        tool_context.session.id,
        tool.name,
        len(text),
        _trunc(text),
    )
    stripped = text.strip()
    if not stripped.startswith("{"):
        logger.warning(
            "a2a_receive_non_json session_id=%s tool=%s (no schema validation)",
            tool_context.session.id,
            tool.name,
        )
        return None
    try:
        inbound = json.loads(stripped)
    except json.JSONDecodeError as e:
        logger.warning(
            "a2a_receive_json_parse_failed session_id=%s error=%s",
            tool_context.session.id,
            e,
        )
        return None
    if not isinstance(inbound, dict):
        return None
    try:
        validate_communication_message(inbound)
    except CommunicationSchemaError as e:
        logger.warning(
            "a2a_receive_schema_mismatch session_id=%s %s errors=%s",
            tool_context.session.id,
            e,
            e.errors,
        )
        return None
    logger.info(
        "a2a_receive_validated session_id=%s %s",
        tool_context.session.id,
        _envelope_teaser(inbound),
    )
    return None


__all__ = [
    "VENDOR_A2A_TOOL_NAME",
    "log_negotiator_after_agent",
    "log_negotiator_before_agent",
    "negotiator_after_tool",
    "negotiator_before_tool",
]
