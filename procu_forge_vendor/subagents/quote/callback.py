from __future__ import annotations

import json

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from procu_forge_vendor.communication_status import VendorThreadStatus, set_status
from procu_forge_vendor.state_keys import COMMUNICATION_KEY, ROUND_KEY


def after_agent_callback(callback_context: CallbackContext) -> types.Content | None:
    """Persist the outbound QUOTE envelope and advance status to QUOTE_SENT."""
    body = callback_context.state.get("temp:response_body")
    print(f" VENDOR QUOTE: after_agent_callback: {body}")
    if body:
        communications = callback_context.state.get(COMMUNICATION_KEY) or []
        communications.append(body)
        callback_context.state[COMMUNICATION_KEY] = communications
        callback_context.state["temp:response_body"] = None
        callback_context.state[ROUND_KEY] = 0
        set_status(callback_context.state, VendorThreadStatus.QUOTE_SENT)
        return types.Content(
            role="model",
            parts=[types.Part(text=json.dumps(body))],
        )

    return None


__all__ = ["after_agent_callback"]
