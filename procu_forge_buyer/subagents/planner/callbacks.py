"""Callbacks for planner_agent (state injection + lifecycle logs)."""

from __future__ import annotations

from functools import partial
from typing import Any

from functools import partial

from google.adk.agents.callback_context import CallbackContext

from ...callbacks import (
    _plan_summary,
    _request_id,
    inject_session_state_before_model,
    managed_log_after_handler,
    managed_log_before_handler,
)
from ...state_keys import PLANNER_PLAN_KEY


inject_planner_session_state_before_model = partial(
    inject_session_state_before_model,
    preamble=(
        "Current ADK session.state (JSON, authoritative). Prefer these keys over "
        "guessing from the short tool `request` string alone:"
    ),
)


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
