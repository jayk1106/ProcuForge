"""ADK lifecycle callbacks: shared helpers, managed span logging, orchestrator hooks."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from functools import partial
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from .pr_status import PrStatus
from .pr_status_transitions import STOP_PR_STATUSES, pr_status_line
from .state_keys import PLANNER_PLAN_KEY, PR_STATUS_KEY

logger = logging.getLogger(__name__)

_MAX_STATE_JSON_CHARS = 24_000

_STOP_PR_STATUS_VALUES = frozenset(s.value for s in STOP_PR_STATUSES)


def _session_state_dict(callback_context: CallbackContext) -> dict[str, Any]:
    return callback_context.state.to_dict()


def inject_session_state_before_model(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
    *,
    preamble: str | None = None,
) -> None:
    """Append session.state JSON so a subagent model sees authoritative workflow state."""
    payload = _state_json_for_injection(_session_state_dict(callback_context))
    intro = preamble or (
        "Current ADK session.state (JSON, authoritative). Prefer these keys over "
        "guessing from prior turns alone:"
    )
    text = f"{intro}\n\n```json\n{payload}\n```"
    llm_request.contents.append(
        types.Content(role="user", parts=[types.Part(text=text)])
    )
    return None


def _state_json_for_injection(data: dict[str, Any]) -> str:
    try:
        text = json.dumps(data, default=str, indent=2, ensure_ascii=False)
    except TypeError:
        text = repr(data)
    if len(text) > _MAX_STATE_JSON_CHARS:
        return text[: _MAX_STATE_JSON_CHARS - 3] + "..."
    return text


def _request_id(state: dict[str, Any]) -> str | None:
    req = state.get("request")
    if isinstance(req, dict):
        rid = req.get("request_id")
        return str(rid) if rid is not None else None
    return None


def _product_id(state: dict[str, Any]) -> str | None:
    req = state.get("request")
    if isinstance(req, dict):
        pid = req.get("product_id")
        return str(pid) if pid is not None else None
    prod = state.get("product")
    if isinstance(prod, dict):
        pid = prod.get("id")
        return str(pid) if pid is not None else None
    return None


def _plan_summary(plan: object | None) -> str:
    if plan is None:
        return "none"
    if isinstance(plan, dict):
        reasoning = plan.get("reasoning")
        reasoning_s = str(reasoning) if reasoning is not None else ""
        reasoning_s = " ".join(reasoning_s.split())
        if len(reasoning_s) > 140:
            reasoning_s = reasoning_s[:137] + "..."
        parts = [
            str(plan.get("next_action", "")),
            str(plan.get("agent_to_invoke", "")),
            f"conf={plan.get('confidence')}",
            f"reasoning={reasoning_s}" if reasoning_s else "",
        ]
        return ",".join(p for p in parts if p and p != "None")
    return str(plan)[:400]


def _span_banner(span: str, *, end: bool = False) -> str:
    phase = "END" if end else "START"
    return f"------------- {phase} {span.upper()} -------------"


def managed_log_before_handler(
    callback_context: CallbackContext,
    *,
    span: str,
    detail_line: Callable[[CallbackContext, dict[str, Any]], str],
) -> None:
    st = _session_state_dict(callback_context)
    logger.info(_span_banner(span, end=False))
    logger.info("%s", detail_line(callback_context, st))
    return None


def managed_log_after_handler(
    callback_context: CallbackContext,
    *,
    span: str,
    detail_line: Callable[[CallbackContext, dict[str, Any]], str],
    trailing_lines: Callable[[CallbackContext, dict[str, Any]], list[str]] | None = None,
) -> None:
    st = _session_state_dict(callback_context)
    logger.info("%s", detail_line(callback_context, st))
    if trailing_lines:
        for extra in trailing_lines(callback_context, st):
            logger.info("%s", extra)
    logger.info(_span_banner(span, end=True))
    return None


def _orch_before(ctx: CallbackContext, st: dict[str, Any]) -> str:
    return (
        "procu_forge_buyer start session_id=%s request_id=%s product_id=%s plan=%s %s"
        % (
            ctx.session.id,
            _request_id(st) or "",
            _product_id(st) or "",
            _plan_summary(st.get(PLANNER_PLAN_KEY)),
            pr_status_line(st),
        )
    )


def _orch_after(ctx: CallbackContext, st: dict[str, Any]) -> str:
    return (
        "procu_forge_buyer end session_id=%s request_id=%s product_id=%s plan=%s %s"
        % (
            ctx.session.id,
            _request_id(st) or "",
            _product_id(st) or "",
            _plan_summary(st.get(PLANNER_PLAN_KEY)),
            pr_status_line(st),
        )
    )


manage_log_before_orchestrator = partial(
    managed_log_before_handler, span="ORCHESTRATOR", detail_line=_orch_before
)
manage_log_after_orchestrator = partial(
    managed_log_after_handler, span="ORCHESTRATOR", detail_line=_orch_after, trailing_lines=None
)


def _pr_router_before(ctx: CallbackContext, st: dict[str, Any]) -> str:
    return (
        "pr_router start session_id=%s request_id=%s product_id=%s plan=%s %s"
        % (
            ctx.session.id,
            _request_id(st) or "",
            _product_id(st) or "",
            _plan_summary(st.get(PLANNER_PLAN_KEY)),
            pr_status_line(st),
        )
    )


def _pr_router_after(ctx: CallbackContext, st: dict[str, Any]) -> str:
    return (
        "pr_router end session_id=%s request_id=%s product_id=%s plan=%s %s"
        % (
            ctx.session.id,
            _request_id(st) or "",
            _product_id(st) or "",
            _plan_summary(st.get(PLANNER_PLAN_KEY)),
            pr_status_line(st),
        )
    )


manage_log_before_pr_router = partial(
    managed_log_before_handler, span="PR_ROUTER", detail_line=_pr_router_before
)
manage_log_after_pr_router = partial(
    managed_log_after_handler, span="PR_ROUTER", detail_line=_pr_router_after, trailing_lines=None
)


def stop_loop_if_terminal(callback_context: CallbackContext) -> types.Content | None:
    """Exit the enclosing ``LoopAgent`` when ``pr_status`` is terminal or human-gated.

    Returns a minimal model ``Content`` so ADK emits an ``Event`` carrying
    ``actions.escalate`` (actions-only callbacks do not always yield an event).
    """
    status = callback_context.state.get(PR_STATUS_KEY)
    if status not in _STOP_PR_STATUS_VALUES:
        return None

    callback_context.actions.escalate = True
    callback_context.actions.skip_summarization = True
    logger.info("loop_exit reason=pr_status_terminal pr_status=%s", status)
    return types.Content(role="model", parts=[types.Part(text=" ")])
