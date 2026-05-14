from __future__ import annotations

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

import json
from procu_forge_vendor.state_keys import COMMUNICATION_KEY, ROUND_KEY

def after_agent_callback(callback_context: CallbackContext) -> types.Content | None:
    """
        This callback is called after the negotiation agent has finished executing.
        It is used to store the response body in the state and increment the round.
    """
    body = callback_context.state.get("temp:response_body")
    print("inside after negotiation agent: BEFORE", callback_context.state.to_dict())
    if body:
        communications = callback_context.state.get(COMMUNICATION_KEY)
        communications.append(body)
        callback_context.state[COMMUNICATION_KEY] = communications
        callback_context.state["temp:response_body"] = None
        callback_context.state[ROUND_KEY] = callback_context.state.get(ROUND_KEY) + 1
        return types.Content(
            role="model",
            parts=[types.Part(text=json.dumps(body))],
        )

    print("inside after negotiation agent: AFTER", callback_context.state.to_dict())
    return None

__all__ = ["after_agent_callback"]
