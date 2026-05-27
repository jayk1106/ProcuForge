from __future__ import annotations

import json

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from communication.schema import MessageType
from procu_forge_vendor.communication_status import VendorThreadStatus, set_status
from procu_forge_vendor.state_keys import COMMUNICATION_KEY, ROUND_KEY


_STATUS_BY_OUTBOUND_TYPE = {
    MessageType.COUNTER_OFFER: VendorThreadStatus.NEGOTIATION_IN_PROGRESS,
    MessageType.ACCEPT: VendorThreadStatus.ACCEPTED,
    MessageType.WALKAWAY: VendorThreadStatus.VENDOR_WALKED_AWAY,
}


def after_agent_callback(callback_context: CallbackContext) -> types.Content | None:
    """Persist the outbound negotiation envelope and advance status.

    Status transitions:
    - COUNTER_OFFER -> NEGOTIATION_IN_PROGRESS
    - ACCEPT -> ACCEPTED  (only if not already ACCEPTED — avoids ACCEPTED→ACCEPTED warning
                           when the buyer sent ACCEPT and the vendor echoes back ACCEPT)
    - WALKAWAY -> VENDOR_WALKED_AWAY
    """
    body = callback_context.state.get("temp:response_body")
    if not body:
        return None

    communications = callback_context.state.get(COMMUNICATION_KEY) or []
    communications.append(body)
    callback_context.state[COMMUNICATION_KEY] = communications
    callback_context.state["temp:response_body"] = None
    callback_context.state[ROUND_KEY] = (callback_context.state.get(ROUND_KEY) or 0) + 1

    msg_type = body.get("message_type")
    try:
        next_status = _STATUS_BY_OUTBOUND_TYPE.get(MessageType(msg_type))
    except ValueError:
        next_status = None
    if next_status is not None:
        from procu_forge_vendor.communication_status import get_status
        if next_status == VendorThreadStatus.ACCEPTED and get_status(callback_context.state) == VendorThreadStatus.ACCEPTED:
            pass  # already ACCEPTED from buyer's ACCEPT message — skip redundant re-set
        else:
            set_status(callback_context.state, next_status)

    return types.Content(
        role="model",
        parts=[types.Part(text=json.dumps(body))],
    )


__all__ = ["after_agent_callback"]
