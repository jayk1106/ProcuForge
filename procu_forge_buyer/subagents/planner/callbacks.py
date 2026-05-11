"""Callbacks for planner_agent (state injection + lifecycle logs)."""

from __future__ import annotations

from functools import partial
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from ...callbacks import (
    _plan_summary,
    _request_id,
    _session_state_dict,
    _state_json_for_injection,
    managed_log_after_handler,
    managed_log_before_handler,
)
from ...state_keys import PLANNER_PLAN_KEY


def inject_planner_session_state_before_model(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> None:
    """Append session state JSON so the planner model sees request/product and current plan."""
    payload = _state_json_for_injection(_session_state_dict(callback_context))
    text = (
        "Current ADK session.state (JSON, authoritative). Prefer these keys over "
        "guessing from the short tool `request` string alone:\n\n"
        f"```json\n{payload}\n```"
    )
    llm_request.contents.append(
        types.Content(role="user", parts=[types.Part(text=text)])
    )
    return None


def _planner_before(ctx: CallbackContext, st: dict[str, Any]) -> str:
    return "session_id=%s request_id=%s prior_plan=%s" % (
        ctx.session.id,
        _request_id(st) or "",
        _plan_summary(st.get(PLANNER_PLAN_KEY)),
    )


def _planner_after(ctx: CallbackContext, st: dict[str, Any]) -> str:
    return "session_id=%s request_id=%s plan=%s" % (
        ctx.session.id,
        _request_id(st) or "",
        _plan_summary(st.get(PLANNER_PLAN_KEY)),
    )


log_planner_before_agent = partial(
    managed_log_before_handler, span="PLANNER", detail_line=_planner_before
)
log_planner_after_agent = partial(
    managed_log_after_handler, span="PLANNER", detail_line=_planner_after, trailing_lines=None
)

__all__ = [
    "inject_planner_session_state_before_model",
    "log_planner_after_agent",
    "log_planner_before_agent",
]
