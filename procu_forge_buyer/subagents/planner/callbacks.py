"""Callbacks for planner_agent (state injection + lifecycle logs)."""

from __future__ import annotations

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from ...callbacks import (
    manage_log_after_planner as log_planner_after_agent,
    manage_log_before_planner as log_planner_before_agent,
    _session_state_dict,
    _state_json_for_injection,
)


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
