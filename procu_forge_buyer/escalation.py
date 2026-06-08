"""Central escalation helpers for buyer workflow blockers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal, MutableMapping

from .pr_status import PrStatus
from .pr_status_transitions import TERMINAL_PR_STATUSES, _parse_current, transition_to_escalated
from .state_keys import (
    ESCALATION_CONTEXT_KEY,
    ESCALATION_PENDING_NOTIFY_KEY,
    PR_STATUS_KEY,
)

logger = logging.getLogger(__name__)

EscalationTier = Literal["notify_only", "full"]

_RECOMMENDED_ACTIONS: dict[str, str] = {
    "no_vendors_discovered": "Onboard vendors for this product or correct catalog data.",
    "no_vendor_available": "Review negotiation outcomes and select an alternate supplier.",
    "negotiation_max_rounds": "Review vendor terms and decide whether to renegotiate or cancel.",
    "negotiator_stall": "Review stalled negotiations and intervene with vendors.",
    "po_rejected": "Review PO rejection reason and regenerate or cancel the order.",
    "invoice_mismatch": "Review invoice discrepancies and request vendor correction.",
    "purchase_stall": "Review purchase phase blockers and approve or correct workflow state.",
    "manual_vendor_thread": "Review escalated vendor thread and decide next action.",
    "loop_exhausted": "Review workflow state — agent loop exhausted without completion.",
}


def _phase_for_status(status: PrStatus) -> str:
    if status in {
        PrStatus.INITIATED,
        PrStatus.VENDORS_DISCOVERED,
        PrStatus.NO_VENDORS_DISCOVERED,
    }:
        return "rfq"
    if status in {
        PrStatus.NEGOTIATION_IN_PROGRESS,
        PrStatus.NEGOTIATION_COMPLETED,
        PrStatus.NO_VENDOR_AVAILABLE,
        PrStatus.ESCALATED,
    }:
        return "neg"
    if status in {
        PrStatus.VENDOR_SELECTED,
        PrStatus.PO_ISSUED,
        PrStatus.PO_ACKNOWLEDGED,
        PrStatus.PO_REJECTED,
        PrStatus.AWAITING_PO_APPROVAL,
        PrStatus.AWAITING_GRN_APPROVAL,
    }:
        return "po"
    return "inv"


def record_escalation_context(
    state: MutableMapping[str, Any],
    *,
    tier: EscalationTier,
    source: str,
    reason: str,
    vendor_id: str | None = None,
    rfq_id: str | None = None,
    recommended_action: str | None = None,
) -> None:
    """Write escalation metadata and flag the API layer to send email once."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    state[ESCALATION_CONTEXT_KEY] = {
        "tier": tier,
        "source": source,
        "reason": reason,
        "trigger_status": current.value,
        "phase": _phase_for_status(current),
        "vendor_id": vendor_id,
        "rfq_id": rfq_id,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "recommended_action": recommended_action
        or _RECOMMENDED_ACTIONS.get(source, "Review the workflow and take appropriate action."),
    }
    state[ESCALATION_PENDING_NOTIFY_KEY] = True
    logger.info(
        "escalation.recorded tier=%s source=%s trigger_status=%s",
        tier,
        source,
        current.value,
    )


def maybe_notify_only(
    state: MutableMapping[str, Any],
    *,
    source: str,
    reason: str,
    vendor_id: str | None = None,
    rfq_id: str | None = None,
    recommended_action: str | None = None,
) -> None:
    """Notify-only escalation: keep current pr_status, queue email."""
    if state.get(ESCALATION_PENDING_NOTIFY_KEY):
        return
    record_escalation_context(
        state,
        tier="notify_only",
        source=source,
        reason=reason,
        vendor_id=vendor_id,
        rfq_id=rfq_id,
        recommended_action=recommended_action,
    )


def maybe_escalate_full(
    state: MutableMapping[str, Any],
    *,
    source: str,
    reason: str,
    vendor_id: str | None = None,
    rfq_id: str | None = None,
    recommended_action: str | None = None,
) -> None:
    """Full escalation: set pr_status to ESCALATED and queue email."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current == PrStatus.ESCALATED:
        return
    if current in TERMINAL_PR_STATUSES:
        maybe_notify_only(
            state,
            source=source,
            reason=reason,
            vendor_id=vendor_id,
            rfq_id=rfq_id,
            recommended_action=recommended_action,
        )
        return
    record_escalation_context(
        state,
        tier="full",
        source=source,
        reason=reason,
        vendor_id=vendor_id,
        rfq_id=rfq_id,
        recommended_action=recommended_action,
    )
    transition_to_escalated(state)


__all__ = [
    "maybe_escalate_full",
    "maybe_notify_only",
    "record_escalation_context",
]
