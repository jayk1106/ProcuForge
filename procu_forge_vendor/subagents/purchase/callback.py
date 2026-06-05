from __future__ import annotations

import json

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from communication.schema import MessageType
from procu_forge_vendor.communication_status import VendorThreadStatus, set_status
from procu_forge_vendor.state_keys import COMMUNICATION_KEY


_STATUS_BY_OUTBOUND_TYPE = {
    MessageType.INVOICE_SUBMITTED: VendorThreadStatus.INVOICE_SUBMITTED,
}


def after_agent_callback(callback_context: CallbackContext) -> types.Content | None:
    """Persist the outbound purchase-manager envelope and advance status.

    Only outbound type is INVOICE_SUBMITTED (PO acknowledgement is auto-handled
    by the orchestrator's before_agent_callback before any subagent runs).

    Control returns to the orchestrator naturally on subagent completion;
    no explicit ``transfer_to_agent`` is needed (matches quote / negotiation
    after-callbacks).
    """
    body = callback_context.state.get("temp:response_body")
    if not body:
        return None

    communications = callback_context.state.get(COMMUNICATION_KEY) or []
    communications.append(body)
    callback_context.state[COMMUNICATION_KEY] = communications
    callback_context.state["temp:response_body"] = None

    msg_type = body.get("message_type")
    try:
        next_status = _STATUS_BY_OUTBOUND_TYPE.get(MessageType(msg_type))
    except ValueError:
        next_status = None
    if next_status is not None:
        set_status(callback_context.state, next_status)

    return types.Content(
        role="model",
        parts=[types.Part(text=json.dumps(body))],
    )


__all__ = ["after_agent_callback"]
