"""Update ``session.state`` ``pr_status`` as the procurement workflow advances."""

from __future__ import annotations

import logging
from typing import Any, Mapping, MutableMapping

from .pr_status import PrStatus
from .state_keys import (
    INVOICE_VENDOR_ACK_KEY,
    NEGOTIATION_CONFIG_KEY,
    PO_VENDOR_ACK_KEY,
    PR_STATUS_KEY,
    PREVIOUS_PR_STATUS_KEY,
    PROCESS_COMPLETE_VENDOR_ACK_KEY,
    RFQ_CLOSED_LOSERS_KEY,
    SELECTED_VENDOR_KEY,
    VENDOR_OFFERS_KEY,
)

logger = logging.getLogger(__name__)

_STATUS_CHANGED_BANNER = "------ status changed -----"

TERMINAL_PR_STATUSES: frozenset[PrStatus] = frozenset(
    {
        PrStatus.COMPLETED,
        PrStatus.CANCELLED,
        PrStatus.NO_VENDORS_DISCOVERED,
        PrStatus.NO_VENDOR_AVAILABLE,
    }
)

HUMAN_GATED_PR_STATUSES: frozenset[PrStatus] = frozenset(
    {
        PrStatus.ESCALATED,
        # AWAITING_USER_APPROVAL is not in this set: the API's /approve endpoint
        # advances it to PO_ISSUED directly via a state_delta event, so the agent
        # never needs to gate on it. The enum value is retained for API consumers.
        PrStatus.READY_FOR_PAYMENT,
        # Vendor-driven or external-trigger states: stop the loop, require API action to resume
        PrStatus.AWAITING_DELIVERY,
        PrStatus.GOODS_RECEIVED,
        PrStatus.AWAITING_INVOICE,
        PrStatus.INVOICE_CORRECTION_PENDING,
        PrStatus.INVOICE_VERIFIED,
        PrStatus.PO_REJECTED,
        # Human-in-the-loop approval gates: the purchase_manager's before-callback
        # parks the loop at these when ``approval_required`` is set in session
        # state. ``POST /workflow/{id}/approve`` transitions back to the active
        # status for the matching step.
        PrStatus.AWAITING_PO_APPROVAL,
        PrStatus.AWAITING_GRN_APPROVAL,
        PrStatus.AWAITING_COMPLETION_APPROVAL,
    }
)

STOP_PR_STATUSES: frozenset[PrStatus] = TERMINAL_PR_STATUSES | HUMAN_GATED_PR_STATUSES

_NEGOTIATION_SOURCE_STATUSES: frozenset[PrStatus] = frozenset(
    {
        PrStatus.VENDORS_DISCOVERED,
        PrStatus.NEGOTIATION_IN_PROGRESS,
    }
)

_INITIATION_PHASE: frozenset[PrStatus] = frozenset(
    {
        PrStatus.INITIATED,
        PrStatus.VENDORS_DISCOVERED,
        PrStatus.NO_VENDORS_DISCOVERED,
    }
)


def _parse_current(raw: object | None) -> PrStatus:
    if raw is None or raw == "":
        return PrStatus.INITIATED
    if isinstance(raw, PrStatus):
        return raw
    try:
        return PrStatus(str(raw))
    except ValueError:
        return PrStatus.INITIATED


def _set(state: MutableMapping[str, Any], current: PrStatus, new: PrStatus) -> None:
    state[PREVIOUS_PR_STATUS_KEY] = current.value
    state[PR_STATUS_KEY] = new.value
    logger.info(_STATUS_CHANGED_BANNER)
    logger.info("pr_status %s -> %s", current.value, new.value)


# ── vendor discovery ──────────────────────────────────────────────────────────

