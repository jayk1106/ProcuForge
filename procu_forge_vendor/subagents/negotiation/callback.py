from __future__ import annotations

import json
import logging

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from communication.schema import MessageType
from procu_forge_vendor.communication_status import (
    VendorThreadStatus,
    get_status,
    set_status,
)
from procu_forge_vendor.state_keys import (
    ACCEPTED_PRICE_KEY,
    COMMUNICATION_KEY,
    VENDOR_IS_FINAL_KEY,
)


logger = logging.getLogger(__name__)


_STATUS_BY_OUTBOUND_TYPE = {
    MessageType.COUNTER_OFFER: VendorThreadStatus.NEGOTIATION_IN_PROGRESS,
    MessageType.ACCEPT: VendorThreadStatus.ACCEPTED,
    MessageType.WALKAWAY: VendorThreadStatus.VENDOR_WALKED_AWAY,
}


def after_agent_callback(callback_context: CallbackContext) -> types.Content | None:
    """Persist the outbound negotiation envelope and advance status.

    Status transitions:
    - COUNTER_OFFER -> NEGOTIATION_IN_PROGRESS
    - ACCEPT -> ACCEPTED (skipped when already ACCEPTED — avoids a spurious
                          invalid-transition warning when the buyer's ACCEPT
                          arrived first and the vendor echoes ACCEPT)
    - WALKAWAY -> VENDOR_WALKED_AWAY

    Side effects:
    - Persists outbound envelope to ``state[communication]``.
    - Records ACCEPTED_PRICE_KEY when emitting ACCEPT so PO validation can
      compare against the agreed price even if the buyer sends PO directly
      after a vendor-side ACCEPT.
    - Latches VENDOR_IS_FINAL_KEY when emitting an ``is_final=True``
      COUNTER_OFFER so ``send_response`` can reject a subsequent counter.
    - Clears ``temp:response_body`` after consuming it.
    - Round numbering is owned by ``send_response`` (mirrors the buyer's
      round); this callback does not mutate ``state[round]`` anymore.
    """
    body = callback_context.state.get("temp:response_body")
    print(f" VENDOR: body: {body}")
    if not body:
        return None

    communications = callback_context.state.get(COMMUNICATION_KEY) or []
    communications.append(body)
    callback_context.state[COMMUNICATION_KEY] = communications
    callback_context.state["temp:response_body"] = None

    msg_type = body.get("message_type")
    payload = body.get("payload") or {}

    if msg_type == MessageType.ACCEPT:
        unit_price = payload.get("unit_price")
        if unit_price is not None:
            try:
                callback_context.state[ACCEPTED_PRICE_KEY] = float(unit_price)
            except (TypeError, ValueError):
                logger.warning(
                    "vendor_outbound_accept_unit_price_unparseable  raw=%r",
                    unit_price,
                )

    if msg_type == MessageType.COUNTER_OFFER and payload.get("is_final"):
        callback_context.state[VENDOR_IS_FINAL_KEY] = True

    try:
        next_status = _STATUS_BY_OUTBOUND_TYPE.get(MessageType(msg_type))
    except ValueError:
        next_status = None
    if next_status is not None:
        current = get_status(callback_context.state)
        if (
            next_status == VendorThreadStatus.ACCEPTED
            and current == VendorThreadStatus.ACCEPTED
        ):
            pass  # already ACCEPTED — avoid redundant transition warning
        else:
            set_status(callback_context.state, next_status)

    return types.Content(
        role="model",
        parts=[types.Part(text=json.dumps(body))],
    )


__all__ = ["after_agent_callback"]
