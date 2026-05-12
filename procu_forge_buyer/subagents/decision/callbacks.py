"""Callbacks for decision_agent: parse structured vendor choice and advance ``pr_status``."""

from __future__ import annotations

import json
import logging
import re

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse

from ...pr_status_transitions import transition_after_decision
from ...state_keys import SELECTED_VENDOR_KEY

logger = logging.getLogger(__name__)

_JSON_VENDOR_RE = re.compile(r'"vendor"\s*:\s*"([^"]+)"', re.IGNORECASE)


def _text_from_llm_response(llm_response: LlmResponse) -> str:
    content = llm_response.content
    if content is None or not content.parts:
        return ""
    chunks: list[str] = []
    for part in content.parts:
        t = getattr(part, "text", None)
        if t:
            chunks.append(t)
    return "\n".join(chunks).strip()


def _extract_vendor_name(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            v = data.get("vendor")
            if isinstance(v, str) and v.strip():
                return v.strip()
    except json.JSONDecodeError:
        pass
    m = _JSON_VENDOR_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def after_model_parse_vendor_and_transition(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> None:
    """Persist ``selected_vendor`` from model text/JSON and move to ``VENDOR_SELECTED``."""
    text = _text_from_llm_response(llm_response)
    vendor = _extract_vendor_name(text)
    if vendor:
        callback_context.state[SELECTED_VENDOR_KEY] = {"vendor": vendor}
        transition_after_decision(callback_context.state)
    else:
        logger.warning("decision_agent: could not parse vendor from model output")
    return None