def transition_after_vendor_discovery(
    state: MutableMapping[str, Any],
    *,
    offer_count: int,
) -> None:
    """Set VENDORS_DISCOVERED or NO_VENDORS_DISCOVERED after offers load."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current not in _INITIATION_PHASE:
        return

    new = PrStatus.VENDORS_DISCOVERED if offer_count > 0 else PrStatus.NO_VENDORS_DISCOVERED
    if new == current:
        return
    _set(state, current, new)


# ── negotiation ───────────────────────────────────────────────────────────────

def _targeted_vendor_ids(state: Mapping[str, Any]) -> list[str]:
    """Return the vendor ids the negotiator is expected to work through.

    Scans ``vendor_offers.offers`` for ``vendor_id`` entries — the field name
    used by ``load_vendor_offers_for_product``.
    """
    block = state.get(VENDOR_OFFERS_KEY)
    if not isinstance(block, dict):
        return []

    offers = block.get("offers")
    if not isinstance(offers, list):
        return []

    ids: list[str] = []
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        vid = offer.get("vendor_id") or offer.get("vendorId")
        if isinstance(vid, str) and vid.strip():
            ids.append(vid.strip())
    return ids


def transition_to_negotiation_in_progress(state: MutableMapping[str, Any]) -> None:
    """Flip VENDORS_DISCOVERED -> NEGOTIATION_IN_PROGRESS at negotiator start.

    Idempotent: no-op if already ``NEGOTIATION_IN_PROGRESS`` or past it.
    """
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current != PrStatus.VENDORS_DISCOVERED:
        return
    _set(state, current, PrStatus.NEGOTIATION_IN_PROGRESS)


def transition_after_negotiation(state: MutableMapping[str, Any]) -> None:
    """Advance to NEGOTIATION_IN_PROGRESS or NEGOTIATION_COMPLETED.

    Reads ``negotiation_config`` and the targeted vendor set (see
    :func:`_targeted_vendor_ids`). The status advances to
    ``NEGOTIATION_COMPLETED`` only when **every** targeted vendor has a
    terminal config entry (``done == True``, set when the buyer sends a closing
    ``ACCEPT`` / ``WALKAWAY``). Otherwise the status sits at
    ``NEGOTIATION_IN_PROGRESS`` so ``pr_router`` keeps delegating back to
    ``negotiator_agent``.
    """
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current not in _NEGOTIATION_SOURCE_STATUSES:
        return

    targeted = _targeted_vendor_ids(state)
    nego = state.get(NEGOTIATION_CONFIG_KEY) or {}

    if not targeted:
        all_done = False
    else:
        all_done = all(
            isinstance(nego.get(vid), dict) and nego[vid].get("done")
            for vid in targeted
        )

    new = PrStatus.NEGOTIATION_COMPLETED if all_done else PrStatus.NEGOTIATION_IN_PROGRESS
    if new.value == state.get(PR_STATUS_KEY):
        return
    _set(state, current, new)


# ── decision ──────────────────────────────────────────────────────────────────

def transition_after_decision(state: MutableMapping[str, Any]) -> None:
    """NEGOTIATION_COMPLETED -> VENDOR_SELECTED."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current == PrStatus.VENDOR_SELECTED:
        return
    if current != PrStatus.NEGOTIATION_COMPLETED:
        return
    _set(state, current, PrStatus.VENDOR_SELECTED)


# ── purchase flow ─────────────────────────────────────────────────────────────

def transition_to_awaiting_user_approval(state: MutableMapping[str, Any]) -> None:
    """Legacy alias: automated flow skips approval and issues the PO immediately."""
    transition_to_po_issued(state)


def transition_to_po_issued(state: MutableMapping[str, Any]) -> None:
    """Advance to PO_ISSUED once a vendor is selected (no human approval step)."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current == PrStatus.PO_ISSUED:
        return
    if current not in (PrStatus.VENDOR_SELECTED, PrStatus.AWAITING_USER_APPROVAL):
        return
    _set(state, current, PrStatus.PO_ISSUED)


def transition_to_po_acknowledged(state: MutableMapping[str, Any]) -> None:
    """PO_ISSUED -> PO_ACKNOWLEDGED after vendor acknowledges the PO."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current != PrStatus.PO_ISSUED:
        return
    _set(state, current, PrStatus.PO_ACKNOWLEDGED)


def transition_to_invoice_under_verification(state: MutableMapping[str, Any]) -> None:
    """PO_ACKNOWLEDGED -> INVOICE_UNDER_VERIFICATION after GRN sent and invoice received."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current != PrStatus.PO_ACKNOWLEDGED:
        return
    _set(state, current, PrStatus.INVOICE_UNDER_VERIFICATION)


def transition_to_completed(state: MutableMapping[str, Any]) -> None:
    """INVOICE_UNDER_VERIFICATION -> COMPLETED after PROCESS_COMPLETE is sent."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current != PrStatus.INVOICE_UNDER_VERIFICATION:
        return
    _set(state, current, PrStatus.COMPLETED)


