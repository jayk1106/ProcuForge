"""Callbacks for purchase_manager_agent: advance pr_status after each A2A document step."""

from __future__ import annotations

import logging

from google.adk.agents.callback_context import CallbackContext

from ...pr_status import PrStatus
from ...pr_status_transitions import (
    transition_to_awaiting_user_approval,
    transition_to_completed,
    transition_to_invoice_under_verification,
    transition_to_po_acknowledged,
)
from ...state_keys import GRN_KEY, INVOICE_KEY, PO_KEY, PR_STATUS_KEY, PROCESS_COMPLETE_KEY

logger = logging.getLogger(__name__)


def purchase_manager_after_agent(callback_context: CallbackContext) -> None:
    """Advance pr_status based on what the purchase_manager accomplished this turn.

    Transition rules (checked in order):
    - VENDOR_SELECTED              → AWAITING_USER_APPROVAL  (human gate before PO)
    - PO_ISSUED   + po in state    → PO_ACKNOWLEDGED
    - PO_ACKNOWLEDGED + grn state  → INVOICE_UNDER_VERIFICATION
    - INVOICE_UNDER_VERIFICATION + process_complete in state → COMPLETED
    """
    state = callback_context.state
    current = state.get(PR_STATUS_KEY)

    if current == PrStatus.VENDOR_SELECTED.value:
        transition_to_awaiting_user_approval(state)

    elif current == PrStatus.PO_ISSUED.value:
        po = state.get(PO_KEY)
        if isinstance(po, dict) and po.get("po_number"):
            transition_to_po_acknowledged(state)
        else:
            logger.warning("purchase_manager: send_po did not produce a valid PO; staying at PO_ISSUED")

    elif current == PrStatus.PO_ACKNOWLEDGED.value:
        grn = state.get(GRN_KEY)
        if isinstance(grn, dict) and grn.get("grn_number"):
            transition_to_invoice_under_verification(state)
        else:
            logger.warning("purchase_manager: send_grn_created did not produce a valid GRN; staying at PO_ACKNOWLEDGED")

    elif current == PrStatus.INVOICE_UNDER_VERIFICATION.value:
        pc = state.get(PROCESS_COMPLETE_KEY)
        if isinstance(pc, dict) and pc.get("po_number"):
            transition_to_completed(state)
        else:
            logger.warning("purchase_manager: send_process_complete did not complete; staying at INVOICE_UNDER_VERIFICATION")

    return None