def transition_to_escalated(state: MutableMapping[str, Any]) -> None:
    """Move to ESCALATED when an automated step stalls or cannot be recovered."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current == PrStatus.ESCALATED:
        return
    if current in TERMINAL_PR_STATUSES:
        return
    _set(state, current, PrStatus.ESCALATED)


def transition_to_po_rejected(state: MutableMapping[str, Any]) -> None:
    """PO_ISSUED -> PO_REJECTED when vendor rejects the PO."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current == PrStatus.PO_REJECTED:
        return
    if current != PrStatus.PO_ISSUED:
        return
    _set(state, current, PrStatus.PO_REJECTED)


def transition_to_invoice_correction_pending(state: MutableMapping[str, Any]) -> None:
    """INVOICE_UNDER_VERIFICATION -> INVOICE_CORRECTION_PENDING on mismatch."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current == PrStatus.INVOICE_CORRECTION_PENDING:
        return
    if current not in {
        PrStatus.INVOICE_UNDER_VERIFICATION,
        PrStatus.INVOICE_CORRECTION_PENDING,
    }:
        return
    _set(state, current, PrStatus.INVOICE_CORRECTION_PENDING)


def transition_resume_for_escalated(state: MutableMapping[str, Any]) -> bool:
    """Restore pr_status from previous_pr_status after human resolves escalation."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current != PrStatus.ESCALATED:
        return False
    prev_raw = state.get(PREVIOUS_PR_STATUS_KEY)
    if not prev_raw:
        return False
    try:
        prev = PrStatus(str(prev_raw))
    except ValueError:
        return False
    _set(state, current, prev)
    return True


# ── HITL approval gates ───────────────────────────────────────────────────────
#
# Gate setters move pr_status FROM the active purchase-phase value TO an
# AWAITING_*_APPROVAL value. They are called from purchase_manager's
# before_agent_callback when ``approval_required`` is set and the matching
# step has not yet been approved.
#
# Resume helpers do the reverse: they move pr_status FROM the gate value back
# TO the active value so the existing ack-driven sync chain can run. They are
# called from ``WorkflowService.approve`` after the human clicks the CTA.

def transition_to_awaiting_po_approval(state: MutableMapping[str, Any]) -> None:
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current == PrStatus.AWAITING_PO_APPROVAL:
        return
    if current != PrStatus.VENDOR_SELECTED:
        return
    _set(state, current, PrStatus.AWAITING_PO_APPROVAL)


def transition_to_awaiting_grn_approval(state: MutableMapping[str, Any]) -> None:
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current == PrStatus.AWAITING_GRN_APPROVAL:
        return
    if current != PrStatus.PO_ACKNOWLEDGED:
        return
    _set(state, current, PrStatus.AWAITING_GRN_APPROVAL)


def transition_to_awaiting_completion_approval(state: MutableMapping[str, Any]) -> None:
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current == PrStatus.AWAITING_COMPLETION_APPROVAL:
        return
    if current != PrStatus.INVOICE_UNDER_VERIFICATION:
        return
    _set(state, current, PrStatus.AWAITING_COMPLETION_APPROVAL)


def transition_resume_for_po(state: MutableMapping[str, Any]) -> None:
    """AWAITING_PO_APPROVAL -> VENDOR_SELECTED so the ack-sync chain can run send_po."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current != PrStatus.AWAITING_PO_APPROVAL:
        return
    _set(state, current, PrStatus.VENDOR_SELECTED)


def transition_resume_for_grn(state: MutableMapping[str, Any]) -> None:
    """AWAITING_GRN_APPROVAL -> PO_ACKNOWLEDGED so the chain can run send_grn_created."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current != PrStatus.AWAITING_GRN_APPROVAL:
        return
    _set(state, current, PrStatus.PO_ACKNOWLEDGED)


def transition_resume_for_completion(state: MutableMapping[str, Any]) -> None:
    """AWAITING_COMPLETION_APPROVAL -> INVOICE_UNDER_VERIFICATION so send_process_complete runs."""
    current = _parse_current(state.get(PR_STATUS_KEY))
    if current != PrStatus.AWAITING_COMPLETION_APPROVAL:
        return
    _set(state, current, PrStatus.INVOICE_UNDER_VERIFICATION)


def _losing_vendor_ids(state: Mapping[str, Any]) -> list[str]:
    selected = state.get(SELECTED_VENDOR_KEY)
    selected_id = None
    if isinstance(selected, dict):
        raw = selected.get("vendor")
        if isinstance(raw, str) and raw.strip():
            selected_id = raw.strip()
    if not selected_id:
        return []
    nego = state.get(NEGOTIATION_CONFIG_KEY) or {}
    if not isinstance(nego, dict):
        return []
    return [vid for vid in nego if vid != selected_id]


def _all_losing_vendors_notified(state: Mapping[str, Any]) -> bool:
    losing = _losing_vendor_ids(state)
    if not losing:
        return True
    raw = state.get(RFQ_CLOSED_LOSERS_KEY) or {}
    if not isinstance(raw, dict):
        return False
    closed = {str(k) for k, v in raw.items() if v}
    return all(vid in closed for vid in losing)


def sync_purchase_pr_status_from_acks(state: MutableMapping[str, Any]) -> bool:
    """Advance purchase-phase ``pr_status`` from vendor-confirmed ack keys.

    RFQ_CLOSED to losers is best-effort: ``po_vendor_ack`` alone can unblock
    ``VENDOR_SELECTED`` → ``PO_ISSUED``. Returns True if any transition ran.
    """
    before = _parse_current(state.get(PR_STATUS_KEY))
    changed = False

    while True:
        current = _parse_current(state.get(PR_STATUS_KEY))
        if current == PrStatus.VENDOR_SELECTED:
            can_issue = _all_losing_vendors_notified(state) or bool(
                state.get(PO_VENDOR_ACK_KEY)
            )
            if not can_issue:
                break
            if state.get(PO_VENDOR_ACK_KEY) and not _all_losing_vendors_notified(state):
                logger.warning(
                    "rfq_closed_incomplete advancing on po_vendor_ack losers=%s closed=%s",
                    _losing_vendor_ids(state),
                    sorted((state.get(RFQ_CLOSED_LOSERS_KEY) or {}).keys()),
                )
            transition_to_po_issued(state)
            if _parse_current(state.get(PR_STATUS_KEY)) != current:
                changed = True
            continue

        if current == PrStatus.PO_ISSUED:
            if not state.get(PO_VENDOR_ACK_KEY):
                break
            transition_to_po_acknowledged(state)
            if _parse_current(state.get(PR_STATUS_KEY)) != current:
                changed = True
            continue

        if current == PrStatus.PO_ACKNOWLEDGED:
            if not state.get(INVOICE_VENDOR_ACK_KEY):
                break
            transition_to_invoice_under_verification(state)
            if _parse_current(state.get(PR_STATUS_KEY)) != current:
                changed = True
            continue

        if current == PrStatus.INVOICE_UNDER_VERIFICATION:
            if not state.get(PROCESS_COMPLETE_VENDOR_ACK_KEY):
                break
            transition_to_completed(state)
            if _parse_current(state.get(PR_STATUS_KEY)) != current:
                changed = True
            continue

        break

    if changed:
        logger.info(
            "purchase_status_sync %s -> %s",
            before.value,
            _parse_current(state.get(PR_STATUS_KEY)).value,
        )
    return changed


# ── legacy stub (superseded by specific purchase-flow transitions above) ──────

def transition_after_fulfillment(state: MutableMapping[str, Any]) -> None:
    """Deprecated stub kept for backwards compatibility. No-op."""
    pass


# ── helpers ───────────────────────────────────────────────────────────────────

def pr_status_line(state: Mapping[str, Any]) -> str:
    """Compact pr_status / previous_pr_status for log lines."""
    cur = state.get(PR_STATUS_KEY)
    prev = state.get(PREVIOUS_PR_STATUS_KEY)
    cur_s = str(cur) if cur not in (None, "") else "?"
    prev_s = str(prev) if prev not in (None, "") else "-"
    return "pr_status=%s previous_pr_status=%s" % (cur_s, prev_s)
